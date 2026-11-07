# Authenticated review rehearsal

Status: **complete for the local synthetic review/signoff flow**. Objective: finish the missing authenticated review segment and deliver playable evidence. Base SHA: `f153e716fa2587755b255068b9ef6e13e9f6a4fe`; rehearsal date: 7 November 2026.

Owned: this handoff, the demo script/production handoff updates, and ignored `reports/demo-output/authenticated/`. Runtime, configuration, PRD, evaluation, historical measured reports and other workers' files remained read-only. The coordinator supplied the UI workspace-setting fix. No commit, push, migration, reset, remote write, paid model call or general worker launch occurred.

## Deliverables

- `reports/demo-output/authenticated/mira-authenticated-review.mp4`: 204 seconds (3:24), 1440×1080, 24 fps, H.264/yuv420p, captioned and silent. Actual Playwright browser action footage plus clearly disclosed still reading holds for guard errors and artifact comparison. Login and decisions use the actual app, Supabase Auth JWT and RLS. Synthetic fixture labels appear throughout.
- `reports/demo-output/authenticated/thumbnail.png`.
- Evidence: `acceptance.json` (ten checks), `artifact-browser-check.json`, `capture-events.json`, `cut-list.json`, `media-check.json`, `decode-check.json`, `browser-playback-check.json`, screenshots `01-` through `18-`, and raw WebM inputs.
- Reproduction sources: `bootstrap-fixture.py`, `new-fixture-run.py`, `capture.cjs`, `capture-artifacts.cjs`, `render-review.py`, `build.py`, `playback-check.cjs`, caption PNGs and `segments.txt`. These are local ignored deliverables, not distributed credentials.
- Prior `reports/demo-output/current/mira-partial-demo.mp4` remains unchanged and separate: it shows historical saved HK partial-report playback. The new fixture is not that measured run. No historical report was reviewed or amended.

## Setup and scope

Read `AGENTS.md`, handoff README/checkpoint, prior demo handoff/script, app review flow, `mira/render_job.py`, `mira/config.py`, and scripted helpers in `tests/test_pipeline_db.py`. Applied PixVerse local video editing after its managed `pvx --help` worked; used installed Playwright/Chromium and FFmpeg. No generation service was called.

Local restored services: PostgreSQL `127.0.0.1:55432`; Supabase Auth/REST/Kong `127.0.0.1:55421`. The explicitly authorized disposable verified Auth account uses an `example.test` email and admin membership only in the new fixture workspace. Local admin JWT and password were held in memory; the browser password file is `/tmp/mira-review-credentials.json`, mode 0600, outside assets. No real personal email, API key, service key or password appears in outputs.

Workspace: `96db74e0-7584-47d6-8803-15ec906bb4b1`, slug `review-d98cd3bb53`. Final fixture run: `c8ec933f-36fa-44f1-8ce8-f77387812276`. An earlier fixture attempt `d053a51f-eab9-4e63-abf5-264b2e16458a` is preserved, including three initial reviews; it is not used as final acceptance. Its verifier response queue had one unresolved inference. The corrected **new run only** used fact-first verifier responses; existing workspace was not reseeded. Automatic approval review initially rejected the correction as suspected reseeding; after displaying the narrowed script with no seed/account/membership changes, the correction was approved and executed.

The app originally hardcoded workspace slug `mira`, preventing an isolated fixture rehearsal. Reported to coordinator; coordinator added `MIRA_WORKSPACE_SLUG` selection while preserving Auth/RLS. Demo service command used during capture (the process stopped at the later interruption; restart for interactive inspection):

```sh
MIRA_WORKSPACE_SLUG=review-d98cd3bb53 .venv/bin/streamlit run app/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8502
```

The fixture uses `ScriptedClient`, `FakeWeb`, real Orchestrator/evidence/verifier/storage/render code and copied test helper callbacks. FakeWeb never fetches a network publication. It supplies a synthetic HKMA `TEST-1` HTML document and an intentional broken-PDF extraction case; missing coverage remains visible. This demonstrates review mechanics, not publication recall, factual accuracy or independent corroboration.

## Exact steps and observations

