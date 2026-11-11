# Enable hybrid retrieval and validate the configured provider

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the existing embedding integration, enable it locally and verify actual provider/cache/scout behavior while MAS stays disabled.

**Architecture:** Follow the approved [hybrid design](../specs/2026-11-08-evidence-completeness-design.md): PostgreSQL/pgvector passage cache, eligible whole passages, bounded keyword/cosine fusion and explicit fallback. No new retrieval algorithm or source grants. Use `text-embedding-3-small`, 384 dimensions, application cache revision `mira-te3-small-384-v1`; this tag is not a claimed immutable provider snapshot.

**Tech Stack:** Existing Python/OpenAI SDK, PostgreSQL/pgvector and pytest.

**Spec:** User request on 2026-11-10: configure the embedding model, enable hybrid retrieval, test it properly, keep MAS disabled and update PR13; existing approved design linked above.

## Global constraints

- Preserve role models, source grants, PR6 guards and historical reports; no remote migration, merge or deployment.
- Existing isolated worktree/PR13 branch; coordinator owns configuration, validation and docs.
- Reuse the existing authorized OpenAI credential without printing it; ignored environment files remain0600. Configure the worktree and existing primary local development checkout consistently; only embedding settings and the existing credential needed by the worktree factory are written.
- Default production retrieval limits stay40passages/60,000characters/20,000tokens/20seconds/20results; excess eligible pools fall back to keywords, not a silently sampled corpus.
- Coordinator authorizes **one controlled live embedding validation**, maximum2provider requests,8,000actual-plus-unknown-reserved tokens,6,000UTF-8 input bytes and90seconds overall; no Exa, publisher fetch, browser, generative role call or HK research execution. No automatic retry/resume/replacement.
- Synthetic passages only; MAS inactive with zero passages sent to the provider. Local validation DB writes are isolated/rolled back. No previous live allowance is reused.

## Review focus

1. Configured384dimensions match persisted vectors; cache revision is explicitly operator-managed.
2. Semantic retrieval must succeed for a synonym-only query with zero lexical matches.
3. Warm retrieval sends only the query and reuses all persisted passage vectors; repeated scout selection adds no request or duplicate charge.
4. Inactive MAS, foreign workspaces and incompatible source/version scope stay outside provider inputs/results; existing focused DB tests cover adversaries.
5. Provider failures/timeouts retain reservations and fall back; the live allowance remains consumed if execution fails or is interrupted.

## Steps and execution ledger

- [x] Inspect existing design/runtime/configuration, official embedding dimensions documentation and credential presence safely. Existing key reuse and local configuration are within this user's ongoing project authorization; no new key is requested.
- [x] Narrow baseline: existing hybrid/factory/deadline tests, then local PostgreSQL runtime tests after reachability check.
- [x] Set ignored local configuration; publish recommended model/revision in `.env.example` while keeping the template opt-in flag off for other installations.
- [x] Prepare one private controlled validation harness using the real factory, isolated SDK process, PostgreSQL cache and scout bridge; check its caps offline, then execute the single authorized validation and preserve aggregate results/hashes. Actual: 2 requests / 45 tokens / 269 bytes / 3.719 seconds; all assertions passed, fixtures rolled back.
- [x] Run one final complete suite with database/Chromium and embedding API disabled in test configuration. Do not repeat the full suite absent a new failure/change. Actual: 939 tests + 8 subtests, no skips, in 72.35 seconds; wrapper 73.53 seconds.
- [x] Fresh read-only review; resolve findings, update handoffs/README/current PRD and prepare the PR13 description with measured scope. No public claim of full-corpus semantic recall or a new HK end-to-end result.

Review: fresh reviewer checked the complete focused diff, raw request/result/proof, all five artifact hashes and source/runtime consistency; no blockers. Coordinator verified enabled factory/official API host, ignored 0600 environments, complete fixture rollback and existing research-workspace MAS disablement. Final delivery is coordinator push and PR-head verification; no merge or deployment.
