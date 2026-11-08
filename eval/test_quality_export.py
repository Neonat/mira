"""Disposable PostgreSQL fixtures only; no providers or existing run exports."""
import copy
from datetime import date
import os
from pathlib import Path
import sys

import pytest
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
from test_pipeline_db import conn, workspace
from test_analysis_coverage_db import policy, register, event, capture, draft
from mira.budget import RunBudget
from mira.contracts import Brief
from mira.db import acting_as
from mira.pg_store import create_run
from quality_preflight import MODELS, measure
from quality_export import export_retained

pytestmark = pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'), reason='local PostgreSQL required')


@pytest.fixture
def retained_fixture(conn, workspace, request):
    ws, user = workspace
    ctx = create_run(conn, ws, user, Brief(topic='AML/CFT', jurisdictions=['HK'],
        period_start=date(2025,11,4), period_end=date(2026,11,4), as_of_date=date(2026,11,4),
        plan_requires_approval=False), RunBudget(max_fetched_documents=30,max_llm_tokens=600000,max_run_minutes=25), MODELS)
    source = conn.execute("select id from public.sources where workspace_id=%s and source_key='hkma'", (ws,)).fetchone()['id']
    conn.execute("update public.sources set is_active=false where workspace_id=%s and source_key='mas'", (ws,))
    doc = conn.execute("insert into public.documents(workspace_id,source_id,canonical_url,title) values(%s,%s,'https://www.hkma.gov.hk/fixture','Fixture') returning id", (ws,source)).fetchone()['id']
    version = conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status) values(%s,%s,1,%s,'https://www.hkma.gov.hk/fixture','Fixture','complete') returning id", (ws,doc,'a'*64)).fetchone()['id']
    passages = [conn.execute("insert into public.document_passages(workspace_id,document_version_id,passage_number,content) values(%s,%s,%s,'Saved passage') returning id", (ws,version,n)).fetchone()['id'] for n in (1,2)]
    events=[]; steps=[]
    for n in (1,2):
        step = conn.execute("""insert into public.agent_steps(workspace_id,analysis_run_id,step_no,role,status,model,prompt_version,tokens_in,tokens_out,input_refs,output_refs)
          values(%s,%s,%s,'analyst','succeeded',%s,'analyst/3',10,2,%s,%s) returning id""", (ws,ctx.analysis_run_id,n,MODELS['analyst'],Jsonb({'batch_id':f'B{n}'}),Jsonb({}))).fetchone()['id']
        steps.append(step)
        events += [dict(kind='model_started',id=f'm{n}',step_id=str(step),model=MODELS['analyst'],prompt_version='analyst/3'),dict(kind='model_completed',id=f'm{n}',tokens_in=10,tokens_out=2)]
    x=dict(ws=ws,user=user,run=ctx.analysis_run_id,rev=ctx.analysis_revision_id,source=source,doc=doc,version=version,passages=passages,step=steps[0])
    policy(conn,x); register(conn,x)
    for i in range(2):
        event(conn,x,'candidate',index=i)
        event(conn,x,'attempted',index=i,batch_id=f'B{i+1}',agent_step_id=steps[i])
        event(conn,x,'analysed',index=i,batch_id=f'B{i+1}',agent_step_id=steps[i])
    if getattr(request, 'param', True):
        draft(conn,x,capture(conn,x))
    conn.execute("update public.analysis_runs set status='partial',started_at='2026-11-08T00:00:00Z',finished_at='2026-11-08T00:01:00Z' where id=%s", (ctx.analysis_run_id,))
    events = [dict(kind='run_started'),*events,dict(kind='run_finished')]
    for e in events: e['run_id']=str(ctx.analysis_run_id)
    t=dict(run_id=str(ctx.analysis_run_id),outcome_status='partial',max_exa_searches=6,events=events)
    return x,t,steps


def test_real_coverage_multiple_batches_and_read_only(conn, retained_fixture):
    x,t,_=retained_fixture
    exported=export_retained(conn,x['run'],telemetry=t)
    assert exported['unique_batch_ids']==['B1','B2']
    assert exported['clean']['unresumed']
    assert exported['usage']==dict(documents=0,actual_tokens=24,reserved_tokens=0,exa_searches=0)
    assert exported['saved_versions']==1
    assert exported['analysis_coverage']==capture(conn,x)
    assert measure(exported)['passages']==dict(candidate=2,analysed=2,failed=0,deferred=0)
    assert exported['claims']==[]
    assert conn.execute('select count(*) n from public.agent_steps where analysis_run_id=%s',(x['run'],)).fetchone()['n']==2


