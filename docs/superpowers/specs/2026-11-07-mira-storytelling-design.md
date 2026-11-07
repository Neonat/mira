# Mira storytelling deck and product film

Status: **approved for production** on 7 November 2026 (“Approve and start production”). Base `f7f2745`. The user selected **Follow the evidence**. Execution uses disjoint slide/video workers plus coordinator-owned HyperFrames sequences.

## Intent

Give the DBS audit audience a reason to care about Mira, explain its bounded agentic workflow and demonstrate the auditor's control. The memorable idea: **a research finding comes with evidence an auditor can inspect**.

Follow the user's sequence: overview, auditor problem, scope, product/value, architecture, agentic highlight, video, HKMA example, proposed DBS roadmap, limits/deployment boundaries, appendix. Total presentation time is unspecified. Coordinator proposes ten main slides plus the film and six appendix slides.

## Approaches

1. **Follow the evidence, selected.** Open on an actual report citation. Its publication and passage become the thread through research and review, using object-to-object transitions and real screens. It combines the product pitch with visible proof.
2. **The auditor's desk.** Open on scattered publications and “What changed in Hong Kong?” A before/after composition reveals Mira. This prioritizes the auditor's burden but gives less attention to evidence lineage.
3. **Inside Mira.** Open on a publication entering the pipeline and follow it through the agent workflow into the report. This foregrounds architecture but delays the user benefit.

The user selected approach 1. Creative details below are coordinator proposals, not additional user requirements. Retain all three in the eventual film project's `STORYLINES.md`.

## Deck

Reuse the editable 16:9 source deck and its white, charcoal and red visual identity. Main slides carry one point each, with explanations and citations in notes and appendices. Keep diagrams and tables editable. Preserve the original file. Rebuild affected layouts only if import/reuse becomes impractical, as the user permits.

Inspection found no separate ink/comment package parts or slide ink elements. Still inspect every slide/image for embedded handwritten marks and remove them. Absence of comment parts alone does not prove visual cleanliness.

| # | Purpose / proposed title | Content |
| --- | --- | --- |
| 1 | Product overview: Mira | Public regulatory and industry research for internal audit. Visible prototype context, one sentence of scope. |
| 2 | Current issue: The auditor's research burden | Publications across markets, dates and formats. Generic reports do not answer detailed audit questions. Stakeholder need: comprehensive, accurate explanations and sources auditors can open. No measured productivity claim. |
| 3 | Scope: Research auditors can inspect | Relevant external developments, preserved dates/context, source-supported facts and labelled inferences. Auditors retain audit actions and DBS decisions. |
| 4 | Product and value: A cited research draft | Real report crop, citation and visible gap. Detailed research, inspectable evidence and reviewer control. No unmeasured speed or accuracy numbers. |
| 5 | How it works: System architecture | Editable diagram: authenticated app, queued run/worker, database/evidence, approved public sources and model provider. Show trust boundaries and server-side secrets. |
| 6 | Agentic highlight: Bounded research agents | Planner, parallel regulatory/industry scouts, analyst, verifier, writer. Code controls sequence, permissions, budgets, typed outputs and persistence. Completeness is programmatic; the bounded gap loop precedes analysis. |
| 7 | Video: Follow the evidence | Poster and playback link, packaged with standalone video fallback. |
| 8 | HKMA example: Why wording matters | Continue the source deck's 28 August 2026 PEP good-practices example. Original date/passage beside the supported statement. Preserve the qualification about considering adoption, rather than turning guidance into a mandatory obligation. Verify against the saved original before publication. |
| 9 | Proposed DBS implementation roadmap | Gates: agree permitted data/sources and evaluation; auditor-assisted HK pilot; improve SG/HK coverage and operating ownership; later corroboration and other-market tests. Proposed roles, no invented delivery dates or approved DBS integration. |
| 10 | Current limits and deployment boundaries | Incomplete coverage, unlabelled human accuracy, source access/storage constraints, local prototype only. DBS deployment needs approved hosting, identity, model/data routes, retention and ownership. Public research inputs go to external services; internal information requires a separately approved route. |
| 11 | Appendix: Measured HK evidence | Run-specific budgets and recall. Fresh pre-fix result 9/18 overall and 9/14 regulatory; 19 facts, 0 inferences, 5 unresolved. Requested 30 documents but 32 saved versions. Recorded usage may omit the failed scout. No post-fix live or controlled improvement claim. |
| 12 | Appendix: Facts, inferences and decisions | A claim is a candidate statement. Source support establishes facts; inferences link facts and preserve uncertainty; auditors decide actions. Checklist coverage, claim support and future corroboration have separate meanings. |
| 13 | Appendix: Human review | Actual synthetic rehearsal screenshots: amendment, stale dependent review, needs-evidence guard, rejection and separate frozen reviewed artifact. Label synthetic evidence and unchanged original. |
| 14 | Appendix: Sources and permissions | SG/HK, PDF/HTML and versioned passages. MAS automated access is blocked and storage permission unresolved; some industry sources lack text-storage permission. Fetchability is not permission. |
| 15 | Appendix: Evaluation | 293 tests plus 8 subtests, PostgreSQL included, none skipped. Separate automated tests, citation recall, human accuracy and time savings. Historical M0 gate has not been accepted. |
| 16 | Appendix: Deferred corroboration | Same factual claim, a second supporting source, independent evidence/origin. Approved future work after coverage, with no runtime implementation. |

