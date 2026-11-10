# Bounded Australia/UAE validation - 10 November 2026

PR13 was pushed and checked for conflicts before this one new authorized test. The live pipeline ran uninterrupted and saved a **partial fallback report**, with PostgreSQL continuously available. **Clean acceptance remains unmet:** two analysis batches failed, the writer hit its output limit, and no UAE claim was verified.

Read the [portable measurements](2026-11-10-au-ae-uninterrupted-validation.json) and [sharing artifact hashes](2026-11-10-au-ae-uninterrupted-artifacts.json). The prior interrupted run and recovered draft remain unchanged in their [separate record](2026-11-10-generation-reliability-validation.md).

## Frozen scope and infrastructure

- Runtime/branch head: `86f2bfecd303b84a3fd7a57fa5e3c93c8f97cb5e`; runtime matches `0c1d500`. No runtime, model/effort or source-grant changes were made for this test.
- Run: `5fad1aa1-e8bc-41a9-9f3d-d5ed223a29c0`; report: `6ab90880-eb7c-468a-bb9d-3a2f65e85d85`.
- Brief: AML/CFT, AU and AE federal,10 November 2025 through 10 November 2026, as of 10 November 2026.
- Caps:8 research representations,600,000 known-plus-unknown-reserved tokens,25 minutes,4 Exa searches,10 embedding requests/100,000 input bytes, zero gap rounds.
- Analysis profile reused the previous four batches of at most three passages/6,000 characters,8,192 output tokens/120 seconds, with 60,000 tokens/360 seconds protected for follow-up. The production analysis output default is 16,384; this test does not validate that larger default.
- Only `au-register`, `austrac`, `cbuae` active in a fresh dedicated workspace. Malaysia/DIFC-DFSA and MAS disabled; MAS has zero versions. Hybrid experimental; CBUAE external embedding and browser escalation remain unenabled.

Push returned up to date. GitHub reported **MERGEABLE/CLEAN** and the local merge-tree check passed against PR13's base. Ewen/PR6 ancestry remains intact. A later post-run conflict check also reported CLEAN.

The detached local supervisor used a scoped macOS `caffeinate` process and PostgreSQL health checks every five seconds, with a 1,500-second hard deadline. Its **164 checks all succeeded**, with the same PostgreSQL postmaster throughout. Container ID/start time/mounts also match the early-run/end snapshots. Process exit 0; no hard deadline, reset, restore, database restart or paid continuation. PostgreSQL was left running. The supervisor ended after the run and did not start a recurring research task.

## Recorded outcome

Normal orchestration completed **partial in 821.877 seconds (13.70 minutes)**. All three scout tasks succeeded. Four analysis batches produced:

| Batch | Outcome | Recorded call |
|---|---|---|
| B1 | Failed - output limit | 118.652 s;8,192 output tokens |
| B2 | Succeeded | 98.459 s |
| B3 | Failed - invalid structured output | 106.728 s |
| B4 | Succeeded | 57.859 s |

Five draft claims persisted:3 AU facts and 2 AU inferences. All three facts passed quote and semantic checks; both inferences were rejected and omitted from the report body. There are **zero verified AE claims**. Source acquisition/relevance-checklist coverage is separate from accepted claim coverage; a checked UAE source does not establish a verified UAE finding.

Three corroboration model calls completed within the 90-second ceiling, including calls lasting 65.226 and 65.513 seconds. All three persisted assessments are **inconclusive**, with workload/origin-evidence/incomplete-assessment limits. No independent support was established. There were **zero generation timeouts**.

The writer was reached but hit its 8,192-output-token limit after 35.249 seconds. The existing deterministic fallback rendered the verified claims without a narrative summary and saved the report row and original HTML through the normal pipeline. This is a live-run fallback draft, **not an offline recovery reconstruction**. It is unreviewed and is not an audit opinion. No model call was retried after the run or replaced with another paid run.

## Retention and exact accounting

Eight saved representations comprise **3 complete native metadata captures and 5 readable HTML/PDF captures**, with 747,381 extracted characters and 1,197 citation passages. All saved extraction hashes and passage offsets match. Every **628,348 publication non-whitespace character** is covered. The native API records are retained in full and intentionally have no citation passages. This measures preservation after extraction, not original PDF/table/OCR or exhaustive fact accuracy.

Passage dispositions balance: **12 attempted = 6 analysed + 6 failed**, plus **1,185 deferred**, zero pending. Failures and deferrals do not delete source text. AU experimental vectors:42 Federal Register + 19 AUSTRAC = 61; UAE vectors:0. Partial indexing and changed ranks do not establish retrieval usefulness.

Actual calls: **21 model,3 Exa and 6 embedding**. Embedding input 40,008 UTF-8 bytes. Known usage is **166,470 model + 8,654 embedding = 175,124 tokens**; unknown reservations and pending usage are both zero. Persisted model steps, embedding diagnostics, the shared ledger and the generated report's 175,124/600,000 counter agree exactly. The previous interrupted run's missing step-usage problem did not recur.

## Comparison with the previous run

Both runs used the same overall caps and three source profiles, but planner decisions and acquired corpora differ.

| Measurement | Prior `f17f39d0` | Current `5fad1aa1` |
|---|---|---|
| Database | Shutdown before writer | Continuous;164 checks, zero failures |
| Report | Separate offline recovery export | Normal persisted fallback report |
| Saved representations | 2 metadata + 6 readable | 3 metadata + 5 readable |
| Passages | 1,198 | 1,197 |
| Analysed / failed / deferred | 12 /0 /1,186 | 6 /6 /1,185 |
| Supported facts | 3 AU + 1 AE | 3 AU + 0 AE |
| Generation timeout calls | 1 corroboration | 0 |
| Other generation errors | 2 output limits | 2 output limits + 1 invalid output |
| Corroboration | 2 primary-source-only,1 inconclusive | 3 inconclusive |

The current run acquired an extra scoped Register Documents record for `C2026C00274` and did not acquire the previous CBUAE press-release HTML page. Under the fixed eight-representation cap, metadata/discovery fan-out consumes acquisition capacity. The prior press page supported the earlier UAE fact. This explains a concrete corpus difference; it is not a controlled claim about retrieval ranking, national publication recall or a best-method winner.

## Verification and peer files

The preflight passed **23 focused checks in 0.21 seconds**. The previous code-identical integrated suite remains **1,075 tests + 8 subtests, no skips,70.34 seconds**, including PostgreSQL and actual offline Chromium. It was not rerun without a code change. An independent retained-artifact audit found no factual blockers in metrics, accounting, country restrictions or comparison; the coordinator separately observed the push/conflict and focused-check tool outputs.

The sharing package contains the 8-page partial research draft and 6-page validation report, each PDF and standalone HTML, plus metadata, README and checksums. Original live HTML bytes are preserved. The PDF uses an abbreviated `Ref.` column heading for print readability; findings, citations and outcomes are unchanged. All pages were rendered and inspected, including detailed timeline/coverage tables. No credentials, `.env`, dumps, publisher originals/full-body exports, vectors or private logs are included. CBUAE quotations remain for private organisational peer review with attribution.

Remaining issues are explicit: the test analysis cap and writer output cap were restrictive; B3 also failed structured-output validation; no verified UAE claim or independent corroboration was established. Larger production analysis defaults were not tested by this profile. Further clean validation needs a new bounded authorization. No merge, remote deployment, model change or historical rewrite occurred.
