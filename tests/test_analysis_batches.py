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
    assert (limits.max_passages, limits.max_characters, limits.max_batches) == (8, 12000, 8)
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


def test_topical_operative_passage_beats_cover_and_navigation_without_starving_other_documents():
    from mira.contracts import Brief
    from datetime import date
    brief = Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2025, 1, 1),
                  period_end=date(2026, 1, 1), as_of_date=date(2026, 1, 1), plan_requires_approval=False)
    cover = passage(1, 'Consultation paper: contents and introduction.')
    operative = passage(2, 'Institutions must apply enhanced customer due diligence to money laundering risks.')
    many = [passage(n, 'AML controls must identify suspicious transactions.') for n in range(3, 30)]
    other = passage(40, 'CFT reporting requirements apply to institutions.', 2)
    plan = plan_batches([cover, operative, *many, other], AnalysisLimits(max_passages=2, max_batches=1), brief=brief)
    assert plan.batches == ((operative, other),)
    assert plan.deferred[cover.id] == 'batch_limit'
    assert len(plan.deferred) == 28


def test_clear_navigation_documents_follow_publications_but_are_not_silently_discarded():
    hub = replace(passage(1, 'AML circulars and links'), title='Guidance Papers and Circulars')
    notice = replace(passage(2, 'Institutions must report suspicious transactions.', 2),
                     title='Circular on reporting', source_id=UUID(int=301))
    plan = plan_batches([hub, notice], AnalysisLimits(max_passages=1, max_batches=1))
    assert plan.batches == ((notice,),)
    assert plan.deferred == {hub.id: 'batch_limit'}
    full = plan_batches([hub, notice], AnalysisLimits(max_passages=2))
    assert full.batches == ((notice, hub),)
    assert not full.deferred


def test_substantive_index_report_is_not_mistaken_for_navigation():
    report = replace(passage(1, 'The AML index report records assessed risks.'), title='Global AML Index Report')
    notice = passage(2, 'Notice contents', 2)
    assert plan_batches([report, notice], AnalysisLimits(max_passages=1, max_batches=1)).batches == ((report,),)


def test_larger_default_batch_keeps_more_whole_passages_with_a_hard_character_bound():
    passages = [passage(n, 'x' * 1400, n) for n in range(1, 10)]
    plan = plan_batches(passages, AnalysisLimits(max_batches=1))
    assert len(plan.batches[0]) == 8
    assert sum(len(p.content) for p in plan.batches[0]) == 11200
    assert plan.deferred == {passages[-1].id: 'batch_limit'}


def test_navigation_waits_for_deeper_publication_passages_across_sources():
    hub = replace(passage(1, 'Links'), title='Publications')
    a, b = passage(2, 'Substantive first paragraph', 2), passage(3, 'Substantive second paragraph', 2)
    other = replace(passage(4, 'Other substantive publication', 3), source_id=UUID(int=301))
    plan = plan_batches([hub, a, b, other], AnalysisLimits(max_passages=3, max_batches=1))
    assert plan.batches == ((a, other, b),)
    assert plan.deferred == {hub.id: 'batch_limit'}


def test_brief_ranking_is_stable_on_ties_and_does_not_change_whole_passages():
    from mira.contracts import Brief
    from datetime import date
    brief = Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2025, 1, 1),
                  period_end=date(2026, 1, 1), as_of_date=date(2026, 1, 1), plan_requires_approval=False)
    cover = passage(1, 'Contents')
    a = passage(2, 'AML controls must monitor customer risks.')
    b = passage(3, 'CFT controls must identify risks.')
    limits = AnalysisLimits(max_passages=2, max_batches=1)
    first = plan_batches([cover, a, b], limits, brief)
    assert first.batches == ((a, b),)
    assert first == plan_batches([cover, a, b], limits, brief)
    assert first.deferred == {cover.id: 'batch_limit'}
    assert plan_batches([cover, a, b], limits).batches == ((cover, a),)


def test_default_character_limit_still_bounds_batches_with_eight_passage_allowance():
    items = [passage(n, 'x' * 2000, n) for n in range(1, 9)]
    plan = plan_batches(items, AnalysisLimits(max_batches=1))
    assert plan.batches == (tuple(items[:6]),)
    assert plan.deferred == {p.id: 'batch_limit' for p in items[6:]}


@pytest.mark.parametrize('role', ['listing', 'maintenance'])
def test_affirmative_grounding_role_defers_generic_navigation_behind_publication(role):
    listing = replace(passage(1, 'Category links'), title='Regulator AML information',
                      acquisition_provenance={'claim_grounding': {'role': role}})
    publication = passage(2, 'Institutions must monitor suspicious transactions.', 2)
    plan = plan_batches([listing, publication], AnalysisLimits(max_passages=1, max_batches=1))
    assert plan.batches == ((publication,),)
    assert plan.deferred == {listing.id: 'batch_limit'}
    assert plan_batches([listing, publication], AnalysisLimits(max_passages=2)).batches == ((publication, listing),)


@pytest.mark.parametrize('title', ['Circulars & Guidance Papers', 'Guidance Papers & Circulars'])
def test_saved_category_title_variants_are_lower_priority(title):
    category = replace(passage(1, 'Publication links'), title=title)
    publication = passage(2, 'Notice full text', 2)
    plan = plan_batches([category, publication], AnalysisLimits(max_passages=1, max_batches=1))
    assert plan.batches == ((publication,),)
    assert plan.deferred == {category.id: 'batch_limit'}


def test_unknown_grounding_classification_does_not_lower_document_priority():
    unknown = replace(passage(1, 'Operative notice'), title='AML information',
                      acquisition_provenance={'claim_grounding': {'role': 'unknown'}})
    other = passage(2, 'Other notice', 2)
    assert plan_batches([unknown, other], AnalysisLimits(max_passages=1, max_batches=1)).batches == ((unknown,),)


def test_affirmative_publication_role_takes_precedence_over_title_fallback():
    publication = replace(passage(1, 'Full operative publication'), title='Circulars & Guidance Papers',
                          acquisition_provenance={'claim_grounding': {'role': 'publication'}})
    other = passage(2, 'Other publication', 2)
    assert plan_batches([publication, other], AnalysisLimits(max_passages=1, max_batches=1)).batches == ((publication,),)
