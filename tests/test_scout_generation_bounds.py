from types import SimpleNamespace

import pytest

from mira.agents import scout
from mira.llm import LLMError, LLMResult


def run_stub(client, *, remaining=30):
    run = scout._ScoutRun.__new__(scout._ScoutRun)
    run.scout = SimpleNamespace(client=client)
    run.task = SimpleNamespace(max_llm_tokens=None)
    run.tokens_in = run.tokens_out = 0
    run.hybrid_tokens = run.hybrid_reserved_tokens = 0
    run.generation_reserved_tokens = 0
    run._remaining_seconds = lambda: remaining
    return run


def test_report_passage_budget_is_bounded_and_respects_smaller_token_allowance():
    run = run_stub(None)
    assert run._passage_char_budget('header') == 16000
    run.task.max_llm_tokens = 11000
    assert run._passage_char_budget('header') <= 8000


def test_report_adapter_bounds_request_and_keeps_ordinary_clients_compatible():
    class Bounded:
        def structured_bounded(self, **kwargs):
            assert 0 < kwargs.pop('timeout_seconds') <= 30
            assert kwargs.pop('max_output_tokens') == 16384
            return LLMResult('ok', 'fake', 'v', 5, 2)

    kwargs = dict(role='regulatory_scout', system='s', user='u', output_type=scout.ScoutReport, prompt_version='v')
    assert scout._SummaryClient(run_stub(Bounded())).structured(**kwargs).output == 'ok'
    class Ordinary:
        def structured(self, **kwargs):
            return LLMResult('fallback', 'fake', 'v', 5, 2)
    assert scout._SummaryClient(run_stub(Ordinary())).structured(**kwargs).output == 'fallback'


def test_bounded_unknown_usage_is_reserved_but_preflight_failure_is_not():
    class Failing:
        def __init__(self, sent): self.sent = sent
        def structured_bounded(self, **kwargs):
            error = LLMError('failure')
            error.request_sent = self.sent
            error.reserved_tokens = 1234
            raise error
    for sent, expected in [(True, 1234), (False, 0)]:
        run = run_stub(Failing(sent))
        with pytest.raises(LLMError):
            scout._SummaryClient(run).structured(role='regulatory_scout', system='s', user='u', output_type=scout.ScoutReport, prompt_version='v')
        assert run.generation_reserved_tokens == expected


def test_whole_passage_cap_keeps_round_robin_and_reports_omissions():
    import threading
    from datetime import date
    from uuid import uuid4

    ids = [uuid4() for _ in range(4)]
    source = uuid4()
    passages = [SimpleNamespace(id=ids[i], source_id=source, source_url=f'https://example.org/{i // 2}',
                                content=chr(97 + i) * 6000, published_at=date(2025, 1, 1)) for i in range(4)]
    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
    class Conn:
        def execute(self, sql, args):
            return Cursor([{'id': item} for item in ids] if 'p.id = any' in sql else [])
    run = run_stub(None)
    run.conn = Conn()
    run.visits = [scout._Visit('https://example.org', uuid4(), ids)]
    run.scout = SimpleNamespace(_fetch_lock=threading.Lock(), _pages={}, hybrid=None)
    run.ctx = SimpleNamespace(workspace_id=uuid4(), analysis_run_id=uuid4(), brief=SimpleNamespace(
        jurisdictions=['AU'], as_of_date=date(2026, 1, 1), period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31), topic='test'))
    run.task = SimpleNamespace(jurisdiction_code='AU', source_ids=[source], question='test')
    run.store = SimpleNamespace(get_passages=lambda workspace, requested: passages)
    selected = run._passages(16000)
    assert [p.id for p in selected] == [ids[0], ids[2]]
    assert [len(p.content) for p in selected] == [6000, 6000]
    assert run.visits[0].passage_ids == ids
    assert run.summary_diagnostics['omitted_passages'] == 2
    assert run.summary_diagnostics['omission_reason']


