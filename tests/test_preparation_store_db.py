"""Real PostgreSQL checks for prepared evidence; no providers."""
from uuid import UUID, uuid4
import pytest
from test_pipeline_db import DSN, conn, workspace

pytestmark = pytest.mark.skipif(not DSN, reason='MIRA_TEST_DATABASE_URL not set')

def test_storage_schema_installed(conn):
    assert conn.execute("select to_regclass('public.prepared_snapshots') as name").fetchone()['name']

def test_overlap_serializes_and_expired_owner_is_fenced(conn, workspace):
    from mira.preparation_store import PreparationStore
    ws, actor = workspace
    sources = [r['id'] for r in conn.execute("select id from public.sources where workspace_id=%s and is_active and jurisdiction_code='HK' and permitted_operations @> array['fetch','store_text']::text[] order by id", (ws,))][:2]
    store = PreparationStore(conn)
    first = store.enqueue_job(ws, actor, sources, {}, {}, {}, {}, 'first')
    second = store.enqueue_job(ws, actor, sources[:1], {}, {}, {}, {}, 'second')
    job = store.claim_job(ws, uuid4())
    assert job['id'] == first['id']
    assert store.claim_job(ws, uuid4()) is None
    conn.execute("update public.preparation_jobs set lease_until=clock_timestamp()-interval '1 second' where id=%s", (job['id'],))
    recovered = store.claim_job(ws, uuid4())
    assert recovered['id'] == job['id'] and recovered['generation'] > job['generation']
    with pytest.raises(Exception, match='lease'):
        store.heartbeat_job(job, 'analysis')
    store.fail_job(recovered, 'fixture stop')
    assert store.claim_job(ws, uuid4())['id'] == second['id']

@pytest.fixture
def prepared(conn, workspace, tmp_path):
    return prepare_run(conn,workspace,tmp_path)


def prepare_run(conn, workspace, tmp_path, key="prepared"):
    from test_pipeline_db import run_hk, analyst
    from mira.preparation_store import PreparationStore
    ctx,outcome=run_hk(conn,workspace,tmp_path,analyst)
    assert outcome.status=='draft'
    roots=[r['finding_id'] for r in conn.execute("select distinct finding_id from public.claim_checks where analysis_run_id=%s and verdict='supported'",(ctx.analysis_run_id,))]
    evidence=conn.execute('select private.capture_evidence_input(%s,%s,%s,%s::uuid[]) as v',(ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,roots)).fetchone()['v']
    sources=sorted({p['source_id'] for p in evidence['passages'].values()})
    checks={}
    for fid in evidence['findings']:
        c=conn.execute('select * from public.claim_checks where finding_id=%s order by checked_at desc,attempt desc,id desc limit 1',(fid,)).fetchone()
        checks[fid]={'check_id':str(c['id']),'input_fingerprint':c['input_fingerprint'],'input_snapshot':c['input_snapshot']}
    store=PreparationStore(conn)
    j=store.enqueue_job(ctx.workspace_id,ctx.user_id,sources,ctx.brief,{}, {},{},key)
    j=store.claim_job(ctx.workspace_id,uuid4()); j=store.set_job_run(j,ctx.analysis_run_id)
    payload={'schema_version':1,'brief':ctx.brief.model_dump(mode='json'),'source_ids':sources,'evidence_input':evidence,'verifications':checks,'coverage':[],'analysis_coverage':None,'reasons':[]}
    return store,j,payload


def test_atomic_pins_do_not_follow_next_cycle_and_failed_refresh_requires_choice(conn,prepared):
    store,j,p=prepared
    first=store.publish_job(j,p)
    assert store.publish_job(j,p)['id']==first['id']
    nextjob=store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{}, {},{},'refresh')
    request=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'during')
    assert request['status']=='waiting'
    nextjob=store.claim_job(j['workspace_id'],uuid4())
    store.fail_job(nextjob,'fixture failed')
    assert store.resolve_request(request['id'])['status']=='evidence_failed'
    later=store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{}, {},{},'later')
    from mira.db import acting_as
    with acting_as(conn,j['actor_id']):
        for sid in j['source_ids']:
            conn.execute('select public.choose_prepared_previous(%s,%s)',(request['id'],sid))
    assert store.resolve_request(request['id'])['status']=='queued'
    assert [s['id'] for s in store.load_request_snapshots(request['id'])]==[first['id']]
    assert conn.execute('select active_job_id from public.preparation_scopes where id=%s',(j['source_ids'][0],)).fetchone()['active_job_id']==later['id']


