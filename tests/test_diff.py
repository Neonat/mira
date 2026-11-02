"""Re-run diff matching (PRD v2 §6.5, AG11): a changed fixture shows as amended."""

from datetime import date
from uuid import uuid4

import pytest

from mira.contracts import ClaimDraft
from mira.diff import diff_key, diff_runs, normalise_title
from mira.store import PreviousFinding, StoredClaim


def draft(title, content, finding_type="obligation_summary"):
    # Factual claims must cite a passage (ClaimDraft enforces this), so the fixture cites one.
    return ClaimDraft(
        claim_label="C1", finding_type=finding_type, title=title, content=content, jurisdiction_code="SG",
        change_type="amended", industry_category=None, key_date=date(2026, 7, 1), key_date_kind="effective",
        is_inference=False, citations=[{"passage_label": "P1", "supporting_quote": content[:20]}], depends_on=[],
        priority="high", priority_reason="x", evidence_confidence="high", evidence_confidence_reason="direct quote",
    )


def stored(title, content, finding_type="obligation_summary"):
    return StoredClaim(uuid4(), draft(title, content, finding_type), (), ())


DOC = uuid4()


def keyed(claim, document_id=DOC):
    return (diff_key(claim.draft.finding_type, document_id, None, claim.draft.title), claim)


def previous(*claims, document_id=DOC):
    return [
        PreviousFinding(diff_key(c.draft.finding_type, document_id, None, c.draft.title), c.draft.title, c.draft.content)
        for c in claims
    ]


def test_normalise_title_ignores_case_punctuation_and_spacing():
    assert normalise_title("  MAS Notice 626: Amendments!  ") == normalise_title("mas notice 626 amendments")


def test_diff_key_needs_a_regulation_or_a_document():
    with pytest.raises(ValueError):
        diff_key("trend", None, None, "x")


def test_diff_key_prefers_the_regulation_and_is_capped_at_300_characters():
    regulation = uuid4()
    assert diff_key("trend", DOC, regulation, "x").startswith(str(regulation))
    assert len(diff_key("trend", DOC, None, "x" * 500)) == 300


def test_changed_content_for_the_same_finding_is_amended():
    old = stored("Notice 626 amended", "Banks must screen customers.")
    new = stored("Notice 626 amended", "Banks must screen customers and beneficial owners.")
    changes = diff_runs(previous(old), [keyed(new)])
    assert [(c.kind, c.previous_content) for c in changes] == [("amended", "Banks must screen customers.")]


def test_unchanged_finding_is_not_listed():
    claim = stored("Notice 626 amended", "Banks must screen customers.")
    assert diff_runs(previous(claim), [keyed(claim)]) == []


def test_new_finding_is_new_and_missing_finding_is_no_longer_supported():
    kept = stored("Notice 626 amended", "Banks must screen customers.")
    gone = stored("Old circular", "Superseded guidance.")
    added = stored("New circular", "New guidance on screening.")
    changes = diff_runs(previous(kept, gone), [keyed(kept), keyed(added)])
    assert sorted((c.kind, c.title) for c in changes) == [
        ("new", "New circular"), ("no_longer_supported", "Old circular"),
    ]


def test_title_changed_only_in_case_or_punctuation_still_matches_and_is_not_new():
    old = stored("Notice 626 amended", "Banks must screen customers.")
    new = stored("NOTICE 626, AMENDED.", "Banks must screen customers.")
    assert diff_runs(previous(old), [keyed(new)]) == []


def test_same_title_from_a_different_document_is_a_different_finding():
    old = stored("Notice 626 amended", "Banks must screen customers.")
    new = stored("Notice 626 amended", "Banks must screen customers.")
    changes = diff_runs(previous(old), [keyed(new, uuid4())])
    assert sorted(c.kind for c in changes) == ["new", "no_longer_supported"]


def test_industry_finding_without_a_regulation_diffs_by_document():
    old = stored("Incident at Bank X", "Penalty imposed.", finding_type="industry_development")
    new = stored("Incident at Bank X", "Penalty imposed and reviewed.", finding_type="industry_development")
    changes = diff_runs(previous(old), [keyed(new)])
    assert [c.kind for c in changes] == ["amended"]