def test_report_rejects_labels_for_unshown_passages(monkeypatch):
    from uuid import uuid4
    from mira.llm import ScriptedClient, LLMOutputError
    shown = uuid4()
    doc = {'document_label': 'D1', 'instrument_type': None, 'industry_category': None,
           'title': 'Example', 'published_date': None, 'effective_date': None, 'change_type': None,
           'relevant_passage_labels': ['P2'], 'expected_source_labels': []}
    client = ScriptedClient(responses={'regulatory_scout': [
        {'documents': [doc], 'expected_source_statuses': [], 'notes': None},
        {'documents': [doc], 'expected_source_statuses': [], 'notes': None},
    ]})
    run = run_stub(client)
    run.ctx = SimpleNamespace(workspace_id=uuid4(), brief=SimpleNamespace(topic='x', jurisdictions=['AU']))
    run.task = SimpleNamespace(expected_source_ids=[], question='x', role='regulatory_scout', max_llm_tokens=None)
    run.store = SimpleNamespace(list_expected_sources=lambda *args: [])
    run.summary_diagnostics = None
    run._passages = lambda budget: [SimpleNamespace(id=shown)]
    monkeypatch.setattr(scout, 'brief_text', lambda brief: 'brief')
    monkeypatch.setattr(scout, 'quote_passage', lambda label, passage: f'{label}: evidence')
    with pytest.raises(LLMOutputError):
        run._report()


def test_report_marks_no_change_missing_without_shown_inspection_evidence(monkeypatch):
    from uuid import uuid4
    from mira.llm import ScriptedClient, LLMOutputError
    expected_id, shown = uuid4(), uuid4()
    status = {'expected_source_label': 'E1', 'status': 'no_change', 'note': None,
              'inspected_passage_labels': []}
    client = ScriptedClient(responses={'regulatory_scout': [
        {'documents': [], 'expected_source_statuses': [status], 'notes': None},
        {'documents': [], 'expected_source_statuses': [status], 'notes': None},
    ]})
    run = run_stub(client)
    run.ctx = SimpleNamespace(workspace_id=uuid4(), brief=SimpleNamespace(topic='x', jurisdictions=['AU']))
    run.task = SimpleNamespace(expected_source_ids=[expected_id], question='x', role='regulatory_scout', max_llm_tokens=None)
    row = SimpleNamespace(id=expected_id, jurisdiction_code='AU', category='guidance', document_hint='guidance')
    run.store = SimpleNamespace(list_expected_sources=lambda *args: [row])
    run.summary_diagnostics = None
    run._passages = lambda budget: [SimpleNamespace(id=shown)]
    monkeypatch.setattr(scout, 'brief_text', lambda brief: 'brief')
    monkeypatch.setattr(scout, 'quote_passage', lambda label, passage: f'{label}: evidence')
    report, _ = run._report()
    assert report.expected_source_statuses[0].status == "missing"


def test_report_preflight_rejection_sends_no_request_and_reserves_nothing():
    class NeverCalled:
        def structured_bounded(self, **kwargs):
            pytest.fail('preflight sent a request')
    run = run_stub(NeverCalled())
    run.task.max_llm_tokens = 100
    with pytest.raises(LLMError) as caught:
        scout._SummaryClient(run).structured(role='regulatory_scout', system='s', user='u',
                                             output_type=scout.ScoutReport, prompt_version='v')
    assert caught.value.request_sent is False
    assert run.generation_reserved_tokens == 0


def test_scout_failure_carries_unknown_reservation_and_known_usage(monkeypatch):
    from contextlib import nullcontext
    from mira.interfaces import ScoutFailure
    class FailingRun:
        def __init__(self, *args):
            self.tokens_in, self.tokens_out = 3, 4
            self.discovery, self.selection_diagnostics, self.log = [], [], []
            self.discovery_omitted, self.allowance = 0, 1
            self.hybrid_diagnostics = self.summary_diagnostics = None
            self.generation_reserved_tokens = 0
            self.model = 'fake'
        def execute(self):
            raise LLMError('timeout', 5, 6, request_sent=True, reserved_tokens=1234)
    monkeypatch.setattr(scout, 'connect', lambda dsn: nullcontext(None))
    monkeypatch.setattr(scout, '_ScoutRun', FailingRun)
    runner = scout.WebScout('dsn', None, None)
    with pytest.raises(ScoutFailure) as caught:
        runner.run(None, None, None)
    assert caught.value.selection_diagnostics['generation_usage']['reserved_tokens'] == 1234
    assert (caught.value.tokens_in, caught.value.tokens_out) == (8, 10)
