"""The single-agent arm runs through the real Orchestrator, with no planner or verifier model (design §5)."""

from mira.llm import ScriptedClient
from mira.orchestrator import Orchestrator
from mira.single_agent import QuoteOnlyVerifier, code_plan
from mira.store import InMemoryStore
from tests.test_orchestrator import (
    E_ENFORCEMENT, E_RULE, MAS, PASSAGES, FakeScout, analyst_output, context, make, writer_output,
)


def single_agent(client, scout):
    store = InMemoryStore(sources=[MAS], expected_sources=[E_RULE, E_ENFORCEMENT], passages=list(PASSAGES))
    orchestrator = Orchestrator(
        store, client, {"regulatory_scout": scout}, QuoteOnlyVerifier(),
        plan_strategy=lambda client, brief, sources, expected, max_documents: code_plan(
            brief, sources, expected, max_documents),
    )
    return orchestrator, store


def test_single_agent_run_calls_no_planner_and_no_verifier_model():
    client = ScriptedClient({"analyst": [analyst_output()], "writer": [writer_output()]})
    orchestrator, store = single_agent(client, FakeScout())
    outcome = orchestrator.run(context(max_gap_rounds=0))

    roles_called = {call.role for call in client.calls}
    assert "planner" not in roles_called  # the plan was built by code
    assert "verifier" not in roles_called  # the quote check decided every verdict
    assert roles_called <= {"analyst", "writer"}
    assert outcome.status == "draft", outcome.reasons


def test_single_agent_plan_is_recorded_as_a_step_with_no_model():
    client = ScriptedClient({"analyst": [analyst_output()], "writer": [writer_output()]})
    orchestrator, store = single_agent(client, FakeScout())
    orchestrator.run(context(max_gap_rounds=0))

    planner_steps = [r for r in store.steps.values() if r.role == "planner"]
    assert len(planner_steps) == 1
    assert planner_steps[0].model is None and planner_steps[0].tokens_in in (None, 0)
    assert store.plans, "the code-built plan is saved like any other plan"


def test_multi_agent_default_still_uses_the_model_planner():
    orchestrator, store, client, _ = make()
    orchestrator.run(context(max_gap_rounds=0))
    assert "planner" in {call.role for call in client.calls}
