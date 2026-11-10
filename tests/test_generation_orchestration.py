from dataclasses import replace

from mira.llm import LLMError
from mira.analysis_batches import AnalysisLimits
from test_passage_analysis_coverage import make_run
from test_orchestrator import context,FakeScout


def test_preflight_analysis_refusal_has_no_unknown_spend():
    run,store,_=make_run([LLMError('admission',request_sent=False)]*3)
    run.run(context())
    failed=[s for s in store.steps.values() if s.role=='analyst' and s.status=='failed']
    assert failed and all(not s.output_refs.get('reserved_tokens') for s in failed)


def test_explicit_unknown_analysis_reserve_is_charged_once():
    run,store,_=make_run([LLMError('attempted',request_sent=True,reserved_tokens=123)]*3)
    run.run(context())
    failed=[s for s in store.steps.values() if s.role=='analyst' and s.status=='failed']
    assert [s.output_refs.get('reserved_tokens') for s in failed]==[123]*3


def test_scout_unknown_reservations_are_not_lost():
    class UnknownScout(FakeScout):
        def run(self,ctx,step_id,task):
            out=super().run(ctx,step_id,task)
            result=out.result.model_copy(update={'selection_diagnostics':{'generation_usage':{'reserved_tokens':321}}})
            return replace(out,result=result)
    run,store,_=make_run([{'claims':[]}]*3)
    run.scouts={'regulatory_scout':UnknownScout()};run.run(context())
    scout=next(s for s in store.steps.values() if s.role=='regulatory_scout')
    assert scout.output_refs['generation_usage']['reserved_tokens']==321


def test_analysis_defaults_bound_per_call_work():
    limits=AnalysisLimits()
    assert (limits.max_passages,limits.max_characters,limits.timeout_seconds)==(8,12000,180)


def test_scout_selected_passage_precedes_bulk_version_expansion():
    from test_orchestrator import PASSAGES
    from test_passage_analysis_coverage import factual
    run,store,_=make_run([factual(PASSAGES[2])],limits=AnalysisLimits(max_passages=1,max_batches=1,reserve_tokens=0,reserve_seconds=0))
    run.scouts={'regulatory_scout':FakeScout(labels={'P1':PASSAGES[2].id})}
    result=run.run(context())
    assert store.claims and next(iter(store.claims.values())).draft.content==PASSAGES[2].content
    attempted=[e.passage_id for e in store.analysis_events if e.status=='attempted']
    assert attempted==[PASSAGES[2].id]
