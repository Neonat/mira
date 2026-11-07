# Mira demo deck outline

**Purpose:** a 15-slide, evidence-led presentation of the current internal audit research prototype and its limits. This is an outline, not a claim that a deck or demo has been produced.

**Evidence cut:** checkpoint dated 2026-11-07 and PRD v3 draft. Do not generalize the Hong Kong results to other scopes. Do not claim production readiness, independent corroboration, measured time savings, auditor-labelled precision, comprehensive coverage, or passed benchmark acceptance targets.

## Slide map

| # | Slide / point | Content and evidence | Status |
|---|---|---|---|
| 1 | Mira: research support for internal audit | Title plus one-sentence scope: public regulatory and industry research; auditors decide and act. PRD v3 §2, D6. | Reusable today |
| 2 | The auditor's research problem | Frame the workflow challenge as a product problem, not a measured baseline: find relevant publications, inspect support, prepare a reviewable synthesis. PRD v3 §2. | Reusable today; avoid quantified pain claims |
| 3 | Who does what | Analyst submits and monitors; reviewer accepts/amends/rejects and signs off; curator handles source permissions/checklist; administrator manages access/configuration. PRD v3 §2. | Reusable today |
| 4 | Current user journey | Brief and run limits → plan/optional approval → research and evidence → review → signed-off report → rerun/diff. PRD v3 §§3–4. | Reusable today; visual walkthrough needs browser evidence |
| 5 | What runs, in what order | Code-controlled orchestration: parallel scoped scouting and budget/cancellation/step records; coverage gap fill occurs before analysis and verification; writer renders saved verified claim text. Do not depict post-verifier claim repair. PRD v3 §§3–4. | Reusable today; exact UI trace needs browser evidence |
| 6 | Fixed code and bounded agent judgement | Show the division: code owns scope, budgets, sequence, typed outputs, evidence persistence and checks; agents propose plans, discover candidates, analyze evidence and draft findings within assigned tasks. Do not imply agents can override gates. PRD v3 §§3–4. | Reusable today |
| 7 | Facts, inferences and DBS decisions | Separate sourced facts from labelled inferences and unresolved items. Contextual risks/trends may be described; DBS audit actions and business decisions stay with the auditor (settled D6). PRD v3 §§2–3. | Reusable today |
| 8 | Sources, permissions and provenance | Show approved/configured source boundary, saved versions/passages and evidence trace. MAS automated access is blocked and storage permission unresolved; some industry sources lack text-storage permission. Fetchability is not permission. PRD v3 §§2, 8. | Policy caveats reusable; current evidence/source UI needs browser evidence |
| 9 | Verification and reviewer control | Explain quote/semantic checks and exclusion of unsupported claims; review supports decision/amend/reject, dependent review and sign-off. Accuracy is not measured; local full-suite evidence is not a live usability proof. PRD v3 §§3, 5.1, 5.5. | Capability summary reusable; reviewer flow needs browser evidence |
| 10 | Corroboration: approved next capability | Independent second-source corroboration is approved future work after coverage; it has no runtime implementation. D7 eligibility, independence, allowance and sign-off policy remain open. PRD v3 §§3, 9. | Future work only; no feature demo |
| 11 | The measured Hong Kong run | Display actual allowance beside outcomes: **30 documents / 600,000 tokens / 25 minutes allowed; 302,985 tokens used; stopped at document allowance.** Results: 17 facts, 1 inference, 1 unresolved; 10 primary publications cited; benchmark recall 7/18 overall and 7/14 regulatory; 15.29 min; estimated $1.4395. Checkpoint and PRD v3 §7.3. | Reusable today; retain partial-run label |
| 12 | Read the comparisons carefully | Baseline: **15 documents allowed**, 1/18 recall, 6 facts/1 inference/1 unresolved, 10.35 min, estimated $0.7135. Initial fix: **15 allowed**, 2/18, 10/1/3, 13.22 min, estimated $1.1883. Final: **30 allowed**, 7/18, 17/1/1, 15.29 min, estimated $1.4395. Different final allowance means not an equal-budget comparison. Human precision is unlabelled; 18 worksheet rows do not establish precision. checkpoint.json; PRD v3 §7.3. | Reusable today with caveats |
| 13 | Coverage and source limits remain | Latest run cited 10 primary publications but matched 7 of 18 benchmark publications; these are distinct measures. MAS access/storage and industry text-storage permissions constrain the scope. Coverage is incomplete, and no comprehensive-coverage claim follows. checkpoint.json; PRD v3 §§5.3, 7.3, 8. | Reusable today |
| 14 | What is implemented versus pending | Implemented prototype: controlled SG/HK brief, on-demand research, saved evidence, HTML report/snapshot, review/sign-off, rerun/diff; local suite 280 tests + 8 subtests, none skipped. Pending/limited: browser rehearsal, human precision labels/accepted benchmark, remote deployment, source permissions, D7 corroboration details. PRD v3 §§2–3 and checkpoint.json. | Reusable today; do not imply deployment |
| 15 | Decisions and next steps | Finish coverage diagnosis and permission review; rehearse actual review workflow; label evidence and agree D9 benchmark; then design/implement corroboration after coverage exit. PRD v3 §§8–9. Close with explicit pilot scope and open decisions. | Reusable today as roadmap; roadmap is not delivery commitment |

## Deck production notes

- Slides 1–3, 6–8, 10, 11–15 can be drafted from the cited tracked sources. Keep future capability visually distinct from implemented behavior.
- Slides 4, 5 and 9 should use captured browser evidence before presenting UI details as a walkthrough; browser rehearsal is still outstanding. Do not invent screenshots or imply rehearsal occurred.
- The three-run comparison must show each document allowance beside its result. Keep actual tokens/minute limits adjacent to the final run, and label elapsed time and cost as observed/estimated values.
- Local HTML reports may support clearly labelled prototype playback. Use the tracked summary for portable measurements, and keep the human precision worksheet labelled as unreviewed.

## Exact next step

Local editable inputs were confirmed to exist during checkpoint integration: latest generated draft `reports/presentation-output/Mira_DBS_Presentation_Corroboration.pptx`, and original `/Users/natsim/Downloads/Mira_DBS_Presentation_Updated.pptx`. The supplied PDF and annotated report also remain in Downloads. These are local inputs, not committed artifacts.

Next, use the current session's `presentations:Presentations` skill to inspect the generated draft, compare it with the original and this outline, and produce a revised editable deck. Update the measured results and future-feature labels. Obtain browser captures for slides 4/5/9 before finalizing. Measured evidence is in PRD v3 §7.3; verification and review behavior are in §§5.1 and 5.5. The actual deck edit is a separate bounded assignment.
