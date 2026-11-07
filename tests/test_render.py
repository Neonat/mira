"""A reviewed render is the saved snapshot with the sign-off added, not a new report (PRD v2 §6.6, §9)."""

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from mira.contracts import Brief, ClaimDraft, CoverageRow, ReportSection, ReportSentence, ReportSnapshot
from mira.coverage_display import MANUAL_IMPORT_NOTE
from mira.render import REASON_NOT_STORED, SavedFinding, render_signed_off
from mira.report import ReportContext, render_html
from mira.store import ClaimEvidence, ExpectedSourceRecord, PassageRecord

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
    snapshot = freeze(snapshot, [saved], [passage])
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
    snapshot = snapshot.model_copy(update={"evidence_bundle": snapshot.evidence_bundle.model_copy(update={"findings": {}})})
    with pytest.raises(ValueError, match="missing finding"):
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


def test_numbered_market_finding_shows_dated_metadata_and_one_link_per_supporting_document():
    snapshot, saved, passage = fixture()
    second_passage = replace(passage, id=uuid4(), passage_number=2)
    claim = replace(
        _stored(saved),
        draft=saved.draft.model_copy(update={"key_date": date(2026, 3, 1), "key_date_kind": "published"}),
        evidence=(*saved.evidence, ClaimEvidence(second_passage.id, "screen customers")),
    )
    expected = ExpectedSourceRecord(uuid4(), 1, "HK", "policy", uuid4(), "Policy updates")
    main_section = snapshot.sections[0].model_copy(update={"sentences": [
        ReportSentence(text=claim.draft.content, finding_ids=[claim.finding_id], structural=False),
    ]})
    timeline = main_section.model_copy(update={"section": "deadlines_timeline"})
    snapshot = snapshot.model_copy(update={
        "coverage": [CoverageRow(expected_source_id=expected.id, gap_round=0, status="missing",
                                 document_version_id=None, note=MANUAL_IMPORT_NOTE)],
        "sections": [main_section, timeline, ReportSection(section="coverage_limitations", sentences=[],
                                                            no_verified_items=False)],
    })

    html = render_html(snapshot, ReportContext(
        brief=BRIEF.model_copy(update={"jurisdictions": ["SG", "HK"]}),
        run_status="partial", claims={saved.finding_id: claim},
        passages={p.id: p for p in (passage, second_passage)}, unresolved={},
        generated_at=AT, expected={expected.id: expected},
    ))

    assert "<h3>Singapore</h3>" in html
    assert '<span class="number">1.</span> Screening' in html
    assert '<span class="tag">Fact</span>' in html
    assert 'Published <time datetime="2026-03-01">1 Mar 2026</time>' in html
    assert html.count('<article class="finding"') == 1
    assert f'href="#finding-{claim.finding_id}"' in html
    finding_html = html.split(f'id="finding-{claim.finding_id}">', 1)[1].split("</article>", 1)[0]
    assert finding_html.count(f'href="{passage.source_url}"') == 1
    assert 'href="#e1"' in finding_html and 'href="#e2"' in finding_html
    assert "Source coverage checklist" in html and "Manual import needed" in html


def _stored(saved):
    from mira.store import StoredClaim

    return StoredClaim(saved.finding_id, saved.draft, saved.evidence, saved.depends_on)


def test_legacy_snapshot_requires_fresh_verification_and_review():
    snapshot, saved, passage = fixture()
    snapshot = snapshot.model_copy(update={"evidence_bundle": None})
    with pytest.raises(ValueError, match="fresh verification and review"):
        render_signed_off(snapshot, brief=BRIEF, findings=[saved], passages={passage.id: passage},
                          expected={}, reviewer="Reviewer A", decided_at=AT, generated_at=AT)


