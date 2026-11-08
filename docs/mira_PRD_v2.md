# Mira Product Requirements v2

> **Reading note — updated 8 November 2026.** V2 is the approved requirements baseline for unchanged scope. [PRD v3](mira_PRD_v3_draft.md) records the current implementation through merged PR9, settled amendments and pilot acceptance; the text below retains the original v2 requirements and historical targets.
>
> **Document audience:** Nathaniel, Ewen, Saai, the product owner and technical reviewers tracing requirements. **Product audience:** bank internal-audit analysts and senior reviewers, supported by curators and administrators. Competition judges and DBS stakeholders should start with the [README](../README.md).
>
> **Current delivery:** approved-source ingestion with optional Exa/browser acquisition, claim-level corroboration, frozen reviewed reports, readable source destinations and improved report tables are implemented. Whole permitted extracted text and passages are stored separately from findings. Source support, source independence and auditor sign-off are distinct checks.
>
> **Settled amendment D6:** contextual risks and trends are allowed; generated DBS audit actions and business decisions remain with the auditor. This amendment supersedes the original “suggested audit actions” wording below. Current validation/demo uses Hong Kong with MAS inactive. Historical milestone/target text is not a claim that a metric has been achieved or an instruction to enable blocked sources.


Agentic external driver research for internal audit

Version 2.0 (passed internal maker-checker review; open decisions in §14) | 21 October 2026 | Audience: Nathaniel, Ewen, Saai and the product owner
Supersedes: [PRD v1.0](archive/mira_PRD_v1.md) (11 October 2026). Inputs: [DBS problem statement](dbs_project_statement.md), [grading rubric](project_grading_rubrics.md), [proposed changes](mira_prd_changes.md), [feasibility analysis](archive/mira_agentic_feasibility.md).

**Build status.** The current build is a Prototype/Minimum Viable Product (MVP). It is an academic prototype using public information only. It is not bank production software and does not reach compliance conclusions about the bank.

**Status of this document.** This is the primary requirements document; v1 is archived. Numerical targets are proposals for team agreement.

---

## 0. What changed from v1

| Area | v1 | v2 |
|---|---|---|
| Product shape | Searchable evidence platform with one bounded research loop (RA07) | Multi-agent researcher; the evidence store is the agents' memory and audit trail |
| Entry point | Ingest → curate → promote theme → build Project → analyse | Topic + jurisdictions + period → plan → research → verified report → review (as the DBS brief describes) |
| Guardrails | Verification as a stage of analysis (RA06) | Independent verifier agent and completeness checker; claims without a supporting passage are blocked |
| Monitoring | Manual ingestion jobs | Re-run a saved brief and see "what changed since" |
| Report | Findings, priority, evidence appendix | Adds plain-language obligations, deadlines, jurisdiction comparison, supervisory trends, industry developments |
| Evaluation | Retrieval metrics | Report-level metrics: citation precision, coverage on real developments, single agent vs multiple agents, time saved |
| MVP scope | 20–30 year archive goal, OpenSearch evaluation | AML/CFT, Singapore + Hong Kong, last 12–24 months. Archive is Stage 2 |
| Kept unchanged | Exact citations, facts separate from inference, priority separate from confidence, dated versions, untrusted source text, draft/reviewed labels, reproducible runs, workspace RLS | Same |

---

## 1. Problem and users

DBS internal audit must stay current on regulatory and industry change across markets. Today auditors check regulator websites, consultation papers, enforcement notices and industry news by hand, then reconcile sources and write summaries. This is slow, hard to repeat consistently, and gets harder as the number of jurisdictions grows. *(DBS brief, Overview.)*

Mira does the first pass of research and checking. The auditor keeps judgement and sign-off.

| User | Need | Mira role |
|---|---|---|
| Auditor (analyst) | A current, cited picture of a topic across selected markets | Submits the research brief, watches the run, reads the draft report |
| Reviewer (senior auditor) | Confidence that each statement is supported and that nothing material is missing | Accepts, amends or rejects findings; signs off the report |
| Curator | A trustworthy source list | Maintains allow-listed sources and the expected-source list |
| Administrator | Controlled access and cost | Manages members, model settings and run budgets |

## 2. Value and business case

