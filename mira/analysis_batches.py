"""Pure, bounded planning for analysis of already eligible saved passages."""

from __future__ import annotations

import os
import re
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, fields
from uuid import UUID

from mira.contracts import Brief, ClaimDraft
from mira.store import NewClaim, PassageRecord


@dataclass(frozen=True)
class AnalysisLimits:
    max_passages: int = 8
    max_characters: int = 12000
    max_batches: int = 8
    max_output_tokens: int = 16384
    timeout_seconds: int = 180
    reserve_tokens: int = 32000
    reserve_seconds: int = 120

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            minimum = 0 if item.name.startswith("reserve_") else 1
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{item.name} must be an integer >= {minimum}")

    @classmethod
    def from_env(cls) -> AnalysisLimits:
        values = {}
        for item in fields(cls):
            value = os.environ.get(f"MIRA_ANALYSIS_{item.name.upper()}")
            if value is not None:
                values[item.name] = int(value)
        return cls(**values)


@dataclass(frozen=True)
class BatchPlan:
    batches: tuple[tuple[PassageRecord, ...], ...]
    deferred: dict[UUID, str]


def _navigation_title(title: str) -> bool:
    """Conservative list-page hint, never a support or eligibility decision."""
    title = " ".join(re.findall(r"[a-z]+", title.lower()))
    return bool(re.fullmatch(
        r"(?:search results|publication index|index of publications|resources|"
        r"publications|guidance papers (?:and )?circulars|circulars (?:and )?guidance papers|"
        r"ordinances and statutory guidelines|"
        r"legal and regulatory requirements)", title))


def _navigation_passage(passage: PassageRecord) -> bool:
    classification = passage.acquisition_provenance.get('claim_grounding')
    if isinstance(classification, dict):
        role = classification.get('role')
        if role in ('listing', 'maintenance'):
            return True
        if role == 'publication':
            return False
    return _navigation_title(passage.title)


def _passage_priority(passage: PassageRecord, brief: Brief) -> tuple[int, int]:
    # Score binary signals rather than frequency so repeated keywords cannot
    # crowd out a single operative clause. Titles alone cannot make text topical.
    topical = bool(re.search(
        r"\b(?:aml|cft|money laundering|terroris[mt] financ\w*|"
        r"financing of terrorism|customer due diligence|suspicious transactions?)\b",
        passage.content, re.I)) if brief.topic == "AML/CFT" else False
    operative = bool(re.search(
        r"\b(?:must|shall|requir\w*|prohibit\w*|oblig\w*|penalt\w*|"
        r"sanction\w*|disciplin\w*|effective|commencement)\b", passage.content, re.I))
    return (int(topical), int(operative))


def plan_batches(passages: Sequence[PassageRecord], limits: AnalysisLimits,
                 brief: Brief | None = None) -> BatchPlan:
    seen: dict[UUID, PassageRecord] = {}
    sources: dict[UUID, dict[UUID, deque[PassageRecord]]] = {}
    for passage in passages:
        if passage.id in seen:
            if seen[passage.id] != passage:
                raise ValueError(f"conflicting passage identity: {passage.id}")
            continue
        seen[passage.id] = passage
        documents = sources.setdefault(passage.source_id, {})
        documents.setdefault(passage.document_id, deque()).append(passage)

    # Publications and unknown document kinds go first. Affirmative saved roles
    # and conservative list-page titles
    # remain candidates and get truthful capacity dispositions, never exclusions.
    source_queues = deque()
    for navigation in (False, True):
        source_queue = deque()
        for documents in sources.values():
            ranked_documents = deque()
            for document in documents.values():
                if all(_navigation_passage(p) for p in document) != navigation:
                    continue
                ordered = list(document)
                if brief is not None:
                    ordered.sort(key=lambda p: _passage_priority(p, brief), reverse=True)
                ranked_documents.append(deque(ordered))
            if ranked_documents:
                source_queue.append(ranked_documents)
        if source_queue:
            source_queues.append(source_queue)
    batches: list[list[PassageRecord]] = []
    deferred: dict[UUID, str] = {}
    current_chars = 0
    exhausted = False
    while source_queues:
        source_queue = source_queues[0]
        if not source_queue:
            source_queues.popleft()
            continue
        documents = source_queue.popleft()
        document = documents.popleft()
        passage = document.popleft()
        if document:
            documents.append(document)
        if documents:
            source_queue.append(documents)
        size = len(passage.content)
        if size > limits.max_characters:
            deferred[passage.id] = "input_limit"
            continue
        if exhausted:
            deferred[passage.id] = "batch_limit"
            continue
        if not batches or len(batches[-1]) >= limits.max_passages or current_chars + size > limits.max_characters:
            if len(batches) >= limits.max_batches:
                exhausted = True
                deferred[passage.id] = "batch_limit"
                continue
            batches.append([])
            current_chars = 0
        batches[-1].append(passage)
        current_chars += size
    return BatchPlan(tuple(tuple(batch) for batch in batches), deferred)


def namespace_claims(claims: Sequence[NewClaim], offset: int) -> list[NewClaim]:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    labels: dict[str, str] = {}
    for index, claim in enumerate(claims, start=1):
        label = claim.draft.claim_label
        if not re.fullmatch(r"C[0-9]{1,4}", label) or label in labels:
            raise ValueError(f"invalid or duplicate claim label: {label}")
        labels[label] = f"C{offset + index}"
    result = []
    for claim in claims:
        try:
            dependencies = [labels[label] for label in claim.draft.depends_on]
        except KeyError as exc:
            raise ValueError(f"unresolved dependency label: {exc.args[0]}") from exc
        payload = claim.draft.model_dump()
        payload.update(claim_label=labels[claim.draft.claim_label], depends_on=dependencies)
        result.append(NewClaim(draft=ClaimDraft.model_validate(payload), evidence=claim.evidence))
    return result
