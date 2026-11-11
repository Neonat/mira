"""Worker connection tests. Need a disposable database with all migrations applied:

    MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres pytest

Never point this at a shared database: it inserts test users and rows. Each test
gets its own throwaway workspace, so a local development database stays usable.
"""

import os
import uuid
from datetime import date

import psycopg
import pytest

from mira.budget import RunBudget
from mira.config import report_file
from mira.contracts import CONTRACT_VERSION, Brief, ReportSnapshot
from mira.db import NotAuthorisedError, acting_as, connect, require_role
from mira.pg_store import PostgresStore, create_run

DSN = os.environ.get("MIRA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="MIRA_TEST_DATABASE_URL not set")


@pytest.fixture()
def conn():
    with connect(DSN) as connection:
        yield connection


@pytest.fixture()
def workspace_id(conn):
    return conn.execute(
        "insert into public.workspaces (slug, name) values (%s, 'Worker test') returning id",
        (f"t-{uuid.uuid4().hex[:12]}",),
    ).fetchone()["id"]


def make_user(conn, workspace_id, role):
    user_id = uuid.uuid4()
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, f"{user_id}@test.local"))
    if role:
        conn.execute(
            "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, %s)",
            (workspace_id, user_id, role),
        )
    return user_id


def make_run(conn, workspace_id, user_id):
    project_id = conn.execute(
        "insert into public.projects (workspace_id, created_by) values (%s, %s) returning id",
        (workspace_id, user_id),
    ).fetchone()["id"]
    revision_id = conn.execute(
        """insert into public.project_revisions
             (workspace_id, project_id, revision_number, title, objective, risk_topics, markets, change_reason, created_by,
              reporting_period_start, reporting_period_end)
           values (%s, %s, 1, 'AML brief', 'test', array['AML/CFT'], array['SG','HK']::char(2)[], 'brief', %s,
                   current_date-365, current_date)
           returning id""",
        (workspace_id, project_id, user_id),
    ).fetchone()["id"]
    # Created cancelled: a queued run in a development database would be picked up by the worker.
    return conn.execute(
        """insert into public.analysis_runs
             (workspace_id, project_revision_id, idempotency_key, query_mode, as_of_date, created_by, status, failure_summary)
           values (%s, %s, %s, 'current', current_date, %s, 'cancelled', 'test fixture, never to run') returning id""",
        (workspace_id, revision_id, str(uuid.uuid4()), user_id),
    ).fetchone()["id"]


