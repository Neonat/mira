# Reconciliation validation — 2 November 2026

Integrated origin/main at 9798269 with Nat’s ingestion branch at af34a56. The working tree was clean before the merge, so no stash was created. Resolved conflicts in README.md, .gitignore and mira/__init__.py by retaining both workflows and updating the status documentation.

## Integration

- Local ingestion remains at `app.py`; authenticated research/review remains at `app/streamlit_app.py`. The local UI never imports the worker database layer.
- The workbench exports an integrity-checked original and CSV in a portable ZIP for `python -m mira import mas --manifest ...`. Fixture-marked demo sources cannot be exported for workspace import.
- The trusted importer re-extracts and applies workspace/source permissions. Database IDs and original-byte hashes remain separate from local staging identities.
- Shared UI/PDF dependency versions match the existing workbench.
- Fixed shared imports reporting failed/unsupported extraction as saved; failed evidence remains auditable but ingestion status now reflects the failure.
- Manual source URLs reject embedded credentials, nonstandard ports and malformed ports.

## Validation performed

1. Component tests for local ingestion, queue, library, PDF, upload validation and UI filters passed.
2. Research, agents, evaluation and security-boundary tests passed independently.
3. Started a fresh local Supabase stack; all four checked-in migrations applied successfully. No hosted project was linked or changed.
4. Twelve worker/database tests passed, including initiating-user audit trails and workspace roles.
5. Eighteen database E2E tests passed: source acquisition, evidence persistence, verification, cited HTML, gap rounds, plan approval/resume, rerun differences, review gates, reviewed rendering, manual imports and local-staging package to research report.
6. Final combined command: `MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres .venv/bin/python -m pytest tests eval -q` — **204 passed, 8 subtests passed, no skips**.
7. `pip check`, both CLI help entry points and Git whitespace/conflict-marker checks passed.
8. Browser checks: original PDF/passages and export controls rendered at desktop/mobile sizes; research app rendered its sign-in page.

## Limits

E2E uses a real local database with synthetic source responses and scripted models in isolated test workspaces. It does not establish live regulator availability, model accuracy, recall/precision, API cost or an authenticated browser journey. This checkout has no configured model credentials or user login. Research sign-in was visually checked, not completed with a real account. The two apps are intentionally separate stages, joined by explicit import, not automatic synchronization. No shared Supabase writes or remote Git push were performed.

Local development services: workbench on 8501, research UI on 8502, Supabase API on 55421 and Postgres on 55432. Test workspaces remain in this newly created local database; they are not in the application’s `mira` workspace.


## Follow-up — 6 November 2026

Integrated origin/main through e63546f into codex/nat-ingestion: the live three-arm runner, comparison decision rule and documentation updates. The working tree was clean before merging; the only conflict was README.md, resolved while preserving both workflows and prior validation evidence.

- Focused comparison component checks: 23 passed.
- Full regression against the existing local Supabase database: **217 passed, 8 subtests passed, no skips** (`MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres .venv/bin/python -m pytest tests eval -q`). This includes 30 pipeline/worker database tests.
- Extended the pipeline E2E to load the comparison runner's actual saved findings, resolve inference citations, build precision worksheet rows and retrieve the expected original URL through full-text search and the plain-search arm.
- Authenticated-role search succeeds for the workspace member and returns no passages for a non-member. The trusted worker connection intentionally bypasses RLS; setting actor claims alone is not an app authorization test.
- Recorded scripted models remain ineligible for a live comparison verdict. Pip dependency and Git whitespace checks pass.
- Restarted existing local Supabase containers after the cached npm CLI launcher failed to find its darwin-arm64 binary. No hosted database changes were made.

The model keys and research login remain unconfigured, so no live-model comparison or authenticated browser journey was completed. MAS manual ingestion remains necessary; prior successful local PDF imports do not establish that the full evaluation corpus is present. The ground-truth document still requires independent human review, and precision requires human labels. These checks validate software behavior, not recall or precision claims.
