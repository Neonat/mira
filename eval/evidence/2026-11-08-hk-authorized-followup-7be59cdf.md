# Authorized Hong Kong follow-up: partial improvement, acceptance incomplete

The explicitly authorized additional run completed once, without continuation, at the 25-minute cap. **Acquisition rose from 5/18 to 6/18; report citation coverage remained 5/18. Corroboration had zero timeouts, eight completed model requests and four output-limit failures.** The writer exhausted the remaining global time, so the existing fallback produced a partial report. This does not establish that the coverage drop or end-to-end reliability is fixed.

## Execution and limits

Run `7be59cdf-8dc7-4c5f-ae22-1c3db4c10b82` used source `c1cf68297ced2a8ca08ceb7dfdcf6309ce5580cf`, including runtime fixes `78c6771`. It ran on 8 November 2026, 08:53:02–09:18:02 UTC (16:53:02–17:18:02 SGT), with 1,500.071 seconds including local finalization. Exactly one fresh workspace/run and one initial analysis; subsequent verifier-requested claim rewrites were normal processing. No restart, repair continuation or replacement run occurred, and runtime code stayed fixed throughout.

The brief remained AML/CFT, Hong Kong only, 4 November 2025–4 November 2026, as of 4 November 2026. Limits were **30 documents, 600,000 tokens, 25 minutes, two gap rounds and at most six Exa searches**. Actual Exa HTTP API-key transport completed **5/5 requested searches**; no plugin relay. Search metadata was subject to normal source/date/permission filtering and was not used as report evidence without acquisition. Existing role models and high reasoning effort were unchanged. Validation calls retained the 360-second/64,000-output-token ceiling, capped by remaining run allowance; corroboration had its narrower limits below.

All 30 saved versions were complete HTTP acquisitions. Live browser acquisition was enabled with a temporary HKMA-only grant, but **zero browser attempts/captures** occurred. HTTP-block fallback was not granted. MAS stayed inactive, with **zero fetches and zero versions**. Temporary browser grants were removed after completion. This run does not exercise the live browser path; the separate earlier [HKMA acquisition evidence](../../docs/agent-handoffs/hkma-live-browser-validation.json) remains its live test.

The partial report contains **19 facts, zero included inferences and three unresolved claims**, citing eight distinct publications. Every included finding had a latest persisted supported primary-verification verdict. The model writer started with only 16.35 seconds left, then timed out at the global deadline; the existing deterministic fallback lists the verified findings without a generated summary. There were 77 successful orchestration steps and one failed writer step. Review status remains draft; no human precision labels or sign-off were added.

## Coverage comparison

Acquisition counts canonical benchmark publications among saved versions; citation coverage counts publications supporting report findings, including factual dependencies. Existing independent M0 scoring ran only after terminal outcome, without injecting benchmark material into runtime.

| Measure | Earlier local e2fda30f | Previous clean 7e877c4e | Authorized follow-up 7be59cdf |
|---|---:|---:|---:|
| Saved versions | 32 (old overshoot) | 30 | 30 |
| Acquired benchmark publications | 9/18 | 5/18 | **6/18** |
| Report citation coverage | 9/18 | 5/18 | **5/18** |
| Regulatory acquisition / citation | 9/14 / 9/14 | 5/14 / 5/14 | **6/14 / 5/14** |
| Corroboration calls completed / requested | Not implemented | 0/6 | **8/12** |
| Corroboration timeouts / output limits | Not implemented | 6 / unknown | **0 / 4** |
| Model writer completed | Yes | Yes | **No; fallback report** |

Current acquisitions are GT04, GT06, GT08, GT21, GT22 and GT23. Versus the previous clean run, GT08 and GT22 were gained and GT03 was not reacquired: net **+1 publication**, or 5.6 percentage points. GT23 was acquired but not cited; current cited IDs are GT04, GT06, GT08, GT21 and GT22. Citation recall therefore did not improve. Final checklist: five found, three no-change, four missing and one fetch-failed.

Acquisition remains three publications below the earlier local 9/18; citation recall remains four below it. The earlier run exceeded its requested document allowance and has incomplete failed-call accounting. The team-recorded 11/18 citation result used different actual models, dates and budgets. These are historical comparisons, not controlled causal or efficiency estimates, and human precision remains unlabelled.

## Corroboration outcome

The revised `corroboration/3-single-candidate` request uses one retrieved candidate, at most two primary passages, exact contiguous 1,800-character windows, a compact single-decision schema and **4,096 output tokens**. The **60-second service cap** includes preparation/discovery and shrinks to remaining run time. One assessor attempt is allowed per assessment/claim revision, with no retry or deadline reset; normal primary-verifier rewrites can create further assessments. Full original passages remain frozen, and limited-context support or apparent conflicts stay uncertain.

All twelve actual requests had approximately 60-second deadlines and 5,436–7,662 input characters. **Eight completed in 22.96–38.78 seconds (median 30.84)**. Four ended with the provider's `output_limit` category after 44.71–49.05 seconds, each with known usage. There were **zero corroboration timeouts**. This is live evidence of provider schema acceptance and some completed requests under the new cap, not proof that every request or the full pipeline is reliable. No throttling cause is inferred.

Twelve assessments persisted: **five primary-source-only and seven inconclusive**. Four inconclusive assessments record output-limit errors; the remaining results also do not establish independent support. No independent corroboration success or validated conflict is claimed. The ledger's 27 successful orchestration steps include eligibility and not-checked paths and must not be treated as 27 successful model checks. Per-request timing/error metadata is in the [portable comparison](2026-11-08-hk-authorized-followup-7be59cdf.json).

## Accounting and verification

Reported provider usage totals **478,544 tokens**. The writer's unknown usage retains a **90,685-token reservation**, totaling **569,229 reported-plus-reserved** within 600,000. A reservation is not measured consumption. The repository-rate model estimate is **$2.2638**, excluding Exa and unreported usage; it is not the total bill. Corroboration reservations and journal reservations are overlapping provenance views, not additional disjoint costs.

The unchanged runtime had already passed **538 tests + 8 subtests, none skipped, in 52.38 seconds**, including PostgreSQL, actual Chromium fixtures, legacy frozen evidence and PR6 quote/seeding/budget regressions. That full suite was not repeated for this evidence-only update. Post-run read-only assertions passed for the single run and initial analysis, no continuation, document/token/time/search caps, unchanged configured models, persisted supported report findings, report artifact, MAS inactivity and grant cleanup. `eval/clean_hk_compare.py` scored the completed workspace; local `verify.py` checked accounting and evidence bindings.

Local ignored `reports/7be59cdf-8dc7-4c5f-ae22-1c3db4c10b82/` retains `report-v1.html`, the sanitized event journal, manifest, outcome, checks and reproduction scripts. Portable metadata contains no publisher full text or credentials. No runtime changes, historical report rewrites, remote migration, merge or deployment accompanied this run. Ewen's PR6 remains intact.

The user authorized exactly one additional bounded run, now used. **Execution and accounting are complete; full coverage/corroboration/report acceptance is incomplete.** Further work should investigate missed selections/citation exclusions, corroboration output exhaustion and verifier/rewrite time before proposing another separately authorized live validation.
