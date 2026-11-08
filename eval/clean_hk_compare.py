"""Offline, read-only HK validation comparison. No runtime/provider calls.

Run after terminal outcome: python eval/clean_hk_compare.py --run-id UUID
  --validation-dir /path/to/validation --output-dir reports/UUID
Only aggregate metadata is exported; publisher text and provider errors are omitted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))
from run_live import cited_urls, load_records, report_finding_ids
from score_recall import canonical, load_items, score

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {'partial', 'failed', 'draft', 'reviewed', 'superseded'}


def require_terminal(row, outcome):
    if row['status'] not in TERMINAL or not row.get('finished_at'):
        raise ValueError('Run is not terminal with finished_at; scoring refused')
    if outcome.get('status') != row['status']:
        raise ValueError('Saved outcome and database status disagree; scoring refused')


def final_checklist(rows):
    latest = {}
    for row in rows:
        key = str(row['expected_source_id'])
        order = (int(row['gap_round']), str(row['created_at']))
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, row['status'])
    return dict(Counter(value[1] for value in latest.values()))


def initial_analysis_steps(steps):
    return [s for s in steps if s['role'] == 'analyst' and
            'passage_ids' in (s.get('input_refs') or {})]


def event_summary(events):
    counts = Counter(e['kind'] for e in events)
    starts = {e.get('id'): e for e in events if e['kind'] == 'model_started'}
    cor_ids = {ident for ident, e in starts.items()
               if e.get('role') == 'verifier' and str(e.get('prompt_version', '')).startswith('corroboration/')}
    cor_events = [e for e in events if e.get('id') in cor_ids]
    cor_errors = [e for e in cor_events if e['kind'] == 'model_error']
    cor_timeouts = sum(e.get('error_code') in ('timeout', 'timed_out', 'request_timeout') or
                       'timed out' in str(e.get('error', '')).lower() for e in cor_errors)
    unknown = [e for e in events if e['kind'] == 'model_error' and not e.get('usage_known', False)]
    return dict(counts=dict(counts),
        corroboration_model_calls=dict(requested=len(cor_ids),
            completed=sum(e['kind'] == 'model_completed' for e in cor_events),
            errors=len(cor_errors), explicitly_reported_timeouts=cor_timeouts,
            prompt_version_instrumented=any('prompt_version' in e for e in starts.values())),
        provider_tokens_known=sum(int(e.get('tokens_in', 0)) + int(e.get('tokens_out', 0))
            for e in events if e['kind'] == 'model_completed') + sum(int(e.get('charged_or_reserved', 0))
            for e in events if e['kind'] == 'model_error' and e.get('usage_known')),
        unknown_usage_reserved_tokens=sum(int(e.get('charged_or_reserved', 0)) for e in unknown),
        unknown_usage_calls=len(unknown), exa_requests=counts['exa_requested'],
        exa_completed=counts['exa_completed'], exa_errors=counts['exa_error'],
        exa_timeouts=counts['exa_timeout'], model_requests=counts['model_started'],
        api_calls=counts['exa_requested'] + counts['model_started'])


def publication_summary(urls, items, scope):
    urls = list(urls)
    recall = score(items, urls, **scope)
    # score each item with the same scope so dates/markets and explicit aliases stay identical.
    ids = [item.id for item in items if score([item], urls, **scope)['all'].found]
    eligible = [item.id for item in items if score([item], [], **scope)['all'].total]
    return dict(distinct_publications=len({canonical(u) for u in urls if u}),
        recall={key: dict(found=value.found, total=value.total) for key, value in recall.items()},
        benchmark_ids=ids, missing_benchmark_ids=sorted(set(eligible) - set(ids)))


def measure(conn, run_id, outcome, events):
    from mira.pg_store import load_run
    from mira.runner import usage_by_role
    ctx = load_run(conn, run_id)
    row = conn.execute('select status, started_at, finished_at from public.analysis_runs where id=%s',
                       (run_id,)).fetchone()
    require_terminal(row, outcome)
    workspace_runs = conn.execute('select count(*) as n from public.analysis_runs where workspace_id=%s',
                                  (ctx.workspace_id,)).fetchone()['n']
    if workspace_runs != 1:
        raise ValueError('Acquisition attribution requires exactly one run in the workspace')
    steps = conn.execute('select step_no, role, gap_round, status, model, tokens_in, tokens_out, input_refs, output_refs '
                         'from public.agent_steps where analysis_run_id=%s order by step_no', (run_id,)).fetchall()
    versions = conn.execute('select source_url, extraction_status from public.document_versions where workspace_id=%s',
                            (ctx.workspace_id,)).fetchall()
    report = conn.execute('select evidence_snapshot from public.reports where analysis_revision_id=%s '
                          'order by report_version limit 1', (ctx.analysis_revision_id,)).fetchone()
    records = load_records(conn, ctx.user_id, run_id)
    snapshot = report['evidence_snapshot'] if report else None
    ids = report_finding_ids(snapshot) if snapshot else []
    urls = cited_urls(ids, records)
    scope = dict(jurisdictions=ctx.brief.jurisdictions, period_start=ctx.brief.period_start,
                 period_end=ctx.brief.period_end, as_of_date=ctx.brief.as_of_date)
    if list(ctx.brief.jurisdictions) != ['HK']:
        raise ValueError('This helper is scoped to HK only')
    items = load_items(ROOT / 'eval/m0_ground_truth.csv')
    logs = [log for s in steps for log in (s['output_refs'] or {}).get('fetch_log', [])]
    coverage = conn.execute('select expected_source_id, gap_round, created_at, status from public.coverage_results '
                            'where analysis_run_id=%s', (run_id,)).fetchall()
    cor = conn.execute('select result from public.corroboration_assessments where analysis_run_id=%s order by sequence',
                       (run_id,)).fetchall()
    assessments = [r['result'] for r in cor]
    stops = Counter(reason for a in assessments for reason in a.get('stop_reasons', []))
    usage = usage_by_role(conn, run_id)
    journal = event_summary(events)
    initial = initial_analysis_steps(steps)
    corroboration_steps = [s for s in steps if (s.get('input_refs') or {}).get('purpose') == 'corroboration']
    writer = [s for s in steps if s['role'] == 'writer']
    writer_llm = any(s['status'] == 'succeeded' and s['model'] for s in writer)
    sources = conn.execute("select source_key,is_active from public.sources where workspace_id=%s and source_key='mas'",
                           (ctx.workspace_id,)).fetchall()
    browser = [log for log in logs if log.get('acquisition_method') == 'live_browser']
    mas_fetches = sum('mas.gov.sg' in log.get('url', '') for log in logs)
    mas_versions = sum('mas.gov.sg' in v['source_url'] for v in versions)
    return dict(run_id=str(run_id), status=row['status'], started_at=row['started_at'], finished_at=row['finished_at'],
        brief=ctx.brief.model_dump(mode='json'), workspace_run_count=workspace_runs,
        saved_versions=len(versions), acquired=publication_summary([v['source_url'] for v in versions], items, scope),
        stored_text=publication_summary([v['source_url'] for v in versions if v['extraction_status'] in ('complete','partial')], items, scope),
        cited=publication_summary(urls, items, scope) if snapshot else None, report_exists=bool(snapshot),
        report_facts=sum(not records.findings[i].is_inference for i in ids),
        report_inferences=sum(records.findings[i].is_inference for i in ids),
        unresolved=len(snapshot.get('unresolved_finding_ids', [])) if snapshot else None,
        checklist=final_checklist(coverage), step_statuses=dict(Counter(s['status'] for s in steps)),
        recorded_tokens=sum(int(u['tokens_in']) + int(u['tokens_out']) for u in usage),
        recorded_cost_estimate_usd=float(sum(u['cost_usd'] for u in usage)), validation_events=journal,
        corroboration=dict(steps=len(corroboration_steps),
            step_statuses=dict(Counter(s['status'] for s in corroboration_steps)),
            completed_steps=sum(s['status'] == 'succeeded' for s in corroboration_steps),
            failed_steps=sum(s['status'] == 'failed' for s in corroboration_steps),
            assessments=len(assessments), statuses=dict(Counter(a.get('status', 'unknown') for a in assessments)),
            persisted_reserved_tokens=sum(int(a.get('reserved_tokens', 0)) for a in assessments),
            assessment_errors=stops['assessment_failed'], time_limit_stops=stops['time_limit'],
            completed_assessments=sum('assessment_failed' not in a.get('stop_reasons', []) and
                'incomplete_assessment' not in a.get('stop_reasons', []) for a in assessments)),
        browser=dict(actual_attempts=sum(log.get('request_sent', True) and log.get('outcome') not in ('refused','reused') for log in browser),
                     log_entries=len(browser), saved=sum(log.get('outcome') == 'saved' for log in browser)),
        mas=dict(active=any(s['is_active'] for s in sources), fetches=mas_fetches, versions=mas_versions,
                 zero=not any(s['is_active'] for s in sources) and mas_fetches == mas_versions == 0),
        writer=dict(llm_succeeded=writer_llm, deterministic_fallback=bool(snapshot) and not writer_llm),
        clean=dict(unresumed=journal['counts'].get('run_resumed', 0) == 0 and not outcome.get('resumed', False),
                   run_started_events=journal['counts'].get('run_started', 0), initial_analysis_steps=len(initial),
                   initial_analysis_once=len(initial) == 1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', type=UUID, required=True)
    parser.add_argument('--validation-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads((args.validation_dir / 'manifest.json').read_text())
    outcome = json.loads((args.validation_dir / 'outcome.json').read_text())
    if manifest['run_id'] != str(args.run_id):
        raise ValueError('Manifest run ID mismatch')
    events = [json.loads(line) for line in (args.validation_dir / 'events.jsonl').read_text().splitlines() if line.strip()]
    if any(e.get('run_id') not in (None, str(args.run_id)) for e in events):
        raise ValueError('Validation journal contains another run')
    from mira.config import load_env
    from mira.db import connect
    from psycopg.conninfo import conninfo_to_dict
    load_env(ROOT / '.env', keys={'MIRA_WORKER_DATABASE_URL'})
    load_env(Path('/Users/natsim/Documents/dbsearch/.env'), keys={'MIRA_WORKER_DATABASE_URL'})
    # Refuse a remote database and never include connection values in output/errors.
    dsn = os.environ.get('MIRA_WORKER_DATABASE_URL', '')
    try:
        host = conninfo_to_dict(dsn).get('host', '')
    except Exception:
        raise ValueError('Invalid local database configuration') from None
    if host not in ('localhost', '127.0.0.1', '::1') and not host.startswith('/'):
        raise ValueError('Only local PostgreSQL is allowed')
    with connect(dsn) as conn:
        conn.execute('begin read only')
        current = measure(conn, args.run_id, outcome, events)
        conn.rollback()
    historical = json.loads((ROOT / 'eval/evidence/2026-11-08-hk-exa-run-fe65444d.json').read_text())
    refs = {name: historical[key] for name, key in [('fe65444d','current'), ('a88dd20e','previous_failed'), ('e2fda30f','earlier_local')]}
    if current['brief'] != historical['brief']:
        raise ValueError('Historical comparison requires the same HK brief and date scope')
    comparisons = {}
    for name, ref in refs.items():
        comparisons[name] = dict(reference=ref,
            acquired_delta=current['acquired']['recall']['all']['found'] - ref['acquisition_recall']['all']['found'],
            newly_acquired=sorted(set(current['acquired']['benchmark_ids']) - set(ref['acquired_benchmark_ids'])),
            not_reacquired=sorted(set(ref['acquired_benchmark_ids']) - set(current['acquired']['benchmark_ids'])))
    result = dict(current=current, historical_comparisons=comparisons,
        source_sha=manifest.get('git_sha'), budget=manifest.get('budget'), models=manifest.get('models'),
        human_precision='unlabelled; no review sign-off',
        limitations=['Historical observations, not a controlled equal-budget or causal feature comparison.',
            'e2fda30f saved 32 versus 30 allowed; a88dd20e had no report; fe65444d was resumed.',
            'Provider reservations are not measured usage; cost excludes Exa and unknown provider usage.',
            'Journal and persisted corroboration reservations are separate provenance views; do not add them as disjoint costs.',
            'Assessment statuses are model checks, not human precision labels.',
            'Corroboration time_limit_stops are persisted stop reasons, not independently timed provider-call counts.'])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / 'clean-hk-comparison.json'
    output.write_text(json.dumps(result, indent=2, default=str) + '\n')
    print(str(output))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never print arbitrary DB/provider errors, DSNs, publisher text or credentials.
        print(f'Offline comparison refused ({type(exc).__name__}); check terminal artifacts and local configuration.', file=sys.stderr)
        raise SystemExit(2)
