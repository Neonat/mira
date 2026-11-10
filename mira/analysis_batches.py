"""Pure, bounded planning for analysis of already eligible saved passages."""

from __future__ import annotations

import os
import re
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, fields
from uuid import UUID

from mira.contracts import ClaimDraft
from mira.store import NewClaim, PassageRecord


@dataclass(frozen=True)
class AnalysisLimits:
    max_passages: int = 3
    max_characters: int = 4500
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


def plan_batches(passages: Sequence[PassageRecord], limits: AnalysisLimits) -> BatchPlan:
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

    source_queue = deque(deque(documents.values()) for documents in sources.values())
    batches: list[list[PassageRecord]] = []
    deferred: dict[UUID, str] = {}
    current_chars = 0
    exhausted = False
    while source_queue:
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