def test_audit_trail_records_initiating_user(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        require_role(conn, workspace_id)
        run_id = make_run(conn, workspace_id, analyst)
    actor = conn.execute(
        "select actor_id from public.audit_events where entity_type = 'analysis_runs' and entity_id = %s",
        (run_id,),
    ).fetchone()["actor_id"]
    assert actor == analyst


def test_worker_can_save_sources_for_an_analyst(conn, workspace_id):
    # RLS would refuse this insert for an analyst's own login; the worker may do it.
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        source_id = conn.execute(
            """insert into public.sources (workspace_id, source_key, name, source_type, base_url, permitted_operations, created_by, is_active)
               values (%s, %s, 'MAS', 'regulator', 'https://www.mas.gov.sg', array['metadata','fetch'], %s, false) returning id""",
            (workspace_id, f"mas-{uuid.uuid4()}", analyst),
        ).fetchone()["id"]
    assert source_id


def test_role_check_refuses_viewer_and_non_member(conn, workspace_id):
    for role in ("viewer", None):
        user = make_user(conn, workspace_id, role)
        with pytest.raises(NotAuthorisedError), acting_as(conn, user):
            require_role(conn, workspace_id)


def test_claims_do_not_leak_between_transactions(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        assert conn.execute("select auth.uid() as uid").fetchone()["uid"] == analyst
    assert conn.execute("select auth.uid() as uid").fetchone()["uid"] is None


def test_new_constraints(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        run_id = make_run(conn, workspace_id, analyst)
        conn.execute("update public.analysis_runs set status = 'cancelled' where id = %s", (run_id,))
    with pytest.raises(psycopg.errors.CheckViolation), acting_as(conn, analyst):
        conn.execute(
            """insert into public.sources (workspace_id, source_key, name, source_type, permitted_operations)
               values (%s, %s, 'x', 'website', array['crawl_everything'])""",
            (workspace_id, f"bad-{uuid.uuid4()}"),
        )


# --- App-user access (row-level security applies) ------------------------------


def as_app_user(conn, user_id):
    """Like a Supabase API request: claims set and role switched to authenticated."""
    conn.execute(
        "select set_config('request.jwt.claim.sub', %s, true), set_config('request.jwt.claims', %s, true)",
        (str(user_id), '{"sub": "%s", "role": "authenticated"}' % user_id),
    )
    conn.execute("set local role authenticated")


def test_report_visibility_and_files_for_two_workspaces(conn, tmp_path):
    # The fixture and its queued runs are never committed or visible to a worker.
    with conn.transaction(force_rollback=True):
        demo_viewer = make_user(conn, None, None)
        store = PostgresStore(conn, tmp_path)
        report_by_member = {}
        html_by_report = {}
        for market in ("SG", "HK"):
            workspace_id = conn.execute(
                "insert into public.workspaces (slug, name) values (%s, %s) returning id",
                (f"t-{uuid.uuid4().hex[:12]}", f"Test {market}"),
            ).fetchone()["id"]
            member = make_user(conn, workspace_id, "analyst")
            conn.execute(
                "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'viewer')",
                (workspace_id, demo_viewer),
            )
            brief = Brief(topic="AML/CFT", jurisdictions=[market], period_start=date(2025, 1, 1),
                          period_end=date(2025, 12, 31), as_of_date=date(2026, 1, 1), plan_requires_approval=False)
            ctx = create_run(conn, workspace_id, member, brief, RunBudget(), {})
            snapshot = ReportSnapshot(contract_version=CONTRACT_VERSION, analysis_run_id=ctx.analysis_run_id,
                                      analysis_revision_id=ctx.analysis_revision_id, sections=[], coverage=[],
                                      unresolved_finding_ids=[])
            html = f"<p>{market} test report</p>"
            report_id = store.save_report(ctx, snapshot, html)
            report_by_member[member] = {report_id}
            html_by_report[report_id] = html

        report_by_member[demo_viewer] = set(html_by_report)
        for user_id, expected_reports in report_by_member.items():
            with conn.transaction(force_rollback=True):
                as_app_user(conn, user_id)
                reports = conn.execute(
                    """select r.id, r.artifact_storage_path, r.report_version, r.review_status, a.analysis_run_id
                       from public.reports r join public.analysis_revisions a
                         on (a.id, a.workspace_id) = (r.analysis_revision_id, r.workspace_id)
                       where r.id = any(%s)""",
                    (list(html_by_report),),
                ).fetchall()
                assert {row["id"] for row in reports} == expected_reports
                for row in reports:
                    path = report_file(row["artifact_storage_path"], run_id=row["analysis_run_id"],
                                       version=row["report_version"], reviewed=row["review_status"] == "reviewed",
                                       reports_dir=tmp_path)
                    assert path is not None
                    assert path.read_text(encoding="utf-8") == html_by_report[row["id"]]


def make_plan(conn, workspace_id, user_id):
    run_id = make_run(conn, workspace_id, user_id)
    return conn.execute(
        """insert into public.research_plans (workspace_id, analysis_run_id, version, contract_version, plan)
           values (%s, %s, 1, '1.0', '{}'::jsonb) returning id""",
        (workspace_id, run_id),
    ).fetchone()["id"], run_id


def test_app_user_cannot_write_worker_tables(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        run_id = make_run(conn, workspace_id, analyst)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, analyst)
        conn.execute(
            "insert into public.agent_steps (workspace_id, analysis_run_id, step_no, role) values (%s, %s, 1, 'planner')",
            (workspace_id, run_id),
        )


def test_app_user_can_read_agent_steps_in_own_workspace(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    outsider = make_user(conn, workspace_id, None)
    with acting_as(conn, analyst):
        run_id = make_run(conn, workspace_id, analyst)
        conn.execute(
            "insert into public.agent_steps (workspace_id, analysis_run_id, step_no, role) values (%s, %s, 1, 'planner')",
            (workspace_id, run_id),
        )
    for user, expected in ((analyst, 1), (outsider, 0)):
        with conn.transaction():
            as_app_user(conn, user)
            count = conn.execute(
                "select count(*) as n from public.agent_steps where analysis_run_id = %s", (run_id,)
            ).fetchone()["n"]
        assert count == expected


def test_plan_can_be_approved_once_by_analyst(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        plan_id, _ = make_plan(conn, workspace_id, analyst)
    approve = "update public.research_plans set approved_by = %s, approved_at = now() where id = %s"
    with conn.transaction():
        as_app_user(conn, analyst)
        assert conn.execute(approve, (analyst, plan_id)).rowcount == 1
    with conn.transaction():
        as_app_user(conn, analyst)
        assert conn.execute(approve, (analyst, plan_id)).rowcount == 0


def test_plan_approval_must_name_the_approver(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    other = make_user(conn, workspace_id, "analyst")
    with acting_as(conn, analyst):
        plan_id, _ = make_plan(conn, workspace_id, analyst)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, analyst)
        conn.execute(
            "update public.research_plans set approved_by = %s, approved_at = now() where id = %s", (other, plan_id)
        )


def test_only_curators_maintain_expected_sources(conn, workspace_id):
    curator = make_user(conn, workspace_id, "curator")
    analyst = make_user(conn, workspace_id, "analyst")
    source_id = conn.execute(
        """insert into public.sources (workspace_id, source_key, name, source_type, is_active)
           values (%s, %s, 'MAS', 'regulator', false) returning id""",
        (workspace_id, f"mas-{uuid.uuid4()}"),
    ).fetchone()["id"]
    insert = """insert into public.expected_sources
                  (workspace_id, list_version, topic, jurisdiction_code, category, source_id, document_hint, is_active)
                values (%s, 1, 'AML/CFT', 'SG', 'rule', %s, %s, false)"""
    with conn.transaction():
        as_app_user(conn, curator)
        conn.execute(insert, (workspace_id, source_id, f"Notice 626 {uuid.uuid4()}"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, analyst)
        conn.execute(insert, (workspace_id, source_id, f"Notice 626 {uuid.uuid4()}"))


def make_report(conn, workspace_id, analyst):
    """A run with one finding and a draft report, written by the worker."""
    with acting_as(conn, analyst):
        run_id = make_run(conn, workspace_id, analyst)
        revision_id = conn.execute(
            """insert into public.analysis_revisions (workspace_id, analysis_run_id, revision_number, created_by)
               values (%s, %s, 1, %s) returning id""",
            (workspace_id, run_id, analyst),
        ).fetchone()["id"]
        finding_id = conn.execute(
            """insert into public.analysis_findings (workspace_id, analysis_run_id, analysis_revision_id, finding_type,
                 title, content, created_by)
               values (%s, %s, %s, 'external_fact', 'HKMA guidance', 'HKMA issued guidance.', %s) returning id""",
            (workspace_id, run_id, revision_id, analyst),
        ).fetchone()["id"]
        conn.execute(
            """insert into public.reports (workspace_id, analysis_revision_id, report_version, format, template_version,
                 evidence_snapshot, generated_by)
               values (%s, %s, 1, 'html', 'report/1', '{}'::jsonb, %s)""",
            (workspace_id, revision_id, analyst),
        )
    return revision_id, finding_id


SIGN_OFF = """with args(workspace_id, revision_id, actor, reviewer) as (
                values (%s::uuid, %s::uuid, %s::uuid, %s::uuid)
              )
              insert into public.reports (workspace_id, analysis_revision_id, report_version, format, review_status,
                template_version, evidence_snapshot, generated_by, reviewed_by, reviewed_at)
              select a.workspace_id, a.id, 2, 'html', 'reviewed', 'report/1',
                jsonb_build_object('contract_version','1.4','analysis_run_id',a.analysis_run_id,
                  'analysis_revision_id',a.id,'sections','[]'::jsonb,'coverage','[]'::jsonb,
                  'unresolved_finding_ids','[]'::jsonb,'review_outcomes','{}'::jsonb),
                args.actor, args.reviewer, now()
              from args join public.analysis_revisions a on a.id=args.revision_id
                and a.workspace_id=args.workspace_id"""


def test_reviewer_records_decisions_and_signs_off(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    reviewer = make_user(conn, workspace_id, "reviewer")
    revision_id, finding_id = make_report(conn, workspace_id, analyst)
    with conn.transaction():
        as_app_user(conn, reviewer)
        conn.execute(
            """insert into public.finding_reviews (workspace_id, finding_id, decision, reviewer_note, reviewed_by)
               values (%s, %s, 'accepted', 'matches the circular', %s)""",
            (workspace_id, finding_id, reviewer),
        )
        conn.execute(SIGN_OFF, (workspace_id, revision_id, reviewer, reviewer))


def test_only_reviewers_sign_off_and_only_as_themselves(conn, workspace_id):
    analyst = make_user(conn, workspace_id, "analyst")
    reviewer = make_user(conn, workspace_id, "reviewer")
    revision_id, finding_id = make_report(conn, workspace_id, analyst)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, analyst)
        conn.execute(SIGN_OFF, (workspace_id, revision_id, analyst, analyst))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, reviewer)
        conn.execute(
            """insert into public.finding_reviews (workspace_id, finding_id, decision, reviewed_by)
               values (%s, %s, 'accepted', %s)""",
            (workspace_id, finding_id, analyst),
        )
