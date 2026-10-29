"""A reviewed render is the saved snapshot with the sign-off added, not a new report (PRD v2 §6.6, §9)."""

import re
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from mira.contracts import Brief, ClaimDraft, ReportSection, ReportSentence, ReportSnapshot
from mira.render import REASON_NOT_STORED, SavedFinding, render_signed_off
from mira.report import ReportContext, render_html
from mira.store import ClaimEvidence, PassageRecord

BRIEF = Brief(topic="AML/CFT", jurisdictions=["SG"], period_start=date(2025, 10, 1), period_end=date(2026, 9, 30),
              as_of_date=date(2026, 10, 26), plan_requires_approval=False)
AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def draft(label, title, content):
    return ClaimDraft(
        claim_label=label, finding_type="obligation_summary", title=title, content=content, jurisdiction_code="SG",
        change_type="new", industry_category=None, key_date=None, key_date_kind=None, is_inference=False,
        citations=[{"passage_label": "P1", "supporting_quote": content[:20]}], depends_on=[],
        priority="high", priority_reason="x", evidence_confidence="high", evidence_confidence_reason="quote",
    )


def fixture():
    passage = PassageRecord(
        uuid4(), uuid4(), uuid4(), uuid4(), "MAS", "SG", "Notice 626", "https://www.mas.gov.sg/notice-626",
        date(2026, 3, 1), 1, "Banks must screen customers against sanctions lists before onboarding.",
    )
    finding_id = uuid4()
    saved = SavedFinding(finding_id, draft("C1", "Screening", "Banks must screen customers against sanctions lists before onboarding."),
                         (ClaimEvidence(passage.id, "Banks must screen customers"),), ())
    snapshot = ReportSnapshot(
        contract_version="1.1", analysis_run_id=uuid4(), analysis_revision_id=uuid4(),
        sections=[ReportSection(section="regulatory_developments", no_verified_items=False, sentences=[
            ReportSentence(text="Banks must screen customers.", finding_ids=[finding_id], structural=False)])],
        coverage=[], unresolved_finding_ids=[],
    )
    return snapshot, saved, passage


def body(html):
    stripped = re.sub(r'<div class="watermark">DRAFT</div>|<tr><td>Status</td>.*?</tr>|<tr><td>Reviewed by</td>.*?</tr>|<tr><td>Decision date</td>.*?</tr>', "", html)
    return re.sub(r"\s+", " ", stripped).strip()


def test_reviewed_render_has_the_same_findings_as_the_draft_it_signs_off():
    snapshot, saved, passage = fixture()
    draft_html = render_html(snapshot, ReportContext(
        brief=BRIEF, run_status="draft", claims={saved.finding_id: _stored(saved)}, passages={passage.id: passage},
        unresolved={}, generated_at=AT,
    ))
    reviewed_html = render_signed_off(
        snapshot, brief=BRIEF, findings=[saved], passages={passage.id: passage}, expected={},
        reviewer="Reviewer A", decided_at=AT, generated_at=AT,
    )
    assert body(draft_html) == body(reviewed_html)  # the findings and evidence are unchanged
    assert 'class="watermark"' not in reviewed_html and 'class="watermark"' in draft_html
    assert "Reviewer A" in reviewed_html and "2026-10-30" in reviewed_html


def test_a_snapshot_citing_a_finding_not_in_the_store_is_refused_not_rendered_with_a_hole():
    snapshot, saved, passage = fixture()
    with pytest.raises(ValueError, match="not in the store"):
        render_signed_off(snapshot, brief=BRIEF, findings=[], passages={passage.id: passage}, expected={},
                          reviewer="Reviewer A", decided_at=AT, generated_at=AT)


def test_unresolved_items_say_the_reason_is_not_kept_rather_than_printing_blank():
    snapshot, saved, passage = fixture()
    unresolved_id = uuid4()
    limitations = ReportSection(section="coverage_limitations", no_verified_items=False, sentences=[
        ReportSentence(text="Coverage is not complete.", finding_ids=[], structural=True)])
    snapshot = snapshot.model_copy(update={"unresolved_finding_ids": [unresolved_id],
                                           "sections": [*snapshot.sections, limitations]})
    html = render_signed_off(snapshot, brief=BRIEF, findings=[saved], passages={passage.id: passage}, expected={},
                             reviewer="Reviewer A", decided_at=AT, generated_at=AT)
    assert REASON_NOT_STORED in html


def _stored(saved):
    from mira.store import StoredClaim

    return StoredClaim(saved.finding_id, saved.draft, saved.evidence, saved.depends_on)
