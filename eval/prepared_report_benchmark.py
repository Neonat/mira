"""Offline synthetic prepared-report benchmark. Never run against a remote DB.

Reproduce: PYTHONPATH=.:tests /Users/natsim/Documents/dbsearch/.venv/bin/python eval/prepared_report_benchmark.py
Each invocation creates one isolated synthetic workspace, one prepared snapshot,
and exactly two report requests. No benchmark data is used by production retrieval.
"""
from __future__ import annotations

import hashlib
from html import escape, unescape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from uuid import uuid4

from psycopg.conninfo import conninfo_to_dict
from mira.agents.verifier import LlmVerifier
from mira.budget import RunBudget
from mira.config import load_env
from mira.contracts import Brief, ClaimCitation, ClaimDraft, StepRecord
from mira.db import acting_as, connect
from mira.evidence_snapshot import build_verification_input
from mira.llm import ScriptedClient
from mira.manual_import import ImportItem, import_files
from mira.pg_store import PostgresStore, create_run
from mira.preparation_store import PreparationStore
from mira.prepared_reporting import build_prepared_payload, execute_prepared_request
from mira.research_settings import ResearchSettings
from mira.seed import seed
from mira.store import ClaimEvidence, NewClaim

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'reports/scheduled-evidence-20261110/benchmark'
SUMMARY = ROOT / 'eval/evidence/2026-11-10-prepared-report-benchmark'

# Invented controls, dates, instruments and obligations; no real HKMA content.
DOCUMENTS = {
    'A': [
        'Article A requires synthetic pilot banks to screen customers before onboarding from 1 October 2026.',
        'Article A requires synthetic pilot banks to retain screening logs for 7 years.',
        'Article A requires synthetic pilot banks to refresh high-risk profiles every 90 days.',
        'Article A exempts dormant synthetic pilot accounts from monthly profile refresh unless activity resumes.',
        'Article A requires synthetic pilot banks to record the beneficial owner before activating an account.',
    ],
    'B': [
        'Article B requires synthetic pilot banks to report confirmed sanctions matches within 2 working days.',
        'Article B requires synthetic pilot banks to escalate unresolved screening alerts after 48 hours.',
        'Article B permits synthetic pilot banks to defer a low-risk review by 30 days only with written approval.',
        'Article B requires synthetic pilot banks to reconcile alert totals every business day.',
        'Article B requires synthetic pilot banks to appoint a named sanctions escalation officer.',
    ],
    'C': [
        'Article C requires synthetic pilot banks to test transaction-monitoring scenarios every quarter.',
        'Article C requires synthetic pilot banks to retain model-validation results for 5 years.',
        'Article C proposes, but does not require, synthetic pilot banks to test an experimental network model.',
        'Article C requires synthetic pilot banks to obtain independent approval before changing alert thresholds.',
        'Article C requires synthetic pilot banks to document false-positive rates in each validation report.',
    ],
    'D': [
        'Article D requires synthetic pilot banks to complete staff training by 15 December 2026.',
        'Article D requires synthetic pilot banks to test recovery of screening records twice each year.',
        'Article D requires synthetic pilot banks to notify the synthetic supervisor before outsourcing screening.',
        'Article D requires synthetic pilot banks to review outsourced screening contracts annually.',
        'Article D allows synthetic pilot banks to use a 60-day transition only for contracts signed before 1 September 2026.',
    ],
}


def network_guard(event, args):
    if event == 'socket.connect':
        address = args[1]
        if not (isinstance(address, tuple) and address[0] in ('localhost', '127.0.0.1', '::1') and address[1] == 55432):
            raise RuntimeError('Offline benchmark prohibits non-local-PostgreSQL network access')


def validate_report(row, payload, expected):
    html = row['html']
    text = unescape(re.sub('<[^>]*>', ' ', html))
    captured = row['capture']['selected_findings']
    assert set(captured) == set(payload['evidence_input']['findings']) == set(expected)
    for fid, fact in expected.items():
        assert captured[fid] == payload['evidence_input']['findings'][fid]
        assert captured[fid]['content'] == fact['text'] and fact['text'] in text
        assert captured[fid]['evidence'][0]['passage_id'] == fact['passage_id']
        assert captured[fid]['evidence'][0]['supporting_quote'] == fact['text']
        assert escape(fact['url'], quote=True) in html
        passage = payload['evidence_input']['passages'][fact['passage_id']]
        assert passage['source_id'] == fact['source_id'] and fact['text'] in passage['content']
    assert all('Article '+letter in text for letter in 'ABC')
    assert '{{PREPARED_REVIEW_WARNING}}' not in html
    assert row['content_sha256'] == hashlib.sha256(html.encode()).hexdigest()


