# Evidence integrity implementation plan

> For agentic workers: use the approved scope and explicit ownership below; do not ask for another scope approval. User explicitly requested implementation and database tests. Coordinator integrates the existing feature branch; workers do not commit, push or delegate.

**Goal:** Preserve exactly the checked/reviewed evidence and exclude superseded retrieval candidates.
**Architecture:** Worker-attested verification input, server-attested review input, typed server-frozen sign-off bundle and bundle-only renderer. Current research selects eligible versions before ranking.
**Spec:** `docs/superpowers/specs/2026-11-07-evidence-integrity.md`.

## Constraints and review focus

No ingestion expansion/corroboration, paid/live APIs, raw-capture/durable-storage build or remote migrations. Preserve original reports. Do not silently fabricate legacy verification inputs. Detect cross-workspace/run JSON, missing transitive evidence, post-check/post-review insertions and stale metadata; no mutable joins during reviewed rendering.

## Task1: Version selection — coverage engineer

Owned scout.py, new test_version_retrieval.py and version-retrieval-fix.md handoff. No other shared files.

- [x] Reproduce stale version leakage.
- [x] Select eligible versions before FTS rank/limits across all passage acquisition paths.
- [x] Run focused reuse/version tests and local isolated database checks; return handoff.
- [x] Coordinator review and integration.

## Task2: Bundle contract and render — assigned worker

Owned contracts.py, store.py provenance/RunStore signature only, new evidence_snapshot.py, render.py, render_job.py, tests/test_render.py, new tests/test_evidence_snapshot.py. Coordinator owns pg_store.py/orchestrator.py/migration/database tests. Consume exact spec JSON shape.

- [x] Add failing pure regressions for missing evidence, changed live citations, dependency closure and legacy refusal.
- [x] Add typed bundle models and actual verification-input builder; extend PassageRecord compatibly and store protocol signature.
- [x] Validate complete bundles and hydrate renderer context exclusively from frozen data, before writing artifacts.
- [x] Run focused pure tests and return handoff; no full suite.

## Task3: Trusted DB binding — coordinator

Owned new migration, pg_store.py, orchestrator.py, tests/test_pipeline_db.py, tests/test_worker_db.py and new tests/test_evidence_integrity_db.py.

- [x] Write failing database regressions for mutation/forgery and frozen independent re-render.
- [x] Store actual pre-call input on checks; capture review input server-side; freeze a server bundle at sign-off after validating matching trusted inputs and scope.
- [x] Apply local migration only; protect reviewed snapshot identity, preserve legacy rows/artifacts.
- [x] Update test fixtures to create legitimate worker attestations instead of silently accepting legacy checks.
- [x] Run narrow database tests, resolve concrete failures.

## Task4: Integration — coordinator and fresh reviewer

- [x] Independent diff review, including concurrency/permissions and actual-input binding.
- [x] Run full tests+eval once with local PostgreSQL after integration.
- [x] Update PRD/checkpoint/handoffs; no generated artifacts/secrets.

Publication follows this verified source checkpoint on existing PR3. Final validation: 350 tests plus 8 subtests, none skipped, including local PostgreSQL; 26 subsequent focused checks passed against the separate report-layout commit. Independent scoped review accepted the final backend/UI/index changes. No paid/live runs, remote deployment, ingestion expansion or corroboration.
