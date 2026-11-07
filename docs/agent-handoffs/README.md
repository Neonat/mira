# Agent handoffs

This directory coordinates parallel engineering work. It is not a change to Mira's runtime agent architecture. Use a fresh task/fork without chat history; include only the task, ownership boundary, and this checkpoint. Do not ask workers to reread historic chat.

## Current checkpoint

- Branch: `codex/nat-ingestion`; origin: `https://github.com/Neonat/mira.git`.
- Pushed runtime checkpoint: `1c970c825565430ae7a36e736f6880da9371edcd`.
- Latest assignment base: `f153e716fa2587755b255068b9ef6e13e9f6a4fe`; resolve `git rev-parse HEAD` for the integrated URL/failure-accounting/demo checkpoint.
- Pre-checkpoint source baseline: `1d38e8916120d45d063d5157abcac6fc2db1af6f`, retained for historical comparisons. The coordinator supplies the current `git rev-parse HEAD` for each new assignment.
- Latest integrated verification: **293 tests plus 8 subtests**, none skipped, including local Postgres at `localhost:55432` and offline evaluation tests. Earlier checkpoints were 280 and 285 tests. Migration `20261107120000` is local only; no remote deployment.
- Latest and only new Hong Kong run `e2fda30f-36f9-4aa3-83c3-d78b81671b83`: requested 30 documents, 600,000 tokens and 25 minutes; **32 saved versions**, 19 facts, no inference, five unresolved, 13 distinct cited source URLs. Recall 9/18 overall/fetchable and 9/14 regulatory; 21.68 minutes, 372,220 recorded tokens and estimated `$1.8290` from recorded steps. Partial due to a malformed HKMA URL; failed-scout usage may be missing. This is **pre-fix**, not a controlled budget comparison or post-fix gain. Earlier 30-document run cited 7/18 overall and 7/14 regulatory. Human precision is unlabelled.
- [Fresh diagnosis](hk-telemetry-diagnosis.md): URL spaces now encoded; invalid requests fail per document; failed scouts persist partial diagnostics and known usage and charge their completed/failed owned fetches before gap rounds. Reviewed and tested offline. Remaining SFC selection/capacity and source access/storage gaps are disclosed; no second paid run and no corroboration implementation.
- Detailed local reports are ignored by git at `reports/<id>/coverage-comparison.json`, `report-v1.html`, and `precision_worksheet.csv`. Preserve portable summaries in tracked artifacts when needed; do not rely on ignored reports for handoff.
- Portable measured evidence is in [checkpoint.json](checkpoint.json). The historical diagnostic and [telemetry implementation](telemetry-implementation.md) are completed; [coverage-trace.md](coverage-trace.md) preserves the original evidence limits. The updated product snapshot is [PRD v3 draft](../mira_PRD_v3_draft.md). Active PR: https://github.com/Neonat/mira/pull/3.

## Starting a fresh coordinator

Use this bounded prompt in a new Codex session in this repository:

> Read AGENTS.md, this handover, checkpoint.json and hk-telemetry-diagnosis.md. Use the current `git rev-parse HEAD` as the assignment base. The single authorized fresh run, diagnosis, URL fix and failed-scout accounting fix are complete; do not repeat them or launch paid runs without new authorization. Use retained diagnostics for generic selection/capacity improvements. Slides continue from their production handoff; authenticated review/sign-off is complete in the local synthetic demo handoff. At most three fresh-context workers with disjoint ownership. Keep corroboration implementation deferred until coverage exits.

The project profiles select models explicitly. See `.codex/agents/`; the coordinator keeps the user's existing model. Profiles follow the [official custom-agent format](https://learn.chatgpt.com/docs/agent-configuration/subagents). They apply to fresh sessions; creating these files does not reset this chat's context or change Mira's API model settings.

## Completed specialist handovers

| Agent/model | Deliverable | State and next step |
|---|---|---|
| coverage_engineer / Terra | [Fresh telemetry diagnosis](hk-telemetry-diagnosis.md), following [telemetry implementation](telemetry-implementation.md) | One paid run complete; URL and failed-scout accounting fixes reviewed. Integrated suite 293 + 8 passed. Next: generic selection/capacity work; post-fix live recall unmeasured. |
| presentation_editor / Luna | [Storytelling deck handoff](../presentation/storytelling-production-handoff.md) | New 16-slide editable deck follows the approved story: ten main slides and six appendices. Annotations absent, diagrams/report crop revised, 16 notes and movie/preview links checked. Local output `reports/presentation-output/storytelling/Mira_DBS_Storytelling.pptx`. |
| demo_engineer / Sol, motion worker / Terra | [Motion showcase handoff](../demo/launch-production-handoff.md), [production checkpoint](../demo/launch/COORDINATOR.md) | Final 180-second HyperFrames/Remotion MP4 exported after user approval. Full decode and five browser playback checks passed. Packaged with the final 16-slide PPTX and relative movie link in `reports/presentation-output/storytelling/Mira_DBS_Presentation_Package.zip`; CRC/hash checks passed. Editable preview remains at `http://localhost:3100/FollowTheEvidence`. Earlier recordings remain unchanged. |

The initial preparation assignments used checkpoint `1c970c8`; the first production pass used `aa05d8d`, with telemetry pushed in `2445846`. This latest pass used `f153e71` and made exactly one paid research run. Read completed handovers before assigning more work; workers are not continuing in the background. Generated deck/video artifacts remain ignored local deliverables, while their reproduction and limitations are tracked here.

## Work order and boundaries

1. `coverage_engineer` first: telemetry, the fresh diagnosis and URL/failure-accounting fixes are integrated. Address evidenced selection/capacity and publication-level gaps using the retained diagnostics. No post-fix live recall is measured; any further paid validation requires new coordinator authorization. Do not expand source permissions/scope. MAS is blocked; some industry sources lack storage permission.
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