def freeze(snapshot, findings, passages, expected=()):
    from dataclasses import asdict
    from mira.budget import RunBudget
    from mira.contracts import FrozenEvidenceBundle, ReviewOutcome
    from mira.evidence_snapshot import build_verification_input
    from mira.store import RunContext

    ctx = RunContext(uuid4(), uuid4(), snapshot.analysis_run_id, snapshot.analysis_revision_id, BRIEF, RunBudget())
    claims = {f.finding_id: _stored(f) for f in findings}
    records = {p.id: p for p in passages}
    frozen_findings, frozen_passages = {}, {}
    for claim in claims.values():
        item = build_verification_input(ctx, claim, claims, records)
        frozen_findings.update(item.findings)
        frozen_passages.update(item.passages)
    bundle = FrozenEvidenceBundle(
        workspace_id=ctx.workspace_id, analysis_run_id=ctx.analysis_run_id,
        analysis_revision_id=ctx.analysis_revision_id, findings=frozen_findings, passages=frozen_passages,
        brief=BRIEF, expected_sources={e.id: asdict(e) for e in expected},
        reviewer_display_name="Reviewer A", reviewed_at=AT,
        verifications={fid: dict(check_id=uuid4(), method="inference_check" if claim.draft.is_inference else "llm",
            verdict="supported", reason="checked", model="test", prompt_version="1", checked_at=AT,
            input_fingerprint="frozen-diagnostic", attempt=1, agent_step_id=uuid4())
            for fid, claim in claims.items()},
    )
    outcomes = {fid: ReviewOutcome(review_id=uuid4(), decision="accepted", reviewed_at=AT,
                                 reviewed_by=ctx.user_id, review_sequence=1, amended_content=None,
                                 exclusion_reason=None) for fid in claims}
    return snapshot.model_copy(update={"evidence_bundle": bundle, "review_outcomes": outcomes})


def test_frozen_bundle_ignores_changed_or_missing_live_inputs():
    snapshot, saved, passage = fixture()
    expected = render_signed_off(snapshot, generated_at=AT)
    changed = replace(passage, content="tampered", source_name="WRONG")
    actual = render_signed_off(snapshot, brief=BRIEF, findings=[], passages={passage.id: changed},
                               expected={}, reviewer="WRONG", decided_at=AT, generated_at=AT)
    assert actual == expected
    assert "WRONG" not in actual


@pytest.mark.parametrize("corruption, message", [
    ("passage", "missing passage"), ("version", "document version"),
    ("quote", "quote"), ("support", "support"), ("review", "review outcome"),
    ("scope", "identity"), ("coverage", "coverage label"), ("verification", "verification"),
])
def test_corrupt_bundle_fails_closed(corruption, message):
    from mira.contracts import CoverageRow
    snapshot, saved, passage = fixture()
    bundle = snapshot.evidence_bundle
    finding = bundle.findings[saved.finding_id]
    if corruption == "passage":
        bundle = bundle.model_copy(update={"passages": {}})
    elif corruption in {"version", "quote", "support"}:
        if corruption == "support":
            finding = finding.model_copy(update={"evidence": []})
        else:
            changes = {"document_version_id": uuid4()} if corruption == "version" else {"supporting_quote": "invented unsupported words"}
            citation = finding.evidence[0].model_copy(update=changes)
            finding = finding.model_copy(update={"evidence": [citation]})
        bundle = bundle.model_copy(update={"findings": {saved.finding_id: finding}})
    elif corruption == "verification":
        bundle = bundle.model_copy(update={"verifications": {}})
    elif corruption == "review":
        snapshot = snapshot.model_copy(update={"review_outcomes": {}})
    elif corruption == "scope":
        bundle = bundle.model_copy(update={"analysis_run_id": uuid4()})
    elif corruption == "coverage":
        snapshot = snapshot.model_copy(update={"coverage": [CoverageRow(expected_source_id=uuid4(),
            gap_round=0, status="missing", document_version_id=None, note=None)]})
    snapshot = snapshot.model_copy(update={"evidence_bundle": bundle})
    with pytest.raises(ValueError, match=message):
        render_signed_off(snapshot, generated_at=AT)


def test_frozen_inference_requires_every_transitive_dependency():
    snapshot, saved, passage = fixture()
    inference_id = uuid4()
    inference_draft = saved.draft.model_copy(update={"claim_label": "C2", "finding_type": "risk_implication",
        "is_inference": True, "citations": [], "depends_on": ["C1"]})
    inference = SavedFinding(inference_id, inference_draft, (), (saved.finding_id,))
    snapshot = snapshot.model_copy(update={"sections": [ReportSection(section="executive_summary",
        no_verified_items=False, sentences=[ReportSentence(text="An inference", finding_ids=[inference_id], structural=False)])]})
    snapshot = freeze(snapshot, [saved, inference], [passage])
    assert passage.source_url in render_signed_off(snapshot, generated_at=AT)
    broken = snapshot.evidence_bundle.model_copy(update={"findings": {
        inference_id: snapshot.evidence_bundle.findings[inference_id]}})
    with pytest.raises(ValueError, match="missing finding"):
        render_signed_off(snapshot.model_copy(update={"evidence_bundle": broken}), generated_at=AT)


