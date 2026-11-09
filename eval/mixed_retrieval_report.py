"""Export allowlisted method-validation metadata as standalone, offline HTML.

Usage: python -m eval.mixed_retrieval_report --input result.json --output result.html

Supported schema_version=1 kinds:
* bounded_source_method_pilot: the saved 2026-11-10 portable pilot metadata.
* mixed_retrieval_integration_validation: optional title/base_sha/date_singapore,
  requested_scope (strings), status, budgets (metric/limit/observed/unit), methods
  (source/method/status/url/characters/pages/passages/permission_status/note),
  storage_checks (check/status/observed/note), checks (check/status/note),
  source_links (label/url), scope_limits (strings).

Only these fields are exported. Inputs must contain shareable metadata, never
article bodies, credentials or personal data in these fields. Unknown fields and
nested cell values are ignored. The exporter does not certify source permissions,
verify the reported checks, or turn model checks into human relevance labels.
It reads only the explicit JSON input and writes only the HTML output; no runtime,
network, database, environment or private artifact access occurs.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


INTEGRATION_KIND = 'mixed_retrieval_integration_validation'
PILOT_KIND = 'bounded_source_method_pilot'


def _cell(value: object) -> str:
    if value is None or not isinstance(value, (str, int, float, bool)):
        return 'Not recorded'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, int):
        return f'{value:,}'
    text = str(value)
    if len(text) > 4000:
        raise ValueError('Metadata cell exceeds 4000 characters; do not export source bodies')
    return escape(text, quote=True)


def _rows(value: object) -> list[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _link(value: object) -> str:
    """Show readable HTTP(S) URLs, retaining legitimate official download queries."""
    if not isinstance(value, str) or any(ord(c) < 33 or ord(c) == 127 for c in value):
        return 'Link omitted'
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return 'Link omitted'
        # Credential-bearing signed/private links do not belong in portable reports.
        sensitive = ('token', 'secret', 'password', 'credential', 'signature', 'api_key', 'apikey')
        if any(any(word in key.lower() for word in sensitive)
               for key, _ in parse_qsl(parsed.query)):
            return 'Link omitted'
        if parsed.fragment and any(word in parsed.fragment.lower() for word in sensitive):
            return 'Link omitted'
    except ValueError:
        return 'Link omitted'
    safe = _cell(value)
    return f'<a href="{safe}" rel="noreferrer">{safe}</a>'


def _table(title: str, rows: object, columns: tuple[tuple[str, str], ...]) -> str:
    data = _rows(rows)
    if not data:
        return f'<section><h2>{title}</h2><p>Not recorded.</p></section>'
    head = ''.join(f'<th scope="col">{label}</th>' for _, label in columns)
    body = []
    for row in data:
        cells = ''.join(f'<td data-label="{escape(label,quote=True)}">{_link(row.get(key)) if key == "url" else _cell(row.get(key))}</td>'
                        for key, label in columns)
        body.append(f'<tr>{cells}</tr>')
    return (f'<section><h2>{title}</h2><div class="table-wrap" tabindex="0" '
            f'role="region" aria-label="{title}"><table><caption>{title}</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div></section>')


def _pilot(data: dict) -> dict:
    """Adapt only saved portable metrics; never read the referenced private files."""
    plan = _mapping(data.get('plan'))
    comparison = _mapping(data.get('comparison'))
    audit = _mapping(data.get('final_audit'))
    totals = _mapping(audit.get('embedding_totals'))
    caps = _mapping(plan.get('caps'))
    acquisitions = _rows(data.get('acquisitions'))
    counts = {
        'publication_targets': len(acquisitions), 'exa_searches': len(_rows(data.get('exa'))),
        'browser_captures': sum(a.get('method') == 'browser' for a in acquisitions),
        'embedding_requests': totals.get('requests'), 'embedding_tokens': totals.get('known_tokens'),
        'embedding_input_bytes': totals.get('input_bytes'), 'seconds': None,
    }
    budgets = [{'metric': key.replace('_', ' '), 'limit': caps.get(key),
                'observed': count, 'unit': 'seconds' if key == 'seconds' else key.split('_')[-1]}
               for key, count in counts.items()]
    methods = []
    for item in acquisitions:
        methods.append({
            'source': item.get('id'),
            'method': f'{item.get("method", "Not recorded")} / {item.get("kind", "unspecified format")}',
            'status': item.get('status'), 'url': item.get('final_url', item.get('requested_url')),
            'characters': item.get('characters'), 'pages': item.get('pages'), 'passages': item.get('passages'),
            'permission_status': ('Private organisational use; no external embedding'
                                  if str(item.get('id', '')).startswith('ae-')
                                  else 'Pilot scope only; no persistent source grant'),
            'note': ('Structured API metadata, not a readable publication'
                     if item.get('kind') == 'json' else item.get('error_type', 'Recorded acquisition; not quality acceptance')),
        })
    for source, note in [
        ('AUSTRAC', 'Robots request timed out; no automated publication acquisition or browser retry.'),
        ('DFSA', 'Permission required for retrieval-system storage.'),
        ('BNM / AML portal', 'ExaBot disallowed; reuse approval not established.'),
        ('Securities Commission Malaysia', 'Written retrieval-system permission required.'),
    ]:
        methods.append({'source': source, 'method': 'deferred', 'status': 'permission/access gated',
                        'permission_status': 'No application fulltext retention', 'note': note})
    storage = [{'check': item.get('document'), 'status': 'JSONB exact round trip',
                'observed': item.get('jsonb_equal'),
                'note': f'{item.get("passages", 0)} passages; {_cell(item.get("characters"))} extracted characters'}
               for item in _rows(comparison.get('fulltext_roundtrips'))]
    summary = _mapping(data.get('descriptive_summary'))
    storage.extend([
        {'check': 'Extracted characters preserved', 'observed': summary.get('characters'),
         'status': 'Preservation after extraction', 'note': 'Does not establish original-document extraction accuracy.'},
        {'check': 'Passages preserved', 'observed': summary.get('passages'),
         'status': 'Offsets checked', 'note': 'Representations are not independent publications.'},
        {'check': 'Private derived snapshot round trip',
         'observed': _mapping(comparison.get('private_snapshot')).get('roundtrip_equal'),
         'status': 'Local only', 'note': 'Attributed derived JSON; not publisher original; not cloud storage.'},
    ])
    sample = _mapping(comparison.get('sample'))
    checks = [
        {'check': 'Original harness exit', 'status': audit.get('original_harness_exit'), 'note': audit.get('failure')},
        {'check': 'Separate read-only scoped audit', 'status': 'Recorded follow-up; no API rerun',
         'note': 'Relevant workspace MAS inactive/zero versions; global counts unchanged; no persisted pilot tables or source grants.'},
        {'check': 'Ranking comparison scope', 'status': 'Unlabelled observational comparison',
         'note': f'{sample.get("selected_passages")} / {sample.get("available_passages")} Australian HTML passages; same sample, frozen questions, equal top10; not full-archive coverage.'},
        {'check': 'Ranking versus quality', 'status': 'No human relevance labels',
         'note': 'Changed ranks do not establish answer-quality improvement; negative control still returns candidates.'},
        {'check': 'Descriptive ranking outcomes', 'status': 'Not a production latency benchmark',
         'note': f'Top1 unchanged: {summary.get("top1_same")} / {summary.get("frozen_questions")}; lexical median: {summary.get("lexical_median_seconds")} seconds; hybrid median including query API: {summary.get("hybrid_median_seconds_including_api")} seconds. Cold indexing excluded; no usefulness winner established.'},
        {'check': 'Production country enablement', 'status': data.get('production_country_enablement'),
         'note': 'The pilot does not establish country-wide access or completeness.'},
        {'check': 'Counter accounting', 'status': 'Publication entries are not all HTTP requests',
         'note': 'Two preliminary API probes, robots probes and policy/resource requests are outside the publication-target count. No single enforced global deadline; see saved pilot record.'},
    ]
    checks.extend({'check': item.get('id'), 'status': 'Ranking implementation agreement',
                   'note': f'Top10 overlap: {item.get("overlap_at_10")}; top1 unchanged: {item.get("top1_same")}; SQL/production fusion match: {item.get("pgvector_matches_production_fusion")}'}
                  for item in _rows(comparison.get('queries')))
    return {
        'title': 'Country source-method pilot', 'base_sha': data.get('base_sha'),
        'date_singapore': data.get('date_singapore'), 'requested_scope': data.get('requested_scope'),
        'status': 'Method checks recorded; original harness exit 1; scoped follow-up audit recorded; quality acceptance false',
        'budgets': budgets, 'methods': methods, 'storage_checks': storage, 'checks': checks,
        'source_links': [{'label': f'{item.get("id")} — ' + ('API metadata' if item.get('kind') == 'json' else 'publication / representation'),
                          'url': item.get('final_url', item.get('requested_url'))} for item in acquisitions],
        'scope_limits': data.get('scope_limits'),
    }


CSS = """
body{margin:0;background:#f4f6f8;color:#172b3a;font:16px/1.6 system-ui,sans-serif}
main{max-width:1200px;margin:auto;padding:36px 24px 64px}header{border-top:6px solid #174d66;padding:24px 0}
h1{font:700 2.4rem/1.2 Georgia,serif;max-width:24ch;margin:12px 0}h2{font-size:1.3rem;margin:0 0 14px}
.kicker{font-size:.85rem;text-transform:uppercase;letter-spacing:.12em}.notice{background:#fff4d6;border-left:5px solid #855400;padding:16px}
section{margin-top:28px;background:white;padding:24px;border:1px solid #cbd5df}.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}caption{text-align:left;font-weight:600;padding-bottom:12px}
th,td{text-align:left;vertical-align:top;border-bottom:1px solid #cbd5df;padding:12px 10px;min-width:7rem;overflow-wrap:anywhere}
th{background:#eaf0f5}a{color:#075781;text-decoration:underline;overflow-wrap:anywhere}a:focus-visible,[tabindex]:focus-visible{outline:3px solid #855400;outline-offset:3px}
li{margin:10px 0}footer{margin-top:28px;color:#455969;font-size:.9rem}
@media(max-width:600px){main{padding:20px 12px}section{padding:16px}h1{font-size:2rem}}
@media print{body{background:white}main{max-width:none;padding:0}section{padding:12px 0;border:0}.table-wrap{overflow:visible}table{font-size:8pt}th,td{padding:6px;min-width:0}h2{break-after:avoid}tr{break-inside:avoid}}
@media print{table{font-size:10pt}table:has(th:nth-child(6)) thead{display:none}table:has(th:nth-child(6)) tr{display:block;border:1px solid #cbd5df;margin:0 0 14px;padding:10px}table:has(th:nth-child(6)) td{display:grid;grid-template-columns:100px 1fr;gap:10px;border:0;padding:3px 0}table:has(th:nth-child(6)) td::before{content:attr(data-label);font-weight:600}table:has(th:nth-child(6)) caption{display:block}}
@media print{table:not(:has(th:nth-child(6))) th{min-width:7rem;overflow-wrap:normal}}
"""


def render_report(data: dict) -> str:
    """Return HTML from a recognized validation metadata schema, without I/O."""
    if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data.get('schema_version') != 1:
        raise ValueError('Expected schema_version 1')
    if data.get('kind') not in (PILOT_KIND, INTEGRATION_KIND):
        raise ValueError('Unsupported validation metadata kind')
    view = _pilot(data) if data['kind'] == PILOT_KIND else data
    title = _cell(view.get('title', 'Mixed retrieval validation'))
    scope = ', '.join(_strings(view.get('requested_scope'))) or 'Not recorded'
    sections = [
        _table('Scope and status', [dict(view, scope=scope)], (
            ('date_singapore', 'Date (Singapore)'), ('base_sha', 'Base SHA'), ('scope', 'Requested scope'), ('status', 'Recorded status'))),
        _table('Budgets', view.get('budgets'), (('metric', 'Metric'), ('limit', 'Limit'), ('observed', 'Observed'), ('unit', 'Unit'))),
        _table('Method results', view.get('methods'), (
            ('source', 'Source'), ('method', 'Method'), ('status', 'Status'), ('url', 'Source URL'),
            ('characters', 'Characters'), ('pages', 'Pages'), ('passages', 'Passages'),
            ('permission_status', 'Permission / retention'), ('note', 'Note'))),
        _table('Storage checks', view.get('storage_checks'), (('check', 'Check'), ('status', 'Status'), ('observed', 'Observed'), ('note', 'Note'))),
        _table('Validation checks', view.get('checks'), (('check', 'Check'), ('status', 'Status'), ('note', 'Note'))),
        _table('Source links', view.get('source_links'), (('label', 'Source / representation'), ('url', 'Readable URL'))),
    ]
    limits = ''.join(f'<li>{_cell(item)}</li>' for item in _strings(view.get('scope_limits')))
    sections.append(f'<section><h2>Limits</h2><ul>{limits or "<li>Not recorded.</li>"}</ul></section>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><style>{CSS}</style></head><body><main>'
            f'<header><p class="kicker">Engineering evidence · method validation</p><h1>{title}</h1>'
            '<p class="notice"><strong>Validation report, not an audit opinion.</strong> '
            'These are recorded engineering tests, not signed-off audit research or corroborated regulatory findings. '
            'Hybrid retrieval remains experimental. Rank changes alone do not establish usefulness or answer quality.</p></header>'
            + ''.join(sections) + '<footer>Offline export of allowlisted metadata. Source links require network access when opened. '
            'No publisher article bodies, vectors or private artifact files are embedded. '
            'Missing values mean not recorded, not passed. Test outcomes are reported from input metadata, not independently rerun by this exporter.</footer>'
            '</main></body></html>')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Output must differ from input')
    try:
        html = render_report(json.loads(args.input.read_text(encoding='utf-8')))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.write_text(html, encoding='utf-8')


if __name__ == '__main__':
    main()
