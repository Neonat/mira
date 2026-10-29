"""Re-run diff: what is new, amended or no longer supported since the previous run (PRD v2 §6.5, AG11).

Findings are matched by ``diff_key``: the source document (or regulation) a finding cites, its
type, and its title in normalised form. Keying on the document, not only the regulation, lets
industry items with no regulation diff too (review finding C6). Title normalisation ignores case,
punctuation and spacing; the content comparison then decides whether a matched finding was amended.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from mira.store import PreviousFinding, StoredClaim

_NON_WORD = re.compile(r"[^a-z0-9]+")
KEY_MAX_LENGTH = 300


def normalise_title(title: str) -> str:
    return _NON_WORD.sub(" ", title.lower()).strip()


def diff_key(finding_type: str, document_id: UUID | None, regulation_id: UUID | None, title: str) -> str:
    """The key a finding is matched on across runs. It needs a regulation or a document."""
    anchor = regulation_id or document_id
    if anchor is None:
        raise ValueError("a finding needs a regulation or a document to be matched across runs")
    return f"{anchor}|{finding_type}|{normalise_title(title)}"[:KEY_MAX_LENGTH]


@dataclass(frozen=True)
class Change:
    kind: str  # "new", "amended" or "no_longer_supported"
    key: str
    title: str
    content: str
    previous_content: str | None = None


def diff_runs(previous: Iterable[PreviousFinding], current: Iterable[tuple[str, StoredClaim]]) -> list[Change]:
    """Compare the previous run's findings with this run's verified claims, each paired with its key.

    A key in both runs is ``amended`` only when its content changed. An identical one is unchanged
    and is not listed. A key that was in the previous run and is not in this one is
    ``no_longer_supported``.
    """
    before = {finding.key: finding for finding in previous}
    seen: set[str] = set()
    changes: list[Change] = []
    for key, claim in current:
        seen.add(key)
        if key not in before:
            changes.append(Change("new", key, claim.draft.title, claim.draft.content))
        elif before[key].content != claim.draft.content:
            changes.append(Change("amended", key, claim.draft.title, claim.draft.content, before[key].content))
    for key, finding in before.items():
        if key not in seen:
            changes.append(Change("no_longer_supported", key, finding.title, finding.content))
    return changes