| Step | Expected | Observed |
| --- | --- | --- |
| Login | Real local verified account enters isolated workspace | Passed; actual form/password authentication, admin role, new brief and run history visible. No Queue run click. |
| Open report findings | Four retained findings, source quote and checks | Passed: two facts, two inferences; quote match and scripted verification checks visible. |
| Initial decisions | Accept all four retained findings | Passed through Save review in the real UI. |
| Amend supporting fact | Save narrowed human text after its inference was reviewed | Passed; amendment visible. No model reverification was claimed. |
| Attempt signoff | Stale dependent inference blocks | Actual UI error: `review the dependent inference again after amending its supporting finding` (23514). |
| Fresh inference review | Later decision clears stale dependency | Passed; saved accepted with note after amendment. |
| Needs evidence | Retained finding blocks signoff | Passed; actual UI error: `report cannot be signed off: finding needs evidence` (23514). |
| Reject separate fact | Remove it and dependent inference | Passed; reviewed snapshot and rendered summary/body exclude both. |
| Sign off | Insert separate frozen reviewed snapshot | Passed; signed status/version 2 visible. |
| Render | Explicit job only for fixture workspace | `render_pending(conn, UUID(workspace), Path('reports'))`; separate reviewed HTML created. No research worker started. |
| Open both artifacts | Original unchanged; reviewed amended/excluded/reviewer/date | Passed in real Chromium file views and ten artifact checks. |
| Citation | Internal citation reaches intended saved evidence | `#e1` reached. TEST-1 source is explicitly synthetic and was not fetched externally. Earlier separate saved-report demo covers the real public HKMA PDF. |

Original: `reports/c8ec933f-36fa-44f1-8ce8-f77387812276/report-v1.html`.
Reviewed: `reports/c8ec933f-36fa-44f1-8ce8-f77387812276/report-v2-reviewed.html`.
Original SHA-256 before **and** after: `d5021643bdfa59c5c8e730baf765a8a8882580ee51a87d739ff8e963225e4a6c`.

`acceptance.json` confirms separate artifact, unchanged original hash, visible amendment, amendment in rendered body and summary, frozen outcomes, reviewer/date, and absence of rejected fact/dependency from retained snapshot and rendered body. Summary has two retained findings; the report's coverage “4 claims verified” is pre-review verification telemetry, not the count retained after review.

## Reproduction and media verification

From repository root, with the existing local services and `.env` anon key available:

1. For a fresh disposable workspace/account, execute `reports/demo-output/authenticated/bootstrap-fixture.py` with `.venv/bin/python`; it provisions only local Auth and seeds only the newly created workspace. It writes mode-0600 credentials under `/tmp` and metadata under the assigned ignored output folder. To add a fresh synthetic run to an already provisioned demo workspace without reseeding, use `new-fixture-run.py` instead. These write real disposable review/evidence records; never target historical measured workspaces.
2. Start isolated UI with the generated workspace slug, as above. Run `node reports/demo-output/authenticated/capture.cjs` for one unreviewed fixture. This records login, evidence, initial decisions, amendment, both error guards, rejection and signoff. Do not rerun it against an already signed report.
3. Run `.venv/bin/python reports/demo-output/authenticated/render-review.py`; it renders only the metadata workspace and verifies the original/reviewed artifacts. Run `node reports/demo-output/authenticated/capture-artifacts.cjs` to open and capture those exact files and the signed UI. UUID redaction changes capture DOM only.
4. `build.py` preserves exact current source intervals and captions in `cut-list.json`. Run with `.venv/bin/python`; for a new browser take, update source intervals from its capture events before building. Final timeline omits a brief report-tab navigation transition and the explicit render job's processing/wait. Still reading holds are disclosed. No claim of real-time research processing is made.
5. Run `node reports/demo-output/authenticated/playback-check.cjs`. Final FFprobe: 204.000 seconds, H.264, 1440×1080, 24/1, yuv420p. Full FFmpeg decode passed. Chromium play/seek checks at 0, 45, 105, 150 and 195 seconds passed with no media error. Visual checks covered stale guard, reviewed summary/body, redacted provenance and caption/thumbnail legibility. No project-wide test run was needed for documentation/media; coordinator owns runtime regression tests.

Remaining limits: this is a local synthetic review demonstration with captioned silent footage and still artifact comparison, not a new research validation or narration recording. Original saved HK research playback stays separate and partial. Independent-source corroboration remains future work. The local disposable account/workspace is preserved; use the command above to reopen the UI. The coordinator restarted the existing local database/Auth containers without reset after the interruption and passed 293 tests plus 8 subtests. Remove only explicitly identified demo resources if cleanup is later requested. There are no remaining blockers for this assigned review/signoff capture.

Exact next step: coordinator reviews the MP4/thumbnail and handoff, integrates the owned documentation plus its workspace configuration fix, and packages ignored local media explicitly if sharing. Status: complete.
