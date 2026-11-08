from dataclasses import asdict, replace
from uuid import uuid4
import pytest
from mira.budget import BudgetTracker, RunBudget
from mira.contracts import FrozenPassage
from mira.corroboration import (AssessmentBatch, CandidateDecision, CandidateEvidence, CorroborationService,
    DiscoveryFailure, LlmAssessor, OriginEvidence, Proposition, SearchLimits)
from mira.evidence_snapshot import build_verification_input
from mira.llm import LLMError, LLMResult
from mira.store import SourceRecord
from test_evidence_snapshot import inputs


def fixture():
    ctx, claim, _, record = inputs()
    record = replace(record, content="Authority's own investigation: Bank A holds 10 units.")
    claim = replace(claim, draft=claim.draft.model_copy(update={"content": "Bank A holds 10 units.", "title": "Bank A holdings"}), evidence=(replace(claim.evidence[0], supporting_quote=record.content),))
    primary = FrozenPassage(**asdict(record))
    p = primary.model_copy(update={"id": uuid4(), "document_id": uuid4(), "document_version_id": uuid4(),
        "source_id": uuid4(), "source_url": "https://second.test/report",
        "content": "Our own investigation found Bank A holds 10 units."})
    sources = [SourceRecord(x.source_id, x.source_name, "regulator", x.source_url, "SG", ("fetch", "store_text"))
               for x in (primary, p)]
    base = build_verification_input(ctx, claim, {}, {record.id: record}).model_dump(mode="json")
    prop = Proposition(entity=["Bank A"], jurisdiction="SG", predicate="holds", scope="current units",
                       dates=[], quantities=["10 units"], regulatory_status=None)
    decision = CandidateDecision(passage_id=p.id, quote=p.content, proposition=prop, relation="supports",
        origin_relation="independent", origin_evidence=[OriginEvidence(passage_id=x.id, quote=x.content,
        kind="original_reporting", reason="Own investigation") for x in (primary, p)], reason="Same proposition")
    batch = AssessmentBatch(proposition=prop, decisions=[decision], model="fixture", prompt_version="fixture/1",
                            tokens_in=3, tokens_out=4)
    return dict(ctx=ctx, claim=claim, base_evidence_input=base, sources=sources, budget=BudgetTracker(ctx.budget),
                saved_candidates=[CandidateEvidence(passage=p, workspace_id=ctx.workspace_id)]), batch, primary


class Assessor:
    def __init__(self, batch): self.batch, self.calls = batch, 0
    def assess(self, *args, **kwargs):
        self.calls += 1
        return self.batch


def test_independent_support_freezes_evidence_and_charges_usage_once():
    args, batch, _ = fixture()
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "independently_corroborated"
    assert args["budget"].tokens_used == 7
    assert result.tokens_in == 3 and result.tokens_out == 4
    assert result.candidates[0].passage.content == result.decisions[0].quote
    assert result.model_dump(mode="json")["base_evidence_input"]


@pytest.mark.parametrize("update", [{"origin_relation": "unknown"}, {"origin_evidence": []},
                                    {"quote": "fabricated"}])
def test_invalid_independence_never_corroborates(update):
    args, batch, _ = fixture()
    batch = batch.model_copy(update={"decisions": [batch.decisions[0].model_copy(update=update)]})
    assert CorroborationService(Assessor(batch)).assess(**args).status == "inconclusive"


def test_entity_mismatch_cannot_support():
    args, batch, _ = fixture()
    batch.decisions[0] = batch.decisions[0].model_copy(update={"proposition": batch.proposition.model_copy(update={"entity": ["B"]})})
    assert CorroborationService(Assessor(batch)).assess(**args).status == "inconclusive"


