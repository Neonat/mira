# Agent handoffs

This directory coordinates parallel engineering work. It is not a change to Mira's runtime agent architecture. Use a fresh task/fork without chat history; include only the task, ownership boundary, and this checkpoint. Do not ask workers to reread historic chat.

## Full eligible archive experiment — 10 November 2026

The subsequent user request removes the whole-corpus 40-passage fallback while keeping hybrid experimental. Implementation `eb83d0e` indexes bounded batches and ranks the full eligible indexed archive in PostgreSQL. The actual API validation indexed 153/153 saved HK passages, zero pending, with MAS inactive and zero activity;16 requests/29,949 tokens/16.797 seconds. Six frozen questions compare the same corpus/index at equal top10; unlabelled rank changes establish no usefulness winner. Controlled synonym gain, exact-term ties, irrelevant no-answer matches and extra latency are disclosed. Final suite: **997 tests + 8 subtests, none skipped,in 71.56 seconds**. Read [current archive handoff](archive-hybrid.md), [evaluation](archive-hybrid-evaluation.md) and [result](../../eval/evidence/2026-11-10-archive-hybrid-validation.md). Older40-passage profile/measurements below are historical. No role-model/source-grant change, research run, remote deployment or merge. This task's single embedding validation is consumed.

## Hybrid profile enabled and live integration checked — 10 November 2026

The user authorized configuring and testing hybrid retrieval in PR13. Existing local environments now enable `text-embedding-3-small`/384 dimensions with application cache revision `mira-te3-small-384-v1`; template installations remain opt-in. A single controlled actual-API validation passed: two requests, 45 tokens, 3.719 seconds; synonym retrieval, pgvector cache reuse and scout usage/no-duplicate-call checks passed. MAS was inactive and excluded, with no acquisition/provider input. No HK research run, role-model/source-grant change, private Storage upload or remote deployment occurred. Default 40-passage limits and recorded keyword fallback remain. Read the [result](../../eval/evidence/2026-11-10-hybrid-embedding-validation.md) and [hybrid handoff](hybrid-retrieval.md). This embedding validation allowance is consumed; historical research run allowances remain consumed too.

## Durable evidence follow-up

The user approved working on durability/recovery and quality-validation preparation. See the [current handoff](durable-evidence-checkpoint.md) and [operator runbook](../backup-recovery.md). This follow-up preserves PR6 guards, existing source grants, role models and MAS disablement. A subsequently authorized single HK run `1637f9f8` was interrupted before downstream verification/corroboration/report generation: 5/18 acquired versus 6/18 previously; citation metrics unavailable. Saved 153 passages and three unverified findings survived database restart. The stranded run was closed failed, without resuming/replacing it; strict quality export refused missing uninterrupted proof. Read [result](../../eval/evidence/2026-11-08-hk-interrupted-1637f9f8.md). The allowance is consumed. No remote deployment or private Storage upload was performed; no further paid run is authorized.

## Evidence-completeness extension under review

The user approved passage coverage/bounded batch analysis first, then permitted originals/page navigation and opt-in hybrid retrieval. Integration and local validation are recorded in [evidence-completeness](evidence-completeness.md). The normal worker records frozen passage dispositions; optional storage/retrieval remain off by default and need existing source approvals. MAS automation, paid runs, role models and remote deployment were not enabled. This extension is based on PR10; older run results below keep their original scope.

## Current documentation and merged delivery

