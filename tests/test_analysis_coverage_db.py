"""Direct SQL coverage ledger fixtures; no provider calls or production data."""
import os
import uuid
from datetime import date

import psycopg
import pytest
from psycopg.types.json import Jsonb

from mira.budget import RunBudget
from mira.contracts import Brief
from mira.db import acting_as
from mira.pg_store import create_run
from test_pipeline_db import conn, workspace

pytestmark = pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'), reason='local PostgreSQL required')

@pytest.fixture
def ledger(conn, workspace):
    ws, user = workspace
    ctx = create_run(conn, ws, user, Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2025,1,1),
        period_end=date(2026,10,26), as_of_date=date(2026,10,26), plan_requires_approval=False), RunBudget(), {})
    source = conn.execute("select id from public.sources where workspace_id=%s and source_key='hkma'", (ws,)).fetchone()['id']
    doc = conn.execute("insert into public.documents(workspace_id,source_id,canonical_url,title) values(%s,%s,'https://www.hkma.gov.hk/fixture','Fixture') returning id", (ws,source)).fetchone()['id']
    version = conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status) values(%s,%s,1,%s,'https://www.hkma.gov.hk/fixture','Fixture','complete') returning id",(ws,doc,'a'*64)).fetchone()['id']
    passages = [conn.execute("insert into public.document_passages(workspace_id,document_version_id,passage_number,content) values(%s,%s,%s,'Saved passage') returning id", (ws,version,n)).fetchone()['id'] for n in range(1,4)]
    step = conn.execute("insert into public.agent_steps(workspace_id,analysis_run_id,step_no,role) values(%s,%s,1,'analyst') returning id", (ws,ctx.analysis_run_id)).fetchone()['id']
    return dict(ws=ws,user=user,run=ctx.analysis_run_id,rev=ctx.analysis_revision_id,source=source,doc=doc,version=version,passages=passages,step=step)

def policy(conn,x):
    with acting_as(conn,x['user']):
        conn.execute('insert into public.analysis_coverage_policies(workspace_id,analysis_run_id,analysis_revision_id,source_ids,created_by) values(%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],[x['source']],x['user']))

def register(conn,x,disposition='eligible',reason=None):
    with acting_as(conn,x['user']):
        conn.execute('insert into public.analysis_coverage_documents(workspace_id,analysis_run_id,analysis_revision_id,document_version_id,disposition,reason,created_by) values(%s,%s,%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],x['version'],disposition,reason,x['user']))

def event(conn,x,status,key=None,index=0,**overrides):
    data=dict(workspace_id=x['ws'],analysis_run_id=x['run'],analysis_revision_id=x['rev'],document_version_id=x['version'],passage_id=x['passages'][index],status=status,event_key=key or str(uuid.uuid4()),created_by=x['user'],batch_id='B1',agent_step_id=x['step'] if status in ('attempted','analysed','failed') else None,reason='bounded stop' if status in ('failed','deferred') else None)
    data.update(overrides)
    with acting_as(conn,x['user']):
        return conn.execute('insert into public.analysis_passage_events('+','.join(data)+') values('+','.join(['%s']*len(data))+') returning id',list(data.values())).fetchone()

def capture(conn,x):
    return conn.execute('select private.capture_analysis_coverage(%s,%s,%s) as value',(x['ws'],x['run'],x['rev'])).fetchone()['value']

def test_missing_policy_and_empty_policy(conn,ledger):
    assert capture(conn,ledger) is None
    policy(conn,ledger)
    result=capture(conn,ledger)
    assert result['documents']==[] and result['event_sequence']==0 and result['candidate_passages']==0

def test_counts_idempotency_and_audit(conn,ledger):
    x=ledger; policy(conn,x); register(conn,x); register(conn,x)
    for i in range(3): event(conn,x,'candidate',index=i)
    event(conn,x,'attempted'); event(conn,x,'analysed',key='done')
    assert event(conn,x,'analysed',key='done') is None
    event(conn,x,'attempted',index=1); event(conn,x,'failed',index=1)
    event(conn,x,'deferred',index=2)
    result=capture(conn,x)
    assert [result[k+'_passages'] for k in ('candidate','attempted','analysed','failed','deferred','pending')]==[3,2,1,1,1,0]
    assert result['documents'][0]['source_url']=='https://www.hkma.gov.hk/fixture'
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,x,'failed',key='done')
    assert conn.execute("select count(*) n from public.audit_events where workspace_id=%s and entity_type='analysis_passage_events'",(x['ws'],)).fetchone()['n']==8

@pytest.mark.parametrize('status', ['attempted','analysed','failed','deferred'])
def test_candidate_must_precede(conn,ledger,status):
    policy(conn,ledger); register(conn,ledger)
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,ledger,status)

