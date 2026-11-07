# Mira Product Requirements v3 — reconciliation draft

Agentic external-driver research for internal audit

**Date:** 7 November 2026 (Asia/Singapore). **Status:** revised draft; remaining open policies await adoption. **Audience:** Nathaniel, Ewen, Saai, the product owner, and the coding agent.

This is a separate update to [PRD v2](mira_PRD_v2.md); neither v2 nor [archived v1](archive/mira_PRD_v1.md) is replaced or deleted. V2 remains the approved baseline until the team adopts this draft. This document records current behavior, gaps and proposed requirements separately; an implementation choice is not evidence of product approval.

## 1. Basis and limits of this reconciliation

The original reconciliation compared v2 with HEAD `1d38e8916120d45d063d5157abcac6fc2db1af6f` and active working changes. This revision incorporates the subsequent correctness fixes, local PostgreSQL validation and live Hong Kong coverage results confirmed on 7 November 2026. Inputs include the user's pasted development handoff, [DBS problem statement](dbs_project_statement.md), [rubric](project_grading_rubrics.md), [approved sources](mira_approved_sources.md), [benchmark](mira_m0_ground_truth.md), [single-agent design](single_agent_arm_design.md), README, application code, migrations and tests.

The working tree was changing during inspection. This is a dated snapshot, not certification of the agent's eventual final branch. Read executable behavior and tests ahead of stale comments: for example, the orchestrator module header still lists plan approval and re-run diff as unbuilt even though their execution paths exist.

Original reconciliation validation returned **222 passed, 40 skipped, 8 subtests passed**. Current validation supersedes that limitation: local migration `20261107120000_mira_reviewed_report_outcomes.sql` is applied, and the full suite returned **280 passed and 8 subtests passed**, with PostgreSQL tests included and none skipped. Integration tests use scripted providers. Separate live Hong Kong research runs also completed; neither these tests nor those runs establish human-labelled precision, a browser rehearsal or remote deployment. No remote migration is claimed.

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
- One prototype workspace using Supabase Auth and workspace-scoped access.

### Deferred unless separately approved

Third jurisdiction, region expansion in the brief UI, scheduled monitoring, news-triggered investigations, 20–30-year archive/backfill, OpenSearch, theme discovery, internal bank uploads, control mapping, production deployment, PDF/DOCX export and email delivery. Open-web fallback is described in v2 but no enabled runtime workflow was established here; it remains deferred rather than assumed available.

**D6 settled by the user:** Mira may explain sourced contextual risks and trends, but must not generate DBS audit actions or business decisions. The auditor decides and acts. This approved boundary updates v2's suggested-audit-actions requirement.

## 3. Current state compared with v2

| Area | V2 expectation | Observed current state | Classification / implication |
|---|---|---|---|
| Brief and access | Controlled brief saved as a Project revision; optional plan approval | Authenticated UI, saved brief, approval pause/resume and controlled SG/HK scope exist | Present; general region expansion not exposed |
| Orchestration | Planner, parallel scouts, analyst, verifier, completeness, writer | Code controls parallel scouting, budgets, cancellation, step records and typed outputs | Present; live HK breadth measured below, wider coverage remains incomplete |
| Sequence | Diagram places verification before completeness-driven follow-up | Execution checks coverage and fills source gaps before analysis and verification | Document the actual sequence; do not imply post-verification claim repair |
| Discovery and evidence | Approved HTML/PDF sources, stored versions and passages | Feeds, hubs, selected links, PDF follow-through, source scoping, reuse and manual import exist | Present; a retrieved page is not proof of adequate research |
| Retrieval | Full text plus local embeddings/semantic search | Current scout retrieval uses full text; vector schema support is not an active embedding pipeline | Gap against v2; defer embeddings pending measured retrieval failures |
| Fact verification | Quote match, fresh-context semantic check, one partial rewrite | Implemented; unsupported claims excluded, inference dependencies checked | Present; accuracy rate unproven |
| Metadata verification | Dates, market and status must be supported | Inference verification now receives displayed metadata and supporting claim metadata | Present; regression validated; human precision remains unlabelled |
| Coverage | Expected-source list, no-change evidence, gap rounds | Item-linked findings and inspected passage labels; imported evidence considered before manual-source fallback | Present; relevance and publication-level completeness still need review |
| Claim-level follow-up | Unsupported claims get a targeted second research attempt | Current gap loop repairs expected-source gaps before verification; no equivalent post-verifier research loop found | Gap; distinguish from source gap filling and corroboration |
| Writer and report | Condense verified claims into structured sections | Writer selects/orders; code renders full saved verified claim text, fills omitted main-section findings, labels facts/inferences and dates | Present; more restrictive than v2's paraphrasing allowance |
| Audit impact | Risks, opportunities and suggested audit actions | Contextual risks/trends allowed; DBS actions and business decisions remain with the auditor | D6 settled by user |
| Human review | Decisions then reviewed report | Decision UI and applied local migration freeze latest outcomes, apply amendments/rejections, block evidence requests and stale dependent reviews | Present; PostgreSQL regressions passed, browser rehearsal outstanding |
| Re-run | Saved brief, previous run link, findings diff | UI/CLI paths and verified-finding diff exist | Present; compare same scope; do not imply automatic scheduling |
| Corroboration | No explicit independent-second-source requirement | Approved as a future feature after coverage; no runtime implementation | Detailed D7 policy remains design work |
| Evaluation | Coverage, precision, time, cost; three arms | Scorer supports market/date scope, explicit official URL aliases and CLI flags; HK live recall measured | Human benchmark acceptance and precision labels outstanding |
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

