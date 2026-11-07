# Agent handoffs

This directory coordinates parallel engineering work. It is not a change to Mira's runtime agent architecture. Use a fresh task/fork without chat history; include only the task, ownership boundary, and this checkpoint. Do not ask workers to reread historic chat.

## Current checkpoint

- Branch: `codex/nat-ingestion`; origin: `https://github.com/Neonat/mira.git`.
- Pushed runtime checkpoint: `1c970c825565430ae7a36e736f6880da9371edcd`.
- Pre-checkpoint source baseline: `1d38e8916120d45d063d5157abcac6fc2db1af6f`, retained for historical comparisons. The coordinator supplies the current `git rev-parse HEAD` for each new assignment.
- Runtime checkpoint verification reported 280 tests plus 8 subtests. Subsequent telemetry integration passed 285 tests plus 8 subtests, none skipped, using local Postgres at `localhost:55432`. Migration `20261107120000` is local only; no remote deployment.
- Latest Hong Kong run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0`: requested limits were 30 documents, 600,000 tokens and 25 minutes; actual 17 facts, 1 inference, 1 unresolved, 10 primary publications. Recall 7/18 overall and 7/14 regulatory. Estimated cost `$1.4395`; elapsed 15.29 minutes; 302,985 tokens. It stopped at the document allowance. This is not directly comparable to the 15-document runs: baseline recall was 1/18; initial fix was 2/18. Human precision is unlabelled.
- Detailed local reports are ignored by git at `reports/<id>/coverage-comparison.json`, `report-v1.html`, and `precision_worksheet.csv`. Preserve portable summaries in tracked artifacts when needed; do not rely on ignored reports for handoff.
- Portable measured evidence is in [checkpoint.json](checkpoint.json). The historical diagnostic and [telemetry implementation](telemetry-implementation.md) are completed; [coverage-trace.md](coverage-trace.md) preserves the original evidence limits. The updated product snapshot is [PRD v3 draft](../mira_PRD_v3_draft.md). Active PR: https://github.com/Neonat/mira/pull/3.

## Starting a fresh coordinator

Use this bounded prompt in a new Codex session in this repository:

> Read AGENTS.md, this handover, checkpoint.json and telemetry-implementation.md. Use the current `git rev-parse HEAD` as the assignment base. Telemetry and its scripted tests are implemented; do not recreate them or repeat the completed historical diagnostic. The next coverage assignment should inspect retained diagnostics from a single explicitly authorized bounded validation before proposing a ranking change. Slides and demo should continue from their production handovers, not from the old outline/script tasks. At most three fresh-context workers with disjoint ownership. Review concrete handovers before integration. Keep corroboration implementation after the coverage milestone.

The project profiles select models explicitly. See `.codex/agents/`; the coordinator keeps the user's existing model. Profiles follow the [official custom-agent format](https://learn.chatgpt.com/docs/agent-configuration/subagents). They apply to fresh sessions; creating these files does not reset this chat's context or change Mira's API model settings.

## Completed specialist handovers

| Agent/model | Deliverable | State and next step |
|---|---|---|
| coverage_engineer / Terra | [Telemetry implementation](telemetry-implementation.md), following the [historical trace](coverage-trace.md) | Implemented and reviewed; 285 tests + 8 subtests passed with PostgreSQL. Next: inspect future retained diagnostics before changing ranking. |
| presentation_editor / Luna | [Deck production handoff](../presentation/production-handoff.md) | Updated 16-slide editable deck rendered and checked; output is local under `reports/presentation-output/current/`. Browser workflow captures remain outstanding. |
| demo_engineer / Sol | [Demo production handoff](../demo/production-handoff.md) | Local 180-second silent saved-report walkthrough captured and playback-tested. Authenticated brief/history/review/sign-off still need rehearsal. |

The initial preparation assignments used checkpoint `1c970c8`; the production pass used `aa05d8d`, with tested telemetry pushed in `2445846`. No new paid research run was made. Read the completed production handovers before assigning more work; workers are not continuing indefinitely in the background. Generated deck/video artifacts remain ignored local deliverables, while their reproduction and limitations are tracked here.

## Work order and boundaries

1. `coverage_engineer` first: bounded candidate/selection telemetry is integrated. Use future retained diagnostics before changing ranking, then address evidenced publication-level completeness, SFC enforcement and applicable-guideline gaps. No new recall score is claimed from instrumentation. Do not expand source permissions/scope. MAS is blocked; some industry sources lack storage permission.
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
