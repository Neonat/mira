"""The live three-arm runner: what a report cites, the precision worksheet, and how liveness is read back."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from compare import Measured  # noqa: E402
from run_live import (  # noqa: E402
    Evidence, Finding, RunRecords, cited_urls, claim_rows, coverage_of, report_finding_ids, sample_id, write_summary,
)

FACT_A, FACT_B, INFERENCE, UNCITED = "f-a", "f-b", "inf", "f-uncited"
RECORDS = RunRecords(
    findings={
        FACT_A: Finding("HKMA PEP guidance", "HKMA issued guidance on PEP controls.", False),
        FACT_B: Finding("SFC layering circular", "SFC issued a circular on layering.", False),
        INFERENCE: Finding("Trend", "Supervisors focus on risk-based controls.", True),
        UNCITED: Finding("Unverified", "Not in the report.", False),
    },
    evidence={
        FACT_A: [Evidence("https://brdr.hkma.gov.hk/a", "guidance on PEP controls", "Passage A text")],
        FACT_B: [Evidence("https://apps.sfc.hk/b", "a circular on layering", "Passage B text")],
        UNCITED: [Evidence("https://example.org/never", "x", "y")],
    },
    depends_on={INFERENCE: [FACT_B]},
)


def snapshot(*sentences):
    return {"sections": [{"section": "executive_summary", "no_verified_items": False, "sentences": list(sentences)}]}


def sentence(ids, structural=False):
    return {"text": "t", "finding_ids": ids, "structural": structural}


def test_structural_sentences_cite_nothing():
    snap = snapshot(sentence([FACT_A]), sentence([UNCITED], structural=True), sentence([FACT_A, INFERENCE]))
    assert report_finding_ids(snap) == [FACT_A, INFERENCE]


def test_cited_urls_follow_an_inference_to_the_facts_it_rests_on():
    # The report cites only the inference; its fact's source still counts for recall.
    assert cited_urls([INFERENCE], RECORDS) == ["https://apps.sfc.hk/b"]
    assert cited_urls([FACT_A, INFERENCE], RECORDS) == ["https://brdr.hkma.gov.hk/a", "https://apps.sfc.hk/b"]


def test_a_finding_the_report_does_not_cite_never_counts():
    assert "https://example.org/never" not in cited_urls([FACT_A, INFERENCE], RECORDS)


def test_worksheet_rows_show_the_passage_for_a_fact_and_the_facts_for_an_inference():
    rows = {row.sample_id: row for row in claim_rows("multi_agent", [FACT_A, INFERENCE], RECORDS)}
    fact = rows[sample_id("multi_agent", FACT_A)]
    assert "Passage A text" in fact.cited_passage and fact.supporting_quote == "guidance on PEP controls"
    inference = rows[sample_id("multi_agent", INFERENCE)]
    assert "SFC layering circular" in inference.cited_passage and inference.supporting_quote == ""


def test_sample_ids_are_stable_and_differ_between_arms():
    assert sample_id("multi_agent", FACT_A) == sample_id("multi_agent", FACT_A)
    assert sample_id("multi_agent", FACT_A) != sample_id("single_agent", FACT_A)


def test_an_arm_without_a_report_has_no_coverage():
    assert coverage_of({"recall": None}) is None
    assert coverage_of({"recall": {"all": {"found": 6, "total": 24}}}) == 0.25


def test_liveness_is_read_from_recorded_models_not_from_the_results_file():
    real = Measured.from_recorded_models("single_agent", [None, "claude-opus-5-5", "claude-sonnet-5-5"], 0.5, 1.0, 60)
    assert real.live
    assert not Measured.from_recorded_models("single_agent", [None, "scripted"], 0.5, 0.0, 1).live
    assert not Measured.from_recorded_models("single_agent", [None, None], 0.5, 0.0, 1).live  # no model answered
    assert not Measured.from_recorded_models("multi_agent", ["claude-opus-5-5", "scripted"], 0.5, 1.0, 60).live


def test_summary_table_states_precision_and_the_verdict(tmp_path):
    summary = {
        "created_at": "20261104T000000Z",
        "brief": {"topic": "AML/CFT", "jurisdictions": ["SG", "HK"], "period_start": "2025-10-26",
                  "period_end": "2026-10-26"},
        "order": ["multi_agent", "single_agent", "plain_search"],
        "arms": {
            "multi_agent": {"status": "draft", "recall": {k: {"found": 9, "total": 24} for k in
                                                          ("all", "fetchable", "regulatory")},
                            "cost_usd": 1.2, "seconds": 600},
            "single_agent": {"status": "partial", "recall": None, "cost_usd": 0.5, "seconds": 300},
            "plain_search": {"status": "draft", "recall": {k: {"found": 3, "total": 24} for k in
                                                           ("all", "fetchable", "regulatory")},
                             "cost_usd": 0.0, "seconds": 1},
        },
    }
    precision = {"multi_agent": {"supported": 28, "labelled": 30, "unlabelled": 0, "rate": 28 / 30},
                 "single_agent": {"supported": 0, "labelled": 0, "unlabelled": 30, "rate": None}}
    write_summary(tmp_path, summary, "not decided: test", precision)
    text = (tmp_path / "summary.md").read_text()
    assert "| multi_agent | draft | 9/24 | 9/24 | 9/24 | 28/30 |" in text
    assert "| single_agent | partial | - | - | - | 30 unlabelled |" in text
    assert "| plain_search | draft | 3/24 | 3/24 | 3/24 | n/a |" in text
    assert "**Verdict:** not decided: test" in text


def test_single_agent_builder_uses_the_code_plan_and_the_quote_only_verifier(monkeypatch):
    import mira.runner as runner
    from mira.agents import planner
    from mira.single_agent import QuoteOnlyVerifier

    class Store:
        def __init__(self, conn):
            pass

        def list_sources(self, workspace):
            return []

    monkeypatch.setattr(runner, "PostgresStore", Store)
    monkeypatch.setattr(runner, "WebScout", lambda dsn, client, fetcher: object())
    orchestrator = runner.build_single_agent_orchestrator(None, "dsn", None, client=object())
    assert isinstance(orchestrator.verifier, QuoteOnlyVerifier)
    assert set(orchestrator.scouts) == {"regulatory_scout"}
    assert orchestrator.plan_strategy is not planner.plan
