"""Prepared console behavior with signed-in boundary doubles; no provider calls."""
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


class Query:
    def __init__(self, sb, name, payload=None):
        self.sb, self.name, self.payload = sb, name, payload
        self.filters = {}

    def select(self, *args): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def in_(self, key, values): self.filters[key] = values; return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args): return self
    def execute(self):
        if self.payload is not None:
            self.sb.calls.append((self.name, self.payload))
            return SimpleNamespace(data='request-1')
        data = deepcopy(self.sb.data.get(self.name, []))
        for key, value in self.filters.items():
            data = [r for r in data if r.get(key) in value] if isinstance(value, list) else [r for r in data if r.get(key) == value]
        return SimpleNamespace(data=data)


class SignedIn:
    def __init__(self, data=None): self.data, self.calls = data or {}, []
    def table(self, name): return Query(self, name)
    def rpc(self, name, payload): return Query(self, name, payload)


def test_request_only_sends_brief_and_sources_to_atomic_rpc():
    from mira.prepared_console import submit_request
    sb = SignedIn()
    result = submit_request(sb, 'w', {'topic': 'AML/CFT', 'jurisdictions': ['HK'], 'period_start': '2025-01-01',
                                    'period_end': '2025-12-31', 'as_of_date': '2025-12-31'}, ['source-1'], 'stable-key')
    assert result == 'request-1'
    assert sb.calls == [('request_prepared_report', {'p_workspace': 'w', 'p_brief': {
        'topic': 'AML/CFT', 'jurisdictions': ['HK'], 'period_start': '2025-01-01',
        'period_end': '2025-12-31', 'as_of_date': '2025-12-31'},
        'p_source_ids': ['source-1'], 'p_idempotency_key': 'stable-key'})]


@pytest.mark.parametrize('state,expected', [('human_checked', 'Human evidence checked'),
    ('human_review_pending', 'Human evidence review pending'), ('mixed', 'Human evidence review pending'),
    (None, 'Human evidence review pending')])
def test_only_explicit_checked_state_can_display_checked_label(state, expected):
    from mira.prepared_console import evidence_review_label
    assert evidence_review_label(state) == expected


def test_review_action_uses_exact_snapshot_and_finding_without_amending_fact():
    from mira.prepared_console import review_fact
    sb = SignedIn()
    review_fact(sb, 'snapshot-1', 'finding-1', 'correction_requested', 'Scope needs correction')
    assert sb.calls == [('review_prepared_fact', {'p_snapshot': 'snapshot-1', 'p_finding': 'finding-1',
        'p_decision': 'correction_requested', 'p_comment': 'Scope needs correction'})]
    with pytest.raises(ValueError):
        review_fact(sb, 'snapshot-1', 'finding-1', 'amended', 'new words')
    assert len(sb.calls) == 1


def test_cancel_only_targets_report_request():
    from mira.prepared_console import cancel_request
    sb = SignedIn()
    cancel_request(sb, 'request-1')
    assert sb.calls == [('cancel_prepared_report_request', {'p_request': 'request-1'})]


def screen(data=None, role='analyst'):
    from streamlit.testing.v1 import AppTest
    records = {'workspaces': [{'id': 'w', 'name': 'Audit', 'slug': 'workspace'}],
        'workspace_members': [{'workspace_id': 'w', 'user_id': 'user', 'role': role}],
        'sources': [{'workspace_id': 'w', 'id': 'source-1', 'name': 'HK regulator', 'jurisdiction_code': 'HK',
                     'is_active': True, 'source_type': 'regulator', 'source_key': 'HKMA',
                     'permitted_operations': ['fetch', 'store_text']}]}
    records.update(data or {})
    app = AppTest.from_file(Path('app/streamlit_app.py').resolve())
    app.session_state.user_id = 'user'
    app.session_state.email = 'analyst@example.test'
    app.session_state.sb = SignedIn(records)
    return app.run()


