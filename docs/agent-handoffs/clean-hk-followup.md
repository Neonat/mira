# Clean HK test and offline follow-up checkpoint

Objective: fix coverage selection and corroboration latency, run one clean bounded Hong Kong validation using actual Exa, keep MAS disabled and update PR7.

Base: `c5542eb`. Measured source: `43a7b1c1c25003ec63cac8dc27a2aa5ce59ffc10`. Latest offline follow-up: `78c67718327776eae7c98c32c83d094a8f0dd138`.

The one authorized run `7e877c4e-e10e-4e19-9025-450db0666773` completed uninterrupted as a model-written draft in 18.30 minutes, with 16 facts and three unresolved claims. It used the actual Exa API (six successful requests), 30 documents, reported 375,187 provider tokens and reserved 139,295 unknown-usage tokens, within the 600,000-token/25-minute allowance. MAS was inactive with zero fetches/versions; temporary HKMA browser permission was removed. Browser fallback did not trigger. No report sign-off or human precision labels were created.

**Acceptance failed:** acquired/cited coverage remained 5/18, and all six corroboration model calls timed out at thirty seconds. All orchestration steps succeeded because those model failures were recorded as inconclusive; that is not latency success. [Measured result](../../eval/evidence/2026-11-08-hk-clean-run-7e877c4e.md) and [portable metadata](../../eval/evidence/2026-11-08-hk-clean-run-7e877c4e.json) preserve the result. The observed source is not the later offline revision.

## Ownership and subsequent changes

Coordinator owns integration, `corroboration_runtime.py`, runtime-limit regression, PRD, evidence/checkpoint and push. Coverage worker owns scout/selection tests; evidence architect owns corroboration/workload tests and assigned client fixtures; evaluator owns the offline comparison/tests. Independent reviewer is read-only. One writer per file; no recursive delegation or worker pushes. No model/effort/global settings, source permissions or applied migrations changed.

The measured fixes retained dated aliases and reserved selected-link slots, but did not establish higher recall. Further retained diagnostics showed tasks exhausting all publication capacity in their first model choice. The offline scout now reserves a funded second existing selection round and supplies escaped prior-selection titles/dates as untrusted, not necessarily acquired. Insufficient estimated time/tokens leaves the original single-round capacity available. Review found that quota-deferred same-publication PDFs could then be suppressed as completed aliases; a red regression reproduced that content loss, and exact deferred PDFs now remain eligible with their date/provenance. Other source/as-of/seen/cache guards remain intact. Prompt version is `scout/6`. Extra calls add time/tokens; higher recall is unmeasured.

The failed clean run also recorded ordinary inference calls longer than thirty seconds. That supports a different bounded allowance, but does not prove the next deadline will succeed. Offline corroboration now uses one retrieved candidate, a compact single-decision schema retaining both propositions/origin evidence, 4,096 output tokens, and a sixty-second service allowance capped by remaining run time. The clock includes service preparation, optional discovery and prompt preparation; saved retrieval before service entry remains within the shared run allowance. Only one assessor attempt occurs, without retry or deadline reset. Full originals remain frozen; all limited-context relations, including apparent conflicts, remain uncertain. Legacy v2 bounded guards and explicit historical thirty-second values remain readable. Broader candidate coverage is traded for smaller work. Model/effort is unchanged.

[Official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs) was consulted for the schema constraints. Actual provider acceptance and latency for the revised schema remain untested; local mocked clients are not live acceptance proof.

## Verification

- Selection and workload regressions observed red/green; test doubles updated without removing their existing assertions. Independent review findings for truncated conflicts and deferred PDF content were resolved with adversarial regressions.
- Final command: `PYTHONPATH=/private/tmp/mira-browser-deps:. MIRA_BROWSER_EXECUTABLE=<existing Chromium> MIRA_TEST_DATABASE_URL=<local PostgreSQL> PYTHONDONTWRITEBYTECODE=1 /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests eval -q -p no:cacheprovider --basetemp=/private/tmp/mira-post-clean-offline-full --tb=short` → **538 passed + 8 subtests, none skipped, 52.38 seconds**.
- Includes PostgreSQL, actual Chromium fixtures, frozen legacy checks and primary numeric/quote guard regressions. Final focused reviews found no remaining blockers. Historical files/snapshots remain unchanged; no remote migration, merge or deployment.

## Exact next step and authorization

PR7 contains concrete offline fixes and the failed measured result. A proposed further test would use one new fresh-workspace HK run with the same brief, 30 documents, 600,000 tokens, 25 minutes, six Exa requests, one-candidate/sixty-second corroboration, MAS inactive and no continuation/replacement. It has **not** been executed. The user authorized one clean paid run and that run has been used; a further live test requires new explicit authorization.

Status: code/review/offline verification complete; coverage/latency acceptance unachieved and further live verification awaiting authorization. Do not claim the later fixes are live-validated.