| Value driver | How we measure it in the MVP |
|---|---|
| Time saved | Hours for an auditor to produce an SG + HK AML update manually vs. with Mira plus review time (target: at least 50% reduction, to be measured) |
| Coverage | Share of a hand-labelled list of real SG and HK AML developments (last 12 months) that appears in the report |
| Trust | Citation precision; number of unsupported claims reaching reviewers |
| Proactivity | "What changed since" diff on re-run, so auditors see new items without rereading the whole report |

The value claim rests on measured results from §11, not on assumed benefits.

## 3. Scope

### 3.1 Mapping to the DBS brief

| Brief item | Mira capability | Section |
|---|---|---|
| Select a topic; define jurisdictions | Research brief form | §4 |
| Structured report | Writer + fixed report template | §9 |
| Multi-agent workflow | Planner, scouts, analyst, verifier, completeness checker, writer | §5 |
| A. Monitor | Regulatory scouts on allow-listed regulator pages; re-run diff | §5, §6.5 |
| A. Identify & summarize | Obligation summaries tagged new / amended / upcoming | §5, §9 |
| A. Track timelines | Deadlines and consultation timeline | §9 |
| A. Assess impact | Risks, opportunities, suggested audit actions | §5, §9 |
| A. Compare jurisdictions | Comparison matrix | §9 |
| A. Analyze trends | Supervisory focus areas over the period | §9 |
| A. Verify | Passage-level citations with original links | §6.3 |
| B. Industry developments | Industry scout: incidents, case studies, best practices, innovations | §5, §9 |
| Guardrail: accuracy & traceability | Verifier rule | §6.3, §7 |
| Guardrail: completeness | Completeness checker | §6.4, §7 |
| Guardrail: hallucination | Verifier + deterministic quote check + evaluation | §6.3, §11 |

### 3.2 MVP (Stage 1)

- Topic: AML/CFT.
- Jurisdictions: Singapore (SG) and Hong Kong (HK). A third jurisdiction if time allows.
- Period: the product supports the last 12 to 24 months, as-of today. Evaluation (§11) and the M0 gate use a fixed 12-month window. Historical as-of mode uses the existing v1 rules (§9 of v1) but is not demonstrated in the MVP.
- Sources: allow-listed regulator pages and a small set of approved industry publications (§5.3).
- Runs are on demand. A re-run produces a diff against the previous run.
- One workspace, Supabase Auth, existing roles.

### 3.3 Out of MVP

| Item | Stage | Reason |
|---|---|---|
| 20–30 year news and regulation archive, large backfills | Stage 2 | Not in the DBS brief; large effort |
| ThemeSuggestion and hybrid project creation (v1 RA09, OD01) | Stage 2 | Not the brief's entry point |
| OpenSearch evaluation, capacity planning at 100M passages | Stage 2 | Not needed at MVP volume |
| Scheduled monitoring; news-triggered investigations (v1 confirmed requirement) | Stretch / Stage 2 | Manual re-run covers the demo; the trigger reuses the re-run code path later |
| Open web search | Off by default; optional, labelled fallback | Injection and quality risk |
| Internal bank data, control mapping, production hosting | Bank deployment | Requires bank approval |
| PDF/DOCX export, email delivery | Later | HTML + JSON first |

---

## 4. Primary user journey

```text
 Auditor                      Mira                                     Reviewer
 ───────                      ────                                     ────────
 1 Brief: topic, jurisdictions,
   period, as-of date  ─────▶ 2 Planner drafts plan (regulators,
                                 sub-questions, budget) ─────▶ shown to auditor
 (optional) edit / approve ◀─
                              3 Scouts run in parallel
                                 (SG regulators, HK regulators, industry)
                              4 Analyst: summaries, impact, comparison, trends
                              5 Verifier (per claim) + completeness checker
                                 └─ gaps → targeted re-scout (within budget)
                              6 Writer builds draft report
                                 from verified claims only ──────────▶ 7 Review each finding:
                                                                         accept / amend / reject /
                                                                         needs evidence; sign off
 8 Later: "Re-run" ─────────▶ new run + "what changed since" diff
```

- The live run view shows each step, its status, sources fetched, claims verified and dropped, and budget used.
- A saved brief is stored as a Project revision, so a re-run uses the same scope. Creating a brief is a direct, user-initiated Project creation; Mira never creates a Project on its own.
- The plan step can be approved automatically (default) or require the auditor's approval (setting).