Publication-level completeness remains distinct from finding a category page. SFC enforcement and other publications, MAS access and industry storage permission remain gaps. Dated live HK results are in §7.3; the larger-capacity run remains partial and is not an equal-budget comparison.

### 5.4 Report output

Retain v2's topic/market/period/as-of header, executive summary, regulatory developments, deadlines, jurisdiction comparison, supervisory trends, industry developments, impact assessment, re-run changes, coverage/limitations and evidence appendix. Empty sections explicitly state that no verified items were established.

Findings show stable report references, full saved wording, fact/inference status, market, supported date and date kind, source links, and priority separate from evidence confidence. Priority is research relevance, not proof of a breach. Under settled D6, impact assessment explains sourced or verified contextual risks and trends without prescribing DBS actions or business decisions.

The current implementation renders saved claim text rather than allowing writer paraphrases. Preserve this as the proposed grounding rule; report length and executive-summary readability still require human review. HTML and structured JSON snapshots are the current output basis; no new export UI is implied.

### 5.5 Review and sign-off

For new reviewed versions, acceptance requires:

- The authoritative latest decisions are frozen into the reviewed snapshot with reviewer identity and time, using deterministic ordering for tied timestamps.
- Accepted findings retain approved text. Amended findings display the amendment; rejected findings and dependent inferences do not survive in the report body or summary.
- Outstanding evidence requests on retained findings prevent sign-off. Undecided findings cannot be made reviewed merely by rendering a file.
- An inference is reviewed again after an amendment to a supporting fact; rejection propagates through dependencies.
- The signed artifact matches the frozen outcomes, has reviewer/date labels, and opens as a separate reviewed file; the unresolved-reason fallback described below is a remaining limitation. Later review events do not mutate earlier report versions.
- A failed render remains pending and does not block unrelated renders.

Current implementation stores review outcomes and renders amendments without calling a model again. It replaces the amendment's title with a reviewer-amendment label and clears the original key date. Automatic evidence re-verification of human amendments is not implemented; dependent-inference re-review is enforced. **D8 must settle whether human attestation is sufficient for a material amendment.** Existing old artifacts remain historical; they are not retroactively certified by the new migration. The signed artifact is a separate `report-vN-reviewed.html`. Only the fallback for unresolved-item reasons points to the draft because some reasons are not persisted; retaining those reasons in the snapshot remains a backlog gap.

## 6. Approved future corroboration feature — after coverage

Source verification asks whether a cited source supports a claim. Corroboration asks whether another independent source supports the same material proposition. Two URLs, a landing page and its PDF, a mirror, or a publisher repeating an original announcement are not automatically independent evidence.

The user approved adding corroboration after coverage. It has no runtime implementation. The following requirements guide further design under D7:

1. Search eligible saved evidence first, then perform a bounded targeted search of approved sources only.
2. Save supporting documents/passages and the relationship to the claim before making a corroboration judgement.
3. Record source identity, provenance/independence rationale, agreements or contradictions, checked time, search attempts and stop reason.
4. Display distinct outcomes such as independently corroborated, primary-source only, conflicting evidence, not checked and inconclusive. Failure to find a second source is not proof a primary-source statement is false.
5. Keep contradictions visible for review; do not inflate confidence solely from source count. Official obligations remain anchored to the authoritative issuer.

Recommended starting policy: apply corroboration selectively to material non-authoritative assertions and disputed claims; permit authoritative regulatory statements as clearly labelled primary-source-only evidence. Feature approval does not settle this detailed policy or add runtime permissions/schema. Claim eligibility, independence criteria, search allowance and sign-off effects remain design work; do not seek feature approval again. Slides must describe corroboration as approved future work until implemented and demonstrated.

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

These remain proposed targets. The live recall measurements below are development evidence, not accepted product scores. Human-labelled precision, time-saving evidence and a final multi-agent verdict remain outstanding; no M0 win is claimed.

The existing live runner shares an evidence store and runs multi-agent, then single-agent, then plain search. Disclose that later arms inherit evidence, that plain search is over saved evidence, and that this is not an isolated cold-start experiment. The current decision code treats any positive coverage or precision difference as a win, while the comparison design warns that one or two items can be noise. D9 must settle the decision threshold and evaluation design before results are presented.

V2's M0 was a pre-build gate; it cannot now be represented as having passed retrospectively. The scorer uses ≥50% **fetchable** recall, whereas v2's wording does not explicitly select that denominator. Recommend preserving the historical record and adopting an explicit evidence gate for demo readiness, pending D9.

### 7.3 Current validation and live HK evidence

