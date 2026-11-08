# One bounded Hong Kong validation — a88dd20e

**Outcome: failed at analysis; no report and no corroboration assessments.** This is a failed test result, not a successful validation of all three features or a coverage improvement.

User authorized exactly one research run, using the connected Exa plugin after the app's `EXA_API_KEY` was found absent. No replacement run or model-only diagnostic was made. Source checkpoint `ef58c47e8f94ae126181a03f7220a5a709fc7b7f`; [PR7](https://github.com/Neonat/mira/pull/7). Runtime source and Ewen's PR6 changes remain untouched.

## Configuration and execution

- Run: `a88dd20e-2fe8-41c2-8839-0b6ef85569a3`; 8 November 2026, 07:11:21–07:19:45 UTC (8.41 minutes).
- Fresh, isolated local workspace; no inherited documents, manual benchmark imports, or benchmark information supplied to runtime. Benchmark scoring ran only after the outcome was saved.
- AML/CFT, HK only, 4 November 2025–4 November 2026; as of 4 November 2026. This deliberately matches the earlier local run, rather than moving the date window.
- Limits: 30 documents, 600,000 tokens, 25 minutes, two gap rounds; at most six Exa discovery requests with ten results each. Corroboration uses the same budget. Model names/effort unchanged: configured GPT-5.4 planner/analyst/verifier, GPT-5.4-mini scouts/writer. Actual successful responses recorded dated snapshots.
- Validation-only provider wrapper: each request isolated, no SDK retries, at most 180 seconds and 16,000 output tokens, with a conservative UTF-8 prompt/schema envelope reservation plus 8,192 framing allowance. Known usage refunds unused reservation; unavailable usage retains its reservation. These extra request caps differ from ordinary runtime defaults and prevent a controlled feature-effect comparison.
- Exa used a URL-only filesystem relay into the actual `ExaDiscovery` interface. The plugin lacks the app transport's hard domain/date arguments: query/objective restrictions plus local domain filtering and the production adapter's source/date/operation checks were used. Search highlights were discarded and never treated as evidence. **The normal Exa HTTP API-key/authentication path was not tested.**
- Six relay requests: three actual connected Exa calls (ten requested results each), one response accepted within ten seconds, five request timeouts. The accepted response supplied ten e-Legislation URLs. Two dispatched responses arrived too late; three requests expired without dispatch. Accepted links still face normal acquisition/robots permissions. Late responses were not injected afterward. Initial manual dispatch and sequential processing of concurrent requests made this relay unreliable; it is not production-transport latency evidence.
- Live browser enabled; only HKMA had a temporary permission reference to its terms for the attributed non-commercial prototype. HTTP-block fallback remained false. Browser acquisition runs only for eligible fallback conditions; **zero browser attempts/captures occurred**. All 30 saved versions came from HTTP and extracted completely. The temporary browser grant was removed after the run.
- MAS and all SG sources inactive in this workspace: zero MAS fetches and zero MAS saved versions. No global environment, source seed, model settings, historical reports or remote migrations changed.

## Coverage comparison

Each acquired benchmark publication counts once by official canonical URL, using `eval/score_recall.py` and the same period/jurisdiction filters. Acquisition coverage counts saved versions, while report coverage counts publications behind report citations. Latest checklist rows use the final gap round per expected source; intermediate rounds are not summed.

| Measure | Earlier local e2fda30f | New a88dd20e |
|---|---:|---:|
| Saved versions | 32 (old allowance overshoot) | 30 |
| Acquired benchmark publications | 9/18 (50.0%) | 7/18 (38.9%) |
| Acquired regulatory publications | 9/14 | 7/14 |
| Report citation coverage | 9/18 | N/A — no report |
| Final checklist: found / no change / missing / fetch failed | 4 / 3 / 6 / 0 | 4 / 2 / 6 / 1 |
| Corroboration assessments | unavailable in old implementation | 0 — not reached |

Acquisition coverage was **two publications lower (−11.1 percentage points)**. The seven retained publications were GT04, GT05, GT06, GT11, GT16, GT21 and GT22; no newly acquired benchmark publication. The prior run additionally acquired GT03 (SFC layering circular) and GT24 (HKMA anti-bribery/account-opening controls). This observation does not establish why they were not reacquired or isolate a feature effect.

The earlier local workspace contains exactly one run and 32 versions, matching its retained audit, so its acquired coverage can be recomputed without mixing later runs. Its failed-scout accounting was incomplete; the requested document allowance was exceeded. Same configured models, brief and nominal limits do not remove those differences, the new harness caps, live-site changes, stochastic selection or this run's failures.

The latest team run `29a153bb` cited **11/18 overall and 11/14 regulatory**. It used different actual models (Haiku), a 7 November date window, 40 documents/650,000 tokens/15 minutes and an earlier source checkpoint. Its local DB is unavailable here; the [tracked historical evidence](2026-11-07-hk-run-29a153bb.md) is the reference. Comparing its report citations directly to this run's acquisition score would mix measures. No new report citation or precision comparison is available.

## Failure and usage

One scout call failed without usage. The analyst later failed after approximately 170.3 seconds with the sanitized error `bounded request failed`. The run stored `analyst failed: bounded request failed`, created no findings/report, and therefore never entered verification or corroboration. The sanitized failure does not reveal the provider/network/output cause; it is **not proof that the 180-second deadline or output cap was hit**.

Recorded successful model usage: **254,700 tokens**; two unavailable-usage calls retain **187,416 reserved tokens**, giving 442,116 known-plus-reserved against 600,000. Reservations are not measured consumption. Repository-rate estimate **$0.6603 covers reported model usage only**, excludes both failed calls and Exa, and is not the total bill. Earlier local recorded usage was 372,220 tokens, also with incomplete failed-scout usage, so no cost/efficiency gain is claimed.

Checks: offline recall scorer **14 passed**; one live research run finished and was scored without rerunning. Accounting assertions verified 30 saved/charged acquisitions, 30 complete extractions, final 13 checklist entries, unchanged nominal brief/models/limits, no MAS activity, removed browser grant, and zero report/corroboration output. No new human precision labels or review sign-off were created.

## Artifacts and next step

[Portable metadata](2026-11-08-hk-bounded-run-a88dd20e.json) is tracked without publisher full text or credentials. Ignored local `reports/a88dd20e-2fe8-41c2-8839-0b6ef85569a3/` contains manifest, sanitized call events, acquisition/step metadata, comparison, scripts and an empty unlabelled worksheet. It contains no report HTML because report generation was not reached.

Next engineering step: improve sanitized bounded-provider failure diagnostics and use an asynchronous connector relay or configured Exa HTTP transport before another live measurement. Browser fallback needs an eligible permitted trigger to be exercised; all-three end-to-end behavior and coverage improvement remain unvalidated. Any further paid research run requires new authorization. Existing slides retain their historical evidence cut. PR7 remains open, not merged or deployed.
