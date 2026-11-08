"""Offline integrity checks; no provider calls or database required."""
import unittest
from datetime import date
from clean_hk_compare import final_checklist, event_summary, require_terminal, publication_summary, initial_analysis_steps
from run_live import Evidence, Finding, RunRecords, cited_urls, report_finding_ids
from score_recall import Item


class CleanHKCompareTests(unittest.TestCase):
    def test_rewrites_do_not_count_as_initial_analysis(self):
        steps = [dict(role='analyst', input_refs={'passage_ids': ['p']}),
                 dict(role='analyst', input_refs={'finding_id': 'f', 'verifier_reason': 'revise'})]
        self.assertEqual(len(initial_analysis_steps(steps)), 1)

    def test_latest_round_per_expected_source(self):
        rows = [dict(expected_source_id='a', gap_round=0, created_at='1', status='missing'),
                dict(expected_source_id='b', gap_round=0, created_at='1', status='found'),
                dict(expected_source_id='a', gap_round=2, created_at='2', status='found')]
        self.assertEqual(final_checklist(rows), {'found': 2})

    def test_corroboration_calls_join_prompt_version_from_start(self):
        events = [dict(kind='model_started', id='c', role='verifier', prompt_version='corroboration/2'),
                  dict(kind='model_completed', id='c', tokens_in=10, tokens_out=2),
                  dict(kind='model_started', id='v', role='verifier', prompt_version='verifier/3'),
                  dict(kind='model_completed', id='v', tokens_in=5, tokens_out=2),
                  dict(kind='model_started', id='e', role='verifier', prompt_version='corroboration/2'),
                  dict(kind='model_error', id='e', error_code='timeout', usage_known=False, charged_or_reserved=30)]
        cor = event_summary(events)['corroboration_model_calls']
        self.assertEqual(cor, dict(requested=2, completed=1, errors=1,
                                  explicitly_reported_timeouts=1, prompt_version_instrumented=True))

    def test_unknown_usage_is_reservation_and_known_failure_is_measured(self):
        events = [dict(kind='model_completed', tokens_in=10, tokens_out=3),
                  dict(kind='model_error', usage_known=False, charged_or_reserved=99),
                  dict(kind='model_error', usage_known=True, charged_or_reserved=7)]
        summary = event_summary(events)
        self.assertEqual(summary['provider_tokens_known'], 20)
        self.assertEqual(summary['unknown_usage_reserved_tokens'], 99)
        self.assertEqual(summary['unknown_usage_calls'], 1)

    def test_terminal_requires_finish_and_matching_outcome(self):
        for row, outcome in [(dict(status='running', finished_at='x'), {'status': 'running'}),
                             (dict(status='partial', finished_at=None), {'status': 'partial'}),
                             (dict(status='draft', finished_at='x'), {'status': 'partial'})]:
            with self.assertRaises(ValueError):
                require_terminal(row, outcome)
        require_terminal(dict(status='partial', finished_at='x'), {'status': 'partial'})

    def test_scope_aliases_and_supporting_facts(self):
        url = 'https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC1'
        alias = 'https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC1&lang=EN'
        records = RunRecords({'i': Finding('', '', True), 'f': Finding('', '', False)},
                             {'f': [Evidence(alias, '', '')]}, {'i': ['f']})
        snapshot = {'sections': [{'sentences': [dict(structural=False, finding_ids=['i'])]}]}
        urls = cited_urls(report_finding_ids(snapshot), records)
        items = [Item('HK', 'regulatory', 'fetchable', url, ('HK',), date(2026, 1, 1)),
                 Item('SG', 'regulatory', 'fetchable', alias, ('SG',), date(2026, 1, 1))]
        result = publication_summary(urls + urls, items, dict(jurisdictions=['HK'],
            period_start=date(2025, 11, 4), period_end=date(2026, 11, 4), as_of_date=date(2026, 11, 4)))
        self.assertEqual(result['benchmark_ids'], ['HK'])
        self.assertEqual(result['recall']['all'], {'found': 1, 'total': 1})
        self.assertEqual(result['distinct_publications'], 1)


if __name__ == '__main__':
    unittest.main()
