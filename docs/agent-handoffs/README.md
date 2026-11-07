# Agent handoffs

This directory coordinates parallel engineering work. It is not a change to Mira's runtime agent architecture. Use a fresh task/fork without chat history; include only the task, ownership boundary, and this checkpoint. Do not ask workers to reread historic chat.

## Current checkpoint

- Branch: `codex/nat-ingestion`; origin: `https://github.com/Neonat/mira.git`.
- Pushed runtime checkpoint: `1c970c825565430ae7a36e736f6880da9371edcd`.
- Pre-checkpoint source baseline: `1d38e8916120d45d063d5157abcac6fc2db1af6f`, retained for historical comparisons. The coordinator supplies the current `git rev-parse HEAD` for each new assignment.
- Local verification reported 280 tests plus 8 subtests, none skipped, using local Postgres at `localhost:55432`. Migration `20261107120000` is local only; no remote deployment.
- Latest Hong Kong run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0`: requested limits were 30 documents, 600,000 tokens and 25 minutes; actual 17 facts, 1 inference, 1 unresolved, 10 primary publications. Recall 7/18 overall and 7/14 regulatory. Estimated cost `$1.4395`; elapsed 15.29 minutes; 302,985 tokens. It stopped at the document allowance. This is not directly comparable to the 15-document runs: baseline recall was 1/18; initial fix was 2/18. Human precision is unlabelled.
- Detailed local reports are ignored by git at `reports/<id>/coverage-comparison.json`, `report-v1.html`, and `precision_worksheet.csv`. Preserve portable summaries in tracked artifacts when needed; do not rely on ignored reports for handoff.
- Portable measured evidence is in [checkpoint.json](checkpoint.json). The [diagnostic brief](coverage-next.md) is completed; [coverage-trace.md](coverage-trace.md) records its result and the next telemetry task. The updated product snapshot is [PRD v3 draft](../mira_PRD_v3_draft.md).

## Starting a fresh coordinator

Use this bounded prompt in a new Codex session in this repository:

> Read AGENTS.md, docs/agent-handoffs/README.md, checkpoint.json and the completed coverage-trace.md. Use the current `git rev-parse HEAD` as the assignment base. Give coverage_engineer one bounded candidate/selection-telemetry task with a scripted regression; explicitly assign any shared persistence files before editing. In parallel, presentation_editor can advance the existing outline into the confirmed editable deck, and demo_engineer can advance the existing script into a bounded rehearsal when the local environment is ready. At most three workers. Do not repeat the completed diagnostic, outline or script. Review concrete handovers before integration; no paid research for the telemetry task. Keep corroboration implementation after the coverage milestone.

The project profiles select models explicitly. See `.codex/agents/`; the coordinator keeps the user's existing model. Profiles follow the [official custom-agent format](https://learn.chatgpt.com/docs/agent-configuration/subagents). They apply to fresh sessions; creating these files does not reset this chat's context or change Mira's API model settings.

## Completed specialist handovers

| Agent/model | Deliverable | State and next step |
|---|---|---|
| coverage_engineer / Terra | [Coverage trace](coverage-trace.md) | Confirms the publication was not fetched; candidate-stage cause is unknown. Next: bounded selection telemetry and a scripted test, not a speculative ranking change. |
| presentation_editor / Luna | [15-slide outline](../presentation/slide-outline.md) | Outline ready; editable local inputs identified. Actual deck editing and browser captures remain outstanding. |
| demo_engineer / Sol | [E2E demo script](../demo/e2e-demo-script.md) | Script ready; screen steps are proposals. Browser rehearsal, review writes and video capture remain outstanding. |

These bounded assignments completed against runtime checkpoint `1c970c8`. No new paid research run or runtime change was made. Read the handover before assigning implementation; workers are not continuing indefinitely in the background.

## Work order and boundaries

1. `coverage_engineer` first: the completed trace calls for bounded candidate/selection telemetry before changing ranking. Follow with evidenced publication-level completeness, SFC enforcement and applicable-guideline work. Do not expand source permissions/scope. MAS is blocked; some industry sources lack storage permission. Report evidence and scoped checks. No broad claims from incomplete runs.
2. `evidence_architect` may do read-only design/review now. Corroboration is approved future work, gated until coverage exits; it has not been built. After activation, keep its implementation to the corroboration module/schema/design and coordinate shared contracts/orchestration with the coordinator.
3. Evaluation, presentation, and demo preparation may proceed in parallel only within their ownership. Presentation outline/script may be drafted with approved facts; do not imply unbuilt features or unlabelled precision. Demo rehearsal uses current behavior and does not change runtime code or claims.
4. Reviewer checks a focused diff read-only. Coordinator integrates, records the integration SHA, and runs the full suite once.

Never have two writers on the same files. Shared contracts, orchestrator, migrations, and PRD require explicit coordinator assignment. See repository `AGENTS.md` for the compact rules and role file boundaries.

## Handover template

```text
Objective:
Base SHA:
Owned files:
Read-only files:
Sources/commands:
Changes:
Scoped checks and results:
Open risks:
Exact next step:
Status: complete | blocked
```