The local review migration is applied. Full-suite validation returned **280 passed and 8 subtests passed**, including PostgreSQL with no skips and scripted integration providers. The four implemented correctness fixes cover immutable review outcomes/latest ordering, displayed inference-metadata verification, item-linked no-change inspection, and imported evidence for sources that cannot be fetched. A browser rehearsal, human precision review and remote deployment remain outstanding.

Live HK runs on **7 November 2026** produced:

| Run | Document allowance | Findings: facts / inferences / unresolved | HK publication recall | Elapsed / estimated cost |
|---|---|---|---|---|
| Baseline `80ffbc29…` | 15 | 6 / 1 / 1 | 1/18 overall | 10.35 min / $0.7135 |
| Initial coverage fix `ebac84e8…` | 15 | 10 / 1 / 3 | 2/18 overall | 13.22 min / $1.1883 |
| Final capacity run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0` | 30 | 17 / 1 / 1 | 7/18 overall; 7/14 regulatory | 15.29 min / $1.4395 |

The final run allowed **30 documents, 600,000 tokens and 25 minutes**, used **302,985 tokens**, cited **10 primary publications**, and remained partial because it reached the document budget. Its larger allowance prevents interpreting it as an equal-budget quality comparison. Ten cited publications and seven benchmark matches measure different sets.

Local, ignored artifacts are `reports/2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0/report-v1.html`, `coverage-comparison.json` and `precision_worksheet.csv` in that run directory. The worksheet has **18 unlabelled rows**; it is not a precision result. These generated artifacts are local evidence, not checkpointed deliverables or remote deployment.

Before demo claims, rehearse sign-in, brief creation, optional plan approval, run monitoring, evidence inspection, amendment/rejection, dependent re-review, sign-off and opening the separate reviewed artifact. Human-review the benchmark and precision worksheet, then run the agreed comparison under D3/D9. Use measured evidence and limitations in slides; clearly mark omitted processing time in a recording.

## 8. Source permissions, security and operational constraints

Retain v2's public-data boundary, workspace access controls, server-side credentials, initiating-user audit trail, source allow-list, redirect/private-address checks, robots/rate limits, bounded size/type handling, untrusted-source instructions and versioned provenance. Fixtures demonstrate particular guardrails, not universal resistance to injection or hallucination.

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
| D7 — feature approved; policy open | Corroboration follows coverage; define eligible claims, independence, search allowance and sign-off consequences | Start selectively, label primary-source-only evidence and expose conflicts; design detail remains unadopted | Product owner + reviewer; future corroboration design/schema/report |
| D8 (new) | Can material reviewer amendments be signed off on human attestation alone, or must they pass evidence verification again? | Require explicit evidence review and dependent-inference re-review; decide whether automated recheck is mandatory | Reviewer + product owner; amendment workflow and verification |
| D9 (new) | What is the accepted benchmark scope, recall denominator, multi-agent improvement threshold and replacement for the unmet pre-build M0 gate? | Human-review eligible items, show all/fetchable subsets, retain caveats and use a forward demo evidence gate | Product owner + evaluator; scorer and presentation conclusions |
| D10 (new) | Is the final demo SG+HK or an explicitly narrower HK pilot; are all four industry categories required before demo? | Retain SG+HK intent; if evidence remains inadequate, obtain explicit scope reduction and reflect it in slides | Product owner; final brief, acceptance and release scope |

**Remaining priority policies:** D7 detail (not feature approval), D8 (amended evidence) and D9 (measurement). D6 is settled. Source permissions and budget policy also remain open; adapters or seeded rows do not close them. Approval to update this draft does not adopt every proposed target or remaining policy.

## 10. Delivery order and specialist work

1. **Update the PRD and push a checkpoint:** preserve v1/v2 history and the local validation record; checkpoint source/documentation changes, with generated run artifacts remaining local and ignored.
2. **Continue coverage as the active priority:** split specialist work across discovery/source acquisition, publication-level completeness and missed-publication analysis, and evaluation/precision preparation. Refresh existing workspace connectors/checklist records without expanding permissions. Close or disclose SFC enforcement/other-publication, MAS and industry-source gaps.
3. **Prepare truthful slides and a demo script in parallel:** use the measured HK runs, budget differences and outstanding human/browser checks; no accepted precision, M0 win or remote-deployment claim.
4. **Design and implement the approved corroboration feature after coverage:** settle D7 details, then demonstrate independence, bounded attempts, conflicts and agreed report/sign-off behavior. It remains future work until delivered.
5. **Complete evaluation and browser demonstration:** adopt D9 measurement policy, human-review benchmark and precision, run the agreed comparison, and rehearse review/sign-off with the separate reviewed artifact.

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

This documentation refresh edits only this v3 draft and preserves v1/v2. It records completed local validation and live-run evidence from the development work; it does not itself run models, change the database or permissions, deploy remotely, or adopt proposed targets.

Before adoption: resolve or explicitly defer the remaining policy register, reconcile subsequent implementation changes with this snapshot, and have the product owner adopt v3. Any later pointer update making v3 the primary PRD should be a separate explicit documentation change; keep v2 and v1 available as historical baselines.