@pytest.mark.parametrize('mutation', ['update','delete'])
def test_immutable(conn,ledger,mutation):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate')
    for table in ('analysis_coverage_policies','analysis_coverage_documents','analysis_passage_events'):
        sql=f'update public.{table} set created_by=created_by' if mutation=='update' else f'delete from public.{table}'
        with pytest.raises(psycopg.errors.CheckViolation): conn.execute(sql+' where analysis_revision_id=%s',(x['rev'],))

def test_scope_actor_and_steps(conn,ledger):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate')
    for kwargs in ({'created_by':uuid.uuid4()}, {'passage_id':uuid.uuid4()}, {'agent_step_id':None}, {'analysis_run_id':uuid.uuid4()}):
        with pytest.raises((psycopg.errors.CheckViolation,psycopg.errors.ForeignKeyViolation)):
            event(conn,x,'attempted',**kwargs)
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,x,'analysed')
    event(conn,x,'attempted')
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,x,'analysed',batch_id='other')

def test_authenticated_cannot_write(conn,ledger):
    x=ledger; policy(conn,x)
    with acting_as(conn,x['user']):
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) n from public.analysis_coverage_policies where workspace_id=%s',(x['ws'],)).fetchone()['n']==1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction(): conn.execute('delete from public.analysis_coverage_policies where analysis_revision_id=%s',(x['rev'],))

def test_stale_version_and_no_text(conn,ledger):
    x=ledger; policy(conn,x)
    newer=conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status) values(%s,%s,2,%s,'https://www.hkma.gov.hk/fixture','New','complete') returning id",(x['ws'],x['doc'],'b'*64)).fetchone()['id']
    with pytest.raises(psycopg.errors.CheckViolation): register(conn,x)
    register(conn,x,'ineligible','stale_version')
    register(conn,{**x,'version':newer},'no_text','no_text')
    assert len(capture(conn,x)['documents'])==2

def draft(conn,x,coverage='missing',version=1,contract='1.6'):
    snapshot={'contract_version':contract,'analysis_run_id':str(x['run']),'analysis_revision_id':str(x['rev']),'sections':[]}
    if coverage!='missing': snapshot['analysis_coverage']=coverage
    return conn.execute("insert into public.reports(workspace_id,analysis_revision_id,report_version,format,template_version,evidence_snapshot,generated_by) values(%s,%s,%s,'html','test',%s,%s) returning *",(x['ws'],x['rev'],version,Jsonb(snapshot),x['user'])).fetchone()

def test_draft_requires_exact_capture_and_legacy_preserved(conn,ledger):
    x=ledger
    with pytest.raises(psycopg.errors.CheckViolation): draft(conn,x)
    assert draft(conn,x,contract='1.4')['evidence_snapshot']['contract_version']=='1.4'
    policy(conn,x); register(conn,x)
    for value in ('missing',None,{}):
        with pytest.raises(psycopg.errors.CheckViolation): draft(conn,x,value,2)
    old=capture(conn,x); event(conn,x,'candidate')
    with pytest.raises(psycopg.errors.CheckViolation): draft(conn,x,old,2)
    saved=draft(conn,x,capture(conn,x),2)
    assert saved['evidence_snapshot']['contract_version']=='1.6'

