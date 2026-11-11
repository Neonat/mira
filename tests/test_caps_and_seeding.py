"""Regressions for four guardrail fixes: exact numbers in the quote check, the coverage
check after budget exhaustion, enforced per-task token caps and category seeding."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

from mira.agents import scout as module
from mira.agents.scout import WebScout, _ScoutRun, seed_plan
from mira.agents.verifier import quote_match
from mira.contracts import LinkSelection, ScoutReport
from mira.extract import Link
from test_orchestrator import E_ENFORCEMENT, E_RULE, MAS, FakeScout, context, make, steps

PASSAGE = ("The Securities and Futures Commission today announced that it has reprimanded and fined "
           "Bank X $3 million for failures in its anti-money laundering controls between 2021 and 2023.")


# --- Fix 4: numbers must match exactly -------------------------------------------------------------------


def test_fuzzy_quote_with_a_wrong_number_is_rejected():
    assert not quote_match("reprimanded and fined Bank X $5 million for failures", PASSAGE)
    assert not quote_match("fined Bank X $30 million", PASSAGE)
    assert not quote_match("controls between 2021 and 2024", PASSAGE)


def test_fuzzy_quote_with_the_right_numbers_still_matches():
    assert quote_match("reprimanded and fined Bank X $3 million for failures", PASSAGE)
    # Small wording differences from extraction noise are still tolerated.
    assert quote_match("it has reprimanded and fined Bank X $3 milion for failures in its anti-money", PASSAGE)


def test_thousands_separators_do_not_count_as_different_numbers():
    passage = "MAS imposed a composition penalty of $300,000 on the trust company for AML/CFT breaches."
    assert quote_match("imposed a composition penalty of $300000 on the trust company", passage)
    assert not quote_match("imposed a composition penalty of $200,000 on the trust company", passage)


# --- Fix 5: the code-only coverage check runs even when the token budget is spent ------------------------


class HungryScout(FakeScout):
    def run(self, ctx, step_id, task):
        return replace(super().run(ctx, step_id, task), tokens_in=10_000)


def test_coverage_is_checked_when_scouting_exhausts_the_budget():
    orchestrator, store, *_ = make(scout=HungryScout())
    outcome = orchestrator.run(context(max_llm_tokens=1_000))

    assert outcome.status == "partial" and "token budget" in outcome.reasons[0]
    assert any(record.role == "completeness_checker" and record.status == "succeeded" for record in steps(store))
    assert {row.expected_source_id for row in store.coverage} == {E_RULE.id, E_ENFORCEMENT.id}
    assert "not checked in this run" not in store.reports[0].html


# --- Fix 6: a task's token cap is checked before each call ----------------------------------------------


def _selection_run(max_llm_tokens, monkeypatch):
    task = SimpleNamespace(max_documents=4, max_llm_tokens=max_llm_tokens, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace()), None, context(), uuid4(), task)
    run.candidates = [Link(f"https://example.org/{i}", "AML circular " * 20, "") for i in range(60)]
    calls = []

    def call_checked(*args, **kwargs):
        calls.append(kwargs["user"])
        return SimpleNamespace(output=LinkSelection(link_labels=[], notes=None), model="s", tokens_in=0, tokens_out=0)

    monkeypatch.setattr(module, "call_checked", call_checked)
    return run, calls


def test_selection_round_is_skipped_when_it_would_crowd_out_the_report(monkeypatch):
    run, calls = _selection_run(4_000, monkeypatch)
    run._select_and_fetch()

    assert calls == []
    assert run.token_stop
    diagnostic = run.selection_diagnostics[0]
    assert diagnostic["stop_reason"] == "token_limit" and diagnostic["presented"] == []
    assert diagnostic["not_sent"] == 60 and len(run.candidates) == 60


def test_selection_round_runs_when_the_cap_has_room(monkeypatch):
    run, calls = _selection_run(200_000, monkeypatch)
    run._select_and_fetch()

    assert len(calls) == 1 and not run.token_stop


def test_report_passages_shrink_and_refuse_an_unfunded_serialized_request():
    task = SimpleNamespace(max_documents=4, max_llm_tokens=None, question="AML", role="regulatory_scout")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace()), None, context(), uuid4(), task)
    assert run._passage_char_budget("header") == module.MAX_PASSAGE_CHARS

    run.task.max_llm_tokens = 60_000
    run.tokens_in = 9_000
    budget = run._passage_char_budget("header")
    assert 0 < budget < module.MAX_PASSAGE_CHARS  # no unfunded minimum floor

    run.tokens_in = 59_000
    assert run._passage_char_budget("header") == 0


# --- Fix 7: code opens every assigned category's index -------------------------------------------------


SFC_LIKE = {
    "feeds": ["https://example.org/rss"],
    "start_urls": ["https://example.org/aml"],
    "category_urls": {
        "circular": ["https://example.org/circular?year={year}"],
        "enforcement": ["https://example.org/enforcement?year={year}"],
        "guideline": ["https://example.org/aml/guideline"],
    },
}


def test_seed_plan_queues_each_category_with_its_years():
    queues, others = seed_plan(SFC_LIKE, ["circular", "enforcement", "guideline"], range(2026, 2024, -1))

    assert queues == [
        ["https://example.org/circular?year=2026", "https://example.org/circular?year=2025"],
        ["https://example.org/enforcement?year=2026", "https://example.org/enforcement?year=2025"],
        ["https://example.org/aml/guideline"],
    ]
    assert others == ["https://example.org/rss", "https://example.org/aml"]


def test_seed_plan_without_category_pages_starts_at_the_first_feed():
    queues, others = seed_plan(SFC_LIKE, ["consultation"], range(2026, 2025, -1))

    assert queues == [["https://example.org/rss"]]
    assert others == ["https://example.org/aml"]


def test_scout_opens_every_assigned_category_before_the_model_chooses(monkeypatch):
    source = replace(MAS, connector_config=SFC_LIKE)
    expected = [replace(E_RULE, id=uuid4(), category=category) for category in ("circular", "enforcement", "guideline")]
    ctx = context()
    task = SimpleNamespace(max_documents=10, source_ids=(source.id,), expected_source_ids=tuple(e.id for e in expected),
                           question="AML", role="regulatory_scout", jurisdiction_code="SG")
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace(), max_rounds=0), None, ctx, uuid4(), task)
    run.store = SimpleNamespace(list_sources=lambda _: [source], list_expected_sources=lambda *args: expected)
    calls = []

    def fetch(url):
        calls.append(url)
        run.allowance -= 1

    monkeypatch.setattr(run, "_fetch", fetch)
    monkeypatch.setattr(run, "_report", lambda: (ScoutReport(documents=[], expected_source_statuses=[], notes=None), {}))
    run.execute()

    years = range(ctx.brief.period_end.year, ctx.brief.period_start.year - 1, -1)
    latest = years[0]
    # One page per category first, then further years, within half the allowance (5 pages).
    assert calls[:3] == [f"https://example.org/circular?year={latest}",
                         f"https://example.org/enforcement?year={latest}",
                         "https://example.org/aml/guideline"]
    assert len(calls) == min(5, 2 * len(years) + 1)
    assert run.allowance == 10 - len(calls)