---

## 5. Agent architecture

### 5.1 Design principles

1. **Orchestrator in code, judgement in LLMs.** A deterministic Python state machine runs the workflow, enforces budgets and records every step. Each agent role is one prompt with a fixed tool set. Agents do not talk to each other directly; they exchange typed records through the orchestrator. The record formats are defined once, as Pydantic models in [`mira/contracts.py`](../mira/contracts.py), and every model output is validated against them. Models never see or write database IDs: they cite short labels (`P1`, `C1`) that code maps back to real IDs, and a cited label that was not handed out is rejected.
2. **Use an agent only where judgement is needed.** Fetching, parsing, hashing, saving, passage splitting, date parsing, diffing and rendering are ordinary code exposed as tools.
3. **Least privilege tools.** No agent can write to the database directly, change its own tools, call arbitrary URLs or see secrets. The orchestrator runs as a trusted server-side worker on a direct Postgres connection with elevated rights ([`mira/db.py`](../mira/db.py)). Each write is one transaction that sets the request claims to the initiating user, so `auth.uid()` and the audit trail record that user as the actor. Before each run the worker checks the user's workspace role with the database's own `private.has_workspace_role`. Because row-level security does not apply to this connection, worker code fills actor columns itself and filters every query by `workspace_id`. The elevated credentials never reach Streamlit or the browser.
4. **Evidence store first.** Agents search saved passages before fetching; every fetched page is saved as a `document_version` before any agent reads it.
5. **Independent checking.** The verifier never sees the analyst's reasoning, only the claim and the cited passage.

### 5.2 Roles

| Role | Copies per run | Input | Output | Tools | Stop condition |
|---|---|---|---|---|---|
| Planner | 1; re-invoked once per gap round | Brief, expected-source list | Research plan: regulators per jurisdiction, sub-questions, per-step budgets | `list_sources`, `list_expected_sources` | Plan validates against schema |
| Regulatory scout | 1 per jurisdiction, parallel | Plan slice for its jurisdiction | Candidate documents with type (rule, guideline, consultation, enforcement, circular), dates, and extracted obligations with passage anchors | `search_passages`, `match_passages`, `fetch_allowed(url)`, `list_source_index(source_id)` | Plan items covered, or step budget reached |
| Industry scout | 1 | Plan industry questions | Incidents, case studies, best practices, innovations, with passage anchors | Same as scouts, restricted to industry sources | As above |
| Analyst | 1 (MVP) | Scout outputs (passages, not raw pages) | Draft claims, each typed and linked to ≥1 passage: obligation summary, deadline, impact, comparison, trend, industry development | None (pure reasoning over provided passages) | All scout items processed |
| Verifier | 1 call per material claim | One claim + its cited passages | Verdict: supported / partially supported / unsupported / contradicted, with reason | `get_passage`, `quote_match` (deterministic) | Verdict produced |
| Completeness checker | 1 | Expected-source list, verified claims, fetch log | Coverage table and gap list | `list_expected_sources` (code-first; LLM only to classify ambiguous items) | Table produced |
| Writer | 1 | Verified claims only, coverage table | Report sections (structured JSON) | None | All sections filled or marked "no verified items" |

The reader role in the change proposal is merged into the scouts for the MVP. The analyst may split into one per jurisdiction plus a merge step if context size requires it.

### 5.3 Tools and sources

- `fetch_allowed(url)`: fetches only URLs whose host is in an active `sources` row (`base_url`) with `permitted_operations` that include fetching. Saves `documents`, `document_versions` (content hash) and `document_passages`, then returns passage IDs. Respects robots.txt and rate limits. Every redirect target is re-checked against the allow-list; private, loopback and link-local addresses are refused; only `http(s)` is allowed; response size and content types (HTML, PDF) are capped.
- `search_passages` / `match_passages`: existing RPCs (full text and pgvector), always scoped to the workspace.
- `quote_match(claim_quote, passage_id)`: deterministic normalised substring or fuzzy match ≥ 0.9.
- Allow-list and draft expected-source list: [approved sources](mira_approved_sources.md) (D4 draft, URLs verified 26 October 2026). Regulators and legislation for SG and HK, international standard-setters (FATF, APG, BIS) and industry bodies (Wolfsberg Group, Egmont Group, ABS, HKAB). HK e-Legislation, Singapore Statutes Online, FATF and BIS refuse automated access, so their documents are imported by hand.
- Open web search is not available to agents unless an administrator enables it for a run. Results from it are labelled as discovered via open search and cannot be cited unless the page is on the allow-list or approved by a curator.