@pytest.mark.parametrize('change', ['scope','nonterminal','foreign','missing_usage','reservation','models','resumed','event_identity','duplicate_request'])
def test_refuses_inconsistent_inputs(conn, retained_fixture, change):
    x,t,steps=retained_fixture
    if change=='scope':
        conn.execute("update public.analysis_runs set as_of_date='2026-10-26' where id=%s",(x['run'],))
    elif change=='nonterminal':
        conn.execute("update public.analysis_runs set status='running' where id=%s",(x['run'],))
    elif change=='foreign': t['run_id']='foreign'
    elif change=='missing_usage': del t['events'][2]['tokens_in']
    elif change=='reservation':
        conn.execute("update public.agent_steps set output_refs=%s where id=%s",(Jsonb({'reserved_tokens':50}),steps[0]))
    elif change=='models':
        conn.execute("update public.analysis_runs set model_settings='{}' where id=%s",(x['run'],))
    elif change=='resumed': t['events'].append(dict(kind='run_resumed',run_id=str(x['run'])))
    elif change=='event_identity': del t['events'][1]['run_id']
    else: t['events'].append(copy.deepcopy(t['events'][1]))
    with pytest.raises((ValueError,KeyError)):
        export_retained(conn,x['run'],telemetry=t)


def test_actual_embedding_usage_and_unknown_reservations_disjoint(conn,retained_fixture):
    x,t,steps=retained_fixture
    conn.execute('update public.agent_steps set output_refs=%s where id=%s', (Jsonb({'embedding_usage':{'tokens':7,'reserved_tokens':9}}),steps[0]))
    t['events'][-1:-1] = [dict(kind='embedding_started',id='e1',step_id=str(steps[0]),run_id=str(x['run'])),
      dict(kind='embedding_completed',id='e1',tokens_in=7,tokens_out=0,run_id=str(x['run'])),
      dict(kind='embedding_started',id='e2',step_id=str(steps[0]),run_id=str(x['run'])),
      dict(kind='embedding_error',id='e2',usage_known=False,charged_or_reserved=9,run_id=str(x['run']))]
    result=export_retained(conn,x['run'],telemetry=t)
    assert result['usage']['actual_tokens']==31
    assert result['usage']['reserved_tokens']==9


def test_attempts_are_not_saved_versions(conn,retained_fixture):
    x,t,steps=retained_fixture
    logs=[dict(url='https://www.hkma.gov.hk/fixture',outcome=o,request_sent=True) for o in ('saved','failed','refused','reused')]
    conn.execute('update public.agent_steps set output_refs=%s where id=%s',(Jsonb({'fetch_log':logs,'fetch_attempts':4}),steps[0]))
    exported=export_retained(conn,x['run'],telemetry=t)
    assert exported['usage']['documents']==2
    assert exported['saved_versions']==1


def test_pending_ledger_does_not_become_deferred(conn,retained_fixture):
    x,t,_=retained_fixture
    new=conn.execute("insert into public.document_passages(workspace_id,document_version_id,passage_number,content) values(%s,%s,3,'Pending') returning id",(x['ws'],x['version'])).fetchone()['id']
    event(conn,{**x,'passages':[new]},'candidate')
    draft(conn,x,capture(conn,x),2)
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


def finding(conn,x):
    with acting_as(conn,x['user']):
        f=conn.execute("""insert into public.analysis_findings(workspace_id,analysis_run_id,analysis_revision_id,finding_type,title,content,created_by)
           values(%s,%s,%s,'external_fact','Fixture finding','Saved passage',%s) returning id""",(x['ws'],x['run'],x['rev'],x['user'])).fetchone()['id']
        ae=conn.execute('insert into public.analysis_evidence(workspace_id,analysis_run_id,document_version_id,passage_id) values(%s,%s,%s,%s) returning id',(x['ws'],x['run'],x['version'],x['passages'][0])).fetchone()['id']
        conn.execute("insert into public.finding_evidence(workspace_id,analysis_run_id,finding_id,analysis_evidence_id,support_type,supporting_quote) values(%s,%s,%s,%s,'supports','Saved passage')",(x['ws'],x['run'],f,ae))
    return f


