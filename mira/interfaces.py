"""Roles the orchestrator calls but other owners build (PRD v2 §12).

- Scouts (Nathaniel; AG04-AG06): fetch allow-listed pages through ``fetch_allowed``,
  save each page as a document version before reading it, and report relevant
  passages by label.
- Verifier (Saai; AG08): the §6.3 rule. Deterministic ``quote_match`` first, then
  an independent model check in a fresh context; the "introduces no new fact"
  check for inferred claims.

The orchestrator owns sequencing, budgets, step records, the analyst rewrite of a
partially supported claim, and what happens to a claim after its verdict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from mira.contracts import FetchAttempt, ScoutResult, Verdict, VerdictLabel
from mira.store import ClaimEvidence, PassageRecord, RunContext, StoredClaim


@dataclass(frozen=True)
class ScoutTask:
    """One plan task with labels resolved to real IDs."""

    task_label: str
    role: Literal["regulatory_scout", "industry_scout"]
    jurisdiction_code: str | None
    question: str
    source_ids: tuple[UUID, ...]
    expected_source_ids: tuple[UUID, ...]
    max_documents: int
    gap_round: int = 0
    max_llm_tokens: int | None = None
    max_minutes: float | None = None


@dataclass(frozen=True)
class ScoutOutcome:
    result: ScoutResult
    model: str | None
    prompt_version: str | None
    tokens_in: int
    tokens_out: int


class ScoutFailure(Exception):
    """A failed scout with the work it completed before the error."""

    def __init__(self, cause: Exception, fetch_log: list[FetchAttempt], selection_diagnostics: dict,
                 model: str | None, prompt_version: str | None, tokens_in: int, tokens_out: int) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.fetch_log = fetch_log
        self.selection_diagnostics = selection_diagnostics
        self.model = model
        self.prompt_version = prompt_version
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


class Scout(Protocol):
    def run(self, ctx: RunContext, step_id: UUID, task: ScoutTask) -> ScoutOutcome:
        """Research one task. Runs in a worker thread, in parallel with other scouts.

        Fetch at most ``task.max_documents`` pages, only from ``task.source_ids``,
        and stop within ``task.max_llm_tokens`` and ``task.max_minutes``: the
        orchestrator cannot interrupt a running scout.
        Use your own database connection, never the orchestrator's store.
        ``result.labels`` must resolve every passage label in ``result.report``,
        and each passage must already be saved.
        """
        ...


@dataclass(frozen=True)
class CheckableClaim:
    """The part of a claim a verifier prompt may contain (§5.1 principle 5).

    The analyst's ratings and reasons are left out so the check stays independent.
    ``evidence`` carries passage IDs; label them before they reach a model.
    """

    finding_type: str
    title: str
    content: str
    jurisdiction_code: str | None
    change_type: str | None
    industry_category: str | None
    key_date: date | None
    key_date_kind: str | None
    is_inference: bool
    evidence: tuple[ClaimEvidence, ...]


def checkable(claim: StoredClaim) -> CheckableClaim:
    draft = claim.draft
    return CheckableClaim(
        draft.finding_type, draft.title, draft.content, draft.jurisdiction_code, draft.change_type,
        draft.industry_category, draft.key_date, draft.key_date_kind, draft.is_inference, claim.evidence,
    )


@dataclass(frozen=True)
class CheckOutcome:
    """Final verdict of one check attempt, with the claim_checks rows that led to it."""

    verdict: VerdictLabel
    checks: tuple[Verdict, ...]
    model: str | None
    prompt_version: str | None
    tokens_in: int
    tokens_out: int


class Verifier(Protocol):
    def check_fact(self, claim: StoredClaim, passages: Sequence[PassageRecord], attempt: int) -> CheckOutcome:
        """Check a factual claim against the saved passages it cites (§6.3 steps 1-3).

        Put only ``checkable(claim)`` and the passage text into a model prompt.
        """
        ...

    def check_inference(self, claim: StoredClaim, facts: Sequence[StoredClaim], attempt: int) -> CheckOutcome:
        """Check that an inference introduces no fact absent from the verified claims it rests on.

        Put only ``checkable(claim)`` and ``checkable(fact)`` for each fact into a model prompt.
        """
        ...
