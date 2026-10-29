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


def test_report_file_stays_inside_the_reports_folder(tmp_path):
    from mira.config import report_file

    reports = tmp_path / "reports"
    (reports / "run").mkdir(parents=True)
    (reports / "run" / "report-v1.html").write_text("<p>ok</p>")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=secret")
    (tmp_path / "outside.html").write_text("<p>outside</p>")
    assert report_file("run/report-v1.html", reports) == (reports / "run" / "report-v1.html").resolve()
    for path in ("../.env", "../outside.html", "/etc/passwd", "run/missing.html", "", None):
        assert report_file(path, reports) is None


def test_blank_budget_values_fall_back_to_defaults():
    budget = RunBudget.from_env({"MIRA_MAX_LLM_TOKENS": " ", "MIRA_MAX_FETCHED_DOCUMENTS": ""})
    assert (budget.max_llm_tokens, budget.max_fetched_documents) == (RunBudget().max_llm_tokens, RunBudget().max_fetched_documents)


def test_rerun_is_allowed_only_after_a_finished_run():
    from mira.brief import RERUNNABLE_STATUSES, check_rerunnable

    for status in ("draft", "reviewed", "superseded"):
        check_rerunnable(status)
    for status in ("queued", "running", "partial", "failed", "cancelled"):
        with pytest.raises(ValueError, match="cannot be re-run"):
            check_rerunnable(status)
    assert RERUNNABLE_STATUSES == {"draft", "reviewed", "superseded"}
