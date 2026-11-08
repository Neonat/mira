# Clean HK offline evaluation helper

Objective: prepare reproducible offline comparison for the coordinator's single clean HK validation.
Base SHA: `c5542eb`.
Owned files: `eval/clean_hk_compare.py`, `eval/test_clean_hk_compare.py`, this handoff.
Read-only: runtime code, database, saved reports, benchmark labels and all other workers' files.

The CLI reads a finished validation's manifest/outcome/journal and local PostgreSQL in a read-only transaction. It refuses nonterminal/missing-finish/mismatched-outcome runs and workspace acquisition attribution unless exactly one run exists. Same HK brief/date scope is required for historical comparison. `.env` loading is restricted to the database key, worktree first and original checkout second; only local database hosts are accepted. It imports only existing evaluation helpers; no runtime execution or provider/source calls occur.

It exports aggregate metadata only: publication recall using explicit aliases; report citations including supporting facts; missing IDs; latest checklist row per expected source; report facts/inferences/unresolved; journal calls, measured tokens and unknown reservations; persisted corroboration statuses, errors/time-limit stops and completed steps; actual browser attempts; MAS activity/fetch/version counts; writer LLM success versus fallback; one workspace run, unresumed state and initial analysis count (rewrites excluded). Three historical references come from tracked `2026-11-08-hk-exa-run-fe65444d.json`. No precision labels or sign-off are created. No full publisher text, passages, raw steps, provider errors or credentials are exported.

Commands:

```sh
/Users/natsim/Documents/dbsearch/.venv/bin/python -m unittest discover -s eval -p test_clean_hk_compare.py -v
/Users/natsim/Documents/dbsearch/.venv/bin/python eval/clean_hk_compare.py --run-id RUN_UUID --validation-dir VALIDATION_DIRECTORY --output-dir reports/RUN_UUID
```

Scoped checks: six pure tests passed. They cover latest-round selection, known/unknown usage separation, terminal guard, explicit SFC aliases + market/date scope + supporting facts, excluding analyst rewrites from initial analysis, and joining corroboration model completions/errors/timeouts to prompt-versioned request IDs. An offline historical smoke against `fe65444d-589c-4a76-b3db-c216d76757ae` succeeded; ignored output is `reports/fe65444d-589c-4a76-b3db-c216d76757ae/offline-helper-check/clean-hk-comparison.json`. It reproduced 5/18 acquired/cited, 30 versions, 8 facts, 4 unresolved, checklist 3 found/5 missing/4 no-change/1 fetch-failed, 321591 known journal tokens and 270717 unknown reservations. No full suite or live check ran.

Open risks: one-run workspace count supports workspace acquisition attribution only for a fresh workspace as arranged by coordinator. Journal API counts represent instrumented model and Exa requests; browser attempts are separate. Corroboration `time_limit_stops` are saved assessment reasons. Separate journal corroboration model request/completion/error/explicit-timeout counts join request IDs to verifier `corroboration/` prompt versions; historical journals without prompt versions cannot classify those model calls. Inconclusive assessment status does not imply a provider error. Journal and assessment reservations may overlap and must not be added. Historical runs differ in transport, interruption and capacity; e2fda30f overshot 30 to 32 documents, a88dd20e had no report, fe65444d resumed twice. Results are observational, not controlled equal-budget evidence or human precision.

Exact next step: after the coordinator's one authorized clean run reaches terminal status, invoke the CLI once with its UUID and validation directory; inspect aggregate output and use it for the coordinator-owned result Markdown/PR7 update. Keep full report/steps/passages only in ignored local reports. No new paid run is authorized by this handoff.

Status: complete (preparation); new-run measurement pending coordinator terminal artifacts.
