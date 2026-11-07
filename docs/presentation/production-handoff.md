# Presentation production handoff

**Objective:** Update the existing editable Mira presentation with the current evidence cut while retaining its existing design and useful content.

**Base SHA:** `aa05d8d0a535212e56e3009a45ccec6875598507`

**Owned files:** `docs/presentation/production-handoff.md`; output artifacts under `reports/presentation-output/current/` (ignored).

**Read-only source references:**

- `docs/presentation/slide-outline.md` (15-slide narrative and claim boundaries)
- `docs/agent-handoffs/checkpoint.json` (three HK runs, budgets, recall, costs, caveats, earlier 280 + 8 local verification); latest-run local `coverage-comparison.json` plus coordinator-reported token counts for the two 15-document runs (172,245 and 239,048)
- `docs/mira_PRD_v3_draft.md` §§2–5, 6, 7.3, 8–9 and decisions D6–D10
- Existing generated source deck `reports/presentation-output/Mira_DBS_Presentation_Corroboration.pptx` (16 slides)
- Coordinator's post-coverage integration update: 285 tests + 8 subtests passed; none skipped. This supersedes the earlier checkpoint's 280 + 8 local result for the final-suite statement.

**Changes:** Revised the existing deck in place as an imported PPTX and saved it as `reports/presentation-output/current/Mira_DBS_Deck_2026-11-07.pptx`. Kept the source deck's 16-slide canvas, imagery, tables and visual style. The additional technical and evaluation appendix slides remain after the 15-slide outline sequence.

- Updated the three-run table with each document allowance, the final run's 600,000-token and 25-minute limits, actual tokens/time/cost, recall denominators, and fact/inference/unresolved counts. Baseline and initial-fix token counts are 172,245 and 239,048, sourced from the latest local run-comparison artifact. Labeled the final run partial and not an equal-budget comparison. Included the 10 primary publications separately from the 7/18 benchmark matches.
- Updated the local suite result to 285 + 8 with no skips, per the coordinator's post-coverage integration update.
- Marked independent corroboration as approved future work after coverage and identified the design steps as illustrative, not implemented. Kept D7 policy details open.
- Kept research-time savings, auditor-labelled precision and benchmark acceptance as unproven. Replaced old acceptance-target language with outstanding evaluation decisions.
- Removed a stale handwritten annotation that overlapped the results table. Added current tracked source references to the relevant speaker notes.

**Sources/commands:** Read the presentation skill, template-following and local-PPTX implementation/finalization references. Loaded the bundled workspace dependencies. Imported and rendered the generated PPTX with `@oai/artifact-tool`; edited existing text and table objects; rendered all 16 slides and inspected the montage plus slides 9, 12–14 and 16. Ran the skill finalizer on the candidate.

**Validation and render QA:** 16-slide count, PPTX package integrity, layout geometry, source-template coverage, required native table on slide 9, and first-party Artifact Tool import all passed. Finalizer reported zero findings and zero layout warnings. The candidate was visually checked at full size for run legibility, future-work labels, closing slide fit and evaluation text fit. The slide 9 preview was refreshed after adding the two coordinator-provided token counts. The result table remains editable.

Preview files are in `reports/presentation-output/current/`: `Mira_DBS_Deck_2026-11-07_Montage.webp`, plus full-size previews for slides 9, 12, 13, 14 and 16.

**Remaining slide gaps:** Slides 4–5 describe the documented research flow; they are not a browser-recorded walkthrough. The reviewer and sign-off screens still need browser rehearsal evidence before the deck can claim the flow was rehearsed. Source limits remain: MAS automated access is blocked and some industry sources lack text-storage permission. The benchmark and precision worksheet still need human review. No corroboration feature, measured time savings, auditor-labelled precision, accepted M0 result or comprehensive-coverage claim is presented.

**Integration:** Coordinator checked the rendered results slide and montage, verified the native slide count and updated token values, and confirmed the 285 + 8 integration result. Track this handoff and deliver the PPTX locally; generated deck/video artifacts remain ignored, consistent with the PR exclusions. The editable deck is not uploaded or published by this change. Next, use actual browser rehearsal captures to replace only generic workflow illustrations and label the observed scope accurately.

**Open risks:** The supplied deck had 16 slides while the outline has 15. I retained the technical and evaluation appendices instead of deleting them. The evaluation appendix labels the historical M0 gate as not passed. Visual QA used bundled Artifact Tool rendering and structural validators; native PowerPoint execution was not tested.

**Status:** Complete
