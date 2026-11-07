# Mira · Follow the evidence

Editable Remotion Studio assembly, 180 seconds / 5,400 frames / 1920×1080 / 30 fps. Preview: **http://localhost:3100/FollowTheEvidence**. No final MP4 has been exported. Export follows preview approval or an explicit export request.

From this directory:

```sh
npm_config_cache=/tmp/mira-video-npm-cache npm ci
python3 scripts/prepare-assets.py
python3 scripts/audio.py
npm run dev -- --no-open --port 3100
```

`prepare-assets.py` reads the coordinator-owned `../motion-manifest.json`, validates dimensions/frame rate and copies existing root-relative source media into ignored `public/`. Missing motion gets a visible labelled preview hold; the completed assembly currently has all three actual clips. `public/asset-ledger.json` records originals and hashes. Public media is deliberately untracked; preserve `reports/demo-output/launch/`, `reports/demo-output/current/`, `reports/demo-output/authenticated/` and the manifest’s motion inputs when packaging.

Each chapter has its own source file and connected composition. Every independently editable clip is an authored JSX node. `Screen.tsx` crops authentic captures while keeping editorial chapter/disclosure text outside the crop. All composition asset references use relative `staticFile()` paths.

- 0–32: coordinator HyperFrames opening.
- 32–52: synthetic brief / fixture-configured conditional approval / recorded steps.
- 52–72: coordinator HyperFrames bounded agents.
- 72–108: historical saved HK research, distinct from the fixture.
- 108–152: existing raw browser review plus disclosed reading holds.
- 152–170: separate original and reviewed synthetic artifacts.
- 170–180: coordinator HyperFrames ending.

No narration. `scripts/audio.py` authors an original sparse 105 BPM instrumental and short action tone locally with deterministic sine synthesis; no samples, model, network, subscription or paid generation. This production releases those two original audio assets under CC0 1.0. Instrumental level is intentionally low; preview listening remains part of user approval.

```sh
npm run lint
node scripts/qa.cjs
```

`qa.cjs` uses the installed Playwright Chrome (or `CHROME_PATH`) to render hero and boundary stills, without final video export. Current QA is under root `reports/demo-output/launch/qa/`.

The fixture/capture scripts are a record of one authorized local rehearsal, not general setup commands. **Do not rerun against the completed fixture.** `fixture.py setup` refuses existing metadata; `capture-workflow.cjs` refuses a second queue operation after the metadata has a run. The saved review capture and historical HK workspaces remain unchanged. See `../../launch-production-handoff.md` for exact run IDs, source paths, observations and limits.
