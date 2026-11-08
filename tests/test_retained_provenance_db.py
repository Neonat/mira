"""Retained identities freeze exactly; old acquisition provenance stays compatible."""
import os

import pytest
from psycopg.types.json import Jsonb

from mira.evidence import EvidenceWriter
from mira.pg_store import PostgresStore, create_run
from mira.evidence_snapshot import build_verification_input
from mira.contracts import Brief, ClaimDraft
from mira.budget import RunBudget
from mira.store import NewClaim, ClaimEvidence
from test_pipeline_db import conn, workspace
from test_originals_evidence_db import setup_original
from test_orchestrator import claim
from datetime import date

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local DB required')

@pytest.mark.parametrize('retain',[True,False])
def test_python_and_database_freeze_same_optional_original_identity(conn,setup_original,retain):
    ws,user,page,extracted,originals=setup_original
    if not retain:
        from mira.originals import PrivateOriginalStore,RetentionPolicy
        originals=PrivateOriginalStore(originals.root,RetentionPolicy())
    saved=EvidenceWriter(conn,ws,user,originals=originals).save(page,extracted)
    ctx=create_run(conn,ws,user,Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2020,1,1),
        period_end=date(2026,10,26),as_of_date=date(2026,10,26),plan_requires_approval=False),RunBudget(),{})
    store=PostgresStore(conn)
    p=store.get_passages(ws,saved.passage_ids)[0]
    draft=ClaimDraft.model_validate(claim('C1','external_fact','P1','First complete paragraph.',jurisdiction_code='HK'))
    c=store.save_claims(ctx,[NewClaim(draft,(ClaimEvidence(p.id,'First complete paragraph.'),))])[0]
    bundle=build_verification_input(ctx,c,{c.finding_id:c},{p.id:p})
    sql=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,%s) value',
        (ws,ctx.analysis_run_id,ctx.analysis_revision_id,[c.finding_id])).fetchone()['value']
    assert bundle.model_dump(mode='json')==sql
    frozen=sql['passages'][str(p.id)]['acquisition_provenance']
    assert ('retained_original' in frozen)==retain
    assert frozen['original_retained']==retain
    if retain:
        assert originals.read(ws,frozen['retained_original'])==page.body
