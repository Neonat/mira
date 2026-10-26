"""Per-run budgets (PRD v2 §6.2, risk G9).

A run stops spending when its token or wall-clock budget runs out and ends as
``partial`` with the reason; the writer still builds a report from what was
verified. The document budget only limits scouting.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass


class BudgetExhausted(Exception):
    """The run has no token or time budget left. The message is the stated reason."""


@dataclass(frozen=True)
class RunBudget:
    """Stored in analysis_runs.source_limits."""

    max_fetched_documents: int = 60
    max_llm_tokens: int = 2_000_000
    max_run_minutes: float = 15
    max_gap_rounds: int = 2

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> RunBudget:
        default = cls()
        return cls(
            max_fetched_documents=int(env.get("MIRA_MAX_FETCHED_DOCUMENTS", default.max_fetched_documents)),
            max_llm_tokens=int(env.get("MIRA_MAX_LLM_TOKENS", default.max_llm_tokens)),
            max_run_minutes=float(env.get("MIRA_MAX_RUN_MINUTES", default.max_run_minutes)),
            max_gap_rounds=int(env.get("MIRA_MAX_GAP_ROUNDS", default.max_gap_rounds)),
        )

    def as_source_limits(self) -> dict[str, float]:
        return asdict(self)


class BudgetTracker:
    def __init__(self, budget: RunBudget, clock: Callable[[], float] = time.monotonic) -> None:
        self.budget = budget
        self._clock = clock
        self._started = clock()
        self.tokens_used = 0
        self.documents_fetched = 0

    def charge_tokens(self, tokens_in: int | None, tokens_out: int | None) -> None:
        self.tokens_used += (tokens_in or 0) + (tokens_out or 0)

    def charge_documents(self, count: int) -> None:
        self.documents_fetched += count

    def remaining_documents(self) -> int:
        return max(0, self.budget.max_fetched_documents - self.documents_fetched)

    def remaining_tokens(self) -> int:
        return max(0, self.budget.max_llm_tokens - self.tokens_used)

    def remaining_minutes(self) -> float:
        return max(0.0, self.budget.max_run_minutes - self.minutes_used())

    def minutes_used(self) -> float:
        return (self._clock() - self._started) / 60

    def check(self) -> None:
        """Raise ``BudgetExhausted`` before starting a step the run can no longer afford."""
        if self.tokens_used >= self.budget.max_llm_tokens:
            raise BudgetExhausted(f"LLM token budget used ({self.tokens_used} of {self.budget.max_llm_tokens})")
        if self.minutes_used() >= self.budget.max_run_minutes:
            raise BudgetExhausted(f"time budget used ({self.budget.max_run_minutes:g} minutes)")

    def status(self) -> dict[str, float]:
        return {
            "tokens_used": self.tokens_used,
            "max_llm_tokens": self.budget.max_llm_tokens,
            "documents_fetched": self.documents_fetched,
            "max_fetched_documents": self.budget.max_fetched_documents,
            "minutes_used": round(self.minutes_used(), 2),
            "max_run_minutes": self.budget.max_run_minutes,
        }
