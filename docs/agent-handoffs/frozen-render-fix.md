# Frozen evidence contract and reviewed rendering

Objective: Capture canonical actual verifier inputs and render reviewed reports exclusively from a validated frozen evidence bundle.

Base SHA: `ad79028` (coordinator assignment).

Owned files: `mira/contracts.py`, `mira/store.py` provenance and check-input signature, new `mira/evidence_snapshot.py`, `mira/render.py`, `mira/render_job.py`, `tests/test_render.py`, new `tests/test_evidence_snapshot.py`, this handoff. Shared checkout; no other writers' changes reverted.

Read-only sources: `AGENTS.md`, `docs/agent-handoffs/README.md`, evidence-integrity spec and plan, `mira/report.py`, `mira/agents/verifier.py`, current sign-off migration and related DB tests. Coordinator explicitly extended the bundle with frozen verification provenance during implementation.

Changes:

- Contract version 1.4. Added typed `EvidenceInput`, `FrozenFinding`, `FrozenCitation`, `FrozenPassage`, `FrozenExpectedSource`, `FrozenVerification`, `FrozenEvidenceBundle`. `ReportSnapshot.evidence_bundle` defaults to None for reading legacy records. Bundles require `verifications`, containing semantic check provenance for each retained finding; EvidenceInput does not contain it.
- `PassageRecord` appends nullable capture hash, extraction version, page and character range. No hash or extraction metadata is invented. `RunStore` and `InMemoryStore.save_checks` accept keyword `input_snapshot`; in-memory check_inputs preserves independent copies aligned with checks.
- `build_verification_input(ctx, claim, claims, passages)` captures the actual claim, full recursive closure, supporting citations and all required passage metadata. Canonical dependencies sort by UUID and citations by passage UUID/quote (all actual input citations have support_type supports). Missing dependencies/passages, mismatched record IDs and cycles fail explicitly. Temporary labels are removed.
- Reviewed renderer ignores all legacy live-context keyword arguments. It validates bundle/report identity, recursive closure, passage identity and document-version relationships, per-version metadata consistency, factual support and deterministic quote match, semantic supported verification, required retained review outcomes and coverage labels. It hydrates deterministic labels, preserves amendments and rejects exclusions. Legacy reviewed snapshots require fresh verification and review.
- `render_one` performs no mutable evidence/brief/source/reviewer reads. It validates row/workspace/revision/sign-off identity before rendering, uses stored generated_at for stable HTML and bundle run ID for the artifact path. Existing pending error handling remains. Unused load_findings/reviewer_name utilities are retained for compatibility.

Scoped commands/results:

- Initial RED: `.venv/bin/pytest -q tests/test_render.py -k legacy` failed because legacy rendering did not raise.
- Added frozen verification requirement produced expected missing-model validation failure before its implementation.
- Final: `.venv/bin/pytest -q tests/test_render.py tests/test_evidence_snapshot.py` — **27 passed in 0.19s**.
- `git diff --check -- mira/contracts.py mira/store.py mira/render.py mira/render_job.py tests/test_render.py` — clean.
- No full suite, DB run, paid/live API call, commit or push.

Open risks: Database capture, attestation binding, sign-off validation and DB fixture updates are coordinator-owned and must match these contracts exactly. Render verification fingerprints are retained diagnostics; Python does not recompute PostgreSQL JSONB-text hashes. Old reviewed files are preserved, but old snapshots cannot be regenerated.

Exact next step: Coordinator integrates pg_store/orchestrator/migration, executes scoped database evidence-integrity tests, then independent review and one integrated full tests+eval run. Ensure pending_signoffs fixtures provide generated_at and SQL bundles include REQUIRED verifications for every recursive retained finding.

Status: complete (assigned pure contract/render work).

## Additional isolated database regression assignment

Owned addition: NEW `tests/test_evidence_integrity_db.py` only, plus this handoff append. Coordinator applied migration `20261107180000` and explicitly authorized a focused local DB run. No migration or other file changes in this assignment.

The new module imports the existing pipeline conn/workspace/run_hk/analyst/review/sign-off helpers and contains **14 parameterized cases**:

- Complete frozen finding closure, passage provenance/version metadata, brief, coverage labels, reviewer identity and exact semantic verification provenance.
- Caller-forged bundle replacement with a server capture; foreign snapshot run/revision refusal.
- Post-verification evidence additions through an authenticated analyst's RLS context block sign-off.
- Post-review additions still block after fresh scripted worker verification; fresh review then permits sign-off. Actual verification inputs are built before LlmVerifier calls and saved through PostgresStore, not copied from server capture SQL.
- Missing and unbound legacy checks block; test-only check deletion/nulling is enclosed in force_rollback transactions on this synthetic run.
- An app analyst cannot forge claim_checks attestations.
- Reviewed snapshots, template, reviewer and report version cannot be replaced, even by the worker connection.
- Reviewed re-render stays byte-identical after new live evidence links, source names, coverage labels and reviewer email changes, and while live passage/finding/reviewer retrieval methods raise if called.

Commands/results (all target the coordinator's local `127.0.0.1:55432` fixture database):

- `MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres .venv/bin/pytest -q tests/test_evidence_integrity_db.py` — 12 passed, 1 synthetic setup failure (changing all coverage labels to one string violated an existing uniqueness constraint).
- Fixed setup to append each row UUID. `... pytest -q tests/test_evidence_integrity_db.py -k frozen_rerender` — 1 passed, 12 deselected.
- Added explicit missing-check parameter alongside legacy null binding. `... pytest -q tests/test_evidence_integrity_db.py -k legacy_checks` — 2 passed, 12 deselected.
- All final 14 cases have passed across those focused runs. No repeated whole-file proof run after correction; integrated full suite remains coordinator-owned.
- `git diff --check -- tests/test_evidence_integrity_db.py` — clean.

Open review observation sent to coordinator: render.py currently treats extraction_version as common document-version metadata, although canonical capture can use each passage's extraction_version. Different passage extraction versions within one document version can be legitimate; remove that comparison or assign a focused follow-up. No runtime files were changed under this additional tests-only assignment.

Next step: Coordinator includes this module in the one integrated suite, handles the extraction_version consistency observation and independent review. No paid/live API, commit, push or full suite run performed. Status: complete.

## Quote identity and future-check review follow-up

Additional assignment owned only `tests/test_evidence_integrity_db.py` and this append. Added three cases:

- A scripted analyst cites two distinct quote slices from the same passage. The real scripted verifier/pipeline must preserve two stored and frozen citation quotes, sign off and render successfully.
- An identical passage/quote pair repeated in analyst output deduplicates to one stored/frozen citation and still signs off/renders successfully.
- A future-dated synthetic check copies the original real worker check's actual input snapshot, fingerprint, model and prompt provenance at the next attempt. Sign-off must retain the original eligible check rather than freeze the future check, and render successfully.

Focused command: `MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres .venv/bin/pytest -q tests/test_evidence_integrity_db.py -k 'same_passage_quotes or future_dated_check'` — **3 passed, 14 deselected in 0.65s**. Coordinator's constraint/time-bound fixes were active before first execution; no new failing run was observed. No whole-file/full-suite repetition. No runtime/migration edits, API calls, commit or push. Status: complete.
