"""The PRD v2 §11 agent-design comparison: does multi-agent beat a single agent or plain search?

The decision rule is the PRD's: "Multi-agent must beat (b) on coverage or precision to justify cost."

This module will not produce a verdict from anything that is not a live run. Each arm result carries a
``live`` flag; a scripted or missing arm is reported as such and blocks the verdict. A harness that printed
a winner from scripted output would be a fabricated result, so that is refused here rather than left to
the reader.

Precision is never computed here. It needs a human to check each sampled claim against its passage (PRD §11);
``eval/precision.py`` scores the labelled worksheet and the result is passed in. Because the rule is "coverage
or precision", a multi-agent arm that does not win on coverage gets no verdict until precision is labelled for
both model arms: it could still win on precision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SCRIPTED_MODEL = "scripted"  # mira.llm.ScriptedClient.model; kept here so eval/ does not import the worker at load


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
    precision: float | None = None  # from a fully labelled worksheet, 0..1, or None while any row is unlabelled

    @classmethod
    def from_client(cls, arm: str, client: object, coverage: float | None, cost_usd: float | None,
                    seconds: float | None, precision: float | None = None) -> Measured:
        # Imported here so eval/ does not import the worker at module load. Only real provider clients are live.
        from mira.llm import AnthropicClient, OpenAIClient, ProviderClient

        return cls(arm=arm, live=(isinstance(client, (AnthropicClient, OpenAIClient))
                                   or (isinstance(client, ProviderClient) and client.live)), coverage=coverage,
                   cost_usd=cost_usd, seconds=seconds, precision=precision)

    @classmethod
    def from_recorded_models(cls, arm: str, models: Sequence[str | None], coverage: float | None,
                             cost_usd: float | None, seconds: float | None,
                             precision: float | None = None) -> Measured:
        """For re-scoring a finished run later: ``live`` comes from the models its ``agent_steps`` recorded.

        Those rows are written by the client that answered, so a run is live only if at least one step names a
        real model and none names the scripted client. A results file cannot mark a run live.
        """
        named = [model for model in models if model]
        live = bool(named) and all(model != SCRIPTED_MODEL for model in named)
        return cls(arm=arm, live=live, coverage=coverage, cost_usd=cost_usd, seconds=seconds, precision=precision)


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
        return Verdict(True, f"multi-agent beats the single agent on coverage by {coverage_gain:.0%}"
                             f"{_precision_note(multi, single)}")
    if multi.precision is None or single.precision is None:
        unlabelled = [m.arm for m in (single, multi) if m.precision is None]
        return Verdict(False, "not decided: multi-agent does not beat the single agent on coverage "
                              f"({multi.coverage:.0%} vs {single.coverage:.0%}), and precision is not labelled for: "
                              f"{', '.join(unlabelled)}. It could still win on precision (PRD §11).")
    precision_gain = multi.precision - single.precision
    if precision_gain > 0:
        return Verdict(True, f"multi-agent beats the single agent on precision by {precision_gain:.0%} "
                             f"({multi.precision:.0%} vs {single.precision:.0%}), though not on coverage "
                             f"({multi.coverage:.0%} vs {single.coverage:.0%})")
    return Verdict(True, "multi-agent beats the single agent on neither coverage "
                         f"({multi.coverage:.0%} vs {single.coverage:.0%}) nor precision "
                         f"({multi.precision:.0%} vs {single.precision:.0%}). "
                         "Under the PRD rule it does not justify its cost.")


def _precision_note(multi: Measured, single: Measured) -> str:
    if multi.precision is None or single.precision is None:
        return " (precision still needs its human check, PRD §11)"
    return f"; precision {multi.precision:.0%} vs {single.precision:.0%}"
