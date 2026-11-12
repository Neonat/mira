"""Concurrency overlaps provider work, never coordinator persistence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, get_ident
from types import SimpleNamespace

import pytest

from mira.analysis_batches import AnalysisLimits
from mira.orchestrator import Orchestrator, _Run
from mira.store import InMemoryStore
from mira.store import passage_event
from test_orchestrator import context, PASSAGES, MAS, FakeVerifier, analyst_output
from mira.contracts import AnalystOutput, LabelMap
from mira.agents.analyst import _resolve


class CoordinatorStore(InMemoryStore):
    def __post_init__(self):
        self.owner = get_ident()

    def start_step(self, *args, **kwargs):
        assert get_ident() == self.owner
        return super().start_step(*args, **kwargs)

    def finish_step(self, *args, **kwargs):
        assert get_ident() == self.owner
        return super().finish_step(*args, **kwargs)

    def save_analysis_batch(self, *args, **kwargs):
        assert get_ident() == self.owner
        return super().save_analysis_batch(*args, **kwargs)

    def save_checks(self, *args, **kwargs):
        assert get_ident() == self.owner
        return super().save_checks(*args, **kwargs)


def setup_run(**kwargs):
    store = CoordinatorStore(sources=[MAS], passages={p.id:p for p in PASSAGES})
    store.owner = get_ident()
    ctx = context()
    return _Run(Orchestrator(store, object(), {}, FakeVerifier(), **kwargs), ctx)


def test_analysis_overlaps_calls_but_persists_in_batch_order(monkeypatch):
    run = setup_run(analysis_limits=AnalysisLimits(max_passages=1), max_parallel_analysis=2)
    run.passages = {p.id:p for p in PASSAGES[:2]}
    run.store.append_analysis_events(run.ctx,[passage_event(p,'candidate') for p in run.passages.values()])
    barrier = Barrier(2)
    def analyse(client, brief, passages, **kwargs):
        barrier.wait(timeout=2)
        return SimpleNamespace(claims=[], llm=SimpleNamespace(model='scripted',prompt_version='parallel/test',tokens_in=3,tokens_out=2))
    monkeypatch.setattr('mira.orchestrator.analyst.analyse', analyse)
    run._analyse_batches()
    assert list(run.analysis_terminal) and len(run.analysis_terminal)==2
    assert [step.input_refs['batch_id'] for step in run.store.steps.values()] == ['B1','B2']
    assert run.budget.tokens_used==10


def test_fact_checks_overlap_and_persist_on_coordinator():
    run = setup_run(max_parallel_checks=2)
    run.passages = {p.id:p for p in PASSAGES}
    labels = LabelMap()
    for p in PASSAGES: labels.add('P',p.id)
    output = AnalystOutput.model_validate(analyst_output())
    run.claims = run.store.save_claims(run.ctx, [_resolve(c,labels) for c in output.claims[:2]])
    barrier=Barrier(2)
    class ParallelVerifier(FakeVerifier):
        def check_fact(self, claim, passages, attempt, *, brief=None):
            assert brief == run.ctx.brief
            barrier.wait(timeout=2)
            return super().check_fact(claim,passages,attempt)
    run.o.verifier=ParallelVerifier()
    run._verify()
    assert len(run.verified)==2
    assert run.budget.tokens_used==40


def test_inference_receives_exact_dependency_passages():
    run = setup_run(max_parallel_checks=2)
    run.passages = {p.id:p for p in PASSAGES}
    labels=LabelMap()
    for p in PASSAGES: labels.add('P',p.id)
    output=AnalystOutput.model_validate(analyst_output())
    run.claims=run.store.save_claims(run.ctx,[_resolve(c,labels) for c in output.claims])
    class ContextVerifier(FakeVerifier):
        def check_inference(self, claim, facts, attempt, *, passages=(), brief=None):
            wanted={e.passage_id for f in facts for e in f.evidence}
            assert {p.id for p in passages}==wanted
            return super().check_inference(claim,facts,attempt)
    run.o.verifier=ContextVerifier()
    run._verify()
    assert len(run.verified)==4


def test_rewrite_rechecks_and_freezes_only_revised_citations():
    run = setup_run(max_parallel_checks=2)
    run.passages = {p.id: p for p in PASSAGES}
    run.o.verifier = FakeVerifier({"C1": ["partially_supported", "supported"]})
    labels = LabelMap()
    for p in PASSAGES:
        labels.add("P", p.id)
    draft = AnalystOutput.model_validate(analyst_output()).claims[0]
    original = draft.model_copy(update={"citations": [
        draft.citations[0],
        draft.citations[0].model_copy(update={"passage_label": "P2", "supporting_quote": PASSAGES[1].content}),
    ]})
    run.claims = run.store.save_claims(run.ctx, [_resolve(original, labels)])
    from mira.llm import ScriptedClient
    run.o.client = ScriptedClient({"analyst": [draft.model_dump()]})

    run._verify()

    assert run.claims[0].finding_id in run.verified
    assert [check.attempt for _, check in run.store.checks] == [1, 2]
    assert [set(snapshot["passages"]) for snapshot in run.store.check_inputs] == [
        {str(PASSAGES[0].id), str(PASSAGES[1].id)}, {str(PASSAGES[0].id)},
    ]


def test_cancel_during_dispatch_drains_already_submitted_analysis(monkeypatch):
    from mira.orchestrator import RunCancelled
    run=setup_run(analysis_limits=AnalysisLimits(max_passages=1),max_parallel_analysis=2)
    run.passages={p.id:p for p in PASSAGES[:2]}
    run.store.append_analysis_events(run.ctx,[passage_event(p,'candidate') for p in run.passages.values()])
    checks=[]
    def cancel():
        checks.append(1)
        if len(checks)==2:raise RunCancelled()
    monkeypatch.setattr(run,'_check_cancel',cancel)
    monkeypatch.setattr('mira.orchestrator.analyst.analyse',lambda *a,**kw:SimpleNamespace(claims=[],
        llm=SimpleNamespace(model='scripted',prompt_version='parallel/test',tokens_in=3,tokens_out=2)))
    with pytest.raises(RunCancelled):run._analyse_batches()
    assert [s.status for s in run.store.steps.values()]==['succeeded']
    assert run.budget.tokens_used==5
    assert run.analysis_terminal=={PASSAGES[0].id}


def test_failed_fact_does_not_strand_other_completed_checks():
    from mira.llm import LLMError
    run=setup_run(max_parallel_checks=2)
    run.passages={p.id:p for p in PASSAGES}
    labels=LabelMap()
    for p in PASSAGES:labels.add('P',p.id)
    output=AnalystOutput.model_validate(analyst_output())
    run.claims=run.store.save_claims(run.ctx,[_resolve(c,labels) for c in output.claims[:2]])
    class FailingVerifier(FakeVerifier):
        def check_fact(self,c,passages,attempt):
            if c.label=='C1':raise LLMError('unavailable',request_sent=False)
            return super().check_fact(c,passages,attempt)
    run.o.verifier=FailingVerifier()
    run._verify()
    assert len(run.verified)==1 and len(run.unresolved)==1
    assert [s.status for s in run.store.steps.values()]==['failed','succeeded']


def test_ten_minute_run_preserves_one_minute_for_writer():
    from mira.generation import GenerationBudget
    budget=GenerationBudget(600000,600)
    assert budget.protected_seconds('verifier')==60


def test_analysis_does_not_spend_with_only_a_short_followup_window(monkeypatch):
    from mira.budget import BudgetTracker
    run=setup_run(analysis_limits=AnalysisLimits(max_passages=1),max_parallel_analysis=2)
    run.ctx=replace(run.ctx,budget=replace(run.ctx.budget,max_run_minutes=200/60))
    run.budget=BudgetTracker(run.ctx.budget,clock=lambda:0)
    run.passages={p.id:p for p in PASSAGES[:2]}
    run.store.append_analysis_events(run.ctx,[passage_event(p,'candidate') for p in run.passages.values()])
    def refuse(*args,**kwargs):
        pytest.fail('a 20-second analysis window must not dispatch provider work')
    monkeypatch.setattr('mira.orchestrator.analyst.analyse',refuse)
    run._analyse_batches()
    assert run.store.steps=={}
    assert run.analysis_terminal==set(run.passages)
    assert {e.reason for e in run.store.analysis_events if e.status=='deferred'}=={'time_budget'}


def test_analysis_respects_a_deliberately_shorter_operator_timeout(monkeypatch):
    from mira.budget import BudgetTracker
    run=setup_run(analysis_limits=AnalysisLimits(max_passages=1,timeout_seconds=10),max_parallel_analysis=2)
    run.ctx=replace(run.ctx,budget=replace(run.ctx.budget,max_run_minutes=200/60))
    run.budget=BudgetTracker(run.ctx.budget,clock=lambda:0)
    run.passages={p.id:p for p in PASSAGES[:2]}
    run.store.append_analysis_events(run.ctx,[passage_event(p,'candidate') for p in run.passages.values()])
    def analyse(*args,**kwargs):
        assert kwargs['timeout_seconds']==10
        return SimpleNamespace(claims=[],llm=SimpleNamespace(model='scripted',prompt_version='parallel/test',tokens_in=3,tokens_out=2))
    monkeypatch.setattr('mira.orchestrator.analyst.analyse',analyse)
    run._analyse_batches()
    assert len(run.analysis_terminal)==2
    assert all(s.status=='succeeded' for s in run.store.steps.values())
