# Ingestion and Corroboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand permitted publication ingestion, then add independent claim corroboration without weakening evidence integrity.
**Architecture:** Extend existing scout adapters; keep semantic corroboration separate from support verification; freeze results server-side.
**Tech Stack:** Python, Pydantic, psycopg/PostgreSQL; optional Exa and controlled browser adapter.
**Spec:** docs/superpowers/specs/2026-11-07-ingestion-corroboration-design.md

## Global Constraints
No live/paid calls; no model setting changes; no benchmark injection; no source permission expansion; no remote migration; no historical rewrite. One writer per file. Coverage milestone exits before corroboration implementation.

## Review Focus
- Unknown source origins must remain inconclusive rather than independent.
- Browser redirects/subresources must not bypass source, public address or robots policy.
- Saved evidence must be current eligible version before limits.
- New assessments after a review must invalidate fresh-signoff input but never mutate signed output.
- Query/document/time exhaustion must be bounded and visible even on failure.

### Task 1: Bounded ingestion expansion (coverage_engineer)
Owned: mira/agents/scout.py, mira/discovery.py (new), mira/browser_capture.py (new), mira/evidence.py, tests/test_ingestion_expansion.py (new), tests/test_research_coverage.py, docs/agent-handoffs/ingestion-expansion.md.
Interfaces: WebScout optional discovery/browser constructor adapters, existing defaults compatible; EvidenceWriter.save retains accurate capture metadata. Coordinator wires runner separately.
- [x] Write fixture regressions demonstrating lost candidate/publication slots and discovery/browser policy boundaries; run red.
- [x] Implement minimal adapters/selection changes and accurate capture/extraction provenance. Saved evidence remains mandatory before report.
- [x] Run focused ingestion/scout/fetch tests; report exact red/green commands.
- [x] Handoff interfaces, changed paths, limitations and next step.

### Task 2: Measurement and first integration (evaluation_engineer + coordinator)
Evaluation owns eval/test_ingestion_effects.py (new), docs/agent-handoffs/ingestion-measurement.md; runtime read-only. Coordinator owns runner.py, shared interfaces/contracts if needed, all migrations and integration.
- [x] Inspect retained telemetry without live acquisition, preserve unknown stage attribution.
- [x] Reproduce generic fixture selection/acquisition before/after effects separately from checklist/citation measures.
- [x] Independently review focused Phase-1 diff, resolve findings.
- [x] Run full tests/eval with local PostgreSQL once after integration; commit/checkpoint Phase 1.

### Task 3: Corroboration module (evidence_architect; starts after Phase-1 exit)
Own mira/corroboration.py (new), tests/test_corroboration.py (new), docs/agent-handoffs/corroboration.md. Coordinator explicitly assigns compatible corroboration schema in own migration; architect does not edit shared contracts/orchestration.
Interfaces: claim-level assessment consumes exact saved passages + proposition + origin evidence; produces validated immutable JSON result with all statuses, quotes, relationship reasons and search accounting. Discuss exact service signatures in concise handoff before coordinator integration.
- [x] Add red tests for all outcomes, stale/source/workspace/budget boundaries.
- [x] Implement saved-first, bounded optional discovery and proposition/origin assessment with conservative defaults.
- [x] Run focused tests; handoff integration details and risks.

### Task 4: Persist, bind and freeze (coordinator)
Own mira/contracts.py, mira/evidence_snapshot.py, mira/store.py, mira/pg_store.py, mira/orchestrator.py, mira/runner.py, mira/render.py, mira/review_display.py, new migration supabase/migrations/20261107200000_mira_corroboration.sql, tests/test_corroboration_db.py, tests/test_evidence_snapshot.py as needed; preserve worker disjoint files.
- [x] Write failing database/renderer tests for append-only workspace-scoped assessments, evidence eligibility, fresh verification/review and immutable reviewed output.
- [x] Implement persistence and server-frozen snapshot integration without modifying applied migrations or historical results.
- [x] Expose source/date/quotes/reasons separately from fact verification and reviewer decisions.
- [x] Focused tests; independent diff review and fix findings.
- [x] Run complete tests/eval with local PostgreSQL, update PRD/checkpoint/handoffs with exact results and limits, commit/push stacked PR targeting codex/nat-ingestion. Do not merge/deploy.

## Execution result
Phase1 checkpoint83c84c1, then corroboration implementation789a93a and final code42efc32. PR4merged during execution; integrated main16effde in78c92d8 and changed final publication target to main. Final offline/local PostgreSQL suite459passed+8subtests none skipped. Independent review findings resolved. No live/paid calls or remote deployment. Detailed handoffs carry commands and remaining limitations.
