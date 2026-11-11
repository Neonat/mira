# Hong Kong scheduled preparation rerun — 11 November 2026

The single authorized live job ran on `a42e92d` with the source-array fix. It saved 29 document versions and 459 passages. The report request waited for the scheduled job. During verification, PostgreSQL rejected a corroboration timestamp as being in the future. The job ended with a failed evidence refresh after 14 minutes 7 seconds, before publishing a prepared snapshot or report.

| Live attempt | Benchmark publications acquired | Benchmark publications cited |
|---|---:|---:|
| Earlier end-to-end run `489c2889` | 5/18 | 1/18 |
| Scheduled run before source-array fix `52f87456` | 0/18 | No report |
| Scheduled rerun `4aadb257` | 6/18 | No report |

The rerun found the earlier five benchmark publications plus GT03. All six have stored passages. Nine scouts succeeded and two hit their model output limits. The source-array error did not recur. Exa completed six searches and browser fallback was unused. Analysis covered 12 of 459 candidate passages. Twelve failed after two provider interruptions and two timeouts, and 435 were deferred. The database retained 20 candidate findings, supported fact checks for four, and one primary-source-only corroboration record. These records are separate from a prepared report.

The test used the same scheduled scope and limits as the failed scheduled attempt. It selected HKMA, SFC and Hong Kong e-Legislation and used keyword retrieval, with hybrid experimental. Limits were USD 10, 25 minutes, 30 documents, 600,000 tokens and six Exa searches. Report scoring uses the prior report brief and the same 18-item benchmark. The earlier end-to-end run had a broader source scope and a ten-minute time limit, so the difference does not isolate the effect of scheduling.

Estimated known charges were USD 1.747144, plus USD 1.100453 reserved for calls with uncertain usage. Total allowance accounted for was USD 2.847597 of USD 10, with no pending reservations. MAS stayed disabled. The schedule is off and the temporary HKMA browser permission was removed.

The database error was reproduced locally with a worker clock ahead of PostgreSQL. The correction caps the saved timestamp at database time and returns the exact stored record for subsequent verification. The original failure and evidence remain recorded. Live report generation with this correction is unmeasured.

[Portable results](2026-11-11-hk-scheduled-preparation-rerun.json) · [Earlier scheduled attempt](2026-11-11-hk-scheduled-preparation-validation.md) · [Earlier end-to-end run](2026-11-10-hk-quality-validation.md)
