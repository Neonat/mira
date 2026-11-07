# Storytelling production checkpoint

Design and immediate production were approved on 7 November 2026. The user chose Follow the evidence. Base: f7f2745, branch codex/nat-ingestion. No runtime changes or paid research/media calls in this production pass.

## Delivered preview and deck

- Editable 16-slide deck: reports/presentation-output/storytelling/Mira_DBS_Storytelling.pptx. Ten main slides follow the requested story, with six appendices. Updated diagrams and enlarged report crop passed coordinator and independent review. Finalizer reports zero findings/warnings, 16 speaker notes and both movie/preview links.
- Complete Remotion preview: http://localhost:3100/FollowTheEvidence. Verified HTTP 200, browser playback and no current overlay error. Exactly 5,400 frames, 180 seconds, 1920×1080, 30 fps. IAB tab1 is marked as a deliverable. Three actual motion clips are integrated; no placeholders remain.
- Editable HyperFrames preview: http://localhost:3010/#project/project. The 62-second source supplies opening32s, agents20s, ending10s. Clips decoded successfully; HyperFrames check returned zero errors and 11 structural organization warnings. Shots are editable elements in one root rather than separate scene files.
- Final film MP4 is not exported. The user was asked to review the complete preview and choose export/adjust/keep-preview. Do not infer approval from elapsed time. After explicit export approval, render, decode/playback-check and place Mira_Follow_the_Evidence.mp4 beside the PPTX.

## Production writers and handoffs

- storytelling_slides (Luna): docs/presentation/storytelling-outline.md and storytelling-production-handoff.md; generated storytelling deck/renders.
- launch_showcase (Sol): docs/demo/launch/remotion and docs/demo/launch-production-handoff.md; generated launch assets except motion.
- motion_sequences (Terra): docs/demo/launch/hyperframes and generated launch/motion assets. README, prepare-assets.sh and MEDIA/REVIEW.md record reproduction and source checks.
- storytelling_delivery_review (Astra): read-only combined spec/quality verdict, no blockers for preview delivery. Reviewed source/security boundaries and selected film/deck frames; audible taste and final export remain unverified.
- Root owns shared manifest, approved design/plan, integration docs and pushes. Workers were fresh-context, disjoint writers, with no recursive delegation or commits/pushes.

## Evidence boundaries

Authentic saved HK research is distinct from synthetic workflow/review. New synthetic UI-created run 84dd4835-2d4b-4d04-82a5-ce2535a198a3 in workspace launch-79141ead7b used ScriptedClient/FakeWeb only. Optional plan approval was configured only for that new run and is disclosed; the New brief UI skips approval by default. Review footage uses the prior separate synthetic rehearsal. No historical measured reports were mutated.

The dated HKMA PEP letter was checked against its official PDF: https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260827-4-EN/20260827-4-EN.pdf. Header: 28 August 2026; source qualification on page2 retained. Audio is generated locally, with no samples or hosted generation. No narration.

Latest research evidence remains pre-fix9/18 recall with32 saved versions versus30 requested. Human accuracy/time savings and production deployment are unestablished. Corroboration stays deferred. Latest application checkpoint293 tests plus8 subtests is historical here; no runtime suite repetition for media-only changes.

## Reproduction and integration

Use the project README/package locks and ignored local source media. HyperFrames CLI0.9.20 was resolved at /tmp/mira-hyperframes-npm-cache/_npx/702923228c2ce1e6/node_modules/hyperframes/bin/hyperframes.mjs; default npm cache had root-owned entries, so task-local caches were used without global changes. FFmpeg/FFprobe: /Applications/AdaL.app/Contents/Resources/bin/. No plugin/skill updates occurred.

Generated reports, credentials, node_modules, assets, thumbnails and build outputs stay ignored. Stage only reproducible source/design/handoff files. Original deck and recordings are preserved. No external publication or production deployment is authorized.