### 5.4 Models

- One hosted LLM with tool use for planner, scouts, analyst and writer; the verifier uses the same or a different model with a separate prompt and fresh context. Exact model chosen under D3.
- Local `all-MiniLM-L6-v2` embeddings (384 dimensions) as in the existing schema.
- Model name, version, prompt version and temperature are saved per step.

---

## 6. Workflows

### 6.1 Run lifecycle

`queued → planning → scouting → analysing → verifying → gap_filling (≤ N rounds) → writing → draft → reviewed` with `partial`, `failed` and `cancelled` as exits. `analysis_runs.status` keeps its existing values and gains `cancelled` (§8); the fine-grained step lives in `agent_steps`.

### 6.2 Budgets

Each run has a budget stored in `analysis_runs.source_limits`: max fetched documents, max LLM tokens, max wall-clock minutes, max gap rounds (default 2). When a budget runs out the run ends as `partial` with a stated reason, and the writer still produces a report from what was verified.

### 6.3 Verifier rule (core guardrail)

For each material claim (every claim type except purely structural text):

1. Load the cited passage(s) from the store. The verifier never uses web content that is not saved.
2. Run `quote_match` on the analyst's supporting quote. If it fails, the claim is `unsupported` without an LLM call.
3. Ask the verifier, in a fresh context, whether the passage supports the claim, including entity, jurisdiction, date and instrument status.
4. `supported` → keep. `partially supported` → the analyst gets one rewrite to narrow the claim, then it is checked again. `unsupported` or `contradicted` → send to gap filling once (re-scout for a better source), within budget.
5. Still unsupported → dropped from the report body and listed under "Unresolved items" for the reviewer. It never appears as a finding.

**Inferred claims** (impact, opportunity, comparison, trend) cannot be "supported" by one passage. Each one must cite the verified factual claims it rests on, be labelled as inference, and pass a check that it introduces no fact (entity, date, number, instrument) absent from those claims. An inference that rests on a dropped fact is dropped too.

The verifier returns a structured verdict only. Passage text is wrapped as quoted data, so a passage that says "this claim is supported" has no effect; the deterministic quote match runs before any LLM judgement.

Every verdict is saved in `claim_checks`.

### 6.4 Completeness check

1. Load the expected-source list for each jurisdiction × topic (e.g. SG AML: MAS Notice 626, MAS guidelines, MAS enforcement actions, MAS consultation papers; HK AML: HKMA guidance, AMLO, SFC enforcement, HKMA consultations).
2. For each entry, check that the scouts fetched it within the period and recorded either a development or "no change in period".
3. Missing → planner adds targeted scout tasks (one round).
4. Still missing → the report states the gap and the reason (fetch failed, not found, out of budget).

The report describes coverage as "relative to the expected-source list v{n}", never as complete.

### 6.5 Monitoring re-run and diff

A re-run creates a new run linked through `previous_run_id`. Findings are matched by `(regulation_id or document_id, finding_type, normalised key)`, so industry items with no regulation still diff correctly. The report gains a "What changed since {date}" section listing new, changed and no-longer-supported items. A scheduled re-run (weekly) is a stretch goal using a cron worker with the same code path.

### 6.6 Human review

Unchanged from v1 (RA08): the reviewer accepts, amends, rejects or marks each finding as needing evidence. A report becomes `reviewed` only when every finding has a decision and a reviewer signs off. Draft reports are watermarked.

---

## 7. Governance, risk and ethics

### 7.1 Risk register

