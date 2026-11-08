# Analysis coverage database handoff

Objective: add the approved worker-only passage-analysis ledger and canonical frozen report summary.
Base SHA: `e4ad439f77bae4ad8d41097251011d3bfaeeeb7c` (`codex/passage-coverage-retrieval`).

Owned files:
- `supabase/migrations/20261108120000_mira_analysis_coverage.sql`
- `tests/test_analysis_coverage_db.py`
- This handoff.

Read-only sources: `AGENTS.md`, handoffs README; coordinator `.superpowers/sdd/2026-11-08-evidence-completeness/coverage-db-contract.md`; evidence-completeness design/plan; PRD v3 §§5.1–5.4; prior schema, evidence-freeze and corroboration migrations; pipeline DB fixtures, `mira/db.py` and `mira/pg_store.py`. No shared contracts, existing migrations, orchestration or configuration edited.

Changes:
- Add immutable policy/document/event tables with scoped foreign keys, member-only reads, worker-only writes, actor binding, metadata-only audits, idempotent inserts and revision-row locking. Eligibility checks source scope/permissions/activity, market, publication as-of, latest eligible version and saved passages.
- Candidate precedes other events; successful/failed events require matching analyst attempts in the same run/batch/step; failed/deferred events require reasons. Summary counts unique passage identities and latest dispositions, retaining zero-passage and excluded documents and ever-attempted counts.
- Early report guard preserves rejection of originally forged legacy `1.6` before existing wrappers rewrite versions (coordinator approved). Final `zzzz` trigger requires canonical summary equality and latest draft equality at review, then sets `1.6` without requiring corroboration. Legacy reports remain unchanged. Reviewed revisions reject new ledger entries; identical retries remain no-ops.
- Event identity defaults allocate before a contended revision lock. Final sequence is therefore reallocated under that lock, preventing preallocated values from reordering dispositions. Sequence gaps are intentional; watermark is deterministic over persisted events.

Scoped checks/results:
- Initial fixture setup mistakes were corrected; 12 tests then failed for missing tables/functions or absent validation before implementation.
- Applied only the new migration to `postgresql://postgres:postgres@127.0.0.1:55432/postgres` using psycopg. After the sequence regression failed, replaced only this migration's new validation function locally; no reset or old migration/schema changes.
- Final command: `MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_analysis_coverage_db.py -q -p no:cacheprovider` → **27 passed in 1.85s**.
- Covers zero/absent policy; counts/audit/idempotency; immutable tables; actor/scope/step guards; authenticated write denial/nonmember read isolation; source/as-of/stale/no-text eligibility; stop reasons; draft/review forged/stale/missing/latest-draft handling; legacy preservation; frozen review without corroboration; transaction rollback; watermark ordering; separate-connection lock timeouts proving event/report serialization on revision rows.
- `git diff --check` passed. No full suite, live/provider run, paid call, remote migration, commit or push.

Limits: SQL transaction rollback is tested, but atomicity of actual Python claim persistence plus analysed events remains coordinator-owned integration work. This measures passage processing coverage; it establishes neither exhaustive fact extraction, publication recall, cited-source verification nor independent corroboration. No historical coverage is invented. The local DB has the final migration objects; do not blindly reapply its non-idempotent CREATE TABLE statements.

Exact next step: coordinator integrates the settled store methods with this canonical SQL capture, adds the actual claim-save rollback test, obtains focused migration review, then runs the single integrated full suite. Review the assigned migration/test files directly; no historic chat required.

Status: complete for the bounded database assignment; integration and independent review remain coordinator-owned.
