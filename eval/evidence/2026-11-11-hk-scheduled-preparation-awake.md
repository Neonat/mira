# Hong Kong scheduled preparation with idle sleep prevented

The live run `8dcdcc8b` on `9b201b8` published a prepared evidence snapshot and delivered a **human-review-pending draft with 14 facts** to the waiting report request. Preparation took 19 minutes 7 seconds. Report assembly took 0.196 seconds after the evidence was ready. macOS held an idle sleep assertion for the worker and released it when the worker exited.

| Live attempt | Benchmark publications acquired | Benchmark publications cited |
|---|---:|---:|
| Earlier end-to-end run `489c2889` | 5/18 | 1/18 |
| Scheduled run before timestamp fix `4aadb257` | 6/18 | No report |
| Scheduled run interrupted by sleep `2dbaed02` | 4/18 | No report |
| Scheduled run with sleep assertion `8dcdcc8b` | 5/18 | 5/18 |

The draft cited all five acquired benchmark publications (GT03, GT04, GT05, GT06 and GT21) and four additional publications. The acquisition set gained GT03 from the interrupted run and lacked GT22 from the six-publication attempt. The scheduled tests used the same 18-item benchmark, source scope and limits. The earlier end-to-end run used broader source scope and a shorter time limit.

The job saved 30 document versions, representing 29 distinct publications, and 382 passages. It analysed 21 passages, with three failed and 358 deferred. The snapshot carries 14 supported facts from 24 candidate findings. PostgreSQL accepted all 11 saved corroboration records with timestamps at or before insertion. The latest assessments cover ten findings, all inconclusive.

The report audit matched all 14 findings to their saved verification records. Forty-three of 44 quotes matched after whitespace normalisation. One PDF passage had a space after a line-break hyphen and passed the verifier's extraction-noise rule. The HTML checksum matched the stored artifact. Chromium checks at 390px and 1440px found no broken internal links or horizontal overflow and confirmed 14 review rows.

The ledger accounted for USD 3.408808 of the USD 10 cap, comprising USD 2.983450 in estimated known charges and USD 0.425358 reserved for uncertain usage. All six Exa searches completed. The run used keyword retrieval and made no browser fallback attempts. MAS stayed disabled, hybrid remains experimental, and the one-time schedule is off. The temporary HKMA browser permission was removed.

[Portable results](2026-11-11-hk-scheduled-preparation-awake.json) · [Prior scheduled result](2026-11-11-hk-scheduled-preparation-timestamp.md)
