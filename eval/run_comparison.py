"""Run the three arms through one scorer and one decision rule (PRD v2 §11; design section 6).

Each arm is an ``ArmOutput``: the URLs it cited, the model client it ran with, and what it cost. This module
does not run the arms itself; a live run supplies the outputs. It scores every arm's cited URLs against the
same ground truth with ``score_recall.score``, builds each measured arm with ``Measured.from_client`` (so
``live`` comes from the client type), and applies ``compare.decide``.

With scripted clients it produces a refusal, which is the point: scripted output must not produce a verdict.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from compare import Measured, Verdict, decide  # noqa: E402
from score_recall import Item, score  # noqa: E402


@dataclass(frozen=True)
class ArmOutput:
    arm: str
    cited_urls: Sequence[str]
    client: object
    cost_usd: float | None
    seconds: float | None
    precision: float | None = None  # eval/precision.py score of a fully labelled worksheet; None until then


def compare(ground_truth: Sequence[Item], arms: Mapping[str, ArmOutput]) -> tuple[dict[str, Measured], Verdict]:
    """Score every arm the same way, then apply the PRD rule. Returns the measurements and the verdict."""
    measured: dict[str, Measured] = {}
    for name, output in arms.items():
        coverage = score(ground_truth, output.cited_urls)["all"].rate
        measured[name] = Measured.from_client(name, output.client, coverage, output.cost_usd, output.seconds,
                                              output.precision)
    return measured, decide(measured)
