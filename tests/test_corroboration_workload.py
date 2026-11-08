"""Offline workload regressions: real prompt construction, no provider calls."""
import json
from uuid import uuid4

import pytest

from mira.corroboration import CorroborationService, LlmAssessor, validate_frozen_assessment
from mira.llm import LLMError, LLMResult
from test_corroboration import fixture


class RecordingClient:
    def __init__(self, batch, relation="supports"):
        self.batch, self.relation, self.calls = batch, relation, []

    def structured_bounded(self, **kwargs):
        self.calls.append(kwargs)
        data = json.loads(kwargs["user"])
        decisions = []
        for candidate in data["candidates"]:
            prop = self.batch.proposition
            if self.relation == "contradicts":
                prop = prop.model_copy(update={"quantities": ["20 units"]})
            decisions.append(dict(passage_label=candidate["passage_label"], quote=candidate["content"][:400],
                proposition=prop, relation=self.relation, origin_relation="unknown", origin_evidence=[],
                reason="Fixture semantic assessment"))
        if "decision" in kwargs["output_type"].model_fields:
            decisions[0].pop("passage_label")
            output = kwargs["output_type"](proposition=self.batch.proposition, decision=decisions[0])
        else:
            output = kwargs["output_type"](proposition=self.batch.proposition, decisions=decisions)
        return LLMResult(output, "fixture", "fixture", 50, 60)


def test_twenty_long_candidates_make_one_small_call_and_keep_originals():
    args, batch, _ = fixture()
    candidate = args["saved_candidates"][0]
    args["saved_candidates"] = [candidate.model_copy(update={"passage": candidate.passage.model_copy(
        update={"id": uuid4(), "content": ("Navigation boilerplate. " * 600) +
                f"Bank A holds {10 + i} units. " + ("Footer boilerplate. " * 600)})}) for i in range(20)]
    original = [c.model_dump() for c in args["saved_candidates"]]
    client = RecordingClient(batch)
    result = CorroborationService(LlmAssessor(client)).assess(**args)
    assert len(client.calls) == 1
    call = client.calls[0]
    payload = json.loads(call["user"])
    assert len(payload["candidates"]) == 1
    assert len(payload["primary"]) <= 2
    assert len(call["user"]) < 14000
    assert call["max_output_tokens"] <= 4096
    assert call["timeout_seconds"] <= 60
    assert all("Bank A holds" in c["content"] for c in payload["candidates"])
    assert [c.model_dump() for c in result.candidates] == [
        c.model_copy(update={"organization_id": str(c.passage.source_id)}).model_dump()
        for c in args["saved_candidates"]]
    assert [c.model_dump() for c in args["saved_candidates"]] == original
    assert result.status == "inconclusive" and "incomplete_assessment" in result.stop_reasons
    assert "assessment_workload_limit" in result.stop_reasons
    assert len(result.decisions) == 1
    assert args["budget"].tokens_used == 110
    validate_frozen_assessment(result)


@pytest.mark.parametrize("relation", ["supports", "contradicts"])
def test_excerpt_retains_evidence_but_cannot_validate_either_relation(relation):
    args, batch, primary = fixture()
    c = args["saved_candidates"][0]
    # Even known-dependent material must still receive the contradiction check.
    args["saved_candidates"] = [c.model_copy(update={"passage": c.passage.model_copy(update={
        "source_id": primary.source_id, "content": "Bank A holds 20 units. " + "Other text. " * 1000})})]
    client = RecordingClient(batch, relation)
    result = CorroborationService(LlmAssessor(client)).assess(**args, authoritative_primary=True)
    assert result.status == "inconclusive"
    assert result.decisions[0].origin_relation == "dependent"
    assert result.decisions[0].quote in result.candidates[0].passage.content
    assert result.decisions[0].relation == "uncertain"
    validate_frozen_assessment(result)


def test_unknown_failure_reserves_only_small_actual_prompt_and_output_allowance():
    args, _, primary = fixture()
    c = args["saved_candidates"][0]
    candidates = [c.model_copy(update={"passage": c.passage.model_copy(update={
        "id": uuid4(), "content": "Bank A holds 10 units. " * 3000})}) for _ in range(20)]
    class Failing:
        def structured_bounded(self, **kwargs):
            raise LLMError("timeout")
    with pytest.raises(LLMError) as caught:
        LlmAssessor(Failing()).assess(args["claim"], [primary], candidates,
                                     timeout_seconds=30, max_tokens=100000)
    assert 0 < caught.value.reserved_tokens < 30000