def test_authoritative_single_source_is_not_false():
    args, _, _ = fixture()
    # Unassessed candidate evidence could conflict: it is explicitly inconclusive.
    assert CorroborationService().assess(**args, authoritative_primary=True).status == "inconclusive"
    assert CorroborationService().assess(**args).status == "inconclusive"
    args["saved_candidates"] = []
    assert CorroborationService().assess(**args, authoritative_primary=True).status == "primary_source_only"


def test_conflict_precedes_independent_support():
    args, batch, _ = fixture()
    p = args["saved_candidates"][0].passage.model_copy(update={"id": uuid4(), "content": "Bank A holds 20 units."})
    args["saved_candidates"].append(CandidateEvidence(passage=p, workspace_id=args["ctx"].workspace_id))
    batch.decisions.append(batch.decisions[0].model_copy(update={"passage_id": p.id, "quote": p.content,
        "relation": "contradicts", "origin_relation": "unknown",
        "proposition": batch.proposition.model_copy(update={"quantities": ["20 units"]})}))
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "conflicting_evidence" and result.decisions[1].quote == p.content


@pytest.mark.parametrize("update", [{"workspace_id": uuid4()}, {"eligible": False}, {"current": False}])
def test_ineligible_candidates_never_reach_assessor(update):
    args, batch, _ = fixture()
    args["saved_candidates"][0] = args["saved_candidates"][0].model_copy(update=update)
    fake = Assessor(batch)
    result = CorroborationService(fake).assess(**args)
    assert not result.candidates and fake.calls == 0


def test_same_source_overrides_independence():
    args, batch, primary = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"][0] = c.model_copy(update={"passage": c.passage.model_copy(update={"source_id": primary.source_id})})
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "inconclusive" and result.decisions[0].origin_relation == "dependent"


def test_run_budget_prevents_work():
    args, batch, _ = fixture()
    args["budget"] = BudgetTracker(RunBudget(max_llm_tokens=0))
    fake = Assessor(batch)
    result = CorroborationService(fake).assess(**args)
    assert fake.calls == 0 and "run_budget_exhausted" in result.stop_reasons


def test_failed_assessor_charges_known_usage():
    class Failing:
        def assess(self, *args, **kwargs): raise LLMError("failed", 13, 7)
    args, _, _ = fixture()
    result = CorroborationService(Failing()).assess(**args)
    assert args["budget"].tokens_used == 20 and result.tokens_in == 13
    assert "assessment_failed" in result.stop_reasons


def test_discovery_failure_charges_attempts():
    class Failing:
        def discover(self, *args, **kwargs): raise DiscoveryFailure("failed", document_attempts=1, tokens_in=2, tokens_out=1)
    args, _, _ = fixture()
    result = CorroborationService(discovery=Failing()).assess(**args, limits=SearchLimits(max_queries=1))
    assert result.queries_used == 1 and result.document_attempts == 1
    assert args["budget"].documents_fetched == 1 and args["budget"].tokens_used == 3
    assert "acquisition_failed" in result.stop_reasons


def test_enriched_base_is_rejected():
    args, _, _ = fixture()
    args["base_evidence_input"]["corroboration"] = {"bad": "recursive"}
    with pytest.raises(ValueError, match="base"):
        CorroborationService().assess(**args)


def test_llm_uses_one_bounded_verifier_call():
    args, batch, primary = fixture()
    class Client:
        calls = []
        def structured_bounded(self, **kwargs):
            self.calls.append(kwargs)
            decision = batch.decisions[0].model_dump(exclude={"passage_id", "origin_evidence"})
            decision["passage_label"] = "P2"
            decision["origin_evidence"] = [dict(passage_label=f"P{i}", quote=e.quote, kind=e.kind, reason=e.reason)
                                           for i,e in enumerate(batch.decisions[0].origin_evidence, 1)]
            output = kwargs["output_type"](proposition=batch.proposition, decisions=[decision])
            return LLMResult(output, "fixture", "fixture/1", 3, 4)
    client = Client()
    result = LlmAssessor(client).assess(args["claim"], [primary], args["saved_candidates"], timeout_seconds=5, max_tokens=100000)
    assert result.tokens_in == 3 and len(client.calls) == 1
    assert client.calls[0]["role"] == "verifier" and client.calls[0]["max_output_tokens"] < 100000