def test_final_report_citations_latest_bound_primary_and_corroboration(conn,retained_fixture):
    x,t,steps=retained_fixture
    f=finding(conn,x)
    with acting_as(conn,x['user']):
        for status in ('inconclusive','primary_source_only'):
            base=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,array[%s]::uuid[]) v',(x['ws'],x['run'],x['rev'],f)).fetchone()['v']
            a=dict(workspace_id=str(x['ws']),analysis_run_id=str(x['run']),analysis_revision_id=str(x['rev']),finding_id=str(f),status=status,checked_at='2026-11-08T00:00:00Z',document_attempts=0,candidates=[])
            conn.execute('insert into public.corroboration_assessments(workspace_id,analysis_run_id,analysis_revision_id,finding_id,base_input,result,created_by) values(%s,%s,%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],f,Jsonb(base),Jsonb(a),x['user']))
        inp=conn.execute('select private.capture_evidence_input(%s,%s,%s,array[%s]::uuid[]) v',(x['ws'],x['run'],x['rev'],f)).fetchone()['v']
        fp=conn.execute('select private.evidence_input_fingerprint(%s) v',(Jsonb(inp),)).fetchone()['v']
        conn.execute("""insert into public.claim_checks(workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,input_snapshot,input_fingerprint)
           values(%s,%s,%s,1,'llm','supported','Fixture check',%s,%s,%s)""",(x['ws'],x['run'],f,MODELS['verifier'],Jsonb(inp),fp))
        snapshot=dict(contract_version='1.6',analysis_run_id=str(x['run']),analysis_revision_id=str(x['rev']),analysis_coverage=capture(conn,x),sections=[dict(sentences=[dict(structural=False,finding_ids=[str(f)])])])
        conn.execute("""insert into public.reports(workspace_id,analysis_revision_id,report_version,format,template_version,evidence_snapshot,generated_by)
          values(%s,%s,2,'html','fixture',%s,%s)""",(x['ws'],x['rev'],Jsonb(snapshot),x['user']))
    result=export_retained(conn,x['run'],telemetry=t)
    assert result['cited_urls']==['https://www.hkma.gov.hk/fixture']
    assert len(result['findings'])==1
    assert result['findings'][0]['primary_verification']=='supported'
    assert result['findings'][0]['corroboration']=='primary_source_only'
    assert result['findings'][0]['primary_check']['bound']
    assert result['report_exists'] and result['report']['version']==2
    assert result['claims'][0]['supporting_quote']=='Saved passage'
    conn.execute("update public.analysis_findings set content='Edited finding' where id=%s",(f,))
    with pytest.raises(ValueError,match='as of generation'):
        export_retained(conn,x['run'],telemetry=t)


def test_exa_requests_from_journal_and_unknown_model_reservation(conn,retained_fixture):
    x,t,steps=retained_fixture
    conn.execute("update public.agent_steps set tokens_in=0,tokens_out=0,output_refs=%s where id=%s",(Jsonb({'reserved_tokens':100}),steps[0]))
    t['events'][2]=dict(kind='model_error',id='m1',run_id=str(x['run']),usage_known=False,charged_or_reserved=100)
    t['events'].insert(-1,dict(kind='exa_requested',id='exa1',run_id=str(x['run'])))
    result=export_retained(conn,x['run'],telemetry=t)
    assert result['usage']==dict(actual_tokens=12,reserved_tokens=100,exa_searches=1,documents=0)


def test_mas_row_enforced(conn,retained_fixture):
    x,t,_=retained_fixture
    conn.execute("update public.sources set is_active=true where workspace_id=%s and source_key='mas'",(x['ws'],))
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


def test_bare_actual_model_identity_preserved(conn,retained_fixture):
    x,t,steps=retained_fixture
    conn.execute("update public.agent_steps set model='gpt-5.4' where id=%s",(steps[0],))
    result=export_retained(conn,x['run'],telemetry=t)
    assert result['actual_step_models'][0]['model']=='gpt-5.4'
    conn.execute("update public.agent_steps set model='gpt-5.4-other' where id=%s",(steps[0],))
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


def test_independent_label_without_origin_evidence_refused(conn,retained_fixture):
    x,t,_=retained_fixture
    f=finding(conn,x)
    with acting_as(conn,x['user']):
        base=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,array[%s]::uuid[]) v',(x['ws'],x['run'],x['rev'],f)).fetchone()['v']
        a=dict(workspace_id=str(x['ws']),analysis_run_id=str(x['run']),analysis_revision_id=str(x['rev']),finding_id=str(f),status='independently_corroborated',checked_at='2026-11-08T00:00:00Z',document_attempts=0,candidates=[],decisions=[])
        conn.execute('insert into public.corroboration_assessments(workspace_id,analysis_run_id,analysis_revision_id,finding_id,base_input,result,created_by) values(%s,%s,%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],f,Jsonb(base),Jsonb(a),x['user']))
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


def test_multiple_workspace_runs_refused(conn,retained_fixture):
    x,t,_=retained_fixture
    create_run(conn,x['ws'],x['user'],Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,11,4),period_end=date(2026,11,4),as_of_date=date(2026,11,4),plan_requires_approval=False),RunBudget(),MODELS)
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