PR7 and PR9 are merged; current main checkpoint is `95bd1f8`. The root README introduces the implemented prototype to competition judges, DBS stakeholders and pilot auditors, with developer setup below. PRD v3 is the current implementation/pilot reference for the product owner, engineering team and technical reviewers; v2 remains the unchanged requirements baseline until v3 adoption, and v1/proposal text remain historical with dated reader notes. Product users are internal-audit analysts and senior reviewers, supported by curators and administrators. Presentation feature-status notes follow the same evidence cut. The documentation refresh is [PR10](https://github.com/Neonat/mira/pull/10). It changes no runtime, permissions, models, database or slide/video binaries; the previous 560 + 8 test result remains linked to its tested code, rather than represented as a fresh run.

## PR7 merged; auditor-facing source links

The user requested merging PR7 before the source-link fix. PR7 merged at `33b6be6` after documentation-only conflicts with PR8 were reconciled and **538 tests + 8 subtests passed, none skipped (53.81s)**. PR6 guards and PR8 slide binaries/historical precision are preserved. The separate [PR9](https://github.com/Neonat/mira/pull/9) (`codex/auditor-source-links`) maps the four existing SFC JSON-content destinations to browser-verified readable publication pages without changing saved evidence URLs. The user's current local draft has 24 updated links across those four publications; all other content remains unchanged. The follow-up passed **560 tests + 8 subtests, none skipped (54.55s)**, with independent review finding no blockers. Read [source-link handoff](auditor-source-links.md) for exact scope and validation. No paid research, model/permission change or remote migration.

## Latest authorized follow-up: partial improvement, acceptance incomplete

The user explicitly authorized one additional uninterrupted run `7be59cdf` at `c1cf682` (runtime `78c6771`). It reached the 25-minute cap with a partial fallback report: **6/18 acquired versus previous 5/18; citation coverage stayed 5/18**. Actual Exa completed 5/5 requests. Corroboration: **8/12 model calls completed, zero timeouts, four output-limit errors**; five primary-source-only and seven inconclusive assessments, no established independent support. The writer had only 16.35 seconds left and timed out. MAS stayed inactive with zero fetches/versions; browser enabled but never triggered, temporary grant removed. Limits/accounting/evidence-binding checks passed. The unchanged runtime's final suite remains **538 tests + 8 subtests, none skipped**; it was not repeated for this evidence-only update. This additional authorization is now used; no continuation/replacement or further paid run is authorized. Read [latest result](../../eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.md), [portable metadata](../../eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.json) and [coordinator checkpoint](clean-hk-followup.md). PR7 is updated without merge/deployment. The prior clean [5/18 / six-timeout result](../../eval/evidence/2026-11-08-hk-clean-run-7e877c4e.md) remains historical evidence.

## Latest actual Exa API validation and analyst fixes

One new authorized HK run `fe65444d` produced a **resumed partial report** within 24.46 minutes: **5/18 acquired and cited**, versus 7/18 acquired in the previous failed run and 9/18 acquired/cited in the earlier local run. The analyst and all six actual Exa API searches succeeded. Four corroboration assessments were persisted, all inconclusive after call limits; browser fallback was enabled but never triggered. MAS stayed inactive with zero fetches or versions. The same run continued twice after quote-precondition and Python/SQL citation-order defects were fixed, with no repeated initial analysis/acquisition or second run. Final suite: **499 tests + 8 subtests, none skipped**. Migration `20261108110000` is local only; no historical rewrite, model change, remote deployment or coverage-improvement claim. Read [results and limits](../../eval/evidence/2026-11-08-hk-exa-run-fe65444d.md) and the [fix handover](analyst-terminal-errors.md).

## Latest bounded Hong Kong research validation

One user-authorized run at `ef58c47` finished **failed at analysis** after 8.41 minutes: 30 complete HTTP acquisitions, acquired benchmark coverage **7/18 versus earlier local 9/18**; no report, browser attempts or corroboration assessments. Exa plugin relay enabled, but only one of six requested searches returned in time (three actual connector calls). MAS stayed inactive with zero fetches/versions, and the temporary HKMA browser grant was removed. Unknown failed-call usage is reserved, not measured. This does not validate all-three end-to-end behavior or a coverage improvement. Read [result and limits](../../eval/evidence/2026-11-08-hk-bounded-run-a88dd20e.md). No runtime code, PR6 behavior, models, slides or historical reports changed; no replacement paid run.

## Latest PR7 follow-up: actual live browser

`0f9526d` adds real Chromium navigation/JavaScript and permitted read-only actions, with explicit global/source approvals and frozen browser context. **487tests +8subtests passed, none skipped**, including real Chromium fixtures, local PostgreSQL and PR6 regressions. One HKMA public-page capture succeeded in24.91s (20,084characters,128links); two denied optional resources mean partial capture. Earlier60s timeout is preserved with unknown-stage caveat. MAS remains disabled by explicit user instruction; no source grants were persisted, model settings changed or paid/model calls made. Read [live-browser integration](live-browser-integration.md) and [portable HKMA evidence](hkma-live-browser-validation.json). PR7 is updated, not merged/deployed.

## Current ingestion/corroboration implementation

The active branch is `codex/ingestion-corroboration`. Phase 1 exited at `83c84c1` with independent review and **378 tests plus 8 subtests, none skipped**, including local PostgreSQL. Phase 2 implements saved-first corroboration, bounded optional targeted acquisition, exact proposition/origin decisions and immutable reviewed results. Read [ingestion expansion](ingestion-expansion.md), [measurement](ingestion-measurement.md), [corroboration](corroboration.md) and [bounded acquisition](corroboration-acquisition.md) for current scoped ownership and evidence. The coordinator's final integration handoff/checkpoint supersedes the historical work order below.

PR4 and subsequent PR5/PR6 are merged; current upstream `16effde` is integrated, preserving their guardrails and documentation. Final integration at `42efc32` passed **459 tests plus 8 subtests, none skipped**, including local PostgreSQL and offline evaluation. See [integration handoff](ingestion-corroboration-integration.md); [PR7](https://github.com/Neonat/mira/pull/7) is open against `main` after PR4/5/6 merged. No paid/live research/model calls or remote migrations are authorized by these changes. D7 defaults are explicit in PRD §6; enterprise policy adoption, original capture retention and durable artifact storage remain open. Existing slides/video keep their historical evidence cut. PR8 links a separate upstream HK precision worksheet, with one labeller and a model-provenance mismatch; it is not post-feature precision evidence.

## Current checkpoint

- Integration branch: `codex/ingestion-corroboration`, incorporating `main` at `ff3a70f` (8 November 2026). PR4, PR5, PR6 and PR8 are merged upstream; PR7 contains the current implementation. Origin: `https://github.com/Neonat/mira.git`.
- Preserved PR6 runtime checkpoint: guardrail/budget/seeding commit `9e4c3c8` (PR6). Every number in a quote must appear in the matched passage; the code-only completeness check runs even after the token budget is spent; scouts estimate each link-selection call and skip a round that would leave too little for their own summary call, and open each assigned checklist category's index page in turn within half the page allowance. Ten new regression tests. Offline suite on `main` (`pytest tests eval`, same code as `9e4c3c8`): **297 passed, 67 skipped, 8 subtests**; the 67 database tests need migration `20261107180000` applied locally before they can be rerun. No paid run; post-fix live recall is unmeasured.
- Preserved historical precision evidence: HK run `29a153bb` ([evidence](../../eval/evidence/2026-11-07-hk-run-29a153bb.md)), Haiku models on pre-PR4 code `83e3b32`. Recall **11/18** overall and **11/14** regulatory (11 of the 13 reachable items). First human-labelled precision: 21 claims, none unsupported or contradicted; **7/21** fully supported on passage text, **17/21** counting recorded publication dates. Below the proposed ≥95%. Four overstatements of hedges, scope or attribution passed Gate 2. One labeller only. Stored `model_settings` (Opus/Sonnet) does not match the recorded Haiku steps; fix before comparing runs.
- Latest evidence-integrity assignment base: `ad79028f650cc4e8632fc94344c72e0ed332a47a`. Implementation commit: `27c28fac8631c9afdb8cdef60ab6b48b526ef5a7`, pushed in follow-up PR4. Separate report-layout commit `53b88fb` arrived during integration and is preserved. Resolve `git log -1 -- docs/agent-handoffs/evidence-integrity-fix.md` for this source checkpoint.
- Earlier runtime checkpoint: `1c970c825565430ae7a36e736f6880da9371edcd`; URL/failure-accounting/demo work followed base `f153e716fa2587755b255068b9ef6e13e9f6a4fe`.
- Pre-checkpoint source baseline: `1d38e8916120d45d063d5157abcac6fc2db1af6f`, retained for historical comparisons. The coordinator supplies the current `git rev-parse HEAD` for each new assignment.
- Latest evidence-integrity verification: **350 tests plus 8 subtests**, none skipped, including local Postgres at `localhost:55432` and offline evaluation. This full suite ran in an isolated checkout excluding concurrent report-layout work; **26 focused renderer/layout checks** then passed with `53b88fb` integrated. Earlier checkpoints were 280, 285 and 293 tests. Migrations through `20261107180000` are local only; no remote deployment.
- [Evidence-integrity checkpoint](evidence-integrity-fix.md): contract-1.4 reviewed snapshots freeze complete evidence, verification provenance and reviewer inputs; incomplete reviewed renders fail closed; retrieval selects current eligible saved versions before ranking/limits. Legacy artifact files remain unchanged, legacy snapshots refuse regeneration, and no historic verification inputs are backfilled. Its deferral records that completed task's scope; the user's subsequent direction now approves **Phase 1 ingestion expansion, then Phase 2 corroboration after the PRD §5.3.2 gate**. Neither extension is implemented yet. No new paid/live API run.
- Earlier Hong Kong telemetry run `e2fda30f-36f9-4aa3-83c3-d78b81671b83`: requested 30 documents, 600,000 tokens and 25 minutes; **32 saved versions**, 19 facts, no inference, five unresolved, 13 distinct cited source URLs. Recall 9/18 overall/fetchable and 9/14 regulatory; 21.68 minutes, 372,220 recorded tokens and estimated `$1.8290` from recorded steps. Partial due to a malformed HKMA URL; failed-scout usage may be missing. This is **pre-fix**, not a controlled budget comparison or post-fix gain. Earlier 30-document run cited 7/18 overall and 7/14 regulatory. This run's precision is unlabelled.
- [Fresh diagnosis](hk-telemetry-diagnosis.md): URL spaces now encoded; invalid requests fail per document; failed scouts persist partial diagnostics and known usage and charge their completed/failed owned fetches before gap rounds. Reviewed and tested offline. Remaining SFC selection/capacity and source access/storage gaps are disclosed; no second paid run and no corroboration implementation.
- Detailed local reports are ignored by git at `reports/<id>/coverage-comparison.json`, `report-v1.html`, and `precision_worksheet.csv`. Preserve portable summaries in tracked artifacts when needed; do not rely on ignored reports for handoff.
- Portable measured evidence is in [checkpoint.json](checkpoint.json). The historical diagnostic and [telemetry implementation](telemetry-implementation.md) are completed; [coverage-trace.md](coverage-trace.md) preserves the original evidence limits. The updated product snapshot is [PRD v3 draft](../mira_PRD_v3_draft.md). PR3 to PR6 are merged into `main`; no PR is open. Check current PR state before assigning new branch work.

## Starting a fresh coordinator

Use this bounded prompt in a new Codex session in this repository:

> Read AGENTS.md, this handover, checkpoint.json, clean-hk-followup.md, ingestion-corroboration-integration.md and the historical eval/evidence/2026-11-07-hk-run-29a153bb.md. Use current `git rev-parse HEAD` as the assignment base. Ingestion and corroboration are implemented and reviewed; the latest authorized run 7be59cdf has partial acceptance (6/18 acquired, 5/18 cited; 8/12 corroboration calls completed, four output limits). Preserve PR6 guardrails, PR8 slides/historical precision and frozen evidence. No paid/live run, model/source-permission change, historical backfill or remote migration is authorized. Read the latest integration verification before assigning further work.


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
