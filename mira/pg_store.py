"""``RunStore`` on Postgres for the trusted worker (PRD v2 §5.1, §8).

Follows ``mira.db``: every write runs inside ``acting_as`` for the user who
started the run, every query filters by ``workspace_id``, and actor columns are
filled here. ``create_run`` saves a brief as a Project revision plus a queued run
(AG01); ``claim_next_run`` lets the worker pick up runs queued by the UI.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from mira.brief import analysis_run_fields, brief_from_rows, project_revision_fields
from mira.budget import RunBudget
from mira.config import REPORTS_DIR
from mira.contracts import CONTRACT_VERSION, Brief, CoverageRow, ReportSnapshot, RunStatus, StepRecord, Verdict
from mira.db import acting_as, require_role
from mira.report import TEMPLATE_VERSION
from mira.store import (
    ExpectedSourceRecord,
    NewClaim,
    PassageRecord,
    PreviousFinding,
    RunContext,
    SourceRecord,
    StoredClaim,
)

FINAL_STATUSES = ("partial", "failed", "cancelled", "draft")


def create_run(
    conn: psycopg.Connection,
    workspace_id: UUID,
    user_id: UUID,
    brief: Brief,
    budget: RunBudget,
    models: dict[str, str],
    previous_run_id: UUID | None = None,
) -> RunContext:
    """Save the brief as a new Project revision and a queued run; return its context."""
    revision = project_revision_fields(brief, "Research brief")
    run = analysis_run_fields(brief, budget, models)
    with acting_as(conn, user_id):
        require_role(conn, workspace_id)
        project_id = conn.execute(
            "insert into public.projects (workspace_id, owner_id, created_by) values (%s, %s, %s) returning id",
            (workspace_id, user_id, user_id),
        ).fetchone()["id"]
        revision_id = conn.execute(
            """insert into public.project_revisions
                 (workspace_id, project_id, revision_number, title, objective, risk_topics, markets,
                  reporting_period_start, reporting_period_end, change_reason, created_by)
               values (%s, %s, 1, %s, %s, %s, %s::char(2)[], %s, %s, %s, %s) returning id""",
            (workspace_id, project_id, revision["title"], revision["objective"], revision["risk_topics"],
             revision["markets"], revision["reporting_period_start"], revision["reporting_period_end"],
             revision["change_reason"], user_id),
        ).fetchone()["id"]
        run_id = conn.execute(
            """insert into public.analysis_runs
                 (workspace_id, project_revision_id, idempotency_key, query_mode, as_of_date, resolved_markets,
                  source_limits, model_settings, retrieval_settings, previous_run_id, created_by)
               values (%s, %s, %s, %s, %s, %s::char(2)[], %s, %s, %s, %s, %s) returning id""",
            (workspace_id, revision_id, str(uuid.uuid4()), run["query_mode"], run["as_of_date"],
             run["resolved_markets"], Jsonb(run["source_limits"]), Jsonb(run["model_settings"]),
             Jsonb(run["retrieval_settings"]), previous_run_id, user_id),
        ).fetchone()["id"]
        analysis_revision_id = conn.execute(
            """insert into public.analysis_revisions (workspace_id, analysis_run_id, revision_number, created_by)
               values (%s, %s, 1, %s) returning id""",
            (workspace_id, run_id, user_id),
        ).fetchone()["id"]
    return RunContext(workspace_id, user_id, run_id, analysis_revision_id, brief, budget, previous_run_id)


def load_run(conn: psycopg.Connection, run_id: UUID) -> RunContext:
    """Rebuild a run's context from its rows, for the worker."""
    run = conn.execute("select * from public.analysis_runs where id = %s", (run_id,)).fetchone()
    revision = conn.execute("select * from public.project_revisions where id = %s", (run["project_revision_id"],)).fetchone()
    analysis_revision = conn.execute(
        "select id from public.analysis_revisions where analysis_run_id = %s order by revision_number desc limit 1",
        (run_id,),
    ).fetchone()
    if analysis_revision is None:
        with acting_as(conn, run["created_by"]):
            analysis_revision = conn.execute(
                """insert into public.analysis_revisions (workspace_id, analysis_run_id, revision_number, created_by)
                   values (%s, %s, 1, %s) returning id""",
                (run["workspace_id"], run_id, run["created_by"]),
            ).fetchone()
    limits = run["source_limits"] or {}
    default = RunBudget.from_env()  # the configured caps, not the 2M-token class default
    budget = RunBudget(
        max_fetched_documents=int(limits.get("max_fetched_documents", default.max_fetched_documents)),
        max_llm_tokens=int(limits.get("max_llm_tokens", default.max_llm_tokens)),
        max_run_minutes=float(limits.get("max_run_minutes", default.max_run_minutes)),
        max_gap_rounds=int(limits.get("max_gap_rounds", default.max_gap_rounds)),
    )
    return RunContext(run["workspace_id"], run["created_by"], run_id, analysis_revision["id"],
                      brief_from_rows(revision, run), budget, run["previous_run_id"])