@pytest.mark.parametrize('change,reason', [
    ("update public.sources set is_active=false where id=%s",'source_inactive'),
    ("update public.sources set permitted_operations=array['fetch'] where id=%s",'operation_denied'),
    ("update public.sources set jurisdiction_code='SG' where id=%s",'jurisdiction_mismatch'),
])
def test_source_eligibility(conn,ledger,change,reason):
    x=ledger; policy(conn,x)
    conn.execute(change,(x['source'],))
    register(conn,x,'ineligible',reason)
    assert capture(conn,x)['documents'][0]['reason']==reason

def test_future_newer_version_does_not_hide_asof_version(conn,ledger):
    x=ledger; policy(conn,x)
    future=conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status,published_at) values(%s,%s,2,%s,'https://www.hkma.gov.hk/fixture','Future','complete','2027-01-01') returning id",(x['ws'],x['doc'],'c'*64)).fetchone()['id']
    register(conn,x)
    register(conn,{**x,'version':future},'ineligible','future_version')
    with pytest.raises(psycopg.errors.CheckViolation): register(conn,{**x,'version':uuid.uuid4()},'ineligible','out_of_scope')

def test_policy_scope_and_out_of_scope_registration(conn,ledger):
    x=ledger
    with acting_as(conn,x['user']):
        conn.execute('insert into public.analysis_coverage_policies(workspace_id,analysis_run_id,analysis_revision_id,source_ids,created_by) values(%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],[],x['user']))
    register(conn,x,'ineligible','out_of_scope')
    assert capture(conn,x)['candidate_passages']==0
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,x,'candidate')

def reviewed(conn,x,snapshot,version):
    return conn.execute("insert into public.reports(workspace_id,analysis_revision_id,report_version,format,template_version,evidence_snapshot,generated_by,review_status,reviewed_by,reviewed_at) values(%s,%s,%s,'html','test',%s,%s,'reviewed',%s,now()) returning *",(x['ws'],x['rev'],version,Jsonb(snapshot),x['user'],x['user'])).fetchone()

def test_review_requires_latest_draft_and_freezes_without_corrob(conn,ledger):
    x=ledger; policy(conn,x); register(conn,x)
    first=draft(conn,x,capture(conn,x))
    event(conn,x,'candidate')
    current={**first['evidence_snapshot'],'analysis_coverage':capture(conn,x)}
    with pytest.raises(psycopg.errors.CheckViolation,match='latest draft'):
        reviewed(conn,x,current,2)
    with pytest.raises(psycopg.errors.CheckViolation,match='missing, stale or forged'):
        reviewed(conn,x,first['evidence_snapshot'],2)
    latest=draft(conn,x,capture(conn,x),2)
    saved=reviewed(conn,x,latest['evidence_snapshot'],3)
    assert saved['evidence_snapshot']['contract_version']=='1.6'
    assert 'corroboration' not in saved['evidence_snapshot']['evidence_bundle']
    assert saved['evidence_snapshot']['analysis_coverage']==latest['evidence_snapshot']['analysis_coverage']
    with pytest.raises(psycopg.errors.CheckViolation,match='immutable'):
        conn.execute("update public.reports set evidence_snapshot=evidence_snapshot-'analysis_coverage' where id=%s",(saved['id'],))
    with pytest.raises(psycopg.errors.CheckViolation,match='already reviewed'): event(conn,x,'deferred')

def test_legacy_review_rejects_original_forged_contract(conn,ledger):
    x=ledger
    row=draft(conn,x,contract='1.4')
    with pytest.raises(psycopg.errors.CheckViolation,match='uninstrumented'):
        reviewed(conn,x,{**row['evidence_snapshot'],'contract_version':'1.6'},2)
    assert reviewed(conn,x,row['evidence_snapshot'],2)['evidence_snapshot']['contract_version']=='1.4'

def test_batch_transaction_rollback(conn,ledger):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate'); event(conn,x,'attempted')
    with pytest.raises(RuntimeError):
        with conn.transaction():
            event(conn,x,'analysed')
            raise RuntimeError('claim save failed')
    assert capture(conn,x)['analysed_passages']==0
    assert capture(conn,x)['pending_passages']==1

