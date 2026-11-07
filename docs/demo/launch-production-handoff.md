# Follow the evidence · showcase handoff

Status: **approved final MP4 exported and verified; editable preview retained**. Objective: assemble approved product/e2e film using authentic saved research and a separate disclosed synthetic workflow/review. Base SHA: `f7f2745`. No commits or pushes.

Owned: `docs/demo/launch/remotion/**`, this handoff and `reports/demo-output/launch/**` except `motion/**`. Read-only: runtime, model configuration, PRD/evaluation, historical reports and captures, coordinator HyperFrames source/manifest/motion assets, other workers’ files. No runtime code change, paid call, general research worker, migration, reset or historical workspace mutation.

## Preview and source

- Working URL: **http://localhost:3100/FollowTheEvidence**. Studio process session `60468`; keep alive for review. Composition `FollowTheEvidence`, exactly **5,400 frames / 180 seconds / 1920×1080 / 30 fps**.
- Editable project: `docs/demo/launch/remotion/`; main `src/Root.tsx`, independently authored `Workflow.tsx`, `SavedResearch.tsx`, `Review.tsx`, `Artifacts.tsx`, manifest adapter `Motion.tsx` and shared screenshot crop `Screen.tsx`.
- Connected compositions: `SyntheticWorkflow`, `SavedHKResearch`, `SyntheticReview`, `ReviewedArtifacts`.
- Coordinator motion imports: actual `opening.mp4` 32 seconds, `agents.mp4` 20 seconds, `ending.mp4` 10 seconds from manifest paths. All three available; no labelled motion placeholder remains in the current preview.
- Ignored media under project `public/`, with source/hash ledger `public/asset-ledger.json`. Originals and source captures preserved under ignored `reports/`.
- Final MP4: `reports/demo-output/launch/Mira_Follow_the_Evidence.mp4`, exported after the user explicitly instructed “Export the final MP4”. Root owns packaging/copying beside the deck.

## Exact setup and commands

Remotion create/markup/video-editing skills plus local video-editing/media guidance used. Scaffolded with `npm_config_cache=/tmp/mira-video-npm-cache npx create-video@latest --yes --blank --no-tailwind docs/demo/launch/remotion`; installed `@remotion/media@4.0.541`. Registry scaffold resolved Remotion 4.0.541 and React 19.3.1. Dependencies/package lock retained; no global settings changed. Installer reported ten moderate dependency advisories; automatic major upgrades were not applied during media production.

From `docs/demo/launch/remotion/`:

```sh
npm_config_cache=/tmp/mira-video-npm-cache npm ci
python3 scripts/prepare-assets.py
python3 scripts/audio.py
npm run dev -- --no-open --port 3100
npm run lint
node scripts/qa.cjs
```

Studio was started and its scaffold preview verified **before** authoring. This worker’s IAB tool initially reported unavailable, so approved Playwright verification was used; coordinator subsequently opened the same URL successfully in IAB. `prepare-assets.py` consumes the read-only manifest’s root-relative render paths and makes local copies. For another machine, provide retained ignored source media and set `CHROME_PATH` for QA if the documented local Playwright installation is absent.

Original audio is generated locally by deterministic arithmetic in `scripts/audio.py`: sparse 105 BPM A-minor/F/C/G instrumental plus a short action tone, no voiceover. No samples, hosted model, media account or billing. These original audio outputs are released CC0 1.0 by this production; no external attribution required. Instrumental WAV is exactly 180 seconds / 22,050 Hz mono. FFmpeg volume check: mean −30.9 dBFS, peak −20.8 dBFS before the composition’s 0.55 gain. It is intentionally quiet; audible mix approval remains with preview review.

## One isolated continuity rehearsal

Existing local DB/Auth were reused at 55432/55421. Existing synthetic account credentials stayed in `/tmp/mira-review-credentials.json`, mode 0600; their values were never printed or placed in sources/assets. The existing synthetic account received membership only in a **new** workspace. No historical workspace was reseeded.

New workspace `c767aea1-5eb2-403a-aaa7-a2bcdb7f6e06`, slug `launch-79141ead7b`. Exactly one real UI-created run: `84dd4835-2d4b-4d04-82a5-ce2535a198a3`, final status `draft`. Metadata `reports/demo-output/launch/fixture.json` records the boundary. Account is synthetic `example.test`; assembled UI crops exclude sidebar account details and internal table IDs.

App command, process session `23401`:

```sh
MIRA_WORKSPACE_SLUG=launch-79141ead7b .venv/bin/streamlit run app/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8503
```

Executed from repository root: `.venv/bin/python docs/demo/launch/remotion/scripts/fixture.py setup`, then `node docs/demo/launch/remotion/scripts/capture-workflow.cjs`. The script signs in, removes SG from the real multiselect, captures the actual brief, clicks Queue run **once**, invokes bounded planner setup only for that run, displays actual conditional approval, clicks Approve plan and resumes only this run through ScriptedClient/FakeWeb. Optional approval was explicitly configured on this new fixture run by coordinator authorization; the current New brief form defaults to skipping approval and offers no toggle. This distinction is persistent on screen.

