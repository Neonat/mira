# Evidence Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make omitted analysis visible, analyse saved passages in bounded batches, retain permitted originals, and add opt-in hybrid retrieval with an auditable path to readable source pages.

**Architecture:** A worker-written passage ledger feeds a frozen report summary. Pure batching logic is separate from orchestrator/persistence integration; original storage and semantic retrieval are optional adapters preserving existing source and evidence controls.

**Tech Stack:** Existing Python/Pydantic/PostgreSQL/pgvector, authenticated Streamlit review and private local artifact storage; scripted providers for validation.

**Spec:** `docs/superpowers/specs/2026-11-08-evidence-completeness-design.md`

## Global Constraints

- MAS stays disabled; do not expand existing source permissions.
- Existing Mira role model and effort settings are unchanged; new embedding/retention features are opt-in.
- Keep workspace/source/as-of/version guards before ranking and limits.
- No historical input/coverage backfill, signed-file rewrite, paid research, remote migration, merge or deployment.
- One writer per file; coordinator owns shared contracts/orchestration/migrations/pushes. At most three bounded workers; no recursive delegation.
- Scoped tests during work; one final complete local PostgreSQL/Chromium tests/eval suite after integration. Repeat only for changed code or a real failure.

## Review Focus

- Long and duplicate passage identities must not be silently truncated/rebound.
- Cross-batch labels/dependencies and failure handling must retain earlier facts without unsafe inference links.
- Coverage counts must match eligible passage versions and freeze at sign-off, including failed/deferred work.
- Private originals must not become cross-workspace file reads or mislabelled browser captures.
- Hybrid vectors must respect source/version eligibility and compatible model identity before limits.

### Task 1: Pure analysis batch planning

**Files:** create `mira/analysis_batches.py`, `tests/test_analysis_batches.py`.
**Interface:** frozen `AnalysisLimits` defaults from spec; `BatchPlan(batches, deferred)`; `plan_batches(passages, limits) -> BatchPlan`; `namespace_claims(claims, offset) -> list[NewClaim]`. Whole passage inputs, stable ordering, duplicate ID/content disagreement rejected; oversized/cap omissions explicit. Namespace each local C label to sequential global C labels while retaining resolved evidence and intra-batch dependencies.

- [x] Write tests for multi-document/multi-fact passage preservation, exact size/count/call boundaries, duplicate identity conflict, oversized deferral and label/dependency mapping.
- [x] Observe expected red failures; implement minimal pure functions and positive-bound validation; run scoped tests.
- [x] Review this bounded diff before orchestration depends on it.

### Task 2: Coverage ledger and normal-worker batch analysis

**Files:** coordinator `mira/contracts.py`, `mira/store.py`, `mira/pg_store.py`, `mira/orchestrator.py`, `mira/agents/analyst.py`, `mira/runner.py`, `mira/render.py`, `mira/report.py`, new additive coverage migration and new focused coverage orchestration/database tests.
**Interface:** store reads full eligible version passages and appends analysis dispositions; normal runner supplies `AnalysisLimits`; report freezes typed analysis coverage. Coordinator settles exact persistence signatures before any worker edits shared files.

- [x] Reproduce A/B/C in disjoint saved passages when scout exposes only A; require recorded B/C disposition and successful extra batch claims under allowance.
- [x] Add scoped worker-only ledger constraints/RLS, full-version source/as-of filtering and transaction-safe claim/disposition writes.
- [x] Integrate bounded calls, reservations, unique labels and partial-result handling; retain direct legacy/single-agent behavior.
- [x] Test size/batch/time/token stops, failures/empty output, cancellation, unknown usage, scope isolation and frozen report behavior; review.

### Task 3: Permission-controlled private originals and page navigation

**Files:** new original-storage adapter/tests, assigned evidence/import/acquisition wiring, coordinator metadata/migration/review-viewer integration, report PDF page links/tests.
**Interface:** storage adapter writes/verifies immutable workspace-bound captures; caller supplies explicit retention approval and records successful capture identity. Authentication remains in the existing workspace-scoped app boundary.

- [x] Test bytes/digest identity, opt-in/source grant denial, browser-DOM distinction, path/symlink/cross-workspace/corruption cases before implementation.
- [x] Implement bounded retention and authenticated access; add readable PDF page references without altering saved source URLs.
- [x] Test original-storage failure preserves extracted evidence and no private raw path/credentials reach HTML; review.

### Task 4: Bounded opt-in hybrid passage retrieval

**Files:** new embedding/hybrid adapters and tests, assigned scout retrieval integration; coordinator factory/config and usage persistence as needed.
**Interface:** compatible model/revision/dimension-labelled passage vectors; filtered lexical/vector candidates, deterministic fused ranking and explicit fallback/usage diagnostics.

- [x] Controlled synonym/exact-term/irrelevant/cross-workspace/latest-as-of fixtures compare equal candidate limits.
- [x] Implement bounded indexing/query calls and compatible storage, then scoped normal-worker retrieval wiring with usage accounting.
- [x] Test denied embed operations, dimension/model mismatch, failure/timeout and lexical fallback; review.

### Task 5: Integration, measurement and PR

- [x] Integrate all scoped tasks; apply new migrations to local test PostgreSQL only.
- [x] Run focused regressions and independent whole-diff review, fixing blockers before final integration verification.
- [x] Final-candidate `pytest tests eval`:691passed+8subtests,no skips,92.39s. The first run exposed six old task stubs, corrected before this result.
- [x] Update PRD/README/handoff with demonstrated behavior, accurate audience and explicit fixture/live evidence distinction; no historical metric rewrite.
- [ ] Secret/scope/JSON/diff checks, commit/push and open a reviewable PR. Do not merge it.
