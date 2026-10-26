# Mira agentic changes: feasibility analysis

Written 21 October 2026. Reviews [`mira_prd_changes.md`](../mira_prd_changes.md) against [`mira_PRD_v1.md`](mira_PRD_v1.md), the checked-in Supabase schema, the [DBS problem statement](../dbs_project_statement.md) and the [grading rubric](../project_grading_rubrics.md). The result feeds [PRD v2](../mira_PRD_v2.md).

## 1. Summary

The move to an agentic architecture is feasible and needed. The DBS brief explicitly asks for "a multi-agent workflow to autonomously research, analyze, synthesize, and consolidate information". PRD v1 describes a search platform with a single bounded loop (RA07), so as written it would score weakly on Problem Framing (20%) and Technical Design (15%).

Most of the proposed changes reuse what already exists. The v1 evidence model (document versions, passages, regulation versions, findings, finding evidence, reviews, report snapshots) is already the right memory and audit trail for agents. The new work is mostly the orchestration and LLM layer, plus five small additive tables.

Three proposals need changing before adoption:

1. **Open live web search** (4.1) conflicts with the engineering guide ("do not add an external web-search … API for the first release") and widens the prompt-injection and data-quality surface. Adopt it in a narrower form: scouts fetch only from an allow-listed set of regulator and approved industry domains. General web search becomes an optional, labelled fallback that is off by default.
2. **Developer re-cut** (4.10) hands scouts to Dev 2 and the planner to Dev 1, which inverts current expertise. Re-cut by existing skills instead (§4.10 below).
3. **Monitoring mode** (4.7) is feasible as an on-demand "re-run and diff" in the MVP. A real scheduler is a stretch goal.

A new dependency is not addressed in the change proposal: agent tool use needs a capable hosted LLM, while the engineering guide assumed an optional local model. This is acceptable for public data only and must be recorded as a governance decision (§5).

## 2. Feasibility by proposal

Ratings: **Feasible** (adopt as proposed), **Feasible with changes** (adopt in modified form), **Defer** (out of MVP).

| # | Proposal | Rating | Technical assessment | Rubric effect |
|---|---|---|---|---|
| 4.1 | Reframe as agent product; evidence store is agent memory | Feasible with changes | The schema already pins every claim to `document_versions` and `document_passages`, so agents can write through the same contracts. Restrict live retrieval to allow-listed domains (`sources.base_url`, `source_type = 'regulator'`). Keep general web search off by default. | Problem Framing 20%, Technical Design 15% |
| 4.2 | Agent roles (planner, scouts, reader, analyst, verifier, completeness, writer) | Feasible | Eight roles are too many for three people if each is a free-form agent. Feasible if the orchestrator is a deterministic state machine in Python and each role is a single prompt plus a small tool set. Merge the reader into the scouts for the MVP, as the proposal itself allows. | Technical Design 15% |
| 4.3 | Topic + jurisdictions → plan → scout → analyse → check → report | Feasible | `analysis_runs` requires a `project_revision_id`. A brief can be saved as a Project revision (topic in `risk_topics`, jurisdictions in `markets`, period in `reporting_period_*`). No breaking schema change. | Problem Framing 20% |
| 4.4 | Verifier rule: no claim without a supporting passage | Feasible | `finding_evidence.support_type` already records supports, contradicts or context. Add a `claim_checks` table for the verdict, method and attempts. Pair the LLM check with a deterministic check that the quoted span exists in the passage text. Run the verifier with a fresh context and a different prompt from the analyst. | Governance 25%, Evidence 10% |
| 4.5 | Completeness checker with expected-source list | Feasible | New `expected_sources` table (jurisdiction × topic × category → source). The list is hand-built for SG and HK AML. Gaps print in the report. This only measures coverage of a list we wrote ourselves, and the report must say so. | Governance 25% |
| 4.6 | Make topic + jurisdictions the primary journey; defer ThemeSuggestion | Feasible with changes | Technically trivial; the theme tables stay in place unused. **Governance issue:** v1 marks OD01 (hybrid creation) as *confirmed* by the product owner. Changing it needs product owner agreement, not a silent edit. PRD v2 marks this as pending confirmation. | Problem Framing 20% |
| 4.7 | Monitoring mode with "what changed since" | Feasible with changes | MVP: "Re-run" on a saved brief links the new run to the previous one (`analysis_runs.previous_run_id`) and diffs findings by regulation version and claim key. A scheduler (pg_cron or a cron worker) is a stretch goal. | Value 15% (proactive monitoring) |
| 4.8 | Missing report sections (comparison, deadlines, trends, industry, plain-language summaries) | Feasible | Needs extra `finding_type` values or a `report_section` column; this is an additive migration. Deadlines come from existing `regulation_versions` date fields. | Problem Framing 20%, Content 10% |
| 4.9 | Measure the report (citation precision, coverage, three-way comparison, time saved) | Feasible | Needs a hand-labelled list of about 20 to 40 real SG and HK AML developments. That costs about one person-day and is the same artefact as the §5 spike. The three-way comparison roughly triples evaluation LLM cost, so keep it to the labelled set. | Evidence 10%, Value 15%, Technical 15% |
| 4.10 | Re-cut ownership by agent role | Feasible with changes | Align with current skills: Nathaniel (ingestion) → scouts and fetch/parse tools; Ewen (analysis) → planner, analyst, writer, orchestrator; Saai (database) → verifier, completeness checker, evidence store, evaluation harness, run trace. Split the UI by screen. | Feasibility 15% |
| 4.11 | Shrink MVP: AML/CFT, SG + HK, 12 to 24 months, defer archive and OpenSearch | Feasible | Lowers risk substantially. The 20 to 30 year archive is not in the DBS brief. It becomes Stage 2 pending product owner confirmation (open decision D1). | Feasibility 15%, Problem Framing 20% |
| 5 | One-day spike: hand-list developments, single agent, measure recall | Feasible | Highest-value next step. It decides how much of the scouting relies on curated regulator pages versus open search. Make it a gate before M1. | Evidence 10% |

