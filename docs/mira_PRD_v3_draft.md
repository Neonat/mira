<!-- Current implementation update: 11 November 2026. Historical measured-run sections remain dated. -->
# Mira Product Requirements v3 — implementation and pilot requirements

## Research console and temporary BYOK — 10 November 2026

**Audience:** pilot audit analysts and senior reviewers; operators use [the console runbook](research-console.md). The existing Streamlit app now exposes source, custom-date, method, analysis-depth and plan-approval controls. Analysts review the submitted request before entering temporary masked provider keys and a USD allowance. The configured role-model profile remains operator-owned. No key or rate catalogue is stored in PostgreSQL, reports or environment files by the BYOK path.

The same-machine broker validates the signed-in owner and workspace role, holds pending keys in memory for at most 60 minutes, and supplies them once through a separate worker-only socket. Approval continuation requires fresh keys while retaining elapsed active time and known/uncertain usage. A shared Decimal ledger reserves model, embedding and Exa charges before dispatch, journals admission, and retains unknown attempted charges. Current first-party prices are checked at execution; unsupported models or unavailable prices refuse paid work. Public-price estimates exclude account-specific discounts/credits and infrastructure costs. Operator-managed CLI execution remains a separate trusted path.

Country-method results use approved portable measurements with explicit scope and denominators. Hong Kong’s one-fact sample is labelled synthetic, separately from the historical 19-fact report and unlabelled six-question/153-passage archive experiment. Australia uses the measured API/direct-file representation approach; UAE federal uses approved hub/direct documents. No causal Exa/browser or storage-quality winner has been established. Malaysia, DIFC/DFSA and MAS stay disabled; hybrid stays experimental and source embedding grants still apply. Historic report bytes and evidence are preserved. This update authorizes implementation and local scripted validation, not another paid research campaign.

Console validation: **1,272 tests +8 subtests, zero skips**, including local PostgreSQL and Chromium; final rerun/brief-budget follow-up **26 checks**. Independent integrated review and scoped fixes passed. [Validation and remaining live scope](agent-handoffs/research-console-byok.md).

## Hong Kong quality and demo latency — 10 November 2026

**Prepared evidence workflow (implemented 11 November):** operators can
schedule evidence acquisition and machine checks independently of reporting.
Analysts request a draft from completed snapshots; each request pins the source
scopes and waits for the exact refresh already scheduled or running for those
sources. Failed refreshes require an explicit choice to use previous evidence.
Reviewers can accept, reject or request a correction to a fact. Reports
prominently flag any included facts awaiting human review and preserve the
captured decisions. Final approval is separate. Prepared report assembly uses
saved evidence without provider calls; enterprise credentials are provisioned
outside the demo for preparation. See the [workflow and review
contracts](superpowers/specs/2026-11-10-scheduled-evidence-reporting-design.md).

**User timing clarification:** the demonstration has a maximum wait of five
minutes; normal research may take substantially longer. Keep the demonstration
acceptance target separate from user-configurable research time and depth.
Normal requests already allow 1–240 minutes and 1–64 analysis batches; the default
time ceiling remains 15 minutes unless configured otherwise. Preserve the USD
allowance and evidence checks while allowing adequate time for substantive
coverage. The earlier ten-minute validation was a coordinator-selected test
bound, not a normal-run product requirement. With evidence ready, a local
[synthetic benchmark](../eval/evidence/2026-11-10-prepared-report-benchmark.md)
preserved 20/20 expected facts from four documents in about 0.09 seconds per
report. The five-minute target applies to the ready-evidence path; live country
coverage and preparation latency were not remeasured.

New report generation distinguishes operative publication dates from container revisions, checks exact inference premises against retained dependency context, and prioritizes dated native publications and substantive passages. Conservative guards cover new captures and recognizable legacy category indexes without changing historical reviewed reports. Independent analysis/checks use at most four lanes under one dollar/token/time allowance; three-passage/4,500-character batches retain explicit deferred coverage. Saved corroboration evaluation can overlap; fresh acquisition remains serial. Role models and source grants stay unchanged. The authorized ten-minute/USD10 observation ended partial at9.1minutes with5/18 acquired and1/18 cited; it failed demo acceptance. The latest smaller-batch and scheduling corrections pass1,360 tests +8 subtests but remain live-unvalidated; no replacement paid run occurred. [Implementation, acceptance and measured follow-up](agent-handoffs/hk-quality-and-latency.md).

## Generation reliability — 10 November 2026

**Earlier analysis/writer follow-up:** analysis then defaulted to three whole passages/4,500 content characters and a 180-second batch ceiling, retaining 16,384 output tokens and eight batches maximum. Invalid structured output or rejected labels can receive one correction under the original batch deadline and remaining run allowance; unknown usage stops correction and keeps its reservation. Safe schema paths/error categories survive the isolated provider boundary and persist with failed steps, without raw response bodies. The writer (`writer/4`) returns seven sections of bounded claim-label groups, not prose; unchanged grounding renders complete saved verified text and fills omitted main-section findings. Writer output headroom is 16,384 tokens/120 seconds under the existing shared ledger. Existing models/effort, evidence, source permissions and historical reports remain unchanged. The integrated suite passed **1,100 tests +8 subtests, no skips, 64.94 seconds**. This follow-up used no paid API execution; live generation reliability is not yet rechecked. Malaysia/DFSA/MAS remain disabled and hybrid experimental. [Implementation and remaining validation](agent-handoffs/analysis-writer-followup.md).

The subsequent user-authorized test `5fad1aa1` at `86f2bfe` ran uninterrupted and saved a normal partial fallback report after 821.877 seconds. A scoped keep-awake process and 164 successful database checks confirmed continuous availability; PostgreSQL was left running. There were no generation timeouts. Two analysis batches failed (output limit/invalid structured output), and the writer hit its output limit, so clean acceptance remains unmet. The report contains three verified Australian facts and no verified UAE claims, with three inconclusive corroboration assessments. Its 175,124-token counter matches the shared ledger and persisted usage exactly. See the [current validation](../eval/evidence/2026-11-10-au-ae-uninterrupted-validation.md). The reused test profile limited analysis to 8,192 output tokens, below the production batch default of 16,384; the larger default was not validated here. Older live-unvalidated statements below describe the preceding checkpoint.

Normal worker generation uses isolated provider requests and a shared admission ledger for model and experimental embedding work. Reservations use serialized UTF-8 input/schema plus output allowance; known usage and unknown attempted usage remain distinct. Local refusals cost zero. Unknown-usage output failures retain their reservation without an unfunded retry. Ordinary injected legacy clients retain their existing contract; the production provider uses bounded calls.

Scout summaries show at most 16,000 whole-passage content characters, with explicit omission diagnostics and no deletion of retained evidence, and allow 16,384 output tokens within 120 seconds. Ordinary model calls, including primary verification, allow 120 seconds/8,192 output tokens; the writer now allows 16,384 as described above. Existing role models and effort are unchanged. Runtime corroboration keeps one candidate and bounded excerpts, with a 90-second total claim ceiling and at most 8,192 output tokens; historical explicit 30/60-second assessment limits remain valid. Admission preserves downstream tokens/time, including writer headroom; it does not guarantee provider latency or exhaustive fact extraction. Source/document rotation and smaller analysis defaults address one large compilation consuming every batch. Budget text distinguishes allowance consumed from measured usage, and request journals retain input/output usage splits separately from database step persistence.

The [single AU/UAE validation](../eval/evidence/2026-11-10-generation-reliability-validation.md) at `a7ff8af` completed four small analysis batches (12/1,198 passages) and persisted supported findings for both markets. It encountered one corroboration timeout and two output limits, then failed when local Docker/PostgreSQL stopped before the writer. The database retained all eight representations and four supported factual claims after restart. The separate offline recovery draft includes only facts whose saved supported checks still match current evidence; it is not a completed live report, reviewed sign-off or uninterrupted quality proof. Follow-up output/deadline and journal changes pass 1,075 tests +8 subtests, with no further paid run; their live latency remains unvalidated. Malaysia/DFSA/MAS remain disabled and hybrid experimental.

## Australia/UAE source extension — 10 November 2026

