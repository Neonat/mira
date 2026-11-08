# Agent handoffs

This directory coordinates parallel engineering work. It is not a change to Mira's runtime agent architecture. Use a fresh task/fork without chat history; include only the task, ownership boundary, and this checkpoint. Do not ask workers to reread historic chat.

## Latest PR7 follow-up: actual live browser

`0f9526d` adds real Chromium navigation/JavaScript and permitted read-only actions, with explicit global/source approvals and frozen browser context. **487tests +8subtests passed, none skipped**, including real Chromium fixtures, local PostgreSQL and PR6 regressions. One HKMA public-page capture succeeded in24.91s (20,084characters,128links); two denied optional resources mean partial capture. Earlier60s timeout is preserved with unknown-stage caveat. MAS remains disabled by explicit user instruction; no source grants were persisted, model settings changed or paid/model calls made. Read [live-browser integration](live-browser-integration.md) and [portable HKMA evidence](hkma-live-browser-validation.json). PR7 is updated, not merged/deployed.

## Current ingestion/corroboration implementation

The active branch is `codex/ingestion-corroboration`. Phase 1 exited at `83c84c1` with independent review and **378 tests plus 8 subtests, none skipped**, including local PostgreSQL. Phase 2 implements saved-first corroboration, bounded optional targeted acquisition, exact proposition/origin decisions and immutable reviewed results. Read [ingestion expansion](ingestion-expansion.md), [measurement](ingestion-measurement.md), [corroboration](corroboration.md) and [bounded acquisition](corroboration-acquisition.md) for current scoped ownership and evidence. The coordinator's final integration handoff/checkpoint supersedes the historical work order below.

