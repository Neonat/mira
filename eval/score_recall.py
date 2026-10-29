"""Score a Mira run's recall against the M0 ground truth (PRD v2 §11; docs/mira_m0_ground_truth.md).

A finding matches a ground-truth item when one of its cited passages comes from the item's canonical
URL (rule 5: same publisher, same publication). Each item counts at most once, however many findings
match it. Recall is reported three ways, as the ground truth requires: all items, ``fetchable`` items
only, and ``regulatory`` items only. The M0 gate halts the full build below 50% recall on the
``fetchable`` set (PRD v2 §11).

This lives in ``eval/`` and never in ``mira/``: the ground truth must not reach prompts (see
``eval/build_ground_truth.py``).

    python eval/score_recall.py eval/m0_ground_truth.csv --run-urls urls.txt
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HALT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Item:
    id: str
    kind: str
    reach: str
    url: str


@dataclass(frozen=True)
class Recall:
    label: str
    found: int
    total: int

    @property
    def rate(self) -> float:
        return self.found / self.total if self.total else 0.0


def canonical(url: str) -> str:
    """Compare URLs as the ground truth does: scheme and host case-insensitive, no fragment, no trailing slash."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def load_items(path: Path) -> list[Item]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [Item(row["id"], row["kind"], row["reach"], row["url"]) for row in csv.DictReader(handle)]


def score(items: Iterable[Item], run_urls: Iterable[str]) -> dict[str, Recall]:
    """Recall for all items, fetchable items and regulatory items. ``run_urls`` are the canonical URLs of
    the passages a run cited; each one matches at most the item with that URL."""
    cited = {canonical(url) for url in run_urls if url and url.strip()}
    items = list(items)
    groups: Mapping[str, list[Item]] = {
        "all": items,
        "fetchable": [item for item in items if item.reach == "fetchable"],
        "regulatory": [item for item in items if item.kind == "regulatory"],
    }
    return {
        label: Recall(label, sum(1 for item in group if canonical(item.url) in cited), len(group))
        for label, group in groups.items()
    }


def gate(recall: Mapping[str, Recall]) -> tuple[bool, str]:
    """The M0 gate: proceed only if fetchable recall is at least 50%."""
    fetchable = recall["fetchable"]
    proceed = fetchable.rate >= HALT_THRESHOLD
    verdict = "PROCEED" if proceed else "HALT: below 50% recall; the team reviews the approach"
    return proceed, f"{verdict} (fetchable recall {fetchable.found}/{fetchable.total}, {fetchable.rate:.0%})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("--run-urls", type=Path, required=True, help="one canonical URL per line")
    args = parser.parse_args(argv)
    items = load_items(args.ground_truth)
    urls = args.run_urls.read_text(encoding="utf-8").splitlines()
    recall = score(items, urls)
    for label in ("all", "fetchable", "regulatory"):
        r = recall[label]
        print(f"{label:<11} {r.found:>3}/{r.total:<3} {r.rate:.0%}")
    proceed, message = gate(recall)
    print(message)
    return 0 if proceed else 1


if __name__ == "__main__":
    sys.exit(main())