| # | Risk | Likelihood / impact | Mitigation | Residual control |
|---|---|---|---|---|
| G1 | Hallucinated or unsupported claim reaches the auditor | Medium / High | Verifier rule §6.3; deterministic quote match; writer sees verified claims only | Citation-precision metric; reviewer sign-off |
| G2 | Incomplete coverage presented as complete | High / High | Completeness checker §6.4; gaps printed; coverage wording rule | Coverage metric on labelled set |
| G3 | Prompt injection in fetched pages | Medium / High | Source text passed as quoted data; allow-listed fetch only; agents have no write tools; writer never sees raw pages | Injection test fixtures (AC-G3) |
| G4 | Confidential bank data sent to an external LLM | Low (MVP) / High | MVP accepts public sources only; topic and jurisdictions are picked from controlled lists, not free text; no upload of bank documents in MVP; D3 records approval | Bank deployment review (v1 NF06) |
| G5 | Over-reliance: auditors treat the draft as a conclusion | Medium / High | Draft watermark; "not a compliance conclusion" statement; priority ≠ breach; external case ≠ bank finding | Mandatory finding-level review |
| G6 | Wrong version or date applied (e.g. superseded rule) | Medium / Medium | `regulation_versions` effective dates; verifier checks status and date; as-of date pinned per run | AC05 from v1 kept |
| G7 | Copyright / terms of use | Medium / Medium | `sources.permitted_operations`; store only permitted text; short quotes in reports with links | Curator source approval |
| G8 | Model drift or vendor change alters output | Medium / Medium | Model, prompt and version saved per step; evaluation re-run on model change | Reproducible runs |
| G9 | Runaway cost or loops | Medium / Low | Budgets §6.2; max gap rounds; partial result on exhaustion | Cost per run tracked |
| G10 | Bias toward English or larger regulators | Medium / Medium | Expected-source list per jurisdiction; coverage per jurisdiction shown side by side | Reviewer judgement |
| G11 | Unauthorised access to runs or reports | Low / Medium | Supabase Auth, workspace RLS, role grants (unchanged) | Existing RLS tests |

### 7.2 What Mira deliberately does not claim

- It uses public or licensed material only.
- It does not conclude that the bank complies or fails to comply.
- An external enforcement case never becomes a finding about the bank on its own.
- High priority means "look at this soon", not "this is a breach".
- Coverage is relative to a named source list, not the whole internet.

### 7.3 Accountability and traceability

Every run stores: brief, plan, each agent step (role, model, prompt version, inputs and outputs by ID, tokens, duration), every fetched document version, every claim and verdict, the completeness table, the report snapshot and every reviewer decision. A reviewer can open any sentence in the report and see the passage, the verifier verdict and the step that produced it.

---

## 8. Data model changes

All existing tables and contracts stay. All changes are in one additive migration, [`20261026120000_mira_agentic_workflow.sql`](../supabase/migrations/20261026120000_mira_agentic_workflow.sql), owned by Saai.

| Change | Purpose |
|---|---|
| `agent_steps` (run_id, step_no, role, jurisdiction, gap_round, status, contract_version, model, prompt_version, temperature, input_refs jsonb, output_refs jsonb, tokens_in, tokens_out, started_at, finished_at, error) | Run trace for the live view and audit |
| `research_plans` (run_id, version, contract_version, plan jsonb, approved_by, approved_at) | Visible, versioned plan; an analyst may approve an unapproved plan once, as themselves |
| `expected_sources` (workspace_id, list_version, topic, jurisdiction_code, category, source_id, document_hint, url_hint, is_active) | Completeness checklist, maintained by curators |
| `claim_checks` (finding_id, attempt, method `quote_match`/`llm`/`inference_check`, verdict, reason, model, prompt_version, checked_at) | Verifier verdict history; `inference_check` is the "introduces no new fact" test (§6.3) |
| `coverage_results` (run_id, expected_source_id, gap_round, status `found`/`no_change`/`missing`/`fetch_failed`/`out_of_budget`, document_version_id, note) | Completeness table for the report |
| `finding_dependencies` (finding_id, depends_on_finding_id) | Links an inferred finding to the verified facts it rests on, so it falls if they fall (§6.3) |
| `finding_evidence.supporting_quote` (required when `support_type = 'supports'`) | Input to `quote_match` (§6.3 step 2) |
| `analysis_runs.previous_run_id`; `analysis_runs.status` adds `cancelled` | Monitoring diff; user cancellation |
| `analysis_findings.finding_type` gains `obligation_summary`, `deadline`, `jurisdiction_comparison`, `trend`, `industry_development`, `opportunity`; adds `jurisdiction_code`, `change_type` (`new`/`amended`/`upcoming`/`unchanged`), `industry_category`, `is_inference`, `evidence_confidence_reason`, `key_date` + `key_date_kind`, `regulation_id`, `document_id`, `diff_key` | New report sections, timeline, facts vs inference, priority and confidence reasons kept separate, re-run diff key (§6.5) |
| `sources.permitted_operations` limited to `metadata`, `fetch`, `store_text`, `quote`, `embed` | Lets `fetch_allowed` check permission before fetching (G7) |

