"""Actual worker path with private broker, real Postgres and scripted providers only."""
import os
import tempfile
from pathlib import Path
from dataclasses import replace
from decimal import Decimal as D
from datetime import date
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb
from mira.db import connect,acting_as
from mira.contracts import Brief
from mira.budget import RunBudget
from mira.research_settings import ResearchSettings
from mira.pg_store import create_run,load_run
from mira.pricing import PriceBook,TokenRate
from mira.credential_broker import CredentialBroker,RunOwner,serve_broker
from mira.credentials import BrokerClient
from mira.llm import ROLE_MODEL_ENV,ScriptedClient
from mira import runner
from test_worker_db import make_user,as_app_user
from test_pipeline_db import planner_for,scout,analyst,writer,FakeWeb
from mira.seed import seed

DSN=os.environ.get('MIRA_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not DSN,reason='MIRA_TEST_DATABASE_URL not set')

def test_broker_worker_approval_continuation_preserves_allowance_and_generates_report(monkeypatch,tmp_path):
    models={role:'openai:gpt-5.4' for role in ROLE_MODEL_ENV}
    for role,var in ROLE_MODEL_ENV.items():monkeypatch.setenv(var,models[role])
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS','1')
    for name in ('MIRA_ENABLE_EXA_DISCOVERY','MIRA_ENABLE_LIVE_BROWSER','MIRA_ENABLE_OFFLINE_BROWSER','MIRA_ENABLE_HYBRID_RETRIEVAL'):
        monkeypatch.delenv(name,raising=False)
    book=PriceBook({'openai:gpt-5.4':TokenRate('openai','gpt-5.4',D('1'),D('2'))},None,None,'fixture',('https://example.test/prices',))
    monkeypatch.setattr(runner,'load_price_book',lambda *a,**k:book)
    clients=[]
    class FakeProvider:
        def __init__(self,*,models,api_keys):
            assert api_keys=={'openai':'only-request-key'}
            self.closed=False;self.calls=[]
            self.script=ScriptedClient({'planner':[planner_for('HK')], 'regulatory_scout':[scout,scout],
                'industry_scout':[scout,scout], 'analyst':[analyst]*8,
                'verifier':[{'verdict':'supported','reason':'stated in passage'},
                    {'introduces_new_fact':False,'new_facts':[],'is_supported_assessment':True,'reason':'grounded'}]*8,
                'writer':[writer]})
            clients.append(self)
        def structured_bounded(self,**kwargs):
            kwargs.pop('timeout_seconds');kwargs.pop('max_output_tokens')
            with connect(DSN) as journal_check:
                usage=journal_check.execute("select retrieval_settings->'monetary_usage' usage from public.analysis_runs where id=%s",
                    (ctx.analysis_run_id,)).fetchone()['usage']
                assert usage['pending_tokens']>0 and D(usage['pending_usd'])>0
            self.calls.append(kwargs['role'])
            return replace(self.script.structured(**kwargs),model='gpt-5.4')
        def close(self):self.closed=True
    monkeypatch.setattr(runner,'ProviderClient',FakeProvider)
    from mira.fetch import Fetcher
    monkeypatch.setattr(runner,'Fetcher',lambda allow:Fetcher(allow,transport=FakeWeb(),resolver=lambda h:['93.184.216.34'],sleep=lambda s:None))
    from mira.agents.scout import WebScout
    monkeypatch.setattr(runner,'WebScout',lambda *a,**k:WebScout(*a,max_rounds=1,**k))
    # The source/verification workflow remains real; no optional second-source call is
    # required to check budget continuation and report generation in this fixture.
    original_build=runner.build_orchestrator
    def build(*a,**kw):
        result=original_build(*a,**kw);result.store.reports_dir=tmp_path;result.corroborator=None
        return result
    monkeypatch.setattr(runner,'build_orchestrator',build)
    with connect(DSN) as conn:
        workspace=conn.execute("insert into public.workspaces(slug,name) values(%s,'Console E2E') returning id",('console-'+uuid4().hex,)).fetchone()['id']
        user=make_user(conn,workspace,'admin');seed(conn,workspace)
        hkma=conn.execute("select id from public.sources where workspace_id=%s and source_key='hkma'",(workspace,)).fetchone()['id']
        brief=Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,10,26),period_end=date(2026,10,26),
                    as_of_date=date(2026,10,26),plan_requires_approval=True)
        ctx=create_run(conn,workspace,user,brief,RunBudget(max_cost_usd='10',max_llm_tokens=2000000,max_gap_rounds=0),models,
            settings=ResearchSettings(source_ids=(str(hkma),),credential_mode='byok',max_analysis_batches=2))
        broker=CredentialBroker(lambda token,w,r:RunOwner(str(user),str(workspace),str(ctx.analysis_run_id),'queued'))
        # Short path is required on macOS; serve_broker creates a private /tmp directory.
        with tempfile.TemporaryDirectory(prefix='mb-',dir='/tmp') as service_dir,serve_broker(broker,Path(service_dir)/'private') as paths:
            monkeypatch.setenv('MIRA_BROKER_WORKER_SOCKET',str(paths.worker_socket))
            monkeypatch.setenv('MIRA_BROKER_CAPABILITY_PATH',str(paths.capability_path))
            def attach():
                handle=BrokerClient(str(paths.client_socket)).put('fixture-access',str(workspace),str(ctx.analysis_run_id),{'openai':'only-request-key'})
                with conn.transaction():
                    as_app_user(conn,user)
                    conn.execute('select public.bind_run_credentials(%s,%s)',(ctx.analysis_run_id,handle))
            attach()
            first=runner.execute_run(conn,DSN,ctx.analysis_run_id)
            assert first.status=='awaiting_approval'
            saved=load_run(conn,ctx.analysis_run_id)
            assert saved.research_settings.credential_handle is None
            before=D(saved.resource_usage['known_estimated_usd'])
            assert before>0 and clients[0].calls==['planner'] and clients[0].closed
            with acting_as(conn,user):
                conn.execute('update public.research_plans set approved_by=%s,approved_at=now() where analysis_run_id=%s',(user,ctx.analysis_run_id))
            attach()
            result=runner.execute_run(conn,DSN,ctx.analysis_run_id)
        assert result.report_id is not None
        saved=load_run(conn,ctx.analysis_run_id)
        assert D(saved.resource_usage['known_estimated_usd'])>before
        assert saved.resource_usage['pending_usd']=='0.000000'
        assert saved.research_settings.credential_handle is None and all(c.closed for c in clients)
        assert 'planner' not in clients[1].calls
        assert len([c for c in saved.resource_usage['calls'] if c['role']=='planner'])==1
        assert 'only-request-key' not in str(conn.execute('select * from public.analysis_runs where id=%s',(ctx.analysis_run_id,)).fetchone())
        assert saved.resource_usage['elapsed_seconds']>=saved.resource_usage['calls'][0]['elapsed_seconds']
        snapshot=conn.execute('select evidence_snapshot from public.reports where id=%s',(result.report_id,)).fetchone()['evidence_snapshot']
        assert 'Cost allowance' in str(snapshot) and 'Keyword' in str(snapshot)
        assert 'representations selected for analysis' in str(snapshot) and 'http_fetch' in str(snapshot)


