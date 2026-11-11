# Scheduled evidence and prepared reporting implementation

Approved spec: [workflow and contracts](../specs/2026-11-10-scheduled-evidence-reporting-design.md).
Base: `bfd45ebef3aee99cecf98ee4fa28231771a66558`.
Existing isolated `codex/durable-evidence-recovery` worktree; update PR13, no merge.

## Global constraints

MAS/Malaysia/DFSA stay disabled, hybrid experimental, source grants and role models
unchanged. Preserve all previous evidence/reviewed report bytes. New tables and
versioned prepared-report contracts are additive: do not transplant old checks
into a new run or bypass legacy single-run sign-off. Enterprise preparation is
operator-managed; current per-request BYOK remains supported. No paid/live API
validation or unattended worker activation in this implementation test scope.
Normal ready-evidence report goal is five minutes; record actual end-to-end and
waiting/generation components without claiming scripted timing proves provider
latency. One integrated full suite after scoped red/green and focused reviews.

## Task 1: Atomic storage, frozen snapshots and reviews

Ownership: evidence architect, explicitly assigned new
`mira/preparation_store.py`, `supabase/migrations/20261110180000_mira_prepared_evidence.sql`,
`tests/test_preparation_store_db.py`. Coordinator integrates shared contracts.

Interfaces: workspace/source canonical scope rows; fenced preparation jobs;
operator schedules; persistent source frontier; immutable snapshots/facts with
original verification provenance; atomic multi-scope report requests; append-only
human fact reviews; prepared report bindings, later rejection alerts and final
approval. Prepared reports use a separate versioned capture retaining original
single-run verification inputs, avoiding forged new checks or changed legacy
report contracts. Every public RPC authenticates the real actor and workspace
role; tables are workspace-readable/worker-written under RLS.

Write failing real PostgreSQL cases first for overlapping sets, atomic pin/wait,
stale leases, idempotent publication, failed refresh/explicit previous choice,
pending/mixed/rejected reviews, dependency rejection and report/review races.
Implement minimal transactional operations and RLS, then run only those cases.

## Task 2: Background scheduler and preparation runtime

Ownership: coverage engineer, explicitly assigned new
`mira/preparation_runtime.py`, `mira/__main__.py`, `mira/agents/scout.py`,
`tests/test_preparation_runtime.py`, `tests/test_preparation_frontier.py`.

Interfaces: use Task1 store and coordinator `execute_run(..., preparation=True)`.
Preparation invokes acquisition/analysis/checking, without writer generation.
Persist actual discovered URLs, trusted dates/origins, attempts and completion
under the current job lease before consumption. Later cycles prioritize pending
frontier items and reuse unchanged retained evidence. Schedules have explicit
frequency/next-due/bounds, disabled by default; due ticks coalesce and workers
claim only explicit jobs. Heartbeat and fence all job-owned progress/publication.
Root owns runner/orchestrator seams and cost admission; never change models.

Red/green tests: due ticks do not duplicate work, overlapping jobs serialize,
frontier survives restart, stale attempt cannot advance, no writer in preparation,
no network/provider work without explicit dispatch. CLI supports one-shot worker
and schedule registration without starting unattended paid work. Keep the
report worker separate so ready scopes can be served during a long refresh.

## Task 3: Prepared report generation and export

Ownership: coordinator: `mira/prepared_reporting.py` new, runner/orchestrator
phase seam, report rendering and supporting contract extensions/tests.

Interfaces: consume only pinned snapshots from Task1. Filter exact frozen claims
by requested source/market/date/as-of and dependency closure, then rank relevant
facts. Keep complete retained source text and deferred analysis separately.
Reuse original checks without repeating semantic checks. Deterministic assembly
organizes immutable supported claims; changed wording or new inference requires
fresh verification in Full research. Pinned cumulative snapshot lineage
preserves older eligible facts and their original review decisions; passage
analysis reuse leaves interrupted work and requested corrections eligible for
catch-up.
Capture review state atomically at publication. Render human-review-pending
warning prominently in UI and exported HTML/PDF; final report approval remains
separate and requires accepted included evidence. Later rejection is a visible
alert, never a historical byte rewrite. Keep the old full research path available.

Red/green tests: no scout/analyst/Exa on ready path; multi-scope exact pinning;
date/permission/dependency filters; pending warning cannot disappear on export;
rejection during composition refuses/rebuilds; cancellation leaves preparation
alone; immutable later alerts; no cross-workspace reads. Measure scripted pipeline
and writer-free deterministic fallback separately from any provider latency claim.

## Task 4: Console request, preparation review and report states

Ownership: demo engineer explicit exception for `app/streamlit_app.py`, new
`mira/prepared_console.py`, `tests/test_prepared_console.py`; existing console
tests only when explicitly assigned. Preserve the current visual language.

Interfaces: authenticated RPCs from Task1, never worker credentials in UI.
Default prepared archive mode; retain full research/BYOK mode. Queue quickly,
show waiting/generating/ready and per-source freshness/review coverage. Reviewer
page accepts/rejects/requests correction on exact prepared facts. Show explicit
old-snapshot choice after failed preparation, pending labels in reports and later
invalidations. Enterprise credential provisioning stays outside demo flow.

Red/green tests: atomic submit has no client-selected latest snapshot; pending,
mixed, rejected and checked labels; expired/failing/waiting states; reviewer vs
analyst access; independent cancellation; existing full research regression.
Inspect desktop/mobile actual browser with scripted/synthetic evidence clearly
labelled, without enabling a paid worker.

## Task 5: Integrated review and acceptance

Coordinator integrates after scoped checks. Independent reviewer checks focused
storage/concurrency and report provenance/UI warnings, then whole diff. Resolve
actual blockers with regressions. Run integrated suite once with local PostgreSQL
and real Chromium. Concurrency tests use separate connections/barriers, not sleeps
alone, and prove mutex scope, publication fencing and review race ordering.

## Task 6: Evidence, documentation and PR13

Record scoped and full checks, timing boundaries and remaining live uncertainty;
provide a meaningful prepared-report artifact and comparison with old on-demand
path without relabelling previous bad reports. Update PRD/runbook/handoff and PR13.
Check mergeability and Ewen/PR6 ancestry; push only coordinator changes. Leave DB
running, schedules disabled unless explicitly configured, no merge/deployment.

## Review focus

Cross-run verification identity, overlapping source sets, multi-scope waits that
must not follow later cycles, expired-worker publication, review/rejection races,
as-of and permission changes, warning persistence, synthetic-vs-real timing claims,
and partial evidence incorrectly described as complete are mandatory controls.

Rulings: user explicitly requested execution of the approved design; routine
implementation choices do not require another design/plan approval round. The
current worktree is already isolated. Preparation publication may be partial
only with truthful dispositions; machine-unsupported/rejected facts never enter
the fast report. No new paid run is inferred from the five-minute target.