New tables follow the existing conventions: `workspace_id` on every row, composite foreign keys, RLS policies, no hard delete for app users, audit triggers. Tables only the worker writes (`agent_steps`, `claim_checks`, `coverage_results`, and new `research_plans` rows) are read-only for app users.

The sentence-to-claim mapping needed by AG10 is stored in `reports.evidence_snapshot`, in the `ReportSnapshot` shape from [`mira/contracts.py`](../mira/contracts.py).

Unused in the MVP but kept: `theme_suggestions*`, large-scale `source_coverage` by year.

---

## 9. Report structure

1. Header: topic, jurisdictions, period, as-of date, run ID, draft or reviewed label, reviewer and date.
2. Executive summary (verified claims only, ≤ 1 page).
3. Regulatory developments by jurisdiction: new / amended / upcoming, with a plain-language obligation summary and citation for each item.
4. Deadlines and consultation timeline (table sorted by date).
5. Jurisdiction comparison matrix: common themes and differences.
6. Supervisory trends and focus areas (with the coverage basis stated).
7. Industry developments: incidents, case studies, best practices, innovations.
8. Impact assessment: risks, opportunities, suggested audit actions; priority and confidence shown separately with reasons.
9. What changed since the previous run (re-runs only).
10. Coverage and limitations: expected-source table, gaps, unresolved items, budget status.
11. Evidence appendix: source, publisher, date, URL, passage location, document version ID.

Formats: HTML and JSON, rendered from saved records without new generation (v1 DB07 unchanged).

---

## 10. Requirements

v1 IDs that remain in force are listed in Appendix B. New requirements:

| ID | Requirement | Acceptance | Owner |
|---|---|---|---|
| AG01 Brief | User picks topic and jurisdictions from controlled lists (regions expand through `market_region_mappings`) and sets period and as-of date; saved as a Project revision | Brief round-trips; re-run uses the same revision | Ewen |
| AG02 Planner | Produces a schema-valid plan from brief and expected sources; plan visible before scouting | Plan lists every expected regulator for each jurisdiction | Ewen |
| AG03 Orchestrator | State machine runs roles, enforces budgets, records `agent_steps`, supports cancel | Budget exhaustion yields `partial` with a reason; trace shows every step | Ewen |
| AG04 Regulatory scouts | One per jurisdiction in parallel; fetch only allow-listed URLs; save before reading | A non-allow-listed URL is refused and logged | Nathaniel |
| AG05 Industry scout | Finds incidents, case studies, best practices, innovations from approved sources | Each category shows verified items or an explicit "none found"; the scout is never required to produce an item | Nathaniel |
| AG06 Fetch and parse tools | HTML/PDF fetch, hash, version, passage split; failures visible | Changed page creates a new version; failure never becomes an empty success (v1 IN03) | Nathaniel |
| AG07 Analyst | Typed claims, each with a quote and passage ID; facts separate from inference | Every claim references ≥1 passage | Ewen |
| AG08 Verifier | §6.3 rule, independent context, deterministic quote check | Seeded false claims are caught at ≥ 90% (proposal) | Saai |
| AG09 Completeness checker | §6.4; coverage table and gap re-scout | A deliberately removed source is detected and reported | Saai |
| AG10 Writer | Builds §9 sections from verified claims only; may condense and order but not add facts | Every non-structural sentence, including the executive summary, carries ≥1 verified claim ID (checked in code before saving) | Ewen |
| AG11 Re-run diff | §6.5 | A changed fixture shows as "amended" in the diff | Saai |
| AG12 Run view UI | Live steps, sources, verdicts, budget | Auditor can follow a run without logs | Ewen (orchestration UI), Nathaniel (sources panel) |
| AG13 Review UI | Finding-level decisions and sign-off (v1 RA08) | Report cannot be marked reviewed with undecided findings | Saai |
| AG14 Injection resistance | Source text never changes tools or policy | Fixture page with embedded instructions has no effect (AC-G3) | All |

