"""Controlled offline fixtures; these results are not live-quality evidence."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pytest

import quality_preflight as q


class QualityPreflightTests(unittest.TestCase):
    def plan(self):
        return dict(scope=copy.deepcopy(q.SCOPE), models=copy.deepcopy(q.MODELS),
                    sources=[dict(source_key='mas', is_active=False)],
                    feature_flags={'hybrid': False, 'original_storage': False},
                    budget=copy.deepcopy(q.CAPS))

    def retained(self):
        return dict(kind='controlled_fixture', run_id='fixture', scope=copy.deepcopy(q.SCOPE),
                    status='partial', started_at='2026-11-08T00:00:00+00:00',
                    finished_at='2026-11-08T00:01:00+00:00', outcome_status='partial',
                    budget=copy.deepcopy(q.CAPS), models=copy.deepcopy(q.MODELS),
                    usage=dict(documents=1, actual_tokens=20, reserved_tokens=10, exa_searches=0),
                    mas=dict(active=False, fetches=0, versions=0), acquired_urls=[], cited_urls=[],
                    passages=[dict(id='p1', status='analysed'), dict(id='p2', status='deferred')],
                    findings=[dict(id='f1', primary_verification='supported', corroboration='primary_source_only')],
                    claims=[dict(claim='A claim', cited_passage='A passage', supporting_quote='A quote')])

    def test_preflight_frozen_and_no_new_flags(self):
        p = self.plan()
        self.assertFalse(q.preflight(p, p)['authorized'])
        for key in ('scope', 'models', 'feature_flags'):
            changed = copy.deepcopy(p)
            changed[key]['jurisdictions' if key == 'scope' else 'unexpected'] = True
            with self.assertRaises(ValueError):
                q.preflight(changed, p)
        for value in (0, -1, 31):
            changed = copy.deepcopy(p)
            changed['budget']['max_fetched_documents'] = value
            with self.assertRaises(ValueError):
                q.preflight(changed, p)
        p['sources'][0]['is_active'] = True
        with self.assertRaises(ValueError):
            q.preflight(p, p)

    def test_compare_and_dispositions(self):
        r = self.retained()
        summary = q.compare(r, r)
        self.assertEqual(summary['acquired_delta'], 0)
        self.assertEqual(summary['current']['passages'],
                         dict(candidate=2, analysed=1, failed=0, deferred=1))
        self.assertEqual(summary['current']['corroboration']['independent_support'], 0)
        self.assertEqual(summary['current']['actual_tokens'], 20)
        self.assertEqual(summary['current']['reserved_tokens'], 10)
        self.assertIsNone(summary['human_precision'])

    def test_reject_scope_terminal_forged_counts_and_bounds(self):
        for mutate in (
            lambda r: r['scope'].update(period_end='2026-10-26'),
            lambda r: r.update(status='running'),
            lambda r: r.update(finished_at=None),
            lambda r: r.update(passage_counts={'candidate': 300}),
            lambda r: r['usage'].update(documents=31),
            lambda r: r['usage'].update(actual_tokens=600000),
            lambda r: r.update(finished_at='2026-11-08T01:00:00+00:00'),
            lambda r: r['findings'][0].update(corroboration='independent_support'),
        ):
            r = self.retained()
            mutate(r)
            with self.assertRaises(ValueError):
                q.compare(r, self.retained())

    def test_historical_saved_summary(self):
        old = json.loads(q.BASELINE.read_text())
        summary = q.measure(old)
        self.assertEqual(summary['acquired']['recall']['all']['found'], 6)
        self.assertEqual(summary['cited']['recall']['all']['found'], 5)
        self.assertEqual(summary['corroboration']['inconclusive'], 7)
        self.assertIsNone(summary['passages'])
        self.assertEqual(q.compare(old, old)['acquired_delta'], 0)
        new = self.retained()
        new['kind'] = 'live_retained'
        self.assertEqual(q.compare(new, old)['acquired_delta'], -6)
        forged = copy.deepcopy(old)
        forged['current']['acquired']['recall']['all']['found'] = 18
        with self.assertRaises(ValueError):
            q.measure(forged)
        with self.assertRaises(ValueError):
            q.compare(self.retained(), old)  # fixtures cannot masquerade as live comparison

    def test_worksheet_blinded_and_never_overwrites_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'blind.csv'
            q.worksheet(self.retained()['claims'], path)
            rows = list(csv.DictReader(path.open()))
            self.assertEqual(rows[0]['arm'], 'blind')
            self.assertEqual(rows[0]['label'], '')
            self.assertNotIn('corroboration', path.read_text())
            with self.assertRaises(FileExistsError):
                q.worksheet([], path)

    def test_import_has_no_runtime_or_provider_imports(self):
        code = 'import sys; import quality_preflight; assert not any(n.startswith(("mira", "openai", "httpx")) for n in sys.modules)'
        subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent, check=True)

    def test_secret_mapping_refused_without_echo(self):
        p = self.plan()
        p['api_key'] = 'secret-example'
        with self.assertRaisesRegex(ValueError, '^Sensitive input refused$'):
            q.preflight(p, p)


if __name__ == '__main__':
    unittest.main()


def test_no_report_is_not_zero_citation_recall():
    r = QualityPreflightTests().retained()
    r['report_exists'] = False
    result = q.compare(r, r)
    assert result['current']['cited'] is None
    assert not result['current']['report_exists']
    assert result['cited_delta'] is None
    r['cited_urls'] = ['https://example.com/forged']
    with pytest.raises(ValueError):
        q.measure(r)
