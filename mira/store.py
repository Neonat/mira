"""What the orchestrator reads from and writes to the evidence store (PRD v2 §5.1, §8).

``RunStore`` is the boundary; ``InMemoryStore`` implements it for tests and
offline runs. A Postgres implementation must follow ``mira.db``: every write
inside ``acting_as`` for the initiating user, every query filtered by
``workspace_id``, actor columns filled by code. Methods map to tables:

- ``start_step`` / ``finish_step``: ``agent_steps``
- ``save_plan``: ``research_plans``
- ``save_claims`` / ``update_claim``: ``analysis_findings``, ``analysis_evidence``,
  ``finding_evidence`` (with ``supporting_quote``), ``finding_dependencies``
- ``save_checks``: ``claim_checks``
- ``save_coverage``: ``coverage_results``
- ``save_report``: ``reports`` (``evidence_snapshot`` is the ``ReportSnapshot``)
- ``set_run_status``: ``analysis_runs.status`` and ``failure_summary``

The orchestrator calls the store from one thread only.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol
from uuid import UUID, uuid4

from mira.budget import RunBudget
from mira.contracts import Brief, ClaimDraft, CoverageRow, ReportSnapshot, RunStatus, StepRecord, Verdict

# --- Records (filled by code, carry real IDs) ----------------------------------


@dataclass(frozen=True)
class RunContext:
    workspace_id: UUID
    user_id: UUID
    analysis_run_id: UUID
    analysis_revision_id: UUID
    brief: Brief
    budget: RunBudget
    previous_run_id: UUID | None = None
    # True once an auditor has approved this run's plan (research_plans.approved_at). Defaults to
    # False, the safe direction: a run that needs approval and has none does not scout.
    plan_approved: bool = False
    # Steps already recorded for this run. A resumed run continues numbering after them, because
    # agent_steps is unique on (analysis_run_id, step_no).
    completed_steps: int = 0


@dataclass(frozen=True)
class SourceRecord:
    id: UUID
    name: str
    source_type: str
    base_url: str | None
    jurisdiction_code: str | None
    permitted_operations: tuple[str, ...]
    connector_config: dict[str, object] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class ExpectedSourceRecord:
    id: UUID
    list_version: int
    jurisdiction_code: str
    category: str
    source_id: UUID
    document_hint: str


@dataclass(frozen=True)
class PassageRecord:
    id: UUID
    document_version_id: UUID
    document_id: UUID
    source_id: UUID
    source_name: str
    jurisdiction_code: str | None
    title: str
    source_url: str
    published_at: date | None
    passage_number: int
    content: str
    imported: bool = False
    content_sha256: str | None = None
    extraction_version: str | None = None
    page_number: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    acquisition_provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimEvidence:
    passage_id: UUID
    supporting_quote: str


@dataclass(frozen=True)
class NewClaim:
    """An analyst claim with its passage labels resolved; ``depends_on`` stays as claim labels."""

    draft: ClaimDraft
    evidence: tuple[ClaimEvidence, ...]


@dataclass(frozen=True)
class PreviousFinding:
    """One finding from the previous run, as stored, with the key the re-run diff matches on."""

    key: str
    title: str
    content: str


@dataclass(frozen=True)
class StoredClaim:
    finding_id: UUID
    draft: ClaimDraft
    evidence: tuple[ClaimEvidence, ...]
    depends_on: tuple[UUID, ...]

    @property
    def label(self) -> str:
        return self.draft.claim_label


class RunStore(Protocol):
    def list_sources(self, workspace_id: UUID) -> list[SourceRecord]: ...

    def list_expected_sources(
        self, workspace_id: UUID, topic: str, jurisdictions: Sequence[str]
    ) -> list[ExpectedSourceRecord]: ...

    def get_passages(self, workspace_id: UUID, passage_ids: Sequence[UUID]) -> list[PassageRecord]: ...

    def set_run_status(self, ctx: RunContext, status: RunStatus, failure_summary: str | None) -> None: ...

    def start_step(self, ctx: RunContext, record: StepRecord) -> UUID: ...

    def finish_step(self, ctx: RunContext, step_id: UUID, record: StepRecord) -> None: ...

    def save_plan(self, ctx: RunContext, version: int, plan: dict[str, object], step_id: UUID) -> UUID: ...

    def save_claims(self, ctx: RunContext, claims: Sequence[NewClaim]) -> list[StoredClaim]: ...

    def update_claim(self, ctx: RunContext, finding_id: UUID, claim: NewClaim) -> StoredClaim: ...

    def save_checks(
        self, ctx: RunContext, step_id: UUID, verdicts: Sequence[Verdict],
        *, input_snapshot: dict | None = None,
    ) -> None: ...

    def save_coverage(self, ctx: RunContext, rows: Sequence[CoverageRow]) -> None: ...

    def save_report(self, ctx: RunContext, snapshot: ReportSnapshot, html: str) -> UUID: ...

    def previous_findings(self, ctx: RunContext) -> list[PreviousFinding]:
        """Findings of the run this one re-runs, keyed as in ``mira.diff``; empty for a first run."""
        ...

    def save_diff_keys(self, ctx: RunContext, keys: dict[UUID, str]) -> None:
        """Store each finding's re-run diff key on analysis_findings.diff_key."""
        ...

    def approved_plan(self, ctx: RunContext) -> dict[str, object] | None:
        """The latest stored plan if an auditor approved it (research_plans.plan), else None."""
        ...

    def cancel_requested(self, ctx: RunContext) -> bool: ...


