"""Runs one research brief from plan to draft report (PRD v2 §4, §6; AG03).

A deterministic state machine: plan → scout → analyse → verify → write. Every
role call is one ``agent_steps`` row with its model, prompt version, tokens and
input/output IDs; the fine-grained phase lives there, and ``analysis_runs.status``
only moves through its own values (running → draft, partial, failed or cancelled).

- Token and time budgets are checked before each step. When one runs out, the
  remaining claims are listed as unchecked, the writer still builds a report
  from what was verified, and the run ends ``partial`` with the reason (§6.2).
- A claim reaches the report only after the verifier returns ``supported``. A
  partially supported fact gets one analyst rewrite and one more check; an
  inference is checked only once every fact it rests on is verified (§6.3).
- Cancellation is checked between steps.

After scouting, a code-only completeness check compares the expected-source
list with what was actually saved (§6.4).

Missing expected sources get gap rounds (§6.4): a targeted re-plan and re-scout, at
most ``max_gap_rounds`` times. Not built yet: waiting for plan approval, claim-level
re-scouting for unsupported claims (§6.3 step 4), and the re-run diff (M3).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol
from datetime import UTC, datetime
from uuid import UUID

from mira.agents import analyst, planner, writer
from mira.brief import check_brief_scope
from mira.budget import BudgetExhausted, BudgetTracker
from mira.completeness import coverage_rows
from mira.coverage_display import coverage_label
from mira.contracts import (
    Brief,
    CONTRACT_VERSION,
    AgentRole,
    CoverageRow,
    FetchAttempt,
    ReportSection,
    ReportSentence,
    ReportSnapshot,
    RunStatus,
    ScoutResult,
    StepRecord,
    StepStatus,
)
from mira.interfaces import CheckOutcome, Scout, ScoutFailure, ScoutOutcome, ScoutTask, Verifier
from mira.llm import LLMClient, LLMError, LLMResult
from mira.diff import diff_key, diff_runs
from mira.evidence_snapshot import build_verification_input
from mira.report import ReportContext, render_html
from mira.store import ExpectedSourceRecord, PassageRecord, RunContext, RunStore, SourceRecord, StoredClaim


class RunCancelled(Exception):
    """The user cancelled the run."""


class RunFailed(Exception):
    """A step the run cannot continue without failed. The message is the failure summary."""


class PlanStrategy(Protocol):
    def __call__(
        self, client: LLMClient, brief: Brief, sources: Sequence[SourceRecord],
        expected: Sequence[ExpectedSourceRecord], max_documents: int,
    ) -> planner.PlannedRun: ...


@dataclass(frozen=True)
class RunOutcome:
    # ``awaiting_approval`` is an outcome only: the stored run goes back to ``queued`` (see execute).
    status: RunStatus | Literal["awaiting_approval"]
    reasons: list[str]
    report_id: UUID | None
    snapshot: ReportSnapshot | None


@dataclass
class _Step:
    id: UUID
    record: StepRecord
    model: str | None = None
    prompt_version: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_precharged: bool = False
    output_refs: dict[str, object] = field(default_factory=dict)


class Orchestrator:
    def __init__(
        self,
        store: RunStore,
        client: LLMClient,
        scouts: Mapping[str, Scout],
        verifier: Verifier,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_parallel_scouts: int = 4,
        plan_strategy: PlanStrategy | None = None,
        corroborator: Callable | None = None,
    ) -> None:
        self.store = store
        self.corroborator = corroborator
        self.client = client
        self.scouts = scouts
        self.verifier = verifier
        self.clock = clock
        self.now = now
        self.max_parallel_scouts = max_parallel_scouts
        # How the first plan is made. The default is the model planner (the multi-agent arm). The single-agent
        # arm passes a code-built plan (mira.single_agent.code_plan), so no planner model is called.
        self.plan_strategy: PlanStrategy = plan_strategy or planner.plan

    def run(self, ctx: RunContext) -> RunOutcome:
        check_brief_scope(ctx.brief)
        try:
            return _Run(self, ctx).execute()
        finally:
            close = getattr(self.corroborator, "close", None)
            if close is not None:
                close()


def split_documents(maxima: Sequence[int], allowance: int) -> list[int]:
    """Share the document budget across tasks one page at a time, up to each task's own limit."""
    caps = [0] * len(maxima)
    while allowance > 0 and any(cap < most for cap, most in zip(caps, maxima)):
        for index, most in enumerate(maxima):
            if allowance > 0 and caps[index] < most:
                caps[index] += 1
                allowance -= 1
    return caps


