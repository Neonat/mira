"""Saved corroboration is append-only, scoped, checked and frozen before sign-off."""
from dataclasses import asdict
from uuid import uuid4
import psycopg
import pytest
from mira.contracts import ReportSnapshot
from mira.db import acting_as
from mira.evidence_snapshot import build_verification_input
from mira.pg_store import PostgresStore
from mira.render import render_signed_off
from mira.render_job import load_findings
from mira.store import StoredClaim
from test_pipeline_db import DSN, conn, workspace, analyst, run_hk, review_all_findings
from test_evidence_integrity_db import sign_off, reverify_current_inputs

pytestmark = pytest.mark.skipif(not DSN, reason='MIRA_TEST_DATABASE_URL not set')


def saved_assessment(conn, ctx, tmp_path, **service_options):
    from mira.corroboration import CorroborationService
    from mira.corroboration_store import CorroborationStore
    from mira.budget import BudgetTracker
    findings = load_findings(conn, ctx.workspace_id, [r['id'] for r in conn.execute(
        'select id from public.analysis_findings where analysis_run_id=%s', (ctx.analysis_run_id,))])
    claims = {f.finding_id: StoredClaim(f.finding_id, f.draft, f.evidence, f.depends_on) for f in findings}
    fact = next(f for f in claims.values() if not f.draft.is_inference)
    store = PostgresStore(conn, reports_dir=tmp_path)
    passages = {p.id: p for p in store.get_passages(ctx.workspace_id, [e.passage_id for e in fact.evidence])}
    base = build_verification_input(ctx, fact, claims, passages).model_dump(mode='json')
    result = CorroborationService(**service_options).assess(ctx=ctx, claim=fact, base_evidence_input=base,
        saved_candidates=[], sources=store.list_sources(ctx.workspace_id), budget=BudgetTracker(ctx.budget),
        authoritative_primary=True)
    ledger = CorroborationStore(conn)
    return ledger, fact, base, ledger.save(ctx, fact, base, result.model_dump(mode='json'))


def test_corroboration_save_caps_worker_clock_ahead_of_postgres(conn, workspace, tmp_path):
    from datetime import datetime, timedelta

    ctx, _ = run_hk(conn, workspace, tmp_path, analyst)
    server_time = conn.execute('select clock_timestamp() as t').fetchone()['t']
    _, _, _, saved = saved_assessment(conn, ctx, tmp_path, now=lambda: server_time + timedelta(minutes=1))
    row = conn.execute('select result,created_at from public.corroboration_assessments where id=%s',
                       (saved['assessment_id'],)).fetchone()
    checked_at = datetime.fromisoformat(row['result']['checked_at'])
    assert server_time <= checked_at <= row['created_at']
    assert saved['assessment'] == row['result']


def test_append_only_and_workspace_read_isolation(conn, workspace, tmp_path):
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == 'draft'
    ledger, fact, base, saved = saved_assessment(conn, ctx, tmp_path)
    assert saved['assessment_id'] and saved['sequence'] > 0
    assert ledger.latest(ctx, [fact.finding_id])[fact.finding_id] == saved
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute('update public.corroboration_assessments set result=result where id=%s', (saved['assessment_id'],))
    outsider = uuid4()
    conn.execute('insert into auth.users (id,email) values (%s,%s)', (outsider, f'{outsider}@test.local'))
    with acting_as(conn, outsider):
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) as n from public.corroboration_assessments where id=%s',
                            (saved['assessment_id'],)).fetchone()['n'] == 0


