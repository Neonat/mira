# Hong Kong scheduled preparation validation — 11 November 2026

Audience: Mira maintainers and audit reviewers assessing live coverage and report presentation.

One scheduled Hong Kong AML/CFT job ran at `e414ded` in a fresh local workspace. The schedule queued exactly one job and was disabled before provider calls began. A report request submitted during preparation entered the waiting state and pinned that job for all three selected sources.

| Measure | Previous live run `489c2889` | Scheduled preparation `52f87456` |
|---|---:|---:|
| Benchmark publications acquired | 5/18 | 0/18 |
| Benchmark publications cited in a report | 1/18 | No report |
| Machine-supported facts | 2 | 0 |
| Elapsed time | 544.778 s end to end | 105.038 s preparation, then report failed |
| Known estimated provider cost | USD 0.834422 | USD 0.131996 |
| Uncertain usage reserve | USD 2.174972 | USD 0 |

Both comparisons use the prior report brief and unchanged 18-publication denominator. The scheduled job used a 25-minute, 30-document, 600,000-token and USD 10 cap. The previous run used a ten-minute end-to-end cap. The scheduler advanced the preparation as-of date to 11 November UTC. The report request and scoring used the previous 4 November as-of date. Scheduled preparation selected HKMA, SFC and Hong Kong e-Legislation, the approved sources that permit retained text and citations. The prior run also admitted sources with more limited grants.

All 16 scout attempts stopped at the first database lookup. The scheduled frontier bound the scout's tuple of source IDs as a PostgreSQL record, which the query rejected where it expected a UUID array. Three planner calls completed. No Exa search, browser acquisition or corroboration started, and no publication or passage was saved. The partial run published an empty snapshot. The waiting request then reported that no eligible machine-supported evidence was available. The shorter elapsed time reflects failure before acquisition and cannot establish a speed or coverage improvement.

The fix sends the source IDs as a database array. A local regression test uses a due schedule, PostgreSQL, the real scout and report workers, scripted model responses and fixture web responses. It reproduced the same database error before the fix and then fetched evidence and delivered a review-pending report to the waiting request. Live coverage after the fix is unmeasured. The single authorized live attempt was used.

A separate check of the synthetic report preserved all 20 findings and exact quotations and displayed the verified 15 December deadline in the timeline. The review table follows the evidence appendix, with a link from the contents. Chromium confirmed it fits at 320, 390 and 1,440 pixels with no horizontal page scrolling. These fixture checks establish presentation and evidence retention.

MAS stayed disabled. The job used keyword retrieval, with hybrid experimental. The local schedule and temporary HKMA browser permission were cleared after the validation. Known usage was 11,073 tokens and the USD allowance journal reconciled with no pending or uncertain charges. The USD value is a provider-price estimate.

[Portable results](2026-11-11-hk-scheduled-preparation-validation.json) · [Prior live run](2026-11-10-hk-quality-validation.md)