from test_byok_resources_db import setup

def test_expired_keys_wait_for_reentry_without_operator_fallback(setup,monkeypatch):
    conn,ctx=setup
    monkeypatch.setenv('OPENAI_API_KEY','operator-must-not-be-used')
    monkeypatch.setenv('MIRA_BROKER_WORKER_SOCKET','/tmp/no-such-credential-service.sock')
    monkeypatch.setenv('MIRA_BROKER_CAPABILITY_PATH','/tmp/no-such-capability')
    called=[]
    monkeypatch.setattr(runner,'ProviderClient',lambda *a,**kw:called.append(kw))
    monkeypatch.setattr(runner,'load_price_book',lambda *a,**kw:called.append(kw))
    result=runner.execute_run(conn,DSN,ctx.analysis_run_id)
    assert result.status=='awaiting_credentials' and called==[]
    assert conn.execute('select status from public.analysis_runs where id=%s',(ctx.analysis_run_id,)).fetchone()['status']=='queued'
    assert load_run(conn,ctx.analysis_run_id).research_settings.credential_handle is None

def test_cancelled_run_does_not_reenter_running_state(setup):
    conn,ctx=setup
    conn.execute("update public.analysis_runs set status='cancelled' where id=%s",(ctx.analysis_run_id,))
    outcome=runner.execute_run(conn,DSN,ctx.analysis_run_id)
    assert outcome.status=='cancelled'
    assert conn.execute('select status from public.analysis_runs where id=%s',(ctx.analysis_run_id,)).fetchone()['status']=='cancelled'


