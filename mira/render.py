"""Render a signed-off report from its saved snapshot, without new analysis (PRD v2 §6.6, §9; v1 DB07).

A reviewed report freezes the reviewed text and the decisions captured by the database. The worker
renders its HTML here using only the frozen evidence bundle and stored review outcomes. No model is
called and nothing is re-analysed. The trusted worker writes artifacts; the app projects frozen
metadata and reads saved files without access to the worker's database credentials.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mira.agents.verifier import quote_match
from mira.contracts import Brief, ClaimDraft, ReportSnapshot
from mira.report import ReportContext, render_html
from mira.store import ClaimEvidence, ExpectedSourceRecord, PassageRecord, StoredClaim

# The reason for an unresolved item is not kept after the run, so a reviewed render says so plainly
# rather than printing a blank or an invented reason.
REASON_NOT_STORED = "reason not kept after the run; see the draft report"


@dataclass(frozen=True)
class SavedFinding:
    """One finding as stored, with the fields a render needs."""

    finding_id: UUID
    draft: ClaimDraft
    evidence: tuple[ClaimEvidence, ...]
    depends_on: tuple[UUID, ...]


def cited_finding_ids(snapshot: ReportSnapshot) -> set[UUID]:
    return {fid for section in snapshot.sections for sentence in section.sentences for fid in sentence.finding_ids}


def frozen_context(snapshot: ReportSnapshot, generated_at: datetime) -> ReportContext:
    """Validate a complete reviewed bundle before creating any report output."""
    bundle = snapshot.evidence_bundle
    if bundle is None:
        raise ValueError("legacy snapshot requires fresh verification and review before regeneration")
    if (bundle.analysis_run_id != snapshot.analysis_run_id
            or bundle.analysis_revision_id != snapshot.analysis_revision_id):
        raise ValueError("frozen evidence scope identity does not match the report snapshot")
    if not bundle.reviewer_display_name.strip():
        raise ValueError("frozen reviewer display name is missing")
    for section in snapshot.sections:
        for sentence in section.sentences:
            if not sentence.structural and not sentence.finding_ids:
                raise ValueError("non-structural reviewed sentence has no finding")
    for row in snapshot.coverage:
        label = bundle.expected_sources.get(row.expected_source_id)
        if label is None or label.id != row.expected_source_id:
            raise ValueError(f"missing frozen coverage label {row.expected_source_id}")
    for expected_id, expected in bundle.expected_sources.items():
        if expected_id != expected.id:
            raise ValueError("frozen coverage label identity mismatch")

    versions: dict[UUID, tuple] = {}
    for passage_id, passage in bundle.passages.items():
        if passage_id != passage.id:
            raise ValueError("frozen passage identity mismatch")
        version_metadata = (
            passage.document_id, passage.source_id, passage.source_name,
            passage.jurisdiction_code, passage.title, passage.source_url,
            passage.published_at, passage.imported, passage.content_sha256,
        )
        previous = versions.setdefault(passage.document_version_id, version_metadata)
        if previous != version_metadata:
            raise ValueError("inconsistent frozen document version metadata")

    labels = {fid: f"C{number}" for number, fid in enumerate(sorted(bundle.findings, key=str), start=1)}
    passage_labels = {pid: f"P{number}" for number, pid in enumerate(sorted(bundle.passages, key=str), start=1)}
    claims: dict[UUID, StoredClaim] = {}
    visiting: set[UUID] = set()

    def hydrate(finding_id: UUID) -> None:
        if finding_id in visiting:
            raise ValueError("frozen dependency cycle")
        if finding_id in claims:
            return
        finding = bundle.findings.get(finding_id)
        if finding is None:
            raise ValueError(f"missing finding {finding_id} in frozen dependency closure")
        if finding.finding_id != finding_id:
            raise ValueError("frozen finding identity mismatch")
        visiting.add(finding_id)
        for dependency_id in finding.depends_on:
            hydrate(dependency_id)
        supported = []
        for citation in finding.evidence:
            passage = bundle.passages.get(citation.passage_id)
            if passage is None:
                raise ValueError(f"missing passage {citation.passage_id} in frozen evidence")
            if citation.document_version_id != passage.document_version_id:
                raise ValueError("frozen citation document version does not match its passage")
            if citation.support_type == "supports":
                if not quote_match(citation.supporting_quote, passage.content):
                    raise ValueError("frozen supporting quote is not present in its passage")
                supported.append(citation)
        if not finding.is_inference and not supported:
            raise ValueError("frozen factual finding has no supporting evidence")
        verification = bundle.verifications.get(finding_id)
        required_method = "inference_check" if finding.is_inference else "llm"
        if (verification is None or verification.verdict != "supported"
                or verification.method != required_method or not verification.model
                or not verification.input_fingerprint.strip()):
            raise ValueError(f"missing or invalid frozen verification for finding {finding_id}")
        if verification.checked_at > bundle.reviewed_at:
            raise ValueError("frozen verification is later than sign-off")
        outcome = snapshot.review_outcomes.get(finding_id)
        if (outcome is None or outcome.decision not in {"accepted", "amended"}
                or outcome.exclusion_reason or outcome.review_id is None
                or outcome.reviewed_at is None or outcome.reviewed_by is None):
            raise ValueError(f"missing or invalid review outcome for retained finding {finding_id}")
        if outcome.reviewed_at > bundle.reviewed_at:
            raise ValueError("review outcome is later than frozen sign-off")
        fields = finding.model_dump(exclude={"finding_id", "depends_on", "evidence"})
        draft = ClaimDraft(
            claim_label=labels[finding_id], **fields,
            citations=[{"passage_label": passage_labels[e.passage_id], "supporting_quote": e.supporting_quote}
                       for e in supported],
            depends_on=[labels[d] for d in finding.depends_on],
        )
        if outcome.decision == "amended":
            if not outcome.amended_content or not outcome.amended_content.strip():
                raise ValueError("reviewed amendment has no text")
            draft = draft.model_copy(update={
                "title": "Reviewer amendment", "content": outcome.amended_content,
                "key_date": None, "key_date_kind": None,
            })
        claims[finding_id] = StoredClaim(
            finding_id, draft,
            tuple(ClaimEvidence(e.passage_id, e.supporting_quote) for e in supported),
            tuple(finding.depends_on),
        )
        visiting.remove(finding_id)

    # Validate roots first, then any extra frozen entries so corrupt data cannot hide unused.
    for finding_id in sorted(cited_finding_ids(snapshot) | set(bundle.findings), key=str):
        hydrate(finding_id)
    passages = {pid: PassageRecord(**p.model_dump()) for pid, p in bundle.passages.items()}
    expected = {eid: ExpectedSourceRecord(**e.model_dump()) for eid, e in bundle.expected_sources.items()}
    return ReportContext(
        brief=bundle.brief, run_status="reviewed", claims=claims, passages=passages,
        unresolved={fid: REASON_NOT_STORED for fid in snapshot.unresolved_finding_ids},
        generated_at=generated_at, expected=expected,
        reviewer=bundle.reviewer_display_name, decided_at=bundle.reviewed_at,
    )


def render_signed_off(
    snapshot: ReportSnapshot,
    *,
    generated_at: datetime,
    brief: Brief | None = None,
    findings: Sequence[SavedFinding] = (),
    passages: Mapping[UUID, PassageRecord] | None = None,
    expected: Mapping[UUID, ExpectedSourceRecord] | None = None,
    reviewer: str | None = None,
    decided_at: datetime | None = None,
) -> str:
    """Render only the frozen bundle; legacy live-input keywords are ignored.

    Old snapshots remain readable as drafts. Regenerating reviewed artifacts
    requires a fresh verification/review/sign-off that captures their evidence.
    """
    return render_html(snapshot, frozen_context(snapshot, generated_at))
