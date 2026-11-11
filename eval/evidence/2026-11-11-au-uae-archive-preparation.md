# Australia and UAE federal archive preparation

11 November 2026, Singapore time. Audience is Mira engineering and demo operators.

One authorised preparation run `fc29ce86-0c8a-411d-92ca-6ccc365a3995` used the
saved workspace archive, the existing model profile and a USD 10 cap. It used
keyword retrieval over AUSTRAC, the Australian Federal Register of Legislation
and CBUAE federal material. It made zero publisher fetches, Exa searches,
browser acquisition calls or embedding requests. Eight retained document versions
stayed in place. The original interrupted run remained failed.

The preparation published snapshot `edcd5bed-8284-47ea-9fad-8f23d830d34a` after
841.121 seconds. The ledger recorded 46 completed calls, one timed-out analyst
call, USD 1.971297 in estimated usage and USD 0.273168 reserved for the timed-out
call with unknown usage. Pending reservations were zero. The source coverage
ledger records 45 of 1,198 passages analysed, three failed and 1,150 deferred.

## Private phone-browser rehearsal

The two iPhone 13 emulation runs timed **Generate report** to the visible report
heading using the normal guest page and report worker with local Supabase.
Both requests pinned the same snapshot, with separate markets and source scopes.

| Measurement | Australia, prior local | Australia, new local | UAE federal, new local |
|---|---:|---:|---:|
| Time from click to open | 5.442 s | 5.520 s | 5.425 s |
| Analysed / candidate passages | 4 / 1,163 | 30 / 1,163 | 15 / 35 |
| Failed / deferred passages | 4 / 1,155 | 2 / 1,131 | 1 / 19 |
| Findings included | 2 | 16 | 1 |
| Citation quotes verified against saved passages | 8 | 32 | 2 |
| Cited document versions | 2 | 1 | 1 |

Australia's improvement is depth of analysis. Its new findings cite one
legislative compilation, so citation breadth decreased. The new Australian
checklist contains one found and one no-change entry. The UAE federal checklist
contains one found entry. The UAE finding records a CBUAE guidance update with
a link to the guidance. The report has limited evidence on the substance of
the update. Neither country has a publication-recall benchmark from this run.

Both drafts retain the human-review-pending warning. The rehearsals checked
quote matches, internal citation navigation, mobile overflow, report download
hashes and guest-link revocation. Report generation made zero provider calls.
Both guest windows were closed. The UAE report remained in the private local
workspace with the CBUAE organisational-use notice. MAS, Malaysia and DFSA
remained disabled. Hybrid retrieval remains experimental.

Regression suite passed 1,449 tests and 8 subtests with local PostgreSQL and
Chromium.