def test_primary_excerpt_anchors_exact_citation_and_cannot_hide_unread_text():
    args, batch, primary = fixture()
    quote = primary.content
    full = "Unrelated preamble. " * 700 + quote + " Unrelated appendix." * 700
    args["base_evidence_input"]["passages"][str(primary.id)]["content"] = full
    client = RecordingClient(batch)
    result = CorroborationService(LlmAssessor(client)).assess(**args, authoritative_primary=True)
    shown = json.loads(client.calls[0]["user"])["primary"][0]
    assert quote in shown["content"]
    assert full[shown["excerpt_start"]:shown["excerpt_end"]] == shown["content"]
    assert result.primary[0].content == full
    assert result.decisions[0].relation == "uncertain"
    validate_frozen_assessment(result)
    # Removing stop reasons must not make the bounded excerpt a complete check.
    tampered = result.model_copy(update={"status": "primary_source_only", "stop_reasons": [],
        "decisions": [result.decisions[0].model_copy(update={"relation": "supports"})]})
    with pytest.raises(ValueError):
        validate_frozen_assessment(tampered)


def test_quote_from_unshown_text_is_rejected_and_usage_charged():
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"] = [c.model_copy(update={"passage": c.passage.model_copy(update={
        "content": "Bank A holds 20 units. " + "Other text. " * 1000 + "UNSHOWN QUOTE"})})]
    class Unshown(RecordingClient):
        def structured_bounded(self, **kwargs):
            response = super().structured_bounded(**kwargs)
            decision = response.output.decision.model_copy(update={"quote": "UNSHOWN QUOTE"})
            return LLMResult(response.output.model_copy(update={"decision": decision}),
                             "fixture", "fixture", 50, 60)
    result = CorroborationService(LlmAssessor(Unshown(batch))).assess(**args)
    assert result.status == "inconclusive" and not result.decisions
    assert args["budget"].tokens_used == 110


def test_one_unshown_quote_does_not_discard_other_valid_contradiction():
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"].append(c.model_copy(update={"passage": c.passage.model_copy(update={"id": uuid4()})}))
    # Historical multi-decision batches still preserve the valid conflict.
    from test_corroboration import Assessor
    valid = batch.decisions[0].model_copy(update={"relation": "contradicts",
        "proposition": batch.proposition.model_copy(update={"quantities": ["20 units"]})})
    invalid = valid.model_copy(update={"passage_id": args["saved_candidates"][1].passage.id, "quote": "fabricated"})
    result = CorroborationService(Assessor(batch.model_copy(update={"decisions": [valid, invalid],
        "prompt_version": "corroboration/2-bounded-excerpts", "tokens_in": 50, "tokens_out": 60}))).assess(**args)
    assert result.status == "conflicting_evidence"
    assert len(result.decisions) == 1 and "incomplete_assessment" in result.stop_reasons
    assert args["budget"].tokens_used == 110
    validate_frozen_assessment(result)


@pytest.mark.parametrize("limited_side", ["candidate", "primary"])
def test_omitted_qualification_cannot_become_validated_conflict(limited_side):
    args, batch, primary = fixture()
    c = args["saved_candidates"][0]
    # The late qualifier changes the apparent temporal scope. It must not be
    # treated as read simply because the returned quotation is exact.
    qualifier = "The prior figure is historical; the current value is now 10."
    full = "Bank A holds 20 units. " + "Appendix detail. " * 1000 + qualifier
    if limited_side == "candidate":
        args["saved_candidates"] = [c.model_copy(update={"passage": c.passage.model_copy(
            update={"content": full})})]
    else:
        full = primary.content + " Appendix detail." * 1000 + qualifier
        args["base_evidence_input"]["passages"][str(primary.id)]["content"] = full
    client = RecordingClient(batch, "contradicts")
    result = CorroborationService(LlmAssessor(client)).assess(**args)
    shown = json.loads(client.calls[0]["user"])["candidates" if limited_side == "candidate" else "primary"][0]
    assert qualifier not in shown["content"]
    assert result.status == "inconclusive"
    assert result.decisions[0].relation == "uncertain"
    assert result.decisions[0].proposition.quantities == ["20 units"]
    assert "potential conflict" in result.decisions[0].reason
    assert result.decisions[0].quote in result.candidates[0].passage.content
    original = result.candidates[0].passage if limited_side == "candidate" else result.primary[0]
    assert original.content == full
    validate_frozen_assessment(result)
    tampered = result.model_copy(update={"status": "conflicting_evidence", "stop_reasons": [],
        "decisions": [result.decisions[0].model_copy(update={"relation": "contradicts"})]})
    with pytest.raises(ValueError, match="bounded excerpt"):
        validate_frozen_assessment(tampered)