# --- In-memory implementation --------------------------------------------------


@dataclass
class SavedReport:
    id: UUID
    snapshot: ReportSnapshot
    html: str


@dataclass
class InMemoryStore:
    sources: list[SourceRecord] = field(default_factory=list)
    expected_sources: list[ExpectedSourceRecord] = field(default_factory=list)
    passages: list[PassageRecord] = field(default_factory=list)
    statuses: list[tuple[RunStatus, str | None]] = field(default_factory=list)
    steps: dict[UUID, StepRecord] = field(default_factory=dict)
    plans: list[dict[str, object]] = field(default_factory=list)
    claims: dict[UUID, StoredClaim] = field(default_factory=dict)
    checks: list[tuple[UUID, Verdict]] = field(default_factory=list)
    check_inputs: list[dict | None] = field(default_factory=list)
    coverage: list[CoverageRow] = field(default_factory=list)
    reports: list[SavedReport] = field(default_factory=list)
    cancel: bool = False
    previous: list[PreviousFinding] = field(default_factory=list)
    diff_keys: dict[UUID, str] = field(default_factory=dict)
    approved_stored_plan: dict[str, object] | None = None

    def list_sources(self, workspace_id: UUID) -> list[SourceRecord]:
        return list(self.sources)

    def list_expected_sources(
        self, workspace_id: UUID, topic: str, jurisdictions: Sequence[str]
    ) -> list[ExpectedSourceRecord]:
        return [row for row in self.expected_sources if row.jurisdiction_code in jurisdictions]

    def get_passages(self, workspace_id: UUID, passage_ids: Sequence[UUID]) -> list[PassageRecord]:
        wanted = set(passage_ids)
        return [passage for passage in self.passages if passage.id in wanted]

    def set_run_status(self, ctx: RunContext, status: RunStatus, failure_summary: str | None) -> None:
        self.statuses.append((status, failure_summary))

    def start_step(self, ctx: RunContext, record: StepRecord) -> UUID:
        step_id = uuid4()
        self.steps[step_id] = record
        return step_id

    def finish_step(self, ctx: RunContext, step_id: UUID, record: StepRecord) -> None:
        self.steps[step_id] = record

    def save_plan(self, ctx: RunContext, version: int, plan: dict[str, object], step_id: UUID) -> UUID:
        self.plans.append(plan)
        return uuid4()

    def save_claims(self, ctx: RunContext, claims: Sequence[NewClaim]) -> list[StoredClaim]:
        ids = {claim.draft.claim_label: uuid4() for claim in claims}
        stored = [
            StoredClaim(
                ids[claim.draft.claim_label],
                claim.draft,
                claim.evidence,
                tuple(ids[label] for label in claim.draft.depends_on),
            )
            for claim in claims
        ]
        self.claims.update({claim.finding_id: claim for claim in stored})
        return stored

    def update_claim(self, ctx: RunContext, finding_id: UUID, claim: NewClaim) -> StoredClaim:
        stored = StoredClaim(finding_id, claim.draft, claim.evidence, self.claims[finding_id].depends_on)
        self.claims[finding_id] = stored
        return stored

    def save_checks(
        self, ctx: RunContext, step_id: UUID, verdicts: Sequence[Verdict],
        *, input_snapshot: dict | None = None,
    ) -> None:
        self.checks.extend((step_id, verdict) for verdict in verdicts)
        self.check_inputs.extend(deepcopy(input_snapshot) for _ in verdicts)

    def save_coverage(self, ctx: RunContext, rows: Sequence[CoverageRow]) -> None:
        self.coverage.extend(rows)

    def save_report(self, ctx: RunContext, snapshot: ReportSnapshot, html: str) -> UUID:
        report = SavedReport(uuid4(), snapshot, html)
        self.reports.append(report)
        return report.id

    def previous_findings(self, ctx: RunContext) -> list[PreviousFinding]:
        return list(self.previous)

    def save_diff_keys(self, ctx: RunContext, keys: dict[UUID, str]) -> None:
        self.diff_keys.update(keys)

    def approved_plan(self, ctx: RunContext) -> dict[str, object] | None:
        return self.approved_stored_plan

    def cancel_requested(self, ctx: RunContext) -> bool:
        return self.cancel

    @property
    def status(self) -> RunStatus | None:
        return self.statuses[-1][0] if self.statuses else None
