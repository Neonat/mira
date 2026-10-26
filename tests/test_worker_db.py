"""Worker connection tests. Need a disposable database with all migrations applied:

    MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres pytest

Never point this at a shared database: it inserts test users and rows.
"""

import os
import uuid

import psycopg
import pytest

from mira.db import NotAuthorisedError, acting_as, connect, require_role

DSN = os.environ.get("MIRA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="MIRA_TEST_DATABASE_URL not set")


@pytest.fixture()
def conn():
    with connect(DSN) as connection:
        yield connection


@pytest.fixture()
def workspace_id(conn):
    return conn.execute("select id from public.workspaces where slug = 'mira'").fetchone()["id"]


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
             (workspace_id, project_id, revision_number, title, objective, risk_topics, markets, change_reason, created_by)
           values (%s, %s, 1, 'AML brief', 'test', array['AML/CFT'], array['SG','HK']::char(2)[], 'brief', %s)
           returning id""",
        (workspace_id, project_id, user_id),
    ).fetchone()["id"]
    return conn.execute(
        """insert into public.analysis_runs
             (workspace_id, project_revision_id, idempotency_key, query_mode, as_of_date, created_by)
           values (%s, %s, %s, 'current', current_date, %s) returning id""",
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
            """insert into public.sources (workspace_id, source_key, name, source_type, base_url, permitted_operations, created_by)
               values (%s, %s, 'MAS', 'regulator', 'https://www.mas.gov.sg', array['metadata','fetch'], %s) returning id""",
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
        """insert into public.sources (workspace_id, source_key, name, source_type)
           values (%s, %s, 'MAS', 'regulator') returning id""",
        (workspace_id, f"mas-{uuid.uuid4()}"),
    ).fetchone()["id"]
    insert = """insert into public.expected_sources
                  (workspace_id, list_version, topic, jurisdiction_code, category, source_id, document_hint)
                values (%s, 1, 'AML/CFT', 'SG', 'rule', %s, %s)"""
    with conn.transaction():
        as_app_user(conn, curator)
        conn.execute(insert, (workspace_id, source_id, f"Notice 626 {uuid.uuid4()}"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        as_app_user(conn, analyst)
        conn.execute(insert, (workspace_id, source_id, f"Notice 626 {uuid.uuid4()}"))