def test_new_assessment_requires_fresh_verification_and_review_then_freezes(conn, workspace, tmp_path):
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == 'draft'
    review_all_findings(conn, ctx, ctx.user_id)
    ledger, fact, base, saved = saved_assessment(conn, ctx, tmp_path)
    with pytest.raises(psycopg.errors.CheckViolation, match='fresh verification'):
        sign_off(conn, ctx)
    # Helper must pass actual persisted corroboration into the verifier and its captured input.
    ids = [r['id'] for r in conn.execute('select id from public.analysis_findings where analysis_run_id=%s',(ctx.analysis_run_id,))]
    reverify_current_inputs(conn,ctx,tmp_path,corroboration=ledger.latest(ctx,ids))
    with pytest.raises(psycopg.errors.CheckViolation, match='review'):
        sign_off(conn, ctx)
    review_all_findings(conn, ctx, ctx.user_id)
    pending = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(pending['evidence_snapshot'])
    assert snapshot.evidence_bundle.corroboration[fact.finding_id] == saved
    first_html = render_signed_off(snapshot, generated_at=pending['generated_at'])
    assert 'Primary-source only' in first_html
    assert 'Corroboration' in first_html
    ledger.save(ctx, fact, base, saved['assessment'])
    assert render_signed_off(snapshot, generated_at=pending['generated_at']) == first_html
    assert ledger.latest(ctx, [fact.finding_id])[fact.finding_id]['sequence'] > saved['sequence']


def test_candidate_search_keeps_paraphrase_and_different_quantity(conn, workspace, tmp_path):
    from datetime import UTC, datetime
    from mira.corroboration_store import CorroborationStore
    from mira.evidence import EvidenceWriter
    from mira.extract import Extracted
    from mira.fetch import FetchedPage
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == 'draft'
    ledger, fact, base, saved = saved_assessment(conn,ctx,tmp_path)
    source = next(s for s in PostgresStore(conn).list_sources(ctx.workspace_id) if s.name == 'SFC')
    page=FetchedPage('https://apps.sfc.hk/publication-variant','https://apps.sfc.hk/publication-variant',
        source,'html','text/html',b'<p>Different corroborating wording</p>',datetime.now(UTC))
    saved_page=EvidenceWriter(conn,ctx.workspace_id,ctx.user_id).save(page,
        Extracted('Independent circular','complete',['Authorized institutions applied enhanced due diligence to 20 customers.']))
    candidates=ledger.candidates(ctx,fact)
    assert any(c.passage.document_version_id==saved_page.document_version_id for c in candidates)
    candidate=next(c for c in candidates if c.passage.document_version_id==saved_page.document_version_id)
    payload=candidate.model_dump(mode='json')
    payload.pop('workspace_id')
    from psycopg.types.json import Jsonb
    assert conn.execute('select private.corroboration_candidate_current(%s,%s,%s) as valid',
        (ctx.workspace_id,ctx.brief.as_of_date,Jsonb(payload))).fetchone()['valid'] is False


