"""Prepared report selection preserves frozen text and review provenance."""
from dataclasses import asdict
from datetime import date
from uuid import uuid4
import pytest
from mira.contracts import Brief
from test_orchestrator import claim


def sample():
    sid,snap,fid,pid,run,revision,ws=[uuid4() for _ in range(7)]
    fact=claim('C1','external_fact','P1','Institutions must screen customers.',
        title='Customer screening requirement',content='Institutions must screen customers.',jurisdiction_code='HK')
    for key in ('claim_label','citations'):fact.pop(key)
    fact.update(finding_id=str(fid),evidence=[{'passage_id':str(pid),'document_version_id':str(uuid4()),
        'supporting_quote':'Institutions must screen customers.','support_type':'supports'}])
    passage={'id':str(pid),'document_version_id':fact['evidence'][0]['document_version_id'],'document_id':str(uuid4()),
        'source_id':str(sid),'source_name':'Example Authority','jurisdiction_code':'HK','title':'Screening notice',
        'source_url':'https://example.org/notice','published_at':'2026-02-03','passage_number':1,
        'content':'Institutions must screen customers.','acquisition_provenance':{}}
    evidence={'schema_version':1,'workspace_id':str(ws),'analysis_run_id':str(run),
        'analysis_revision_id':str(revision),'findings':{str(fid):fact},'passages':{str(pid):passage}}
    check={'check_id':str(uuid4()),'method':'llm','verdict':'supported','reason':'Source-supported',
        'model':'scripted','prompt_version':'test','checked_at':'2026-11-10T00:00:00Z',
        'input_fingerprint':'abc','attempt':1,'agent_step_id':None,'input_snapshot':evidence}
    row={'id':snap,'workspace_id':ws,'published_at':'2026-11-10T00:00:00Z','payload':{'schema_version':1,
        'source_ids':[str(sid)],'evidence_input':evidence,'verifications':{str(fid):check},'coverage':[],
        'analysis_coverage':None,'reasons':[],'prepared_through':'2026-11-04'}}
    brief=Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,11,4),
        period_end=date(2026,11,4),as_of_date=date(2026,11,4),plan_requires_approval=False)
    return row,brief,sid,snap,fid


def test_ready_report_is_newly_assembled_from_exact_frozen_facts():
    from mira.prepared_reporting import select_prepared_facts,compose_prepared_report
    row,brief,sid,snap,fid=sample()
    selected=select_prepared_facts([row],brief,{str(sid):str(snap)},{str(sid)}, {})
    assert len(selected.claims)==1 and selected.claims[0].draft.content=='Institutions must screen customers.'
    html,capture=compose_prepared_report(uuid4(),brief,selected)
    assert '{{PREPARED_REVIEW_WARNING}}' in html
    assert 'Institutions must screen customers.' in html
    assert capture['selected_findings'][str(fid)]==row['payload']['evidence_input']['findings'][str(fid)]
    assert capture['snapshots'][str(snap)]['verifications'][str(fid)]['check_id']==row['payload']['verifications'][str(fid)]['check_id']


@pytest.mark.parametrize('case',['rejected','correction_requested','future','unselected','newer_snapshot'])
def test_ineligible_evidence_never_enters_prepared_report(case):
    from mira.prepared_reporting import select_prepared_facts
    row,brief,sid,snap,fid=sample();allowed={str(sid)};pins={str(sid):str(snap)};reviews={}
    if case in ('rejected','correction_requested'):reviews[(str(snap),str(fid))]=case
    if case=='future':next(iter(row['payload']['evidence_input']['passages'].values()))['published_at']='2026-12-01'
    if case=='unselected':allowed=set()
    if case=='newer_snapshot':pins[str(sid)]=str(uuid4())
    selected=select_prepared_facts([row],brief,pins,allowed,reviews)
    assert selected.claims==[]


def test_nested_corroboration_cannot_bypass_source_and_as_of_filters():
    from mira.prepared_reporting import select_prepared_facts
    row,brief,sid,snap,fid=sample()
    row['payload']['evidence_input']['corroboration']={str(fid):{'assessment':{'candidates':[
        {'passage':{'source_id':str(uuid4()),'published_at':'2026-12-20','content':'Unrequested future evidence'}}]}}}
    selected=select_prepared_facts([row],brief,{str(sid):str(snap)},{str(sid)}, {})
    assert selected.claims==[]


def test_report_export_keeps_publication_coverage_and_fact_review_placeholder():
    from mira.prepared_reporting import select_prepared_facts,compose_prepared_report
    row,brief,sid,snap,fid=sample();expected=str(uuid4())
    row['payload']['coverage']=[{'expected_source_id':expected,'gap_round':0,'status':'missing',
        'document_version_id':None,'note':'A scheduled publication category remains unconfirmed.'}]
    selected=select_prepared_facts([row],brief,{str(sid):str(snap)},{str(sid)}, {})
    html,capture=compose_prepared_report(uuid4(),brief,selected)
    assert 'A scheduled publication category remains unconfirmed.' in html
    assert '{{PREPARED_FACT_REVIEWS}}' in html
    assert capture['report_snapshot']['coverage'][0]['expected_source_id']==expected


def test_inherited_identical_fact_prefers_original_accepted_review_once():
    from copy import deepcopy
    from mira.prepared_reporting import select_prepared_facts
    old,brief,sid,old_id,fid=sample();new=deepcopy(old);new_id=uuid4();new['id']=new_id
    old['admitted_source_ids']=[str(sid)];new['admitted_source_ids']=[str(sid)]
    selected=select_prepared_facts([new,old],brief,{str(sid):str(new_id)},{str(sid)},
        {(str(old_id),str(fid)):'accepted'},max_facts=2)
    assert len(selected.claims)==1
    assert selected.bindings==[{'snapshot_id':str(old_id),'finding_id':str(fid)}]
