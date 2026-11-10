"""Focused research console behavior, without network or provider calls."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def app():
    spec = spec_from_file_location('research_console', Path('app/streamlit_app.py'))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_label_requires_operator_flag_and_demo_workspace(monkeypatch):
    console = app()
    monkeypatch.setenv('MIRA_DEMO_MODE', '1')
    assert console.is_synthetic_demo('mira-local-demo')
    assert not console.is_synthetic_demo('other-workspace')
    monkeypatch.delenv('MIRA_DEMO_MODE')
    assert not console.is_synthetic_demo('mira-local-demo')


def test_old_run_cost_is_unavailable():
    assert app().monetary_summary({}) == 'Unavailable'


def test_byok_rerun_requires_new_credentials():
    import pytest
    console = app()
    with pytest.raises(ValueError, match='credentials'):
        console.queue_rerun('workspace', 'user', {'status': 'draft', 'retrieval_settings': {'research': {'credential_mode': 'byok'}}})


def test_budget_summary_uses_recorded_snapshot():
    assert app().monetary_summary({'monetary_usage': {'known_estimated_usd': '1.2500'}}) == '$1.2500'


def test_queue_handoff_never_writes_keys_and_revokes_on_bind_failure(monkeypatch):
    from types import SimpleNamespace
    from mira.research_settings import ResearchSettings
    from mira.contracts import Brief
    from mira.budget import RunBudget
    from datetime import date
    import pytest
    console = app()
    writes = []
    class Query:
        def __init__(self, name): self.name = name
        def insert(self, payload): writes.append((self.name, payload)); return self
        def update(self, payload): writes.append((self.name, payload)); return self
        def eq(self, *args): return self
        def execute(self):
            if self.name == 'bind_run_credentials': raise RuntimeError('bind failed')
            return SimpleNamespace(data=[{'id': self.name + '-id'}])
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='access'))
        def table(self, name): return Query(name)
        def rpc(self, name, payload): writes.append((name, payload)); return Query(name)
    revoked = []
    class Broker:
        def __init__(self, path): pass
        def put(self, token, workspace, run, keys): return 'opaque'
        def revoke(self, token, handle): revoked.append(handle)
    monkeypatch.setattr(console, 'client', lambda: SB())
    import mira.credentials
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    brief = Brief(topic='AML/CFT', jurisdictions=['HK'], period_start=date(2024, 1, 1), period_end=date(2025, 1, 1), as_of_date=date(2025, 1, 1), plan_requires_approval=False)
    settings = ResearchSettings(credential_mode='byok')
    with pytest.raises(Exception):
        console.queue_run('w', 'u', brief, RunBudget(), settings=settings, provider_keys={'openai': 'private-key'})
    assert 'private-key' not in repr(writes)
    assert revoked == ['opaque']
    assert ('analysis_runs', {'status': 'cancelled'}) in writes


def test_source_selection_excludes_inactive_sources():
    sources = [
        {'id': 'a', 'is_active': True, 'source_type': 'regulator'},
        {'id': 'b', 'is_active': False, 'source_type': 'regulator'},
        {'id': 'c', 'is_active': True, 'source_type': 'manual'},
    ]
    assert [s['id'] for s in app().eligible_sources(sources)] == ['a', 'c']


def test_unpriced_cost_never_defaults_to_zero():
    assert app().monetary_summary({'monetary_usage': {}}) == 'Unavailable'


def test_sign_in_screen_renders_without_errors(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv('MIRA_DEMO_MODE', raising=False)
    screen = AppTest.from_file(Path('app/streamlit_app.py').resolve()).run()
    assert not screen.exception
    assert screen.text_input[1].label == 'Password'


def test_research_controls_use_usd_and_approved_sources(monkeypatch):
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    class Query:
        def __init__(self, table): self.name = table
        def select(self, *args): return self
        def eq(self, *args): return self
        def execute(self):
            data = {
                'workspaces': [{'id': 'w', 'name': 'Audit'}],
                'workspace_members': [{'role': 'analyst'}],
                'expected_sources': [],
                'sources': [{'id': 's', 'name': 'Regulator', 'source_type': 'regulator', 'is_active': True}],
            }
            return SimpleNamespace(data=data[self.name])
    class SB:
        def table(self, name): return Query(name)
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    screen = AppTest.from_file(Path('app/streamlit_app.py').resolve())
    screen.session_state.user_id = 'user'
    screen.session_state.email = 'user@example.test'
    screen.session_state.sb = SB()
    screen.run()
    assert not screen.exception
    labels = [x.label for x in screen.text_input]
    assert 'Maximum estimated cost (USD)' in labels
    assert 'Max model tokens' not in [x.label for x in screen.number_input]
    assert 'Approved active sources' in [x.label for x in screen.multiselect]
    assert screen.button(key='FormSubmitter:brief-Review research').disabled


def test_cost_details_preserve_unknown_and_pending_estimates():
    usage = {'max_usd': '5', 'known_estimated_usd': '1', 'unknown_reserved_usd': '0.5',
             'pending_usd': '0.25', 'allowance_used_usd': '1.75'}
    assert app().monetary_details({'monetary_usage': usage}) == [
        ('Allowance', '$5'), ('Known estimate', '$1'), ('Unknown reserved', '$0.5'),
        ('Pending', '$0.25'), ('Allowance used', '$1.75')]


def test_launch_queues_selected_settings_without_storing_key(monkeypatch):
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    from mira.llm import ROLE_MODEL_ENV
    import mira.pricing, mira.credentials
    writes = []
    class Query:
        def __init__(self, name): self.name = name
        def select(self, *args): return self
        def eq(self, *args): return self
        def insert(self, payload): writes.append((self.name, payload)); return self
        def execute(self):
            return SimpleNamespace(data={
                'workspaces': [{'id': 'w', 'name': 'Audit'}],
                'workspace_members': [{'role': 'analyst'}],
                'expected_sources': [],
                'sources': [{'id': '11111111-1111-1111-1111-111111111111', 'name': 'Regulator', 'source_type': 'regulator', 'is_active': True}],
            }.get(self.name, [{'id': self.name + '-id'}]))
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='access'))
        def table(self, name): return Query(name)
        def rpc(self, name, payload): writes.append((name, payload)); return Query(name)
    class Book:
        def token_rate(self, *args): return SimpleNamespace(input_per_million='1', output_per_million='2', context_threshold=None, high_input_multiplier=1, high_output_multiplier=1)
        def search_cost(self, *args): return 1
        def metadata(self): return {'checked_at': 'today', 'sources': []}
    class Broker:
        def __init__(self, path): pass
        def put(self, token, workspace, run, keys): return 'opaque'
    monkeypatch.setattr(mira.pricing, 'load_price_book', lambda *args, **kwargs: Book())
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    for var in ROLE_MODEL_ENV.values(): monkeypatch.setenv(var, 'openai:gpt-5.4-mini')
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS', '1')
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    screen = AppTest.from_file(Path('app/streamlit_app.py').resolve())
    screen.session_state.user_id = 'user'
    screen.session_state.email = 'user@example.test'
    screen.session_state.sb = SB()
    screen.run()
    next(b for b in screen.button if b.label == 'Check current prices').click().run()
    next(x for x in screen.selectbox if x.label == 'Period').select('Custom').run()
    from datetime import date
    next(x for x in screen.date_input if x.label == 'Period start').set_value(date(2024, 1, 2))
    next(x for x in screen.date_input if x.label == 'Period end').set_value(date(2024, 12, 31))
    next(x for x in screen.checkbox if x.label == 'Approve research plan before acquisition').check()
    next(b for b in screen.button if b.label == 'Review research').click().run()
    assert not writes
    assert any('Regulator' in x.value for x in screen.markdown)
    assert any('60 minutes' in x.value for x in screen.markdown)
    assert any('2024-01-02 to 2024-12-31' in x.value for x in screen.markdown)
    next(x for x in screen.text_input if x.label == 'Openai API key').input('secret-value')
    next(b for b in screen.button if b.label == 'Queue research').click().run()
    assert not screen.exception
    run = next(payload for name, payload in writes if name == 'analysis_runs')
    assert run['source_limits']['max_cost_usd'] == '10.00'
    assert run['retrieval_settings']['plan_requires_approval'] is True
    assert run['retrieval_settings']['research']['source_ids'] == ['11111111-1111-1111-1111-111111111111']
    assert 'secret-value' not in repr(writes)
    screen.run()
    assert not any(x.label == 'Openai API key' for x in screen.text_input)
    assert 'secret-value' not in repr(screen.session_state)


def test_source_focus_uses_latest_active_categories_and_keeps_unclassified():
    records = [
        {'source_id': 'a', 'jurisdiction_code': 'HK', 'category': 'industry', 'list_version': 1, 'is_active': True},
        {'source_id': 'a', 'jurisdiction_code': 'HK', 'category': 'rule', 'list_version': 2, 'is_active': True},
        {'source_id': 'b', 'jurisdiction_code': 'HK', 'category': 'industry', 'list_version': 2, 'is_active': True},
    ]
    assert app().source_groups(['a', 'b', 'c'], records, ['HK']) == {'a': {'Regulatory'}, 'b': {'Industry'}, 'c': {'Other'}}


def test_country_methods_is_public_and_discloses_unmeasured_comparisons(monkeypatch):
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    class Query:
        def __init__(self, table): self.name = table
        def select(self, *args): return self
        def eq(self, *args): return self
        def execute(self):
            return SimpleNamespace(data={'workspaces': [{'id': 'w', 'name': 'Audit'}],
                'workspace_members': [{'role': 'analyst'}], 'sources': [], 'expected_sources': []}[self.name])
    class SB:
        def table(self, name): return Query(name)
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    screen = AppTest.from_file(Path('app/streamlit_app.py').resolve())
    screen.session_state.user_id = 'user'
    screen.session_state.email = 'user@example.test'
    screen.session_state.sb = SB()
    screen.run()
    screen.sidebar.radio[0].set_value('Country methods').run()
    assert not screen.exception
    assert any('Not available' in text.value for text in screen.markdown)
    assert any('Not tested' in text.value for text in screen.markdown)


def test_cancel_run_revokes_bound_pending_credentials(monkeypatch):
    from types import SimpleNamespace
    import mira.credentials
    console = app()
    events = []
    class Query:
        def update(self, data): events.append(('cancel', data)); return self
        def eq(self, *args): return self
        def execute(self): return SimpleNamespace(data=[{'id': 'r'}])
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='token'))
        def table(self, name): return Query()
    class Broker:
        def __init__(self, path): pass
        def revoke(self, token, handle): events.append(('revoke', handle))
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    console.cancel_run(SB(), {'id': 'r', 'status': 'queued', 'retrieval_settings': {'research': {'credential_handle': 'opaque'}}})
    assert events == [('cancel', {'status': 'cancelled'}), ('revoke', 'opaque')]


def test_rebind_pending_run_revokes_new_handle_when_bind_fails(monkeypatch):
    from types import SimpleNamespace
    import mira.credentials
    import pytest
    events = []
    class Broker:
        def __init__(self, path): pass
        def put(self, token, workspace, run, keys): events.append(('put', run)); return 'lease'
        def revoke(self, token, handle): events.append(('revoke', handle))
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='token'))
        def rpc(self, name, payload): raise RuntimeError('failed')
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    with pytest.raises(RuntimeError):
        app().bind_fresh_credentials(SB(), 'w', 'r', {'openai': 'secret'})
    assert events == [('put', 'r'), ('revoke', 'lease')]


def test_queued_run_accepts_fresh_keys_and_cancel_revokes_lease(monkeypatch):
    from types import SimpleNamespace
    from streamlit.testing.v1 import AppTest
    import mira.credentials, mira.pricing
    events = []
    run = {'id': 'r', 'workspace_id': 'w', 'created_at': '2026-01-01T00:00:00',
           'resolved_markets': ['HK'], 'status': 'queued', 'source_limits': {}, 'failure_summary': None,
           'model_settings': {'writer': 'openai:gpt-5.4-mini'},
           'retrieval_settings': {'research': {'credential_mode': 'byok', 'credential_handle': None}}}
    class Query:
        def __init__(self, name): self.name = name
        def select(self, *args): return self
        def eq(self, *args): return self
        def order(self, *args, **kwargs): return self
        def limit(self, *args): return self
        def update(self, payload): self.payload = payload; return self
        def execute(self):
            if hasattr(self, 'payload'):
                events.append(('cancel', self.payload)); return SimpleNamespace(data=[{'id': 'r'}])
            return SimpleNamespace(data={'workspaces': [{'id': 'w', 'name': 'Audit'}],
                'workspace_members': [{'role': 'analyst'}], 'sources': [], 'expected_sources': [],
                'analysis_runs': [run], 'agent_steps': [], 'research_plans': [], 'coverage_results': []}.get(self.name, []))
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='token'))
        def table(self, name): return Query(name)
        def rpc(self, name, payload): events.append(('bind', payload)); return Query(name)
    class Broker:
        def __init__(self, path): pass
        def put(self, token, workspace, run_id, keys): events.append(('put', run_id)); return 'lease'
        def revoke(self, token, handle): events.append(('revoke', handle))
    class Book:
        def token_rate(self, *args): return object()
        def metadata(self): return {'checked_at': 'today', 'sources': []}
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    monkeypatch.setattr(mira.pricing, 'load_price_book', lambda *args, **kwargs: Book())
    monkeypatch.setenv('MIRA_WORKSPACE_SLUG', 'workspace')
    monkeypatch.setenv('MIRA_ENABLE_BYOK_RUNS', '1')
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    screen = AppTest.from_file(Path('app/streamlit_app.py').resolve())
    screen.session_state.user_id = 'u'
    screen.session_state.email = 'user@example.test'
    screen.session_state.sb = SB()
    screen.session_state['refresh-run'] = False
    screen.run()
    screen.sidebar.radio[0].set_value('Runs').run()
    assert next(b for b in screen.button if b.label == 'Supply fresh keys').disabled
    next(b for b in screen.button if b.label == 'Check current prices for continuation').click().run()
    next(x for x in screen.text_input if x.label == 'Openai API key').input('secret')
    next(b for b in screen.button if b.label == 'Supply fresh keys').click().run()
    assert ('bind', {'p_run_id': 'r', 'p_handle': 'lease'}) in events
    assert 'secret' not in repr(events)
    run['retrieval_settings']['research']['credential_handle'] = 'lease'
    next(b for b in screen.button if b.label == 'Cancel run').click().run()
    assert ('revoke', 'lease') in events
    assert not screen.exception


def test_cancel_reports_revocation_failure(monkeypatch):
    from types import SimpleNamespace
    import mira.credentials
    class Query:
        def update(self, value): return self
        def eq(self, *args): return self
        def execute(self): return SimpleNamespace(data=[{'id': 'r', 'retrieval_settings': {'research': {'credential_handle': 'lease'}}}])
    class SB:
        auth = SimpleNamespace(get_session=lambda: SimpleNamespace(access_token='token'))
        def table(self, name): return Query()
    class Broker:
        def __init__(self, path): pass
        def revoke(self, *args): raise OSError('unavailable')
    monkeypatch.setenv('MIRA_BROKER_SOCKET', '/socket')
    monkeypatch.setattr(mira.credentials, 'BrokerClient', Broker)
    assert not app().cancel_run(SB(), {'id': 'r', 'status': 'queued'})
