"""Render a signed-off report from its saved snapshot, without new analysis (PRD v2 §6.6, §9; v1 DB07).

A reviewed report is a new reports row that points at the same snapshot as the draft. The worker
renders its HTML here, from the findings, passages and coverage that were already saved. No model is
called and nothing is re-analysed. The app cannot do this itself: it never reaches the worker's
database or the report files (tests/test_app_boundary.py).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

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


def render_signed_off(
    snapshot: ReportSnapshot,
    *,
    brief: Brief,
    findings: Sequence[SavedFinding],
    passages: Mapping[UUID, PassageRecord],
    expected: Mapping[UUID, ExpectedSourceRecord],
    reviewer: str,
    decided_at: datetime,
    generated_at: datetime,
) -> str:
    """HTML of the reviewed report: no draft watermark, reviewer and decision date shown.

    Every finding the snapshot cites must be among ``findings``. A missing one means the snapshot and
    the store disagree, and the report is refused rather than rendered with a hole in it.
    """
    wanted = cited_finding_ids(snapshot)
    available = {f.finding_id for f in findings}
    missing = wanted - available
    if missing:
        raise ValueError(f"{len(missing)} cited finding(s) are not in the store; the reviewed report is not rendered")
    claims = {f.finding_id: StoredClaim(f.finding_id, f.draft, f.evidence, f.depends_on) for f in findings}
    context = ReportContext(
        brief=brief, run_status="reviewed", claims=claims, passages=passages,
        unresolved={fid: REASON_NOT_STORED for fid in snapshot.unresolved_finding_ids},
        generated_at=generated_at, expected=expected, reviewer=reviewer, decided_at=decided_at,
    )
    return render_html(snapshot, context)
