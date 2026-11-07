# Mira storytelling production implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkboxes for tracking. User has approved design and immediate parallel production; no further plan approval is needed.

**Goal:** Deliver the approved storytelling deck and an editable motion-led product/demo preview.
**Architecture:** Reuse the existing deck and evidence. Coordinator supplies HyperFrames motion sequences; demo worker assembles them with actual recordings in Remotion; presentation worker produces the separate deck. All write paths are disjoint in the existing `codex/nat-ingestion` checkout.
**Tech stack:** Bundled Artifact Tool, HyperFrames HTML/GSAP, Remotion React, Playwright, FFmpeg.
**Spec:** `docs/superpowers/specs/2026-11-07-mira-storytelling-design.md` (approved).

## Global constraints

- Deck: 16:9, ten main slides plus six appendices in the approved order; source palette/font; editable diagrams/tables.
- Film: nominally 180 seconds at 1920 × 1080 and 30 fps; only ±10 seconds for readability.
- White/charcoal/red `#FFFFFF`, `#222222`, `#60646B`, `#E60028`; no voiceover by default; free licensed/local sound.
- Authentic saved HK research and synthetic workflow/review are separate labelled chapters; time omissions disclosed.
- No paid research/media, runtime changes, model changes, historical mutations or expanded permissions. Corroboration deferred.
- No worker commits/pushes or delegates; coordinator integrates. Original deliverables unchanged. No credentials in captures/Git.

## Review focus

1. Burned-in image annotations survive XML cleanup: inspect every slide and relevant image.
2. Cropping hides synthetic/time disclosures or makes UI unreadable: check final 1080p hero frames.
3. A missing motion asset silently becomes a blank sequence: require manifest paths, duration and visible preview checks.
4. A seamless edit implies the real HK report passed synthetic sign-off: persistent chapter labels and copy review.
5. Roadmap wording implies DBS approval/deployment or measured accuracy: check all main slides and notes.

## Task 1: Storytelling deck — presentation worker

Owned: `docs/presentation/storytelling-outline.md`, `docs/presentation/storytelling-production-handoff.md`, `reports/presentation-output/storytelling/**`.
Read-only: approved spec, existing deck, PRD/checkpoint, existing reports and demo captures.

- [x] Read presentation skill, inspect existing deck, choose supported import/session route or documented local fallback.
- [x] Produce exactly the approved 16-slide content and hierarchy, preserving editable source layouts where useful.
- [x] Remove visible annotations, update factual metrics and current local rehearsal status.
- [x] Add video slide using portable relative link `Mira_Follow_the_Evidence.mp4` and a standalone-video fallback note. Do not invent an existing MP4; coordinator supplies exported video later.
- [x] Render all slides, inspect annotation/text-fit and main narrative; correct issues.
- [x] Return editable deck/preview, QA evidence and concise handoff. Main expected file `reports/presentation-output/storytelling/Mira_DBS_Storytelling.pptx` if local delivery is required.

## Task 2: HyperFrames motion — coordinator

Owned: `docs/demo/launch/hyperframes/**`, `docs/demo/launch/motion-manifest.json`; generated `reports/demo-output/launch/motion/**`.

- [x] Inspect CLI/runtime and registry, define DESIGN.md, SPEC.md, STORYLINES.md before composition code.
- [x] Build separate editable sequences for opener (0–32), agents (52–72), end card (170–180). Use real report/source imagery supplied locally.
- [x] Manifest schema: `{fps:30,width:1920,height:1080,sequences:[{id,startSeconds,durationSeconds,compositionPath,renderPath}]}`. Ids `opening`, `agents`, `ending`. Remotion consumes renderPath when supplied; before render it may use labelled live placeholders.
- [x] Validate/check/snapshot each sequence and expose HyperFrames preview. Share exact paths/durations with demo worker.
- [x] Render intermediate motion assets only as needed for the approved editable assembly; final delivery render awaits preview approval/export request.

## Task 3: Remotion showcase — demo worker

Owned: `docs/demo/launch/remotion/**`, `docs/demo/launch-production-handoff.md`, generated `reports/demo-output/launch/**` except `motion/**`.
Read-only: motion manifest/HyperFrames source, approved spec, existing recordings/fixture scripts, runtime and credentials (never print).

- [x] Read Remotion and media/video-editing skills. Scaffold isolated project; ignore node_modules/build/assets locally.
- [x] Start Remotion preview before authoring and keep available.
- [x] Inventory raw captures. If required, record missing brief/approval/progress in one new isolated local synthetic fixture with scripted providers. Coordinator authorizes that bounded fixture operation; no paid/general worker, no existing-workspace reseed/reset.
- [x] Build independently editable JSX clips for authentic evidence/report and synthetic workflow/review. Enforce chapter disclosures and reading time.
- [x] Assemble coordinator motion assets via manifest. Add licensed/free instrumental and restrained effects; provenance in handoff.
- [x] Verify previews at each chapter/transition; inspect full duration, disclosures, readability and absence of secrets. Do not export final MP4 until preview approval or explicit export request.
- [x] Return working preview URL/composition ID, exact setup, source paths, checks and remaining limits.

## Task 4: Integration/review — coordinator

- [x] Independently inspect deck, motion snapshots, Remotion preview and actual source-to-claim example.
- [x] Fresh reviewer checks exact deliverables against approved spec, truthfulness and readability; fix concrete findings.
- [x] Package the approved final deck and MP4; verify relative movie target, matching copy hashes and ZIP integrity. Preserve original assets.
- [x] Update production handoffs and this checklist. Commit/push only owned reproducible sources/docs; exclude generated media and secrets. No runtime suite repetition for media-only edits.

## Progress

- Design approved; builder check: no important questions left. Production and focused delivery review completed. User explicitly approved final export; exact 180-second MP4 passed decode and five browser playback checks. Final PPTX opened in PowerPoint. ZIP/copy hashes passed, and the exact relative movie target resolves to the packaged file. Approved production is complete.
- Parallel paths are explicit; shared checkout is acceptable under AGENTS.md and avoids copying ignored assets/credentials.