def test_runtime_assesses_saved_second_source_before_check_and_freezes(conn, workspace, tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from mira.corroboration import AssessmentBatch, CandidateDecision, OriginEvidence, Proposition
    from mira.corroboration_runtime import ClaimCorroborator
    from mira.evidence import EvidenceWriter
    from mira.extract import Extracted
    from mira.fetch import FetchedPage
    import test_pipeline_db as fixtures
    import mira.corroboration_runtime as runtime
    ws,user=workspace
    source=next(s for s in PostgresStore(conn).list_sources(ws) if s.name=='SFC')
    text='Our own supervisory investigation examined enhanced due diligence for customers linked to example schemes on 12 December 2025.'
    page=FetchedPage('https://apps.sfc.hk/independent-investigation','https://apps.sfc.hk/independent-investigation',
        source,'html','text/html',text.encode(),datetime.now(UTC))
    EvidenceWriter(conn,ws,user).save(page,Extracted('Independent supervisory investigation','complete',[text]))
    class Assessor:
        def assess(self,claim,primary,candidates,**bounds):
            proposition=Proposition(entity=['Authorized institutions'],jurisdiction='HK',predicate='apply enhanced due diligence',
                scope='customers linked to example schemes',dates=['2025-12-12'],quantities=[],regulatory_status='guidance')
            decisions=[]
            for c in candidates:
                independent=c.passage.source_url.endswith('/independent-investigation')
                decisions.append(CandidateDecision(passage_id=c.passage.id,quote=c.passage.content,proposition=proposition,
                    relation='supports' if independent else 'irrelevant',origin_relation='independent' if independent else 'unknown',
                    origin_evidence=[OriginEvidence(passage_id=p.id,quote=p.content,kind='original_reporting',reason='Original official guidance / own investigation')
                                     for p in [primary[0],c.passage]] if independent else [],reason='Separate original investigation of the same material proposition'))
            return AssessmentBatch(proposition=proposition,decisions=decisions,model='scripted-origin-assessor',
                                   prompt_version='test/1',tokens_in=3,tokens_out=4)
    monkeypatch.setattr(runtime,'LlmAssessor',lambda client:Assessor())
    actual=fixtures.Orchestrator
    monkeypatch.setattr(fixtures,'Orchestrator',lambda store,client,scouts,verifier:actual(store,client,scouts,verifier,
        corroborator=ClaimCorroborator(conn,client)))
    ctx,outcome=run_hk(conn,workspace,tmp_path,analyst)
    assert outcome.status=='draft',outcome.reasons
    rows=conn.execute('select * from public.corroboration_assessments where analysis_run_id=%s',(ctx.analysis_run_id,)).fetchall()
    assert len(rows)==1 and rows[0]['result']['status']=='independently_corroborated'
    checks=conn.execute("select input_snapshot from public.claim_checks where analysis_run_id=%s and method='llm'",(ctx.analysis_run_id,)).fetchall()
    assert all('corroboration' in row['input_snapshot'] for row in checks)
    review_all_findings(conn,ctx,ctx.user_id)
    pending=sign_off(conn,ctx)
    snapshot=ReportSnapshot.model_validate(pending['evidence_snapshot'])
    html=render_signed_off(snapshot,generated_at=pending['generated_at'])
    assert 'Independently corroborated' in html and text in html
    assert 'https://apps.sfc.hk/independent-investigation' in html
    (tmp_path/'corroboration-reviewed.html').write_text(html)
    corrupted=snapshot.model_copy(deep=True)
    entry=next(iter(corrupted.evidence_bundle.corroboration.values()))
    entry['assessment']['decisions'][0]['quote']='Fabricated quotation'
    with pytest.raises(ValueError):
        render_signed_off(corrupted,generated_at=pending['generated_at'])
    # A newer eligible candidate invalidates a new sign-off while the signed artifact stays frozen.
    EvidenceWriter(conn,ws,user).save(page,Extracted('Updated independent investigation','complete',[text+' Updated finding.']))
    assert render_signed_off(snapshot,generated_at=pending['generated_at'])==html
    with pytest.raises(psycopg.errors.CheckViolation,match='candidate changed'):
        sign_off(conn,ctx,draft=conn.execute('select * from public.reports where id=%s',(pending['id'],)).fetchone())


def test_multiple_quotes_use_same_ordinal_order_in_python_and_database(conn,workspace,tmp_path):
    ctx,_=run_hk(conn,workspace,tmp_path,analyst)
    row=conn.execute('select finding_id,analysis_evidence_id from public.finding_evidence where analysis_run_id=%s limit 1',(ctx.analysis_run_id,)).fetchone()
    with acting_as(conn,ctx.user_id):
        conn.execute("insert into public.finding_evidence(workspace_id,analysis_run_id,finding_id,analysis_evidence_id,support_type,supporting_quote) values(%s,%s,%s,%s,'supports','Authorized institutions')",(ctx.workspace_id,ctx.analysis_run_id,row['finding_id'],row['analysis_evidence_id']))
    ledger,fact,base,saved=saved_assessment(conn,ctx,tmp_path)
    actual=conn.execute('select private.capture_base_evidence_input(%s,%s,%s,%s) as base',(ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,[fact.finding_id])).fetchone()['base']
    assert base==actual
    assert ledger.latest(ctx,[fact.finding_id])[fact.finding_id]==saved
