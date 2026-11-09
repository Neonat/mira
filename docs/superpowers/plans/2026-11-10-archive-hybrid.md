# Full archive experimental retrieval plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for coordinator implementation; one bounded independent evaluation worker and final read-only reviewer.

**Goal:** Remove the corpus-size fallback and measure hybrid usefulness against keyword search.
**Architecture:** Incremental content-bound cache indexing; full eligible archive SQL lexical/cosine retrieval with bounded top-k/deadlines, explicit indexing coverage.
**Tech Stack:** Existing Python, OpenAI embeddings, PostgreSQL/pgvector, pytest.
**Spec:** [design](../specs/2026-11-10-archive-hybrid-design.md), implementing the user's current request.

## Constraints and review focus

MAS disabled; no source grants, role models, historical reports, global settings or remote deployment changed. Batch bounds are not corpus bounds. Preserve known/unknown usage and prior cache batches under failures. Partial/unindexable coverage must be visible. Exact SQL gates precede ranking; keyword baseline uses equal scope/caps. No presumption of semantic superiority or human precision without labels.

## Tasks and ownership

- [ ] Coordinator: write failing archive DB tests in `tests/test_hybrid_archive_db.py`; implement SQL/ranking in `mira/hybrid_archive.py` and bounded indexing/runtime in `mira/hybrid_runtime.py`. Add limits in `mira/hybrid.py`, factory in `mira/runner.py`, diagnostics in `mira/agents/scout.py`, bounded index CLI/tests and new cache source-gate migration. Own shared integration/config/docs/push. Narrow red/green before broad checks.
- [ ] Evaluation engineer: own only `eval/hybrid_archive_compare.py`, `eval/test_hybrid_archive_compare.py`, `eval/hybrid_archive_queries.json` and `docs/agent-handoffs/archive-hybrid-evaluation.md`. Offline comparison consumes pre-exported candidate rankings/labels, equal top-k; no provider/DB/runtime calls or benchmark injection. Frozen generic AML query set and controlled fixtures with wins/ties/losses. Self-contained handover.
- [ ] Coordinator: integrate focused proofs, inspect existing saved corpus and execute the single bounded embedding validation in the design. Retain actual/request/reservation counts and index coverage; no research run.
- [ ] Fresh focused review, resolve findings; one complete PostgreSQL/Chromium tests+eval run after integration. Publish results/limits to README/current PRD/handoffs and update PR13, preserving Ewen's changes.

Base `4eb63707ef8ecdaecf9c472f46be18c81691b6c1`; existing isolated PR13 worktree. Existing credentials were previously authorized for this project and are reused without exposure. Full implementation is within the user's request; coordinator selects the implementation details above. No further paid execution beyond the single validation.