## 3. Technical risks the proposal does not cover

| Risk | Why it matters | Mitigation adopted in PRD v2 |
|---|---|---|
| Regulator sites change layout, rate-limit or block bots | Scouts silently miss documents, which damages completeness | Per-source fetch adapters with a health check; failures are recorded in `ingestion_run_items` and surface as coverage gaps |
| Prompt injection from fetched pages | The brief requires source-grounded output; injected text could steer agents | Fetched text is passed as quoted data; agents have no write or network tools beyond fetching allow-listed URLs; the writer only sees verified claims |
| Verifier agrees with the analyst (same model) | The guardrail becomes theatre | Separate context, separate prompt, deterministic quote check, and a measured catch rate on seeded false claims |
| LLM cost and latency per run | Two jurisdictions × several documents × per-claim verification can exceed budget | Per-run token and wall-clock budget recorded in `analysis_runs.source_limits`; per-claim verification only for material claims; caching of fetched documents by content hash |
| Hosted LLM vs. "no external API" guidance | Bank data must not leave approved environments | MVP inputs are public regulator and news content only; no bank-confidential context is entered; recorded as a governance decision |
| Completeness is measured against our own list | Over-claiming completeness | The report states coverage relative to the named expected-source list, never "complete" |
| Three-person capacity | Eight roles and new UI | Reader merged into scouts; industry scout shares scout code; scheduler and theme discovery deferred |

## 4. Rubric cross-check

| Criterion (weight) | v1 position | After adopting the feasible changes |
|---|---|---|
| Governance, Risk and Ethics (25%) | Strong intent (RA06, NF01–NF06) but the verifier was a stage inside the analyst | Independent verifier, completeness checker, injection controls, trace log, human sign-off, explicit non-claims. Strongest category. |
| Problem Framing (20%) | Entry point did not match the brief (project-first) | Entry point matches the brief word for word; scope narrowed to one topic and two jurisdictions |
| Feasibility, Value (15%) | 30-year archive and OpenSearch made delivery doubtful | Narrow MVP; business case tied to measured time saved |
| Technical Design (15%) | One loop, no roles | Role-based multi-agent design with an LLM used where judgement is needed, plus an evaluation showing the multi-agent design earns its cost |
| Communication (15%) | Dense 500-line PRD | README maps to brief and rubric; PRD v2 has a one-page journey and diagram |
| Content and Evidence (10%) | Retrieval metrics only | Report-level metrics on real developments |

## 5. Decisions needed before PRD v2 is final

1. **D1** Is the 20 to 30 year archive a sponsor requirement? Not in the brief. Recommend Stage 2.
2. **D2** Product owner confirms OD01 (hybrid project creation) moves out of the MVP.
3. **D3** Approve a hosted LLM for public-data-only processing, and choose the model and the per-run cost cap.
4. **D4** Agree the expected-source list for SG and HK AML.
5. **D5** Confirm reviewer roles for sign-off (v1 OD08).

## 6. Verdict

Adopt 4.2, 4.3, 4.4, 4.5, 4.8, 4.9 and 4.11 as proposed. Adopt 4.1, 4.6, 4.7 and 4.10 with the changes above. Run the §5 spike first. None of the changes requires dropping or rewriting an existing migration; all schema work is additive.