def test_pending_report_remains_pending_later_rejection_alert_and_immutable(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'report')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    report=store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'<h1>{{PREPARED_REVIEW_WARNING}}</h1>',bindings)
    assert report['review_state']=='human_review_pending'
    assert 'review pending' in report['html']
    fid=bindings[0]['finding_id']
    with acting_as(conn,j['actor_id']):
        conn.execute("select public.review_prepared_fact(%s,%s,'rejected','fixture')",(snap['id'],fid))
    assert conn.execute('select count(*) as n from public.prepared_report_alerts where report_id=%s',(report['id'],)).fetchone()['n']==1
    with pytest.raises(Exception,match='immutable'):
        conn.execute("update public.prepared_reports set html='changed' where id=%s",(report['id'],))
    with acting_as(conn,j['actor_id']):
        for b in bindings: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','fixture')",(snap['id'],b['finding_id']))
    with pytest.raises(Exception,match='pending historical'):
        with acting_as(conn,j['actor_id']): conn.execute("select public.approve_prepared_report(%s,'fixture')",(report['id'],))


def test_rejection_during_composition_prevents_publish(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'report')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with acting_as(conn,j['actor_id']): conn.execute("select public.review_prepared_fact(%s,%s,'correction_requested','fixture')",(snap['id'],bindings[0]['finding_id']))
    with pytest.raises(ValueError,match='rejected or correction'):
        store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
    assert not conn.execute('select 1 from public.prepared_reports where request_id=%s',(req['id'],)).fetchone()


def test_forged_verification_is_refused(conn,prepared):
    store,j,p=prepared
    next(iter(p['verifications'].values()))['check_id']=str(uuid4())
    with pytest.raises(ValueError,match='verification provenance'):
        store.publish_job(j,p)
    assert not conn.execute('select 1 from public.prepared_snapshots where job_id=%s',(j['id'],)).fetchone()


def test_report_capture_cannot_change_frozen_facts(conn,prepared):
    store,j,p=prepared; snap=store.publish_job(j,p)
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'forged')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with pytest.raises(ValueError,match='capture'):
        store.publish_report(req,{'bindings':bindings,'selected_findings':{}},'{{PREPARED_REVIEW_WARNING}}',bindings)


def test_approval_refuses_newer_failed_machine_check(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with acting_as(conn,j['actor_id']):
        for b in bindings: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','fixture')",(snap['id'],b['finding_id']))
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'checked')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    report=store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
    fid=bindings[0]['finding_id']
    with acting_as(conn,j['actor_id']):
        conn.execute("insert into public.claim_checks(workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,checked_at) values(%s,%s,%s,99,'llm','unsupported','new failure','fixture',clock_timestamp())",(j['workspace_id'],j['analysis_run_id'],fid))
    with pytest.raises(Exception,match='machine support'):
        with acting_as(conn,j['actor_id']): conn.execute("select public.approve_prepared_report(%s,'fixture')",(report['id'],))


def test_review_racing_publication_produces_alert_without_rewriting(conn,prepared):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from mira.db import connect,acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'race')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    fid=sorted(p['evidence_input']['findings'])[0]
    started=threading.Event(); state={}
    def review():
        with connect(DSN) as other:
            state['pid']=other.info.backend_pid
            with acting_as(other,j['actor_id']):
                started.set()
                other.execute("select public.review_prepared_fact(%s,%s,'rejected','race')",(snap['id'],fid))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with acting_as(conn,j['actor_id']):
            conn.execute('select 1 from public.prepared_facts where snapshot_id=%s order by finding_id for update',(snap['id'],)).fetchall()
            future=pool.submit(review); assert started.wait(2)
            # Observe PostgreSQL's actual lock wait before committing the report.
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                with connect(DSN) as monitor:
                    waiting=monitor.execute("select wait_event_type from pg_stat_activity where pid=%s",(state['pid'],)).fetchone()
                if waiting and waiting['wait_event_type']=='Lock': break
                time.sleep(.01)
            else: pytest.fail('review never reached row lock')
            report=store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
        future.result(timeout=3)
    row=conn.execute('select * from public.prepared_reports where id=%s',(report['id'],)).fetchone()
    assert row['html']==report['html'] and row['review_state']=='human_review_pending'
    assert conn.execute('select count(*) as n from public.prepared_report_alerts where report_id=%s',(report['id'],)).fetchone()['n']==1


