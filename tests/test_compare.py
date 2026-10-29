"""The comparison refuses any verdict that is not from live, measured runs (PRD v2 §11)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from compare import Measured, decide  # noqa: E402


def live(arm, coverage):
    return Measured(arm=arm, live=True, coverage=coverage, cost_usd=1.0, seconds=60.0)


def scripted(arm, coverage):
    return Measured(arm=arm, live=False, coverage=coverage, cost_usd=0.0, seconds=0.0)


def test_no_verdict_when_an_arm_is_missing():
    verdict = decide({"plain_search": live("plain_search", 0.2), "single_agent": live("single_agent", 0.4)})
    assert not verdict.ready and "multi_agent" in verdict.message


def test_no_verdict_from_scripted_output_even_when_the_numbers_look_decisive():
    arms = {
        "plain_search": live("plain_search", 0.10),
        "single_agent": live("single_agent", 0.40),
        "multi_agent": scripted("multi_agent", 0.95),  # a scripted run must never win a comparison
    }
    verdict = decide(arms)
    assert not verdict.ready and "without a live run" in verdict.message and "multi_agent" in verdict.message


def test_no_verdict_when_coverage_was_not_measured():
    arms = {
        "plain_search": live("plain_search", 0.2),
        "single_agent": live("single_agent", None),
        "multi_agent": live("multi_agent", 0.6),
    }
    verdict = decide(arms)
    assert not verdict.ready and "single_agent" in verdict.message


def test_a_live_multi_agent_that_beats_the_single_agent_is_reported_with_the_precision_caveat():
    arms = {
        "plain_search": live("plain_search", 0.2),
        "single_agent": live("single_agent", 0.5),
        "multi_agent": live("multi_agent", 0.7),
    }
    verdict = decide(arms)
    assert verdict.ready and "beats the single agent" in verdict.message and "human check" in verdict.message


def test_a_live_multi_agent_that_does_not_beat_the_single_agent_does_not_justify_its_cost():
    arms = {
        "plain_search": live("plain_search", 0.2),
        "single_agent": live("single_agent", 0.6),
        "multi_agent": live("multi_agent", 0.6),
    }
    verdict = decide(arms)
    assert verdict.ready and "does not yet justify its cost" in verdict.message
