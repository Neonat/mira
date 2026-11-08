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
            decisions.append(dict(passage_label=candidate["passage_label"], quote=candidate["content"],
                proposition=prop, relation=self.relation, origin_relation="unknown", origin_evidence=[],
                reason="Fixture semantic assessment"))
        return LLMResult(kwargs["output_type"](proposition=self.batch.proposition, decisions=decisions),
                         "fixture", "fixture", 50, 60)


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
    assert 1 <= len(payload["candidates"]) <= 3
    assert len(payload["primary"]) <= 2
    assert len(call["user"]) < 14000
    assert call["max_output_tokens"] <= 4096
    assert call["timeout_seconds"] <= 30
    assert all("Bank A holds" in c["content"] for c in payload["candidates"])
    assert [c.model_dump() for c in result.candidates] == [
        c.model_copy(update={"organization_id": str(c.passage.source_id)}).model_dump()
        for c in args["saved_candidates"]]
    assert [c.model_dump() for c in args["saved_candidates"]] == original
    assert result.status == "inconclusive" and "incomplete_assessment" in result.stop_reasons
    assert "assessment_workload_limit" in result.stop_reasons
    assert result.decisions and len(result.decisions) <= 3
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
            decision = response.output.decisions[0].model_copy(update={"quote": "UNSHOWN QUOTE"})
            return LLMResult(response.output.model_copy(update={"decisions": [decision]}),
                             "fixture", "fixture", 50, 60)
    result = CorroborationService(LlmAssessor(Unshown(batch))).assess(**args)
    assert result.status == "inconclusive" and not result.decisions
    assert args["budget"].tokens_used == 110


def test_one_unshown_quote_does_not_discard_other_valid_contradiction():
    args, batch, _ = fixture()
    c = args["saved_candidates"][0]
    args["saved_candidates"].append(c.model_copy(update={"passage": c.passage.model_copy(update={"id": uuid4()})}))
    class Partial(RecordingClient):
        def structured_bounded(self, **kwargs):
            response = super().structured_bounded(**kwargs)
            decisions = list(response.output.decisions)
            decisions[1] = decisions[1].model_copy(update={"quote": "fabricated"})
            return LLMResult(response.output.model_copy(update={"decisions": decisions}), "fixture", "fixture", 50, 60)
    result = CorroborationService(LlmAssessor(Partial(batch, "contradicts"))).assess(**args)
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