def test_authenticated_rpc_roles_and_workspace_isolation(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    outsider=uuid4()
    conn.execute('insert into auth.users(id,email) values(%s,%s)',(outsider,f'{outsider}@test.local'))
    with acting_as(conn,outsider):
        conn.execute('set local role authenticated')
        assert not conn.execute('select * from public.prepared_snapshots where id=%s',(snap['id'],)).fetchone()
    with pytest.raises(Exception,match='reviewer role'):
        with acting_as(conn,outsider):
            conn.execute('set local role authenticated')
            conn.execute("select public.review_prepared_fact(%s,%s,'accepted','forged')",(snap['id'],next(iter(p['evidence_input']['findings']))))
    with pytest.raises(Exception,match='permission denied'):
        with acting_as(conn,j['actor_id']):
            conn.execute('set local role authenticated')
            conn.execute("update public.preparation_jobs set generation=99 where id=%s",(j['id'],))


def test_checked_report_approval_and_dependency_exclusion(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with acting_as(conn,j['actor_id']):
        for b in bindings: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','fixture')",(snap['id'],b['finding_id']))
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'approved')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    inference=next((fid for fid,f in p['evidence_input']['findings'].items() if f['depends_on']),None)
    assert inference
    with pytest.raises(ValueError,match='dependency'):
        store.publish_report(req,{'bindings':[{'snapshot_id':snap['id'],'finding_id':inference}],'selected_findings':{inference:p['evidence_input']['findings'][inference]}},'{{PREPARED_REVIEW_WARNING}}',[{'snapshot_id':snap['id'],'finding_id':inference}])
    report=store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
    assert report['review_state']=='human_checked'
    with acting_as(conn,j['actor_id']):
        approval=conn.execute("select public.approve_prepared_report(%s,'approved') as id",(report['id'],)).fetchone()['id']
    assert approval


def test_multi_scope_manifest_is_atomic_with_registration(conn,prepared):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from mira.db import connect
    from mira.preparation_store import PreparationStore
    store,j,p=prepared
    # Publish one snapshot across two source scopes, even where one has no facts.
    extra=conn.execute("select id from public.sources where workspace_id=%s and is_active and permitted_operations @> array['fetch','store_text']::text[] and jurisdiction_code='HK' and not(id=any(%s)) limit 1",(j['workspace_id'],j['source_ids'])).fetchone()['id']
    # The original job finishes its original exact scope first.
    first=store.publish_job(j,p)
    both=j['source_ids']+[extra]
    extra_job=store.enqueue_job(j['workspace_id'],j['actor_id'],[extra],j['brief'],{},{},{},'extra')
    ej=store.claim_job(j['workspace_id'],uuid4()); store.fail_job(ej,'no initial extra evidence')
    barrier=threading.Barrier(2)
    def enqueue():
        with connect(DSN) as c:
            barrier.wait()
            return PreparationStore(c).enqueue_job(j['workspace_id'],j['actor_id'],both,j['brief'],{},{},{},'both')
    def request():
        with connect(DSN) as c:
            barrier.wait()
            return PreparationStore(c).request_report(j['workspace_id'],j['actor_id'],j['brief'],both,'both-request')
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(enqueue); b=pool.submit(request); newjob=a.result(timeout=5); req=b.result(timeout=5)
    entries=conn.execute('select * from public.prepared_report_request_scopes where request_id=%s',(req['id'],)).fetchall()
    assert len(entries)==len(both)
    # Either registration wins for every overlapping scope, or the request pins
    # pre-registration state for every scope. A mixed observation is impossible.
    observed={e['scope_id']:e['job_id'] for e in entries}
    before={sid:(extra_job['id'] if sid==extra else None) for sid in both}
    assert observed=={sid:newjob['id'] for sid in both} or observed==before
    assert len(store.load_request_snapshots(req['id'])) in (0,1)


def test_stale_publication_and_cancel_do_not_affect_shared_job(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'cancel')
    with acting_as(conn,j['actor_id']): conn.execute('select public.cancel_prepared_report_request(%s)',(req['id'],))
    conn.execute("update public.preparation_jobs set lease_until=clock_timestamp()-interval '1 second' where id=%s",(j['id'],))
    recovered=store.claim_job(j['workspace_id'],uuid4())
    with pytest.raises(ValueError,match='lease'):
        store.publish_job(j,p)
    snap=store.publish_job(recovered,p)
    assert snap['generation']==recovered['generation']
    assert store.resolve_request(req['id'])['status']=='cancelled'


def test_full_check_metadata_is_canonical_and_not_caller_invented(conn,prepared):
    from mira.contracts import FrozenVerification
    store,j,p=prepared
    import copy
    forged=copy.deepcopy(p)
    next(iter(forged['verifications'].values()))['model']='invented-model'
    with pytest.raises(ValueError,match='verification metadata'):
        store.publish_job(j,forged)
    snap=store.publish_job(j,p)
    for v in snap['payload']['verifications'].values():
        FrozenVerification.model_validate({k:value for k,value in v.items() if k!='input_snapshot'})
    assert store.publish_job(j,p)['id']==snap['id']


def test_request_after_failed_refresh_requires_explicit_old_choice(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snapshot=store.publish_job(j,p)
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'later-failure')
    failed=store.claim_job(j['workspace_id'],uuid4()); store.fail_job(failed,'refresh failed')
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'after-failure')
    assert req['status']=='evidence_failed'
    assert not store.load_request_snapshots(req['id'])
    with acting_as(conn,j['actor_id']):
        for sid in j['source_ids']: conn.execute('select public.choose_prepared_previous(%s,%s)',(req['id'],sid))
    assert store.resolve_request(req['id'])['status']=='queued'
    assert store.load_request_snapshots(req['id'])[0]['id']==snapshot['id']


