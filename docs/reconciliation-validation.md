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


## DBS public-document checks — 6 November 2026

Following explicit user approval, saved the two public originals through Safari's PDF save and HTML Page Source save. Mira's robots-aware automated fetch refused the PDF; the browser download was separately authorised. No fetch policy was disabled.

Imported into isolated local workspace `test-real-dbs-b67bb5069c` (`673df2e7-4222-4bb5-8689-26280c7b51a1`). The workspace-specific `dbs-test` source permits metadata/text/quotes for these tests but not automated fetching. The production source seed, main application workspace, shared Supabase and M0 ground truth were not changed.

| Original | Extraction | Search checks |
|---|---|---|
| [2025 risk-management PDF](https://www.dbs.com/annualreports/2025/i/pdf/dbs-ar-2025-risk-management.pdf) | Complete, 17 pages, 78 passages | `"compliance risk"` and `"financial crime"` retrieved the expected supporting wording and original URL |
| [AI in banking article](https://www.dbs.com/artificial-intelligence-machine-learning/artificial-intelligence/ai-the-future-of-banking-and-finance.html) | Complete, 9 passages; date preserved as 2023-04-18 | `"human analysts"` and `"money laundering"` retrieved the expected supporting wording and original URL |

All four searches passed under the authenticated database role. Non-member retrieval returned no results. Original file hashes match saved version hashes, every passage matches its exact extracted-text offsets, and repeat imports reused the existing document versions.

Local originals, manifest, reproducible validation script and detailed results are in `data/manual/dbs/` (gitignored). Re-run with `PYTHONPATH=. .venv/bin/python data/manual/dbs/validate.py` while local Supabase is running. The script uses only the fixed local database address and reuses its saved test workspace.

Limits: no live-model report or regulatory recall/precision was measured. The article is historical background; the search adapter itself has no date filter, and exclusion from a current-period report remains unverified. The annual report's reporting year is not a confirmed publication date, so its publication date remains unknown. These records are in a test workspace and are not automatically visible in the main app workspace.


## Date-handling follow-up — 6 November 2026

Added deterministic checks to analyst output and rewrites: known publication/event dates outside the research period are rejected, as are claims supported only by publications known to be outside that period. Historical sources remain available as context and for an explicit current or upcoming effective date/deadline; the verifier must still establish that the text actually supports the date. Unknown publication dates remain eligible for verification and are not automatically treated as current. Publications after the as-of date are excluded from scout passages and rejected as claim evidence. Scout stored-source selection now uses period_end rather than as_of_date for the publication window. Prompt versions were incremented.

Validation: **233 passed, 8 subtests passed, no skips** with the full local-database command above. Added coverage for inclusive period boundaries, unknown dates, post-period and future publications, historical deadlines, analyst repair/rejection, rewrite rejection, and both direct-import and workbench-to-report flows. A persistent historical-only claim fails the analyst step before findings, verification or report generation rather than producing a misleading report.

A separate check against the actual stored DBS 2023 article rejected both scripted attempts to label its content a current development. Local details: `data/manual/dbs/date-results.json`. This establishes the code guard on real saved evidence, not live-model accuracy. Mixed-date evidence and unknown dates still require semantic verification; an invented deadline cannot be ruled out from publication metadata alone. No shared Supabase or model credentials were needed.