The user-approved mixed retrieval extension adds `AU` and `AE` to controlled brief selection. `AE` means the approved CBUAE federal source profile, excluding DIFC/DFSA, VARA and other regulators. SG/HK remain the form defaults. Malaysia/DFSA remain unenabled and MAS is forced inactive by seeding; synthetic guard tests opt in explicitly without live MAS requests.

Federal Register native metadata preserves instrument identity and separates registration/availability from effective dates. Recognized fixed publication HTML/PDF supply text; title/viewer shells and API discovery records retain metadata without citable legal-text passages. The Scout retains discovered counterparts through deduplication and fetches HTML/PDF within its existing document reservations. AUSTRAC uses permitted public guidance/file acquisition with live robots checks. UAE federal hubs supply only approved same-host files; no browser escalation or external embedding grant is added.

Permitted complete extracted text and native JSON are independent of derived claims. Source reuse notices are captured and frozen consistently in Python/SQL, with legacy shapes preserved when no notice exists. Original-byte retention remains separately permissioned. Hybrid retains its experimental status and keyword comparison path; this extension is not a human-labelled usefulness or national-completeness acceptance.

The source catalog/checklist is v3. The source-notice capture migration is local-only until separately deployed. See the [source register](mira_approved_sources.md) and [implementation plan](superpowers/plans/2026-11-10-mixed-retrieval.md). Historical measured-run sections below retain their original scope and dates.

Agentic external-driver research for internal audit

**Updated:** 12 November 2026 (Asia/Singapore). Monthly preparation and report requirements are in §4, with the verified hosted Hong Kong download and demo readiness in §7.4. The dated implementation and evaluation record remains below. **Status:** current implementation reference and pilot requirements draft.

**Document audience:** the product owner, Nathaniel, Ewen, Saai, implementation agents and technical reviewers making scope, design and acceptance decisions. **Product audience:** bank internal-audit analysts and senior reviewers; source curators and administrators support that workflow. The [README](../README.md) is the introduction for competition judges and DBS stakeholders.

This is a separate update to [PRD v2](mira_PRD_v2.md); neither v2 nor [archived v1](archive/mira_PRD_v1.md) is replaced or deleted. V2 remains the approved baseline until the team adopts this draft. This document records current behavior, gaps and proposed requirements separately; an implementation choice is not evidence of product approval.

## 1. Current implementation and evidence basis