@pytest.mark.parametrize('revocation',['actor','source'])
def test_revoked_queued_job_does_not_starve_independent_job(conn,workspace,revocation):
    from mira.preparation_store import PreparationStore
    ws,actor=workspace; store=PreparationStore(conn)
    sources=[r['id'] for r in conn.execute("select id from public.sources where workspace_id=%s and is_active and jurisdiction_code='HK' and permitted_operations @> array['fetch','store_text']::text[] order by id limit 2",(ws,))]
    other=uuid4(); conn.execute('insert into auth.users(id,email) values(%s,%s)',(other,f'{other}@test.local'))
    conn.execute("insert into public.workspace_members(workspace_id,user_id,role) values(%s,%s,'analyst')",(ws,other))
    bad=store.enqueue_job(ws,other,sources[:1],{},{},{},{},'bad')
    good=store.enqueue_job(ws,actor,sources[1:],{},{},{},{},'good')
    if revocation=='actor': conn.execute('delete from public.workspace_members where workspace_id=%s and user_id=%s',(ws,other))
    else: conn.execute('update public.sources set is_active=false where id=%s',(sources[0],))
    claimed=store.claim_job(ws,uuid4())
    assert claimed['id']==good['id']
    failed=conn.execute('select * from public.preparation_jobs where id=%s',(bad['id'],)).fetchone()
    assert failed['status']=='failed' and failed['reason']
    assert conn.execute('select active_job_id from public.preparation_scopes where id=%s',(sources[0],)).fetchone()['active_job_id'] is None


def test_revoked_due_schedule_is_disabled_without_blocking_other_schedule(conn,workspace):
    from datetime import datetime,UTC,timedelta
    from mira.preparation_store import PreparationStore
    ws,actor=workspace; store=PreparationStore(conn)
    sources=[r['id'] for r in conn.execute("select id from public.sources where workspace_id=%s and is_active and jurisdiction_code='HK' and permitted_operations @> array['fetch','store_text']::text[] order by id limit 2",(ws,))]
    due=conn.execute("select clock_timestamp()-interval '1 minute' as due").fetchone()['due']
    brief={'topic':'AML/CFT','jurisdictions':['HK'],'period_start':'2025-01-01',
           'period_end':'2025-02-01','as_of_date':'2025-02-01','plan_requires_approval':False}
    ids=[store.configure_schedule(ws,actor,[sid],brief,{},{},{},60,due,enabled=True) for sid in sources]
    conn.execute('update public.sources set is_active=false where id=%s',(sources[0],))
    assert store.tick_schedules(ws)==1
    bad=conn.execute('select * from public.preparation_schedules where id=%s',(ids[0],)).fetchone()
    assert not bad['enabled'] and bad['error']
    assert conn.execute('select count(*) as n from public.preparation_jobs where workspace_id=%s',(ws,)).fetchone()['n']==1


