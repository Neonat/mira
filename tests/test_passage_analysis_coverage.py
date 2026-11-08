"""Whole stored versions reach bounded analysis; omitted work remains explicit."""
from dataclasses import replace

from mira.analysis_batches import AnalysisLimits
from mira.llm import LLMError, ScriptedClient
from mira.orchestrator import Orchestrator
from mira.store import InMemoryStore
from test_orchestrator import (
    E_ENFORCEMENT, E_RULE, MAS, PASSAGES, FakeScout, FakeVerifier,
    analyst_output, claim, context, plan_task, writer_output,
)


def make_run(outputs, *, limits=None, client=None, store=None):
    store = store or InMemoryStore(sources=[MAS], expected_sources=[E_RULE, E_ENFORCEMENT], passages=list(PASSAGES))
    client = client or ScriptedClient({
        "planner": [{"tasks": [plan_task()], "notes": None}],
        "analyst": outputs, "writer": [writer_output()],
    })
    limits = limits or AnalysisLimits(max_passages=1, reserve_tokens=0, reserve_seconds=0)
    orchestrator = Orchestrator(store, client, {"regulatory_scout": FakeScout(labels={"P1": PASSAGES[0].id})},
                                FakeVerifier(), analysis_limits=limits)
    return orchestrator, store, client


def factual(passage):
    return analyst_output(claim("C1", "external_fact", "P1", passage.content, content=passage.content))


def test_all_saved_passages_of_selected_version_are_analysed_not_only_scout_label():
    run, store, client = make_run([factual(p) for p in PASSAGES])
    result = run.run(context())
    assert result.status == "draft", result.reasons
    assert {c.draft.content for c in store.claims.values()} == {p.content for p in PASSAGES}
    assert {c.label for c in store.claims.values()} == {"C1", "C2", "C3"}
    summary = result.snapshot.analysis_coverage
    assert (summary.candidate_passages, summary.attempted_passages, summary.analysed_passages) == (3, 3, 3)
    assert summary.deferred_passages == summary.failed_passages == summary.pending_passages == 0
    assert 'Passage analysis coverage' in store.reports[-1].html
    assert all(p.content in store.reports[-1].html for p in PASSAGES)
    assert len([c for c in client.calls if c.role == 'analyst']) == 3


def test_batch_cap_defers_unread_passages_and_marks_partial():
    limits = AnalysisLimits(max_passages=1, max_batches=1, reserve_tokens=0, reserve_seconds=0)
    run, store, client = make_run([factual(PASSAGES[0])], limits=limits)
    result = run.run(context())
    assert result.status == 'partial'
    summary = result.snapshot.analysis_coverage
    assert (summary.analysed_passages, summary.deferred_passages) == (1, 2)
    assert any('batch_limit' in event.reason for event in store.analysis_events if event.status == 'deferred')
    assert len([c for c in client.calls if c.role == 'analyst']) == 1


def test_later_failed_batch_preserves_prior_and_subsequent_claims():
    run, store, client = make_run([factual(PASSAGES[0]), LLMError('scripted failure', 7, 3), factual(PASSAGES[2])])
    result = run.run(context())
    assert result.status == 'partial'
    assert {c.draft.content for c in store.claims.values()} == {PASSAGES[0].content, PASSAGES[2].content}
    summary = result.snapshot.analysis_coverage
    assert (summary.analysed_passages, summary.failed_passages, summary.attempted_passages) == (2, 1, 3)
    assert len([c for c in client.calls if c.role == 'analyst']) == 3
    assert PASSAGES[0].content in store.reports[-1].html


def test_valid_empty_model_output_still_records_passages_as_processed():
    run, _, _ = make_run([{'claims': []}] * 3)
    result = run.run(context())
    assert result.status == 'draft', result.reasons
    assert result.snapshot.analysis_coverage.analysed_passages == 3
    assert result.snapshot.analysis_coverage.failed_passages == 0


def test_insufficient_reserve_defers_before_any_analyst_call():
    limits = AnalysisLimits(max_passages=1, reserve_tokens=1_000_000, reserve_seconds=0)
    run, store, client = make_run([], limits=limits)
    result = run.run(context(max_llm_tokens=200_000))
    assert result.status == 'partial'
    assert result.snapshot.analysis_coverage.deferred_passages == 3
    assert not any(c.role == 'analyst' for c in client.calls)
    assert all(e.reason == 'token_budget' for e in store.analysis_events if e.status == 'deferred')


