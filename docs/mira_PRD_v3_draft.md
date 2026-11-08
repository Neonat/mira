<!-- Current implementation update: 8 November 2026. Historical measured-run sections remain dated. -->
# Mira Product Requirements v3 — reconciliation draft

Agentic external-driver research for internal audit

**Date:** 7 November 2026 (Asia/Singapore); evidence updated 8 November 2026. **Status:** revised draft; remaining open policies await adoption. **Audience:** Nathaniel, Ewen, Saai, the product owner, and the coding agent.

This is a separate update to [PRD v2](mira_PRD_v2.md); neither v2 nor [archived v1](archive/mira_PRD_v1.md) is replaced or deleted. V2 remains the approved baseline until the team adopts this draft. This document records current behavior, gaps and proposed requirements separately; an implementation choice is not evidence of product approval.

## 1. Basis and limits of this reconciliation

The original reconciliation compared v2 with HEAD `1d38e8916120d45d063d5157abcac6fc2db1af6f` and active working changes. This revision incorporates the subsequent correctness fixes, local PostgreSQL validation and live Hong Kong coverage results confirmed on 7 November 2026. It also records the user's next-work direction: ingestion expansion first, then independent-source corroboration after the Phase 1 exit criteria. This lifts the previous deferral for those phases without claiming either is implemented. Inputs include the user's pasted development handoff, [DBS problem statement](dbs_project_statement.md), [rubric](project_grading_rubrics.md), [approved sources](mira_approved_sources.md), [benchmark](mira_m0_ground_truth.md), [single-agent design](single_agent_arm_design.md), README, application code, migrations and tests.

The working tree was changing during inspection. This is a dated snapshot, not certification of the agent's eventual final branch. Read executable behavior and tests ahead of stale comments: for example, the orchestrator module header still lists plan approval and re-run diff as unbuilt even though their execution paths exist.

Original reconciliation validation returned **222 passed, 40 skipped, 8 subtests passed**. Current validation supersedes that limitation: local review migrations through `20261107180000_mira_frozen_reviewed_evidence.sql` are applied. The evidence-integrity integration suite returned **350 passed and 8 subtests passed**, with PostgreSQL included and none skipped. It ran in an isolated checkout excluding concurrent report-layout work; 26 focused renderer/layout checks subsequently passed with that separate commit integrated. Integration tests use scripted providers. Separate live Hong Kong research runs, the first human-labelled precision sample and an authenticated local synthetic review rehearsal are recorded in §7.3; they do not establish accepted precision or remote deployment. No remote migration is claimed. The later guardrail/budget/seeding fix (`9e4c3c8`, PR6) passed 297 offline tests at commit; `main` (`16effde`) has the same code and returns the same 297 passed, 67 database tests skipped and 8 subtests (`pytest tests eval`).

Status labels below:

- **Present:** executable path exists; passing offline fixtures do not prove live quality.
- **WIP:** work in progress that still requires its stated implementation or validation.
- **Gap:** required or proposed behavior is absent or materially incomplete.
- **Unproven:** tooling exists, but supporting live or human evidence was not established here.
- **Decision:** product input is needed before implementing or accepting a scope change.

## 2. Product purpose, users and boundaries

Mira helps an internal auditor research public regulatory and industry developments, inspect evidence and produce a reviewed research report. Its value must come from useful coverage, accurate statements, traceable evidence and lower research-plus-review effort. It does not determine the bank's compliance or establish deficiencies in its controls.

Users remain auditor/analyst, reviewer, source curator and administrator. Analysts submit and monitor research; reviewers decide whether findings are acceptable and sign off; curators manage source permissions and the expected-source checklist; administrators control access and runtime configuration. Existing assignments in v2 are retained as historical ownership, not renewed delivery commitments.

### Current prototype scope

- AML/CFT; Singapore and Hong Kong selected directly from controlled lists.
- Public material and configured approved sources, with manual import where automated access is unavailable and storage is permitted.
- User-selected period and as-of date. V2's 12–24 months is a pilot scope, not an enforced restriction in `Brief`; its validator checks date ordering. Arbitrary historical correctness is not established by a date field alone.
- On-demand research, optional plan approval, saved evidence, HTML reports and structured snapshots, finding review, sign-off, re-run and diff.
- A server-configured prototype workspace, defaulting to `mira`, using Supabase Auth and workspace-scoped access. `MIRA_WORKSPACE_SLUG` lets a separate app process target a disposable rehearsal workspace without changing authentication or row-level security.

### Deferred unless separately approved

Third jurisdiction, region expansion in the brief UI, scheduled monitoring, news-triggered investigations, 20–30-year archive/backfill, OpenSearch, theme discovery, internal bank uploads, control mapping, production deployment, PDF/DOCX export and email delivery. Unrestricted open-web fallback remains deferred. Bounded Exa-assisted discovery and controlled browser extraction are approved Phase 1 extensions where justified by observed gaps, within existing source permissions; they are implemented locally with explicit opt-in and source-policy checks; live coverage effects remain unmeasured.

**D6 settled by the user:** Mira may explain sourced contextual risks and trends, but must not generate DBS audit actions or business decisions. The auditor decides and acts. This approved boundary updates v2's suggested-audit-actions requirement.

## 3. Current state compared with v2

