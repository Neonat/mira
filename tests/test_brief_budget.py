from datetime import date
from uuid import uuid4

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


def test_report_file_is_bound_to_the_selected_run_version_and_review_status(tmp_path):
    from mira.config import report_file

    reports = tmp_path / "reports"
    run_id = uuid4()
    draft = reports / str(run_id) / "report-v1.html"
    signed = reports / str(run_id) / "report-v2-reviewed.html"
    draft.parent.mkdir(parents=True)
    draft.write_text("<p>draft</p>")
    signed.write_text("<p>reviewed</p>")
    (tmp_path / "outside.html").write_text("<p>outside</p>")

    def lookup(path, *, run=run_id, version=1, reviewed=False):
        return report_file(path, run_id=run, version=version, reviewed=reviewed, reports_dir=reports)

    draft_relative = draft.relative_to(reports).as_posix()
    signed_relative = signed.relative_to(reports).as_posix()
    assert lookup(draft_relative) == draft.resolve()
    assert lookup(signed_relative, version=2, reviewed=True) == signed.resolve()
    assert lookup(draft_relative, run=uuid4()) is None
    assert lookup(draft_relative, version=2) is None
    assert lookup(signed_relative, version=2) is None
    for path in ("../outside.html", str(draft), "", None):
        assert lookup(path) is None

    missing = f"{run_id}/report-v3.html"
    assert lookup(missing, version=3) is None
    (reports / missing).symlink_to(draft)
    assert lookup(missing, version=3) is None


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
