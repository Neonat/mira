# Mira motion sequences

Editable HyperFrames project, 1920 × 1080 at 30 fps. Run the installed HyperFrames CLI from this directory with `preview --background`; preview URL is reported by the CLI. The main composition lasts 62 seconds: opening 0–32, agents 32–52, ending 52–62. These offsets are local to this project, not the complete film. Intermediate silent clips are for Remotion assembly; the final film owns its audio mix.

## Evidence and provenance

`assets/report-facts.png` is the supplied saved historical HK report screenshot. `assets/report-paragraph.png` is its crop (x=285, y=155, width=795, height=105), enlarged 2×. `assets/pep-source-page-2.png` is supplied page 2 of the original HKMA letter. `assets/pep-first-line.png` is its crop (x=205, y=315, width=915, height=40), enlarged. Original: https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260827-4-EN/20260827-4-EN.pdf, dated 28 August 2026. The quote retains “expected to consider adopting” and does not characterize guidance as a mandatory obligation. These assets are historical research, distinct from the synthetic demonstration assembled elsewhere.

`SPEC.md` and `STORYLINES.md` record the approved visual constraints and alternatives. Lint reports structural warnings because the nine shots are directly editable timed clips in one root rather than separate files. The check found no errors. See `MEDIA/REVIEW.md` for snapshot review and remaining limitations.

## Reconstruct ignored assets and preview

From this project directory, run `./prepare-assets.sh`. It checks the saved report screenshot at `reports/demo-output/current/03-regulatory-facts.png`, downloads the official public PDF, checks both source SHA-256 hashes, renders page 2 at 1800 pixels high with `pdftoppm`, and recreates the two crops with macOS `sips`. It requires `curl`, Poppler's `pdftoppm`, `sips`, and `shasum`. To use an existing verified PDF without downloading it, run `./prepare-assets.sh /path/to/hkma-pep.pdf`. If a hash changes, inspect the source before updating the script; the crops depend on the exact versions.

The project scripts pin HyperFrames 0.9.20. With Node 22 and FFmpeg available, run:

```sh
export PATH="/Applications/AdaL.app/Contents/Resources/bin:$PATH"
npx --yes hyperframes@0.9.20 preview --background
npx --yes hyperframes@0.9.20 check --json
# Only when an intermediate render is authorized:
npx --yes hyperframes@0.9.20 render --quality looks --output full-intermediate.mp4
```

The FFmpeg path shown is this machine's AdaL installation; substitute another directory containing both `ffmpeg` and `ffprobe` on other machines. The original render used the locally cached 0.9.20 CLI at `/tmp/mira-hyperframes-npm-cache/_npx/702923228c2ce1e6/node_modules/hyperframes/bin/hyperframes.mjs`; that cache path is ephemeral, so the version-pinned commands above are the reproducible entry point.