The first capture stopped on a duplicate “Runs” text locator **after** queue/planning; fixed locator and `RESUME_CAPTURE=1` resumed the same run, with no second Queue click or new run. After the run completed, a browser reload returned to New brief so the expected Runs button timed out; a separate read-only sign-in/navigation captured the completed status. Both raw takes remain preserved. Metadata and runner output confirm the same run finished `draft`; no general worker was launched. The parser’s `EOF marker not found` warning from the intentional broken-PDF fixture is retained in the local result log; it did not prevent completion.

Fixture code lives in `scripts/fixture.py`; production runtime remains unchanged. `setup` refuses existing metadata; the capture refuses another Queue run after metadata has a run. Treat this as rehearsal provenance, not a command to repeat against the completed fixture.

## Steps: expected versus observed

| Film step | Expected | Observed / asset |
| --- | --- | --- |
| 32–38 brief | Actual controlled scope and budget form | Captured `workflow-brief.png`; new synthetic HK-only brief queued once. |
| 38–46 plan / approval | Wait before fetching, real authenticated approval | Captured `workflow-plan.png` and `workflow-approved.png`; optional fixture configuration disclosed; before/after holds preserve the actual action. |
| 46–52 progress | Actual persisted concurrent scout steps | `workflow-progress.png` shows regulatory and industry scouts running. Processing/navigation omitted, persistent synthetic label. |
| 72–88 saved HK | Real historical report, original PEP finding/date/citation | Original `reports/2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0/report-v1.html`; exact PEP finding captured `pep-finding.png`, `#e15` click captured `pep-citation.png` (raw provenance capture only; internal IDs are not shown in assembly). |
| 88–99 original source | Preserve guidance qualification | Root supplied authentic HKMA public PDF/page2; assembly shows only its first line, including “expected to consider adopting”. Source URL below. |
| 99–108 visible gap | Partial result retains limits | Existing authentic `current/07-coverage-gaps.png`; historical partial draft and omitted 15.29-minute processing disclosed. This is the earlier saved run, not the latest 9/18 measurement. |
| 108–152 review | Evidence/checks, amendment, stale review, needs evidence, rejection/signoff | Existing uncaptioned browser WebM plus actual evidence/guard/fresh-review screenshots; no new writes to old review workspace. Stills explicitly disclosed as reading holds. Actual signed status precedes separate rendering; original UI’s temporarily unavailable artifact message is preserved. |
| 152–170 artifacts | Original unchanged; reviewed amendment/exclusions | Existing actual original/reviewed HTML captures and prior ten artifact checks reused. Crop enlarges original supporting finding versus applied reviewer amendment. |
| Motion 0–32 / 52–72 / 170–180 | Coordinator source clips at manifest boundaries | Actual 32/20/10 second clips imported. Boundary and final-frame stills confirm no blank transition. |

Authentic source: `https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260827-4-EN/20260827-4-EN.pdf`, letter dated **28 August 2026**, page 2. Root supplied `reports/demo-output/launch/motion/pep-source-page-2.png`; raw PDF remains in coordinator-owned HyperFrames assets. Saved report source title/date and URL agree. The first-line excerpt is a short source crop, not an invented product screen.

Synthetic review source remains `authenticated/raw/page@bb202f021ab21334ab86fca9ca3f68d6.webm` with original source intervals declared in JSX. Original/reviewed artifacts belong to the earlier synthetic run `c8ec933f-36fa-44f1-8ce8-f77387812276`; they are **not** the new continuity run or historical HK report. The film persistently labels each chapter so these cannot be mistaken for one generated-and-signed research result. No corroboration or live accuracy/coverage improvement claim is added.

## Checks, evidence and limits

`npm run lint` (ESLint and TypeScript) passed. Manifest/media preparation reports 25 copied assets and no missing files. Still QA metadata confirms 5,400 frames, 30 fps, 1920×1080; exact chapter boundaries, hero frames and frame 5399 render successfully. Studio load reports no page errors; Play changes to Pause and plays the real motion preview. `qa/studio-playback.json` and `studio-playing.png` retain playback evidence. This is interactive-preview verification, not final-MP4 decode QA.

QA folder: `reports/demo-output/launch/qa/`. Hero frames: opening `frame-0100.png`; brief `frame-0960.png`; optional plan `frame-1180.png`; agents `frame-1800.png`; saved PEP `frame-2400.png`; original source `frame-2640.png`; review evidence `frame-3310.png`; stale guard `frame-3760.png`; needs-evidence guard `frame-4160.png`; original `frame-4650.png`; reviewed `frame-4890.png`; ending `frame-5300.png`; final `frame-5399.png`. Contact sheet is a convenient overview; inspect full-size heroes for reading detail.

