"""Offline validation reports preserve caveats and export only allowlisted metadata."""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys

import pytest

from eval.mixed_retrieval_report import render_report


PILOT = Path(__file__).resolve().parents[1] / 'eval/evidence/2026-11-10-country-method-pilot.json'


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))


def integration():
    return {
        'schema_version': 1, 'kind': 'mixed_retrieval_integration_validation',
        'title': 'Australia / UAE validation', 'base_sha': 'abc123',
        'date_singapore': '2026-11-10', 'requested_scope': ['AU', 'AE-federal'],
        'status': 'partial',
        'budgets': [{'metric': 'embedding requests', 'limit': 10, 'observed': 8, 'unit': 'requests'}],
        'methods': [{'source': 'CBUAE', 'method': 'direct PDF', 'status': 'acquired',
                     'url': 'https://centralbank.ae/document.pdf?download=1', 'pages': 8,
                     'permission_status': 'private organisational use', 'note': 'No external embedding'}],
        'storage_checks': [{'check': 'JSONB round trip', 'status': 'passed', 'observed': 6}],
        'checks': [{'check': 'research draft', 'status': 'not run', 'note': 'No audit opinion'}],
        'source_links': [{'label': 'Publication', 'url': 'https://centralbank.ae/document.pdf?download=1'}],
        'scope_limits': ['No human relevance labels'],
    }


def test_integration_sections_offline_and_unchanged():
    data = integration()
    before = deepcopy(data)
    html = render_report(data)
    assert data == before
    for expected in ('Scope and status', 'Budgets', 'Method results', 'Storage checks',
                     'Validation checks', 'Source links', 'Limits', 'partial', '8', '10',
                     'validation report, not an audit opinion', 'Hybrid retrieval remains experimental',
                     'No human relevance labels', 'No external embedding'):
        assert expected.lower() in html.lower()
    tags = Tags(html)
    assert tags.tags.count('h1') == 1
    assert 'caption' in tags.tags and 'th' in tags.tags
    assert not set(tags.tags) & {'script', 'iframe', 'img', 'link'}
    assert 'https://centralbank.ae/document.pdf?download=1' in tags.links


def test_pilot_preserves_exception_sample_and_retention_limits():
    html = render_report(json.loads(PILOT.read_text()))
    for expected in ('Original harness exit', 'incorrectly global', '1,282,162', '1,671',
                     '30', '488', 'equal top10', 'not full-archive', 'No human relevance labels',
                     '7,557', '34,204', '0.00129', '0.88053', '5 / 6', 'AUSTRAC', 'DFSA', 'BNM', 'metadata',
                     'No application fulltext retention', 'not publisher original'):
        assert expected in html
    assert '/Users/' not in html
    assert 'hk-durable-' not in html
    assert 'User-agent:' not in html


def test_unknown_fields_and_nested_values_do_not_export_bodies_or_secrets():
    data = integration()
    data.update({'article_body': 'SECRET UAE FULLTEXT', 'credentials': 'SECRET TOKEN'})
    data['methods'][0].update({'body': 'SECRET BODY', 'vectors': [123]})
    data['methods'][0]['characters'] = {'text': 'NESTED BODY'}
    data['scope_limits'].append({'text': 'NESTED LIMIT'})
    html = render_report(data)
    for private in ('SECRET UAE FULLTEXT', 'SECRET TOKEN', 'SECRET BODY', 'NESTED BODY', 'NESTED LIMIT'):
        assert private not in html


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///private/body',
                                'https://user:password@example.com/x', 'https://example.com/\nsecret',
                                'https://example.com/?api_key=secret', '//example.com/x'])
def test_unsafe_urls_are_not_exported(url):
    data = integration()
    data['methods'][0]['url'] = url
    data['source_links'][0]['url'] = url
    html = render_report(data)
    assert not Tags(html).links
    assert 'password' not in html and 'api_key' not in html


def test_html_is_escaped():
    data = integration()
    data['title'] = '<script>alert("bad")</script>'
    data['methods'][0]['note'] = '<img src=x onerror=evil>'
    html = render_report(data)
    assert '&lt;script&gt;' in html and '&lt;img' in html
    assert 'script' not in Tags(html).tags


@pytest.mark.parametrize('data', [{}, {'schema_version': 2, 'kind': 'bounded_source_method_pilot'},
                                 {'schema_version': 1, 'kind': 'audit_opinion'}])
def test_rejects_unrecognized_schema(data):
    with pytest.raises(ValueError):
        render_report(data)


def test_cli_writes_standalone_report(tmp_path):
    output = tmp_path / 'report.html'
    result = subprocess.run([sys.executable, '-m', 'eval.mixed_retrieval_report',
                             '--input', str(PILOT), '--output', str(output)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text().startswith('<!doctype html>')


def test_cli_refuses_to_overwrite_input(tmp_path):
    source = tmp_path / 'metadata.json'
    source.write_text(json.dumps(integration()))
    original = source.read_bytes()
    result = subprocess.run([sys.executable, '-m', 'eval.mixed_retrieval_report',
                             '--input', str(source), '--output', str(source)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert source.read_bytes() == original


def test_long_text_cells_are_rejected_as_not_portable_metadata():
    data = integration()
    data['methods'][0]['note'] = 'body' * 1001
    with pytest.raises(ValueError, match='Metadata cell exceeds'):
        render_report(data)
