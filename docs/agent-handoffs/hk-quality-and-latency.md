# Hong Kong grounding, coverage and latency

Audience: maintainers and operators preparing an audit-analyst demonstration.
Base: `cece393` and saved observation `ea485995`; PR13 remains unmerged.

The saved run missed available native publications, analysed only 24/296 passages,
accepted an index update as the date of a 2023 amendment, and accepted an unsupported
technology characterization. Its 23.5-minute runtime failed demo acceptance.

Changes:

- Prefer topical, dated native publication records under existing acquisition
  limits. Search snippets cannot establish publication dates.
- Retain new capture grounding provenance through Python and SQL evidence inputs.
  Container dates cannot date listed events. Conservative category-title guards
  also protect new analysis of legacy index captures without rewriting them.
- Validate inference premise ownership, exact quotes, qualifications and factual
  vocabulary against retained dependency passages in the existing check call.
  Conservative abstention can reject legitimate paraphrases; it is not a semantic
  accuracy guarantee. Include the shared untrusted-source instruction.
- Initial validation expanded batches to eight passages/12,000 characters; this
  failed live. Current defaults restore three passages/4,500 characters, still
  eight batches,16,384 output tokens and180 seconds per batch. Require a120-second
  useful window, clamped to an explicitly shorter timeout, and reserve180 seconds
  for verification/writer. Prioritize substantive
  topical text, preserve source/document fairness and record every deferral.
- Use four lanes for independent analysis/checks. Ordinary database persistence
  stays on the coordinator thread in deterministic order. Saved corroboration
  has separate preparation, provider evaluation and persistence; permitted fresh
  acquisition stays serial. Dispatched calls drain before cancellation/cleanup.
- Keep the shared dollar/token/deadline admission and conservative unknown usage.
  A ten-minute run protects one minute for the writer. Explicit manual import
  publication dates retain their basis, separately from import time.

The first integrated suite exposed outdated scripted inference fixtures and a
manual-import date-basis regression. Fixtures now exercise real premise labels,
quotes and source context; security/sign-off assertions were preserved. Seventy
affected database/integration checks and 51 grounding/import checks passed.
Independent focused reviews cleared their reproduced blockers. The final integrated suite passed **1,353 tests +8 subtests, zero skips,75.32seconds**, including local PostgreSQL and actual Chromium. [Portable checks](../../eval/evidence/2026-11-10-hk-quality-checks.json). The one subsequent live observation failed demo acceptance; see below.

No role models/effort, source reuse grants or historical report bytes changed.
MAS/Malaysia/DFSA remain disabled; hybrid remains experimental. No remote migration
or deployment. One additional user-authorized validation only: USD10, ten minutes,
30 documents,600,000 tokens,six Exa searches,eight analysis batches; previous HK
brief and 18-item denominator, keyword retrieval with Exa/permitted browser enabled.
No paid preflight or automatic replacement run. Local PostgreSQL remains running.


## Observed result and unfunded correction

Run `489c2889` at `03db382` ended partial after544.778seconds (9.1minutes).
Acquisition stayed5/18; report citations fell4/18→1/18 and facts10→2. Seven analysis
calls timed out, including four admitted with only~33seconds; one primary check
also timed out. Corroboration had zero timeouts but all three assessments were
inconclusive. Six Exa calls completed; enabled browser had zero attempts. The
writer succeeded. Both included facts/dates have retained source support, but a
relevant supervisory point was stored and omitted. This is not a demo acceptance.

Known estimate$0.834422 plus unknown reserve$2.174972 used$3.009394 of$10; no pending
charges remain. MAS stayed disabled and the database stayed available. The report
is preserved, with a private validation cover. [Measured evidence](../../eval/evidence/2026-11-10-hk-quality-validation.md).

After that observation, restored smaller batches, added useful-window admission
and larger downstream reserve, and required subject relevance for deterministic
native selection. The failed run had selected unrelated enforcement headlines on
generic publisher/document-kind words. No claim that specific missing benchmark
items will be recovered. No paid restart/replacement/continuation occurred.

Final post-run integrated checks: **1,360 tests +8 subtests, zero skips,78.00seconds**;
focused review found no blockers. These latest corrections remain live-unvalidated.
Five-minute fresh report generation and adequate country/report coverage remain
unproven; do not use this result as a clean competition demonstration.