def test_schedule_advances_cutoff_without_shifting_start_or_drifting_cadence(conn, workspace):
    from datetime import timedelta
    from mira.preparation_store import PreparationStore
    ws, actor = workspace
    store = PreparationStore(conn)
    source = conn.execute("""select id from public.sources where workspace_id=%s
        and jurisdiction_code='HK' and is_active
        and permitted_operations @> array['fetch','store_text']::text[]
        order by id limit 1""",(ws,)).fetchone()['id']
    now = conn.execute("select clock_timestamp() as now, (clock_timestamp() at time zone 'UTC')::date as today").fetchone()
    today = now['today']
    due = now['now'] - timedelta(days=4, minutes=1)
    brief = {'topic':'AML/CFT','jurisdictions':['HK'],
             'period_start':(today-timedelta(days=365)).isoformat(),
             'period_end':(today-timedelta(days=6)).isoformat(),
             'as_of_date':(today-timedelta(days=5)).isoformat(),'plan_requires_approval':False}
    schedule = store.configure_schedule(ws,actor,[source],brief,{},{},{},86400,due,enabled=True)
    assert store.tick_schedules(ws)==1
    saved = conn.execute("select brief from public.preparation_jobs where workspace_id=%s",(ws,)).fetchone()['brief']
    assert saved['as_of_date']==today.isoformat()
    assert saved['period_end']==(today-timedelta(days=1)).isoformat()
    assert saved['period_start']==brief['period_start']
    next_due = conn.execute("select next_due from public.preparation_schedules where id=%s",(schedule,)).fetchone()['next_due']
    assert next_due==due+timedelta(days=5)
    assert store.tick_schedules(ws)==0


def test_per_fact_review_html_captures_mixed_decisions_and_quotes(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with acting_as(conn,j['actor_id']): conn.execute("select public.review_prepared_fact(%s,%s,'accepted','checked')",(snap['id'],bindings[0]['finding_id']))
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'mixed-details')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    report=store.publish_report(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}{{PREPARED_FACT_REVIEWS}}',bindings)
    assert '{{PREPARED_FACT_REVIEWS}}' not in report['html']
    assert '<table' in report['html'] and 'Accepted' in report['html'] and 'Pending' in report['html']
    assert str(snap['id']) in report['html']
    for fact in p['evidence_input']['findings'].values():
        for citation in fact['evidence']:
            import html
            assert html.escape(citation['supporting_quote']) in report['html']


def test_successful_refresh_clears_prior_failure_for_new_requests(conn,prepared):
    store,j,p=prepared; store.publish_job(j,p)
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'failed-cycle')
    failed=store.claim_job(j['workspace_id'],uuid4()); store.fail_job(failed,'failed')
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'good-cycle')
    good=store.claim_job(j['workspace_id'],uuid4()); good=store.set_job_run(good,j['analysis_run_id'])
    snapshot=store.publish_job(good,p)
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'after-success')
    assert req['status']=='queued'
    assert store.load_request_snapshots(req['id'])[0]['id']==snapshot['id']


def test_per_fact_review_html_escapes_untrusted_citation_fields(prepared):
    from copy import deepcopy
    from mira.preparation_store import PreparationStore
    store,j,p=prepared
    evidence=deepcopy(p['evidence_input']); fid=next(fid for fid,f in evidence['findings'].items() if f['evidence'])
    fact=evidence['findings'][fid]; fact['title']='<script>title()</script>'
    citation=fact['evidence'][0]; citation['supporting_quote']='<img src=x onerror=alert(1)>'
    passage=evidence['passages'][citation['passage_id']]
    passage['source_url']='javascript:alert(1)'; passage['title']='<svg onload=alert(1)>'
    sid=uuid4()
    rendered=PreparationStore._fact_review_html([{'snapshot_id':str(sid),'finding_id':fid,'decision':None}],{sid:{'payload':{'evidence_input':evidence}}})
    assert '<script>' not in rendered and '<img' not in rendered and '<svg' not in rendered
    assert 'href="javascript:' not in rendered and '&lt;script&gt;' in rendered