def test_llm_refuses_too_small_budget_without_call():
    args, batch, primary = fixture()
    with pytest.raises(LLMError, match="budget"):
        LlmAssessor(object()).assess(args["claim"], [primary], args["saved_candidates"], timeout_seconds=5, max_tokens=1)


@pytest.mark.parametrize("dimension,value", [("dates", ["2026-01-02"]), ("quantities", ["20 units"]),
    ("regulatory_status", "proposed"), ("jurisdiction", "HK"), ("scope", "prior year")])
def test_material_dimension_mismatch_does_not_support(dimension, value):
    args, batch, _ = fixture()
    batch.decisions[0] = batch.decisions[0].model_copy(update={"proposition": batch.proposition.model_copy(update={dimension:value})})
    assert CorroborationService(Assessor(batch)).assess(**args).status == "inconclusive"


@pytest.mark.parametrize("mechanism", ["document", "text", "capture_hash", "organization", "origin", "publication", "syndication"])
def test_mirrors_shared_origins_and_copies_are_dependent(mechanism):
    args, batch, primary = fixture()
    c = args["saved_candidates"][0]
    if mechanism == "document":
        c = c.model_copy(update={"passage": c.passage.model_copy(update={"document_id": primary.document_id})})
    elif mechanism == "text":
        c = c.model_copy(update={"passage": c.passage.model_copy(update={"content": primary.content})})
        batch.decisions[0] = batch.decisions[0].model_copy(update={"quote": primary.content,
            "origin_evidence": [e.model_copy(update={"quote": primary.content}) for e in batch.decisions[0].origin_evidence]})
    elif mechanism == "capture_hash":
        args["base_evidence_input"]["passages"][str(primary.id)]["acquisition_provenance"] = {"capture_sha256": "same"}
        c = c.model_copy(update={"passage": c.passage.model_copy(update={"acquisition_provenance": {"capture_sha256": "same"}})})
    elif mechanism in ("organization", "origin"):
        field = mechanism + "_id"
        c = c.model_copy(update={field: "shared"})
        args["sources"][0] = replace(args["sources"][0], connector_config={field: "shared"})
    elif mechanism == "publication":
        c = c.model_copy(update={"publication_id": str(primary.document_id)})
    else:
        batch.decisions[0] = batch.decisions[0].model_copy(update={"origin_evidence": [
            e.model_copy(update={"kind": "derivation"}) for e in batch.decisions[0].origin_evidence]})
    args["saved_candidates"][0] = c
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "inconclusive" and result.decisions[0].origin_relation == "dependent"


def test_composite_content_hash_is_not_capture_hash():
    args, batch, primary = fixture()
    args["base_evidence_input"]["passages"][str(primary.id)]["content_sha256"] = "composite"
    c = args["saved_candidates"][0]
    args["saved_candidates"][0] = c.model_copy(update={"passage": c.passage.model_copy(update={"content_sha256": "composite"})})
    assert CorroborationService(Assessor(batch)).assess(**args).status == "independently_corroborated"


def test_inference_is_not_checked():
    args, _, _ = fixture()
    args["claim"] = replace(args["claim"], draft=args["claim"].draft.model_copy(update={"is_inference": True}))
    args["base_evidence_input"]["findings"][str(args["claim"].finding_id)]["is_inference"] = True
    assert CorroborationService().assess(**args).status == "not_checked"


def test_unknown_publication_date_is_preserved_and_future_date_rejected():
    from datetime import date
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"][0] = c.model_copy(update={"passage": c.passage.model_copy(update={"published_at": date(2030,1,1)})})
    fake = Assessor(batch)
    assert not CorroborationService(fake).assess(**args).candidates and fake.calls == 0


