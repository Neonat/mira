# Hong Kong scheduled preparation after the timestamp fix

One live job ran on `aecd624` with the database timestamp correction. Run `2dbaed02` saved 28 document versions and 264 passages. The local workstation entered idle sleep during analysis from 04:49:18 to 05:39:40 UTC. The worker lease expired during that interval. The job ended before verification or corroboration, so the timestamp correction was not exercised. No snapshot or report was published.

| Live attempt | Benchmark publications acquired | Benchmark publications cited |
|---|---:|---:|
| Earlier end-to-end run `489c2889` | 5/18 | 1/18 |
| First scheduled attempt `52f87456` | 0/18 | No report |
| Scheduled rerun before timestamp correction `4aadb257` | 6/18 | No report |
| Scheduled run after timestamp correction `2dbaed02` | 4/18 | No report |

The final run acquired GT04, GT05, GT06 and GT21, all with stored passages. The previous scheduled run also acquired GT03 and GT22. Each scheduled run used the same approved HKMA, SFC and Hong Kong e-Legislation source scope and the same 18-item benchmark. The earlier end-to-end run had broader source scope and a shorter time limit.

The job completed five Exa searches and made no browser fallback attempts. Two scout calls hit output limits. Four analysis calls were in flight during the interruption and timed out. No findings passed through analysis to verification. The worker recorded 7 minutes 55 seconds of monotonic runtime. The start and end timestamps were 58 minutes 15 seconds apart, including 50 minutes 22 seconds of host sleep.

Known estimated charges were USD 0.384929, plus USD 1.099829 reserved for uncertain usage. Total allowance accounted for was USD 1.484758 of USD 10, with zero pending reservations. MAS stayed disabled and the run used keyword retrieval. Hybrid remains experimental. The one-time schedule is off and the temporary HKMA browser permission was removed.

The expired job was closed through the store's lease and failure transitions. The waiting report request now shows a failed evidence refresh. The acquired evidence and usage records remain saved.

[Portable results](2026-11-11-hk-scheduled-preparation-timestamp.json) · [Prior scheduled comparison](2026-11-11-hk-scheduled-preparation-rerun.md)