@pytest.mark.parametrize('operation',['publish','approve'])
def test_quote_revoked_after_selection_blocks_report_not_preparation(conn,prepared,operation):
    from mira.db import acting_as
    store,j,p=prepared; snap=store.publish_job(j,p)
    bindings=[{'snapshot_id':snap['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with acting_as(conn,j['actor_id']):
        for b in bindings: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','fixture')",(snap['id'],b['finding_id']))
    store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'quote-revoke')
    req=store.claim_report_request(j['workspace_id'],uuid4())
    args=(req,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
    report=store.publish_report(*args) if operation=='approve' else None
    source=next(iter(p['evidence_input']['passages'].values()))['source_id']
    conn.execute("update public.sources set permitted_operations=array_remove(permitted_operations,'quote') where id=%s",(source,))
    # Ingestion remains allowed with the exact original source permissions otherwise intact.
    assert store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'retain-still-allowed')
    with pytest.raises(Exception,match='machine support|quote permission'):
        if operation=='publish': store.publish_report(*args)
        else:
            with acting_as(conn,j['actor_id']): conn.execute("select public.approve_prepared_report(%s,'fixture')",(report['id'],))


def test_quote_guard_checks_nested_corroboration_source(conn,prepared):
    from psycopg.types.json import Jsonb
    store,j,p=prepared
    primary=next(iter(p['evidence_input']['passages'].values()))['source_id']
    candidate=conn.execute("select id from public.sources where workspace_id=%s and id<>%s and is_active and permitted_operations @> array['fetch','store_text','quote']::text[] limit 1",(j['workspace_id'],primary)).fetchone()['id']
    input={'passages':{'primary':{'source_id':primary}},'corroboration':{'fact':{'result':{'candidates':[{'passage':{'source_id':str(candidate)}}]}}}}
    def allowed():
        return conn.execute('select private.prepared_input_quote_allowed(%s,%s) as ok',(j['workspace_id'],Jsonb(input))).fetchone()['ok']
    assert allowed()
    conn.execute("update public.sources set permitted_operations=array_remove(permitted_operations,'quote') where id=%s",(candidate,))
    assert not allowed()
    assert conn.execute('select private.prepared_sources_allowed(%s,%s::uuid[]) as ok',(j['workspace_id'],[candidate])).fetchone()['ok']


def test_cumulative_snapshot_lineage_preserves_original_reviews_and_fixed_root(conn,prepared,tmp_path):
    from mira.db import acting_as
    store,j,p=prepared; first=store.publish_job(j,p)
    with acting_as(conn,j['actor_id']):
        for fid in p['evidence_input']['findings']: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','original check')",(first['id'],fid))
    _,j2,p2=prepare_run(conn,(j['workspace_id'],j['actor_id']),tmp_path,'second')
    second=store.publish_job(j2,p2)
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'pin-second')
    loaded=store.load_request_snapshots(req['id'])
    assert {s['id'] for s in loaded}=={first['id'],second['id']}
    assert all(set(s['admitted_source_ids'])==set(j['source_ids']) for s in loaded)
    assert all(s['root_snapshot_ids']==[second['id']] for s in loaded)
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'third')
    j3=store.claim_job(j['workspace_id'],uuid4());j3=store.set_job_run(j3,j2['analysis_run_id'])
    third=store.publish_job(j3,p2)
    assert third['id'] not in {s['id'] for s in store.load_request_snapshots(req['id'])}
    request=store.claim_report_request(j['workspace_id'],uuid4(),request_id=req['id'])
    bindings=[{'snapshot_id':s['id'],'finding_id':fid} for s in loaded for fid in s['payload']['evidence_input']['findings']]
    facts={fid:f for s in loaded for fid,f in s['payload']['evidence_input']['findings'].items()}
    report=store.publish_report(request,{'bindings':bindings,'selected_findings':facts},'{{PREPARED_REVIEW_WARNING}}{{PREPARED_FACT_REVIEWS}}',bindings)
    assert report['review_state']=='human_review_pending'
    captured=report['capture']['prepared_bindings']
    assert all(b['decision']=='accepted' for b in captured if b['snapshot_id']==str(first['id']))
    assert all(b['decision'] is None for b in captured if b['snapshot_id']==str(second['id']))


