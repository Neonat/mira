import os
from datetime import UTC, datetime
from dataclasses import replace

import pytest

from mira.evidence import EvidenceWriter
from mira.extract import Extracted
from mira.fetch import FetchedPage
from mira.pg_store import PostgresStore
from mira.seed import seed
from test_pipeline_db import conn, workspace

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local DB required')


def source_for(conn, ws, key):
    return next(s for s in PostgresStore(conn).list_sources(ws) if s.name==key)


def test_native_record_and_all_text_retained_without_metadata_citations(conn,workspace):
    ws,user=workspace
    source=source_for(conn,ws,'Federal Register of Legislation')
    raw={'id':'C2006A00169','facts':['A','B','C'],'versions':[{'registeredAt':'2026-07-10'}]}
    ex=Extracted('AML metadata','complete',['Discovery metadata only; not legal text.'],metadata={'role':'discovery_metadata','native_record':raw,'acquisition_method':'untrusted'})
    url='https://api.prod.legislation.gov.au/v1/Titles/C2006A00169'
    page=FetchedPage(url,url,source,'json','application/json',b'{"fixture":true}',datetime.now(UTC))
    saved=EvidenceWriter(conn,ws,user).save(page,ex)
    version=conn.execute('select extracted_text,metadata from public.document_versions where id=%s',(saved.document_version_id,)).fetchone()
    assert version['extracted_text']==ex.text
    assert version['metadata']['extraction_metadata']['native_record']==raw
    assert version['metadata']['acquisition_method']=='http_fetch'
    assert saved.text_stored and saved.passage_ids==[]
    again=EvidenceWriter(conn,ws,user).save(page,ex)
    assert again.unchanged and again.text_stored and again.passage_ids==[]
    assert not PostgresStore(conn).get_passages(ws,saved.passage_ids)


def test_full_publication_and_reuse_notice_reach_frozen_passages(conn,workspace):
    ws,user=workspace
    source=source_for(conn,ws,'CBUAE (federal)')
    text='Fact A: training.\n\nFact B: screening.\n\nFact C: record retention.'
    ex=Extracted('Example review','complete',[text])
    url='https://centralbank.ae/media/example.pdf'
    page=FetchedPage(url,url,source,'pdf','application/pdf',b'%PDF fixture',datetime.now(UTC))
    saved=EvidenceWriter(conn,ws,user).save(page,ex)
    row=conn.execute('select extracted_text,metadata from public.document_versions where id=%s',(saved.document_version_id,)).fetchone()
    assert row['extracted_text']==text and all(f'Fact {f}' in row['extracted_text'] for f in 'ABC')
    passages=PostgresStore(conn).get_passages(ws,saved.passage_ids)
    assert passages and all('© Central Bank of the UAE' in p.acquisition_provenance['source_reuse']['notice'] for p in passages)
    assert row['metadata']['original_retained'] is False
    from mira.corroboration_display import provenance_html
    from dataclasses import asdict
    rendered=provenance_html(asdict(passages[0]))
    assert '© Central Bank of the UAE' in rendered and 'terms-and-conditions' in rendered


def test_reseed_keeps_operator_disablement_and_forces_mas_inactive(conn,workspace):
    ws,_=workspace
    conn.execute("update public.sources set is_active=false where workspace_id=%s and source_key='cbuae'",(ws,))
    conn.execute("update public.sources set is_active=true where workspace_id=%s and source_key='mas'",(ws,))
    conn.execute("update public.sources set permitted_operations=array_remove(permitted_operations,'embed') where workspace_id=%s and source_key='au-register'",(ws,))
    seed(conn,ws)
    rows=conn.execute("select source_key,is_active from public.sources where workspace_id=%s and source_key in ('mas','cbuae')",(ws,)).fetchall()
    assert {r['source_key']:r['is_active'] for r in rows}=={'mas':False,'cbuae':False}
    assert 'embed' not in conn.execute("select permitted_operations from public.sources where workspace_id=%s and source_key='au-register'",(ws,)).fetchone()['permitted_operations']


def test_australian_viewer_shell_is_discovery_only_in_database(conn,workspace):
    from mira.extract import extract
    ws,user=workspace;source=source_for(conn,ws,'Federal Register of Legislation')
    url='https://www.legislation.gov.au/C2006A00169/2026-07-01/text'
    page=FetchedPage(url,url,source,'html','text/html',b'<h1>AML Act</h1><p>Viewer contents only</p>',datetime.now(UTC))
    ex=extract(page);saved=EvidenceWriter(conn,ws,user).save(page,ex)
    assert ex.metadata['role']=='discovery_metadata'
    assert saved.passage_ids==[] and saved.text_stored


def test_source_reuse_freezes_identically_in_python_and_database(conn,workspace):
    from datetime import date
    from mira.contracts import Brief,ClaimDraft
    from mira.budget import RunBudget
    from mira.pg_store import create_run
    from mira.store import NewClaim,ClaimEvidence
    from mira.evidence_snapshot import build_verification_input
    from test_orchestrator import claim
    ws,user=workspace;source=source_for(conn,ws,'CBUAE (federal)')
    url='https://centralbank.ae/media/freeze-test.pdf'
    page=FetchedPage(url,url,source,'pdf','application/pdf',b'pdf',datetime.now(UTC))
    ex=Extracted('Example','complete',['Institutions screen customers.'])
    saved=EvidenceWriter(conn,ws,user).save(page,ex)
    ctx=create_run(conn,ws,user,Brief(topic='AML/CFT',jurisdictions=['AE'],period_start=date(2020,1,1),period_end=date(2026,11,10),as_of_date=date(2026,11,10),plan_requires_approval=False),RunBudget(),{})
    store=PostgresStore(conn);p=store.get_passages(ws,saved.passage_ids)[0]
    draft=ClaimDraft.model_validate(claim('C1','external_fact','P1',ex.text,jurisdiction_code='AE'))
    c=store.save_claims(ctx,[NewClaim(draft,(ClaimEvidence(p.id,ex.text),))])[0]
    bundle=build_verification_input(ctx,c,{c.finding_id:c},{p.id:p})
    sql=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,%s) snapshot',(ws,ctx.analysis_run_id,ctx.analysis_revision_id,[c.finding_id])).fetchone()['snapshot']
    assert sql==bundle.model_dump(mode='json',exclude={'corroboration'})
    assert '© Central Bank of the UAE' in sql['passages'][str(p.id)]['acquisition_provenance']['source_reuse']['notice']