---

## 11. Evaluation

| Metric | Method | Proposed target |
|---|---|---|
| Coverage | Hand-labelled list of real SG + HK AML developments, last 12 months (20–40 items) | ≥ 80% found |
| Citation precision | Sample of report claims, human-checked against cited passage | ≥ 95% supported |
| Verifier catch rate | Seeded unsupported claims | ≥ 90% caught; leaked count reported |
| Unsupported claims leaked to reviewers | Count per report | 0 critical |
| Agent design value | Same briefs through (a) plain search + template, (b) single agent, (c) multi-agent; compare coverage, precision, cost, time | Multi-agent must beat (b) on coverage or precision to justify cost |
| Time saved | 2–3 auditors or proxies; manual vs Mira + review | ≥ 50% reduction |
| Cost and latency | Tokens and minutes per run | Within D3 budget; run < 15 min |

Retrieval metrics from v1 (recall@20, top-5 relevance) remain as diagnostics, not headline results.

**Gate before M1 (riskiest assumption): run the M0 test before any full build.**

1. Hand-list the real SG and HK AML developments in the 12-month window. Build this list before seeing any system output; it is the ground truth for coverage.
2. Run a single-agent prototype restricted to the allow-list ([approved sources](mira_approved_sources.md)).
3. Measure recall: the share of hand-listed developments the prototype finds.

**If recall is below 50%, the project halts before the full build.** M1 does not start; the team reviews the result and decides whether to change the approach. At 50% or above, M1 proceeds.

---

## 12. Delivery plan

| Milestone | Content | Exit condition |
|---|---|---|
| M0 Spike (1–2 days) | §11 gate; labelled development list; expected-source list draft | Recall ≥ 50% and allow-list agreed. Below 50%: project halts before the full build |
| M1 Thin end-to-end | Brief → planner → 1 scout (SG) → analyst → verifier → writer → HTML report; `agent_steps` | One verified report on real MAS content |
| M2 Multi-agent | HK scout, industry scout, completeness checker, gap round, comparison and timeline sections, run view | AG01–AG10 pass |
| M3 Guardrails and evaluation | Injection fixtures, seeded false claims, three-way comparison, review UI, re-run diff | §11 metrics reported; AG11–AG14 pass |
| M4 Demo and presentation | Rehearsed live run, recorded backup, slides tied to the rubric | Presentation ready |
| Stretch | Scheduled monitoring, third jurisdiction | Not required |

Ownership by existing strengths:

- **Nathaniel** (ingestion): scouts, fetch/parse tools, source allow-list, sources panel.
- **Ewen** (analysis): planner, orchestrator, analyst, writer, brief and run-view UI.
- **Saai** (database): additive migrations, verifier, completeness checker, re-run diff, review UI, evaluation harness.

---

## 13. Rubric mapping

| Criterion (weight) | Evidence in this PRD |
|---|---|
| Feasibility, Value and Application (15%) | §2 business case; §3 narrow MVP; §12 plan; [feasibility analysis](archive/mira_agentic_feasibility.md) |
| Governance, Risk and Ethics (25%) | §6.3–6.4 guardrails; §7 risk register, non-claims, traceability |
| Problem Framing and Industry Relevance (20%) | §1; §3.1 clause-by-clause mapping to the DBS brief |
| Technical Design and Prototype (15%) | §5 architecture; §6 workflows; §8 data model; agent value test in §11 |
| Communication and Presentation (15%) | §0 change table; §4 journey; README |
| Content Quality and Evidence (10%) | §11 report-level metrics on real developments |

---

## 14. Open decisions

| ID | Decision | Recommendation | Owner |
|---|---|---|---|
| D3 | Hosted LLM for public data; model; cost cap per run | Approve with public-data-only rule | Product owner + team |
| D4 | Allow-list and expected-source list for SG and HK AML | Drafted in [approved sources](mira_approved_sources.md); open: MAS written permission to store text, manual imports for AMLO, FATF and BIS | Nathaniel + Saai |
| D5 | Reviewer roles for sign-off (v1 OD08) | Senior auditor proxy from mentors | Product owner |