def test_lineage_supersession_uses_pinned_root_cutoff(conn,prepared):
    store,j,p=prepared; first=store.publish_job(j,p)
    old_request=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'before-new-version')
    version=next(iter(p['evidence_input']['passages'].values()))['document_version_id']
    conn.execute("""insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,published_at,retrieved_at,extraction_status,extracted_text)
     select workspace_id,document_id,version_number+1,%s,source_url,title,published_at,clock_timestamp()-interval '1 day','complete','new fixture text' from public.document_versions where id=%s""",(uuid4().hex+uuid4().hex,version))
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'after-new-version')
    nextjob=store.claim_job(j['workspace_id'],uuid4());nextjob=store.set_job_run(nextjob,j['analysis_run_id'])
    second=store.publish_job(nextjob,p)
    new_request=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'after-new-version')
    old=store.load_request_snapshots(old_request['id'])
    assert old[0]['excluded_finding_ids']==[]
    current=store.load_request_snapshots(new_request['id'])
    old_lineage=next(s for s in current if s['id']==first['id'])
    assert old_lineage['excluded_finding_ids']
    claimed=store.claim_report_request(j['workspace_id'],uuid4(),request_id=new_request['id'])
    bindings=[{'snapshot_id':first['id'],'finding_id':fid} for fid in p['evidence_input']['findings']]
    with pytest.raises(ValueError,match='superseded'):
        store.publish_report(claimed,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)


def test_lineage_source_overlap_does_not_admit_other_scope_facts(conn,prepared):
    from copy import deepcopy
    store,j,p=prepared; first=store.publish_job(j,p)
    extra=conn.execute("select id from public.sources where workspace_id=%s and is_active and permitted_operations @> array['fetch','store_text']::text[] and jurisdiction_code='HK' and not(id=any(%s)) limit 1",(j['workspace_id'],j['source_ids'])).fetchone()['id']
    both=j['source_ids']+[extra]
    store.enqueue_job(j['workspace_id'],j['actor_id'],both,j['brief'],{},{},{},'overlap')
    middle_job=store.claim_job(j['workspace_id'],uuid4());middle_job=store.set_job_run(middle_job,j['analysis_run_id'])
    middle_payload=deepcopy(p);middle_payload['source_ids']=[str(x) for x in both]
    middle=store.publish_job(middle_job,middle_payload)
    # Refresh just the other scope with no supported facts. It inherits only
    # that scope's ancestry, not every source in the shared predecessor.
    store.enqueue_job(j['workspace_id'],j['actor_id'],[extra],j['brief'],{},{},{},'other-scope')
    last_job=store.claim_job(j['workspace_id'],uuid4());last_job=store.set_job_run(last_job,j['analysis_run_id'])
    empty=deepcopy(p);empty['source_ids']=[str(extra)];empty['verifications']={}
    empty['evidence_input']=conn.execute('select private.capture_evidence_input(%s,%s,%s,%s::uuid[]) as v',(j['workspace_id'],j['analysis_run_id'],p['evidence_input']['analysis_revision_id'],[])).fetchone()['v']
    latest=store.publish_job(last_job,empty)
    request=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],[extra],'only-other')
    rows=store.load_request_snapshots(request['id'])
    assert {s['id'] for s in rows}=={middle['id'],latest['id']}
    parent=next(s for s in rows if s['id']==middle['id'])
    assert parent['admitted_source_ids']==[extra]
    assert set(map(str,parent['excluded_finding_ids']))==set(p['evidence_input']['findings'])
    assert first['id'] not in {s['id'] for s in rows}


