"""The three comparison arms of PRD v2 §11 ("agent design value"), scored the same way.

    (a) plain search + template: the saved passages a full-text search returns for the brief, listed in
        a fixed template. No model, no planner, no verifier. This is the baseline the agents must beat.
    (b) single agent: the same pipeline with one regulatory scout and no separate verifier pass.
    (c) multi-agent: the full pipeline (planner, scouts, analyst, verifier, completeness, writer).

Every arm reports the canonical URLs of the passages it cites, so ``score_recall.score`` measures all of
them identically. Arms (b) and (c) need a live model; this module builds them as code, and nothing here
prints a verdict. A comparison is only reported from live runs (see eval/compare.py).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

TEMPLATE_HEADER = "Plain search results for the brief (no agent analysis)."


@dataclass(frozen=True)
class Hit:
    """One saved passage that a search returned."""

    passage_id: str
    source_url: str
    title: str
    content: str


@dataclass(frozen=True)
class ArmResult:
    arm: str
    cited_urls: tuple[str, ...]
    llm_tokens: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


def plain_search(query: str, search: Callable[[str, int], Sequence[Hit]], limit: int = 20) -> ArmResult:
    """Arm (a): the top passages for the brief's query, cited by their URLs, no model called.

    ``search(query, limit)`` is the saved-passage search (search_passages in the database). It is passed in,
    so the arm can be tested without a database and so it can never reach a model.
    """
    hits = list(search(query, limit))[:limit]
    urls: list[str] = []
    for hit in hits:
        if hit.source_url not in urls:
            urls.append(hit.source_url)
    return ArmResult(arm="plain_search", cited_urls=tuple(urls), llm_tokens=0, seconds=0.0,
                     notes=[TEMPLATE_HEADER, f"{len(hits)} passages"])
