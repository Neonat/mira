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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit
import re

from mira.agents.scout import document_key

HALT_THRESHOLD = 0.5


@dataclass(frozen=True)
class Item:
    id: str
    kind: str
    reach: str
    url: str
    jurisdictions: tuple[str, ...] = ()
    published: date | None = None
    effective: date | None = None


@dataclass(frozen=True)
class Recall:
    label: str
    found: int
    total: int

    @property
    def rate(self) -> float:
        return self.found / self.total if self.total else 0.0


def canonical(url: str) -> str:
    """Resolve explicit official publication aliases while preserving distinct documents."""
    publication = document_key(url.strip())
    if publication.startswith("hkma:"):
        return publication
    parts = urlsplit(url.strip())
    if parts.hostname == "apps.sfc.hk":
        match = re.fullmatch(
            r"/edistributionWeb/(?:api|gateway/(?:EN|TC)(?:/news-and-announcements)?)/(circular|news|consultation)/(?:aml/)?(?:content|list-content|doc|openFile)",
            parts.path,
        )
        query = parse_qs(parts.query)
        if match and query.get("refNo") and not query.get("appendix"):
            language = query.get("lang", ["TC" if "/gateway/TC/" in parts.path else "EN"])[0]
            return f"sfc:{language}:{match[1]}:{query['refNo'][0]}"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def load_items(path: Path) -> list[Item]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [Item(
            row["id"], row["kind"], row["reach"], row["url"],
            tuple(code.strip() for code in row.get("jurisdiction", "").split(",") if code.strip()),
            date.fromisoformat(row["published"]) if row.get("published") else None,
            date.fromisoformat(row["effective"]) if row.get("effective") else None,
        ) for row in csv.DictReader(handle)]


def score(items: Iterable[Item], run_urls: Iterable[str], *, jurisdictions: Sequence[str] | None = None,
          period_start: date | None = None, period_end: date | None = None,
          as_of_date: date | None = None) -> dict[str, Recall]:
    """Recall for all items, fetchable items and regulatory items. ``run_urls`` are the canonical URLs of
    the passages a run cited; each one matches at most the item with that URL."""
    cited = {canonical(url) for url in run_urls if url and url.strip()}
    eligible = []
    for item in items:
        if jurisdictions is not None and not set(item.jurisdictions).intersection(jurisdictions):
            continue
        cutoff = as_of_date or period_end
        if cutoff and item.published and item.published > cutoff:
            continue
        if period_start or period_end:
            dates = [day for day in (item.published, item.effective) if day is not None]
            if not any((period_start is None or day >= period_start) and
                       (period_end is None or day <= period_end) for day in dates):
                continue
        eligible.append(item)
    items = eligible
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
    parser.add_argument("--jurisdictions", nargs="+", help="score only the brief's markets, e.g. HK or SG HK")
    parser.add_argument("--period-start", type=date.fromisoformat)
    parser.add_argument("--period-end", type=date.fromisoformat)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args(argv)
    items = load_items(args.ground_truth)
    urls = args.run_urls.read_text(encoding="utf-8").splitlines()
    recall = score(items, urls, jurisdictions=args.jurisdictions, period_start=args.period_start,
                   period_end=args.period_end, as_of_date=args.as_of)
    for label in ("all", "fetchable", "regulatory"):
        r = recall[label]
        print(f"{label:<11} {r.found:>3}/{r.total:<3} {r.rate:.0%}")
    proceed, message = gate(recall)
    print(message)
    return 0 if proceed else 1


if __name__ == "__main__":
    sys.exit(main())
