# Hong Kong quality validation — 10 November 2026

Audience: maintainers and audit analysts assessing the prototype. **Demo acceptance failed.**

One authorized real BYOK run `489c2889-40f0-4ba9-b87c-5e592bbbabfa` at `03db382` ended partial in **544.778 seconds (9.1 minutes)**. It used the unchanged AML/CFT/HK brief, 4 November 2025–4 November 2026, as-of 4 November 2026. Caps: USD10,30 documents,600,000 tokens,six Exa searches,eight analysis batches,ten minutes. Previous completed runs had a25-minute cap, so elapsed time is not a controlled speed gain.

| Measurement | Earlier `7be59cdf` | Immediate prior `ea485995` | This `489c2889` |
|---|---:|---:|---:|
| Acquired benchmark publications |6/18|5/18|5/18|
| Report-cited benchmark publications |5/18|4/18|1/18|
| Model-supported facts |19|10|2|
| Model-supported inferences |0|1|0|
| Elapsed minutes |Earlier profile|23.5|9.1|
| Writer |Fallback|Successful|Successful|

The 18-item denominator is unchanged, including disabled-source items. Acquired GT22 replaced GT20 relative to the immediate prior run; the other matches were GT04/05/06/21. The report cites only GT21. These are publication matches, not a country-completeness estimate. Source representations total30;24 have passages. Of538 saved passages,8 were analysed,56 failed and474 were deferred. Seven analysis calls timed out: three at180seconds and four after admission with only about33seconds left. The one completed eight-passage batch took156.483seconds and produced11,648 output tokens. One primary verification request also timed out. Three corroboration assessments were inconclusive; none timed out and no independent support was established.

**Cost accounting:** $0.834422 known public-price estimate +$2.174972 unknown-usage reserve =**$3.009394** allowance used, pending0. This is not an invoice.180,340 known +255,588 unknown-reserved tokens =435,928 of600,000. Six Exa searches completed. Permitted HKMA browser fallback was enabled but never triggered: zero live browser attempts, so this run establishes no browser coverage contribution. Keyword retrieval selected; hybrid remains experimental. MAS stayed inactive with zero versions/fetches/browser attempts. Malaysia/DFSA remained outside the selected/approved scope. Temporary keys and browser approval were cleared; no general worker was enabled. Database checks observed no outage/restart and the database was left running.

**Content QA:** both included facts match substantive Smart Tips v2.0 source text, and their28August2026 date matches the publication body. The source explicitly defines artificial intelligence/generative artificial intelligence; no unsupported acronym interpretation or inference was found in these two findings. This is qualitative scoped review, not a precision benchmark. The source also states an expectation to consider the practices and forthcoming thematic examinations; that important supervisory point was retained but omitted from findings. The report is incomplete and unsuitable as a clean demo output.

**Unfunded correction after this observation:** restore3-passages/4,500-character batches while preserving substantive priority and four-lane execution; refuse new batches lacking a120-second useful window (clamped to an explicitly shorter operator timeout); protect180seconds for verification/writer; require subject-bearing relevance before automatically acquiring native publications. The previous native rule selected unrelated enforcement headlines on publisher/document-kind words. These corrections are tested offline, not live validated. No rerun/resume/replacement was made. Role models/effort, source restrictions and historical report bytes remain unchanged. The original generated HTML and PDF with a validation cover are supplied privately, not committed.