## Film and visual identity

- Proposed length: 180 seconds, 1920 × 1080, 30 fps, 5,400 frames. Builder may adjust by up to ten seconds for reading time, without padding.
- HyperFrames authors the opening, evidence-lineage motion, agent-flow sequence, chapter handoffs and end card. Remotion assembles these with independently editable recordings/holds, owns final timing and provides the complete interactive preview. Both contribute authored source.
- Deliver editable sources and preview first. Final MP4 follows preview approval or an explicit export request, as required by the video skills. Update deck playback link when exported.
- Palette from source: `#FFFFFF`, `#222222`, `#60646B`, `#E60028`. Red emphasizes one focus per shot. Existing Arial/compatible type. Display 72–104 px, body 32–40 px, disclosures at least 28 px at 1080p. Margins 96 px, important text within central 80% title-safe area.
- One hero move per shot. Camera moves 12–18 frames with `power2.inOut`; entrances 12–21 frames with `power3.out`/`expo.out`; secondary moves lag 3–6 frames. Keep text stationary while read. Transitions follow the evidence object or the action that causes the next shot.
- Proposed sound: understated instrumental bed at 100–110 BPM plus restrained action/transition effects, sourced from free appropriately licensed/local assets with provenance. No narration by default. No paid media/research API call.
- Banned: invented UI, unsupported speed/accuracy claims, miniature UI in a dark void, neon/glow/particles, decorative KPI grids, three-card feature lists, drifting titles, repeated slide-up entrances and a permanent corner logo. Evidence/synthetic disclosures remain visible where needed.

### Storyboard

| Seconds / frames | Picture and story | Evidence / production |
| --- | --- | --- |
| 0–8 / 0–239 | Actual report statement and citation. “A finding needs evidence”. The citation is the first hero move. | Real saved report; no fabricated UI or standalone logo opening. |
| 8–22 / 240–659 | Citation becomes publication, date and relevant passage. Show the difficulty of finding and reconciling detailed material. | Authentic HTML/PDF evidence with restrained type; no quantified time savings. |
| 22–32 / 660–959 | Reveal Mira and a dated HK AML/CFT research task. | HyperFrames reveal into the real product. |
| 32–52 / 960–1559 | Set brief, inspect/approve plan, see recorded run progress. | Actual UI, disposable local synthetic workspace. Capture missing continuity with scripted providers and fake-publication fixtures; persistently label synthetic research and omitted processing time. |
| 52–72 / 1560–2159 | Open the workflow: parallel scoped scouts, code coverage checks, analyst, verifier, writer. | HyperFrames diagram separates code gates from model judgement. No corroboration shown. |
| 72–108 / 2160–3239 | Inspect the saved HK report, date, statement, citation, original source and a visible gap. | Separate chapter “Saved HK research”. Prefer PEP example for continuity with slide 8; verify authentic source. This is its own historical run. |
| 108–152 / 3240–4559 | Evidence inspection, amendment, stale-review and needs-evidence blocks, fresh review, rejection, sign-off. | Actual browser actions, existing raw recordings or fresh isolated fixture. Persistent “Synthetic review demonstration”. Avoid stacked captions over old captioned MP4s. |
| 152–170 / 4560–5099 | Original versus reviewed artifact: visible amendment, rejected material/dependency absent, original unchanged. | Real local fixture outputs held long enough to read. |
| 170–180 / 5100–5399 | Return to citation, land Mira end card: “Research with evidence. Reviewed by auditors.” | Prototype context, one end-card move. Presenter continues with HKMA wording example. |

The film combines authentic saved research and a synthetic workflow demonstration. It must never imply that the real HK report was generated, reviewed or signed through the synthetic fixture. Edited processing omissions remain disclosed. Local tests do not establish factual accuracy or deployment readiness.

## Boundaries and production roles

Coordinator owns approved story/factual copy, integration and pushes. After approval, assign disjoint paths to a fresh presentation worker and a fresh demo worker; no recursive delegation. Presentation worker owns revised deck/outline/assets/handoff. Demo worker owns captures, HyperFrames/Remotion source, media/handoff. No runtime/model configuration change.

Missing full-flow footage may use one new isolated synthetic workspace/run and existing test providers. Coordinator will authorize the bounded fixture runner for that run only; no paid calls, general research worker, historical mutations, reset or reseeding an existing workspace. Credentials stay outside assets and Git.

Preserve original deck/recordings. New generated deliverables go to a new ignored output directory; keep designs, reproducible sources and handoffs tracked where suitable. Follow presentation skill's Spaces import/session route if available, with a supported local Artifact Tool fallback if required. Explain delivery route rather than silently losing editability.

## Acceptance

Deck: user sequence, 16 slides, no visible handwritten annotations/comments, readable main slides, detailed editable appendices, accurate notes/citations, current metrics/future labels. Render and inspect every slide, especially architecture, HKMA wording, roadmap and measurement caveats.

Film: working preview, authentic controls/sources, disclosed synthetic chapters and omitted time, readable crops/holds, smooth handoffs and balanced licensed audio. Validate/inspect HyperFrames and Remotion, review hero frames and transitions, then after authorized export check metadata, full decode, browser playback and deck playback link.

No new paid research/generated media, external publication or DBS production deployment. Corroboration remains deferred.
