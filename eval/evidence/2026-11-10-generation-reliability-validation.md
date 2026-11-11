# Australia/UAE generation reliability validation - 10 November 2026

The single authorized live validation **did not meet clean end-to-end acceptance**. It completed four analysis batches and persisted supported findings for both markets, then lost its local database connection before the writer. The retained evidence was recovered without paid continuation. Final follow-up bounds pass automated tests but remain live-unvalidated.

Audience: engineering reviewers and private organisational peers. This is engineering evidence, not audit sign-off, national publication coverage or a human precision evaluation. The [portable result](2026-11-10-generation-reliability-validation.json) contains measured scope and counters; [artifact hashes](2026-11-10-generation-reliability-artifacts.json) identify the sharing package.

## Runtime and test scope

Live run `f17f39d0-9fd1-4059-8c3f-e44088269b51` used runtime **`a7ff8afcaf226f17efeaac9d12c8f64adfc1d1eb`**. It used existing configured role models/effort, actual Exa API discovery and experimental approved-source embeddings. Only `au-register`, `austrac` and `cbuae` were active in its dedicated workspace. Malaysia/DIFC-DFSA remained outside the enabled source set; MAS was inactive with zero saved versions. UAE external embedding and browser escalation were not enabled.

Frozen caps: **8 research representations,600,000 known-plus-unknown-reserved tokens,25 minutes,4 Exa searches,10 embedding requests/100,000 UTF-8 input bytes, zero gap rounds**. Analysis was scoped to four calls of at most three whole passages/6,000 content characters,8,192 output tokens and 120 seconds, protecting 60,000 tokens/360 seconds for downstream work. These are validation settings, not exhaustive archive processing or a proof of the larger production defaults.

The ledger shared model/embedding admission and downstream reserves. Ordinary requests used runtime bounds, without the previous wrapper's scout60s/analyst90s clamps. No model configuration or source grant was changed.

## Actual outcome

| Measurement | Recorded result |
|---|---|
| Execution | Failed after 715.154 seconds; no live report row or writer call |
| Acquisition | 8 saved representations: 2 native metadata captures and 6 readable HTML/PDF captures across all 3 source profiles |
| Retained text | 747,479 extracted characters and 1,198 citation passages |
| Analysis | 4/4 calls succeeded ; 12 analysed passages,4 each from the three sources ; 1,186 deferred, zero failed/pending |
| Persisted findings | 7 draft claims; four supported facts (3 AU/1 AE); recovery export includes those four facts only |
| Corroboration | 3 stored assessments: 2 primary-source-only and 1 inconclusive; one additional fact not assessed because its primary quote was not exact |
| Failed generation | One 60.03-second corroboration timeout; AE scout summary and final inference output-limit errors |
| Calls | 21 model,2 Exa and3 embedding requests |
| Experimental indexing | 28 AU vectors, zero UAE vectors;1,135 eligible AU passages still pending indexing |

Four factual claims have saved quote and semantic checks. A supported model check is not a human relevance/precision label. No independent second-source support was established. The incomplete source checklist is retained even where later analysis found a supported UAE fact.

The provider ledger settled every request before recording the outcome. Local Docker/PostgreSQL stopped at **20:51:24 UTC on 9 November** (10 November Singapore time). The orchestrator could not persist its final failed inference step or update its run status on that lost connection. The existing container was restarted later without reset/restore; the stranded run and step were closed failed, without research resume. Database closure timestamps include downtime and do not establish execution duration. The original parent exit status was not retained; no exit result is invented.

## Usage and durability

Known usage reconciles as **123,779 persisted model tokens  + 4,998 persisted embedding tokens  + 8,991 known failed-request tokens retained externally  = 137,768 known tokens**. Add **13,401 unknown-call reservations** for **151,169/600,000 allowance used**. Unknown reservations are not measured billed tokens. The interrupted failed request's input/output split was unavailable in this ledger version; it was not fabricated or assigned to a new provider call. Final follow-up journaling now retains that split.

After restart, all eight saved extraction hashes match. Every one of 1,198 passage offsets matches its saved text, and all **628,999 publication non-whitespace characters** are covered. The two discovery captures retain complete native JSON records and intentionally have no citation passages. This establishes preservation **after extraction**, not original PDF/table/OCR or exhaustive fact accuracy. All7 claims and saved checks survived. Same-volume identity before the run was not independently recorded; the restart used the existing container and no reset/restore command.

The recovered draft was rendered offline using the existing claim-section/report renderer. It includes only four factual claims whose latest supported checks still match current SQL evidence fingerprints and whose supporting quotations pass the existing quote/numeric check. It shows saved corroboration, source notices, source links and coverage dispositions. It has **no new provider calls, report database row, generated writer summary or sign-off**. It is a separate partial recovery artifact, not an uninterrupted live report or strict quality-export acceptance.

## Comparison with the previous run

| Measurement | Previous `0451a19c` | Current `f17f39d0` |
|---|---|---|
| Document/token/time caps | 12 /250,000 /20 min | 8 /600,000 /25 min |
| Acquired source profiles | 3 | 3 |
| Saved representations | 11 | 8 (2 metadata +6 readable) |
| Citation passages | 2,048 | 1,198 |
| Analysis | One actual analyst call timed out; later calls declined | Four calls completed;12 passages analysed |
| Supported facts | 0 | 4 persisted; offline recovered draft |
| Generation timeout calls | 3 (2 scout,1 analyst) | 1 (corroboration) |
| Live writer/report | Skipped; coverage-only fallback | Not reached; database interruption |

Budgets, acquired representations and corpus differ. The larger prior passage count included alternate legislation representations/compilations; the current eight-representation cap also funds native metadata. This is a descriptive engineering comparison, **not publication recall, national coverage, efficiency or a hybrid usefulness win**. Source breadth stayed at all three profiles.

## Final follow-up and verification

Final runtime **`0c1d500ae3879bcc06b6ea9d830a97f1b3a369f5`** retains the source/document-fair batch planner,16k whole-passage scout input selection, common serialized reservation formula and downstream reserves. Follow-up changes after the live run provide:

- Scout summaries:16,384 output tokens within 120 seconds.
- Ordinary verification:8,192 output tokens within 120 seconds.
- Runtime corroboration:one candidate, unchanged bounded excerpts,90-second total claim ceiling and at most 8,192 output tokens. Historical default/explicit 30/60-second assessments remain valid.
- Explicit `request_timeout` classification; per-request input/output usage splits; report allowance wording includes unknown reservations.

Red/green checks reproduce the old bound/journal mismatches. Final integrated verification: **1,075 tests +8 subtests passed, none skipped, in 70.34 seconds**, with local PostgreSQL and actual offline Chromium. Independent scoped runtime review and a separate retained-artifact audit found no blockers. Higher bounds can reduce the number of funded calls and do not guarantee provider latency. **No paid rerun of this final runtime occurred.**

## Peer files

The local package under `reports/generation-reliability-20261110/` contains a 7-page recovered research draft and a 6-page validation report, both PDF and standalone HTML, plus metadata, README and checksums. All PDF pages were rendered and checked; source cards and tables are readable. The package excludes credentials, environment files, database dumps, full publisher originals/bodies, vectors and private process logs. CBUAE evidence remains for private organisational peer review with attribution.

Clean live end-to-end acceptance, human precision, extraction completeness and hybrid usefulness remain open. The one new live validation allowance is consumed. No replacement paid run, merge, remote deployment, historical rewrite or model-setting change was performed.