def test_stale_worker_cannot_clear_replaced_handle(setup):
    from test_byok_resources_db import bind
    conn,ctx=setup
    bind(conn,ctx,'a'*40)
    old=load_run(conn,ctx.analysis_run_id)
    bind(conn,ctx,'b'*40)
    runner._clear_credential_handle(conn,old)
    assert load_run(conn,ctx.analysis_run_id).research_settings.credential_handle=='b'*40

def test_busy_worker_does_not_consume_or_clear_lease(setup):
    from test_byok_resources_db import bind
    conn,ctx=setup
    bind(conn,ctx)
    with connect(DSN) as other:
        other.execute("select pg_advisory_lock(hashtextextended(%s,0))",(str(ctx.analysis_run_id),))
        result=runner.execute_run(conn,DSN,ctx.analysis_run_id)
        assert result.status=='busy'
        assert load_run(conn,ctx.analysis_run_id).research_settings.credential_handle=='a'*40
        other.execute("select pg_advisory_unlock(hashtextextended(%s,0))",(str(ctx.analysis_run_id),))

def test_stale_invocation_cannot_overwrite_journal(setup):
    conn,ctx=setup
    conn.execute("""update public.analysis_runs set retrieval_settings=jsonb_set(
        jsonb_set(retrieval_settings,'{worker_invocation}','\"new\"'),
        '{monetary_usage}','{\"known_estimated_usd\":\"2\"}') where id=%s""",(ctx.analysis_run_id,))
    with pytest.raises(ValueError,match='journal unavailable'):
        runner._journal_usage(DSN,ctx,{'spending':{},'calls':[],'pending_tokens':0},'old')
    assert load_run(conn,ctx.analysis_run_id).resource_usage['known_estimated_usd']=='2'

def test_expired_key_cleanup_preserves_lease_attached_during_broker_call(setup,monkeypatch):
    from test_byok_resources_db import bind
    from mira.credentials import CredentialError
    import mira.credential_worker
    conn,ctx=setup
    bind(conn,ctx,'a'*40)
    def expire(*args,**kwargs):
        bind(conn,ctx,'b'*40)
        raise CredentialError('expired')
    monkeypatch.setattr(mira.credential_worker,'claim_keys',expire)
    assert runner.execute_run(conn,DSN,ctx.analysis_run_id).status=='awaiting_credentials'
    assert load_run(conn,ctx.analysis_run_id).research_settings.credential_handle=='b'*40

def test_invocation_audit_records_run_actor(setup,monkeypatch):
    import mira.credential_worker
    from mira.credentials import CredentialError
    conn,ctx=setup
    def expire(*args,**kwargs):
        raise CredentialError('expired')
    monkeypatch.setattr(mira.credential_worker,'claim_keys',expire)
    runner.execute_run(conn,DSN,ctx.analysis_run_id)
    events=conn.execute("""select actor_id from public.audit_events where entity_type='analysis_runs'
        and entity_id=%s and action='update' and details->'changed_fields' ? 'retrieval_settings'
        order by created_at,id""",(ctx.analysis_run_id,)).fetchall()
    assert events and all(event['actor_id']==ctx.user_id for event in events)

def test_failed_preflight_records_completion_time(setup,monkeypatch):
    import mira.credential_worker
    conn,ctx=setup
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS','1')
    monkeypatch.setattr(mira.credential_worker,'claim_keys',lambda *a,**k:{'openai':'fixture'})
    monkeypatch.setattr(runner,'models_from_env',lambda:{'planner':'openai:different-profile'})
    assert runner.execute_run(conn,DSN,ctx.analysis_run_id).status=='failed'
    row=conn.execute('select status,finished_at from public.analysis_runs where id=%s',(ctx.analysis_run_id,)).fetchone()
    assert row['status']=='failed' and row['finished_at'] is not None
