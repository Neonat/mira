"""Precision for the comparison (PRD v2 §11; docs/single_agent_arm_design.md section 7).

Precision is the share of sampled report claims that a human marks as supported by their cited passage.
Code does three things and never judges a claim:

1. ``sample``: draws claims with a fixed seed, so two reviewers and two runs draw the same sample.
2. ``write_worksheet``: writes each sampled claim, its cited passage and its quote, with a blank label column.
3. ``score``: computes precision from labelled rows only. A blank label is not supported; a sample with any
   unlabelled row reports precision as incomplete rather than as a number.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LABELS = ("supported", "partially_supported", "unsupported", "contradicted")
SEED = 20261029
WORKSHEET_FIELDS = ["sample_id", "arm", "claim", "cited_passage", "supporting_quote", "label", "reviewer_note"]


@dataclass(frozen=True)
class ClaimRow:
    """One report claim as it appears in a worksheet."""

    sample_id: str
    arm: str
    claim: str
    cited_passage: str
    supporting_quote: str


@dataclass(frozen=True)
class Precision:
    arm: str
    labelled: int
    supported: int
    unlabelled: int
    rate: float | None  # None while any sampled row is unlabelled

    @property
    def complete(self) -> bool:
        return self.unlabelled == 0 and self.labelled > 0


def sample(claims: Sequence[ClaimRow], k: int, seed: int = SEED) -> list[ClaimRow]:
    """A fixed-seed sample of up to ``k`` claims, in a stable order."""
    ordered = sorted(claims, key=lambda row: row.sample_id)
    if k >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, k), key=lambda row: row.sample_id)


def write_worksheet(rows: Sequence[ClaimRow], path: Path) -> None:
    """Write the sample for a human to label. The label column is left blank on purpose."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "sample_id": row.sample_id, "arm": row.arm, "claim": row.claim,
                "cited_passage": row.cited_passage, "supporting_quote": row.supporting_quote,
                "label": "", "reviewer_note": "",
            })


def score(path: Path, arm: str) -> Precision:
    """Precision from a labelled worksheet. Only rows with a recognised label count."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["arm"] == arm]
    labelled = [row for row in rows if row["label"] in LABELS]
    unlabelled = len(rows) - len(labelled)
    supported = sum(1 for row in labelled if row["label"] == "supported")
    rate = None if unlabelled or not labelled else supported / len(labelled)
    return Precision(arm=arm, labelled=len(labelled), supported=supported, unlabelled=unlabelled, rate=rate)