| Area | V2 expectation | Observed current state | Classification / implication |
|---|---|---|---|
| Brief and access | Controlled brief saved as a Project revision; optional plan approval | Authenticated UI, saved brief, approval pause/resume and controlled SG/HK scope exist | Present; general region expansion not exposed |
| Orchestration | Planner, parallel scouts, analyst, verifier, completeness, writer | Code controls parallel scouting, budgets, cancellation, step records and typed outputs | Present; live HK breadth measured below, wider coverage remains incomplete |
| Sequence | Diagram places verification before completeness-driven follow-up | Execution checks coverage and fills source gaps before analysis and verification | Document the actual sequence; do not imply post-verification claim repair |
| Discovery and evidence | Approved HTML/PDF sources, stored versions and passages | Feeds, hubs, selected links, PDF follow-through, source scoping, reuse and manual import exist | Present; a retrieved page is not proof of adequate research |
| Ingestion expansion | Additional discovery/acquisition routes to improve publication coverage | Scoped Exa discovery, controlled browser acquisition and candidate retention are implemented; bounded live observations are recorded below | Phase 1 gate complete; full coverage recovery remains unachieved |
| Retrieval | Full text plus local embeddings/semantic search | Current scout retrieval uses full text; vector schema support is not an active embedding pipeline | Gap against v2; defer embeddings pending measured retrieval failures |
| Fact verification | Quote match, fresh-context semantic check, one partial rewrite | Implemented; unsupported claims excluded, inference dependencies checked; every number in a quote must appear in the matched passage (PR6) | Present; one labelled sample (§7.3) found no unsupported claims but four overstatements that passed the semantic check |
| Metadata verification | Dates, market and status must be supported | Inference verification now receives displayed metadata and supporting claim metadata | Present; regression validated; labelled sample shows dates supported by recorded `published_at`, not passage text |
| Coverage | Expected-source list, no-change evidence, gap rounds | Item-linked findings and inspected passage labels; imported evidence considered before manual-source fallback | Present; relevance and publication-level completeness still need review |
| Claim-level follow-up | Unsupported claims get a targeted second research attempt | Current gap loop repairs expected-source gaps before verification; no equivalent post-verifier research loop found | Gap; distinguish from source gap filling and corroboration |
| Writer and report | Condense verified claims into structured sections | Writer selects/orders; code renders full saved verified claim text, fills omitted main-section findings, labels facts/inferences and dates | Present; more restrictive than v2's paraphrasing allowance |
| Audit impact | Risks, opportunities and suggested audit actions | Contextual risks/trends allowed; DBS actions and business decisions remain with the auditor | D6 settled by user |
| Human review | Decisions then reviewed report | New sign-offs freeze exact checked/reviewed evidence and outcomes; amendments/rejections and dependent review gates remain; incomplete reviewed renders fail closed | Present; PostgreSQL regressions passed; earlier authenticated rehearsal predates the full frozen bundle; real-auditor validation remains outstanding |
| Re-run | Saved brief, previous run link, findings diff | UI/CLI paths and verified-finding diff exist | Present; compare same scope; do not imply automatic scheduling |
| Corroboration | No explicit independent-second-source requirement | Saved-first claim corroboration, bounded permitted follow-up, origin/proposition decisions and frozen reviewed output are implemented locally | Phase 1 exited at 83c84c1; prototype defaults below, enterprise policy adoption remains D7 |
| Evaluation | Coverage, precision, time, cost; three arms | Scorer supports market/date scope, explicit official URL aliases and CLI flags; HK live recall measured; one run's claims human-labelled | Human benchmark acceptance, a second labeller and precision at target outstanding |
| M0 gate | Single-agent recall ≥50% before full build | Full build already exists; no accepted gate result established; scorer uses fetchable recall | Decision D9; record unmet historical gate honestly |

Evidence anchors: [orchestrator](../mira/orchestrator.py), [scout](../mira/agents/scout.py), [verifier](../mira/agents/verifier.py), [coverage](../mira/completeness.py), [writer](../mira/agents/writer.py), [review UI](../app/streamlit_app.py), [signed-off renderer](../mira/render.py), [new review migration](../supabase/migrations/20261107120000_mira_reviewed_report_outcomes.sql), [live evaluation](../eval/run_live.py), [recall scorer](../eval/score_recall.py).

## 4. Required user journey and architecture

1. Auditor signs in and supplies topic, markets, dates and run limits. Scope and settings are saved.
2. Planner produces a visible plan. If approval is required, work pauses before fetching; approval resumes the saved plan.
3. Regulatory and industry scouts search eligible saved evidence and discover approved publications within their task scope. Newly fetched content is versioned before analysis.
4. Code checks the expected-source checklist. Missing items can trigger targeted re-planning and re-scouting within the remaining document, token, time and gap-round budgets.
5. Analyst drafts facts and contextual inferences. Verifier checks quote authenticity and factual support; partially supported facts receive at most one narrowing rewrite. Inferences depend on verified supporting claims.
6. Writer selects and orders verified findings; deterministic grounding renders their saved content. Coverage, limitations and unresolved items remain visible.
7. Reviewer inspects evidence and records accept, amend, reject or needs-evidence outcomes. Sign-off creates a separate reviewed snapshot and artifact reflecting those outcomes.
8. Auditor can re-run a finished brief and inspect new, amended and no-longer-supported findings. The original brief's date scope is retained; this is not automatically a rolling monitoring window.

The orchestrator is deterministic Python. Agent judgement is constrained by typed outputs and short evidence/claim labels mapped to stored IDs. Fetching, parsing, date extraction, versioning, budgets, coverage, diffing and rendering remain code. The verifier's separate context is not independent source corroboration and does not guarantee an independent model/provider.

## 5. Evidence, correctness and report requirements

### 5.1 Evidence and temporal integrity

Every factual finding must identify saved supporting passages, source URLs, document versions and quotations. A normalized or bounded fuzzy quote match is a necessary authenticity check, not sufficient proof that a claim follows from a passage. The semantic verifier must check entity, market, date, numbers and instrument status.

Current retrieval selects the highest saved version number per document whose publication date is unknown or on/before the brief's as-of date, before full-text ranking and result limits. The same version policy filters fresh visits, shared reuse and manual/stored passages. A future-dated latest version falls back to an older eligible version. Capture time is not a claim about what the publisher's page contained historically; historical evidence is not presented as a separate archive-search mode.

Publication dates must come from retained publication evidence. Retrieval/import dates, arbitrary filenames and model guesses must not become publication dates. Unknown dates remain visibly unknown and do not prove recency. Older material may support a relevant effective date or deadline where the evidence establishes it. An inference's displayed metadata must be checked with its text and dependency metadata; rejected or unsupported dependencies cannot support an inference.

### 5.2 Coverage semantics

Coverage is relative to the named expected-source list and brief, never a guarantee of comprehensiveness. It is distinct from benchmark recall and number of verified claims. A long report or larger document budget does not establish breadth.

| Auditor-facing outcome | Required basis |
|---|---|
| Relevant material found | Relevant saved passages linked to the particular checklist item, from its expected source |
| Checked, no change found | Identified publication/category evidence inspected for that item and relevant period; a same-host unrelated page is insufficient |
| Coverage unconfirmed | Evidence does not establish the item's coverage, even if a hub or other page was retrieved |
| Manual import needed | Automated access unavailable and suitable imported evidence has not resolved the item |
| Could not retrieve / Could not extract text | Acquisition or extraction failed; do not present empty content as successful research |
| Stopped at run limit | A stated run allowance prevented further work |

