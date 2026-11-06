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

## OpenAI client — 6 November 2026

Added an OpenAI Responses API adapter behind the same structured-output interface as the team's Anthropic adapter. Both orchestrators and the live comparison runner now route each role using its existing `provider:model` setting. Claude defaults and behavior remain available. The new adapter streams strict JSON Schema, validates with Pydantic, retains usage on invalid/incomplete/refused outputs, and uses the existing repair retry. Provider errors are sanitized before recording. No provider-native search tools or silent model fallback were introduced.

Nat's ignored local configuration uses GPT-5.4 for planning, analysis and verification, and GPT-5.4 mini for scouting and writing. The key stays in the ignored local environment file. Separate verifier context is preserved, but this configuration is not cross-provider verification.

Validation: **241 passed, 8 subtests passed, no skips** against local Supabase, plus clean dependency and whitespace checks. Coverage includes strict request shape, repair/token accounting, refusals, incomplete responses, sanitized API failures, mixed-provider routing and evaluation liveness. Live synthetic smoke calls accepted the verifier and nested analyst schemas on GPT-5.4 mini; a routed GPT-5.4 verifier call also succeeded. These smoke calls establish connectivity and contract compatibility, not report quality.

Live HK run `2c5db30c-e1f8-434b-927e-9a7a4c4e5dda` completed on the isolated local workspace using the sample's 2025-11-04–2026-11-04 period. It produced `reports/2c5db30c-e1f8-434b-927e-9a7a4c4e5dda/report-v1.html` (gitignored). All executed model steps succeeded, including two analyst rewrites and report writing. The run is partial because it used all 15 documents: 179,908 tokens, 10.64 minutes and estimated standard-rate cost $0.8752 (not a billing record). Six claims were verified; two were unresolved. Final coverage combines rounds: two expected sources found, eight missing and two out of budget. Internal HTML citation targets resolve. Configuration, usage, trace and the implementation patch used during the run are saved under `reports/hk-reproduction/<run-id>/`.

This is a successful live integration test, not proof of equivalent quality to Saai's Claude report. The original run's evidence and model settings are unavailable. Both reports concentrate on HKMA PEP material; PDF/landing-page/RSS overlap and unknown appendix publication dates remain. The generated writer prose also needs human review: its impact assessment contains supervisory-focus interpretation and a suggested audit action even though two related analyst inferences were rejected. Valid citation labels alone do not establish sentence-level support. No human precision assessment, complete regulatory coverage, hosted Supabase writes or authenticated browser E2E were performed.

## Report grounding and retrieval follow-up — 6 November 2026

The writer now selects and orders claims; a final deterministic gate renders their complete saved content, rather than accepting new writer prose on the strength of valid citation IDs. Full statements preserve negations and conditions. Section eligibility prevents factual claims from being turned into new risks or recommendations. Both comparison arms use this gate; no independent verifier call was added to the single-agent arm. Writer step metadata records how many proposed sentences were replaced or removed. This is an intentional restriction on narrative freedom, not a claim that all model-verified claims are accurate.

Scouts share fetch/save results through run- and workspace-scoped futures. Concurrent requests for the same URL spend one document allowance; reuse is visible in the fetch log. Contract version 1.2 adds the `reused` fetch outcome without a database migration. Known HKMA PDF/landing aliases collapse in candidate selection and evidence ranking. Candidate prompts prioritize question relevance and balance hosts; unselected candidates remain available in subsequent rounds. Stored passages are restricted to the task's assigned sources. Identical text with different document identities or dates remains distinct. A coverage item marked found must have an explicitly linked passage from its own source; a fetched hub alone is insufficient.

Explicit RSS/Atom publication dates propagate to linked documents, and a narrow HKMA adapter reads an unambiguous standalone circular date before its salutation. Publication evidence is saved in version metadata. Unknown dates can be enriched on unchanged content while preserving version IDs, passage IDs and offsets; existing known dates are retained. Neither Atom update dates nor arbitrary dates in PDF bodies are substituted for publication dates. Old HTML reports remain unchanged historical snapshots.

Validation: **249 passed, 8 subtests passed, no skips**, including database pipeline tests. Added regressions cover rejected inferences reappearing with valid citations, negation preservation, concurrent fetch reuse, run isolation, alias boundaries, item-specific coverage, publication/update separation, ambiguous PDF headers, RSS-to-appendix propagation and unchanged-version date enrichment. Dependency and whitespace checks pass. Docker was stopped at the first full-suite attempt; the existing local stack was restarted before the successful database run. No shared Supabase changes were made.

### Live comparison and claim review

Run `759832da-1b0f-4bfb-99f5-16e6c3571417` used a fresh, empty local workspace with source settings checked equal to the baseline, the same OpenAI role models, the same period and the same budgets. Report: `reports/759832da-1b0f-4bfb-99f5-16e6c3571417/report-v1.html`. Configuration, implementation patch, usage and trace are in `reports/hk-quality/<run-id>/`; `reports/hk-quality/review.py` reproduces the read-only body/citation checks and writes `review.json`. All are ignored local artifacts. Saai's sample was re-read from `AML_CFT report_ HK (1).pdf`; its original evidence database, trace and model configuration remain unavailable.

| Observed result | Saai sample | OpenAI baseline | Updated OpenAI run |
|---|---:|---:|---:|
| Report status | Partial | Partial | Partial |
| Model-verified claims | 9 | 6 | 5 |
| Unresolved claims | 0 | 2 | 3 |
| Tokens | 111,872 | 179,908 | 117,805 |
| Minutes | 2.6 | 10.64 | 8.17 |
| Estimated standard-rate cost | Unknown | $0.8752 | $0.6314 |
| Fetched-document budget used | 15/15 | 15/15 | 15/15 |
| Reported coverage: found / missing / no change / out of budget | 1 / 10 / 1 / 0 | 2 / 8 / 0 / 2 | 2 / 5 / 3 / 2 |
| Distinct cited URLs | 3 | 3 | 1 |
| PEP circular appendix publication date | Unknown | Unknown | 2026-08-28 |

These are individual runs, not a controlled estimate of model performance. The updated run logged six fetch reuses without double charging. Eleven body sentences matched their cited saved claim content exactly; two proposed writer sentences were replaced/removed by the grounding gate. All internal citation targets resolve. The three rejected inferences are absent from the report body, and the impact section correctly says there are no verified items. All citations now point to three passages of the original HKMA circular PDF, rather than counting its landing and RSS representations as additional evidence.

Assistant review of the five factual claims against their full saved passages found support for the circular's 28 August date and version 2.0, the qualified expectation to **consider adopting** good practices, planned thematic examinations, reported control improvements and remaining gaps, and AI/genAI examples. The year in “later in 2026” is supported by the circular's publication metadata. This is an assistant technical/content review, not an independent human precision score or auditor sign-off.

**Coverage has not been proven to improve.** The body still rests on one underlying publication. In particular, the reported “HKMA Guideline on AML/CFT” match uses PEP Smart Tips material and needs reviewer confirmation; it must not be counted as demonstrated retrieval of the main AML guideline. The three “no change” classifications are model judgements from limited feeds/pages, not proof that no developments occurred. Missing categories and manually imported sources remain outstanding. The inference checker also rejected contextual references and suggested audit questions rather strictly; that is a separate quality issue from writer leakage and was preserved for an honest comparison. No ground-truth entries or human precision labels were changed.
