from datetime import date

import pytest

from mira.brief import analysis_run_fields, brief_from_rows, check_brief_scope, project_revision_fields
from mira.budget import BudgetExhausted, BudgetTracker, RunBudget
from mira.contracts import Brief

BRIEF = Brief(
    topic="AML/CFT", jurisdictions=["SG", "HK"], period_start=date(2025, 10, 1), period_end=date(2026, 9, 30),
    as_of_date=date(2026, 10, 26), plan_requires_approval=True,
)


def test_brief_round_trips_through_project_revision_and_run_rows():
    revision = project_revision_fields(BRIEF, "new brief")
    run = analysis_run_fields(BRIEF, RunBudget(), {"planner": "anthropic:claude-opus-5-5"})
    assert brief_from_rows(revision, run) == BRIEF
    assert run["source_limits"]["max_gap_rounds"] == 2


def test_brief_scope_uses_controlled_lists():
    check_brief_scope(BRIEF)
    for jurisdictions in (["US"], ["SG", "SG"]):
        with pytest.raises(ValueError):
            check_brief_scope(BRIEF.model_copy(update={"jurisdictions": jurisdictions}))


def test_budget_reads_environment():
    budget = RunBudget.from_env({"MIRA_MAX_FETCHED_DOCUMENTS": "5", "MIRA_MAX_RUN_MINUTES": "0.5"})
    assert (budget.max_fetched_documents, budget.max_run_minutes, budget.max_llm_tokens) == (5, 0.5, 2_000_000)


def test_tracker_stops_on_tokens_and_time():
    now = [0.0]
    tracker = BudgetTracker(RunBudget(max_llm_tokens=100, max_run_minutes=1), clock=lambda: now[0])
    tracker.charge_tokens(60, 30)
    tracker.check()
    tracker.charge_tokens(10, None)
    with pytest.raises(BudgetExhausted, match="token"):
        tracker.check()

    tracker = BudgetTracker(RunBudget(max_run_minutes=1), clock=lambda: now[0])
    now[0] = 61
    with pytest.raises(BudgetExhausted, match="time"):
        tracker.check()


def test_document_allowance_never_goes_negative():
    tracker = BudgetTracker(RunBudget(max_fetched_documents=3))
    tracker.charge_documents(5)
    assert tracker.remaining_documents() == 0
