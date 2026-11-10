"""Per-request queue binding and worker-owned allowance journal on local PostgreSQL."""
import os
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from psycopg.types.json import Jsonb

from mira.budget import RunBudget
from mira.contracts import Brief
from mira.db import acting_as, connect
from mira.pg_store import claim_next_run, create_run, load_run
from mira.research_settings import ResearchSettings
from test_worker_db import make_user, as_app_user
import uuid

DSN=os.environ.get('MIRA_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not DSN,reason='MIRA_TEST_DATABASE_URL not set')

@pytest.fixture
def setup():
    with connect(DSN) as conn:
        workspace=conn.execute("insert into public.workspaces(slug,name) values(%s,'BYOK tests') returning id",
                               ('byok-'+uuid.uuid4().hex,)).fetchone()['id']
        user=make_user(conn,workspace,'analyst')
        brief=Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,1,1),
                    period_end=date(2026,1,1),as_of_date=date(2026,1,1),plan_requires_approval=False)
        ctx=create_run(conn,workspace,user,brief,RunBudget(max_cost_usd='5'),{'planner':'openai:gpt-5.4'},
                       settings=ResearchSettings(credential_mode='byok',max_analysis_batches=3))
        try:yield conn,ctx
        finally:
            conn.execute("update public.analysis_runs set status='cancelled' where workspace_id=%s",(workspace,))

def bind(conn,ctx,handle='a'*40):
    with conn.transaction():
        as_app_user(conn,ctx.user_id)
        conn.execute('select public.bind_run_credentials(%s,%s)',(ctx.analysis_run_id,handle))

def test_roundtrip_settings_and_pending_keys_gate_claim(setup):
    conn,ctx=setup
    loaded=load_run(conn,ctx.analysis_run_id)
    assert loaded.research_settings.max_analysis_batches==3
    assert loaded.budget.max_cost_usd=='5'
    assert loaded.model_settings=={'planner':'openai:gpt-5.4'}
    assert claim_next_run(conn,ctx.workspace_id) is None
    bind(conn,ctx)
    assert claim_next_run(conn,ctx.workspace_id)==ctx.analysis_run_id
    assert claim_next_run(conn,ctx.workspace_id) is None

def test_bind_replaces_revoked_lease_and_preserves_usage(setup):
    conn,ctx=setup
    usage={'known_estimated_usd':'1.23','unknown_reserved_usd':'.5','elapsed_seconds':12}
    with acting_as(conn,ctx.user_id):
        conn.execute("update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,'{monetary_usage}',%s) where id=%s",
                     (Jsonb(usage),ctx.analysis_run_id))
    bind(conn,ctx)
    bind(conn,ctx,'b'*40)
    loaded=load_run(conn,ctx.analysis_run_id)
    assert loaded.research_settings.credential_handle=='b'*40
    assert loaded.resource_usage==usage

@pytest.mark.parametrize('change',['journal','budget','models','research'])
def test_client_cannot_refund_or_change_started_allowance(setup,change):
    conn,ctx=setup
    with acting_as(conn,ctx.user_id):
        conn.execute("update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,'{monetary_usage}',%s) where id=%s",
                     (Jsonb({'known_estimated_usd':'1'}),ctx.analysis_run_id))
    statement={
        'journal':"retrieval_settings=retrieval_settings-'monetary_usage'",
        'budget':"source_limits='{}'::jsonb",
        'models':"model_settings='{}'::jsonb",
        'research':"retrieval_settings=jsonb_set(retrieval_settings,'{research,max_analysis_batches}','64')"}[change]
    with pytest.raises(psycopg.errors.InsufficientPrivilege),conn.transaction():
        as_app_user(conn,ctx.user_id)
        conn.execute(f'update public.analysis_runs set {statement} where id=%s',(ctx.analysis_run_id,))

def test_client_cannot_forge_first_journal(setup):
    conn,ctx=setup
    with pytest.raises(psycopg.errors.InsufficientPrivilege),conn.transaction():
        as_app_user(conn,ctx.user_id)
        conn.execute("update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,'{monetary_usage}',%s) where id=%s",
                     (Jsonb({'known_estimated_usd':'0'}),ctx.analysis_run_id))

@pytest.mark.parametrize('condition',['other_admin','running','operator','bad_handle'])
def test_lease_bind_refuses_wrong_owner_status_mode_or_handle(setup,condition):
    conn,ctx=setup
    user=ctx.user_id
    handle='a'*40
    if condition=='other_admin':user=make_user(conn,ctx.workspace_id,'admin')
    if condition=='running':conn.execute("update public.analysis_runs set status='running' where id=%s",(ctx.analysis_run_id,))
    if condition=='operator':conn.execute("update public.analysis_runs set retrieval_settings='{}'::jsonb where id=%s",(ctx.analysis_run_id,))
    if condition=='bad_handle':handle='secret\nvalue'
    with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.InvalidParameterValue)),conn.transaction():
        as_app_user(conn,user)
        conn.execute('select public.bind_run_credentials(%s,%s)',(ctx.analysis_run_id,handle))

def test_operator_cli_cannot_silently_rerun_byok_with_ambient_keys(setup):
    from mira.pg_store import create_rerun
    conn,ctx=setup
    conn.execute("update public.analysis_runs set status='draft' where id=%s",(ctx.analysis_run_id,))
    with pytest.raises(ValueError,match='fresh'):
        create_rerun(conn,ctx.workspace_id,ctx.user_id,ctx.analysis_run_id,dict(ctx.model_settings))
