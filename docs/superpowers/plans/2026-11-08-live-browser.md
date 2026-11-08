# Live Browser Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans, with disjoint ownership below.

**Goal:** Acquire permitted public pages using a real browser and preserve exact evidence/budgets in PR7.
**Architecture:** Explicitly permitted, isolated, bounded Chromium adapter; HTTP-first acquisition with separate attempts; existing evidence verification/review pipeline.
**Tech Stack:** Python, Playwright Chromium, PostgreSQL, existing Mira contracts.
**Spec:** docs/superpowers/specs/2026-11-08-live-browser-design.md

## Global Constraints
No MAS enablement without established approval; no robots/access bypass, model configuration change, paid/model/Exa validation calls, historical rewriting, remote migrations or deployment. Keep PR6 intact. One writer per file.

## Review Focus
- Browser HTTP redirects/subresources cannot escape task/public-network/robots scope.
- A block page remains failure, never saved usable evidence.
- Both HTTP and browser attempts consume shared allowance and retain failures.
- Session isolation and hard process cancellation cover all browser children.
- Complete acquisition context enters checked/reviewed snapshots with backward compatibility.

### Task 1: Live adapter (coverage_engineer)
Owned: mira/live_browser.py, tests/test_live_browser.py, docs/agent-handoffs/live-browser.md.
- [x] Red tests for explicit permission, real Chromium JS/actions, policy boundaries and hard timeout.
- [x] Implement LiveBrowserAcquirer/LiveBrowserResult and preflight helper with frozen capture context.
- [x] Focused real-browser/unit checks and handoff; no full suite or commit.

### Task 2: Integration (coordinator)
Owned: mira/agents/scout.py, mira/fetch.py if needed, mira/runner.py, mira/corroboration_acquisition.py, mira/corroboration_runtime.py, mira/evidence.py, mira/pg_store.py, new migration20261108100000, tests/test_live_browser_integration.py and appropriate integration regressions.
- [x] Red fixtures for HTTP failure -> approved live browser -> saved evidence, separate budget/logging, disabled/no-permission refusal.
- [x] Wire adapter globally opt-in and per-source grants, preserve old offline adapter.
- [x] Add exact browser context to evidence identity/projection and frozen verification/review capture without editing applied migrations.
- [x] Prove end-to-end checked/reviewed rendering and immutable output; preserve PR6 regressions.

### Task 3: Review and delivery (coordinator/reviewer)
- [x] Independent focused review and resolve findings.
- [x] Complete tests/eval including local PostgreSQL after integration; no skipped required cases.
- [x] Record permitted live-browser validation only if source permission established; clearly disclose MAS gap otherwise.
- [x] Update PRD/checkpoint/handoffs, commit/push existing branch, update PR7. Do not merge/deploy.

## Result
Implementation0f9526d. Fullsuite487passed+8subtests none skipped in50.63s; independent review found no blockers. HKMA livecapture24.91s20,084chars128links, partial due2optionaldenials; initial60sunknown-stage timeout retained. MASdisabled; no paid/modelcalls; new provenance migrationlocalonly. ExistingPR7 updated, no merge/deploy.
