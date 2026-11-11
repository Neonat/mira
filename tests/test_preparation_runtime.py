from types import SimpleNamespace

from mira.preparation_runtime import process_job


class Store:
    def __init__(self, alive=True):
        self.alive = alive
        self.published = []
        self.failed = []
    def heartbeat_job(self, job, phase):
        return self.alive
    def set_job_run(self, job, run_id):
        job['analysis_run_id'] = run_id
        return True
    def publish_job(self, job, payload):
        self.published.append(payload)
    def fail_job(self, job, reason):
        self.failed.append(reason)


def test_preparation_dispatches_without_writer_and_publishes():
    store = Store()
    job = {'id': 'job', 'analysis_run_id': None, 'source_ids': ['source']}
    calls = []
    def execute(run_id, guard, frontier):
        calls.append((run_id, frontier))
        guard('verify')
        return SimpleNamespace(status='draft', reasons=[])
    status = process_job(store, job, create_run=lambda job: 'run', execute=execute,
                         payload=lambda run_id, sources: {'run': run_id}, frontier='frontier')
    assert status == 'published'
    assert calls == [('run', 'frontier')]
    assert store.published == [{'run': 'run'}]


def test_expired_lease_never_dispatches_or_publishes():
    store = Store(alive=False)
    job = {'id': 'job', 'analysis_run_id': None, 'source_ids': ['source']}
    called = []
    status = process_job(store, job, create_run=lambda job: called.append('create'),
                         execute=lambda *args: called.append('execute'), payload=lambda *args: {})
    assert status == 'lease_lost'
    assert called == []
    assert store.published == []


def test_interrupted_run_is_not_automatically_resumed():
    store = Store()
    job = {'id': 'job', 'analysis_run_id': 'prior', 'source_ids': ['source']}
    called = []
    status = process_job(store, job, create_run=lambda job: called.append('create'),
                         execute=lambda *args: called.append('execute'), payload=lambda *args: {})
    assert status == 'failed'
    assert not called and not store.published
    assert store.failed


def test_worker_import_does_not_start_background_work():
    import importlib
    import threading
    before = {thread.ident for thread in threading.enumerate()}
    importlib.reload(importlib.import_module('mira.preparation_runtime'))
    assert {thread.ident for thread in threading.enumerate()} == before


def test_lease_lost_during_execution_prevents_publication():
    store = Store()
    job = {'id': 'job', 'analysis_run_id': None, 'source_ids': ['source']}
    def execute(run_id, guard, frontier):
        store.alive = False
        return SimpleNamespace(status='draft', reasons=[])
    status = process_job(store, job, create_run=lambda job: 'run', execute=execute,
                         payload=lambda *args: {'unsafe': True})
    assert status == 'lease_lost'
    assert store.published == []


def test_run_attachment_failure_rolls_back_creation(monkeypatch):
    from contextlib import contextmanager
    from uuid import uuid4
    import mira.db
    import mira.pg_store
    import mira.runner
    from mira.preparation_runtime import create_preparation_run
    from mira.budget import RunBudget

    changes = []
    @contextmanager
    def transaction(conn, actor):
        try:
            yield
        except Exception:
            changes.clear()
            raise
    class Connection:
        def execute(self, *args):
            changes.append('marked')
    class FailingStore:
        def set_job_run(self, job, run_id):
            raise ValueError('lease lost')
    def create(*args, **kwargs):
        changes.append('created')
        return SimpleNamespace(analysis_run_id=uuid4())
    monkeypatch.setattr(mira.db, 'acting_as', transaction)
    monkeypatch.setattr(mira.pg_store, 'create_run', create)
    monkeypatch.setattr(mira.runner, 'models_from_env', lambda: {'scout': 'provider:model'})
    source = str(uuid4())
    job = {'actor_id': uuid4(), 'workspace_id': uuid4(), 'source_ids': [source],
           'brief': {'topic': 'AML/CFT', 'jurisdictions': ['HK'], 'period_start': '2025-01-01',
                     'period_end': '2025-12-31', 'as_of_date': '2025-12-31', 'plan_requires_approval': False},
           'budget': {**RunBudget().as_source_limits(), 'max_cost_usd': '1'},
           'models': {'scout': 'provider:model'}, 'settings': {'source_ids': [source]}}
    import pytest
    with pytest.raises(ValueError, match='lease lost'):
        create_preparation_run(Connection(), FailingStore(), job)
    assert changes == []
