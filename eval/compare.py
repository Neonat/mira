"""The PRD v2 §11 agent-design comparison: does multi-agent beat a single agent or plain search?

The decision rule is the PRD's: "Multi-agent must beat (b) on coverage or precision to justify cost."

This module will not produce a verdict from anything that is not a live run. Each arm result carries a
``live`` flag; a scripted or missing arm is reported as such and blocks the verdict. A harness that printed
a winner from scripted output would be a fabricated result, so that is refused here rather than left to
the reader.

Precision is not computed here. It needs a human to check each sampled claim against its passage (PRD §11),
so this module records it as a pending human step rather than estimating it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Measured:
    """One arm's measured results over the same briefs.

    Build it with ``from_client``, never directly: ``live`` must come from the model client that actually ran,
    so a caller cannot mark scripted output as live.
    """

    arm: str
    live: bool  # set only by from_client, from the client type
    coverage: float | None  # recall on the ground truth, 0..1, or None if not measured
    cost_usd: float | None
    seconds: float | None

    @classmethod
    def from_client(cls, arm: str, client: object, coverage: float | None, cost_usd: float | None,
                    seconds: float | None) -> Measured:
        # Imported here so eval/ does not import the worker at module load. Only a real Anthropic client is live.
        from mira.llm import AnthropicClient

        return cls(arm=arm, live=isinstance(client, AnthropicClient), coverage=coverage,
                   cost_usd=cost_usd, seconds=seconds)


@dataclass(frozen=True)
class Verdict:
    ready: bool
    message: str


def decide(arms: Mapping[str, Measured]) -> Verdict:
    """Apply the PRD rule. Refuses unless every arm is a live, measured run."""
    required = ("plain_search", "single_agent", "multi_agent")
    missing = [name for name in required if name not in arms]
    if missing:
        return Verdict(False, f"not compared: arms missing: {', '.join(missing)}")
    unlive = [name for name in required if not arms[name].live]
    if unlive:
        return Verdict(False, f"not compared: arms without a live run: {', '.join(unlive)} (no verdict from scripted output)")
    unmeasured = [name for name in required if arms[name].coverage is None]
    if unmeasured:
        return Verdict(False, f"not compared: coverage not measured for: {', '.join(unmeasured)}")

    multi, single = arms["multi_agent"], arms["single_agent"]
    coverage_gain = multi.coverage - single.coverage
    if coverage_gain > 0:
        return Verdict(True, f"multi-agent beats the single agent on coverage by {coverage_gain:.0%} "
                             "(precision still needs its human check, PRD §11)")
    return Verdict(True, "multi-agent does not beat the single agent on coverage; precision is a human check. "
                         "Under the PRD rule it does not yet justify its cost.")