def test_request_pins_registered_queued_job_on_unoccupied_scope(conn,prepared):
    from copy import deepcopy
    store,j,p=prepared; store.publish_job(j,p)
    extras=[r['id'] for r in conn.execute('select id from public.sources where workspace_id=%s and not(id=any(%s)) and private.prepared_sources_allowed(workspace_id,array[id]) order by id limit 2',(j['workspace_id'],j['source_ids']))]
    assert len(extras)==2
    a,c=extras; b=j['source_ids'][0]
    store.enqueue_job(j['workspace_id'],j['actor_id'],[a,b],j['brief'],{},{},{},'AB')
    ab=store.claim_job(j['workspace_id'],uuid4()); ab=store.set_job_run(ab,j['analysis_run_id'])
    bc=store.enqueue_job(j['workspace_id'],j['actor_id'],[b,c],j['brief'],{},{},{},'BC')
    assert conn.execute('select active_job_id from public.preparation_scopes where id=%s',(c,)).fetchone()['active_job_id'] is None
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],[c],'only-C')
    entry=conn.execute('select * from public.prepared_report_request_scopes where request_id=%s',(req['id'],)).fetchone()
    assert req['status']=='waiting' and entry['job_id']==bc['id']
    abp=deepcopy(p);abp['source_ids']=[str(a),str(b)]
    store.publish_job(ab,abp)
    claimed=store.claim_job(j['workspace_id'],uuid4());assert claimed['id']==bc['id']
    claimed=store.set_job_run(claimed,j['analysis_run_id'])
    bcp=deepcopy(p);bcp['source_ids']=[str(b),str(c)]
    snapshot=store.publish_job(claimed,bcp)
    assert store.resolve_request(req['id'])['status']=='queued'
    assert conn.execute('select snapshot_id from public.prepared_report_request_scopes where request_id=%s',(req['id'],)).fetchone()['snapshot_id']==snapshot['id']


def test_exact_dependency_may_bind_original_reviewed_snapshot(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared; first=store.publish_job(j,p)
    store.enqueue_job(j['workspace_id'],j['actor_id'],j['source_ids'],j['brief'],{},{},{},'same-evidence')
    j2=store.claim_job(j['workspace_id'],uuid4());j2=store.set_job_run(j2,j['analysis_run_id'])
    second=store.publish_job(j2,p)
    inference=next(fid for fid,f in p['evidence_input']['findings'].items() if f['depends_on'])
    deps=p['evidence_input']['findings'][inference]['depends_on']
    with acting_as(conn,j['actor_id']):
        for fid in deps: conn.execute("select public.review_prepared_fact(%s,%s,'accepted','original')",(first['id'],fid))
    req=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'reuse-dep')
    claimed=store.claim_report_request(j['workspace_id'],uuid4(),request_id=req['id'])
    bindings=[{'snapshot_id':second['id'],'finding_id':inference}]+[{'snapshot_id':first['id'],'finding_id':fid} for fid in deps]
    report=store.publish_report(claimed,{'bindings':bindings,'selected_findings':p['evidence_input']['findings']},'{{PREPARED_REVIEW_WARNING}}',bindings)
    assert report['review_state']=='human_review_pending'
    assert all(b['decision']=='accepted' for b in report['capture']['prepared_bindings'] if b['snapshot_id']==str(first['id']))


def test_loader_excludes_fact_with_changed_original_latest_check(conn,prepared):
    from mira.db import acting_as
    store,j,p=prepared;snap=store.publish_job(j,p)
    request=store.request_report(j['workspace_id'],j['actor_id'],j['brief'],j['source_ids'],'changed-check')
    fid=next(iter(p['evidence_input']['findings']))
    with acting_as(conn,j['actor_id']):
        conn.execute("insert into public.claim_checks(workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,checked_at) values(%s,%s,%s,99,'llm','unsupported','later check','fixture',clock_timestamp())",(j['workspace_id'],j['analysis_run_id'],fid))
    assert UUID(fid) in store.load_request_snapshots(request['id'])[0]['excluded_finding_ids']


@pytest.mark.parametrize('difference',['fact','fingerprint','missing_fingerprint'])
def test_dependency_alias_requires_identical_fact_and_verification(prepared,difference):
    from copy import deepcopy
    from mira.preparation_store import PreparationStore
    store,j,p=prepared
    inference=next(f for f in p['evidence_input']['findings'].values() if f['depends_on'])
    dep=UUID(inference['depends_on'][0]);origin=uuid4();alias=uuid4()
    snapshots={origin:{'payload':deepcopy(p)},alias:{'payload':deepcopy(p)}}
    assert PreparationStore._dependency_binding_matches(snapshots,[(alias,dep)],origin,dep)
    actual=snapshots[alias]['payload']
    if difference=='fact': actual['evidence_input']['findings'][str(dep)]['content']='Changed material proposition'
    elif difference=='fingerprint': actual['verifications'][str(dep)]['input_fingerprint']='0'*64
    else: actual['verifications'][str(dep)].pop('input_fingerprint')
    assert not PreparationStore._dependency_binding_matches(snapshots,[(alias,dep)],origin,dep)