Current code structurally links inspected passages to checklist rows and checks source identity; that alone cannot prove the passage is relevant or covers the requested period. Acceptance must include an unrelated-passage adversarial case and a human inspection of real checklist outcomes. Manual imports must satisfy the same scope, source and evidence standards as fetched material.

### 5.3 Research breadth

Before increasing budgets, trace missed expected publications through discovery, fetching, extraction, passage selection, analysis, verification and report inclusion. Check both markets, regulator categories and industry categories. Document fetch/store restrictions separately from discovery failures. Candidate balancing, source reuse and alias deduplication must preserve relevant document content and avoid spending the document allowance repeatedly on identical material.

Current coverage work adds category-specific HKMA/SFC indexes, SFC public POST search and full-publication JSON, consultation-conclusion PDF follow-through, year slices bounded by the reporting period, primary HKMA PDFs and official aliases. Fetches and gap attempts respect source permissions; passage selection is balanced with expanded context for selected documents, and fetch logs expose acquisition outcomes. Checklist v2 adds SFC circulars. Existing workspace connector/checklist records still need refresh; code/seed changes alone do not update them or expand permissions.

Candidate-selection telemetry is implemented in `agent_steps.output_refs.selection_diagnostics`. It records bounded discovery/origin metadata, filtering reasons, prompt ranks and labels, selection, fetch references, allowance and stop reasons. Omitted record counts make truncation visible; raw article text and model reasoning are not included. Old scout results parse without diagnostics. In-process scout failures now carry partial diagnostics and known usage to the orchestrator, which persists and charges their fetches before subsequent gap rounds. This cannot recover historical missing diagnostics or unreported provider usage. This observability does not change ranking or establish a recall gain.

Publication-level completeness remains distinct from finding a category page. SFC enforcement and other publications, MAS access and industry storage permission remain gaps. Dated live HK results are in §7.3; the larger-capacity run remains partial and is not an equal-budget comparison.

#### 5.3.1 Approved Phase 1: ingestion expansion

Use retained telemetry to trace discovery, filtering, candidate presentation/selection, fetching, extraction, permitted storage, analyst input and report citation. Diagnose selection/capacity failures as well as missing acquisition routes. Do not infer discovery failure where the historical failed scout retained no diagnostics, or inject benchmark targets into runtime search.

Choose the smallest useful extensions, including Exa-assisted discovery and controlled browser extraction where they address an observed gap. Singapore/Hong Kong remain the primary scope. Required behavior:

1. Preserve approved-source scoping, workspace isolation, public-data boundaries, budgets, canonical publication identity/deduplication and the existing version/as-of policy. Discovery permission does not imply fetch or text-storage permission; browser access must not bypass source restrictions.
2. Keep original capture, extraction, citation and reviewed snapshot identities distinct. Identify Exa responses/extracts and browser captures by their actual acquisition method/context and time; do not describe an extract as a complete archived publisher original. Retain capture/extraction hashes and extraction versions where available, with unknowns explicit. Do not relabel an extraction hash as the original-download hash.
3. Persist permitted evidence through the existing version/passage and verification paths. Show per-document acquisition, extraction, storage and run-limit failures clearly; empty content is not successful ingestion.
4. Preserve contract-1.4 guarantees: bind actual verification/review inputs, freeze all required evidence at sign-off, refuse incomplete reviewed renders and leave historical reviewed files/snapshots unchanged. New adapter data must not silently enter an existing signed report.
5. Record why each extension is needed and which stages it changes. More connectors or saved documents do not establish improved report-citation recall. Original-download retention and durable artifact storage/restore remain separate unfinished work; new capture persistence must be described accurately rather than claiming those broader gaps are solved.

#### 5.3.2 Phase 1 exit and transition to corroboration

Before Phase 2 implementation, demonstrate the targeted ingestion paths end to end through saved evidence, verification and reviewed rendering; pass relevant fixture-based coverage and evidence-integrity regressions; obtain independent diff review; and checkpoint the implementation after integrated tests/eval with local PostgreSQL. Record before/after evidence, remaining access/storage gaps and measurement limits. Separate acquisition, checklist coverage and report-citation recall.

Perfect coverage is not required. Unresolved access limitations must remain visible; a genuine prerequisite blocking safe corroboration must be resolved or explicitly scoped before that dependent work begins. Once this gate is met, proceed to Phase 2 without seeking feature approval again. Offline fixtures establish tested behavior, not live recall: further paid/live validation still requires explicit bounded authorization, and prior HK figures remain historical/pre-fix.

### 5.4 Report output

Retain v2's topic/market/period/as-of header, executive summary, regulatory developments, deadlines, jurisdiction comparison, supervisory trends, industry developments, impact assessment, re-run changes, coverage/limitations and evidence appendix. Empty sections explicitly state that no verified items were established.

Findings show stable report references, full saved wording, fact/inference status, market, supported date and date kind, source links, and priority separate from evidence confidence. Priority is research relevance, not proof of a breach. Under settled D6, impact assessment explains sourced or verified contextual risks and trends without prescribing DBS actions or business decisions.

The current implementation renders saved claim text rather than allowing writer paraphrases. Preserve this as the proposed grounding rule; report length and executive-summary readability still require human review. HTML and structured JSON snapshots are the current output basis; no new export UI is implied.

### 5.5 Review and sign-off

For new reviewed versions, acceptance requires:

- The authoritative latest decisions are frozen into the reviewed snapshot with reviewer identity and time, using deterministic ordering for tied timestamps.
- The complete retained finding/dependency closure, passage text and quotations, document versions, citation/provenance metadata, semantic-check provenance, brief and checklist labels are frozen in a typed contract-1.4 bundle. Sign-off binds worker-recorded actual verification inputs and server-captured reviewer inputs to that exact evidence; changed or unbound inputs require fresh verification/review.
- Accepted findings retain approved text. Amended findings display the amendment; rejected findings and dependent inferences do not survive in the report body or summary.
- Outstanding evidence requests on retained findings prevent sign-off. Undecided findings cannot be made reviewed merely by rendering a file.
- An inference is reviewed again after an amendment to a supporting fact; rejection propagates through dependencies.
- The signed artifact matches the frozen outcomes, has reviewer/date labels, and opens as a separate reviewed file; the unresolved-reason fallback described below is a remaining limitation. Later review events do not mutate earlier report versions.
- A failed render remains pending and does not block unrelated renders.
- Reviewed rendering and the signed review screen use the frozen bundle alone. Missing findings, dependency evidence, passages, version consistency or verification/review records prevent a reviewed artifact from being written. Later live links and metadata cannot enter an earlier signed version. Reviewed snapshot fields are immutable; artifact-path completion remains allowed.

