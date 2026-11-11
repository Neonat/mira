"""Background preparation persists machine evidence without generating a report."""
from test_passage_analysis_coverage import make_run,factual
from test_orchestrator import context,PASSAGES
from mira.orchestrator import RunCancelled


def test_preparation_stops_before_writer_and_retains_all_checked_facts():
    worker,store,client=make_run([factual(p) for p in PASSAGES])
    outcome=worker.run(context(),preparation=True)
    assert outcome.status=='draft'
    assert outcome.report_id is outcome.snapshot is None
    assert len(store.claims)==3
    assert store.reports==[]
    assert not any(c.role=='writer' for c in client.calls)


def test_lost_preparation_lease_stops_before_any_acquisition():
    worker,store,client=make_run([])
    def fence():raise RunCancelled()
    outcome=worker.run(context(),preparation=True,preparation_guard=fence)
    assert outcome.status=='cancelled'
    assert client.calls==[] and store.reports==[]


def test_repeated_preparation_spends_on_unanalysed_passages_not_reused_text():
    worker,store,client=make_run([factual(PASSAGES[1]),factual(PASSAGES[2])])
    store.previously_prepared_passages=lambda ctx:{PASSAGES[0].id}
    result=worker.run(context(),preparation=True)
    assert result.status=='draft',result.reasons
    assert len([c for c in client.calls if c.role=='analyst'])==2
    assert {c.draft.content for c in store.claims.values()}=={p.content for p in PASSAGES[1:]}
    assert any(e.passage_id==PASSAGES[0].id and e.reason=='prepared_snapshot_reuse' for e in store.analysis_events)
