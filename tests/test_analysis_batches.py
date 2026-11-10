from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest

from mira.analysis_batches import AnalysisLimits, namespace_claims, plan_batches
from mira.contracts import ClaimCitation, ClaimDraft
from mira.store import ClaimEvidence, NewClaim, PassageRecord


def passage(n, text, document=1):
    return PassageRecord(id=UUID(int=n), document_version_id=UUID(int=100 + document),
                         document_id=UUID(int=200 + document), source_id=UUID(int=300),
                         source_name="Regulator", jurisdiction_code="HK", title="Notice",
                         source_url="https://example.org/notice", published_at=None,
                         passage_number=n, content=text)


def claim(label, *, depends=(), evidence=()):
    inference = bool(depends)
    draft = ClaimDraft(claim_label=label, finding_type="risk_implication" if inference else "external_fact",
                       title="Finding", content="The finding", jurisdiction_code="HK",
                       change_type=None, industry_category=None, key_date=None, key_date_kind=None,
                       is_inference=inference,
                       citations=[] if inference else [ClaimCitation(passage_label="P1", supporting_quote="quoted")],
                       depends_on=list(depends), priority="medium", priority_reason=None,
                       evidence_confidence="high", evidence_confidence_reason=None)
    return NewClaim(draft=draft, evidence=tuple(evidence))


def test_limits_defaults_and_validation(monkeypatch):
    limits = AnalysisLimits()
    assert (limits.max_passages, limits.max_characters, limits.max_batches) == (3, 4500, 8)
    assert (limits.max_output_tokens, limits.timeout_seconds, limits.reserve_tokens, limits.reserve_seconds) == (16384, 180, 32000, 120)
    with pytest.raises(FrozenInstanceError):
        limits.max_batches = 2
    for field in ("max_passages", "max_characters", "max_batches", "max_output_tokens", "timeout_seconds"):
        with pytest.raises(ValueError):
            AnalysisLimits(**{field: 0})
    for field in ("reserve_tokens", "reserve_seconds"):
        with pytest.raises(ValueError):
            AnalysisLimits(**{field: -1})
        assert getattr(AnalysisLimits(**{field: 0}), field) == 0
    monkeypatch.setenv("MIRA_ANALYSIS_MAX_BATCHES", "3")
    monkeypatch.setenv("MIRA_ANALYSIS_RESERVE_TOKENS", "0")
    assert AnalysisLimits.from_env().max_batches == 3
    assert AnalysisLimits.from_env().reserve_tokens == 0


def test_batches_keep_whole_passages_at_exact_boundaries_with_document_rotation():
    a, b, c, d = passage(1, "abc"), passage(2, "de"), passage(3, "fghij", 2), passage(4, "k", 2)
    plan = plan_batches([a, b, c, d], AnalysisLimits(max_passages=2, max_characters=5, max_batches=2))
    assert plan.batches == ((a,), (c,))
    assert plan.deferred == {b.id: "batch_limit", d.id: "batch_limit"}


def test_oversized_and_duplicates_have_explicit_dispositions():
    a, huge, b = passage(1, "abc"), passage(2, "123456"), passage(3, "def")
    plan = plan_batches([a, huge, a, b, huge], AnalysisLimits(max_characters=5, max_batches=1))
    assert plan.batches == ((a,),)
    assert plan.deferred == {huge.id: "input_limit", b.id: "batch_limit"}
    with pytest.raises(ValueError):
        plan_batches([a, replace(a, title="Other")], AnalysisLimits())
    with pytest.raises(ValueError):
        plan_batches([huge, replace(huge, content="x")], AnalysisLimits(max_characters=5))


def test_claim_namespace_preserves_evidence_and_resolves_forward_dependencies():
    evidence = ClaimEvidence(passage_id=UUID(int=8), supporting_quote="quoted")
    inference = claim("C8", depends=("C2", "C9"))
    a, b = claim("C2", evidence=(evidence,)), claim("C9", evidence=(evidence,))
    mapped = namespace_claims([inference, a, b], 12)
    assert [c.draft.claim_label for c in mapped] == ["C13", "C14", "C15"]
    assert mapped[0].draft.depends_on == ["C14", "C15"]
    assert mapped[1].evidence == (evidence,)
    assert mapped[1].draft.citations == a.draft.citations
    assert mapped[1].draft.content == a.draft.content
    assert a.draft.claim_label == "C2"


def test_claim_namespace_rejects_ambiguous_or_unresolved_labels():
    with pytest.raises(ValueError):
        namespace_claims([claim("C1"), claim("C1")], 0)
    with pytest.raises(ValueError):
        namespace_claims([claim("C1", depends=("C2",))], 0)
    with pytest.raises(ValueError):
        namespace_claims([claim("P1")], 0)
    with pytest.raises(ValueError):
        namespace_claims([claim("C1")], -1)


def test_batch_limit_does_not_backfill_after_first_overflow():
    first, overflow, later = passage(1, "abcd"), passage(2, "xy"), passage(3, "z")
    plan = plan_batches([first, overflow, later], AnalysisLimits(max_characters=5, max_batches=1))
    assert plan.batches == ((first,),)
    assert plan.deferred == {overflow.id: "batch_limit", later.id: "batch_limit"}


def test_source_round_robin_gives_short_later_source_an_opportunity():
    long_source = [passage(n, "x") for n in range(1, 101)]
    later = replace(passage(101, "y", 2), source_id=UUID(int=301))
    plan = plan_batches(long_source + [later], AnalysisLimits(max_passages=2, max_batches=1))
    assert plan.batches == ((long_source[0], later),)
    assert all(plan.deferred[p.id] == "batch_limit" for p in long_source[1:])


def test_round_robin_rotates_documents_within_each_source():
    a1, a2 = passage(1, "a"), passage(2, "b")
    b1, b2 = passage(3, "c", 2), passage(4, "d", 2)
    c1, c2 = (replace(passage(n, text, 3), source_id=UUID(int=301))
              for n, text in [(5, "e"), (6, "f")])
    plan = plan_batches([a1, a2, b1, b2, c1, c2], AnalysisLimits(max_passages=6))
    assert plan.batches == ((a1, c1, b1, c2, a2, b2),)
    assert not plan.deferred


def test_duplicate_conflict_is_validated_even_after_capacity_exhausted():
    first, later = passage(1, "a"), passage(2, "b", 2)
    limits = AnalysisLimits(max_passages=1, max_batches=1)
    assert plan_batches([first, later, later], limits).deferred == {later.id: "batch_limit"}
    with pytest.raises(ValueError, match="conflicting passage identity"):
        plan_batches([first, later, replace(later, title="changed")], limits)
