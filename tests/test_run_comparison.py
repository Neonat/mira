"""End to end, with scripted clients: the comparison scores every arm and still refuses a verdict (step 6)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from run_comparison import ArmOutput, compare  # noqa: E402
from score_recall import load_items  # noqa: E402

from mira.llm import AnthropicClient, ScriptedClient  # noqa: E402

GROUND_TRUTH = load_items(Path(__file__).parent.parent / "eval" / "m0_ground_truth.csv")
FETCHABLE = [item.url for item in GROUND_TRUTH if item.reach == "fetchable"]


def test_scripted_arms_are_scored_but_refused_a_verdict():
    arms = {
        "plain_search": ArmOutput("plain_search", FETCHABLE[:4], ScriptedClient({}), 0.0, 0.0),
        "single_agent": ArmOutput("single_agent", FETCHABLE[:8], ScriptedClient({}), 0.0, 0.0),
        "multi_agent": ArmOutput("multi_agent", FETCHABLE[:12], ScriptedClient({}), 0.0, 0.0),
    }
    measured, verdict = compare(GROUND_TRUTH, arms)
    assert all(m.live is False for m in measured.values())
    assert measured["multi_agent"].coverage > measured["single_agent"].coverage  # the scores are real
    assert not verdict.ready and "without a live run" in verdict.message


def test_a_verdict_needs_every_arm_to_be_a_real_model_client():
    live = AnthropicClient(client=object())  # a real client type, constructed without any network call
    arms = {
        "plain_search": ArmOutput("plain_search", FETCHABLE[:4], ScriptedClient({}), 0.0, 0.0),
        "single_agent": ArmOutput("single_agent", FETCHABLE[:8], live, 1.0, 60.0),
        "multi_agent": ArmOutput("multi_agent", FETCHABLE[:12], live, 2.0, 90.0),
    }
    _, verdict = compare(GROUND_TRUTH, arms)
    assert not verdict.ready and "plain_search" in verdict.message  # the scripted baseline still blocks it


def test_coverage_is_measured_the_same_way_for_every_arm():
    urls = FETCHABLE[:5]
    arms = {name: ArmOutput(name, urls, ScriptedClient({}), 0.0, 0.0) for name in ("plain_search", "single_agent", "multi_agent")}
    measured, _ = compare(GROUND_TRUTH, arms)
    assert len({m.coverage for m in measured.values()}) == 1  # identical URLs, identical coverage
