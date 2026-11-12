# Australia and UAE federal prepared-report check

11 November 2026, Singapore time. Audience is Mira engineers and demo operators.

The local archive and the hosted Hong Kong demo workspace had no ready snapshot
for either market before this check. Australia could reuse evidence from the
completed partial run `5fad1aa1-e8bc-41a9-9f3d-d5ed223a29c0`. The rehearsal froze
its existing Australian findings and verification records under the AUSTRAC and
Federal Register of Legislation source scope. It used the normal prepared report
worker and guest page on the local machine. The hosted Hong Kong rehearsal used
the same guest flow through its HTTPS tunnel and hosted database.

| Measurement | Hong Kong, hosted | Australia, local | UAE federal |
|---|---:|---:|---|
| Generate click to open draft in iPhone 13 browser emulation | 12.141 s | 5.442 s | No ready snapshot |
| Findings in the draft | 14 | 2 | No draft |
| Citation quotes matching saved passages | 44 | 8 | No draft |
| Document versions cited by the findings | 9 | 2 | No draft |
| Retained document versions / passages | 30 / 382 | 6 / 1,163 | 2 / 34 in the latest partial run |
| Source checklist | 3 found, 3 no change, 2 missing, 1 fetch failed | 2 found | No prepared checklist |

The Australian draft includes two of the three historically supported findings.
The remaining finding's saved corroboration failed the selected source/date
scope check. Four of 1,163 Australian candidate passages were analysed, four
failed and 1,155 were deferred. The two source checklist entries indicate relevant
material was found in both configured categories. The timing and checklist counts
cannot establish comparative national coverage or retrieval performance.

The earlier interrupted UAE federal run `f17f39d0-9fd1-4059-8c3f-e44088269b51` has
one supported finding with two matching quotes and an intact saved verification
input. Its run status remains failed. Snapshot preparation accepts completed
draft or partial runs, so that finding was unavailable for a guest request.
The [earlier UAE recovery report](2026-11-10-generation-reliability-validation.md)
documents the archived evidence.

The first Australian browser rehearsal revealed a UAE checklist row and
mixed-run passage totals in the Australian report. The corrected rehearsal
reused the same immutable snapshot. Report assembly filtered the checklist and
recalculated passage totals for the admitted sources. It preserved the review
warning, passed the quote and internal-link checks, and downloaded HTML whose
hash matched the saved report. The corrected report is
`080a638b-1d66-45ea-a3ab-49eec30c4d56`, pinned to snapshot
`a887772e-9242-41c9-95d2-d3072b2563a2`.

The temporary local guest window was closed. Generation added no research run
or preparation job and used zero paid provider calls. MAS, Malaysia and DFSA
stayed disabled. Hybrid retrieval remains experimental and was outside this
prepared-report timing check.