def test_event_watermark_is_allocated_under_revision_lock(conn,ledger):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate')
    before=capture(conn,x)['event_sequence']
    # A preallocated identity must not reorder an event that acquired the revision
    # lock later. The trigger owns the final sequence regardless of input/default.
    with acting_as(conn,x['user']):
        conn.execute("insert into public.analysis_passage_events(sequence,workspace_id,analysis_run_id,analysis_revision_id,document_version_id,passage_id,status,event_key,created_by,reason) overriding system value values(-999,%s,%s,%s,%s,%s,'deferred',%s,%s,'cap')",(x['ws'],x['run'],x['rev'],x['version'],x['passages'][0],str(uuid.uuid4()),x['user']))
    result=capture(conn,x)
    assert result['event_sequence']>before
    assert result['deferred_passages']==1

@pytest.mark.parametrize('operation',['event','report'])
def test_appends_and_report_freeze_share_revision_lock(conn,ledger,operation):
    from mira.db import connect
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate')
    summary=capture(conn,x)
    with connect(os.environ['MIRA_TEST_DATABASE_URL']) as other:
        other.execute("set lock_timeout='150ms'")
        with conn.transaction():
            conn.execute('select id from public.analysis_revisions where id=%s for update',(x['rev'],))
            with pytest.raises(psycopg.errors.LockNotAvailable):
                if operation=='event': event(other,x,'deferred')
                else: draft(other,x,summary)
    assert capture(conn,x)==summary

def test_nonmember_cannot_read_and_authenticated_cannot_insert(conn,ledger):
    x=ledger; policy(conn,x)
    with acting_as(conn,uuid.uuid4()):
        conn.execute('set local role authenticated')
        for table in ('analysis_coverage_policies','analysis_coverage_documents','analysis_passage_events'):
            assert conn.execute(f'select count(*) n from public.{table} where workspace_id=%s',(x['ws'],)).fetchone()['n']==0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction(): conn.execute(f'insert into public.{table} default values')

@pytest.mark.parametrize('status',['failed','deferred'])
def test_stops_need_nonempty_reasons(conn,ledger,status):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate'); event(conn,x,'attempted')
    with pytest.raises(psycopg.errors.CheckViolation): event(conn,x,status,reason='   ')

def test_policy_rejects_foreign_source(conn,ledger):
    x=ledger
    with pytest.raises(psycopg.errors.CheckViolation,match='source scope'):
        policy(conn,{**x,'source':uuid.uuid4()})


@pytest.mark.parametrize('terminal', ['analysed','failed','deferred'])
@pytest.mark.parametrize('next_status', ['candidate','attempted','analysed','failed','deferred'])
def test_terminal_disposition_cannot_be_rewritten(conn,ledger,terminal,next_status):
    x=ledger; policy(conn,x); register(conn,x); event(conn,x,'candidate')
    if terminal != 'deferred': event(conn,x,'attempted')
    event(conn,x,terminal)
    with pytest.raises(psycopg.errors.CheckViolation,match='phase transition'):
        event(conn,x,next_status)


def test_postgres_store_claims_and_dispositions_commit_atomically(conn,ledger):
    from mira.pg_store import PostgresStore, load_run
    from mira.store import NewClaim, ClaimEvidence, passage_event
    from mira.contracts import ClaimDraft
    from test_orchestrator import claim
    x=ledger; store=PostgresStore(conn); ctx=load_run(conn,x['run'])
    store.begin_analysis_coverage(ctx,[x['source']])
    passages=store.load_analysis_candidates(ctx,{x['version']:[x['source']]})
    assert len(passages)==3
    store.append_analysis_events(ctx,[passage_event(p,'attempted','B1',x['step']) for p in passages])
    new=NewClaim(ClaimDraft.model_validate(claim('C1','external_fact','P1','Saved passage',jurisdiction_code='HK')),
                 (ClaimEvidence(passages[0].id,'Saved passage'),))
    with pytest.raises(psycopg.errors.CheckViolation):
        store.save_analysis_batch(ctx,'wrong',x['step'],[new],passages)
    assert conn.execute('select count(*) n from public.analysis_findings where analysis_run_id=%s',(x['run'],)).fetchone()['n']==0
    assert store.analysis_coverage(ctx).analysed_passages==0
    saved=store.save_analysis_batch(ctx,'B1',x['step'],[new],passages)
    assert len(saved)==1 and store.analysis_coverage(ctx).analysed_passages==3


