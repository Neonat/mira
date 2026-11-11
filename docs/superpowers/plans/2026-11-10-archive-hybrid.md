# Full archive experimental retrieval plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for coordinator implementation; one bounded independent evaluation worker and final read-only reviewer.

**Goal:** Remove the corpus-size fallback and measure hybrid usefulness against keyword search.
**Architecture:** Incremental content-bound cache indexing; full eligible archive SQL lexical/cosine retrieval with bounded top-k/deadlines, explicit indexing coverage.
**Tech Stack:** Existing Python, OpenAI embeddings, PostgreSQL/pgvector, pytest.
**Spec:** [design](../specs/2026-11-10-archive-hybrid-design.md), implementing the user's current request.

## Constraints and review focus

MAS disabled; no source grants, role models, historical reports, global settings or remote deployment changed. Batch bounds are not corpus bounds. Preserve known/unknown usage and prior cache batches under failures. Partial/unindexable coverage must be visible. Exact SQL gates precede ranking; keyword baseline uses equal scope/caps. No presumption of semantic superiority or human precision without labels.

## Tasks and ownership

- [x] Coordinator: write failing archive DB tests in `tests/test_hybrid_archive_db.py`; implement SQL/ranking in `mira/hybrid_archive.py` and bounded indexing/runtime in `mira/hybrid_runtime.py`. Add limits in `mira/hybrid.py`, factory in `mira/runner.py`, diagnostics in `mira/agents/scout.py`, bounded index CLI/tests and new cache source-gate migration. Narrow red/green before broad checks.
- [x] Evaluation engineer: own only `eval/hybrid_archive_compare.py`, `eval/test_hybrid_archive_compare.py`, `eval/hybrid_archive_queries.json` and `docs/agent-handoffs/archive-hybrid-evaluation.md`. Pure offline comparison and 36 tests; six unlabelled questions frozen before retrieval. No provider/DB/runtime calls or benchmark injection.
- [x] Integrate74focused proofs and execute one bounded validation:16 requests/29,949 tokens/137,040 bytes/16.797 seconds. Saved153/153indexed, no pending; controlled 47/47rolled back. No acquisition/generative role calls; MAS inactive.
- [x] Fresh runtime review; fix both accounting/character findings with regressions and re-review. One complete PostgreSQL/Chromium tests+eval run:997 tests+ 8 subtests, no skips,in 71.56 seconds. Runtime commit `eb83d0e`.
- [x] Final evidence/documentation review: no blockers; all 15 artifact hashes/six runtime fingerprints, 997 + 8 proof and scope/usage/interpretation checked. Prepare PR13 delivery; preserve Ewen's changes, no merge/deployment or further paid execution.

Coordinator final native checks: 153 eligible/indexed, 0 pending/blocked, unchanged corpus hash, MAS inactive, no synthetic fixture workspace, interrupted old run still failed. All 148 local document links and added-content secret scan passed. Final step is pushing the reviewed implementation/evidence commits and verifying PR13 head; no additional proof run is needed.

Base `4eb63707ef8ecdaecf9c472f46be18c81691b6c1`; existing isolated PR13 worktree. Existing credentials were previously authorized for this project and are reused without exposure. Full implementation is within the user's request; coordinator selects the implementation details above. No further paid execution beyond the single validation.