def test_failed_unknown_usage_has_separate_reservation_and_no_successful_disposition():
    run, store, _ = make_run([LLMError('unknown usage'), factual(PASSAGES[1]), factual(PASSAGES[2])])
    result = run.run(context())
    assert result.status == 'partial'
    assert result.snapshot.analysis_coverage.failed_passages == 1
    failed = [s for s in store.steps.values() if s.role == 'analyst' and s.status == 'failed']
    assert len(failed) == 1 and failed[0].output_refs['reserved_tokens'] > 0
    assert failed[0].tokens_in is None and failed[0].tokens_out is None


def test_character_and_time_stops_are_frozen_as_readable_reasons():
    for limits, reason in ((AnalysisLimits(max_characters=1), 'input_limit'),
                           (AnalysisLimits(reserve_seconds=2000, reserve_tokens=0), 'time_budget')):
        run, store, client = make_run([], limits=limits)
        result = run.run(context())
        assert result.status == 'partial'
        assert result.snapshot.analysis_coverage.documents[0].reason_counts == {reason: 3}
        assert reason.replace('_', ' ') in store.reports[-1].html
        assert not any(c.role == 'analyst' for c in client.calls)


def test_saved_fetch_is_analysed_even_when_scout_selects_no_document():
    from mira.interfaces import ScoutOutcome
    class NoSelection(FakeScout):
        def run(self, ctx, step_id, task):
            out = super().run(ctx,step_id,task)
            report = out.result.report.model_copy(update={'documents':[]})
            return replace(out, result=out.result.model_copy(update={'report':report,'labels':{}}))
    run, store, _ = make_run([factual(p) for p in PASSAGES])
    run.scouts = {'regulatory_scout':NoSelection()}
    result = run.run(context())
    assert result.snapshot.analysis_coverage.analysed_passages == 3
    assert len(store.claims) == 3


def test_cancellation_between_batches_preserves_ledger_and_first_claim():
    run, store, _ = make_run([])
    def stop_after_first(prompt):
        store.cancel = True
        return factual(PASSAGES[0])
    run.client = ScriptedClient({'planner':[{'tasks':[plan_task()], 'notes':None}], 'analyst':[stop_after_first]})
    ctx = context()
    result = run.run(ctx)
    assert result.status == 'cancelled'
    assert len(store.claims) == 1 and not store.reports
    coverage = store.analysis_coverage(ctx)
    assert coverage.analysed_passages == 1 and coverage.deferred_passages == 2
    assert coverage.documents[0].reason_counts == {'cancelled':2}


def test_legacy_report_serialization_has_no_invented_analysis_coverage():
    from mira.contracts import ReportSnapshot
    value = dict(contract_version='1.4', analysis_run_id=context().analysis_run_id,
                 analysis_revision_id=context().analysis_revision_id, sections=[], coverage=[], unresolved_finding_ids=[])
    assert 'analysis_coverage' not in ReportSnapshot(**value).model_dump()


def test_frozen_report_rejects_wrong_coverage_scope_and_keeps_saved_reasons():
    from test_render import fixture, AT
    from mira.render import frozen_context
    import pytest
    snapshot, _, _ = fixture()
    run, store, _ = make_run([], limits=AnalysisLimits(max_characters=1))
    result = run.run(context())
    summary = result.snapshot.analysis_coverage.model_copy(update={
        'workspace_id':snapshot.evidence_bundle.workspace_id, 'analysis_run_id':snapshot.analysis_run_id,
        'analysis_revision_id':snapshot.analysis_revision_id})
    snapshot = snapshot.model_copy(update={'contract_version':'1.6','analysis_coverage':summary})
    frozen_context(snapshot,AT)
    broken = summary.model_copy(update={'analysis_run_id':context().analysis_run_id})
    with pytest.raises(ValueError, match='coverage scope'):
        frozen_context(snapshot.model_copy(update={'analysis_coverage':broken}),AT)


def test_saved_inspection_reference_expands_version_even_without_new_fetch():
    from mira.contracts import ExpectedSourceStatusDraft
    class InspectionOnly(FakeScout):
        def run(self,ctx,step_id,task):
            out=super().run(ctx,step_id,task)
            report=out.result.report.model_copy(update={'documents':[], 'expected_source_statuses':[
                ExpectedSourceStatusDraft(expected_source_label='E1',status='no_change',note='fixture inspection',
                                          inspected_passage_labels=['P1'])]})
            return replace(out,result=out.result.model_copy(update={'report':report,'fetch_log':[]}))
    run,store,_=make_run([factual(p) for p in PASSAGES])
    run.scouts={'regulatory_scout':InspectionOnly(labels={'P1':PASSAGES[0].id})}
    result=run.run(context())
    assert result.snapshot.analysis_coverage.analysed_passages==3
    assert len(store.claims)==3