def test_no_store_permission_refuses_candidate():
    args, batch, _ = fixture()
    args["sources"][1] = replace(args["sources"][1], permitted_operations=("fetch",))
    assert not CorroborationService(Assessor(batch)).assess(**args).candidates


def test_saved_candidate_caps_and_no_repeated_assessment():
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"] = [c, c] + [c.model_copy(update={"passage": c.passage.model_copy(update={
        "id": uuid4(), "document_id": uuid4(), "document_version_id": uuid4()})}) for i in range(8)]
    result = CorroborationService().assess(**args, limits=SearchLimits(max_documents=2, max_passages=2))
    assert len(result.candidates) == 2 and result.passages_checked == 2


def test_failed_discovery_and_saved_documents_share_claim_cap():
    class Failing:
        caps=[]
        def discover(self, *args, **kwargs):
            self.caps.append(kwargs["max_documents"])
            raise DiscoveryFailure("failed", document_attempts=kwargs["max_documents"])
    args, _, _ = fixture()
    callback = Failing()
    result = CorroborationService(discovery=callback).assess(**args)
    assert callback.caps == [4] and result.document_attempts == 4 and result.queries_used == 1


def test_late_semantic_result_cannot_corroborate_but_usage_is_charged():
    args, batch, _ = fixture()
    class Clock:
        value=0
        def __call__(self): return self.value
    clock=Clock()
    class Late:
        def assess(self, *args, **kwargs):
            clock.value = 31
            return batch
    result = CorroborationService(Late(), clock=clock).assess(**args)
    assert result.status == "inconclusive" and "time_limit" in result.stop_reasons
    assert args["budget"].tokens_used == 7


def test_frozen_validator_rejects_tampering_and_uses_no_live_evidence():
    from mira.corroboration import validate_frozen_assessment
    args, batch, _ = fixture()
    result = CorroborationService(Assessor(batch)).assess(**args)
    validate_frozen_assessment(result)
    for changed in [result.model_copy(update={"status": "conflicting_evidence"}),
        result.model_copy(update={"decisions": [result.decisions[0].model_copy(update={"quote": "fake"})]}),
        result.model_copy(update={"base_evidence_fingerprint": "wrong"})]:
        with pytest.raises(ValueError): validate_frozen_assessment(changed)


def test_discovery_never_receives_out_of_scope_source():
    args, _, _ = fixture()
    foreign = replace(args["sources"][0], id=uuid4(), jurisdiction_code="HK")
    args["sources"].append(foreign)
    class Capture:
        ids=[]
        def discover(self, query, **kwargs):
            self.ids.extend(kwargs["source_ids"])
            from mira.corroboration import DiscoveryBatch
            return DiscoveryBatch()
    callback=Capture()
    CorroborationService(discovery=callback).assess(**args)
    assert foreign.id not in callback.ids


def test_frozen_validator_rejects_missing_primary_and_fabricated_eligibility():
    from mira.corroboration import validate_frozen_assessment
    args, batch, _ = fixture()
    result = CorroborationService(Assessor(batch)).assess(**args)
    for changed in [result.model_copy(update={"primary": []}),
                    result.model_copy(update={"eligible": False, "status": "not_checked"})]:
        with pytest.raises(ValueError): validate_frozen_assessment(changed)


def test_unknown_usage_failed_bounded_call_reserves_tokens_separately():
    args, _, _ = fixture()
    class Client:
        def structured_bounded(self, **kwargs): raise LLMError("timeout")
    result = CorroborationService(LlmAssessor(Client())).assess(**args)
    assert result.status == "inconclusive"
    assert result.tokens_in == result.tokens_out == 0
    assert result.reserved_tokens > 0 and args["budget"].tokens_used == result.reserved_tokens