This revision uses merged `95bd1f8` as its baseline and records the user-approved evidence-completeness extension under review on 8 November 2026. [PR6](https://github.com/Neonat/mira/pull/6) provides quote/budget/source-seeding guards; [PR7](https://github.com/Neonat/mira/pull/7) adds permitted ingestion expansion, actual browser acquisition and frozen claim-level corroboration; [PR8](https://github.com/Neonat/mira/pull/8) preserves presentation and historical evaluation evidence; [PR9](https://github.com/Neonat/mira/pull/9) makes verified SFC citation destinations readable to auditors. The report template also includes the requested table-spacing improvements.

The preceding merged-code engineering validation passed **560 tests plus 8 subtests, none skipped**, including local PostgreSQL, actual Chromium fixtures, review/evidence integrity and readable source-link regressions. Four existing SFC publication destinations were separately checked in a browser. These checks establish the exercised workflow; research-quality measurements remain separate in §7 and the dated engineering record in Appendix C.

The original reconciliation started at `1d38e8916120d45d063d5157abcac6fc2db1af6f`. Historical test/run checkpoints remain in the [handoffs](agent-handoffs/README.md) and linked evidence artifacts. Inputs include the [DBS statement](dbs_project_statement.md), [rubric](project_grading_rubrics.md), [approved-source catalog](mira_approved_sources.md), [benchmark](mira_m0_ground_truth.md), application code, migrations and tests. The earlier documentation refresh changed no runtime. The new extension adds runtime/schema behavior below; existing role models, source grants, historical reports and remote deployment remain unchanged.

Status labels below:

- **Present:** implemented behavior, with its evidence and acceptance scope stated.
- **WIP:** work in progress against a stated requirement.
- **Gap:** an implementation or acceptance item for the team to resolve.
- **Unproven:** a measurable outcome that has not been established by the recorded evidence.
- **Decision:** product input needed to adopt a policy or target.

### Evidence completeness extension — implementation under review

**User approval:** implement passage coverage and bounded batch analysis first, then permitted originals/page navigation and optional hybrid retrieval; test locally and open a PR. Product users remain audit analysts and reviewers. This section is the current technical delta; historical research measurements in §7 retain their original scope.

- **Passage analysis:** normal workers expand scoped acquired/reused/selected versions to all eligible saved passages. Whole-passage batches default to three passages/4,500 content characters, eight batches maximum, 16,384 output tokens per attempt and a shared 180-second ceiling per batch, including at most one invalid-output correction. Selection prioritizes substantive topical passages and rotates across sources and documents; affirmative listings follow publication content. Up to four independent batches/checks overlap, with deterministic coordinator persistence and shared admission. All dispatched work drains before cleanup. Shared run limits take precedence, retaining a 32,000-token/180-second follow-up reserve and a120-second useful analysis window, clamped to an explicitly shorter timeout; correction admission includes the full serialized request reservation. Each validated batch saves claims and analysed dispositions atomically; later failures retain earlier findings. Valid empty output counts as analysed, not exhaustive fact extraction. Oversized, unfunded or capped inputs remain stored with explicit reasons.
- **Frozen coverage:** worker-only append-only candidate/attempt/terminal events bind passage/version/run/step identities. New instrumented reports use contract 1.6 with canonical document counts and failure/defer reasons, verified again at review. Legacy 1.4/1.5 summaries remain unchanged; no historical dispositions are invented. Existing source-checklist coverage remains a separate measure.
- **Original files:** optional private local content-addressed storage requires global opt-in plus a current source approval/reference beyond `store_text`. Digest/size/workspace checks guard reads; the signed-in review screen checks current membership/source permission before preparing a download. HTTP/manual-import bytes qualify; rendered browser DOM does not. Failure preserves extracted text. Known PDFs gain page links. Retained identities enter new frozen provenance; old artifacts are untouched. Deployment still needs durable storage and tested backup/restore.
- **Experimental hybrid retrieval:** opt-in; full-archive PostgreSQL keyword/cosine ranks are fused after workspace/source/active/permission/jurisdiction/latest-as-of gates. Manual imports remain usable without fetch permission. Semantic indexing additionally requires `embed`, explicit model/revision and 384dimensions, with content-bound immutable vectors. Forty is now per indexing batch, at most4 default; the default 60,000 cumulative-character/20,000-token/20-second envelope bounds work, not archive cardinality. Completed batches survive later failures; eligible/indexed/pending/blocked coverage and stop reasons are exposed. All eligible stored text stays keyword-searchable, including unindexed/oversized whole passages. Measured usage and unknown reservations are separate from role billing. MAS is excluded; role model/source grants are unchanged. Usefulness against keyword search remains an experiment.

**Acceptance evidence:** final integrated local suite **691 tests +8 subtests passed,none skipped (92.39s)**, covering scripted-provider, PostgreSQL, filesystem/access, process-deadline and Chromium fixtures; [implementation record](agent-handoffs/evidence-completeness.md). Controlled semantic fixtures demonstrate the mechanism, not live recall or precision gains. No new paid/live validation or source grants, MAS activation, remote migration or deployment is included.

### Durable evidence and quality-validation follow-up — implementation under review

User-approved follow-up adds optional private Supabase copies of report HTML and permitted originals, verified immutable publication/retry, authenticated retrieval after local-file loss, and direct bucket policies enforcing current workspace/source grants. Report references remain separate from frozen signed snapshots; no historical report is rewritten. The source retention opt-in/reference and existing role models remain unchanged. An anon key is app-only; private uploads require a separate worker credential and an explicitly enabled backend.

Consistent native database snapshots pair all relational evidence with referenced original/report bytes in a private verified package. Restore requires a trusted operator-created archive and a separate empty local database, validates every member before writes, preserves legacy HTML byte-for-byte, and refuses source/shared/non-loopback targets. Current tests cover the mechanism; hosted deployment, independently managed backup storage/schedules, and provider restore acceptance are separate operator work. See the [runbook](backup-recovery.md).

An offline preflight/export/comparison path prepares the next quality validation using the actual historical Hong Kong scope2025-11-04..2026-11-04, unchanged role models and declared caps. Passage, primary-verification and corroboration measurements remain distinct; missing historical fields are not invented, and human precision still needs blinded labels. No new paid/live model, embedding or Exa run is included in this implementation. MAS remains inactive.

### Initial hybrid profile activation — 10 November 2026

The user subsequently approved configuring and enabling hybrid retrieval and testing the actual embedding integration. The existing local worker environments now enable `text-embedding-3-small` at 384 dimensions, with application cache revision `mira-te3-small-384-v1`; the revision is not a provider snapshot. Existing role models, source grants and retrieval bounds remain unchanged. New installations retain an off-by-default template flag.

A single controlled live validation used two actual embedding requests, 45 measured tokens and 3.719 seconds. A synonym-only query with zero eligible lexical matches returned the expected passage; four cached passage vectors were reused for a query-only warm request, and repeated scout selection incurred no extra request or charge. Inactive MAS, foreign-workspace, future/superseded-version and missing-embed-permission controls were excluded. All synthetic database rows were rolled back. MAS acquisition, Exa, browser and generative-role calls were zero. See [result and scope](../eval/evidence/2026-11-10-hybrid-embedding-validation.md). This establishes provider/cache/scout integration, not whole-corpus indexing, a new Hong Kong run or a recall/precision gain. Pools above the default 40 eligible passages still use recorded keyword fallback.

### Subsequent full-archive hybrid experiment — 10 November 2026

The user requested removal of that corpus cutoff and explicitly kept usefulness experimental. The new bounded incremental index and exact database query path indexed **153/153 eligible saved HK passages**, zero pending, in five batches; a separate 47-passage controlled archive also completed. The one authorized validation used 16 embedding requests/29,949 tokens/16.797 seconds, with no web acquisition, generative-role calls or MAS activity. New source-grant validation was migrated locally only. An explicit finite-budget backfill command supports larger archives without a research run.

Six questions frozen before retrieval used equal top10 and a fixed corpus/index snapshot. Their top10 overlaps were5,7,5,8,7,4; relevance is unlabelled, so no usefulness winner is established. Median warm latency including query embedding was0.80705 seconds hybrid versus 0.0084 seconds keyword. Controlled synonyms benefited; exact identifiers tied on fixed-k relevance, with extra irrelevant semantic candidates; a no-answer case returned three irrelevant semantic results versus none for keyword. Keep the keyword switch and downstream evidence checks; do not infer product efficacy from ranking changes. [Experiment and limits](../eval/evidence/2026-11-10-archive-hybrid-validation.md). Fresh final suite: **997 tests + 8 subtests, none skipped,in 71.56 seconds**. This does not create a new HK acquisition/report recall or human precision result.

## 2. Product purpose, users and boundaries

Mira helps an internal auditor research public regulatory and industry developments, inspect evidence and produce a reviewed research report. Its value must come from useful coverage, accurate statements, traceable evidence and lower research-plus-review effort. It does not determine the bank's compliance or establish deficiencies in its controls.

Users remain auditor/analyst, reviewer, source curator and administrator. Analysts submit and monitor research; reviewers decide whether findings are acceptable and sign off; curators manage source permissions and the expected-source checklist; administrators control access and runtime configuration. Existing assignments in v2 are retained as historical ownership, not renewed delivery commitments.

### Current prototype scope

- Combined AML/CFT with controlled Singapore, Hong Kong, Australian and UAE federal source lists. The prepared-report console also supports Cybersecurity for scoped UAE federal sources. SG/HK remain the demo priorities.
- Public material and configured approved sources, with manual import where automated access is unavailable and storage is permitted.
- User-selected period and as-of date. V2's 12–24 months is a pilot scope, not an enforced restriction in `Brief`; its validator checks date ordering. Arbitrary historical correctness is not established by a date field alone.
- On-demand research, optional plan approval, saved evidence, HTML reports and structured snapshots, finding review, sign-off, re-run and diff.
- A server-configured prototype workspace, defaulting to `mira`, using Supabase Auth and workspace-scoped access. `MIRA_WORKSPACE_SLUG` lets a separate app process target a disposable rehearsal workspace without changing authentication or row-level security.

The research console exposes controlled jurisdictions, sources, custom dates, an as-of date, run allowances and an optional plan approval. The prepared-report path is described in §4.3. Auth passwords belong to provisioned Supabase Auth users. A configured developer email only prefills sign-in, and password setup/reset is operator-managed.

### Deferred unless separately approved

Full preparation beyond the demo markets in §7.4, news-triggered investigations, 20–30-year archive/backfill, OpenSearch, theme discovery, internal bank uploads, control mapping, production deployment, product PDF/DOCX export and email delivery. The separately generated peer-validation PDFs are test deliverables, not a new product export workflow. Unrestricted open-web fallback remains deferred. Bounded Exa-assisted discovery and controlled browser extraction are approved Phase 1 extensions where justified by observed gaps, within existing source permissions; they are merged with explicit opt-in and source-policy checks. Dated acquisition and research observations are recorded in §7 and Appendix C.

**D6 settled by the user:** Mira may explain sourced contextual risks and trends, but must not generate DBS audit actions or business decisions. The auditor decides and acts. This approved boundary updates v2's suggested-audit-actions requirement.

## 3. Current state compared with v2

| Area | V2 expectation | Observed current state | Classification / implication |
|---|---|---|---|
| Brief and access | Controlled brief saved as a Project revision; optional plan approval | Authenticated UI, saved brief, approval pause/resume and controlled SG/HK/AU/AE scope exist | Present; AE is scoped federal sources; wider region expansion deferred |
| Orchestration | Planner, parallel scouts, analyst, verifier, completeness, writer | Code controls parallel scouting, budgets, cancellation, step records and typed outputs | Present; live HK breadth measured below, wider coverage remains incomplete |
| Sequence | Diagram places verification before completeness-driven follow-up | Execution checks coverage and fills source gaps before analysis and verification | Document the actual sequence; do not imply post-verification claim repair |
| Discovery and evidence | Approved HTML/PDF sources, stored versions and passages | Feeds, hubs, selected links, PDF follow-through, source scoping, reuse and manual import exist | Present; a retrieved page is not proof of adequate research |
| Ingestion expansion | Additional discovery/acquisition routes to improve publication coverage | Scoped Exa discovery, controlled browser acquisition and candidate retention are implemented; bounded live observations are recorded below | Phase 1 gate complete; full coverage recovery remains unachieved |
| Retrieval | Full text plus local embeddings/semantic search | Experimental full eligible archive SQL keyword/cosine fusion with incremental content-bound pgvector cache; explicit index coverage and finite backfill budgets |153/153 saved HK passages indexed and queried; usefulness against keyword search and very-large-archive performance remain unproven |
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

### 4.1 Analyst setup and monthly evidence preparation

1. The analyst chooses the country, topics and fixed initial date window, then selects monetary authorities, secondary news outlets, or both. Show eligible publishers and whether each can be fetched automatically, needs manual import, or is limited to discovery. The official-source option includes relevant legislation and other official publications needed for the brief. Only prepare content for operations the source permits.
2. Before starting, show estimated cost and elapsed time for the initial window and a typical monthly refresh. Show the expected publications and passages, reusable work, paid discovery and model charges, and time for any manual steps. Show **publisher licence fees** as a separate line, with **quote pending** when the fee is unknown. Record actual costs, times and processing outcomes against the preview.
3. The analyst selects a database from the workspace's authorised destinations. Default to the existing destination for that workspace. Store the schedule, permitted originals and indexed evidence against that destination so reports use the intended database and retain their source references.
4. Run on a calendar-monthly schedule after the analyst approves the configuration. Use the workspace time zone, with Asia/Singapore as the demo default. Carry forward missed intervals and outstanding eligible work. Reuse completed checks for unchanged evidence when the topic and check inputs still match. Preserve prior originals, findings, verification records and reports as new versions and snapshots are published. Show failed or incomplete refreshes and what remains to prepare.

### 4.2 User report request

1. The user selects a country, one of **AML**, **CFT** or **Cybersecurity**, and a date range. Check coverage for that scope against the selected prepared sources in the workspace's database. Show the evidence cutoff and any source-level gaps, including holes within an otherwise prepared interval.
2. If the range is covered, assemble a draft from indexed, verified saved evidence without provider calls. Cite the exact supporting evidence and display human-review status. Measure time from the user's report request to the visible draft when evidence is ready. Retain the five-minute maximum for the demo and measure preparation and review separately.
3. If coverage is incomplete, show the affected dates and sources and why each is missing. Offer a covered date range for a quicker draft when one exists. If the user keeps the original dates, preview cost and time, then prepare only the eligible missing intervals and topics after the user chooses to proceed. Reuse eligible saved checks and join matching work already in progress. Once the gap closes, generate the report for the original request automatically. If work stops or a source is blocked, show the remaining gap and offer the available coverage explicitly.
4. Attribute secondary reporting at claim level. Show whether a claim has official support, independent corroboration, conflicting evidence or unconfirmed secondary reporting. Shared-origin coverage counts once. Preserve the status stated by the evidence, such as an allegation or a conviction, and show human review separately.

### 4.3 Implementation gap as of 11 November 2026

| Workflow | Available today | Work remaining |
|---|---|---|
| Preparation setup | Approved-source controls in the research console, manual imports for eligible sources, and operator-configured preparation schedules at fixed second intervals | Analyst-facing source and destination selection for preparation, scope-specific cost and time preview, calendar-monthly recurrence and refresh status |
| Incremental processing | Versioned inputs, searchable passages, prepared snapshots and reuse for matching briefs and settings | Durable coverage across source, topic and date intervals. Carry forward outstanding work and reuse matching checks when the requested window shifts. Allow authorised manual-only sources to feed preparation |
| Fast report | Saved-evidence draft, review labels and model-free assembly. Console checks the shared dates of selected source snapshots, suggests saved dates and can wait for an existing refresh | Separate AML and CFT selections, Cybersecurity beyond the scoped UAE federal prototype, precise gaps within saved intervals and a priced backfill of those gaps that automatically completes the original report |
| News and corroboration | Claim-level support and independent-origin checks exist. Source permissions determine which content can be stored or used | Analyst publisher selection, authorised secondary ingestion and report evidence states tested on a real secondary source |

In the Hong Kong rehearsal, evidence preparation took 19 minutes 7 seconds and draft assembly took 0.196 seconds once the snapshot was ready. In the Australian and UAE federal browser rehearsals, ready-evidence drafts opened in about 5.5 seconds after the click. Those were local drafts with partial coverage and human review pending. [Hong Kong rehearsal](../eval/evidence/2026-11-11-hk-scheduled-preparation-awake.md) · [Australian and UAE rehearsals](../eval/evidence/2026-11-11-au-uae-archive-preparation.md)

### 4.4 Existing full research workflow

1. Auditor signs in and supplies topic, markets, dates and run limits. Scope and settings are saved.
2. Planner produces a visible plan. If approval is required, work pauses before fetching; approval resumes the saved plan.
3. Regulatory and industry scouts search eligible saved evidence and discover approved publications within their task scope. Newly fetched content is versioned before analysis.
4. Code checks the expected-source checklist. Missing items can trigger targeted re-planning and re-scouting within the remaining document, token, time and gap-round budgets.
5. Analyst drafts facts and contextual inferences. Factual claims receive bounded saved-first corroboration and primary quote/support checks. Partially supported facts receive at most one narrowing rewrite; inferences depend on verified supporting claims. Corroboration status remains distinct from primary support.
6. Writer selects and orders verified findings; deterministic grounding renders their saved content, readable source destinations and corroboration details. The report includes coverage and unresolved items. If writing cannot finish within the run allowance, the existing fallback preserves verified claims in a labelled partial report.
7. Reviewer inspects evidence and records accept, amend, reject or needs-evidence outcomes. Sign-off creates a separate reviewed snapshot and artifact reflecting those outcomes.
8. Auditor can re-run a finished brief and inspect new, amended and no-longer-supported findings. The original brief's date scope is retained; this is not automatically a rolling monitoring window.

The orchestrator is deterministic Python. Agent judgement is constrained by typed outputs and short evidence/claim labels mapped to stored IDs. Fetching, parsing, date extraction, versioning, budgets, coverage, diffing and rendering remain code. The verifier's separate context is not independent source corroboration and does not guarantee an independent model/provider.

### 4.5 Guest reports from the demo slides

1. The fixed QR code on the slides opens the hosted market chooser for the saved Hong Kong AML/CFT, Australia AML/CFT and UAE federal Cybersecurity (2023–2025) reports. The chooser displays a closed message until the host opens a window for five minutes or one hour. A rehearsal and the live demo use the same QR code with separate windows. The host can close the rehearsal and open a fresh one-hour window for the presentation.
2. An attendee scans the QR code, opens the public HTTPS page on their phone, chooses a market and taps **Generate report**. The page requires no account, app or API key. It displays the new draft and offers an HTML download.
3. The hosted report path uses the selected draft's pinned Supabase evidence. Each attendee receives a fresh report record and downloads the HTML from that same record, with the saved citations, coverage and review status. A report from an earlier guest session is inaccessible to a fresh session. Research, ingestion, verification, embeddings and paid provider calls stay outside the guest path.
4. When replacing a market's template, validate the frozen draft and update that market's fixed QR pointer between guest windows. Open a new window on the selected version. Check a guest download against the template's exact finding bindings and review status before using it in a rehearsal or presentation.
5. The target is **5.5 seconds or less** from tapping **Generate report** to readable report content, including when 20 guests submit at once. Measure each market on a physical phone in a fresh private browser session against the public HTTPS address. Test the audience burst separately. Check that the links reject new requests at expiry and after manual closure. Include network and browser rendering in the timing.

## 5. Evidence, correctness and report requirements

### 5.1 Evidence and temporal integrity

Where `store_text` is permitted, retain the complete extracted text in `document_versions.extracted_text` and its ordered searchable segments in `document_passages` before deriving findings. An extracted fact is an additional record linked to evidence; it never replaces the article with a summary. Therefore, retaining fact A leaves the saved text containing B and C available for later retrieval. This is extracted-text retention, not a claim that original HTML/PDF binaries are archived.

Run-specific passage selection and claim extraction are separate from storage. A saved article is not automatically fully analysed, and analysing a passage does not prove every material fact was extracted. The next pilot coverage work should record analysed/deferred passages and test multi-fact articles; this is a proposed acceptance extension, not existing exhaustive-extraction behavior.

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
5. Record why each extension is needed and which stages it changes. More connectors or saved documents do not establish improved report-citation recall. Permission-controlled original-download retention is implemented in the extension above; durable artifact storage/restore remains separate work; new capture persistence must be described accurately rather than claiming those broader gaps are solved.

#### 5.3.2 Phase 1 exit and transition to corroboration

Before Phase 2 implementation, demonstrate the targeted ingestion paths end to end through saved evidence, verification and reviewed rendering; pass relevant fixture-based coverage and evidence-integrity regressions; obtain independent diff review; and checkpoint the implementation after integrated tests/eval with local PostgreSQL. Record before/after evidence, remaining access/storage gaps and measurement limits. Separate acquisition, checklist coverage and report-citation recall.

Perfect coverage is not required. Unresolved access limitations must remain visible; a genuine prerequisite blocking safe corroboration must be resolved or explicitly scoped before that dependent work begins. Once this gate is met, proceed to Phase 2 without seeking feature approval again. Offline fixtures establish tested behavior, not live recall: further paid/live validation still requires explicit bounded authorization, and prior HK figures remain historical/pre-fix.

### 5.4 Report output

Retain v2's topic/market/period/as-of header, executive summary, regulatory developments, deadlines, jurisdiction comparison, supervisory trends, industry developments, impact assessment, re-run changes, coverage/limitations and evidence appendix. Empty sections explicitly state that no verified items were established.

Findings show stable report references, full saved wording, fact/inference status, market, supported date and date kind, source links, and priority separate from evidence confidence. Priority is research relevance, not proof of a breach. Under settled D6, impact assessment explains sourced or verified contextual risks and trends without prescribing DBS actions or business decisions.

**Reader:** the internal auditor and senior reviewer. The report body uses publication titles, readable dates, finding references and plain-language status/reasons. API payloads, database identities, hashes and capture diagnostics belong in supporting provenance, rather than being required reading for the primary workflow. Evidence links should open a verified human-readable publisher page or readable document when that destination is known. PR9 maps unambiguous English SFC circular/news content endpoints to their corresponding public pages; original acquisition URLs remain saved and frozen. Other endpoints are not guessed or silently retargeted.

The template provides contents/paragraph navigation, explicit table column widths and spacing, a narrow-screen coverage layout and a scrollable timeline. Corroboration has its own contents entry and shows dates, outcomes, quotations, source links and origin rationale. Source verification, source independence and human acceptance remain separate decisions.

Reports are static saved artifacts. Updated templates apply to new renders; previously exported files retain their prior layout and destinations. Use the latest artifact for demonstrations, and preserve historical reviewed files. A reader-friendly source link does not rewrite a saved quotation or verification input.

The current implementation renders saved claim text rather than allowing writer paraphrases. Preserve this as the proposed grounding rule; report length and executive-summary readability still require human review. HTML and structured JSON snapshots are the current output basis; no new export UI is implied.

### 5.5 Review and sign-off

For new reviewed versions, acceptance requires:

- The authoritative latest decisions are frozen into the reviewed snapshot with reviewer identity and time, using deterministic ordering for tied timestamps.
- The complete retained finding/dependency closure, passage text and quotations, document versions, citation/provenance metadata, semantic-check provenance, brief and checklist labels are frozen in a typed evidence bundle (contract 1.4, or 1.5 with corroboration). Sign-off binds worker-recorded actual verification inputs and server-captured reviewer inputs to that exact evidence; changed or unbound inputs require fresh verification/review.
- Accepted findings retain approved text. Amended findings display the amendment; rejected findings and dependent inferences do not survive in the report body or summary.
- Outstanding evidence requests on retained findings prevent sign-off. Undecided findings cannot be made reviewed merely by rendering a file.
- An inference is reviewed again after an amendment to a supporting fact; rejection propagates through dependencies.
- The signed artifact matches the frozen outcomes, has reviewer/date labels, and opens as a separate reviewed file; the unresolved-reason fallback described below is a remaining limitation. Later review events do not mutate earlier report versions.
- A failed render remains pending and does not block unrelated renders.
- Reviewed rendering and the signed review screen use the frozen bundle alone. Missing findings, dependency evidence, passages, version consistency or verification/review records prevent a reviewed artifact from being written. Later live links and metadata cannot enter an earlier signed version. Reviewed snapshot fields are immutable; artifact-path completion remains allowed.

Current implementation stores review outcomes and renders amendments without calling a model again. It replaces the amendment's title with a reviewer-amendment label and clears the original key date. Automatic evidence re-verification of human amendments is not implemented; dependent-inference re-review is enforced. **D8 must settle whether human attestation is sufficient for a material amendment.** Existing old artifacts remain historical; they are not retroactively certified by the new migration. The signed artifact is a separate `report-vN-reviewed.html`. Only the fallback for unresolved-item reasons points to the draft because some reasons are not persisted; retaining those reasons in the snapshot remains a backlog gap.

Legacy reviewed snapshots without the complete bundle refuse regeneration and never fall back to current live evidence. Their existing rendered files remain available. Historical checks and review events are not backfilled with guessed input bindings: new sign-off requires fresh checking/review where those bindings are absent. A complete frozen snapshot can still render if the live evidence becomes unavailable. Permission-controlled original-download retention is implemented in the extension above; durable artifact storage/restore remains separate work.

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
- To make the bounded semantic workload practical, the normal worker retrieves at most one eligible saved candidate passage before assessment and records that narrower limit. The assessor shows at most two primary passages and one candidate passage as exact contiguous excerpts (up to 1,800 characters each), with a 4,096-output-token ceiling inside a sixty-second claim deadline capped by the shared run deadline. Full saved passages remain frozen. Truncated or omitted context cannot establish support or a validated conflict: those decisions remain uncertain, with potential-conflict evidence retained. These are prototype workload bounds, not evidence of live latency or precision. The separately authorized sixty-second/single-candidate validation below completed 8/12 calls with zero corroboration timeouts and four output-limit failures; full acceptance remains incomplete.
- Exact quotations and matching entity, jurisdiction, predicate/scope, dates, quantities and regulatory status are required for support. A conflict requires an explicit incompatible value within the same proposition scope; a missing value is not a contradiction. Source organization/origin configuration takes precedence over supplied candidate defaults. Same publications, known aliases, same organizations, copied captures/text and shared origins are dependent; a different URL is insufficient. Independent origin requires retained exact evidence of original work on both sides. Unknown origins remain inconclusive.
- Validated conflicts take precedence. Missing, rejected or uncertain candidate assessments are explicit incomplete checks and prevent a clean positive outcome. An authoritative primary-source fact remains valid evidence without a second source; `primary_source_only` applies when there is no unresolved candidate, while incomplete candidate checks are `inconclusive`. Absence of a check is `not_checked`.
- Auditors see statuses, dates, exact passages, origin decisions/reasons, source links, limits and acquisition provenance separately from fact verification and human decisions. Existing review decisions acknowledge the captured assessment; no universal two-source sign-off rule or automatic DBS action recommendation is introduced. Maker/checker and material-amendment policies remain D5/D8.
- Assessments append to a worker-written, workspace-readable ledger ordered by a server sequence. Each assessment binds an acyclic base evidence input; actual verification and reviewer inputs include its complete immutable result and candidate evidence. New/changed assessments require fresh verification and review. A changed or superseded candidate blocks a new sign-off. Contract-1.5 reviewed bundles freeze assessments and evidence; later queries never alter earlier reports. Complete contract-1.4 bundles remain readable, with absent corroboration treated as not checked. No historical assessments or verification bindings are invented.

The local fixture evidence includes a saved independent investigation flowing through the normal fact-verification path into a signed report, rejection of stale candidates for a new sign-off, stable historical rendering after later changes, copied/shared origins, missing decisions, contradictions, budget exhaustion and workspace isolation. Live precision of the corroboration assessor remains unmeasured. Existing delivered slides/video retain their historical evidence cut; use the current feature-status handoff before making new presentation claims.

## 7. Evaluation and release evidence

**Audience:** product owner, evaluator and technical reviewers. This section keeps software verification, publication coverage and human judgement distinct; the competition overview links here for the supporting record.

Current engineering checkpoint: **560 tests + 8 subtests, none skipped (54.55 seconds)** at the PR9 implementation; independent focused review found no blockers. The subsequent merged tree has the same tested code. Tests use controlled providers and local PostgreSQL/Chromium fixtures. The [source-link handoff](agent-handoffs/auditor-source-links.md) records commands and four browser-verified publication destinations.

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

Recorded Hong Kong research runs produced the dated results below:

| Run | Document allowance | Findings: facts / inferences / unresolved | HK publication recall | Elapsed / estimated cost |
|---|---|---|---|---|
| Baseline `80ffbc29…` | 15 | 6 / 1 / 1 | 1/18 overall | 10.35 min / $0.7135 |
| Initial coverage fix `ebac84e8…` | 15 | 10 / 1 / 3 | 2/18 overall | 13.22 min / $1.1883 |
| Final capacity run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0` | 30 | 17 / 1 / 1 | 7/18 overall; 7/14 regulatory | 15.29 min / $1.4395 |
| Fresh telemetry diagnosis `e2fda30f-36f9-4aa3-83c3-d78b81671b83` (pre-fix) | 30 requested; 32 saved versions | 19 / 0 / 5 | 9/18 overall and fetchable; 9/14 regulatory | 21.68 min / $1.8290 from recorded steps |
| Latest authorised `7be59cdf` (8 November; partial fallback) | 30 | 19 / 0 / 3 | 5/18 cited; 6/18 acquired | 25.00 min / $2.2638 recorded model estimate |
| Labelled-precision run `29a153bb-ffa2-40a1-a702-3abc828bed4c` (Haiku; code `83e3b32`) | 40; 34 used | 19 / 2 / 4 | 11/18 overall; 11/14 regulatory; 11 of 13 reachable | 9.6 min / $0.128 |

Run `29a153bb` is the first with human-labelled precision ([evidence](../eval/evidence/2026-11-07-hk-run-29a153bb.md)). All 21 draft-report claims were labelled by one team member who had not seen the verifier verdicts: **0 unsupported or contradicted**, **7/21 fully supported** on passage text, and **17/21** when each document's recorded publication date is accepted as date evidence. Neither meets the proposed ≥95%. The four remaining partials overstate the source's hedges, scope, addressee or attribution, and all passed the semantic check; tightening Gate 2 on these is the evidenced next accuracy step. Caveats: one run, one labeller, Haiku models on code that predates PR4 and PR6, self-review sign-off, and a provenance defect: the stored `model_settings` lists Opus/Sonnet while every step recorded `claude-haiku-5-5`. It is not a controlled comparison with the earlier runs.

The earlier capacity run allowed **30 documents, 600,000 tokens and 25 minutes**, used **302,985 tokens**, cited **10 primary publications**, and remained partial because it reached the document budget. Its larger allowance prevents interpreting it as an equal-budget quality comparison. Ten cited publications and seven benchmark matches measure different sets.

The single fresh telemetry run used the same requested limits and recorded **372,220 tokens** and **13 distinct cited source URLs**. A malformed HKMA PDF URL aborted a scout. Its partial work was lost from diagnostics and budget accounting, allowing **32 saved versions despite the requested 30-document limit**; failed requests are additional to saved-version counts. Usage/cost from that failed scout may also be missing. This is not an equal-enforced-budget comparison or a post-fix coverage gain. The URL is now encoded safely, invalid requests become per-document failures, and failed scouts retain diagnostics/known usage and consume the later gap budget. These fixes were validated offline; no second live run was made. Three missed SFC enforcement publications were discovered and presented with one slot remaining; selection/capacity remains a coverage issue. Other misses include access/storage constraints and incomplete discovery evidence. See [the diagnosis](agent-handoffs/hk-telemetry-diagnosis.md).

Local, ignored artifacts are `reports/2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0/report-v1.html`, `coverage-comparison.json` and `precision_worksheet.csv` in that run directory. That worksheet has **18 unlabelled rows**; it is not a precision result. These generated artifacts are local evidence, not checkpointed deliverables or remote deployment.

Authenticated sign-in, evidence inspection, amendment/rejection, dependent re-review, sign-off and separate reviewed-artifact opening have been rehearsed locally with synthetic evidence. The approved 180-second HyperFrames/Remotion film now joins a new UI-created synthetic brief, fixture-configured optional approval and recorded progress with saved HK evidence inspection and the separate synthetic review rehearsal. Chapters and omitted processing time are disclosed. Final MP4 decode/browser playback and the paired 16-slide PowerPoint package passed delivery checks. This is a product showcase assembled from separate observed examples. Human-review the benchmark and precision worksheet, then run the agreed comparison under D3/D9. See [the film handoff](demo/launch-production-handoff.md).

### 7.4 Demo market scope and readiness

The public QR rehearsal uses the three saved snapshots listed in §4.5. These reports demonstrate the guest flow and retain their coverage and human-review labels. The broader preparation and discovery criteria below apply to the separate market-readiness milestone.

**Hong Kong proof of concept.** Use the saved Hong Kong AML/CFT draft for **4 November 2025 through 4 November 2026**. Show guest report generation from the prepared snapshot, then open a finding and follow its citations. The HKMA politically exposed persons example shows a verified inference and its supporting evidence. Keep the draft and partial-coverage labels visible. Report generation from this snapshot uses zero paid API calls. Use the Singapore publication inventory to show planned coverage. The four-publisher news pilot and its quote-pending licence fees belong in the stakeholder expansion discussion.

**Hosted Hong Kong update, 12 November.** The first hosted update used the saved draft with **133 machine-supported findings**, including 33 additions from the SFC validation. It scored **16/18 cited publications** on the corrected Hong Kong benchmark, retaining all ten baseline matches and adding all six SFC publications. Mira analysed **38 of 40** pinned passages. Two failed because their proposed dates lacked support in the cited text. Both publications were cited from other checked passages. The local preparation and targeted retry took 30 minutes 50 seconds through draft save, with US$5.80 in estimated model charges. An anonymous request through the hosted QR returned the updated draft with all **133 exact finding bindings** and the human-review-pending label. The previous draft and the Australia and UAE pointers were preserved. [Validation record](../eval/evidence/2026-11-12-hk-sfc-hosted-download.md)

**SFC footnote correction, 12 November.** Corrected extracts for 26EC13 and 26EC39 separated superscript footnotes from dates. Mira verified six additional findings from the two passages and retained all 392 exact citation bindings from the 133-finding draft. The fixed QR now selects the **139-finding draft** for the next guest window. A hosted anonymous download rehearsal preserved all 139 exact finding and review bindings and the human-review-pending label. The draft still scores **16/18** overall and **14/14** for regulatory publications. The outstanding items are Wolfsberg's June risk-based approach guidance and July guidance on banking services for non-bank payment providers. Both are in-period industry guidance. The source currently permits metadata and fetching in Mira. Adding them to a downloadable report requires an approved basis for storing and analysing the evidence and quoting it in guest downloads, followed by claim verification. [Footnote and Wolfsberg assessment](../eval/evidence/2026-11-12-hk-sfc-footnote-followup.md)

In the 11 November public rehearsal, all three drafts were readable by the 4.2-second check on a physical iPhone using Chrome Incognito over Wi-Fi. Hong Kong returned 14 facts and one verified inference, Australia returned 85 facts, and UAE federal returned 13 facts.

The first audience test returned eight drafts for 20 simultaneous requests to the Australian link. After adding separate guest slots, reusing the evidence checks prepared at window opening and spacing retries, all 20 isolated mobile browser sessions opened a draft on the public site in 0.82–2.66 seconds, with a 1.73-second median. All 20 requests used the same one-hour window and pinned Australian snapshot, produced distinct saved reports, and started zero new preparation or analysis jobs. The load test ran on one Mac. Cellular and simultaneous physical phone timing remain unmeasured.

Use **4 November 2025 through 4 November 2026, inclusive** for the demo planning window. The existing inventory and estimates cover official banking AML and CFT. The planning assumption is to prepare Cybersecurity for HK and SG in the same window, with a separate bank-relevant publication inventory and estimate. Monetary authorities and relevant official legislation, consultations, guidance, enforcement and commencement events form the required source set. Include applicable baseline versions where needed to interpret in-window developments. Secondary outlets are optional, subject to explicit selection and permission.

| Market | Market-readiness milestone | Readiness and preparation estimate |
|---|---|---|
| Hong Kong | Complete preparation | The hosted AML/CFT draft cites 16/18 publications in the scoped benchmark. The separate banking inventory, remaining passage analysis and Cybersecurity coverage still need reconciliation before full market readiness. [Hosted validation](../eval/evidence/2026-11-12-hk-sfc-hosted-download.md) · [Preparation plan](plans/2026-11-11-hk-sg-demo-coverage.md) |
| Singapore | Complete preparation | No prepared snapshot in the assessed demo workspace. Reconcile the official inventory, obtain permission for intended MAS use and enable authorised manual-only evidence in prepared reports. Use permitted legislation imports where needed. Official banking AML/CFT planning estimate is 30–80 batches and US$3–12 in model charges. [Manual import guide](../data/manual/README.md) · [Current preparation rules](../supabase/migrations/20261110180000_mira_prepared_evidence.sql) |
| UAE | Discovery only | Reuse the scoped federal publication discovery evidence. Record uncovered source categories and publisher approval requirements for the demo inventory. [Source discovery pilot](../eval/evidence/2026-11-10-country-method-pilot.md) |
| Australia | Discovery only | Reuse Federal Register and scoped AUSTRAC discovery evidence. Reconcile the demo-period publication and version list. [Source discovery pilot](../eval/evidence/2026-11-10-country-method-pilot.md) |
| Indonesia | Discovery only | Identify official publication routes and applicable source permissions, then build and size the initial inventory. There is no controlled Indonesia research scope in the current prototype. |

**Complete preparation** requires an agreed source and publication inventory, a recorded disposition for each expected category, and every in-scope publication acquired in a permitted form, extracted and searchable. Retain publisher originals where permitted. Resolve missing files, failed extraction and all outstanding eligible passage analysis and checks. Any included report finding must cite its frozen verification evidence. A blocked required publisher or publication keeps the affected scope incomplete until permitted evidence resolves it. Track publication coverage, passage processing and human review separately.

**Discovery-only acceptance** requires a deduplicated list of candidate publications and versions with publisher, URL, dates, topic, access or manual status, and any exclusions or unresolved categories. Estimate publication volume, operator time and any paid search or later preparation charges from that list. Manual and native catalogue discovery can proceed with US$0 in model charges. Full acquisition, passage analysis and indexing are outside this demo requirement for these three markets.

For later preparation sizing, the scoped Australian and UAE federal archive run analysed 45 of 1,198 candidate passages in about 14 minutes. It recorded US$1.97 in estimated usage and US$0.27 reserved for uncertain usage. Use that as a partial-run reference when pricing further preparation from each inventory. [Archive run](../eval/evidence/2026-11-11-au-uae-archive-preparation.md)

The combined HK/SG official banking AML/CFT estimate is **97–198 batches, US$9–29 and approximately 1–3.5 hours of model processing** at four concurrent calls. It assumes up to three passages per batch and includes verification and occasional rewrites. The estimate uses saved passages, missing-document page counts and allowances for short publications and applicable statutory sections. Refresh it after permitted extraction and deduplication. Budget separately for Cybersecurity, optional news, licences, manual collection and human review. The broader milestone is ready when HK and SG meet the scoped completion gate, a covered report opens within five minutes, and each of the other three markets has its discovery inventory.

#### Optional news expansion and publisher fees

**Publisher licence fees are quote pending** for all four outlets. Show them separately from the API estimate under expansion costs on the stakeholder slides. The technical demo uses prepared evidence and focuses on the report workflow.

The initial news pilot is estimated at **US$5–11 in API charges** across both markets. Assume 12 months of discovery, three Exa Auto searches per outlet per month with up to ten results per search, and five distinct articles per outlet for analysis and verification. Exa costs US$0.007 per search before credits. The model allowance applies the existing estimate for ten articles to each market. Reprice once the permitted, deduplicated article list is known. [Coverage and cost plan](plans/2026-11-11-hk-sg-demo-coverage.md) · [Exa pricing](https://exa.ai/pricing)

| Pilot scope | Articles | Exa discovery | Analysis and verification | Estimated API total |
|---|---:|---:|---:|---:|
| Singapore · CNA and The Straits Times | 10 | US$0.50 | US$2–5 | US$2.50–5.50 |
| Hong Kong · South China Morning Post and RTHK English News | 10 | US$0.50 | US$2–5 | US$2.50–5.50 |
| **Combined** | **20** | **US$1.01** | **US$4–10** | **About US$5–11** |

| Market | Candidate publisher | Coverage and reuse status |
|---|---|---|
| Singapore | CNA | Candidate for local and regional coverage. Check terms and fees for the intended reuse with Mediacorp. [Rights enquiries](https://www.channelnewsasia.com/contact-us/help-and-feedback) |
| Singapore | The Straits Times | Candidate for Singapore banking and policy coverage. Check reuse rights and fees with SPH Media. [Content-use terms](https://www.sph.com.sg/tnc/website) |
| Hong Kong | South China Morning Post (SCMP) | English-language banking and finance coverage, including bank technology incidents. Its terms require prior express written consent for automated extraction, indexing and AI use, including use through third parties. [Banking and finance](https://www.scmp.com/business/banking-finance) · [Terms, §3.2](https://www.scmp.com/terms-conditions?module=footer&pgtype=page) |
| Hong Kong | RTHK English News | Public broadcaster with coverage of local scams and enforcement. RTHK ranked among the most trusted brands in the Reuters Institute’s 2026 Hong Kong survey. Confirm reuse rights and fees for news text with RTHK. [Coverage example](https://news.rthk.hk/rthk/en/component/k2/1868796-20260904.htm) · [Trust survey](https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2026/hong-kong) · [RTHK contacts](https://www.rthk.hk/contactus/index_en.html) |

Keep these outlets as candidates until the workspace records permission for the intended collection, storage, analysis and report use. Cite regulators and legislation for regulatory requirements. Treat news as context or corroboration where the underlying reporting independently supports the claim.

## 8. Source permissions, security and operational constraints

Retain v2's public-data boundary, workspace access controls, server-side credentials, initiating-user audit trail, source allow-list, redirect/private-address checks, robots/rate limits, bounded size/type handling, untrusted-source instructions and versioned provenance. Fixtures demonstrate particular guardrails, not universal resistance to injection or hallucination.

The baseline scout retained extracted text/passages. The evidence-completeness extension adds optional permitted original HTML/PDF bytes in private local storage; rendered report files also use the local filesystem. Frozen snapshots solve reviewed evidence identity, not original-capture retention, artifact durability or restore. Ingestion expansion and corroboration are implemented locally under the Phase 1/2 gates, including frozen acquisition provenance and new reviewed corroboration snapshots. The default remains local; optional private Storage and verified recovery are implemented in the follow-up above, with hosted deployment, backup scheduling and provider recovery acceptance still operator work. Source-permission changes, additional paid/live calls and remote deployment are not implied by that authorization.

The repository records MAS automated access as blocked and written storage permission as outstanding, despite prototype seeding allowing text storage. This is an existing unresolved project decision, not confirmation of permission. Other named industry sources have fetch/metadata permission without stored passages, constraining citable coverage. Manual acquisition does not itself settle storage permission. D4 must identify permitted demo evidence, remaining source reviews, and the owner/refresh schedule for imported documents. MAS remains inactive in the current validation/demo configuration. Explicit source grants are still required; a seeded operation is not permission to bypass that configuration.

Budgets are runtime configuration, not product promises. Code defaults currently include 60 fetched documents, 2,000,000 tokens, 15 minutes and two gap rounds; `.env.example` supplies a 300,000-token development setting; CLI examples can choose a smaller document allowance. Record actual run settings instead of treating one of these as an agreed cost cap. Providers and per-role models are configurable; actual configuration and costs require D3 agreement.

## 9. Settled decisions and remaining policy work

This register is for the product owner and delivery team. Settled decisions guide implementation; open items define pilot/enterprise acceptance work. Routine correctness fixes preserve the existing approved behavior. Recorded targets and proposed operating policies do not become approved solely because the implementation exists.

| ID | Decision needed | Recommendation, not approval | Owner / affected work |
|---|---|---|---|
| D3 (carried) | Which per-role model setup, token/document limits and cost cap are acceptable for demo and comparison runs? | Pin actual settings and a per-run plus total evaluation allowance; preserve public-data-only input | Product owner + team; spending and live evaluation |
| D4 (carried) | Which sources may supply stored demo evidence, who completes permission reviews, and who imports/refreshes blocked material? | Use explicitly permitted evidence and disclose unresolved SG/industry gaps; do not infer permission from fetchability | Product owner + curator; source expansion/import policy |
| D5 (carried) | Who is the sign-off reviewer, and is self-review acceptable in the prototype? | Name a senior auditor proxy and record whether maker/checker separation is required | Product owner; review access and demo claims |
| D6 — settled | User approved contextual risks/trends without generated DBS audit actions or business decisions | Preserve this boundary; auditor decides actions | Settled scope; prompts, verifier and report |
| D7 — prototype implemented; enterprise policy open | Corroboration follows the Phase 1 gate in §5.3.2; define eligible claims, independence, search allowance and sign-off consequences | Prototype checks factual claims with explicit bounded limits, origin evidence and existing reviewer sign-off; adopt or revise this policy explicitly before enterprise rollout | Product owner + reviewer; corroboration design/schema/report |
| D8 (new) | Can material reviewer amendments be signed off on human attestation alone, or must they pass evidence verification again? | Require explicit evidence review and dependent-inference re-review; decide whether automated recheck is mandatory | Reviewer + product owner; amendment workflow and verification |
| D9 (new) | What is the accepted benchmark scope, recall denominator, multi-agent improvement threshold and replacement for the unmet pre-build M0 gate? | Human-review eligible items, show all/fetchable subsets, retain caveats and use a forward demo evidence gate | Product owner + evaluator; scorer and presentation conclusions |
| D10 — market scope settled | Complete preparation for Hong Kong and Singapore. Discovery only for UAE, Australia and Indonesia | Use the completion and discovery criteria in §7.4. Source permissions and precise publication inventories remain delivery work | Product owner + curator, demo acceptance |

**Remaining priority policies:** D7 detail (not feature approval), D8 (amended evidence) and D9 (measurement). D6 is settled. Source permissions and budget policy also remain open; adapters or seeded rows do not close them. Approval to update this draft does not adopt every proposed target or remaining policy.

## 10. Delivery order and specialist work

The current demo priority is to reconcile the HK and SG inventories, resolve the MAS permission and manual preparation path, and size Cybersecurity for both markets. In parallel with corpus preparation, add the analyst setup, monthly scheduling and report gap workflow in §4. Complete the UAE, Australian and Indonesian discovery inventories and rehearse a covered report and a date-gap request. Preserve the delivered evidence and evaluation checkpoints below.

1. **Preserve the completed evidence-integrity checkpoint:** full frozen evidence, incomplete-render blocking and version-aware retrieval are implemented and locally validated. Preserve v1/v2 and historical artifacts; no input-binding backfill or remote migration.
2. **Phase 1 merged:** inspect existing designs/code and retained telemetry; choose justified Exa/browser extensions and address evidenced selection/capacity gaps under §5.3.1. Complete and document §5.3.2 before dependent corroboration implementation. Scoped live observations below do not establish full coverage recovery; no repeated paid runs without new bounded authorization or reconstruction of missing historical diagnostics. MAS and industry-source permission gaps remain disclosed.
3. **Phase 2 merged:** saved-first corroboration, bounded optional acquisition and frozen evidence/decisions implement §6. Prototype defaults are explicit; enterprise adoption remains D7. Independent reviews and the complete integrated suite passed. Live semantic/origin precision remains unmeasured.
4. **Complete evaluation:** adopt D9 measurement policy, human-review the benchmark, show recorded publication dates in the precision worksheet, add a second labeller, fix the `model_settings` provenance mismatch, tighten Gate 2 on hedges/scope/attribution, and run the agreed comparison only within authorized budgets. Run narrow regressions during development and one complete tests/eval suite with local PostgreSQL per integration milestone; repeat only for changed code or failures. Record the exact tested scope and separate offline evidence from live quality claims.

5. **Keep delivered slides/video aligned with demonstrated behavior:** the storytelling deck and approved 180-second product/workflow film are packaged. New ingestion/corroboration behavior needs observed evidence before inclusion as working functionality; retain synthetic/historical and edited-time disclosures. No accepted precision, M0 win or production-deployment claim is established.

This order records the user's current direction. Specialist work should use bounded, reviewable tasks; it does not adopt remaining open policies or permit new source storage.

## Appendix A. Requirement continuity

V2 IDs remain useful for code/test traceability. No unmet requirement is silently removed by observing a narrower implementation.

| V2 ID | Disposition in this draft | Main code / acceptance evidence |
|---|---|---|
| AG01 Brief | Controlled SG/HK/AU/AE selection; UAE federal source scope; wider expansion deferred | `mira/brief.py`, `mira/contracts.py`, `tests/test_brief_budget.py`, `tests/test_mixed_sources.py` |
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

## Appendix C. Dated engineering record — team reference

The entries below preserve what was implemented and measured at each checkpoint. Earlier statements such as “not merged” or an older suite count describe that entry's date/source. The current merged checkpoint is §1; these entries do not replace it.

### 8 November 2026 initial implementation evidence

The ingestion-first gate exited at `83c84c1`: 378 tests plus 8 subtests, none skipped, including local PostgreSQL. Generic candidate-retention ablation reaches 123 rather than 120 selection-frontier attempts with equal document allowance and an extra selection call; it does not establish saved-publication or report-citation recall improvement. URL discovery is metadata only; reports require separately permitted saved passages. Offline Chromium capture was exercised with synthetic HTML, scripts disabled and all resource routes aborted; pages needing external scripts/data remain unsupported. Capture/extraction identities and non-retention status enter verification and frozen review inputs. The normal HTTP scout retains its existing per-request timeout; new bounded corroboration uses a persistent, killable acquisition broker and shrinking database statement deadlines.

Upstream PRs 4–6 were merged during this implementation and are preserved, including numeric quote checks, category seeding and scout budget guards. A separate team-recorded [HK run/precision worksheet](../eval/evidence/2026-11-07-hk-run-29a153bb.md) reports 11/18 citation recall and 7/21 strict versus 17/21 publication-date-adjusted supported claims. PR8 links that document as historical measured evidence; it records one labeller, self-review and a model-provenance mismatch, and predates these features and the integrity/guardrail updates. Its labels are not post-feature precision or an accepted release gate. Historical runs in §7.3 retain their original unlabelled-precision caveats. This task performs no paid/live research/model calls, no remote migrations, no model-setting changes and no historical report rewrites.

Final integrated validation at implementation `42efc32`: **459 tests plus 8 subtests, none skipped, 13.83 seconds**, including local PostgreSQL and offline evaluation. New migrations are local only. Independent review found no remaining important issues. See [integration handoff](agent-handoffs/ingestion-corroboration-integration.md) for exact commands, remaining limits and publication state.

### 8 November 2026 PR7 follow-up: actual computer/browser acquisition

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


### 8 November merged delivery and auditor readability

PR7 merged at `33b6be6` after the current branch incorporated PR8's documentation/slides and retained PR6 guardrails; the integrated tree passed 538 tests + 8 subtests, none skipped. PR9 merged at `95bd1f8`; its source-link implementation passed **560 tests + 8 subtests, none skipped (54.55 seconds)**. No model, source-permission or remote-migration change accompanied those merges.

Report template `report/6` combines the table-spacing changes with reader-facing source links. Browser checks confirmed readable SFC pages for 26EC69, 26EC2, 26EC39 and 26PR19. The explicitly updated current draft has 24 corrected anchors across those four publications; other report content and saved evidence remain unchanged. Older exports remain historical files. See [auditor-source handoff](agent-handoffs/auditor-source-links.md).

### Evidence-completeness validation — 8 November 2026

The final integrated candidate passed691tests+8subtests with no skips in92.39seconds. New coverage includes complete scoped saved versions, checklist-only inspection references, atomic claim/disposition persistence, frozen failure reasons and strict terminal states; permitted-original storage/authentication/integrity and signed identity races; PDF page links; and optional semantic fusion, source/version filtering, content-bound caches, hard process deadlines and measured/unknown usage. The initial full run identified six old task stubs missing jurisdiction fields; these were corrected to match the real contract without relaxing production checks. Independent review findings were fixed with regressions. No new paid/live coverage measurement, MAS activation, remote migration, role-model change or source grant accompanied this validation. See the [implementation handoff](agent-handoffs/evidence-completeness.md).

### Durable-evidence validation — 8 November 2026

The final integrated candidate passed **939 tests +8 subtests,none skipped,in64.05s** with local PostgreSQL17 and actual Chromium. New scope includes verified private object publication and app reads, source/bucket RLS, immutable retries, full snapshot/package/native recovery mechanics, legacy HTML/original preservation, and frozen/as-of-bound offline quality measurement. Native restore drills use disposable synthetic databases; actual SDK tests use offline HTTP transport. No hosted Storage deployment, whole application-schema hosted recovery, new paid research or precision gain is claimed. The interrupted test run and temporary database-unavailability replay are recorded in the [current handoff](agent-handoffs/durable-evidence-checkpoint.md); the passing candidate followed a reachability check. Existing research results remain dated and unchanged.

### Configured embedding validation — 10 November 2026

The separately authorized controlled embedding validation passed through the actual configured API, PostgreSQL cache and scout bridge: two requests,45tokens,3.719seconds, with MAS excluded and no research acquisition. Fresh regression proof: **939 tests +8 subtests,none skipped,in72.35s**, including local PostgreSQL and actual Chromium; source-scoping, process deadlines, fallback and usage regressions passed. See the [hybrid result](../eval/evidence/2026-11-10-hybrid-embedding-validation.md) and [handoff](agent-handoffs/hybrid-retrieval.md). The live fixture result is not a new HK recall/precision measurement. Source grants and agent role model settings remain unchanged.