@pytest.mark.parametrize("field,value", [("method", "quote_match"), ("verdict", "unsupported")])
def test_semantic_verification_is_required(field, value):
    snapshot, saved, passage = fixture()
    bundle = snapshot.evidence_bundle
    check = bundle.verifications[saved.finding_id].model_copy(update={field: value})
    bundle = bundle.model_copy(update={"verifications": {saved.finding_id: check}})
    with pytest.raises(ValueError, match="verification"):
        render_signed_off(snapshot.model_copy(update={"evidence_bundle": bundle}), generated_at=AT)


def test_corrupt_bundle_is_rejected_before_job_writes_artifact(tmp_path):
    from mira.render_job import render_one
    snapshot, saved, passage = fixture()
    bundle = snapshot.evidence_bundle.model_copy(update={"passages": {}})
    snapshot = snapshot.model_copy(update={"evidence_bundle": bundle})
    pending = {"id": uuid4(), "workspace_id": bundle.workspace_id,
        "analysis_revision_id": bundle.analysis_revision_id,
        "evidence_snapshot": snapshot.model_dump(mode="json"), "generated_at": AT,
        "reviewed_at": AT, "reviewed_by": uuid4(), "report_version": 2}
    class NoDatabaseReads:
        def execute(self, *args, **kwargs):
            raise AssertionError("reviewed render must not fetch live evidence")
    with pytest.raises(ValueError, match="missing passage"):
        render_one(NoDatabaseReads(), bundle.workspace_id, pending, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_frozen_reviewer_amendment_is_preserved_and_exclusion_fails_closed():
    snapshot, saved, passage = fixture()
    outcome = snapshot.review_outcomes[saved.finding_id].model_copy(update={
        "decision": "amended", "amended_content": "Reviewer corrected the assessment."})
    # Sign-off freezes amended prose in the snapshot as well as the outcome.
    section = snapshot.sections[0].model_copy(update={"sentences": [ReportSentence(
        text=outcome.amended_content, finding_ids=[saved.finding_id], structural=False)]})
    snapshot = snapshot.model_copy(update={"review_outcomes": {saved.finding_id: outcome}, "sections": [section]})
    html = render_signed_off(snapshot, generated_at=AT)
    assert "Reviewer amendment" in html
    assert "Reviewer corrected the assessment." in html
    outcome = outcome.model_copy(update={"exclusion_reason": "Excluded by reviewer"})
    snapshot = snapshot.model_copy(update={"review_outcomes": {saved.finding_id: outcome}})
    with pytest.raises(ValueError, match="review outcome"):
        render_signed_off(snapshot, generated_at=AT)


def test_frozen_coverage_labels_ignore_live_labels():
    snapshot, saved, passage = fixture()
    expected = ExpectedSourceRecord(uuid4(), 1, "SG", "policy", uuid4(), "Original coverage label")
    snapshot = freeze(snapshot, [saved], [passage], [expected])
    snapshot = snapshot.model_copy(update={"coverage": [CoverageRow(expected_source_id=expected.id,
        gap_round=0, status="missing", document_version_id=None, note=None)], "sections": [*snapshot.sections,
        ReportSection(section="coverage_limitations", no_verified_items=False, sentences=[])]})
    html = render_signed_off(snapshot, generated_at=AT,
        expected={expected.id: replace(expected, document_hint="Changed live label")})
    assert "Original coverage label" in html and "Changed live label" not in html


def test_render_job_uses_frozen_context_and_stored_generation_time(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from mira import render_job

    snapshot, saved, passage = fixture()
    bundle = snapshot.evidence_bundle
    report_id = uuid4()
    pending = {"id": report_id, "workspace_id": bundle.workspace_id,
        "analysis_revision_id": bundle.analysis_revision_id,
        "evidence_snapshot": snapshot.model_dump(mode="json"), "generated_at": AT,
        "reviewed_at": AT, "reviewed_by": uuid4(), "report_version": 2}
    updates = []
    class ArtifactUpdatesOnly:
        def execute(self, sql, params):
            assert sql.startswith("update public.reports set artifact_storage_path")
            updates.append(params)
    monkeypatch.setattr(render_job, "acting_as", lambda *args: nullcontext())
    assert render_job.render_one(ArtifactUpdatesOnly(), bundle.workspace_id, pending, tmp_path) == report_id
    relative = f"{bundle.analysis_run_id}/report-v2-reviewed.html"
    assert updates == [(relative, report_id, bundle.workspace_id)]
    assert (tmp_path / relative).read_text() == render_signed_off(snapshot, generated_at=AT)
