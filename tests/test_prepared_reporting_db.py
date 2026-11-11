"""Actual snapshot/request/export integration; no provider calls on report path."""
import os
from uuid import UUID,uuid4
import pytest
from test_preparation_store_db import conn,workspace,prepared
from mira.prepared_reporting import build_prepared_payload,execute_prepared_request
from mira.pg_store import claim_next_run,create_run
from mira.db import acting_as
from mira.contracts import Brief
from mira.budget import RunBudget
from datetime import date

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local DB required')


def test_ready_snapshot_report_preserves_checks_and_pending_export(conn,prepared):
    store,job,_=prepared
    payload=build_prepared_payload(conn,job['analysis_run_id'],job['source_ids'])
    snapshot=store.publish_job(job,payload)
    request=store.request_report(job['workspace_id'],job['actor_id'],job['brief'],job['source_ids'],'fresh')
    class NoProvider:
        def structured(self,**kwargs):raise AssertionError('prepared report must not call a model')
    result=execute_prepared_request(conn,'unused',request['id'],NoProvider())
    assert result['status']=='ready',result
    report=conn.execute('select * from public.prepared_reports where id=%s',(result['report_id'],)).fetchone()
    assert report['review_state']=='human_review_pending'
    assert 'human evidence review pending' in report['html'].lower()
    assert 'Pending human review' in report['html'] or 'Pending' in report['html']
    assert '{{PREPARED_' not in report['html']
    assert len(report['capture']['selected_findings'])==2
    assert report['capture']['snapshots'][str(snapshot['id'])]['verifications']==snapshot['payload']['verifications']
    assert report['capture']['report_snapshot']['coverage']


def test_legacy_worker_cannot_claim_scheduled_preparation_run(conn,workspace):
    ws,user=workspace
    brief=Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,1,1),
        period_end=date(2026,1,1),as_of_date=date(2026,1,1),plan_requires_approval=False)
    ctx=create_run(conn,ws,user,brief,RunBudget(),{})
    with acting_as(conn,user):
        conn.execute("update public.analysis_runs set retrieval_settings=retrieval_settings||'{\"execution_mode\":\"preparation\"}'::jsonb where id=%s",(ctx.analysis_run_id,))
    assert claim_next_run(conn,ws) is None


def test_analysis_reuse_leaves_deferred_passages_for_catchup_and_reopens_corrections(conn,prepared):
    from mira.pg_store import PostgresStore,load_run
    from mira.store import passage_event
    from mira.orchestrator import Orchestrator,_Run
    from test_orchestrator import FakeVerifier
    store,job,payload=prepared;ctx=load_run(conn,job['analysis_run_id']);pg=PostgresStore(conn)
    versions={UUID(p['document_version_id']):job['source_ids'] for p in payload['evidence_input']['passages'].values()}
    with acting_as(conn,ctx.user_id):
        conn.execute("update public.analysis_runs set status='running' where id=%s",(ctx.analysis_run_id,))
    pg.begin_analysis_coverage(ctx,job['source_ids'])
    passages=pg.load_analysis_candidates(ctx,versions)
    first=next(p for p in passages if p.id in {UUID(x) for x in payload['evidence_input']['passages']})
    run=_Run(Orchestrator(pg,object(),{},FakeVerifier()),ctx)
    step=run._start('analyst')
    pg.append_analysis_events(ctx,[passage_event(first,'attempted','B1',step.id),passage_event(first,'analysed','B1',step.id)])
    pg.append_analysis_events(ctx,[passage_event(p,'deferred',reason='time_budget') for p in passages if p.id!=first.id])
    run._finish(step,'succeeded');pg.set_run_status(ctx,'partial','Synthetic fixture deferred work')
    frozen=store.publish_job(job,build_prepared_payload(conn,ctx.analysis_run_id,job['source_ids']))
    assert pg.previously_prepared_passages(ctx)=={first.id}
    fid=next(fid for fid,f in frozen['payload']['evidence_input']['findings'].items() if not f['is_inference'])
    with acting_as(conn,ctx.user_id):
        conn.execute("select public.review_prepared_fact(%s,%s,'correction_requested','Reanalyse this evidence')",(frozen['id'],fid))
    assert first.id not in pg.previously_prepared_passages(ctx)


def test_report_worker_does_not_wait_for_or_claim_unrelated_preparation(conn,prepared):
    import subprocess,sys
    from test_preparation_store_db import DSN
    store,job,payload=prepared
    store.publish_job(job,payload)
    request=store.request_report(job['workspace_id'],job['actor_id'],job['brief'],job['source_ids'],'already-pinned')
    later=store.enqueue_job(job['workspace_id'],job['actor_id'],job['source_ids'],job['brief'],{}, {},{},'later-refresh')
    slug=conn.execute('select slug from public.workspaces where id=%s',(job['workspace_id'],)).fetchone()['slug']
    run=subprocess.run([sys.executable,'-m','mira','prepared-report-worker','--once'],capture_output=True,text=True,
        timeout=10,env={'PATH':os.environ['PATH'],'PYTHONPATH':'.','MIRA_WORKER_DATABASE_URL':DSN,
            'MIRA_WORKSPACE_SLUG':slug,'MIRA_ENABLE_SCHEDULED_PREPARATION':'0'})
    assert run.returncode==0,run.stderr
    assert conn.execute('select status from public.prepared_report_requests where id=%s',(request['id'],)).fetchone()['status']=='ready'
    assert conn.execute('select status from public.preparation_jobs where id=%s',(later['id'],)).fetchone()['status']=='queued'
