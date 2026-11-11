# Hong Kong validation interrupted before verification

The user authorized one bounded run after PR13: “what is a worker only credential? you can run it”. Run `1637f9f8-a3f3-49e0-af06-2d15f6d198f6` used runtime `240aef8` at source checkpoint `3c0842f`, the existing OpenAI role models and actual Exa API key. The scope remained HK AML/CFT, 2025-11-04 through 2026-11-04, as of 2026-11-04; caps remained 30 document attempts, 600,000 tokens, 25 minutes and six Exa searches. No benchmark inputs entered the runner. [Portable metadata](2026-11-08-hk-interrupted-1637f9f8.json) retains the measurements and evidence hashes.

The execution disappeared during a chat interruption; the Docker daemon was also stopped when checked. No normal completion event or report exists. The coordinator restarted only the existing local database, confirmed the run/provider child processes were absent, and closed the stranded run/step as failed without resuming it or making more API calls. The interruption's exact process-stop/provider-completion time is unavailable. Database `finished_at` records administrative closure and includes downtime; it is not uninterrupted execution duration.

| Observation | This interrupted run | Previous `7be59cdf` |
|---|---:|---:|
| Acquired benchmark publications | 5/18 | 6/18 |
| Cited benchmark publications | Unavailable: no report | 5/18 |
| Actual Exa requests completed | 5/5 | 5/5 |
| Corroboration model calls | Not reached | 8/12 completed; four output-limit errors |
| Human precision | Unlabelled | Unlabelled |

Newly acquired: GT11. Not reacquired: GT08 and GT22. This is an interrupted observation, not a controlled or clean end-to-end comparison. Unreached corroboration does not establish a zero-timeout improvement. The strict quality exporter correctly refused **“Single uninterrupted execution proof required”**; missing citation metrics remain unavailable.

The database retained **29 document versions, 153 passages containing 132,858 characters, and three unverified findings** after Docker/database restart. All eight analysis batches started: five completed, two hit the 120-second deadline, and the eighth was interrupted. Final passage dispositions are 60 analysed, 24 failed by request timeout, 12 failed by interruption and 57 deferred by the eight-batch limit. No passages remain pending after closure. A completed batch may return no findings: processed-passage counts do not establish exhaustive fact extraction. Deferred and failed text remains stored independently of generated findings.

Known provider usage was **233,332 tokens**, plus **83,528** conservative reservations for the two failed requests and **44,166** for the unfinished request: **361,026 actual-plus-unknown-reserved tokens**. Unknown reservations are not measured usage or cost. The original journal remains intact with one start, 24 model starts, 21 completions, two error terminals and one unresolved request; no normal `run_finished` was fabricated. The native scout log contains 29 sent acquisition attempts, four policy refusals and two reused entries.

MAS remained inactive with **zero fetches and zero versions**. Browser acquisition was enabled globally, with existing source grants unchanged; no source currently has a browser approval, so there were zero browser attempts. Private artifacts remained local. The separate worker Storage key is absent; the configured database URL already provides the worker's database connection. No anon key was repurposed, private Supabase upload attempted, remote migration applied, role model changed or historical report rewritten.

The unchanged implementation's prior proof remains **939 tests +8 subtests passed, none skipped (64.05s)**. This evidence-only update did not repeat that suite. Offline harness checks covered concurrent/shared Exa caps, known/unknown token reservations, deadline refusal and syntax/SQL construction. Post-interruption checks verified retained text/findings, terminal closure, MAS exclusion and strict exporter refusal. Local journals, native step records, manifest, coverage before/after closure and SHA256 inventory are retained under `reports/1637f9f8-a3f3-49e0-af06-2d15f6d198f6/`.

Team follow-up: improve bounded analyst reliability and use generic publication/index metadata to prioritize useful passages within the batch allowance. Verification, corroboration, report acceptance and human precision still need an uninterrupted validation. The single authorization was used; no continuation or replacement was started.
