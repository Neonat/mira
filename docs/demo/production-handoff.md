# Demo production handoff

Status: **saved-report capture complete; authenticated synthetic review/signoff now complete in the separate [authenticated handoff](authenticated-review-handoff.md)**. Base SHA: `aa05d8d0a535212e56e3009a45ccec6875598507`. Capture date: 7 November 2026. Objective: turn the existing script into an observed local rehearsal and playable asset, with no new research.

Owned: this file and `reports/demo-output/current/`. Runtime, configuration, historical report, evaluation truth, PRD, slide files and other workers' files were read-only. No commit/push, migrations, source-permission changes, worker, new research, review writes or auth-account creation.

## Deliverables

- `reports/demo-output/current/mira-partial-demo.mp4`: 180 seconds, 1440×1080, 24 fps, H.264/yuv420p, silent. Ten real screenshots/document renders held for 18 seconds each, with editorial captions. This is a screenshot walkthrough, not a recording of a completed authenticated user journey.
- `reports/demo-output/current/thumbnail.png`: report scope with saved-playback labeling.
- Same folder: `storyboard.json` (exact timing/copy), `observations.json` (source response and screens), `playback-check.json`, raw screenshots, `frame-01.png` through `frame-10.png`, cited public PDF/page, `capture.cjs`, `build.py`, and `frames.txt`.
- Outputs are ignored by git under `reports/`; copy them explicitly for any later delivery. No upload or publication occurred.

## Setup and exact reproduction

Read `AGENTS.md`, `docs/agent-handoffs/README.md`, `checkpoint.json`, `docs/demo/e2e-demo-script.md`, app sign-in/brief/run labels and relevant README sections. Applied the PixVerse local video-editing skill; its local wrapper help works. No PixVerse generation/account call was needed.

Initial safe inspection found local Supabase URL `127.0.0.1:55421`, configured anon key, no configured demo email/password, and no listeners on 8501/55421/55423/55432. Values of keys/passwords were never printed. Start only the UI:

```sh
.venv/bin/streamlit run app/streamlit_app.py --server.headless true --server.address 127.0.0.1 --server.port 8501
```

Streamlit required sandbox approval to bind the local socket. It loaded the actual sign-in screen. No form submission was made. The coordinator subsequently restored the existing local DB/Auth/REST/Kong containers; the capture did not retest credentials or extend into an auth fixture. At handoff the UI remains available at `http://127.0.0.1:8501`; worker was never started. Original UI process session: `77712`.

Capture reads the original saved HTML directly:
`reports/2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0/report-v1.html`.
The script uses installed Playwright at `/Users/natsim/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`, headless Chromium, 1440×900 viewport. It redacts visible UUID text and hides the Run metadata row in the capture DOM only; the original HTML is unchanged. It clicks the actual first citation anchor, then separately retrieves that entry's public PDF via HTTP. This is **not** a recorded external browser-tab click.

```sh
node reports/demo-output/current/capture.cjs
```

The public source is [HKMA Supporting Artificial Intelligence Adoption in AML/CFT](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20251118-3-EN/20251118-3-EN.pdf). HTTP 200 and `application/pdf` were observed. `sips -s format png … --out /tmp/mira-source-page.png` rendered its first page. `pdftoppm` emitted a fontconfig warning during the first pass; system `sips` was used for the final page render. The build composites PDF transparency onto white.

```sh
sips -s format png reports/demo-output/current/cited-publication.pdf --out /tmp/mira-source-page.png
.venv/bin/python reports/demo-output/current/build.py
```

Build uses Pillow, Arial fonts in `/System/Library/Fonts/Supplemental/`, and `/Applications/AdaL.app/Contents/Resources/bin/ffmpeg` plus `ffprobe`; no installation required. Machine-specific paths are preserved in the local scripts. Captions are editorial text, not speech transcription. No audio track was added.

## Expected versus observed

| Step | Expected from proposed script | Observed |
| --- | --- | --- |
| Sign in | Authorized user enters workspace | Actual empty sign-in screen loads. No demo credentials available at initial inspection; no login attempted. |
| Brief / run history | Scope form, plan, steps, usage | Unrehearsed because capture stayed outside authenticated screens. No new run queued. |
| Saved report | Open draft, inspect facts/inference | Actual HTML opens: Draft (partial run), not reviewed; HK period 2025-11-04–2026-11-04; Fact and Inference tags visible. |
| Citation | Follow report source | First internal citation navigates to evidence entry [1]; its exact public HKMA PDF returns 200 and is shown as a rendered document page. Appendix shows passage references, not the quoted text itself. |
| Coverage | Visible gaps and limits | Actual table includes unconfirmed coverage, manual import needed, relevant material found and checked/no change. Long URLs squeeze narrow item/outcome columns into awkward word wrapping at 1440px; preserved as observed, runtime not edited. |
| Empty sections | Truthful scope display | Jurisdiction comparison and supervisory trends sections say “No verified items.” Industry section has actual HKMA findings. |
| Review / sign-off | Amend, reject, dependent re-review, new reviewed artifact | Not rehearsed. No decisions written and no reviewed artifact generated. Do not present this asset as proof of these behaviors. |

Burned captions disclose saved playback, partial status, 15.29-minute processing omitted, exhausted document allowance, unlabelled human precision, future independent-source corroboration and outstanding review flow. Checkpoint-attributed counts are 17 facts / 1 inference / 1 unresolved, 10 primary publications, recall 7/18 overall and 7/14 regulatory. They are not a fresh measurement or equal-budget comparison.

## Verification and next step

`ffprobe` confirms duration 180.000 seconds, H.264, 1440×1080, 24/1 fps and yuv420p. All ten storyboard frames were generated from actual capture inputs; visual inspection covered sign-in, report scope, citation appendix/redaction, inference, source document and coverage layout. Full FFmpeg decoding completed with no errors. Chromium played the MP4 and sought to 90 seconds: duration 180, readyState 4, error null (`browser-playback-check.json`). Decoder/playback checks are saved alongside the asset. No project test suite was run for this documentation/media-only task.

Remaining gaps: authenticated brief/history, actual quote/check UI, real reviewer decisions/dependency gates and separate reviewed-artifact acceptance. The coordinator authorized a disposable local fixture after restoring services, but this first pass completed the unaffected partial capture instead. Exact next step: a separate bounded rehearsal creates an ephemeral local account and disposable public-evidence fixture, exercises review/sign-off without starting the general worker, and appends clearly labeled fixture footage only after the reviewed body/summary acceptance checks pass. Historical measured run remains read-only.


## Authenticated follow-up completed

The separate 204-second captioned MP4 is `reports/demo-output/authenticated/mira-authenticated-review.mp4` with `thumbnail.png`. Real local Auth/RLS, evidence inspection, supporting-fact amendment, stale-dependency guard, fresh inference review, needs-evidence guard, rejection, signoff and separate reviewed rendering passed. Ten artifact checks and full decode/browser playback passed. The fixture is synthetic and separate from the historical HK measured run. See [exact setup, observed flow and artifact hashes](authenticated-review-handoff.md). This follow-up supersedes the outstanding authenticated steps above; the prior partial video and its historical capture account remain unchanged.
