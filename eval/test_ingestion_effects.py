"""Offline effects. Run pytest -s, or --retained-run PATH for saved trace scoring."""
from collections import Counter
from datetime import date
import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import uuid4

from mira.agents import scout as module
from mira.agents.scout import WebScout, _ScoutRun
from mira.contracts import Brief, LinkSelection
from mira.extract import Link
from eval.score_recall import Item, load_items, score


def summarize_retained(audit, config, snapshot, items):
    """Keep missing discovery unknown; never interpret machine output as labels."""
    brief = config['brief']
    scope = dict(jurisdictions=brief['jurisdictions'], period_start=date.fromisoformat(brief['period_start']),
                 period_end=date.fromisoformat(brief['period_end']), as_of_date=date.fromisoformat(brief['as_of_date']))
    eligible = [item for item in items if score([item], [], **scope)['all'].total]
    ids = {item.id for item in eligible}
    traces = [t for t in audit['traces'] if t['id'] in ids]
    def recall(urls):
        return {k: dict(found=v.found, total=v.total) for k, v in score(eligible, urls).items()}
    stages = []
    for t in traces:
        presented = [dict(rank=c.get('rank'), selected=c.get('selected'),
                          remaining_allowance_start=r.get('remaining_allowance_start'))
                     for s in t['scouts'] for r in s.get('rounds', []) for c in r.get('candidates', [])
                     if c.get('stage') == 'presented']
        stages.append(dict(id=t['id'], discovery='observed' if any(s.get('discovery') for s in t['scouts']) else 'unknown',
                           presented=presented, saved_versions=len(t['versions']), analyst_passages=len(t['analyst_input']),
                           supporting_findings=len(t['supporting_findings']), cited=t['cited'],
                           verifier_verdicts=dict(Counter(v['verdict'] for v in t['verifier']))))
    return dict(run_id=audit['run_id'], scope=brief,
                acquisition_recall=recall([v['source_url'] for t in traces for v in t['versions']]),
                citation_recall=recall(audit['cited_urls']),
                checklist_statuses=dict(Counter(r['status'] for r in snapshot['coverage'])), trace_items=stages,
                untraced_eligible_items=sorted(ids - {t['id'] for t in traces}),
                caveats=['Missing discovery records are unknown; failed-scout partial telemetry was not retained.',
                         'Checklist statuses/verifier verdicts are machine outputs, not human labels.',
                         'Historical acquisition predates fixes and exceeded its requested allowance.'])


def test_saved_stages_scope_aliases_and_checklist_remain_separate():
    url = 'https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260101-1-EN'
    pdf = 'https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260101-1-EN/20260101-1-EN.pdf'
    items = [Item('saved', 'regulatory', 'fetchable', url, ('HK',), date(2026, 1, 1)),
             Item('missing', 'regulatory', 'fetchable', 'https://example.org/missing', ('HK',), date(2026, 1, 1)),
             Item('sg', 'regulatory', 'fetchable', 'https://example.org/sg', ('SG',), date(2026, 1, 1)),
             Item('future', 'regulatory', 'fetchable', 'https://example.org/future', ('HK',), date(2027, 1, 1))]
    def trace(id_, versions):
        return dict(id=id_, versions=versions, scouts=[], analyst_input=[], supporting_findings=[], verifier=[], cited=False)
    audit = dict(run_id='offline', traces=[trace('saved', [dict(source_url=pdf)]), trace('missing', [])], cited_urls=[])
    config = dict(brief=dict(jurisdictions=['HK'], period_start='2025-11-04', period_end='2026-11-04', as_of_date='2026-11-04'))
    result = summarize_retained(audit, config, dict(coverage=[dict(status='found'), dict(status='no_change')]), items)
    assert result['acquisition_recall']['all'] == dict(found=1, total=2)
    assert result['citation_recall']['all'] == dict(found=0, total=2)
    assert result['checklist_statuses'] == dict(found=1, no_change=1)
    assert result['trace_items'][1]['discovery'] == 'unknown'
    assert result['untraced_eligible_items'] == []


def test_candidate_retention_equal_document_allowance_effect(monkeypatch):
    """Retention ablation: scripted attempts, no real save or report/live recall.

    Equal document allowance/round ceiling; extra selection work means this is
    not an equal token/time comparison. Counterfactual discards after selection.
    """
    cap = module.MAX_LINKS_SHOWN
    count = cap + 3
    links = [Link(f'https://publisher.example/publication/{i}', 'AML publication', '', date(2026, 1, 1), 'fixture')
             for i in range(count)]
    brief = Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2025, 11, 4),
                  period_end=date(2026, 11, 4), as_of_date=date(2026, 11, 4), plan_requires_approval=False)
    ctx = SimpleNamespace(workspace_id=uuid4(), analysis_run_id=uuid4(), user_id=uuid4(), brief=brief)
    task = SimpleNamespace(max_documents=count, question='AML publications', role='regulatory_scout')
    def select(*args, **kwargs):
        labels = re.findall(r'<link label="([^"]+)"', kwargs['user'])
        return SimpleNamespace(output=LinkSelection(link_labels=labels, notes=None), model='offline-script', tokens_in=0, tokens_out=0)
    monkeypatch.setattr(module, 'call_checked', select)
    def measure(discard):
        run = _ScoutRun(WebScout('unused', None, SimpleNamespace(), links_per_round=cap), None, ctx, uuid4(), task)
        run.candidates = list(links)
        attempted = []
        def acquire(url, link):
            assert run.allowance > 0
            attempted.append(url)
            run.seen.add(url)
            run.allowance -= 1
        monkeypatch.setattr(run, '_fetch_document', acquire)
        for _ in range(2):
            if not run.candidates or not run.allowance:
                break
            run._select_and_fetch()
            if discard:
                run.candidates.clear()  # Explicit legacy discard ablation; shared ranking.
        return dict(attempted=len(set(attempted)), remaining=run.allowance, selection_calls=len(run.selection_diagnostics))
    before, after = measure(True), measure(False)
    assert before == dict(attempted=cap, remaining=3, selection_calls=1)
    assert after == dict(attempted=count, remaining=0, selection_calls=2)
    print(json.dumps(dict(fixture='candidate_retention_ablation', document_allowance=count,
                          max_selection_rounds=2, legacy_discard=before, retained=after), sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-run', type=Path, required=True)
    args = parser.parse_args()
    def read(name):
        return json.loads((args.retained_run / name).read_text())
    print(json.dumps(summarize_retained(read('telemetry-audit.json'), read('validation-config.json'),
                                      read('validation-result.json')['snapshot'],
                                      load_items(Path(__file__).with_name('m0_ground_truth.csv'))), indent=2))


if __name__ == '__main__':
    main()
