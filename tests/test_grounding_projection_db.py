"""Conditional provenance on new captures does not retrofit historical snapshots."""
import os
from datetime import date
import pytest
from mira.evidence import EvidenceWriter
from mira.pg_store import PostgresStore, create_run
from mira.evidence_snapshot import build_verification_input
from mira.contracts import Brief, ClaimDraft
from mira.budget import RunBudget
from mira.store import NewClaim, ClaimEvidence
from test_pipeline_db import conn, workspace
from test_originals_evidence_db import setup_original
from test_orchestrator import claim

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local DB required')

@pytest.mark.parametrize('new_capture',[False,True])
def test_grounding_projection_matches_frozen_sql_without_legacy_backfill(conn,setup_original,new_capture):
    ws,user,page,extracted,originals=setup_original
    metadata={'role':'publication','date_scope':'unknown','date_basis':None}
    if new_capture:
        extracted.metadata['claim_grounding']=metadata
    saved=EvidenceWriter(conn,ws,user,originals=originals).save(page,extracted)
    store=PostgresStore(conn)
    p=store.get_passages(ws,saved.passage_ids)[0]
    assert ('claim_grounding' in p.acquisition_provenance)==new_capture
    if new_capture:
        assert p.acquisition_provenance['claim_grounding']==metadata
    ctx=create_run(conn,ws,user,Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2020,1,1),
        period_end=date(2026,10,26),as_of_date=date(2026,10,26),plan_requires_approval=False),RunBudget(),{})
    draft=ClaimDraft.model_validate(claim('C1','external_fact','P1','First complete paragraph.',jurisdiction_code='HK'))
    fact=store.save_claims(ctx,[NewClaim(draft,(ClaimEvidence(p.id,'First complete paragraph.'),))])[0]
    bundle=build_verification_input(ctx,fact,{fact.finding_id:fact},{p.id:p})
    sql=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,%s) value',
        (ws,ctx.analysis_run_id,ctx.analysis_revision_id,[fact.finding_id])).fetchone()['value']
    assert bundle.model_dump(mode='json')==sql
    # Reusing old identical bytes must not silently retrofit new provenance.
    if not new_capture:
        extracted.metadata['claim_grounding']=metadata
        reused=EvidenceWriter(conn,ws,user,originals=originals).save(page,extracted)
        assert reused.document_version_id==saved.document_version_id
        assert 'claim_grounding' not in store.get_passages(ws,saved.passage_ids)[0].acquisition_provenance


def test_explicit_manual_publication_date_retains_its_binding(conn,workspace,tmp_path):
    from mira.manual_import import ImportItem,import_files
    from mira.claim_grounding import grounding
    ws,user=workspace
    path=tmp_path/'circular.html'
    path.write_text('<h1>Customer screening</h1><p>Institutions must screen customers.</p>')
    result=import_files(conn,ws,user,'hkma',[ImportItem(path,'https://www.hkma.gov.hk/example-notice',
        'Customer screening',date(2026,2,3))])[0]
    assert result.outcome=='saved'
    passage=conn.execute('select id from public.document_passages where document_version_id=%s',
        (result.document_version_id,)).fetchone()
    p=PostgresStore(conn).get_passages(ws,[passage['id']])[0]
    assert grounding(p)['date_scope']=='publication'
    assert grounding(p)['date_basis']=='manual manifest publication date'