def test_normal_factory_enables_batch_coverage_and_keeps_comparison_legacy(conn,ledger):
    from mira.runner import build_orchestrator, build_single_agent_orchestrator
    from mira.llm import ScriptedClient
    worker=build_orchestrator(conn,os.environ['MIRA_TEST_DATABASE_URL'],ledger['ws'],ScriptedClient({}))
    assert worker.analysis_limits.max_passages==8
    worker.corroborator.close()
    comparison=build_single_agent_orchestrator(conn,os.environ['MIRA_TEST_DATABASE_URL'],ledger['ws'],ScriptedClient({}))
    assert comparison.analysis_limits is None


def test_bounded_fake_web_pipeline_freezes_full_pool_and_keeps_mas_inactive(conn,workspace,tmp_path):
    from mira.analysis_batches import AnalysisLimits
    from mira.agents.verifier import LlmVerifier
    from mira.fetch import AllowList,Fetcher
    from mira.llm import ScriptedClient
    from mira.orchestrator import Orchestrator
    from mira.pg_store import PostgresStore
    from test_pipeline_db import WebScout,FakeWeb,planner_for,scout,analyst,writer,DSN
    ws,user=workspace
    conn.execute("update public.sources set is_active=false where workspace_id=%s and source_key='mas'",(ws,))
    ctx=create_run(conn,ws,user,Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,10,26),
        period_end=date(2026,10,26),as_of_date=date(2026,10,26),plan_requires_approval=False),
        RunBudget(max_fetched_documents=30,max_gap_rounds=0),{})
    def analyse_relevant(prompt):
        return analyst(prompt) if 'apply enhanced' in prompt else {'claims':[]}
    client=ScriptedClient({'planner':[planner_for('HK')],'regulatory_scout':[scout,scout],
        'industry_scout':[scout,scout],'analyst':[analyse_relevant]*8,
        'verifier':[{'verdict':'supported','reason':'fixture direct quote'},
            {'introduces_new_fact':False,'new_facts':[],'is_supported_assessment':True,'reason':'fixture'}]*8,
        'writer':[writer]})
    store=PostgresStore(conn,reports_dir=tmp_path)
    fetcher=Fetcher(AllowList(store.list_sources(ws)),transport=FakeWeb(),
        resolver=lambda host:['93.184.216.34'],sleep=lambda _:None)
    web=WebScout(DSN,client,fetcher)
    result=Orchestrator(store,client,{'regulatory_scout':web,'industry_scout':web},LlmVerifier(client),
        analysis_limits=AnalysisLimits()).run(ctx)
    assert result.status in ('draft','partial'), result.reasons
    summary=result.snapshot.analysis_coverage
    assert summary.candidate_passages>0 and summary.analysed_passages==summary.candidate_passages
    assert summary.failed_passages==summary.deferred_passages==summary.pending_passages==0
    saved=conn.execute('select evidence_snapshot,artifact_storage_path from public.reports where analysis_revision_id=%s',(ctx.analysis_revision_id,)).fetchone()
    assert saved['evidence_snapshot']['analysis_coverage']==summary.model_dump(mode='json')
    assert saved['evidence_snapshot']['contract_version']=='1.6'
    assert 'Passage analysis coverage' in (tmp_path/saved['artifact_storage_path']).read_text()
    assert conn.execute("select is_active from public.sources where workspace_id=%s and source_key='mas'",(ws,)).fetchone()['is_active'] is False
    assert conn.execute("select count(*) n from public.document_versions v join public.documents d on d.id=v.document_id join public.sources s on s.id=d.source_id where v.workspace_id=%s and s.source_key='mas'",(ws,)).fetchone()['n']==0
