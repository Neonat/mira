"""Canonical pre-verifier input captures complete evidence without invented metadata."""

from dataclasses import replace
from datetime import date
from uuid import UUID, uuid4

import pytest

from mira.budget import RunBudget
from mira.contracts import Brief, ClaimDraft
from mira.evidence_snapshot import build_verification_input
from mira.store import ClaimEvidence, PassageRecord, RunContext, StoredClaim


def inputs():
    brief = Brief(topic="AML/CFT", jurisdictions=["SG"], period_start=date(2026, 1, 1),
                  period_end=date(2026, 1, 31), as_of_date=date(2026, 2, 1), plan_requires_approval=False)
    ctx = RunContext(uuid4(), uuid4(), uuid4(), uuid4(), brief, RunBudget())
    passage = PassageRecord(uuid4(), uuid4(), uuid4(), uuid4(), "Source", "SG", "Title",
                            "https://example.test/report", None, 1, "Quoted evidence")
    draft = ClaimDraft(claim_label="C1", finding_type="external_fact", title="Fact", content="Claim",
                       jurisdiction_code="SG", change_type=None, industry_category=None, key_date=None,
                       key_date_kind=None, is_inference=False, citations=[dict(passage_label="P1",
                       supporting_quote="Quoted evidence")], depends_on=[], priority="high",
                       priority_reason=None, evidence_confidence="high", evidence_confidence_reason=None)
    fact = StoredClaim(uuid4(), draft, (ClaimEvidence(passage.id, passage.content),), ())
    inference = StoredClaim(uuid4(), draft.model_copy(update={"claim_label": "C2", "is_inference": True,
        "finding_type": "risk_implication", "citations": [], "depends_on": ["C1"]}), (), (fact.finding_id,))
    return ctx, fact, inference, passage


def test_input_captures_transitive_closure_with_explicit_unknown_provenance():
    ctx, fact, inference, passage = inputs()
    result = build_verification_input(ctx, inference, {fact.finding_id: fact}, {passage.id: passage})
    assert set(result.findings) == {fact.finding_id, inference.finding_id}
    assert result.findings[inference.finding_id].depends_on == [fact.finding_id]
    citation = result.findings[fact.finding_id].evidence[0]
    assert citation.document_version_id == passage.document_version_id
    assert citation.support_type == "supports"
    frozen = result.passages[passage.id]
    assert frozen.content == passage.content
    assert frozen.content_sha256 is None and frozen.extraction_version is None
    payload = result.model_dump(mode="json")
    assert "claim_label" not in payload["findings"][str(fact.finding_id)]
    assert "citations" not in payload["findings"][str(fact.finding_id)]
    assert payload["workspace_id"] == str(ctx.workspace_id)


def test_input_preserves_actual_provenance():
    ctx, fact, _, passage = inputs()
    passage = replace(passage, content_sha256="original-document-hash", extraction_version="extract-v2",
                      page_number=4, char_start=20, char_end=35)
    frozen = build_verification_input(ctx, fact, {}, {passage.id: passage}).passages[passage.id]
    assert frozen.content_sha256 == "original-document-hash"
    assert (frozen.extraction_version, frozen.page_number, frozen.char_start, frozen.char_end) == ("extract-v2", 4, 20, 35)


@pytest.mark.parametrize("missing", ["dependency", "passage"])
def test_missing_closure_is_an_error(missing):
    ctx, fact, inference, passage = inputs()
    claims = {} if missing == "dependency" else {fact.finding_id: fact}
    passages = {} if missing == "passage" else {passage.id: passage}
    with pytest.raises(ValueError, match=f"missing {missing}"):
        build_verification_input(ctx, inference, claims, passages)


def test_dependency_cycle_is_an_error():
    ctx, fact, inference, passage = inputs()
    cyclic = replace(fact, depends_on=(inference.finding_id,))
    with pytest.raises(ValueError, match="cycle"):
        build_verification_input(ctx, inference, {fact.finding_id: cyclic, inference.finding_id: inference}, {passage.id: passage})


def test_dependency_and_evidence_order_are_canonical():
    ctx, fact, inference, passage = inputs()
    second_passage = replace(passage, id=UUID(int=1), passage_number=2)
    fact = replace(fact, evidence=(*fact.evidence, ClaimEvidence(second_passage.id, "Quoted")))
    second_fact = replace(fact, finding_id=UUID(int=2))
    inference = replace(inference, depends_on=(fact.finding_id, second_fact.finding_id))
    claims = {f.finding_id: f for f in (fact, second_fact, inference)}
    passages = {p.id: p for p in (passage, second_passage)}
    original = build_verification_input(ctx, inference, claims, passages)
    reversed_claims = {fid: replace(f, evidence=tuple(reversed(f.evidence)), depends_on=tuple(reversed(f.depends_on)))
                       for fid, f in claims.items()}
    reordered = build_verification_input(ctx, reversed_claims[inference.finding_id], reversed_claims, passages)
    assert original.model_dump(mode="json") == reordered.model_dump(mode="json")