class Clock:
    value = 0.0
    def __call__(self):
        return self.value


@pytest.mark.parametrize("elapsed,expected", [(45, "independently_corroborated"), (61, "inconclusive")])
def test_total_sixty_second_claim_deadline_accepts_timely_result_only(elapsed, expected):
    from mira.budget import BudgetTracker
    args, batch, _ = fixture()
    clock = Clock()
    args["budget"] = BudgetTracker(args["ctx"].budget, clock=clock)
    class Timed:
        def assess(self, *args, **kwargs):
            assert kwargs["timeout_seconds"] == 60
            clock.value = elapsed
            return batch
    result = CorroborationService(Timed(), clock=clock).assess(**args)
    assert result.status == expected
    assert result.limits.max_seconds == 60
    assert args["budget"].tokens_used == 7
    assert ("time_limit" in result.stop_reasons) == (elapsed > 60)


def test_shared_remaining_time_caps_whole_claim():
    from mira.budget import BudgetTracker, RunBudget
    args, batch, _ = fixture()
    clock = Clock()
    args["budget"] = BudgetTracker(RunBudget(max_run_minutes=25), clock=clock)
    clock.value = 25 * 60 - 12
    class Timed:
        def assess(self, *args, **kwargs):
            assert kwargs["timeout_seconds"] == pytest.approx(12)
            clock.value += 13
            return batch
    result = CorroborationService(Timed(), clock=clock).assess(**args)
    assert result.status == "inconclusive" and "time_limit" in result.stop_reasons
    assert args["budget"].tokens_used == 7


def test_acquisition_uses_same_total_deadline_not_a_new_window():
    from mira.budget import BudgetTracker
    from mira.corroboration import DiscoveryBatch
    args, batch, _ = fixture()
    candidates, args["saved_candidates"] = args["saved_candidates"], []
    clock = Clock()
    args["budget"] = BudgetTracker(args["ctx"].budget, clock=clock)
    class Discovery:
        def discover(self, *args, **kwargs):
            assert kwargs["timeout_seconds"] == 60
            clock.value += 20
            return DiscoveryBatch(candidates=candidates)
    class Timed:
        def assess(self, *args, **kwargs):
            assert kwargs["timeout_seconds"] == 40
            clock.value += 25
            return batch
    result = CorroborationService(Timed(), Discovery(), clock=clock).assess(**args)
    assert result.status == "independently_corroborated" and result.elapsed_seconds == 45
    assert result.queries_used == 1


def test_one_assessor_attempt_even_if_failure_returns_before_deadline():
    from mira.corroboration import DiscoveryBatch
    args, _, _ = fixture()
    calls = []
    class Failing:
        def assess(self, *args, **kwargs):
            calls.append(kwargs)
            exc = LLMError("unknown failure")
            exc.reserved_tokens = 1200
            raise exc
    class Discovery:
        def discover(self, *positional, **kwargs):
            c = args["saved_candidates"][0]
            return DiscoveryBatch(candidates=[c.model_copy(update={"passage": c.passage.model_copy(
                update={"id": uuid4()})})])
    result = CorroborationService(Failing(), Discovery()).assess(**args)
    assert len(calls) == 1 and result.queries_used == 0
    assert result.reserved_tokens == args["budget"].tokens_used == 1200
    assert result.status == "inconclusive"


@pytest.mark.parametrize("version", ["corroboration/1", "corroboration/2-bounded-excerpts"])
def test_legacy_thirty_second_frozen_results_keep_original_limits(version):
    from mira.corroboration import SearchLimits
    from test_corroboration import Assessor
    args, batch, _ = fixture()
    batch = batch.model_copy(update={"prompt_version": version})
    result = CorroborationService(Assessor(batch)).assess(**args, limits=SearchLimits(max_seconds=30))
    serialized = result.model_dump(mode="json")
    validate_frozen_assessment(type(result).model_validate(serialized))
    assert serialized["limits"]["max_seconds"] == 30
    assert result.status == "independently_corroborated"