Current implementation stores review outcomes and renders amendments without calling a model again. It replaces the amendment's title with a reviewer-amendment label and clears the original key date. Automatic evidence re-verification of human amendments is not implemented; dependent-inference re-review is enforced. **D8 must settle whether human attestation is sufficient for a material amendment.** Existing old artifacts remain historical; they are not retroactively certified by the new migration. The signed artifact is a separate `report-vN-reviewed.html`. Only the fallback for unresolved-item reasons points to the draft because some reasons are not persisted; retaining those reasons in the snapshot remains a backlog gap.

Legacy reviewed snapshots without the complete bundle refuse regeneration and never fall back to current live evidence. Their existing rendered files remain available. Historical checks and review events are not backfilled with guessed input bindings: new sign-off requires fresh checking/review where those bindings are absent. A complete frozen snapshot can still render if the live evidence becomes unavailable. Original-download retention and durable artifact storage remain separate unfinished work.

## 6. Implemented independent-source corroboration and prototype defaults

Source verification asks whether a cited source supports a claim. Corroboration asks whether another independent source supports the same material proposition. Two URLs, a landing page and its PDF, a mirror, or a publisher repeating an original announcement are not automatically independent evidence.

Phase 1 exited after independent review and local PostgreSQL integration (378 tests plus 8 subtests, none skipped) at `83c84c1`. Phase 2 now implements the following requirements; its implementation defaults are explicit below. Offline evidence does not establish live research quality or policy adoption under D7:

1. Search eligible saved evidence first, then perform a bounded targeted search of approved sources only.
2. Save supporting/conflicting documents and passages, exact quotations, document versions and the relationship to the claim before making a corroboration judgement. Check the same material proposition, including entity, jurisdiction, dates, quantities and instrument status.
3. Record source identity, provenance/independence rationale, agreements or contradictions, checked time, search attempts and stop reason.
4. Display distinct outcomes such as independently corroborated, primary-source only, conflicting evidence, not checked and inconclusive, with source links, dates and understandable reasons. Failure to find a second source is not proof a primary-source statement is false or unverified.
5. Keep contradictions visible for review; do not inflate confidence solely from source count. Official obligations remain anchored to the authoritative issuer.
6. Freeze corroboration decisions, independence rationale and their supporting/conflicting evidence into each new reviewed snapshot. Later searches must not alter a signed version. Changed verification/review inputs require the existing fresh-verification/review guards; use compatible new contracts/migrations rather than rewriting applied migrations or inventing historical backfills.
7. Test independent support, copied/syndicated reporting, mismatched propositions, contradictions, authoritative single-source evidence, exhausted search budgets, stale evidence, workspace isolation and frozen reviewed output. A different URL or model context alone is not independent-source corroboration.

**Implemented prototype defaults (D7 remains an enterprise-policy decision):**

- Every factual claim in the normal multi-agent path is eligible; inferences retain separate verification and expose supporting facts' corroboration. The comparison arm retains its existing behavior. Eligible saved evidence is selected by workspace, permitted source, jurisdiction and latest publication/as-of-eligible document version before retrieval limits. Bounded salient-term OR retrieval admits paraphrases and potentially conflicting quantities; semantic assessment determines relevance.
- Search saved evidence first. Optional targeted discovery uses the Phase 1 Exa opt-in, then policy-controlled acquisition and permitted storage. Default per-claim limits are two queries, five candidate documents/acquisition attempts, twenty passages and sixty seconds, capped by the shared run's remaining document/token/deadline budget. Failed acquisition attempts and reported model usage are charged. Unknown usage on a cancelled model request consumes a separately labelled conservative reservation; it is not presented as reported billing.
- To make the bounded semantic workload practical, the normal worker retrieves at most one eligible saved candidate passage before assessment and records that narrower limit. The assessor shows at most two primary passages and one candidate passage as exact contiguous excerpts (up to 1,800 characters each), with a 4,096-output-token ceiling inside a sixty-second claim deadline capped by the shared run deadline. Full originals remain frozen. Truncated or omitted context cannot establish support or a validated conflict: those decisions remain uncertain, with potential-conflict evidence retained. These are prototype workload bounds, not evidence of live latency or precision. The separately authorized sixty-second/single-candidate validation below completed 8/12 calls with zero corroboration timeouts and four output-limit failures; full acceptance remains incomplete.
- Exact quotations and matching entity, jurisdiction, predicate/scope, dates, quantities and regulatory status are required for support. A conflict requires an explicit incompatible value within the same proposition scope; a missing value is not a contradiction. Source organization/origin configuration takes precedence over supplied candidate defaults. Same publications, known aliases, same organizations, copied captures/text and shared origins are dependent; a different URL is insufficient. Independent origin requires retained exact evidence of original work on both sides. Unknown origins remain inconclusive.
- Validated conflicts take precedence. Missing, rejected or uncertain candidate assessments are explicit incomplete checks and prevent a clean positive outcome. An authoritative primary-source fact remains valid evidence without a second source; `primary_source_only` applies when there is no unresolved candidate, while incomplete candidate checks are `inconclusive`. Absence of a check is `not_checked`.
- Auditors see statuses, dates, exact passages, origin decisions/reasons, source links, limits and acquisition provenance separately from fact verification and human decisions. Existing review decisions acknowledge the captured assessment; no universal two-source sign-off rule or automatic DBS action recommendation is introduced. Maker/checker and material-amendment policies remain D5/D8.
- Assessments append to a worker-written, workspace-readable ledger ordered by a server sequence. Each assessment binds an acyclic base evidence input; actual verification and reviewer inputs include its complete immutable result and candidate evidence. New/changed assessments require fresh verification and review. A changed or superseded candidate blocks a new sign-off. Contract-1.5 reviewed bundles freeze assessments and evidence; later queries never alter earlier reports. Complete contract-1.4 bundles remain readable, with absent corroboration treated as not checked. No historical assessments or verification bindings are invented.

The local fixture evidence includes a saved independent investigation flowing through the normal fact-verification path into a signed report, rejection of stale candidates for a new sign-off, stable historical rendering after later changes, copied/shared origins, missing decisions, contradictions, budget exhaustion and workspace isolation. Live precision of the corroboration assessor remains unmeasured. Existing delivered slides/video retain their historical evidence cut; use the current feature-status handoff before making new presentation claims.

## 7. Evaluation and release evidence