Visual QA tightened the PEP paragraph, original source line, quote/checks and reviewed amendment. Final correction moved the needs-evidence crop down to the actual error and excluded the internal plan identifier from the approved-plan hold. Disclosures remain outside every source crop at 28 px. No passwords, JWTs, API keys or internal personal data appear in the assembled clips. The synthetic `example.test` identity may remain in preserved raw originals but is excluded from assembled sidebar crops; raw login footage must not be shared unreviewed.

Remaining limits: authored preview uses genuine screenshots and selected raw action intervals, with disclosed reading holds; it is an edited demonstration, not real-time processing. Static screenshots enlarge to read and retain their native softness. The instrumental has numerical level checks but needs an audible taste/level check during user preview. No runtime suite was rerun for media-only changes. Existing measured checkpoint remains 293 tests plus 8 subtests; latest pre-fix HK result 9/18, 32 saved versus 30 requested is not represented as a gain. Independent-source corroboration remains deferred.

Coordinator packaging is complete: the final MP4 and final PPTX are together in `reports/presentation-output/storytelling/`, and `Mira_DBS_Presentation_Package.zip` contains both plus extraction/playback instructions. Movie hyperlink is the exact relative filename; copy SHA-256 and ZIP CRC checks passed. Final PPTX reopened in native PowerPoint without repair. Native external-player launch was not exercised; the MP4 passed browser playback. Exact next step: deliver the ZIP and preserve the editable sources/ignored media. Status: **complete for approved preview, export and packaging**.

## Explicitly approved final export

The user explicitly approved **“Export the final MP4”**. The validated composition/assets were reused without a new fixture, research call or preview QA rebuild. The initial render failed before frame 0 when its temporary localhost:3000 server returned no response. A retry with a dedicated local render port and concurrency 2 completed; Studio on 3100 remained intact.

Exact successful render command, from `docs/demo/launch/remotion/`:

```sh
npm_config_cache=/tmp/mira-video-npm-cache npx remotion render src/index.ts FollowTheEvidence /Users/natsim/Documents/dbsearch/reports/demo-output/launch/Mira_Follow_the_Evidence.mp4 --codec=h264 --pixel-format=yuv420p --audio-codec=aac --crf=18 --port=3120 --browser-executable='/Users/natsim/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing' --concurrency=2 --log=error
```

FFprobe found a renderer delivery detail despite the requested CLI pixel format: 180.000-second H.264 video marked `yuvj420p`/full range, with an AAC tail extending the container to 180.011 seconds. The approved picture/timing and audio mix were preserved; local FFmpeg normalized the output to the requested exact format/duration:

```sh
/Applications/AdaL.app/Contents/Resources/bin/ffmpeg -hide_banner -loglevel error -i reports/demo-output/launch/Mira_Follow_the_Evidence.mp4 -map 0:v:0 -map 0:a:0 -vf 'scale=in_range=pc:out_range=tv,format=yuv420p' -color_range tv -c:v libx264 -crf 18 -preset medium -c:a aac -af 'atrim=duration=180' -t 180 -movflags +faststart -y reports/demo-output/launch/Mira_Follow_the_Evidence-normalized.mp4
```

The unchanged Remotion output was renamed `Mira_Follow_the_Evidence-remotion-fullrange.mp4`; the normalized file was promoted to **`Mira_Follow_the_Evidence.mp4`**. Deliver the latter only.

Final file: **7,486,227 bytes**; SHA-256 **`ca759c32dab5dc5523edead03de6d34ec4645f686bae3a70f2467071cd8bd938`**. Format, video and audio durations are all exactly **180.000 seconds**. Video: **H.264 / yuv420p / TV range / 1920×1080 / 30 fps / 5,400 frames**. Audio: **AAC / 48,000 Hz / stereo**.

All final-file checks passed:

- `ffprobe -v error -show_format -show_streams -of json …` → `export-metadata.json`.
- `ffmpeg -v error -i … -f null /dev/null` → `export-decode.log`, empty; exit 0, full video/audio decode.
- `ffmpeg -hide_banner -i … -vn -af volumedetect -f null /dev/null` → `export-audio-level.log`: mean **−36.2 dBFS**, peak **−25.0 dBFS**, no clipping. Quiet approved mix retained.
- `node reports/demo-output/launch/export-playback-check.cjs` → `export-playback-check.json`: real Chromium play/seek at **0, 45, 90, 135 and 179 seconds**, readyState 4 throughout, no media/page errors, duration 180, 1920×1080. Screenshot `qa/export-playback-final.png` retained.
- `export-verification.json` summarizes final metadata/hash/results. No subjective listening was performed: no audible inspection tool was available in this session. Numerical levels and actual browser playback are verified; taste/volume judgement is not claimed.

No deck files were edited or copied by this worker. Coordinator owns packaging and final deck-link validation. All disclosures, chapter timing and deferred-corroboration limits remain as approved. Export status: **complete**.