@pytest.mark.parametrize('retained_fixture',[False],indirect=True)
def test_absent_report_exports_unmeasured_citation_recall(conn,retained_fixture):
    x,t,_=retained_fixture
    exported=export_retained(conn,x['run'],telemetry=t)
    assert not exported['report_exists'] and exported['report'] is None
    assert measure(exported)['cited'] is None


def test_all_corroboration_acquisitions_counted_and_mas_proof_required(conn,retained_fixture):
    x,t,_=retained_fixture
    f=finding(conn,x)
    with acting_as(conn,x['user']):
        base=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,array[%s]::uuid[]) v',(x['ws'],x['run'],x['rev'],f)).fetchone()['v']
        for n,status in [(2,'inconclusive'),(3,'primary_source_only')]:
            a=dict(workspace_id=str(x['ws']),analysis_run_id=str(x['run']),analysis_revision_id=str(x['rev']),finding_id=str(f),status=status,checked_at='2026-11-08T00:00:00Z',document_attempts=n,candidates=[])
            conn.execute('insert into public.corroboration_assessments(workspace_id,analysis_run_id,analysis_revision_id,finding_id,base_input,result,created_by) values(%s,%s,%s,%s,%s,%s,%s)',(x['ws'],x['run'],x['rev'],f,Jsonb(base),Jsonb(a),x['user']))
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)
    t['corroboration_document_attempts']=5
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)
    t['corroboration_mas_fetches']=0
    exported=export_retained(conn,x['run'],telemetry=t)
    assert exported['usage']['documents']==5
    assert exported['acquisition_counters']['corroboration_assessments_all']==5
    assert exported['findings'][0]['corroboration']=='primary_source_only'
    t['corroboration_mas_fetches']=1
    with pytest.raises(ValueError): export_retained(conn,x['run'],telemetry=t)


def verify_finding(conn,x,f,attempt=1):
    with acting_as(conn,x['user']):
        inp=conn.execute('select private.capture_evidence_input(%s,%s,%s,array[%s]::uuid[]) v',(x['ws'],x['run'],x['rev'],f)).fetchone()['v']
        fp=conn.execute('select private.evidence_input_fingerprint(%s) v',(Jsonb(inp),)).fetchone()['v']
        conn.execute("""insert into public.claim_checks(workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,input_snapshot,input_fingerprint)
          values(%s,%s,%s,%s,'llm','supported','Fixture check',%s,%s,%s)""",(x['ws'],x['run'],f,attempt,MODELS['verifier'],Jsonb(inp),fp))


def cited_draft(conn,x,f):
    snapshot=dict(contract_version='1.6',analysis_run_id=str(x['run']),analysis_revision_id=str(x['rev']),analysis_coverage=capture(conn,x),coverage=[],unresolved_finding_ids=[],sections=[dict(section='executive_summary',no_verified_items=False,sentences=[dict(text='Fixture claim.',structural=False,finding_ids=[str(f)])])])
    with acting_as(conn,x['user']):
        return conn.execute("""insert into public.reports(workspace_id,analysis_revision_id,report_version,format,template_version,evidence_snapshot,generated_by)
          values(%s,%s,2,'html','fixture',%s,%s) returning *""",(x['ws'],x['rev'],Jsonb(snapshot),x['user'])).fetchone()


@pytest.mark.parametrize('mutation',['finding','evidence','dependency'])
def test_post_report_mutation_and_fresh_check_cannot_rebind_old_draft(conn,retained_fixture,mutation):
    x,t,_=retained_fixture
    f=finding(conn,x)
    verify_finding(conn,x,f)
    report=cited_draft(conn,x,f)
    assert export_retained(conn,x['run'],telemetry=t)['report_binding']['mode']=='draft_checks_as_of_generation'
    if mutation=='finding':
        conn.execute("update public.analysis_findings set content='Later claim' where id=%s",(f,))
    elif mutation=='evidence':
        conn.execute("update public.finding_evidence set supporting_quote='Saved' where finding_id=%s",(f,))
    else:
        dep=finding(conn,{**x,'passages':[x['passages'][1]]})
        conn.execute('insert into public.finding_dependencies(workspace_id,analysis_run_id,finding_id,depends_on_finding_id) values(%s,%s,%s,%s)',(x['ws'],x['run'],f,dep))
        verify_finding(conn,x,dep)
    verify_finding(conn,x,f,2)
    assert conn.execute('select max(checked_at)>%s later from public.claim_checks where finding_id=%s',(report['generated_at'],f)).fetchone()['later']
    with pytest.raises(ValueError,match='as of generation'):
        export_retained(conn,x['run'],telemetry=t)