def claim_next_run(conn: psycopg.Connection, workspace_id: UUID) -> UUID | None:
    """Take the workspace's oldest queued run, marking it running so no other worker takes it."""
    with conn.transaction():
        row = conn.execute(
            """select id, created_by from public.analysis_runs where workspace_id = %s and status = 'queued'
               order by created_at limit 1 for update skip locked""",
            (workspace_id,),
        ).fetchone()
        if row is None:
            return None
    with acting_as(conn, row["created_by"]):
        conn.execute(
            "update public.analysis_runs set status = 'running', started_at = now() where id = %s and status = 'queued'",
            (row["id"],),
        )
    return row["id"]


def _as_date(value: datetime | None) -> date | None:
    return value.date() if value else None


class PostgresStore:
    def __init__(self, conn: psycopg.Connection, reports_dir: Path = REPORTS_DIR) -> None:
        self.conn = conn
        self.reports_dir = reports_dir

    # --- Reads ----------------------------------------------------------------

    def list_sources(self, workspace_id: UUID) -> list[SourceRecord]:
        rows = self.conn.execute(
            """select id, name, source_type, base_url, jurisdiction_code, permitted_operations, connector_config
               from public.sources where workspace_id = %s and is_active order by source_key""",
            (workspace_id,),
        ).fetchall()
        return [
            SourceRecord(row["id"], row["name"], row["source_type"], row["base_url"],
                         (row["jurisdiction_code"] or "").strip() or None, tuple(row["permitted_operations"]),
                         row["connector_config"] or {})
            for row in rows
        ]

    def list_expected_sources(
        self, workspace_id: UUID, topic: str, jurisdictions: Sequence[str]
    ) -> list[ExpectedSourceRecord]:
        rows = self.conn.execute(
            """select id, list_version, jurisdiction_code, category, source_id, document_hint
               from public.expected_sources e
               where workspace_id = %s and topic = %s and jurisdiction_code = any(%s::char(2)[]) and is_active
                 and list_version = (select max(list_version) from public.expected_sources
                                     where workspace_id = e.workspace_id and topic = e.topic and is_active)
               order by jurisdiction_code, category, document_hint""",
            (workspace_id, topic, list(jurisdictions)),
        ).fetchall()
        return [
            ExpectedSourceRecord(row["id"], row["list_version"], row["jurisdiction_code"].strip(), row["category"],
                                 row["source_id"], row["document_hint"])
            for row in rows
        ]

    def get_passages(self, workspace_id: UUID, passage_ids: Sequence[UUID]) -> list[PassageRecord]:
        if not passage_ids:
            return []
        rows = self.conn.execute(
            """select p.id, p.document_version_id, v.document_id, d.source_id, s.name as source_name,
                      s.jurisdiction_code, v.title, v.source_url, v.published_at, p.passage_number, p.content,
                      coalesce(v.metadata->>'import', '') = 'manual' as imported
               from public.document_passages p
               join public.document_versions v on v.id = p.document_version_id
               join public.documents d on d.id = v.document_id
               join public.sources s on s.id = d.source_id
               where p.workspace_id = %s and p.id = any(%s)""",
            (workspace_id, list(passage_ids)),
        ).fetchall()
        return [
            PassageRecord(row["id"], row["document_version_id"], row["document_id"], row["source_id"],
                          row["source_name"], (row["jurisdiction_code"] or "").strip() or None, row["title"],
                          row["source_url"], _as_date(row["published_at"]), row["passage_number"], row["content"],
                          row["imported"])
            for row in rows
        ]

    def save_diff_keys(self, ctx: RunContext, keys: dict[UUID, str]) -> None:
        with acting_as(self.conn, ctx.user_id):
            for finding_id, key in keys.items():
                self.conn.execute(
                    "update public.analysis_findings set diff_key = %s where id = %s and workspace_id = %s",
                    (key, finding_id, ctx.workspace_id),
                )

    def previous_findings(self, ctx: RunContext) -> list[PreviousFinding]:
        """The previous run's findings with the diff key stored when they were saved (PRD v2 §6.5)."""
        if ctx.previous_run_id is None:
            return []
        # Diff only against a run that finished with a report. A failed or cancelled run is incomplete,
        # so its findings would show things as "no longer supported" that were never checked.
        rows = self.conn.execute(
            """select f.diff_key, f.title, f.content from public.analysis_findings f
               join public.analysis_runs r on r.id = f.analysis_run_id and r.workspace_id = f.workspace_id
               where f.analysis_run_id = %s and f.workspace_id = %s and f.diff_key is not null
                 and r.status in ('draft', 'reviewed', 'superseded')
               order by f.created_at""",
            (ctx.previous_run_id, ctx.workspace_id),
        ).fetchall()
        return [PreviousFinding(row["diff_key"], row["title"], row["content"]) for row in rows]

    def cancel_requested(self, ctx: RunContext) -> bool:
        row = self.conn.execute(
            "select status from public.analysis_runs where id = %s and workspace_id = %s",
            (ctx.analysis_run_id, ctx.workspace_id),
        ).fetchone()
        return row is not None and row["status"] == "cancelled"

    # --- Writes ---------------------------------------------------------------

    def set_run_status(self, ctx: RunContext, status: RunStatus, failure_summary: str | None) -> None:
        with acting_as(self.conn, ctx.user_id):
            self.conn.execute(
                """update public.analysis_runs
                   set status = %s, failure_summary = %s,
                       started_at = coalesce(started_at, now()),
                       finished_at = case when %s = any(%s) then now() else finished_at end
                   where id = %s and workspace_id = %s""",
                (status, failure_summary, status, list(FINAL_STATUSES), ctx.analysis_run_id, ctx.workspace_id),
            )

    def _step_values(self, record: StepRecord) -> tuple[object, ...]:
        return (record.status, record.contract_version, record.model, record.prompt_version, record.temperature,
                Jsonb(record.input_refs), Jsonb(record.output_refs), record.tokens_in, record.tokens_out,
                record.started_at, record.finished_at, record.error)

    def start_step(self, ctx: RunContext, record: StepRecord) -> UUID:
        with acting_as(self.conn, ctx.user_id):
            return self.conn.execute(
                """insert into public.agent_steps
                     (workspace_id, analysis_run_id, step_no, role, jurisdiction_code, gap_round, status,
                      contract_version, model, prompt_version, temperature, input_refs, output_refs, tokens_in,
                      tokens_out, started_at, finished_at, error)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (ctx.workspace_id, ctx.analysis_run_id, record.step_no, record.role, record.jurisdiction_code,
                 record.gap_round, *self._step_values(record)),
            ).fetchone()["id"]

    def finish_step(self, ctx: RunContext, step_id: UUID, record: StepRecord) -> None:
        with acting_as(self.conn, ctx.user_id):
            self.conn.execute(
                """update public.agent_steps
                   set status = %s, contract_version = %s, model = %s, prompt_version = %s, temperature = %s,
                       input_refs = %s, output_refs = %s, tokens_in = %s, tokens_out = %s, started_at = %s,
                       finished_at = %s, error = %s
                   where id = %s and workspace_id = %s""",
                (*self._step_values(record), step_id, ctx.workspace_id),
            )

    def save_plan(self, ctx: RunContext, version: int, plan: dict[str, object], step_id: UUID) -> UUID:
        with acting_as(self.conn, ctx.user_id):
            return self.conn.execute(
                """insert into public.research_plans
                     (workspace_id, analysis_run_id, version, contract_version, plan, agent_step_id)
                   values (%s, %s, %s, %s, %s, %s) returning id""",
                (ctx.workspace_id, ctx.analysis_run_id, version, CONTRACT_VERSION, Jsonb(plan), step_id),
            ).fetchone()["id"]

    def _evidence_id(self, ctx: RunContext, passage_id: UUID) -> tuple[UUID, UUID]:
        version = self.conn.execute(
            "select document_version_id from public.document_passages where id = %s and workspace_id = %s",
            (passage_id, ctx.workspace_id),
        ).fetchone()["document_version_id"]
        row = self.conn.execute(
            """insert into public.analysis_evidence (workspace_id, analysis_run_id, document_version_id, passage_id,
                                                     selection_reason)
               values (%s, %s, %s, %s, 'cited by analyst') on conflict do nothing returning id""",
            (ctx.workspace_id, ctx.analysis_run_id, version, passage_id),
        ).fetchone()
        if row is None:
            row = self.conn.execute(
                """select id from public.analysis_evidence where analysis_run_id = %s and document_version_id = %s
                     and passage_id = %s and incident_revision_id is null and regulation_version_id is null
                     and provision_id is null""",
                (ctx.analysis_run_id, version, passage_id),
            ).fetchone()
        return row["id"], version

    def _insert_evidence(self, ctx: RunContext, finding_id: UUID, claim: NewClaim) -> UUID | None:
        document_id = None
        for item in claim.evidence:
            evidence_id, version_id = self._evidence_id(ctx, item.passage_id)
            if document_id is None:
                document_id = self.conn.execute(
                    "select document_id from public.document_versions where id = %s", (version_id,)
                ).fetchone()["document_id"]
            self.conn.execute(
                """insert into public.finding_evidence
                     (workspace_id, analysis_run_id, finding_id, analysis_evidence_id, support_type, supporting_quote)
                   values (%s, %s, %s, %s, 'supports', %s) on conflict do nothing""",
                (ctx.workspace_id, ctx.analysis_run_id, finding_id, evidence_id, item.supporting_quote),
            )
        return document_id

    @staticmethod
    def _finding_values(claim: NewClaim) -> tuple[object, ...]:
        d = claim.draft
        return (d.finding_type, d.title, d.content, d.priority, d.evidence_confidence, d.priority_reason,
                d.jurisdiction_code, d.change_type, d.industry_category, d.is_inference,
                d.evidence_confidence_reason, d.key_date, d.key_date_kind)

    def save_claims(self, ctx: RunContext, claims: Sequence[NewClaim]) -> list[StoredClaim]:
        ids: dict[str, UUID] = {}
        with acting_as(self.conn, ctx.user_id):
            for claim in claims:
                finding_id = self.conn.execute(
                    """insert into public.analysis_findings
                         (workspace_id, analysis_run_id, analysis_revision_id, finding_type, title, content, priority,
                          evidence_confidence, priority_reason, jurisdiction_code, change_type, industry_category,
                          is_inference, evidence_confidence_reason, key_date, key_date_kind, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                    (ctx.workspace_id, ctx.analysis_run_id, ctx.analysis_revision_id, *self._finding_values(claim),
                     ctx.user_id),
                ).fetchone()["id"]
                ids[claim.draft.claim_label] = finding_id
                document_id = self._insert_evidence(ctx, finding_id, claim)
                if document_id:
                    self.conn.execute("update public.analysis_findings set document_id = %s where id = %s",
                                      (document_id, finding_id))
            for claim in claims:
                for label in claim.draft.depends_on:
                    self.conn.execute(
                        """insert into public.finding_dependencies
                             (workspace_id, analysis_run_id, finding_id, depends_on_finding_id)
                           values (%s, %s, %s, %s)""",
                        (ctx.workspace_id, ctx.analysis_run_id, ids[claim.draft.claim_label], ids[label]),
                    )
        return [
            StoredClaim(ids[c.draft.claim_label], c.draft, c.evidence, tuple(ids[label] for label in c.draft.depends_on))
            for c in claims
        ]

    def update_claim(self, ctx: RunContext, finding_id: UUID, claim: NewClaim) -> StoredClaim:
        with acting_as(self.conn, ctx.user_id):
            self.conn.execute(
                """update public.analysis_findings
                   set finding_type = %s, title = %s, content = %s, priority = %s, evidence_confidence = %s,
                       priority_reason = %s, jurisdiction_code = %s, change_type = %s, industry_category = %s,
                       is_inference = %s, evidence_confidence_reason = %s, key_date = %s, key_date_kind = %s
                   where id = %s and workspace_id = %s""",
                (*self._finding_values(claim), finding_id, ctx.workspace_id),
            )
            self.conn.execute(
                "delete from public.finding_evidence where finding_id = %s and support_type = 'supports'", (finding_id,)
            )
            self._insert_evidence(ctx, finding_id, claim)
            depends = self.conn.execute(
                "select depends_on_finding_id from public.finding_dependencies where finding_id = %s", (finding_id,)
            ).fetchall()
        return StoredClaim(finding_id, claim.draft, claim.evidence, tuple(row["depends_on_finding_id"] for row in depends))

    def save_checks(self, ctx: RunContext, step_id: UUID, verdicts: Sequence[Verdict]) -> None:
        with acting_as(self.conn, ctx.user_id):
            for v in verdicts:
                self.conn.execute(
                    # clock_timestamp(), not now(): checks saved in one transaction keep their order.
                    """insert into public.claim_checks
                         (workspace_id, analysis_run_id, finding_id, attempt, method, verdict, reason, model,
                          prompt_version, agent_step_id, checked_at)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())""",
                    (ctx.workspace_id, ctx.analysis_run_id, v.finding_id, v.attempt, v.method, v.verdict, v.reason,
                     v.model, v.prompt_version, step_id),
                )

    def save_coverage(self, ctx: RunContext, rows: Sequence[CoverageRow]) -> None:
        with acting_as(self.conn, ctx.user_id):
            for row in rows:
                self.conn.execute(
                    """insert into public.coverage_results
                         (workspace_id, analysis_run_id, expected_source_id, gap_round, status, document_version_id, note)
                       values (%s, %s, %s, %s, %s, %s, %s)""",
                    (ctx.workspace_id, ctx.analysis_run_id, row.expected_source_id, row.gap_round, row.status,
                     row.document_version_id, row.note),
                )

    def save_report(self, ctx: RunContext, snapshot: ReportSnapshot, html: str) -> UUID:
        with acting_as(self.conn, ctx.user_id):
            version = self.conn.execute(
                "select coalesce(max(report_version), 0) + 1 as v from public.reports where analysis_revision_id = %s",
                (ctx.analysis_revision_id,),
            ).fetchone()["v"]
            relative = Path(str(ctx.analysis_run_id)) / f"report-v{version}.html"
            path = self.reports_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            return self.conn.execute(
                """insert into public.reports
                     (workspace_id, analysis_revision_id, report_version, format, review_status, template_version,
                      evidence_snapshot, artifact_storage_path, generated_by)
                   values (%s, %s, %s, 'html', 'draft', %s, %s, %s, %s) returning id""",
                (ctx.workspace_id, ctx.analysis_revision_id, version, TEMPLATE_VERSION,
                 Jsonb(json.loads(snapshot.model_dump_json())), str(relative), ctx.user_id),
            ).fetchone()["id"]