PR4 and subsequent PR5/PR6 are merged; current upstream `16effde` is integrated, preserving their guardrails and documentation. Final integration at `42efc32` passed **459 tests plus 8 subtests, none skipped**, including local PostgreSQL and offline evaluation. See [integration handoff](ingestion-corroboration-integration.md); [PR7](https://github.com/Neonat/mira/pull/7) is open against `main` after PR4/5/6 merged. No paid/live research/model calls or remote migrations are authorized by these changes. D7 defaults are explicit in PRD §6; enterprise policy adoption, original capture retention and durable artifact storage remain open. Existing slides/video keep their historical evidence cut. A separate upstream HK precision worksheet awaits review and is not post-feature evidence.

## Current checkpoint

- Runtime checkpoint branch: `codex/nat-ingestion`; roadmap documentation branch: `codex/prd-ingestion-corroboration`; origin: `https://github.com/Neonat/mira.git`.
- Latest evidence-integrity assignment base: `ad79028f650cc4e8632fc94344c72e0ed332a47a`. Implementation commit: `27c28fac8631c9afdb8cdef60ab6b48b526ef5a7`, pushed in follow-up PR4. Separate report-layout commit `53b88fb` arrived during integration and is preserved. Resolve `git log -1 -- docs/agent-handoffs/evidence-integrity-fix.md` for this source checkpoint.
- Earlier runtime checkpoint: `1c970c825565430ae7a36e736f6880da9371edcd`; URL/failure-accounting/demo work followed base `f153e716fa2587755b255068b9ef6e13e9f6a4fe`.
- Pre-checkpoint source baseline: `1d38e8916120d45d063d5157abcac6fc2db1af6f`, retained for historical comparisons. The coordinator supplies the current `git rev-parse HEAD` for each new assignment.
- Latest evidence-integrity verification: **350 tests plus 8 subtests**, none skipped, including local Postgres at `localhost:55432` and offline evaluation. This full suite ran in an isolated checkout excluding concurrent report-layout work; **26 focused renderer/layout checks** then passed with `53b88fb` integrated. Earlier checkpoints were 280, 285 and 293 tests. Migrations through `20261107180000` are local only; no remote deployment.
- [Evidence-integrity checkpoint](evidence-integrity-fix.md): contract-1.4 reviewed snapshots freeze complete evidence, verification provenance and reviewer inputs; incomplete reviewed renders fail closed; retrieval selects current eligible saved versions before ranking/limits. Legacy artifact files remain unchanged, legacy snapshots refuse regeneration, and no historic verification inputs are backfilled. Its deferral records that completed task's scope; the user's subsequent direction now approves **Phase 1 ingestion expansion, then Phase 2 corroboration after the PRD §5.3.2 gate**. Neither extension is implemented yet. No new paid/live API run.
- Latest and only new Hong Kong run `e2fda30f-36f9-4aa3-83c3-d78b81671b83`: requested 30 documents, 600,000 tokens and 25 minutes; **32 saved versions**, 19 facts, no inference, five unresolved, 13 distinct cited source URLs. Recall 9/18 overall/fetchable and 9/14 regulatory; 21.68 minutes, 372,220 recorded tokens and estimated `$1.8290` from recorded steps. Partial due to a malformed HKMA URL; failed-scout usage may be missing. This is **pre-fix**, not a controlled budget comparison or post-fix gain. Earlier 30-document run cited 7/18 overall and 7/14 regulatory. Human precision is unlabelled.
- [Fresh diagnosis](hk-telemetry-diagnosis.md): URL spaces now encoded; invalid requests fail per document; failed scouts persist partial diagnostics and known usage and charge their completed/failed owned fetches before gap rounds. Reviewed and tested offline. Remaining SFC selection/capacity and source access/storage gaps are disclosed; no second paid run and no corroboration implementation.
- Detailed local reports are ignored by git at `reports/<id>/coverage-comparison.json`, `report-v1.html`, and `precision_worksheet.csv`. Preserve portable summaries in tracked artifacts when needed; do not rely on ignored reports for handoff.
- Portable measured evidence is in [checkpoint.json](checkpoint.json). The historical diagnostic and [telemetry implementation](telemetry-implementation.md) are completed; [coverage-trace.md](coverage-trace.md) preserves the original evidence limits. The updated product snapshot is [PRD v3 draft](../mira_PRD_v3_draft.md). Roadmap documentation PR: https://github.com/Neonat/mira/pull/5. Implementation PR4 and earlier PR3 are merged; check current PR state before assigning new branch work.

## Starting a fresh coordinator

Use this bounded prompt in a new Codex session in this repository:

> Read AGENTS.md, this handover, checkpoint.json and ingestion-corroboration-integration.md. Both authorized phases are implemented and independently reviewed. Runtime source checkpoint is 42efc32, with upstream main16effde preserved. Final tests/eval including local PostgreSQL:459passed+8subtests, none skipped. Do not repeat paid/live runs, change model/source permissions, invent historical bindings or deploy remotely. Existing slides/video remain historical; use the current feature-status note before new claims. Resolve remaining enterprise policy/live measurement/storage gaps through a newly scoped assignment.

The project profiles select models explicitly. See `.codex/agents/`; the coordinator keeps the user's existing model. Profiles follow the [official custom-agent format](https://learn.chatgpt.com/docs/agent-configuration/subagents). They apply to fresh sessions; creating these files does not reset this chat's context or change Mira's API model settings.

## Completed specialist handovers

| Agent/model | Deliverable | State and next step |
|---|---|---|
| coverage_engineer / Terra | [Fresh telemetry diagnosis](hk-telemetry-diagnosis.md), following [telemetry implementation](telemetry-implementation.md) | One paid run complete; URL and failed-scout accounting fixes reviewed. Integrated suite 293 + 8 passed. Next: generic selection/capacity work; post-fix live recall unmeasured. |
| presentation_editor / Luna | [Storytelling deck handoff](../presentation/storytelling-production-handoff.md) | New 16-slide editable deck follows the approved story: ten main slides and six appendices. Annotations absent, diagrams/report crop revised, 16 notes and movie/preview links checked. Local output `reports/presentation-output/storytelling/Mira_DBS_Storytelling.pptx`. |
| demo_engineer / Sol, motion worker / Terra | [Motion showcase handoff](../demo/launch-production-handoff.md), [production checkpoint](../demo/launch/COORDINATOR.md) | Final 180-second HyperFrames/Remotion MP4 exported after user approval. Full decode and five browser playback checks passed. Packaged with the final 16-slide PPTX and relative movie link in `reports/presentation-output/storytelling/Mira_DBS_Presentation_Package.zip`; CRC/hash checks passed. Editable preview remains at `http://localhost:3100/FollowTheEvidence`. Earlier recordings remain unchanged. |

The initial preparation assignments used checkpoint `1c970c8`; the first production pass used `aa05d8d`, with telemetry pushed in `2445846`. This latest pass used `f153e71` and made exactly one paid research run. Read completed handovers before assigning more work; workers are not continuing in the background. Generated deck/video artifacts remain ignored local deliverables, while their reproduction and limitations are tracked here.

## Historical work order and boundaries (superseded by the completed integration above)

1. The integrity fixes are complete. Next implement Phase 1 ingestion expansion/coverage using retained diagnostics and justified Exa/browser paths under PRD §5.3.1, preserving eligible-version filtering and source permissions. No post-fix live recall is measured; further paid/live validation requires new bounded coordinator authorization. MAS is blocked; some industry sources lack storage permission.
2. `evidence_architect` remains read-only design/review until Phase 1 exits under PRD §5.3.2. Then activate the approved Phase 2 corroboration implementation without another feature-approval request. Keep its implementation to assigned corroboration module/schema/design files and coordinate shared contracts/orchestration/migrations with the coordinator. Both new phases are currently unimplemented.
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