def _latest_rows(rows: Sequence[CoverageRow]) -> list[CoverageRow]:
    """One row per expected source; the row from the latest gap round wins."""
    latest: dict[UUID, CoverageRow] = {}
    for row in rows:
        latest[row.expected_source_id] = row
    return list(latest.values())


class _Run:
    def __init__(self, orchestrator: Orchestrator, ctx: RunContext) -> None:
        self.o = orchestrator
        self.store = orchestrator.store
        self.ctx = ctx
        self.budget = BudgetTracker(ctx.budget, orchestrator.clock)
        self.step_no = ctx.completed_steps
        self.reasons: list[str] = []
        self.tasks: tuple[ScoutTask, ...] = ()
        self.sources: dict[UUID, SourceRecord] = {}
        self.expected: list[ExpectedSourceRecord] = []
        self.scout_results: dict[str, ScoutResult] = {}
        self.skipped: dict[str, str] = {}
        self.coverage: list[CoverageRow] = []
        self.passages: dict[UUID, PassageRecord] = {}
        self.claims: list[StoredClaim] = []
        self.verified: dict[UUID, StoredClaim] = {}
        self.unresolved: dict[UUID, str] = {}
        self.corroboration: dict[UUID, dict] = {}

    # --- Run ----------------------------------------------------------------------

    def execute(self) -> RunOutcome:
        ctx = self.ctx
        self.store.set_run_status(ctx, "running", None)
        try:
            try:
                self._plan()
                if ctx.brief.plan_requires_approval and not ctx.plan_approved:
                    # PRD v2 §4: the auditor approves the plan before any scouting. The run goes back to
                    # queued and resumes once an approval is recorded (research_plans.approved_at).
                    self.store.set_run_status(ctx, "queued", "waiting for plan approval")
                    return RunOutcome("awaiting_approval", ["waiting for plan approval"], None, None)
                self._scout(self.tasks)
                self._check_coverage()
                self._fill_gaps()
                self._analyse()
                self._verify()
            except BudgetExhausted as exc:
                self.reasons.append(str(exc))
            for claim in self.claims:
                if claim.finding_id not in self.verified and claim.finding_id not in self.unresolved:
                    self.unresolved[claim.finding_id] = "not checked: the run stopped before this claim"
            report_id, snapshot, status = self._write()
        except RunCancelled:
            self.store.set_run_status(ctx, "cancelled", "cancelled by user")
            return RunOutcome("cancelled", self.reasons, None, None)
        except RunFailed as exc:
            self.store.set_run_status(ctx, "failed", str(exc))
            return RunOutcome("failed", [*self.reasons, str(exc)], None, None)
        except Exception as exc:
            self.store.set_run_status(ctx, "failed", f"internal error: {exc!r}")
            raise
        self.store.set_run_status(ctx, status, "; ".join(self.reasons) or None)
        return RunOutcome(status, self.reasons, report_id, snapshot)

    # --- Steps --------------------------------------------------------------------

    def _check_cancel(self) -> None:
        if self.store.cancel_requested(self.ctx):
            raise RunCancelled()

    def _start(
        self, role: AgentRole, *, jurisdiction: str | None = None, gap_round: int = 0,
        input_refs: dict[str, object] | None = None, status: StepStatus = "running",
    ) -> _Step:
        self.step_no += 1
        record = StepRecord(
            analysis_run_id=self.ctx.analysis_run_id, step_no=self.step_no, role=role, jurisdiction_code=jurisdiction,
            gap_round=gap_round, status=status, contract_version=CONTRACT_VERSION, model=None, prompt_version=None,
            temperature=None, input_refs=input_refs or {}, output_refs={}, tokens_in=None, tokens_out=None,
            started_at=self.o.now() if status == "running" else None, finished_at=None, error=None,
        )
        return _Step(self.store.start_step(self.ctx, record), record)

    def _finish(self, step: _Step, status: StepStatus, error: str | None = None) -> None:
        if not step.tokens_precharged:
            self.budget.charge_tokens(step.tokens_in, step.tokens_out)
        used_llm = step.model is not None or step.tokens_in or step.tokens_out
        record = step.record.model_copy(update={
            "status": status,
            "model": step.model,
            "prompt_version": step.prompt_version,
            "tokens_in": step.tokens_in if used_llm else None,
            "tokens_out": step.tokens_out if used_llm else None,
            "output_refs": step.output_refs,
            "finished_at": self.o.now(),
            "error": error,
        })
        self.store.finish_step(self.ctx, step.id, record)

    def _skip(self, role: AgentRole, reason: str, *, jurisdiction: str | None = None, gap_round: int = 0) -> None:
        step = self._start(role, jurisdiction=jurisdiction, gap_round=gap_round, status="skipped")
        step.output_refs["reason"] = reason
        self.store.finish_step(self.ctx, step.id, step.record.model_copy(update={"output_refs": step.output_refs}))

    @contextmanager
    def _step(self, role: AgentRole, *, check_budget: bool = True, **kwargs: object) -> Iterator[_Step]:
        """One recorded step. Checks cancellation and budget first; records failure and re-raises."""
        self._check_cancel()
        if check_budget:
            self.budget.check()
        step = self._start(role, **kwargs)
        try:
            yield step
        except Exception as exc:
            if isinstance(exc, LLMError):
                step.tokens_in += exc.tokens_in
                step.tokens_out += exc.tokens_out
            self._finish(step, "failed", f"{type(exc).__name__}: {exc}")
            raise
        self._finish(step, "succeeded")

    @staticmethod
    def _used(step: _Step, result: LLMResult | ScoutOutcome | ScoutFailure | CheckOutcome) -> None:
        step.model = result.model
        step.prompt_version = result.prompt_version
        step.tokens_in += result.tokens_in
        step.tokens_out += result.tokens_out

    # --- Phases -------------------------------------------------------------------

    def _plan(self) -> None:
        ctx, brief = self.ctx, self.ctx.brief
        sources = self.store.list_sources(ctx.workspace_id)
        expected = self.store.list_expected_sources(ctx.workspace_id, brief.topic, brief.jurisdictions)
        self.sources = {source.id: source for source in sources}
        self.expected = list(expected)
        if ctx.plan_approved:
            # A resumed run scouts the plan the auditor approved. It does not plan again, because a new
            # plan would be one nobody reviewed (PRD v2 §4).
            approved = self.store.approved_plan(ctx)
            if approved is None:
                raise RunFailed("the run is marked approved but no approved plan is stored")
            try:
                self.tasks = planner.tasks_from_stored(approved, brief)
            except (ValueError, KeyError) as exc:
                raise RunFailed(f"approved plan cannot be used: {exc}") from exc
            return
        refs = {"source_ids": [str(s.id) for s in sources], "expected_source_ids": [str(e.id) for e in expected]}
        try:
            with self._step("planner", input_refs=refs) as step:
                planned = self.o.plan_strategy(self.o.client, brief, sources, expected, self.budget.remaining_documents())
                self._used(step, planned.llm)
                plan_id = self.store.save_plan(ctx, 1, planned.stored_plan(), step.id)
                step.output_refs.update(research_plan_id=str(plan_id), tasks=len(planned.tasks))
        except (LLMError, ValueError) as exc:
            raise RunFailed(f"planner failed: {exc}") from exc
        self.tasks = planned.tasks

    def _scout(self, tasks: Sequence[ScoutTask]) -> None:
        runnable: list[tuple[ScoutTask, Scout]] = []
        for task in tasks:
            scout = self.o.scouts.get(task.role)
            if scout is None:
                reason = f"task {task.task_label} not run: no {task.role.replace('_', ' ')} is available"
                self._skip(task.role, reason, jurisdiction=task.jurisdiction_code, gap_round=task.gap_round)
                self.reasons.append(reason)
                self.skipped[task.task_label] = reason
            else:
                runnable.append((task, scout))
        caps = split_documents([task.max_documents for task, _ in runnable], self.budget.remaining_documents())
        funded: list[tuple[ScoutTask, Scout, int]] = []
        for (task, scout), cap in zip(runnable, caps):
            if cap == 0:
                reason = f"task {task.task_label} not run: document budget used"
                self._skip(task.role, reason, jurisdiction=task.jurisdiction_code, gap_round=task.gap_round)
                self.reasons.append(reason)
                self.skipped[task.task_label] = reason
            else:
                funded.append((task, scout, cap))
        if not funded:
            return

        self._check_cancel()
        self.budget.check()
        # Scouts run unattended, so each gets its share of what is left up front.
        tokens = self.budget.remaining_tokens() // len(funded)
        minutes = self.budget.remaining_minutes()
        launch = [
            (replace(task, max_documents=cap, max_llm_tokens=tokens, max_minutes=minutes), scout)
            for task, scout, cap in funded
        ]
        steps = [
            self._start(
                task.role, jurisdiction=task.jurisdiction_code, gap_round=task.gap_round,
                input_refs={
                    "task_label": task.task_label, "question": task.question, "max_documents": task.max_documents,
                    "max_llm_tokens": task.max_llm_tokens, "max_minutes": round(task.max_minutes or 0, 2),
                    "source_ids": [str(i) for i in task.source_ids],
                    "expected_source_ids": [str(i) for i in task.expected_source_ids],
                },
            )
            for task, _ in launch
        ]
        with ThreadPoolExecutor(max_workers=min(len(launch), self.o.max_parallel_scouts)) as pool:
            futures: list[Future[ScoutOutcome]] = [
                pool.submit(scout.run, self.ctx, step.id, task) for (task, scout), step in zip(launch, steps)
            ]
            # Collected in plan order on this thread; the store is never touched from a worker.
            for (task, _), step, future in zip(launch, steps, futures):
                try:
                    self._collect_scout(task, step, future.result())
                except Exception as exc:
                    if isinstance(exc, ScoutFailure):
                        self._used(step, exc)
                        self._record_scout_fetches(step, exc.fetch_log, exc.selection_diagnostics)
                        error_type = type(exc.cause).__name__
                    else:
                        if isinstance(exc, LLMError):
                            step.tokens_in += exc.tokens_in
                            step.tokens_out += exc.tokens_out
                        error_type = type(exc).__name__
                    self._finish(step, "failed", f"{error_type}: {exc}")
                    self.reasons.append(f"task {task.task_label} ({task.role.replace('_', ' ')}) failed: {exc}")
                    self.skipped[task.task_label] = f"scout failed: {exc}"
                else:
                    self._finish(step, "succeeded")

    def _collect_scout(self, task: ScoutTask, step: _Step, outcome: ScoutOutcome) -> None:
        self._used(step, outcome)
        result = outcome.result
        self._record_scout_fetches(step, result.fetch_log, result.selection_diagnostics)
        if (result.analysis_run_id, result.agent_step_id, result.role) != (self.ctx.analysis_run_id, step.id, task.role):
            raise ValueError("scout result belongs to a different run, step or role")
        passage_ids: list[UUID] = []
        for document in result.report.documents:
            for label in document.relevant_passage_labels:
                if not label.startswith("P") or label not in result.labels:
                    raise ValueError(f"scout cited passage label {label!r} it did not define")
                if result.labels[label] not in passage_ids:
                    passage_ids.append(result.labels[label])
        document_passage_ids = set(passage_ids)
        for status in result.report.expected_source_statuses:
            for label in status.inspected_passage_labels:
                passage_id = result.labels.get(label)
                if not label.startswith("P") or passage_id is None:
                    raise ValueError(f"scout cited inspection label {label!r} it did not define")
                if passage_id not in passage_ids:
                    passage_ids.append(passage_id)
        found = self.store.get_passages(self.ctx.workspace_id, passage_ids)
        missing = set(passage_ids) - {passage.id for passage in found}
        if missing:
            raise ValueError(f"{len(missing)} cited passages are not saved in the evidence store")
        selected_versions = {p.document_version_id for p in found if p.id in document_passage_ids}
        shown_ids = [real for label, real in result.labels.items() if label.startswith("P") and real not in passage_ids]
        for passage in self.store.get_passages(self.ctx.workspace_id, shown_ids):
            if passage.document_version_id in selected_versions:
                found.append(passage)
                passage_ids.append(passage.id)
        self.passages.update({passage.id: passage for passage in found})
        self.scout_results[task.task_label] = result
        step.output_refs.update(
            passage_ids=[str(i) for i in passage_ids],
            documents=len(result.report.documents),
        )

    def _record_scout_fetches(self, step: _Step, fetch_log: list[FetchAttempt], diagnostics: dict) -> None:
        self.budget.charge_documents(sum(1 for attempt in fetch_log if attempt.outcome not in ("refused", "reused")))
        step.output_refs.update(
            fetch_attempts=len(fetch_log),
            fetch_refused=sum(1 for attempt in fetch_log if attempt.outcome == "refused"),
            fetch_reused=sum(1 for attempt in fetch_log if attempt.outcome == "reused"),
            fetch_failed=sum(1 for attempt in fetch_log if attempt.outcome == "failed"),
            fetch_log=[attempt.model_dump(mode="json") for attempt in fetch_log],
            selection_diagnostics=diagnostics,
        )

    def _check_coverage(self) -> None:
        if not self.expected:
            return
        # Code only, so it costs no tokens: run it even when the budget is spent, so a
        # partial report still shows which checklist items were covered.
        with self._step("completeness_checker", check_budget=False,
                        input_refs={"expected_source_ids": [str(e.id) for e in self.expected]}) as step:
            self.coverage = coverage_rows(self.expected, self.sources, self.tasks, self.scout_results, self.skipped,
                                          passages=self.passages)
            self.store.save_coverage(self.ctx, self.coverage)
            counts: dict[str, int] = {}
            for row in self.coverage:
                counts[row.status] = counts.get(row.status, 0) + 1
            step.output_refs.update(counts)

    def _fill_gaps(self) -> None:
        """Re-plan and re-scout for expected sources still missing, at most ``max_gap_rounds`` times (§6.4).

        Only items whose coverage is ``missing`` on a source that may be fetched are retried. Fetch
        failures, budget shortfalls and sources that refuse automated access are reported, not
        retried. A round that cannot finish is stated as a limitation and the run carries on.
        """
        for gap_round in range(1, self.ctx.budget.max_gap_rounds + 1):
            missing = self._missing_expected()
            if not missing:
                return
            try:
                self._check_cancel()
                self.budget.check()
                if self.budget.remaining_documents() == 0:
                    raise BudgetExhausted("document budget used")
                planned = self._plan_gap(gap_round, missing)
                tasks = tuple(
                    replace(task, task_label=f"G{gap_round}-{task.task_label}", gap_round=gap_round)
                    for task in planned.tasks
                )
                self._scout(tasks)
            except BudgetExhausted as exc:
                self.reasons.append(f"gap round {gap_round} stopped: {exc}")
                return
            except (LLMError, ValueError) as exc:
                self.reasons.append(f"gap round {gap_round} planner failed: {exc}")
                return
            self._check_gap_coverage(gap_round, missing, tasks)

    def _missing_expected(self) -> list[ExpectedSourceRecord]:
        latest = {row.expected_source_id: row for row in self.coverage}
        missing = []
        for item in self.expected:
            row = latest.get(item.id)
            source = self.sources.get(item.source_id)
            if (row is None or row.status != "missing" or source is None
                    or not {"fetch", "store_text"} <= set(source.permitted_operations)):
                continue
            missing.append(item)
        return missing

    def _plan_gap(self, gap_round: int, missing: Sequence[ExpectedSourceRecord]) -> planner.PlannedRun:
        refs = {"gap_round": gap_round, "expected_source_ids": [str(e.id) for e in missing]}
        with self._step("planner", gap_round=gap_round, input_refs=refs) as step:
            planned = planner.plan(
                self.o.client, self.ctx.brief, list(self.sources.values()), missing,
                self.budget.remaining_documents(), gap_round=gap_round,
            )
            self._used(step, planned.llm)
            plan_id = self.store.save_plan(self.ctx, gap_round + 1, planned.stored_plan(), step.id)
            step.output_refs.update(research_plan_id=str(plan_id), tasks=len(planned.tasks))
        return planned

    def _check_gap_coverage(
        self, gap_round: int, missing: Sequence[ExpectedSourceRecord], tasks: Sequence[ScoutTask],
    ) -> None:
        with self._step(
            "completeness_checker", check_budget=False, gap_round=gap_round,
            input_refs={"expected_source_ids": [str(e.id) for e in missing]},
        ) as step:
            rows = coverage_rows(missing, self.sources, tasks, self.scout_results, self.skipped,
                                 gap_round=gap_round, passages=self.passages)
            self.store.save_coverage(self.ctx, rows)
            self.coverage = _latest_rows([*self.coverage, *rows])
            counts: dict[str, int] = {}
            for row in rows:
                counts[row.status] = counts.get(row.status, 0) + 1
            step.output_refs.update(counts)

    def _analyse(self) -> None:
        if not self.passages:
            self._skip("analyst", "no passages were found")
            return
        try:
            with self._step("analyst", input_refs={"passage_ids": [str(i) for i in self.passages]}) as step:
                analysis = analyst.analyse(self.o.client, self.ctx.brief, list(self.passages.values()))
                self._used(step, analysis.llm)
                self.claims = self.store.save_claims(self.ctx, analysis.claims)
                step.output_refs["finding_ids"] = [str(claim.finding_id) for claim in self.claims]
        except (LLMError, ValueError) as exc:
            raise RunFailed(f"analyst failed: {exc}") from exc

    def _verify(self) -> None:
        for claim in self.claims:
            if claim.draft.finding_type == "audit_question":
                self.unresolved[claim.finding_id] = "out of scope: audit actions are for the auditor to decide"
        for claim in self.claims:
            if not claim.draft.is_inference:
                self._verify_fact(claim)
        pending = [claim for claim in self.claims
                   if claim.draft.is_inference and claim.finding_id not in self.unresolved]
        progress = True
        while pending and progress:
            progress = False
            for claim in list(pending):
                if any(dependency in self.unresolved for dependency in claim.depends_on):
                    self.unresolved[claim.finding_id] = "rests on a claim that was not verified"
                elif all(dependency in self.verified for dependency in claim.depends_on):
                    facts = [self.verified[dependency] for dependency in claim.depends_on]
                    outcome = self._check(claim, 1, lambda: self.o.verifier.check_inference(claim, facts, 1, **self._corroboration_kwargs(claim)))
                    self._decide(claim, outcome)
                else:
                    continue
                pending.remove(claim)
                progress = True
        for claim in pending:
            self.unresolved[claim.finding_id] = "circular dependency between inferences"

    def _verify_fact(self, claim: StoredClaim) -> None:
        for attempt in (1, 2):
            self._corroborate(claim)
            passages = [self.passages[item.passage_id] for item in claim.evidence]
            outcome = self._check(claim, attempt, lambda: self.o.verifier.check_fact(claim, passages, attempt, **self._corroboration_kwargs(claim)))
            if outcome is None or outcome.verdict != "partially_supported" or attempt == 2:
                self._decide(claim, outcome)
                return
            rewritten = self._rewrite(claim, passages, outcome.checks[-1].reason)
            if rewritten is None:
                self.unresolved[claim.finding_id] = "partially supported; the rewrite failed"
                return
            claim = rewritten

    def _corroboration_kwargs(self, claim):
        captured = build_verification_input(self.ctx, claim,
            {c.finding_id:c for c in self.claims}, self.passages, self.corroboration)
        return {"corroboration":captured.corroboration} if captured.corroboration else {}

    def _corroborate(self, claim):
        if self.o.corroborator is None:
            return
        with self._step("verifier", check_budget=False,
                        input_refs={"finding_id":str(claim.finding_id),"purpose":"corroboration"}) as step:
            base = build_verification_input(self.ctx,claim,
                {c.finding_id:c for c in self.claims},self.passages).model_dump(mode="json")
            # The service consumes this shared budget during bounded follow-up calls.
            step.tokens_precharged = True
            try:
                envelope = self.o.corroborator(self.ctx,claim,base,self.budget)
            except Exception as exc:
                failed = getattr(exc,"assessment",{})
                step.tokens_in = failed.get("tokens_in",0)
                step.tokens_out = failed.get("tokens_out",0)
                step.model = failed.get("model")
                step.prompt_version = failed.get("prompt_version")
                step.output_refs["reserved_tokens"] = failed.get("reserved_tokens",0)
                raise
            self.corroboration[claim.finding_id] = envelope
            assessment = envelope["assessment"]
            step.tokens_in = assessment.get("tokens_in",0)
            step.tokens_out = assessment.get("tokens_out",0)
            step.model = assessment.get("model")
            step.prompt_version = assessment.get("prompt_version")
            step.output_refs.update(assessment_id=envelope["assessment_id"],
                                    corroboration_status=assessment["status"],
                                    reserved_tokens=assessment.get("reserved_tokens",0))

    def _check(self, claim: StoredClaim, attempt: int, call: Callable[[], CheckOutcome]) -> CheckOutcome | None:
        refs = {"finding_id": str(claim.finding_id), "attempt": attempt}
        try:
            with self._step("verifier", input_refs=refs) as step:
                checked_input = build_verification_input(
                    self.ctx, claim, {item.finding_id: item for item in self.claims}, self.passages, self.corroboration,
                )
                outcome = call()
                self._used(step, outcome)
                if not outcome.checks or any(
                    (check.finding_id, check.attempt) != (claim.finding_id, attempt) for check in outcome.checks
                ):
                    raise ValueError("verifier returned checks for a different claim or attempt")
                self.store.save_checks(
                    self.ctx, step.id, outcome.checks, input_snapshot=checked_input.model_dump(mode="json"),
                )
                step.output_refs["verdict"] = outcome.verdict
        except (LLMError, ValueError) as exc:
            self.reasons.append(f"verifier failed on claim {claim.label}: {exc}")
            return None
        return outcome

    def _decide(self, claim: StoredClaim, outcome: CheckOutcome | None) -> None:
        if outcome is None:
            self.unresolved[claim.finding_id] = "not checked: the verifier failed"
        elif outcome.verdict == "supported":
            self.verified[claim.finding_id] = claim
        else:
            self.unresolved[claim.finding_id] = f"{outcome.verdict.replace('_', ' ')}: {outcome.checks[-1].reason}"

    def _rewrite(self, claim: StoredClaim, passages: list[PassageRecord], reason: str) -> StoredClaim | None:
        refs = {"finding_id": str(claim.finding_id), "verifier_reason": reason}
        try:
            with self._step("analyst", input_refs=refs) as step:
                new_claim, result = analyst.rewrite(self.o.client, self.ctx.brief, claim, passages, reason)
                self._used(step, result)
                stored = self.store.update_claim(self.ctx, claim.finding_id, new_claim)
        except (LLMError, ValueError):
            return None
        self.claims = [stored if c.finding_id == stored.finding_id else c for c in self.claims]
        return stored

    def _write(self) -> tuple[UUID, ReportSnapshot, RunStatus]:
        verified = [claim for claim in self.claims if claim.finding_id in self.verified]
        if not verified:
            self._skip("writer", "no verified claims")
            sections = writer.claim_sections([])
        else:
            try:
                with self._step("writer", check_budget=False, input_refs={"finding_ids": [str(c.finding_id) for c in verified]}) as step:
                    written = writer.write(self.o.client, self.ctx.brief, verified)
                    self._used(step, written.llm)
                    sections = written.sections
                    step.output_refs["sections"] = [s.section for s in sections if not s.no_verified_items]
                    step.output_refs["grounded_sentences"] = written.grounded_sentences
            except (LLMError, ValueError) as exc:
                self.reasons.append(f"writer failed ({exc}); the report lists verified claims without a summary")
                sections = writer.claim_sections(verified)

        status: RunStatus = "partial" if self.reasons else "draft"
        self.store.save_diff_keys(self.ctx, {c.finding_id: self._diff_key(c) for c in verified})
        changes = self._changes_section()
        if changes is not None:
            sections.append(changes)
        sections.append(self._coverage_section())
        snapshot = ReportSnapshot(
            contract_version=CONTRACT_VERSION,
            analysis_run_id=self.ctx.analysis_run_id,
            analysis_revision_id=self.ctx.analysis_revision_id,
            sections=sections,
            coverage=self.coverage,
            unresolved_finding_ids=list(self.unresolved),
        )
        context = ReportContext(
            brief=self.ctx.brief,
            run_status=status,
            claims={claim.finding_id: claim for claim in self.claims},
            passages=self.passages,
            unresolved=self.unresolved,
            generated_at=self.o.now(),
            expected={row.id: row for row in self.expected},
            corroboration=self.corroboration,
        )
        report_id = self.store.save_report(self.ctx, snapshot, render_html(snapshot, context))
        return report_id, snapshot, status

    def _changes_section(self) -> ReportSection | None:
        """What changed since the previous run, from verified claims only (PRD v2 §6.5, AG11).

        Returns None for a first run. Each sentence cites the verified claim it describes, or, for an
        item no longer supported, is structural text that names the previous finding without citing it.
        """
        if self.ctx.previous_run_id is None:
            return None
        previous = self.store.previous_findings(self.ctx)
        keyed = [(self._diff_key(claim), claim) for claim in self.claims if claim.finding_id in self.verified]
        changes = diff_runs(previous, keyed)
        if not changes:
            return ReportSection(section="what_changed", sentences=[ReportSentence(
                text="No new, amended or dropped items since the previous run.", finding_ids=[], structural=True,
            )], no_verified_items=False)
        claim_for_key = {key: claim for key, claim in keyed}
        sentences = []
        for change in changes:
            if change.kind == "no_longer_supported":
                # Not a verified claim in this run, so it is named but never cited (AG10).
                sentences.append(ReportSentence(
                    text=f"No longer supported in this run: {change.title}.", finding_ids=[], structural=True,
                ))
                continue
            label = "New since the previous run" if change.kind == "new" else "Amended since the previous run"
            sentences.append(ReportSentence(
                text=f"{label}: {change.title}.", finding_ids=[claim_for_key[change.key].finding_id], structural=False,
            ))
        return ReportSection(section="what_changed", sentences=sentences, no_verified_items=False)

    def _diff_key(self, claim: StoredClaim) -> str:
        """Key a finding by the document it rests on (see ``mira.diff``).

        A fact cites its own passage. An inference cites none and rests on the facts in ``depends_on``,
        so its document comes from the first fact it rests on. The MVP does not set ``regulation_id``,
        so the document is the anchor; industry items diff too.
        """
        document_id = self._anchor_document(claim)
        return diff_key(claim.draft.finding_type, document_id, None, claim.draft.title)

    def _anchor_document(self, claim: StoredClaim) -> UUID:
        if claim.evidence:
            return self.passages[claim.evidence[0].passage_id].document_id
        by_id = {c.finding_id: c for c in self.claims}
        for dependency in claim.depends_on:
            if dependency in by_id:
                return self._anchor_document(by_id[dependency])
        raise ValueError(f"claim {claim.label} has no passage or fact to anchor its diff key")

    def _coverage_section(self) -> ReportSection:
        status = self.budget.status()
        if self.coverage:
            counts: dict[str, int] = {}
            for row in self.coverage:
                label = coverage_label(row.status, row.note).lower()
                counts[label] = counts.get(label, 0) + 1
            version = max(row.list_version for row in self.expected)
            summary = " · ".join(f"{n} {label}" for label, n in sorted(counts.items()))
            coverage_line = f"Source coverage checklist v{version} — {summary}."
        else:
            coverage_line = "This run did not check a configured source coverage checklist."
        lines = [
            coverage_line,
            f"{len(self.verified)} claims verified; {len(self.unresolved)} unresolved and kept out of the report body.",
            f"Budget used: {status['tokens_used']} of {status['max_llm_tokens']} model tokens, "
            f"{status['documents_fetched']} of {status['max_fetched_documents']} documents, "
            f"{status['minutes_used']:g} of {status['max_run_minutes']:g} minutes.",
            *[f"Limitation: {reason}." for reason in self.reasons],
        ]
        sentences = [ReportSentence(text=line, finding_ids=[], structural=True) for line in lines]
        return ReportSection(section="coverage_limitations", sentences=sentences, no_verified_items=False)
