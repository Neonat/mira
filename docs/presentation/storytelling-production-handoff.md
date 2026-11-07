# Storytelling deck production handoff

**Objective:** Produce the approved editable 16-slide “Follow the evidence” storytelling deck.

**Base SHA:** `f7f2745` (assignment base supplied by coordinator).

**Owned files:** `docs/presentation/storytelling-outline.md`, `docs/presentation/storytelling-production-handoff.md`, `reports/presentation-output/storytelling/**`.

**Read-only sources:** Approved storytelling design and plan dated 2026-11-07; `docs/agent-handoffs/README.md`; `docs/agent-handoffs/checkpoint.json`; PRD v3 draft as assigned; existing deck, report captures and synthetic review captures. No runtime or evaluation files changed.

**Sources and commands:** Read the presentation skill, template-following, imported-deck, implementation, image and finalization guidance. Checked for Artifact Session and found no connected presentation session or uploaded source ID. Loaded bundled workspace dependencies. `Presentation.load()` reported that its Node adapter is unavailable in the local bundle (`@oai/granola/node` is not installed). Used the approved local Artifact Tool fallback to create editable slides and a new PPTX; did not use `python-pptx`. Built under `/private/tmp/mira-deckbuild/build.mjs`. Reused the source identity palette (white, charcoal, red) and Arial; embedded authentic local report and synthetic-review captures; drew workflow diagrams as native editable shapes.

**Changed outputs:**

- `reports/presentation-output/storytelling/Mira_DBS_Storytelling.pptx`
- `reports/presentation-output/storytelling/Mira_DBS_Storytelling_Montage.webp`
- `reports/presentation-output/storytelling/pep-finding-citation-crop.png`
- `reports/presentation-output/storytelling/renders/slide-01.png` through `slide-16.png`
- `docs/presentation/storytelling-outline.md`
- `docs/presentation/storytelling-production-handoff.md`

**Factual controls:** Slide 11 displays 30-document / 600,000-token / 25-minute requested limits beside the actual 32 saved versions / 372,220 recorded tokens / 21.68 minutes / estimated `$1.8290`, with 9/18 overall and 9/14 regulatory recall. It labels the run partial and pre-fix, discloses potentially missing failed-scout usage and makes no controlled or post-fix improvement claim. Slides 4 and 8 use the authentic saved-report PEP statement, official HKMA PDF dated 28 August 2026, page 2, and retain the “expected to consider adopting” qualification. Synthetic review is labelled and kept separate from real research. Corroboration and the DBS roadmap are identified as future/proposed work.

**Checks:** Artifact Tool exported and rendered all 16 slides. Inspected the montage and all slides individually, then reinspected the targeted revision on slides 4–9. Slide 4 now gives the authentic cited HKMA PEP paragraph a large projection-readable crop. Slides 5–6 use connected, editable architecture and agent-flow diagrams. The diagrams show app-to-worker flow, saved-evidence storage, separate external sources/model provider, parallel scouts, code-controlled completeness and its bounded return loop. Slide 9 uses the audience-facing “Proposed pilot gates” label. All slides carry source references in speaker notes, with visible references on canvas. The local finalizer passed: 16-slide package integrity, 16-slide layout/heading checks, Arial font policy and first-party Artifact Tool import; zero findings/warnings. Receipt: `/private/tmp/mira-deckbuild/Mira_DBS_Storytelling.validation.json`. The deck remains 16 slides and its preview/movie targets were confirmed in the PPTX package.

**Remaining slide gaps:** Slide 7 links to the editable preview at `http://localhost:3100/FollowTheEvidence`; the coordinator's local HTTP check returned 200. The portable relative link `Mira_Follow_the_Evidence.mp4` is in place, but the MP4 has not been exported. Native PowerPoint opening/playback has not been checked. Slide 4 is an authentic saved report excerpt, not a complete browser walkthrough. The latest HK evidence remains pre-fix and partial; no broad coverage, measured time savings, auditor-labelled precision, or independent corroboration is established.

**Exact next step:** Open the PPTX in PowerPoint, inspect all 16 slides and click the verified preview link. After preview acceptance or export authorization, place `Mira_Follow_the_Evidence.mp4` beside the deck and confirm its relative link.

**Status:** Complete for the bounded deck-production assignment; open gaps above remain.