### 7.1 Measurement contract and remaining acceptance

The existing benchmark has a fixed 26 October 2025–26 October 2026 window and 24 documented items; its own status requires human auditor review. It excludes commercial industry news and therefore does not measure every industry-development requirement.

The scorer now carries market/publication/effective dates, filters to the brief's market/date scope, and exposes CLI scope flags. Explicit official URL aliases match publication identities, including supported landing/PDF alternatives, while preserving meaningful document/query identifiers. Human acceptance of the benchmark and eligibility policy remains outstanding. A matching URL is a recall proxy, not proof the report accurately covers the development. Preserve benchmark isolation from agent prompts and do not tune acceptance thresholds after seeing results.

Distinguish: checklist coverage, eligible-development recall, and human-labelled claim precision. Report all-item, fetchable-only and regulatory subsets with explicit denominators. Industry breadth needs its own evidence review rather than being inferred from the regulatory benchmark.

### 7.2 Proposed targets retained from v2

| Measure | Proposed target / evidence |
|---|---|
| Eligible development recall | ≥80%, with market/period and denominator stated |
| Citation precision | ≥95% fully supported on a human-labelled sample; report partial/unsupported/contradicted labels separately |
| Seeded false-claim detection | ≥90% caught; report leaked count and fixture scope |
| Critical unsupported claims | Zero reaching reviewers in the evaluated sample; never present this as a universal guarantee |
| Time saved | ≥50% against manual research plus review, measured with 2–3 auditors or proxies |
| Latency and cost | Proposed <15 minutes; actual model, tokens, time and estimated cost reported; approved budget needed under D3 |
| Multi-agent value | Compare plain search, single agent and multi-agent on the same eligible brief; report coverage, precision, cost and latency |

These remain proposed targets. The live recall and precision measurements below are development evidence, not accepted product scores. The first labelled precision sample is below the ≥95% target. Accepted precision, time-saving evidence and a final multi-agent verdict remain outstanding; no M0 win is claimed.

The existing live runner shares an evidence store and runs multi-agent, then single-agent, then plain search. Disclose that later arms inherit evidence, that plain search is over saved evidence, and that this is not an isolated cold-start experiment. The current decision code treats any positive coverage or precision difference as a win, while the comparison design warns that one or two items can be noise. D9 must settle the decision threshold and evaluation design before results are presented.

V2's M0 was a pre-build gate; it cannot now be represented as having passed retrospectively. The scorer uses ≥50% **fetchable** recall, whereas v2's wording does not explicitly select that denominator. Recommend preserving the historical record and adopting an explicit evidence gate for demo readiness, pending D9.

### 7.3 Current validation and live HK evidence

The evidence-integrity changes passed **350 tests plus 8 subtests**, with local PostgreSQL and offline evaluation included, no skips and no paid/live model or research calls. The first full run exposed two fixture problems (a repeated synthetic email and an outdated query stub); after correcting those, both focused cases and the complete suite passed. The isolated suite used source base `ad79028`; a subsequent 26-case renderer/layout check passed against the separately committed report-layout change `53b88fb`. Regression cases exercise late-link and dependency changes, caller-bundle forgery, stale or unbound verification/review inputs, required supporting-finding decisions, immutable signed rows, byte-identical re-render after live metadata changes, incomplete/legacy refusal, distinct and long quotations, future-check exclusion, and eligible-version selection before limits. The new migration is local only. The signed review projection has automated tests; the earlier browser/video rehearsal did not exercise contract 1.4. See [evidence-integrity handoff](agent-handoffs/evidence-integrity-fix.md).

The local review migration is applied. The correctness checkpoint returned **280 passed and 8 subtests passed**, including PostgreSQL with no skips and scripted integration providers. The four implemented correctness fixes cover immutable review outcomes/latest ordering, displayed inference-metadata verification, item-linked no-change inspection, and imported evidence for sources that cannot be fetched. These automated checks do not establish human precision or remote deployment.

Subsequent candidate-selection telemetry integration passed **285 tests and 8 subtests**, including PostgreSQL with no skips. Focused regressions cover filtering versus presentation/selection, caps and omitted counts, allowance/fetch references, repeated selection labels, old-result compatibility and step persistence. That change used no new paid research run. Its first demo was a partial saved-report walkthrough; the subsequent authenticated rehearsal below supersedes that review-flow limitation.

The integrated URL-fetch, failed-scout accounting/diagnostic persistence and configurable UI-workspace fixes passed **293 tests and 8 subtests**, including PostgreSQL with no skips (`pytest tests eval`, 8.76 seconds). The local synthetic rehearsal exercised actual Supabase Auth/RLS and browser actions: amendment, stale-inference and needs-evidence sign-off guards, fresh dependent review, rejection, sign-off and explicit reviewed-artifact rendering. Ten artifact checks passed, including unchanged original SHA-256, amendment in body and summary, and exclusion of the rejected fact and dependent inference. The 3:24 captioned video discloses synthetic evidence and uses no paid research or historical-report mutations. This demonstrates local review mechanics, not factual accuracy, reviewer independence or production deployment. See [authenticated-review-handoff.md](demo/authenticated-review-handoff.md).

Live HK runs on **7 November 2026** produced:

| Run | Document allowance | Findings: facts / inferences / unresolved | HK publication recall | Elapsed / estimated cost |
|---|---|---|---|---|
| Baseline `80ffbc29…` | 15 | 6 / 1 / 1 | 1/18 overall | 10.35 min / $0.7135 |
| Initial coverage fix `ebac84e8…` | 15 | 10 / 1 / 3 | 2/18 overall | 13.22 min / $1.1883 |
| Final capacity run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0` | 30 | 17 / 1 / 1 | 7/18 overall; 7/14 regulatory | 15.29 min / $1.4395 |
| Fresh telemetry diagnosis `e2fda30f-36f9-4aa3-83c3-d78b81671b83` (pre-fix) | 30 requested; 32 saved versions | 19 / 0 / 5 | 9/18 overall and fetchable; 9/14 regulatory | 21.68 min / $1.8290 from recorded steps |
| Labelled-precision run `29a153bb-ffa2-40a1-a702-3abc828bed4c` (Haiku; code `83e3b32`) | 40; 34 used | 19 / 2 / 4 | 11/18 overall; 11/14 regulatory; 11 of 13 reachable | 9.6 min / $0.128 |

Run `29a153bb` is the first with human-labelled precision ([evidence](../eval/evidence/2026-11-07-hk-run-29a153bb.md)). All 21 draft-report claims were labelled by one team member who had not seen the verifier verdicts: **0 unsupported or contradicted**, **7/21 fully supported** on passage text, and **17/21** when each document's recorded publication date is accepted as date evidence. Neither meets the proposed ≥95%. The four remaining partials overstate the source's hedges, scope, addressee or attribution, and all passed the semantic check; tightening Gate 2 on these is the evidenced next accuracy step. Caveats: one run, one labeller, Haiku models on code that predates PR4 and PR6, self-review sign-off, and a provenance defect: the stored `model_settings` lists Opus/Sonnet while every step recorded `claude-haiku-5-5`. It is not a controlled comparison with the earlier runs.

The earlier capacity run allowed **30 documents, 600,000 tokens and 25 minutes**, used **302,985 tokens**, cited **10 primary publications**, and remained partial because it reached the document budget. Its larger allowance prevents interpreting it as an equal-budget quality comparison. Ten cited publications and seven benchmark matches measure different sets.

The single fresh telemetry run used the same requested limits and recorded **372,220 tokens** and **13 distinct cited source URLs**. A malformed HKMA PDF URL aborted a scout. Its partial work was lost from diagnostics and budget accounting, allowing **32 saved versions despite the requested 30-document limit**; failed requests are additional to saved-version counts. Usage/cost from that failed scout may also be missing. This is not an equal-enforced-budget comparison or a post-fix coverage gain. The URL is now encoded safely, invalid requests become per-document failures, and failed scouts retain diagnostics/known usage and consume the later gap budget. These fixes were validated offline; no second live run was made. Three missed SFC enforcement publications were discovered and presented with one slot remaining; selection/capacity remains a coverage issue. Other misses include access/storage constraints and incomplete discovery evidence. See [the diagnosis](agent-handoffs/hk-telemetry-diagnosis.md).

Local, ignored artifacts are `reports/2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0/report-v1.html`, `coverage-comparison.json` and `precision_worksheet.csv` in that run directory. That worksheet has **18 unlabelled rows**; it is not a precision result. These generated artifacts are local evidence, not checkpointed deliverables or remote deployment.

Authenticated sign-in, evidence inspection, amendment/rejection, dependent re-review, sign-off and separate reviewed-artifact opening have been rehearsed locally with synthetic evidence. The approved 180-second HyperFrames/Remotion film now joins a new UI-created synthetic brief, fixture-configured optional approval and recorded progress with saved HK evidence inspection and the separate synthetic review rehearsal. Chapters and omitted processing time are disclosed. Final MP4 decode/browser playback and the paired 16-slide PowerPoint package passed delivery checks. This is a product showcase assembled from separate observed examples. Human-review the benchmark and precision worksheet, then run the agreed comparison under D3/D9. See [the film handoff](demo/launch-production-handoff.md).

## 8. Source permissions, security and operational constraints

Retain v2's public-data boundary, workspace access controls, server-side credentials, initiating-user audit trail, source allow-list, redirect/private-address checks, robots/rate limits, bounded size/type handling, untrusted-source instructions and versioned provenance. Fixtures demonstrate particular guardrails, not universal resistance to injection or hallucination.

The scout still retains extracted text/passages rather than durable original HTML/PDF captures, and rendered report files still use the local filesystem. Frozen snapshots solve reviewed evidence identity, not original-capture retention, artifact durability or restore. Ingestion expansion and corroboration are implemented locally under the Phase 1/2 gates, including frozen acquisition provenance and new reviewed corroboration snapshots. Original binaries and report artifacts still lack durable storage/restore. Source-permission changes, additional paid/live calls and remote deployment are not implied by that authorization.

The repository records MAS automated access as blocked and written storage permission as outstanding, despite prototype seeding allowing text storage. This is an existing unresolved project decision, not confirmation of permission. Other named industry sources have fetch/metadata permission without stored passages, constraining citable coverage. Manual acquisition does not itself settle storage permission. D4 must identify permitted demo evidence, remaining source reviews, and the owner/refresh schedule for imported documents. No source permissions were changed in this reconciliation and no current external terms were independently rechecked.

Budgets are runtime configuration, not product promises. Code defaults currently include 60 fetched documents, 2,000,000 tokens, 15 minutes and two gap rounds; the README describes a 300,000-token development setting and historical 15-document runs. Record actual run settings instead of treating one of these as an agreed cost cap. Providers and per-role models are configurable; actual configuration and costs require D3 agreement.

## 9. Settled decisions and remaining policy work

The document may be reviewed without resolving every item. Changes implementing the affected policies should wait for the relevant decision. Routine correctness work that restores an existing requirement is distinguished from adopting new scope; this draft does not instruct or control the other agent's active run.

| ID | Decision needed | Recommendation, not approval | Owner / affected work |
|---|---|---|---|
| D3 (carried) | Which per-role model setup, token/document limits and cost cap are acceptable for demo and comparison runs? | Pin actual settings and a per-run plus total evaluation allowance; preserve public-data-only input | Product owner + team; spending and live evaluation |
| D4 (carried) | Which sources may supply stored demo evidence, who completes permission reviews, and who imports/refreshes blocked material? | Use explicitly permitted evidence and disclose unresolved SG/industry gaps; do not infer permission from fetchability | Product owner + curator; source expansion/import policy |
| D5 (carried) | Who is the sign-off reviewer, and is self-review acceptable in the prototype? | Name a senior auditor proxy and record whether maker/checker separation is required | Product owner; review access and demo claims |
| D6 — settled | User approved contextual risks/trends without generated DBS audit actions or business decisions | Preserve this boundary; auditor decides actions | Settled scope; prompts, verifier and report |
| D7 — prototype implemented; enterprise policy open | Corroboration follows the Phase 1 gate in §5.3.2; define eligible claims, independence, search allowance and sign-off consequences | Prototype checks factual claims with explicit bounded limits, origin evidence and existing reviewer sign-off; adopt or revise this policy explicitly before enterprise rollout | Product owner + reviewer; corroboration design/schema/report |
| D8 (new) | Can material reviewer amendments be signed off on human attestation alone, or must they pass evidence verification again? | Require explicit evidence review and dependent-inference re-review; decide whether automated recheck is mandatory | Reviewer + product owner; amendment workflow and verification |
| D9 (new) | What is the accepted benchmark scope, recall denominator, multi-agent improvement threshold and replacement for the unmet pre-build M0 gate? | Human-review eligible items, show all/fetchable subsets, retain caveats and use a forward demo evidence gate | Product owner + evaluator; scorer and presentation conclusions |
| D10 (new) | Is the final demo SG+HK or an explicitly narrower HK pilot; are all four industry categories required before demo? | Retain SG+HK intent; if evidence remains inadequate, obtain explicit scope reduction and reflect it in slides | Product owner; final brief, acceptance and release scope |

**Remaining priority policies:** D7 detail (not feature approval), D8 (amended evidence) and D9 (measurement). D6 is settled. Source permissions and budget policy also remain open; adapters or seeded rows do not close them. Approval to update this draft does not adopt every proposed target or remaining policy.

## 10. Delivery order and specialist work

1. **Preserve the completed evidence-integrity checkpoint:** full frozen evidence, incomplete-render blocking and version-aware retrieval are implemented and locally validated. Preserve v1/v2 and historical artifacts; no input-binding backfill or remote migration.
2. **Phase 1 complete locally:** inspect existing designs/code and retained telemetry; choose justified Exa/browser extensions and address evidenced selection/capacity gaps under §5.3.1. Complete and document §5.3.2 before dependent corroboration implementation. Scoped live observations below do not establish full coverage recovery; no repeated paid runs without new bounded authorization or reconstruction of missing historical diagnostics. MAS and industry-source permission gaps remain disclosed.
3. **Phase 2 complete locally:** saved-first corroboration, bounded optional acquisition and frozen evidence/decisions implement §6. Prototype defaults are explicit; enterprise adoption remains D7. Independent reviews and the complete integrated suite passed. Live semantic/origin precision remains unmeasured.
4. **Complete evaluation:** adopt D9 measurement policy, human-review the benchmark, show recorded publication dates in the precision worksheet, add a second labeller, fix the `model_settings` provenance mismatch, tighten Gate 2 on hedges/scope/attribution, and run the agreed comparison only within authorized budgets. Run narrow regressions during development and one complete tests/eval suite with local PostgreSQL per integration milestone; repeat only for changed code or failures. Record the exact tested scope and separate offline evidence from live quality claims.

5. **Keep delivered slides/video aligned with demonstrated behavior:** the storytelling deck and approved 180-second product/workflow film are packaged. New ingestion/corroboration behavior needs observed evidence before inclusion as working functionality; retain synthetic/historical and edited-time disclosures. No accepted precision, M0 win or production-deployment claim is established.

This order records the user's current direction. Specialist work should use bounded, reviewable tasks; it does not adopt remaining open policies or permit new source storage.

## Appendix A. Requirement continuity

V2 IDs remain useful for code/test traceability. No unmet requirement is silently removed by observing a narrower implementation.

| V2 ID | Disposition in this draft | Main code / acceptance evidence |
|---|---|---|
| AG01 Brief | Retain; SG/HK direct selection; region expansion deferred | `mira/brief.py`, `mira/contracts.py`, `tests/test_brief_budget.py` |
| AG02 Planner | Retain visible valid plans and optional approval | `mira/agents/planner.py`, approval tests in `tests/test_pipeline_db.py` |
| AG03 Orchestrator | Retain budgets, cancellation and trace; clarify actual sequence | `mira/orchestrator.py`, `tests/test_orchestrator.py` |
| AG04 Regulatory scouts | Retain source-scoped, parallel saved-evidence research | `mira/agents/scout.py`, `tests/test_scout_reuse.py` |
| AG05 Industry scout | Retain categories; permit explicit no verified items; breadth unproven | `mira/agents/scout.py`, source permissions and D10 |
| AG06 Fetch/parse | Retain versions, visible acquisition/extraction failure and manual import | `mira/fetch.py`, `mira/extract.py`, `mira/manual_import.py` |
| AG07 Analyst | Retain facts/inferences and evidence links; settled D6 excludes DBS actions | `mira/agents/analyst.py`, `mira/contracts.py` |
| AG08 Verifier | Retain support checks; strengthen metadata acceptance; claim re-scout remains a gap | `mira/agents/verifier.py`, `tests/test_correctness.py`, `tests/test_report_grounding.py` |
| AG09 Coverage | Retain source-gap rounds; strengthen no-change/import semantics | `mira/completeness.py`, `tests/test_correctness.py` |
| AG10 Writer | Retain verified-only report and implemented full-saved-text grounding | `mira/agents/writer.py`, `tests/test_report_grounding.py` |
| AG11 Re-run | Retain previous-run linkage and verified-finding diff | `mira/diff.py`, `tests/test_diff.py`, `tests/test_pipeline_db.py` |
| AG12 Run UI | Retain visible steps, source outcomes and limits; browser proof outstanding | `app/streamlit_app.py` |
| AG13 Review | Strengthen effective outcomes, immutable snapshots and dependency review | new migration, `mira/render.py`, `tests/test_pipeline_db.py`; D8 |
| AG14 Injection | Retain source-as-data and code-enforced boundaries; report tested scope | `mira/agents/common.py`, `tests/test_guardrails.py` |

V2 Appendix B remains the reference for inherited v1 requirements. In particular DB03 hybrid retrieval is not fulfilled by full text alone, applicability/as-of controls are not equivalent to proven arbitrary historical reconstruction, and DB07 reproducibility has the unresolved-reason persistence limit noted above. No archive-scale or production capability is newly promised here.

## Appendix B. Adoption and preservation

This documentation refresh preserves v1/v2 and aligns the companion coordinator handoff/checkpoint with the approved two-phase work order. It records completed local validation and live-run evidence from the development work; it does not itself implement ingestion/corroboration, run models, change the database or permissions, deploy remotely, or adopt proposed targets.

Before adoption: resolve or explicitly defer the remaining policy register, reconcile subsequent implementation changes with this snapshot, and have the product owner adopt v3. Any later pointer update making v3 the primary PRD should be a separate explicit documentation change; keep v2 and v1 available as historical baselines.

## 8 November 2026 implementation evidence update

The ingestion-first gate exited at `83c84c1`: 378 tests plus 8 subtests, none skipped, including local PostgreSQL. Generic candidate-retention ablation reaches 123 rather than 120 selection-frontier attempts with equal document allowance and an extra selection call; it does not establish saved-publication or report-citation recall improvement. URL discovery is metadata only; reports require separately permitted saved passages. Offline Chromium capture was exercised with synthetic HTML, scripts disabled and all resource routes aborted; pages needing external scripts/data remain unsupported. Capture/extraction identities and non-retention status enter verification and frozen review inputs. The normal HTTP scout retains its existing per-request timeout; new bounded corroboration uses a persistent, killable acquisition broker and shrinking database statement deadlines.

Upstream PRs 4–6 were merged during this implementation and are preserved, including numeric quote checks, category seeding and scout budget guards. A separate team-recorded [HK run/precision worksheet](../eval/evidence/2026-11-07-hk-run-29a153bb.md) reports 11/18 citation recall and 7/21 strict versus 17/21 publication-date-adjusted supported claims. PR8 links that document as historical measured evidence; it records one labeller, self-review and a model-provenance mismatch, and predates these features and the integrity/guardrail updates. Its labels are not post-feature precision or an accepted release gate. Historical runs in §7.3 retain their original unlabelled-precision caveats. This task performs no paid/live research/model calls, no remote migrations, no model-setting changes and no historical report rewrites.

Final integrated validation at implementation `42efc32`: **459 tests plus 8 subtests, none skipped, 13.83 seconds**, including local PostgreSQL and offline evaluation. New migrations are local only. Independent review found no remaining important issues. See [integration handoff](agent-handoffs/ingestion-corroboration-integration.md) for exact commands, remaining limits and publication state.

## 8 November 2026 PR7 follow-up: actual computer/browser acquisition

The offline renderer remains available, and a separate actual Chromium adapter now navigates public URLs, executes JavaScript and performs at most three curator-configured read-only click/wait actions. This is deterministic browser automation, not a new paid vision/model computer-use agent or a model-configuration change. It is globally disabled by default (`MIRA_ENABLE_LIVE_BROWSER=0`) and additionally requires existing fetch/store_text plus explicit source browser approval/reference. Retrying an HTTP block requires its own approval flag. The user explicitly chose to keep MAS disabled; no MAS acquisition or seeded permission change was made.

HTTP remains first and both HTTP/browser attempts consume allowance separately. Source/robots/private-address denials and429 are not retried through the browser. Real browser requests use pinned public DNS, TLS-verified robots reads, honest user-agent identification and task-source constraints on redirects/resources. Images/fonts/media are omitted and optional unapproved resources denied visibly. Configured clicks cannot interact with forms; login/CAPTCHA/access-denial checks run before and after actions. Fresh contexts import no credentials/session state; WebSockets/service workers/WebRTC channels are restricted. Process-group deadlines cancel browser children; failed requests preserve learned crawl delay, and unknown interrupted policy quarantines only that target for the current run. The observed byte monitor can overshoot a delivered chunk; request count, DOM and wall deadlines remain bounded.

Current source browser permission is rechecked under lock before storing a capture, including the original HTTP-block-fallback grant. Acquisition method, DOM/initial-navigation identities, explicitly unknown final-response identity, permission reference, read actions and sanitized resource/stage context enter actual verification/reviewer inputs and frozen reviewed evidence through new local-only migration20261108100000. Historical records and applied migrations are unchanged. Browser captures are not complete archived publisher originals; original/durable storage gaps remain.

Current HKMA [terms](https://www.hkma.gov.hk/eng/other-information/terms-and-conditions-of-use/) were checked for the existing non-commercial prototype use; robots returned404 (missing, allowed by existing policy). A bounded actual HKMA circulars-page navigation with JS succeeded in24.91s, extracting20,084characters and128links with22requests. Two optional resources were denied and42non-text assets omitted, so integration labels the capture partial. The initial60s timeout had no retained stage trace and cannot be attributed to source blocking. Portable metadata is in [validation evidence](agent-handoffs/hkma-live-browser-validation.json); no source approval was persisted. This is one acquisition test, not live claim verification, publication completeness, recall or assessor precision.

Implementation `0f9526d`: **487tests +8subtests passed, none skipped,50.63s**, including actual Chromium fixtures, local PostgreSQL, old integrity/corroboration cases and Ewen PR6's quote/token/seeding regressions. Independent focused review findings were resolved. PR7 is updated without merging/deploying. No paid/model/Exa calls, no Mira model-setting changes, no historical report rewriting.


### 8 November clean validation: acceptance not achieved

At measured source `43a7b1c`, one uninterrupted bounded HK run `7e877c4e` produced a model-written draft in 18.30 minutes: 16 facts, three unresolved, 30 complete HTTP acquisitions, six successful actual Exa searches, no browser fallback and no MAS activity. Acquired and cited benchmark coverage stayed **5/18**, versus previous5/18 and earlier local9/18. All **six** thirty-second corroboration model calls timed out; persisted results were inconclusive. Passing519tests+8subtests and completed orchestration are not evidence that coverage or latency acceptance passed. See [full result](../eval/evidence/2026-11-08-hk-clean-run-7e877c4e.md). The later funded-round and one-candidate/sixty-second revisions were not part of that measured source; their subsequently authorized validation is recorded below. Existing slides keep their historical evidence cut; no accuracy, time-saving or production claim follows.


### 8 November additionally authorized validation: partial improvement

The user explicitly authorized one further uninterrupted bounded run. At source `c1cf682` (runtime `78c6771`), run `7be59cdf` kept 30 documents, 600,000 tokens, 25 minutes, two gap rounds and at most six Exa searches, with unchanged role models/effort and MAS inactive. Actual Exa HTTP API-key transport completed 5/5 requests. Thirty complete HTTP acquisitions yielded **6/18 benchmark publications versus previous 5/18; citation recall stayed 5/18**, below earlier local 9/18. Browser was enabled but never triggered; MAS had zero fetches/versions and temporary browser grants were removed.

The compact one-candidate/4,096-output-token/sixty-second assessor completed **8/12 calls in 22.96–38.78 seconds**, with **zero corroboration timeouts and four output-limit failures**. Twelve persisted assessments are five primary-source-only and seven inconclusive; no independent corroboration success is established. The writer had 16.35 seconds remaining and timed out at the overall cap; the existing fallback produced a partial report with 19 verified facts, zero included inferences and three unresolved claims. Reported 478,544 tokens plus 90,685 unknown-usage reservation stayed within 600,000; reservations are not measured usage. The unchanged runtime's final suite remains 538 tests + 8 subtests, none skipped; post-run accounting/evidence checks passed. Full coverage recovery and reliable end-to-end completion remain unachieved. This is one historical observation, not causal, precision or efficiency proof. [Measured result and limitations](../eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.md). The additional paid-run allowance is used; existing slides/historical reports remain unchanged, and no merge or remote deployment occurred.