def test_default_prepared_request_is_available_without_byok_gate(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS', '0')
    today = date.today()
    app = screen({
        'preparation_scopes': [{'workspace_id': 'w', 'source_id': 'source-1', 'topic': 'AML/CFT',
                                'latest_snapshot_id': 'snapshot-1'}],
        'prepared_snapshots': [{'workspace_id': 'w', 'id': 'snapshot-1', 'prepared_through': today.isoformat(),
                                'brief': {'period_start': (today - timedelta(days=365)).isoformat(),
                                          'period_end': today.isoformat()}}],
    })
    assert not app.exception
    assert next(r for r in app.radio if r.label == 'Workflow').value == 'Prepared archive report'
    assert next(s for s in app.selectbox if s.label == 'Topic').options == ['AML/CFT']
    assert not any('API key' in x.label for x in app.text_input)
    submit = next(b for b in app.button if b.label == 'Review request')
    assert not submit.disabled
    submit.click().run()
    assert not app.exception
    assert app.session_state.sb.calls == []
    next(b for b in app.button if b.label == 'Queue report').click().run()
    assert not app.exception
    assert app.session_state.sb.calls[0][0] == 'request_prepared_report'
    assert app.session_state.sb.calls[0][1]['p_brief']['plan_requires_approval'] is False
    assert len(app.session_state.sb.calls) == 1


def test_outside_saved_dates_can_queue_the_covered_portion(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    today = date.today()
    prepared_through = (today - timedelta(days=12)).isoformat()
    first = (today - timedelta(days=180)).isoformat()
    app = screen({
        'preparation_scopes': [{'workspace_id': 'w', 'source_id': 'source-1', 'topic': 'AML/CFT',
                                'latest_snapshot_id': 'snapshot-1'}],
        'prepared_snapshots': [{'workspace_id': 'w', 'id': 'snapshot-1', 'prepared_through': prepared_through,
                                'brief': {'period_start': first, 'period_end': prepared_through}}],
    })
    next(b for b in app.button if b.label == 'Review request').click().run()
    assert not any(b.label == 'Queue report' for b in app.button)
    next(b for b in app.button if b.label == 'Use saved dates').click().run()
    next(b for b in app.button if b.label == 'Queue report').click().run()
    brief = app.session_state.sb.calls[0][1]['p_brief']
    assert brief['period_start'] == first
    assert brief['period_end'] == brief['as_of_date'] == prepared_through


def test_keep_dates_carries_the_request_to_full_research_without_launching(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS', '0')
    app = screen()
    next(b for b in app.button if b.label == 'Review request').click().run()
    pending = app.session_state.pending_prepared_request
    next(b for b in app.button if b.label == 'Keep dates and continue to research').click().run()
    assert not app.exception
    assert next(r for r in app.radio if r.label == 'Workflow').value == 'Full research'
    assert next(s for s in app.selectbox if s.label == 'Period').value == 'Custom'
    assert next(i for i in app.date_input if i.label == 'Period start').value.isoformat() == pending['brief']['period_start']
    assert next(i for i in app.date_input if i.label == 'Period end').value.isoformat() == pending['brief']['period_end']
    assert next(m for m in app.multiselect if m.label == 'Approved active sources').value == pending['source_ids']
    assert next(b for b in app.button if b.label == 'Review research').disabled
    assert app.session_state.sb.calls == []


def test_prepared_fact_review_is_read_only_for_analyst(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = screen(snapshot_records())
    next(r for r in app.radio if r.label == 'Page').set_value('Prepared evidence').run()
    assert not app.exception
    assert any('Banks must document' in text.value for text in app.markdown)
    assert not any(b.label == 'Save evidence decision' for b in app.button)


def request_records(status='waiting', *, report=False):
    request = {'id': 'request-1', 'workspace_id': 'w', 'actor_id': 'user',
        'brief': {'topic': 'AML/CFT'}, 'source_ids': ['source-1'], 'status': status,
        'created_at': '2026-11-10T09:00:00+00:00', 'generation_started_at': '2026-11-10T09:02:00+00:00',
        'finished_at': '2026-11-10T09:03:00+00:00' if report else None,
        'reason': 'Refresh failed' if status == 'evidence_failed' else None}
    data = {'prepared_report_requests': [request], 'prepared_report_request_scopes': [
        {'workspace_id': 'w', 'request_id': 'request-1', 'scope_id': 'source-1', 'job_id': 'job-1',
         'snapshot_id': None, 'previous_snapshot_id': 'snapshot-old'}],
        'preparation_jobs': [{'id': 'job-1', 'workspace_id': 'w', 'status': 'failed' if status == 'evidence_failed' else 'preparing',
                             'phase': 'verification', 'created_at': '2026-11-10T08:59:00+00:00',
                             'lease_until': '2026-11-10T09:01:00+00:00', 'reason': 'Lease expired'}]}
    if report:
        data['prepared_reports'] = [{'workspace_id': 'w', 'id': 'report-1', 'request_id': 'request-1',
             'review_state': 'human_review_pending', 'html': '<h1>Draft — human evidence review pending</h1>',
             'capture': {}, 'created_at': '2026-11-10T09:03:00+00:00'}]
    return data


def navigate(app, page):
    return next(r for r in app.radio if r.label == 'Page').set_value(page).run()


def test_wait_does_not_offer_older_snapshot_before_failure(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = navigate(screen(request_records()), 'Prepared reports')
    assert not app.exception
    assert any('Waiting for the scheduled' in x.value for x in app.info)
    assert any('verification' in x.value for x in app.markdown)
    assert not any(b.label == 'Use previous completed snapshot' for b in app.button)


def test_failed_refresh_has_explicit_previous_choice_and_cancellation(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = navigate(screen(request_records('evidence_failed')), 'Prepared reports')
    assert not app.exception
    assert any('Refresh failed' in x.value for x in app.error)
    next(b for b in app.button if b.label == 'Use previous completed snapshot').click().run()
    assert app.session_state.sb.calls == [('choose_prepared_previous', {'p_request': 'request-1', 'p_scope': 'source-1'})]
    next(b for b in app.button if b.label == 'Cancel report request').click().run()
    assert app.session_state.sb.calls[-1] == ('cancel_prepared_report_request', {'p_request': 'request-1'})


def test_report_timing_and_pending_capture_block_approval_even_after_later_check(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = navigate(screen(request_records('ready', report=True), role='reviewer'), 'Prepared reports')
    assert not app.exception
    assert any('human evidence review pending' in x.value for x in app.warning)
    assert next(b for b in app.button if b.label == 'Approve prepared report').disabled
    metrics = {m.label: m.value for m in app.metric}
    assert metrics['Total elapsed'] == '3m 0s'
    assert metrics['Evidence wait'] == '2m 0s'
    assert metrics['Report generation'] == '1m 0s'


def test_reviewer_cannot_cancel_another_analysts_request(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    data = request_records()
    data['prepared_report_requests'][0]['actor_id'] = 'another-user'
    app = navigate(screen(data, role='reviewer'), 'Prepared reports')
    assert not app.exception
    assert not any(b.label == 'Cancel report request' for b in app.button)


def test_prepared_source_menu_excludes_disabled_routes_even_if_misconfigured_active():
    from mira.prepared_console import prepared_sources
    sources = [{'id': key, 'is_active': True, 'source_key': key, 'jurisdiction_code': market,
                'permitted_operations': ['fetch', 'store_text']} for key, market in
               [('HKMA', 'HK'), ('MAS', 'SG'), ('DFSA', 'AE'), ('MY_BANK', 'MY')]]
    sources.append({'id': 'denied', 'is_active': True, 'source_key': 'AU', 'jurisdiction_code': 'AU', 'permitted_operations': ['fetch']})
    assert [s['id'] for s in prepared_sources(sources)] == ['HKMA']


def snapshot_records():
    fact = {'finding_id': 'finding-1', 'title': 'Synthetic controls requirement', 'content': 'Banks must document their controls.',
        'finding_type': 'regulatory_change', 'is_inference': False, 'depends_on': [],
        'evidence': [{'passage_id': 'passage-1', 'document_version_id': 'version-1',
                      'supporting_quote': 'Banks must document their controls.', 'support_type': 'supports'}]}
    payload = {'prepared_through': '2026-11-09', 'prepared_at': '2026-11-10T08:00:00+00:00',
        'brief': {'period_start': '2025-11-09', 'period_end': '2026-11-09'},
        'evidence_input': {'findings': {'finding-1': fact}, 'passages': {'passage-1': {'id': 'passage-1',
            'source_id': 'source-1', 'document_version_id': 'version-1', 'title': 'Synthetic publication',
            'source_name': 'HK regulator', 'source_url': 'https://example.test/synthetic', 'published_at': '2026-11-01',
            'content': 'Banks must document their controls. This is a synthetic fixture.'}}},
        'verifications': {'finding-1': {'check_id': 'check-1', 'verdict': 'supported', 'method': 'semantic_entailment',
            'reason': 'Exact requirement supported.', 'checked_at': '2026-11-10T07:59:00+00:00', 'input_fingerprint': 'frozen-input'}},
        'coverage': [], 'analysis_coverage': {'retained_passages': 20, 'analysed_passages': 1},
        'reasons': ['Nineteen passages remain deferred.']}
    return {'prepared_snapshots': [{'id': 'snapshot-1', 'workspace_id': 'w', 'published_at': '2026-11-10T08:00:00+00:00',
                                   'source_ids': ['source-1'], 'payload': payload}],
        'prepared_facts': [{'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-1',
                            'fact': fact, 'input_fingerprint': 'exact-fact'}],
        'prepared_fact_reviews': [{'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-1',
            'sequence': 1, 'decision': 'rejected', 'comment': 'First review', 'created_at': '2026-11-10T08:05:00+00:00'},
            {'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-1', 'sequence': 2,
             'decision': 'accepted', 'comment': 'Second review', 'created_at': '2026-11-10T08:06:00+00:00'}]}


def test_exact_snapshot_evidence_checks_and_review_history_are_visible(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = navigate(screen(snapshot_records(), role='reviewer'), 'Prepared evidence')
    assert not app.exception
    assert any('semantic entailment' in x.value for x in app.caption)
    assert any('First review' in x.value for x in app.caption)
    assert any('Second review' in x.value for x in app.caption)
    assert any('https://example.test/synthetic' in x.value for x in app.markdown)
    next(r for r in app.radio if r.label == 'Evidence decision').set_value('correction_requested')
    next(x for x in app.text_area if x.label == 'Review note').input('Scope needs correction')
    next(b for b in app.button if b.label == 'Save evidence decision').click().run()
    assert app.session_state.sb.calls[-1] == ('review_prepared_fact', {'p_snapshot': 'snapshot-1',
        'p_finding': 'finding-1', 'p_decision': 'correction_requested', 'p_comment': 'Scope needs correction'})


def test_later_alert_does_not_change_captured_checked_status_or_enable_approval(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    data = request_records('ready', report=True)
    data['prepared_reports'][0]['review_state'] = 'human_checked'
    data['prepared_report_alerts'] = [{'workspace_id': 'w', 'report_id': 'report-1', 'finding_id': 'finding-1',
                                      'snapshot_id': 'snapshot-1', 'decision': 'rejected', 'created_at': '2026-11-10T09:05:00+00:00'}]
    app = navigate(screen(data, role='reviewer'), 'Prepared reports')
    assert not app.exception
    assert any('Human evidence checked' in x.value for x in app.success)
    assert any('Later evidence rejection' in x.value for x in app.error)
    assert next(b for b in app.button if b.label == 'Approve prepared report').disabled


def test_cancelled_request_offers_no_cancel_or_previous_choice(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    app = navigate(screen(request_records('cancelled')), 'Prepared reports')
    assert not app.exception
    assert not any(b.label in {'Cancel report request', 'Use previous completed snapshot'} for b in app.button)


def test_manifest_displays_each_pinned_snapshot_freshness_and_source_review_counts(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    data = request_records('queued')
    data.update(snapshot_records())
    # One snapshot spans two sources; its unrelated pending fact must not be
    # counted as pending evidence for the first source.
    data['prepared_snapshots'][0]['source_ids'].append('source-2')
    payload = data['prepared_snapshots'][0]['payload']
    payload['evidence_input']['passages']['passage-2'] = {'source_id': 'source-2'}
    data['prepared_facts'].append({'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-2',
                                  'fact': {'evidence': [{'passage_id': 'passage-2'}]}})
    data['prepared_report_request_scopes'] = [{'workspace_id': 'w', 'request_id': 'request-1', 'scope_id': 'source-1',
                                               'snapshot_id': 'snapshot-1', 'job_id': None, 'previous_snapshot_id': None}]
    app = navigate(screen(data), 'Prepared reports')
    assert not app.exception
    assert any('Prepared through 2026-11-09' in x.value for x in app.caption)
    assert any('Published 2026-11-10 08:00 UTC' in x.value for x in app.caption)
    assert any('0 pending · 1 accepted' in x.value for x in app.markdown)


def test_checked_report_can_be_separately_approved_by_reviewer(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    data = request_records('ready', report=True)
    data['prepared_reports'][0]['review_state'] = 'human_checked'
    app = navigate(screen(data, role='reviewer'), 'Prepared reports')
    next(x for x in app.text_input if x.label == 'Final approval note').input('Approved for audit planning')
    approve = next(b for b in app.button if b.label == 'Approve prepared report')
    assert not approve.disabled
    approve.click().run()
    assert not app.exception
    assert app.session_state.sb.calls == [('approve_prepared_report', {'p_report': 'report-1', 'p_comment': 'Approved for audit planning'})]


def test_mixed_report_shows_captured_per_fact_decisions_and_publications(monkeypatch):
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    data = request_records('ready', report=True)
    capture = {'prepared_bindings': [
        {'snapshot_id': 'snapshot-1', 'finding_id': 'finding-1', 'decision': 'accepted', 'review_sequence': 1},
        {'snapshot_id': 'snapshot-1', 'finding_id': 'finding-2', 'decision': None, 'review_sequence': None}],
        'selected_findings': {
            'finding-1': {'title': 'Customer identification', 'evidence': [{'passage_id': 'passage-1'}]},
            'finding-2': {'title': 'Record retention', 'evidence': [{'passage_id': 'passage-2'}]}},
        'snapshots': {'snapshot-1': {'evidence_input': {'passages': {
            'passage-1': {'title': 'Customer due diligence circular', 'source_name': 'HK regulator'},
            'passage-2': {'title': 'Recordkeeping guideline', 'source_name': 'HK regulator'}}}}}}
    data['prepared_reports'][0]['capture'] = capture
    # Live reviews are deliberately different from the publication-time record.
    data['prepared_fact_reviews'] = [
        {'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-1', 'decision': 'rejected', 'sequence': 2},
        {'workspace_id': 'w', 'snapshot_id': 'snapshot-1', 'finding_id': 'finding-2', 'decision': 'accepted', 'sequence': 1}]
    app = navigate(screen(data, role='reviewer'), 'Prepared reports')
    assert not app.exception
    tables = [d.value for d in app.dataframe if 'Captured evidence decision' in d.value.columns]
    assert len(tables) == 1
    assert tables[0][['Finding', 'Captured evidence decision', 'Publications']].to_dict('records') == [
        {'Finding': 'Customer identification', 'Captured evidence decision': 'Accepted',
         'Publications': 'Customer due diligence circular · HK regulator'},
        {'Finding': 'Record retention', 'Captured evidence decision': 'Pending',
         'Publications': 'Recordkeeping guideline · HK regulator'}]
    assert any('human evidence review pending' in x.value for x in app.warning)
    assert next(b for b in app.button if b.label == 'Approve prepared report').disabled
    assert app.session_state.sb.data['prepared_reports'][0]['capture'] == capture
