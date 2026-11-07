"""Worker job: render the reviewed file of each sign-off that has none yet (PRD v2 §6.6).

The app records a sign-off as a reviewed reports row with no artifact (see app/streamlit_app.py,
_sign_off). This job finds those rows, renders each from its saved snapshot with mira.render, writes the
file next to the drafts, and records the path on the row. It never calls a model and never re-analyses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg

from mira.brief import brief_from_rows
from mira.config import REPORTS_DIR
from mira.contracts import ClaimDraft, ReportSnapshot
from mira.db import acting_as
from mira.pg_store import PostgresStore
from mira.render import SavedFinding, cited_finding_ids, render_signed_off
from mira.store import ClaimEvidence, ExpectedSourceRecord


def reviewer_name(conn: psycopg.Connection, user_id: UUID | None) -> str:
    """The reviewer as shown on the page: their email from auth.users, never a raw ID."""
    if user_id is None:
        raise ValueError("a reviewed report has no reviewer")
    row = conn.execute("select email from auth.users where id = %s", (user_id,)).fetchone()
    return row["email"] if row and row["email"] else "reviewer (name not on record)"


def pending_signoffs(conn: psycopg.Connection, workspace_id: UUID) -> list[dict[str, object]]:
    """Reviewed reports that have no rendered file yet, oldest first."""
    return conn.execute(
        """select r.id, r.workspace_id, r.analysis_revision_id, r.report_version, r.evidence_snapshot,
                  r.reviewed_by, r.reviewed_at, r.generated_by
           from public.reports r
           where r.workspace_id = %s and r.review_status = 'reviewed' and r.artifact_storage_path is null
           order by r.generated_at""",
        (workspace_id,),
    ).fetchall()


def load_findings(conn: psycopg.Connection, workspace_id: UUID, finding_ids: list[UUID]) -> list[SavedFinding]:
    """The stored findings a render needs, with their evidence and dependencies. Read only."""
    if not finding_ids:
        return []
    rows = conn.execute(
        """select f.id, f.finding_type, f.title, f.content, f.priority, f.evidence_confidence, f.priority_reason,
                  f.jurisdiction_code, f.change_type, f.industry_category, f.is_inference,
                  f.evidence_confidence_reason, f.key_date, f.key_date_kind
           from public.analysis_findings f
           where f.workspace_id = %s and f.id = any(%s)""",
        (workspace_id, finding_ids),
    ).fetchall()
    evidence = conn.execute(
        """select e.finding_id, e.supporting_quote, ae.passage_id
           from public.finding_evidence e
           join public.analysis_evidence ae on ae.id = e.analysis_evidence_id
           where e.workspace_id = %s and e.finding_id = any(%s) and e.support_type = 'supports'
           order by e.created_at""",
        (workspace_id, finding_ids),
    ).fetchall()
    depends = conn.execute(
        """select finding_id, depends_on_finding_id from public.finding_dependencies
           where workspace_id = %s and finding_id = any(%s)""",
        (workspace_id, finding_ids),
    ).fetchall()
    by_evidence: dict[UUID, list[ClaimEvidence]] = {}
    for row in evidence:
        by_evidence.setdefault(row["finding_id"], []).append(ClaimEvidence(row["passage_id"], row["supporting_quote"]))
    by_depends: dict[UUID, list[UUID]] = {}
    for row in depends:
        by_depends.setdefault(row["finding_id"], []).append(row["depends_on_finding_id"])
    labels = {row["id"]: f"C{number}" for number, row in enumerate(rows, start=1)}
    findings = []
    for row in rows:
        # The stored row already passed the model-output rules when it was saved, and ClaimDraft enforces
        # those rules again. Each finding gets its own label so it cannot depend on itself, and a fact is
        # never given a dependency or an inference a citation.
        is_inference = row["is_inference"]
        draft_depends = [labels[d] for d in by_depends.get(row["id"], []) if d in labels] if is_inference else []
        if is_inference and not draft_depends:
            raise ValueError(f"stored inference {row['id']} has no stored facts it rests on")
        draft = ClaimDraft(
            claim_label=labels[row["id"]], finding_type=row["finding_type"], title=row["title"],
            content=row["content"], jurisdiction_code=(row["jurisdiction_code"] or "").strip() or None,
            change_type=row["change_type"], industry_category=row["industry_category"],
            key_date=row["key_date"], key_date_kind=row["key_date_kind"], is_inference=is_inference,
            citations=[] if is_inference else [
                {"passage_label": "P1", "supporting_quote": e.supporting_quote} for e in by_evidence.get(row["id"], [])[:1]
            ],
            depends_on=draft_depends, priority=row["priority"], priority_reason=row["priority_reason"],
            evidence_confidence=row["evidence_confidence"], evidence_confidence_reason=row["evidence_confidence_reason"],
        )
        findings.append(SavedFinding(row["id"], draft, tuple(by_evidence.get(row["id"], [])),
                                     tuple(by_depends.get(row["id"], []))))
    return findings


def render_one(conn: psycopg.Connection, workspace_id: UUID, pending: dict[str, object], reports_dir: Path) -> UUID:
    """Render one reviewed report and record its file. Raises on failure, leaving the row pending."""
    snapshot = ReportSnapshot.model_validate(pending["evidence_snapshot"])
    finding_ids = sorted(cited_finding_ids(snapshot), key=str)
    revision = conn.execute(
        """select a.analysis_run_id, r.project_revision_id from public.analysis_revisions a
           join public.analysis_runs r on r.id = a.analysis_run_id
           where a.id = %s and a.workspace_id = %s""",
        (pending["analysis_revision_id"], workspace_id),
    ).fetchone()
    run = conn.execute(
        "select * from public.analysis_runs where id = %s and workspace_id = %s",
        (revision["analysis_run_id"], workspace_id),
    ).fetchone()
    revision_row = conn.execute(
        "select * from public.project_revisions where id = %s", (run["project_revision_id"],),
    ).fetchone()
    brief = brief_from_rows(revision_row, run)
    if finding_ids:
        # A summary-only inference in an older snapshot may cite facts that
        # do not appear directly in any section. Load their evidence as well.
        finding_ids = [row["id"] for row in conn.execute(
            """with recursive evidence_findings(id) as (
                   select unnest(%s::uuid[])
                   union
                   select d.depends_on_finding_id from public.finding_dependencies d
                   join evidence_findings f on f.id = d.finding_id
                   where d.workspace_id = %s
               )
               select id from evidence_findings order by id""",
            (finding_ids, workspace_id),
        )]
    findings = load_findings(conn, workspace_id, finding_ids)
    passage_ids = {evidence.passage_id for finding in findings for evidence in finding.evidence}
    store = PostgresStore(conn, reports_dir=reports_dir)
    passages = {p.id: p for p in store.get_passages(workspace_id, list(passage_ids))}
    expected_rows = conn.execute(
        "select * from public.expected_sources where workspace_id = %s", (workspace_id,),
    ).fetchall()
    expected = {
        row["id"]: ExpectedSourceRecord(row["id"], row["list_version"], (row["jurisdiction_code"] or "").strip(),
                                        row["category"], row["source_id"], row["document_hint"])
        for row in expected_rows
    }
    html = render_signed_off(
        snapshot, brief=brief, findings=findings, passages=passages,
        expected=expected, reviewer=reviewer_name(conn, pending["reviewed_by"]),
        decided_at=pending["reviewed_at"], generated_at=datetime.now(UTC),
    )
    relative = Path(str(run["id"])) / f"report-v{pending['report_version']}-reviewed.html"
    path = reports_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    with acting_as(conn, pending["reviewed_by"]):
        conn.execute(
            "update public.reports set artifact_storage_path = %s where id = %s and workspace_id = %s",
            (str(relative), pending["id"], workspace_id),
        )
    return pending["id"]


def render_pending(conn: psycopg.Connection, workspace_id: UUID, reports_dir: Path = REPORTS_DIR) -> list[UUID]:
    """Render every pending sign-off. Each one is independent: a failure is reported and that row stays pending for
    the next pass, while the rows after it still render."""
    rendered: list[UUID] = []
    for pending in pending_signoffs(conn, workspace_id):
        try:
            rendered.append(render_one(conn, workspace_id, pending, reports_dir))
        except Exception as exc:  # noqa: BLE001 - one bad row must not block the rest; it stays pending
            print(f"sign-off {pending['id']} not rendered, will retry: {type(exc).__name__}: {exc}")
    return rendered
