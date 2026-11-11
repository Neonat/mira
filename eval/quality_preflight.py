"""Offline proposal, retained-result comparison and blinded precision worksheet.

No runner, environment, database or network access. Inputs are local JSON exports;
preflight emits a proposal requiring fresh bounded authorization, never executes it.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.json'
SCOPE = dict(topic='AML/CFT', jurisdictions=['HK'], period_start='2025-11-04',
             period_end='2026-11-04', as_of_date='2026-11-04')
MODELS = dict(planner='openai:gpt-5.4', regulatory_scout='openai:gpt-5.4-mini',
              industry_scout='openai:gpt-5.4-mini', analyst='openai:gpt-5.4',
              verifier='openai:gpt-5.4', writer='openai:gpt-5.4-mini')
CAPS = dict(max_fetched_documents=30, max_llm_tokens=600000,
            max_run_minutes=25, max_exa_searches=6)
COR = ('independent_support', 'primary_source_only', 'conflicting', 'inconclusive', 'not_checked')
PRIMARY = ('supported', 'partially_supported', 'unsupported', 'contradicted', 'not_checked')


def safe_input(value):
    """Refuse credential-shaped input; callers supply settings, never credentials."""
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r'(api.?key|secret|password|credential|authorization|database_url|access_token)', key, re.I):
                raise ValueError('Sensitive input refused')
            safe_input(item)
    elif isinstance(value, list):
        for item in value:
            safe_input(item)
    elif isinstance(value, str) and re.search(r'(sk-[A-Za-z0-9]|Bearer\s|://[^/\s]+:[^/\s]+@)', value):
        raise ValueError('Sensitive input refused')


def scope(value):
    actual = {key: value.get(key) for key in SCOPE}
    if actual != SCOPE:
        raise ValueError('Frozen HK scope mismatch')
    return actual


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid nonnegative accounting value')
    return value


def budget(value):
    for key, cap in CAPS.items():
        if not 0 < number(value[key]) <= cap:
            raise ValueError('Budget outside declared caps')
    return {key: value[key] for key in CAPS}


def preflight(planned, current):
    safe_input(planned)
    safe_input(current)
    scope(planned['scope'])
    scope(current['scope'])
    if planned['models'] != MODELS or current['models'] != MODELS:
        raise ValueError('Role models changed')
    for key in ('sources', 'feature_flags'):
        if planned[key] != current[key]:
            raise ValueError('Source permissions or flags changed; separate explicit decision required')
    if not isinstance(planned['feature_flags'], dict) or any(type(v) is not bool for v in planned['feature_flags'].values()):
        raise ValueError('Explicit boolean feature flag mapping required')
    mas = [s for s in planned['sources'] if s.get('source_key') == 'mas']
    if len(mas) != 1 or mas[0].get('is_active') is not False:
        raise ValueError('MAS must be explicitly inactive')
    limits = budget(planned['budget'])
    return dict(authorized=False, state='proposal_requires_new_bounded_authorization', scope=SCOPE,
                models=MODELS, sources=[{k: s[k] for k in ('source_key', 'is_active', 'permitted_operations', 'live_browser') if k in s} for s in planned['sources']], feature_flags=planned['feature_flags'],
                budget=limits, hard_caps=CAPS, executions=1, continuation=False,
                acceptance='Terminal saved export plus blinded human labels; model checks cannot certify quality',
                measurement='Acquire and cite recall separately; all passage/finding dispositions retained',
                offline_compare_command='python eval/quality_preflight.py compare --current RETAINED.json --baseline BASELINE.json')


def publication(urls):
    # Lazy import keeps preflight/import completely independent of runtime modules.
    # Reuse the canonical scorer (including official publication aliases), never prompts.
    try:
        from score_recall import load_items, score, canonical
    except ModuleNotFoundError:
        from eval.score_recall import load_items, score, canonical
    items = load_items(ROOT / 'eval/m0_ground_truth.csv')
    criteria = dict(jurisdictions=SCOPE['jurisdictions'], **{
        k: date.fromisoformat(SCOPE[k]) for k in ('period_start', 'period_end', 'as_of_date')})
    scores = score(items, urls, **criteria)
    ids = [i.id for i in items if score([i], urls, **criteria)['all'].found]
    eligible = [i.id for i in items if score([i], [], **criteria)['all'].total]
    return dict(recall={k: dict(found=v.found, total=v.total) for k, v in scores.items()},
                benchmark_ids=ids, missing_benchmark_ids=sorted(set(eligible)-set(ids)))


def saved_publication(value):
    """Validate retained aggregate counts; raw acquisition membership is not reverified."""
    try:
        from score_recall import load_items
    except ModuleNotFoundError:
        from eval.score_recall import load_items
    items = {i.id: i for i in load_items(ROOT / 'eval/m0_ground_truth.csv')}
    ids = value['benchmark_ids']
    if len(set(ids)) != len(ids) or any(i not in items for i in ids):
        raise ValueError('Invalid retained benchmark identifiers')
    result = publication([items[i].url for i in ids])
    if result != {k: value[k] for k in result}:
        raise ValueError('Retained recall counts disagree with benchmark identifiers')
    return result


def dispositions(rows, statuses):
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate disposition identity')
    result = dict.fromkeys(statuses, 0)
    for row in rows:
        if row['status'] not in result:
            raise ValueError('Unknown disposition')
        result[row['status']] += 1
    return result


def measure(data):
    legacy = 'current' in data
    if not legacy and data.get('kind') not in ('controlled_fixture', 'live_retained'):
        raise ValueError('Explicit retained-result kind required')
    r = data['current'] if legacy else data
    scope(r['brief'] if legacy else r['scope'])
    if r['status'] not in ('partial', 'failed', 'draft', 'reviewed', 'superseded') or not r.get('finished_at'):
        raise ValueError('Terminal run required')
    outcome = data['outcome']['status'] if legacy else r['outcome_status']
    if outcome != r['status']:
        raise ValueError('Terminal outcome mismatch')
    seconds = (datetime.fromisoformat(r['finished_at']) - datetime.fromisoformat(r['started_at'])).total_seconds()
    b = budget(dict(data['budget'], max_exa_searches=data['manifest']['exa']['max_queries']) if legacy else r['budget'])
    models = data['models'] if legacy else r['models']
    if models != MODELS:
        raise ValueError('Role model mismatch')
    mas = r['mas']
    if mas['active'] is not False or mas['fetches'] != 0 or mas['versions'] != 0:
        raise ValueError('MAS inactive and zero acquisition required')
    if legacy:
        events = r['validation_events']
        usage = dict(documents=r['saved_versions'], actual_tokens=events['provider_tokens_known'],
                     reserved_tokens=events['unknown_usage_reserved_tokens'], exa_searches=events['exa_requests'])
        acquired, cited = saved_publication(r['acquired']), saved_publication(r['cited']) if r['cited'] else None
        passages, primary = None, None
        cor = dict.fromkeys(COR, 0)
        for key, count in r['corroboration']['statuses'].items():
            if key not in cor:
                raise ValueError('Unknown retained corroboration status')
            cor[key] = number(count)
        if sum(cor.values()) != r['corroboration']['assessments']:
            raise ValueError('Retained assessment counts disagree')
    else:
        safe_input(data)
        usage = r['usage']
        if r.get('report_exists') is False and r['cited_urls']:
            raise ValueError('Absent report cannot have cited URLs')
        acquired = publication(r['acquired_urls'])
        cited = publication(r['cited_urls']) if r.get('report_exists', True) else None
        passages = dispositions(r['passages'], ('analysed', 'failed', 'deferred'))
        passages = dict(candidate=len(r['passages']), **passages)
        if 'passage_counts' in r and r['passage_counts'] != passages:
            raise ValueError('Passage totals disagree with dispositions')
        primary = dispositions([dict(id=f['id'], status=f['primary_verification']) for f in r['findings']], PRIMARY)
        cor = dispositions([dict(id=f['id'], status=f['corroboration']) for f in r['findings']], COR)
        for f in r['findings']:
            if f['corroboration'] == 'independent_support' and not f.get('independence_evidence_refs'):
                raise ValueError('Independent status requires retained independence evidence references')
    for value in usage.values():
        if number(value) != int(value):
            raise ValueError('Accounting counts must be integers')
    calls = r['validation_events']['corroboration_model_calls'] if legacy else r.get('corroboration_calls')
    if calls is not None:
        calls = {key: number(calls[key]) for key in ('requested', 'completed', 'errors', 'explicitly_reported_timeouts')}
        if calls['requested'] != calls['completed'] + calls['errors'] or calls['explicitly_reported_timeouts'] > calls['errors']:
            raise ValueError('Corroboration call accounting disagrees')
    if (usage['documents'] > b['max_fetched_documents'] or
        usage['actual_tokens'] + usage['reserved_tokens'] > b['max_llm_tokens'] or
        usage['exa_searches'] > b['max_exa_searches'] or seconds < 0 or seconds > b['max_run_minutes']*60 + 1):
        raise ValueError('Run exceeds bounded accounting caps')
    return dict(run_id=r['run_id'], kind='live_retained' if legacy else r['kind'], status=r['status'],
                scope=SCOPE, budget=b, models=models, elapsed_seconds=seconds,
                report_exists=r.get('report_exists', cited is not None),
                **usage, acquired=acquired, cited=cited, passages=passages,
                primary_verification=primary, corroboration=cor,
                corroboration_calls=calls,
                provenance='retained aggregate; no raw membership recheck' if legacy else 'supplied retained rows; no authenticity certification',
                missing_measurements=['passage dispositions', 'primary verification dispositions'] if legacy else [])


def compare(current, baseline):
    a, b = measure(current), measure(baseline)
    if a['kind'] != b['kind']:
        raise ValueError('Controlled fixtures and live results must remain separate')
    def delta(key):
        return None if a[key] is None or b[key] is None else a[key]['recall']['all']['found']-b[key]['recall']['all']['found']
    return dict(current=a, baseline=b, acquired_delta=delta('acquired'), cited_delta=delta('cited'),
                comparison='same declared budget; observational, not causal' if a['budget']==b['budget'] else 'capacity test; unequal declared budgets',
                human_precision=None, caveats=['Model verification/corroboration statuses are not human labels.',
                'Reserved tokens are not measured provider usage; no cost or quality certification.',
                'Elapsed time includes partial/failed outcomes; one second terminal persistence tolerance.'])


def worksheet(claims, path):
    try:
        from precision import ClaimRow, sample, write_worksheet
    except ModuleNotFoundError:
        from eval.precision import ClaimRow, sample, write_worksheet
    safe_input(claims)
    # Exclusive creation preserves all previous human labels, even for an empty sample.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x'):
        pass
    rows = [ClaimRow(f'S{i:04d}', 'blind', r['claim'], r['cited_passage'], r['supporting_quote'])
            for i, r in enumerate(claims, 1)]
    write_worksheet(sample(rows, 30), path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('preflight')
    p.add_argument('--planned', type=Path, required=True)
    p.add_argument('--current-settings', type=Path, required=True)
    p = sub.add_parser('compare')
    p.add_argument('--current', type=Path, required=True)
    p.add_argument('--baseline', type=Path, default=BASELINE)
    p = sub.add_parser('worksheet')
    p.add_argument('--claims', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    read = lambda path: json.loads(path.read_text())
    if args.command == 'preflight':
        result = preflight(read(args.planned), read(args.current_settings))
    elif args.command == 'compare':
        result = compare(read(args.current), read(args.baseline))
    else:
        worksheet(read(args.claims), args.output)
        result = dict(worksheet='created', human_precision=None)
    safe_input(result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError):
        print('Offline validation refused; check schema, scope, terminal evidence and caps.', file=sys.stderr)
        raise SystemExit(2)