def test_unknown_passage_labels_fail_closed_with_reported_usage():
    args, batch, _ = fixture()
    class Client:
        def structured_bounded(self, **kwargs):
            decision = batch.decisions[0].model_dump(exclude={"passage_id", "origin_evidence"})
            decision.update(passage_label="P999", origin_evidence=[])
            return LLMResult(kwargs["output_type"](proposition=batch.proposition, decisions=[decision]), "fixture", "fixture", 3, 4)
    result = CorroborationService(LlmAssessor(Client())).assess(**args)
    assert result.status == "inconclusive" and args["budget"].tokens_used == 7


def test_missing_dimension_is_not_an_explicit_contradiction():
    args, batch, _ = fixture()
    batch.decisions[0] = batch.decisions[0].model_copy(update={"relation": "contradicts", "origin_relation": "unknown",
        "proposition": batch.proposition.model_copy(update={"quantities": []})})
    assert CorroborationService(Assessor(batch)).assess(**args).status == "inconclusive"


def test_wrong_jurisdiction_assessment_remains_valid_inconclusive_snapshot():
    from mira.corroboration import validate_frozen_assessment
    args, batch, _ = fixture()
    batch = batch.model_copy(update={"proposition": batch.proposition.model_copy(update={"jurisdiction": "HK"})})
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "inconclusive"
    validate_frozen_assessment(result)


@pytest.mark.parametrize("field", ["organization_id", "origin_id"])
def test_canonical_source_origin_overrides_supplied_candidate_default(field):
    from mira.corroboration import validate_frozen_assessment
    args, batch, _ = fixture()
    for i, source in enumerate(args["sources"]):
        args["sources"][i] = replace(source, connector_config={field: "shared-canonical-origin"})
    c = args["saved_candidates"][0]
    args["saved_candidates"][0] = c.model_copy(update={field: str(c.passage.source_id)})
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "inconclusive" and result.decisions[0].origin_relation == "dependent"
    assert getattr(result.candidates[0], field) == "shared-canonical-origin"
    validate_frozen_assessment(result)
    # Frozen canonical metadata still prevents erasing dependence after serialization.
    fake = result.model_copy(update={"candidates": [result.candidates[0].model_copy(update={field: "erased"})],
        "decisions": [result.decisions[0].model_copy(update={"origin_relation": "independent"})],
        "status": "independently_corroborated"})
    with pytest.raises(ValueError): validate_frozen_assessment(fake)


@pytest.mark.parametrize("invalid_second", ["omitted", "bad_quote", "uncertain"])
def test_incomplete_assessment_cannot_hide_second_candidate(invalid_second):
    from mira.corroboration import validate_frozen_assessment
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    second = c.model_copy(update={"passage": c.passage.model_copy(update={"id": uuid4(),
        "content": "Bank A holds 20 units."})})
    args["saved_candidates"].append(second)
    if invalid_second != "omitted":
        batch.decisions.append(batch.decisions[0].model_copy(update={"passage_id": second.passage.id,
            "quote": "absent" if invalid_second == "bad_quote" else second.passage.content,
            "relation": "uncertain"}))
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "inconclusive" and "incomplete_assessment" in result.stop_reasons
    validate_frozen_assessment(result)
    # A fabricated clean status fails even if its author removes the stop reason.
    fake = result.model_copy(update={"status": "independently_corroborated",
        "stop_reasons": [r for r in result.stop_reasons if r != "incomplete_assessment"]})
    with pytest.raises(ValueError): validate_frozen_assessment(fake)


def test_incomplete_assessment_preserves_known_conflict():
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"].append(c.model_copy(update={"passage": c.passage.model_copy(update={"id": uuid4()})}))
    batch.decisions[0] = batch.decisions[0].model_copy(update={"relation": "contradicts",
        "proposition": batch.proposition.model_copy(update={"quantities": ["20 units"]})})
    result = CorroborationService(Assessor(batch)).assess(**args)
    assert result.status == "conflicting_evidence" and "incomplete_assessment" in result.stop_reasons