---

## Appendix A. Maker-checker log

The architecture and workflows were drafted first (maker). A separate review pass then audited the draft against the DBS problem statement on three tests: **valid** (traces to a brief requirement and is technically sound against the current schema), **secure** (no new attack or data-leak path) and **scoped** (needed for the brief, deliverable by three people). The checker found the issues below; every one was fixed before this version was finalised.

| # | Test | Finding in maker draft | Resolution |
|---|---|---|---|
| C1 | Valid | Verifier rule only covered factual claims. Impact, comparison and trend statements are inferences that no single passage "supports", so they bypassed the hallucination guardrail the brief requires. | §6.3: inferred claims must cite verified facts, be labelled inference and introduce no new facts; they fall if their facts fall. |
| C2 | Secure | `fetch_allowed` checked only the first URL. Redirects or crafted links could reach other hosts or internal addresses (SSRF). | §5.3: redirect re-check, private-address block, scheme, size and type limits. |
| C3 | Secure | The orchestrator writes on behalf of users, but the draft did not say with which credentials. The engineering guide forbids exposing the service-role key. | §5.1: trusted server-side worker, role check per run, initiating user recorded as actor. |
| C4 | Secure | Free-text topic could carry confidential context to a hosted LLM. | Controlled topic and jurisdiction lists (G4, AG01). |
| C5 | Valid | Lifecycle used `cancelled`, which the existing `analysis_runs.status` check constraint does not allow. | §6.1 and §8: additive migration adds `cancelled`. |
| C6 | Valid | Re-run diff keyed on `regulation_id`; industry findings have none, so they could not be diffed. | §6.5: key on regulation or document. |
| C7 | Valid | Writer and executive summary could add unverified synthesis, which would break "report from verified claims only". | AG10: every non-structural sentence carries a verified claim ID, checked in code. |
| C8 | Scoped | v1 confirmed requirement "latest news triggers investigations" was dropped without being recorded. | Listed in §3.3 as Stage 2 on the re-run code path. |
| C9 | Valid | AG05 required at least one item per category, which pressures the agent to invent items. | AG05 accepts "none found". |

Items checked and left unchanged:

- **Scope vs brief.** Every MVP capability in §3.2 traces to a row in §3.1. Out-of-scope items in §3.3 are either absent from the brief (archive, OpenSearch, theme discovery) or are bank-deployment conditions. No feature in the MVP lacks a brief requirement.
- **Regions.** The brief says "jurisdictions/regions". Region expansion already exists (`market_region_mappings`) and is now exposed in AG01.
- **Human oversight.** Plan visibility, finding-level review and sign-off keep the auditor in charge, matching the brief's "support proactive decision-making" rather than replacing it.
- **Targets.** All numbers in §11 are labelled as proposals.

## Appendix B. v1 requirements status

| v1 ID | Status in v2 |
|---|---|
| IN01 Source catalogue | Kept (allow-list) |
| IN02 Manual ingestion jobs | Kept, used by scouts |
| IN03 Extraction pipeline | Kept (AG06) |
| IN04 Incident construction | Kept for industry scout |
| IN05 Duplicates | Kept, light |
| IN06 Latest/archive views | Stage 2 |
| IN07 Storage handoff | Kept |
| IN08 Backfill | Stage 2 |
| RA01 Regulatory ingestion | Kept, via scouts |
| RA02 Projects and links | Kept (brief = Project revision) |
| RA03 Project relevance | Folded into analyst |
| RA04 Applicability and time | Kept |
| RA05 Risk implications | Kept, plus opportunities |
| RA06 Evidence verification | Replaced by AG08 |
| RA07 Bounded research | Replaced by AG03 |
| RA08 Structured analysis and review | Kept (AG13) |
| RA09 Theme discovery | Stage 2 |
| DB01–DB02 Storage | Kept |
| DB03 Hybrid retrieval | Kept (agent tool) |
| DB04 Index consistency | Kept |
| DB05 Manual records | Kept, light |
| DB06 Access and reproducibility | Kept |
| DB07 Report delivery | Kept |
| DB08 Operational foundation | Light for MVP; full in bank deployment |