def test_check_only_after_report_does_not_supply_missing_original_binding(conn,retained_fixture):
    x,t,_=retained_fixture
    f=finding(conn,x)
    cited_draft(conn,x,f)
    verify_finding(conn,x,f)
    with pytest.raises(ValueError,match='as of generation'):
        export_retained(conn,x['run'],telemetry=t)


def test_reviewed_citations_and_precision_use_frozen_bundle_after_live_mutation(conn,retained_fixture):
    from test_analysis_coverage_db import reviewed
    x,t,_=retained_fixture
    f=finding(conn,x)
    conn.execute("update public.analysis_findings set priority='high',evidence_confidence='high' where id=%s",(f,))
    verify_finding(conn,x,f)
    report=cited_draft(conn,x,f)
    with acting_as(conn,x['user']):
        conn.execute("insert into public.finding_reviews(workspace_id,finding_id,decision,reviewed_by) values(%s,%s,'accepted',%s)",(x['ws'],f,x['user']))
        reviewed(conn,x,report['evidence_snapshot'],3)
    before=export_retained(conn,x['run'],telemetry=t)
    assert before['report_binding']['mode']=='frozen_reviewed_bundle'
    conn.execute("update public.analysis_findings set content='Later mutable claim' where id=%s",(f,))
    conn.execute("update public.finding_evidence set supporting_quote='Saved' where finding_id=%s",(f,))
    verify_finding(conn,x,f,2)
    after=export_retained(conn,x['run'],telemetry=t)
    assert after['claims']==before['claims']
    assert after['claims'][0]['supporting_quote']=='Saved passage'
    assert after['cited_urls']==before['cited_urls']
    assert 'Later mutable claim' not in after['claims'][0]['claim']


@pytest.mark.parametrize('persisted,purpose,request_prompt',[
    ('verifier/2',None,'corroboration/3-single-candidate'),
    ('corroboration/3-single-candidate',None,'corroboration/3-single-candidate'),
    ('verifier/2','corroboration','verifier/2'),
    ('corroboration/3-single-candidate','corroboration','corroboration/forged'),
    ('verifier/2',None,'verifier/forged'),
])
def test_request_prompt_and_purpose_cannot_forge_corroboration(conn,retained_fixture,persisted,purpose,request_prompt):
    x,t,_=retained_fixture
    refs={} if purpose is None else dict(purpose=purpose)
    step=conn.execute("""insert into public.agent_steps(workspace_id,analysis_run_id,step_no,role,status,model,prompt_version,tokens_in,tokens_out,input_refs)
       values(%s,%s,3,'verifier','succeeded',%s,%s,5,1,%s) returning id""",(x['ws'],x['run'],MODELS['verifier'],persisted,Jsonb(refs))).fetchone()['id']
    t['events'][-1:-1]=[dict(kind='model_started',id='v1',run_id=str(x['run']),step_id=str(step),model=MODELS['verifier'],prompt_version=request_prompt),dict(kind='model_completed',id='v1',run_id=str(x['run']),tokens_in=5,tokens_out=1)]
    with pytest.raises(ValueError,match='prompt|classification'):
        export_retained(conn,x['run'],telemetry=t)


def test_persisted_corroboration_prompt_counts_and_scout_allowlist(conn,retained_fixture):
    x,t,steps=retained_fixture
    conn.execute("update public.agent_steps set role='verifier',prompt_version='corroboration/3-single-candidate',input_refs=%s where id=%s",(Jsonb({'purpose':'corroboration'}),steps[0]))
    t['events'][1]['prompt_version']='corroboration/3-single-candidate'
    result=export_retained(conn,x['run'],telemetry=t)
    assert result['corroboration_calls']['requested']==1
    assert result['corroboration_calls']['completed']==1
    conn.execute("update public.agent_steps set role='regulatory_scout',model=%s,prompt_version='scout/6',input_refs='{}' where id=%s",(MODELS['regulatory_scout'],steps[0]))
    t['events'][1].update(model=MODELS['regulatory_scout'],prompt_version='scout/6')
    assert export_retained(conn,x['run'],telemetry=t)['corroboration_calls']['requested']==0
    conn.execute("update public.agent_steps set prompt_version='scout/forged' where id=%s",(steps[0],))
    t['events'][1]['prompt_version']='scout/forged'
    with pytest.raises(ValueError,match='scout'):
        export_retained(conn,x['run'],telemetry=t)