def main():
    load_env(keys={'MIRA_WORKER_DATABASE_URL', 'MIRA_TEST_DATABASE_URL'})
    dsn = os.environ.get('MIRA_TEST_DATABASE_URL') or os.environ.get('MIRA_WORKER_DATABASE_URL')
    if not dsn:
        raise RuntimeError('Local PostgreSQL DSN is required')
    config = conninfo_to_dict(dsn)
    if config.get('host') not in ('localhost', '127.0.0.1', '::1') or config.get('port') != '55432':
        raise RuntimeError('Benchmark requires local PostgreSQL on port 55432')
    sys.addaudithook(network_guard)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with connect(dsn) as conn:
        actor = uuid4()
        conn.execute('insert into auth.users(id,email) values(%s,%s)', (actor, f'{actor}@synthetic.invalid'))
        ws = conn.execute("insert into public.workspaces(slug,name) values(%s,'SYNTHETIC prepared benchmark only') returning id", ('synthetic-prepared-'+uuid4().hex[:12],)).fetchone()['id']
        conn.execute("insert into public.workspace_members(workspace_id,user_id,role) values(%s,%s,'admin')", (ws,actor))
        seed(conn, ws)
        assert conn.execute("select not is_active as disabled from public.sources where workspace_id=%s and source_key='mas'", (ws,)).fetchone()['disabled']
        source = conn.execute("select id from public.sources where workspace_id=%s and source_key='hkma'", (ws,)).fetchone()['id']
        settings = ResearchSettings(source_ids=(str(source),), retrieval='keyword')
        assert settings.retrieval == 'keyword' and not settings.enable_exa and not settings.enable_browser
        brief = Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2026,9,1),
                      period_end=date(2026,11,10), as_of_date=date(2026,11,10), plan_requires_approval=False)
        store = PostgresStore(conn, reports_dir=ARTIFACTS)
        ctx = create_run(conn,ws,actor,brief,RunBudget(),{},settings=settings)
        documents = []
        expected_inputs = []
        for letter, facts in DOCUMENTS.items():
            path = ARTIFACTS / f'synthetic-article-{letter}.html'
            title = f'SYNTHETIC Article {letter} — benchmark fixture, not regulatory guidance'
            url = f'https://www.hkma.gov.hk/synthetic-benchmark/{ws}/article-{letter}'
            path.write_text('<html><head><meta name="article:published_time" content="2026-09-15"></head><body><main><h1>'+title+'</h1><p>SYNTHETIC FIXTURE. Published 15 September 2026. No actual regulatory content.</p>'+''.join('<p>'+escape(f)+'</p>' for f in facts)+'</main></body></html>')
            imported, = import_files(conn,ws,actor,'hkma',[ImportItem(path,url,title,date(2026,9,15))])
            assert imported.outcome == 'saved', imported.error
            pids = [r['id'] for r in conn.execute('select id from public.document_passages where workspace_id=%s and document_version_id=%s',(ws,imported.document_version_id))]
            passages = store.get_passages(ws,pids)
            documents.append({'article':letter,'url':url,'version_id':str(imported.document_version_id),'passages':len(passages),'published_at':'2026-09-15'})
            for fact in facts:
                passage = next(p for p in passages if fact in p.content)
                expected_inputs.append((fact,passage,url))
        drafts = []
        for i,(text,passage,url) in enumerate(expected_inputs,1):
            draft = ClaimDraft(claim_label=f'C{i}',finding_type='obligation_summary',title=f'SYNTHETIC critical fact {i}',
                content=text,jurisdiction_code='HK',change_type='new',industry_category=None,
                key_date=date(2026,9,15),key_date_kind='published',is_inference=False,
                citations=[ClaimCitation(passage_label=f'P{i}',supporting_quote=text)],depends_on=[],priority='high',
                priority_reason='Synthetic fixture',evidence_confidence='high',evidence_confidence_reason='Scripted fixture, not human judgement')
            drafts.append(NewClaim(draft,(ClaimEvidence(passage.id,text),)))
        claims = store.save_claims(ctx,drafts)
        by_id = {c.finding_id:c for c in claims}
        all_passages = {p.id:p for _,p,_ in expected_inputs}
        scripted = ScriptedClient({'verifier':[{'verdict':'supported','reason':'SYNTHETIC scripted support response; exact fixture sentence.'} for _ in claims]},model='synthetic-scripted-no-provider',tokens_in=0,tokens_out=0)
        verifier = LlmVerifier(scripted)
        step = store.start_step(ctx,StepRecord(analysis_run_id=ctx.analysis_run_id,step_no=1,role='verifier',jurisdiction_code='HK',gap_round=0,
            status='succeeded',contract_version='synthetic-benchmark/1',model='synthetic-scripted-no-provider',prompt_version='verifier/3',
            temperature=None,input_refs={'synthetic':True},output_refs={'synthetic':True},tokens_in=0,tokens_out=0,
            started_at=datetime.now(UTC),finished_at=datetime.now(UTC),error=None))
        expected = {}
        for claim,(text,passage,url) in zip(claims,expected_inputs):
            frozen = build_verification_input(ctx,claim,by_id,all_passages).model_dump(mode='json')
            outcome = verifier.check_fact(claim,[passage],1,brief=brief)
            assert outcome.verdict == 'supported'
            store.save_checks(ctx,step,outcome.checks,input_snapshot=frozen)
            expected[str(claim.finding_id)] = {'text':text,'passage_id':str(passage.id),'source_id':str(source),'url':url}
        assert len(scripted.calls) == 20
        store.set_run_status(ctx,'draft','SYNTHETIC fixture: only 20 manually selected facts checked; no acquisition/discovery or exhaustive analysis benchmark.')
        prep = PreparationStore(conn)
        job = prep.enqueue_job(ws,actor,[source],brief,{}, {},settings.__dict__,'synthetic-preparation')
        job = prep.claim_job(ws,uuid4())
        assert job is not None
        job = prep.set_job_run(job,ctx.analysis_run_id)
        payload = build_prepared_payload(conn,ctx.analysis_run_id,[source])
        assert len(payload['evidence_input']['findings']) == 20
        snapshot = prep.publish_job(job,payload)
        no_calls = ScriptedClient({})
        cases = []
        first_report = None
        for case in ('review_pending','scripted_review_accepted'):
            if case == 'scripted_review_accepted':
                with acting_as(conn,actor):
                    for fid in expected:
                        conn.execute("select public.review_prepared_fact(%s,%s,'accepted','SYNTHETIC scripted review only; not a human accuracy label')",(snapshot['id'],fid))
            started = time.perf_counter()
            request = prep.request_report(ws,actor,brief,[source],case)
            outcome = execute_prepared_request(conn,dsn,request['id'],no_calls,workspace_id=ws)
            assert outcome['status'] == 'ready', outcome
            report = conn.execute('select * from public.prepared_reports where id=%s',(outcome['report_id'],)).fetchone()
            elapsed = time.perf_counter()-started
            validate_report(report,payload,expected)
            assert not no_calls.calls
            assert elapsed < 300
            if case == 'review_pending':
                assert report['review_state'] == 'human_review_pending' and 'human evidence review pending' in report['html']
                first_report = report
            else:
                assert report['review_state'] == 'human_checked' and 'Final report approval is separate.' in report['html']
                historical = conn.execute('select * from public.prepared_reports where id=%s',(first_report['id'],)).fetchone()
                assert historical['html'] == first_report['html'] and historical['review_state'] == 'human_review_pending'
            (ARTIFACTS / f'{case}.html').write_text(report['html'])
            (ARTIFACTS / f'{case}-capture.json').write_text(json.dumps(report['capture'],indent=2,default=str))
            cases.append({'case':case,'request_id':str(request['id']),'report_id':str(report['id']),
                'submit_to_final_html_seconds':elapsed,'worker_seconds':outcome['seconds'],'under_300_seconds':True,
                'review_state':report['review_state'],'facts_preserved':20,'html_sha256':report['content_sha256'],
                'provider_calls':0,'artifact':str((ARTIFACTS/f'{case}.html').relative_to(ROOT))})
        assert conn.execute('select count(*) as n from public.prepared_report_requests where workspace_id=%s',(ws,)).fetchone()['n'] == 2
        assert conn.execute('select count(*) as n from public.claim_checks where analysis_run_id=%s',(ctx.analysis_run_id,)).fetchone()['n'] == 40
        result = {'schema_version':1,'synthetic':True,'base_sha':'bfd45eb','observed_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'measured_at':datetime.now(UTC).isoformat(),'workspace_id':str(ws),'analysis_run_id':str(ctx.analysis_run_id),
            'snapshot_id':str(snapshot['id']),'source_ids':[str(source)],'fixture':{'sources':1,'documents':4,'critical_facts':20,
                'saved_passages':sum(d['passages'] for d in documents),'documents_detail':documents,'facts':expected},
            'machine_checks':{'scripted_verifier_calls':20,'quote_match_checks':20,'scripted_support_checks':20,'canonical_input_and_provenance':True},
            'cases':cases,'assertions':{'exact_content_citations_source_ids':True,'article_ABC_preserved':True,'qualifications_dates_preserved':True,
                'pending_warning_present':True,'historical_report_unchanged_after_review':True,'mas_inactive':True,'retrieval':'keyword','hybrid':'experimental; unused'},
            'limitations':['All documents, claims, model responses and review decisions are synthetic; no human precision or country coverage claim.',
                'Single cold first submission plus one second submission; no statistical latency distribution, equal-budget comparison or capacity test.',
                'Timer starts after completed preparation, excludes import/check/publication, and includes normal request submission, DB worker and final HTML retrieval.',
                'No fresh ingestion latency, discovery recall, report recall against real publications, live provider reliability or final report approval measured.',
                'Fixture selects 20 known facts directly; no analysis coverage events were written, so analysis_coverage is null and exhaustive analysis is unmeasured.',
                'Only local PostgreSQL network access permitted; scripted verifier calls are not provider calls. Benchmark workspace remains isolated for inspection.']}
        SUMMARY.with_suffix('.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
        md = '# Offline synthetic prepared-report benchmark — 10 November 2026\n\n'
        md += '**All fixture data, verifier responses and review decisions are synthetic. These results are not human precision or country coverage.**\n\n'
        md += f'Base `{result["base_sha"]}`; observed HEAD `{result["observed_head"]}`. Real local PostgreSQL; one source, four documents, 20 distinct critical facts; 20 exact-quote checks and 20 scripted support checks saved with canonical frozen evidence. Real job lease, immutable snapshot publication and normal report request queue. MAS inactive; keyword retrieval configured; hybrid experimental and unused.\n\n'
        md += '| Case | Submit to final HTML | Facts preserved | Captured state | Provider calls |\n|---|---:|---:|---|---:|\n'
        for c in cases:
            md += f'| {c["case"]} | {c["submit_to_final_html_seconds"]:.6f}s | 20/20 | {c["review_state"]} | 0 |\n'
        md += '\nBoth submissions were below 300 seconds. Exact factual text, Article A/B/C, dates, exceptions, quoted passages, finding IDs, source IDs, citation URLs and HTML hashes were asserted. First report retained its pending warning and immutable content after later scripted acceptances. `human_checked` describes captured database review state; no person labelled these facts and final approval was not performed.\n\n'
        md += 'Reproduce from repository root (loads only DB environment keys and refuses remote/non-55432 connections):\n\n```sh\nPYTHONPATH=.:tests /Users/natsim/Documents/dbsearch/.venv/bin/python eval/prepared_report_benchmark.py\n```\n\n'
        md += 'Each invocation creates a new isolated workspace and exactly two reports; it overwrites these dated output summaries. Private HTML, source fixtures and full captures: `reports/scheduled-evidence-20261110/benchmark/`. Portable JSON includes all 20 expected facts and database identities. No historical data or truth labels changed.\n\nLimitations:\n\n'+''.join('- '+x+'\n' for x in result['limitations'])
        md += '\nNext bounded step: coordinator may visually inspect the two saved HTML artifacts, then integrate the benchmark with focused runtime checks. A real prepared corpus and human labels require a separate explicit assignment.\n'
        SUMMARY.with_suffix('.md').write_text(md)
        print(json.dumps({'status':'passed','cases':cases,'summary':str(SUMMARY.with_suffix('.json'))},indent=2))


if __name__ == '__main__':
    main()