def test_legacy_v2_truncated_conflict_promotion_remains_rejected():
    from test_corroboration import Assessor
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"][0] = c.model_copy(update={"passage": c.passage.model_copy(
        update={"content": c.passage.content + " appendix" * 1000})})
    decision = batch.decisions[0].model_copy(update={"relation": "uncertain",
        "proposition": batch.proposition.model_copy(update={"quantities": ["20 units"]})})
    result = CorroborationService(Assessor(batch.model_copy(update={"decisions": [decision],
        "prompt_version": "corroboration/2-bounded-excerpts"}))).assess(**args)
    validate_frozen_assessment(result)
    fake = result.model_copy(update={"status": "conflicting_evidence", "stop_reasons": [],
        "decisions": [result.decisions[0].model_copy(update={"relation": "contradicts"})]})
    with pytest.raises(ValueError, match="bounded excerpt"):
        validate_frozen_assessment(fake)


def test_single_decision_schema_binds_candidate_in_code_and_bounds_output():
    args, batch, _ = fixture()
    client = RecordingClient(batch)
    result = CorroborationService(LlmAssessor(client)).assess(**args)
    schema = client.calls[0]["output_type"].model_json_schema()
    assert set(schema["properties"]) == {"proposition", "decision"}
    decision_schema = schema["$defs"][schema["properties"]["decision"]["$ref"].split("/")[-1]]
    assert "passage_label" not in decision_schema["properties"]
    assert decision_schema["properties"]["quote"]["maxLength"] == 400
    assert decision_schema["properties"]["reason"]["maxLength"] == 240
    assert decision_schema["properties"]["origin_evidence"]["maxItems"] == 3
    assert result.decisions[0].passage_id == args["saved_candidates"][0].passage.id


def test_unknown_origin_label_does_not_discard_fully_shown_conflict():
    args, batch, _ = fixture()
    class BadOrigin(RecordingClient):
        def structured_bounded(self, **kwargs):
            response = super().structured_bounded(**kwargs)
            value = response.output.model_dump()
            value["decision"]["origin_evidence"] = [dict(passage_label="P999", quote="not shown",
                kind="original_reporting", reason="Unresolvable origin")]
            return LLMResult(kwargs["output_type"](**value), "fixture", "fixture", 50, 60)
    result = CorroborationService(LlmAssessor(BadOrigin(batch, "contradicts"))).assess(**args)
    assert result.status == "conflicting_evidence"
    assert result.decisions[0].origin_relation == "unknown"
    assert result.decisions[0].origin_evidence == []
    assert "unshown origin quotation rejected" in result.decisions[0].reason
    validate_frozen_assessment(result)


def test_service_preparation_consumes_total_deadline(monkeypatch):
    from mira.contracts import FrozenPassage
    from mira.budget import BudgetTracker
    args, batch, _ = fixture()
    clock = Clock()
    args["budget"] = BudgetTracker(args["ctx"].budget, clock=clock)
    original = FrozenPassage.model_validate
    def parse(cls, value, **kwargs):
        clock.value += 10
        return original(value, **kwargs)
    monkeypatch.setattr(FrozenPassage, "model_validate", classmethod(parse))
    calls = []
    class Assessor:
        def assess(self, *args, **kwargs):
            calls.append(kwargs)
            return batch
    result = CorroborationService(Assessor(), clock=clock).assess(**args)
    assert calls[0]["timeout_seconds"] == 50
    assert result.status == "independently_corroborated" and result.elapsed_seconds == 10


def test_prompt_preparation_consumes_same_call_deadline(monkeypatch):
    import mira.corroboration as module
    args, batch, primary = fixture()
    clock = Clock()
    monkeypatch.setattr(module.time, "monotonic", clock)
    original = module._excerpt
    def excerpt(*args, **kwargs):
        clock.value += 2
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "_excerpt", excerpt)
    client = RecordingClient(batch)
    LlmAssessor(client).assess(args["claim"], [primary], args["saved_candidates"],
                               timeout_seconds=60, max_tokens=100000)
    assert len(client.calls) == 1 and client.calls[0]["timeout_seconds"] == 56


def test_sixty_second_ceiling_and_legacy_thirty_second_limit():
    from pydantic import ValidationError
    from mira.corroboration import SearchLimits
    assert SearchLimits().max_seconds == 60
    assert SearchLimits(max_seconds=30).max_seconds == 30
    with pytest.raises(ValidationError):
        SearchLimits(max_seconds=61)
