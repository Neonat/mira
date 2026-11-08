# Private original storage adapter

Objective: implement the bounded pure private-original adapter; caller/UI and metadata integration remain coordinator-owned.

Base SHA: `e4ad439`; assigned branch `codex/passage-coverage-retrieval`.

Owned files: `mira/originals.py`, `tests/test_originals.py`, this handoff. Read-only: `mira/store.py`, current handoff README, accepted evidence-completeness design, existing browser tests and project configuration. No shared files, source grants, model settings, commits, pushes, providers or network calls changed.

Sources/commands: read `docs/superpowers/specs/2026-11-08-evidence-completeness-design.md` and `docs/agent-handoffs/README.md`. Scoped command: `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_originals.py -q`.

Changes: `RetentionPolicy` defaults off with a 20,000,000-byte bound and environment construction. Retain requires `store_text`, a literal approved grant and nonempty reference, plus HTTP fetch or manual import acquisition. Browser DOM and unknown acquisition methods return no identity. Bounded byte storage uses workspace/digest paths, private directories/files and atomic no-overwrite hard-link publication from a flushed temporary file. Reads and repeated writes verify digest/size. Every root/ancestor/workspace path component opens with `O_NOFOLLOW` through directory descriptors; original files must be private regular files. Identity is JSON-compatible and contains no local path.

Scoped checks and results: test-first missing-module red (14 failures), followed by green **14 passed in 0.10s**. Cases cover opt-in and grants, environment bounds, browser distinction, both eligible methods, round trip, immutability/idempotence, permissions, oversize, corruption, invalid identity/cross-workspace and symlink ancestors/root/workspace/file. Full suite intentionally reserved for coordinator integration per assignment/repository rules.

Open risks: adapter cannot establish active source/database workspace membership or caller authentication/role; coordinator must validate these against current state before retain/read, including source permission revocation. Exceptions (`ValueError` for invalid bytes/identity/integrity, `OSError` for filesystem failures) must be caught so saved extracted text survives retention failure and metadata is saved only after success. Root must be a dedicated local directory; any symlink ancestor is rejected (configure canonical absolute paths). File permissions are OS-level, not cryptographic encryption. No live retention or MAS grant created.

Exact next step: coordinator wires successful returned identity into saved acquisition metadata and authenticated current-workspace/source/role checks; independent reviewer checks this focused diff, then coordinator runs integrated suite once.

Status: complete.

## Evidence writer and authenticated access follow-up

Objective/base: same accepted design and `e4ad439` base. Additional explicit ownership: `mira/evidence.py`, new `mira/original_access.py`, new `tests/test_originals_evidence_db.py`, new `tests/test_original_access.py`; coordinator also explicitly requested the malformed-config guard in `mira/originals.py` (covered in `tests/test_originals.py`). No other runtime/shared files edited.

Changes: `EvidenceWriter(..., originals=None)` constructs an off-by-default private store from environment (`MIRA_ORIGINALS_DIR`, otherwise `REPO_ROOT/private-originals`). Before retention it loads the actual active source in the writer workspace, including current operations/config, rather than trusting page grants. HTTP/manual byte capture is eligible; browser acquisition flags take precedence over manual flags, and unknown acquisition methods cannot retain. Returned identity is checked against actual capture digest/length/workspace. New version metadata records `original_retained`, `retained_original`, and bounded `original_retention_status` (`retained`, `not_enabled`, `not_permitted`, `failed`). Storage/configuration failures preserve extracted text/passages. A successful repeated real capture may add retention identity to the existing version; no historical capture is invented. Caller-supplied original metadata cannot override writer-generated fields.

`read_original(client, workspace_id, version_id, store)` requires the signed-in app client, `auth.get_user()`, current workspace membership and RLS-visible workspace-bound version/document/source rows. It gets identity only from saved version metadata. Current source must remain active, permit `store_text`, and hold an approved retention grant with exactly the identity's approval reference. All auth/query/storage/identity failures produce a generic `PermissionError` without path/credential details. Coordinator must supply the existing signed-in Supabase app client; never a service-role/worker client.

Scoped checks: used only the supplied local PostgreSQL instance at `127.0.0.1:55432`, with `test_pipeline_db` throwaway workspace fixtures and local byte fixtures. Initial tests: 27 red failures plus one expected foreign-key case; green 28. Added red/green path-redaction test and malformed-configuration tests. Pure adapter now rejects non-mapping connector config before `.get()`; grant is accepted only as a mapping. Final direct command:

`MIRA_TEST_DATABASE_URL=<supplied-local-DSN> /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_original_access.py tests/test_originals_evidence_db.py tests/test_originals.py -q`

Result: **46 passed in 0.68s**. Earlier scoped regression group including `tests/test_evidence_integrity_db.py`, `tests/test_manual_import.py`, `tests/test_live_browser_integration.py` passed **84 in 3.11s** before the final malformed-config hardening and concurrent retrieval edits. A later run of that group produced **66 passed, 3 failed, 16 errors**: all pipeline failures reported `could not determine data type of parameter $1` in scout tasks. Coordinator notified and assigned the concurrent query issue to its owner; worker did not touch retrieval files or repeat the group.

Exact failing/error test identities from that concurrent run:

- `tests/test_evidence_integrity_db.py::test_same_passage_quotes_survive_verified_signoff[distinct-quotes]` and `[identical-duplicate]` (failures).
- `tests/test_live_browser_integration.py::test_http_block_browser_evidence_is_verified_and_frozen` (failure).
- `test_evidence_integrity_db.py` setup errors: `test_signoff_freezes_complete_metadata_and_verification_provenance`, `test_signoff_overwrites_caller_forged_bundle_with_server_capture`, `test_foreign_snapshot_run_or_revision_is_rejected[analysis_run_id]` and `[analysis_revision_id]`, `test_post_verification_support_addition_requires_new_verification`, `test_post_review_support_addition_requires_new_review_even_after_worker_recheck`, `test_legacy_checks_require_fresh_verification[missing]` and `[unbound]`, `test_app_analyst_cannot_forge_verification_bindings`, `test_reviewed_snapshot_and_identity_cannot_be_replaced[evidence_snapshot]`, `[template_version]`, `[reviewed_by]` and `[report_version]`, `test_frozen_rerender_survives_live_citation_source_label_changes_and_unavailable_retrieval`, `test_future_dated_check_cannot_be_frozen_as_signoff_verification`, `test_long_supporting_quote_persists_and_identical_candidate_deduplicates`.

Open risks/next step: coordinator owns frozen provenance contracts, UI original-download action, signed-in client wiring, and integrated suite after concurrent SQL fix. Storage is a separate filesystem side effect before DB insert, so DB rollback may leave an unreferenced private content-addressed object (never a false retained version). Source permission recheck does not lock a source against later revocation; access checks current permissions again. No real source grants, MAS activation, live/provider calls, models, migrations, commits or pushes changed. Files handed back; worker will make no further edits unless assigned.

Status: complete for owned implementation; integrated regression verification remains coordinator-owned.
