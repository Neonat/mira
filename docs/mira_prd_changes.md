# Mira PRD: what should change

Source documents: `project_description.md` (DBS sponsor brief) and `Mira_Product_Requirements_v1.docx` (PRD v1.0, 11 Oct 2026).
Written 21 Oct 2026, condensed from the review discussion.

## 1. Diagnosis

The brief asks for an agentic researcher. The PRD describes a database and search platform.

- The PRD is built around nouns (Incident, Project, Regulation version, Passage, Index). The brief is built around verbs: monitor, identify, summarize, track, assess, compare, verify.
- A human drives every step in the PRD. A curator starts ingestion, an analyst creates a Project, an analyst starts analysis. The PRD says latest news should "trigger investigations" but never defines what triggers what.
- Only RA07 describes an agent loop. It is one of 25 numbered requirements (IN01-08, RA01-09, DB01-08) and defines no roles, planner or handoffs.
- The entry point is wrong. The brief says: select a topic, define jurisdictions, generate a structured report. In the PRD you must ingest, curate, promote a theme, build a Project, then run analysis.
- Effort is lopsided. Devs 1 and 3 own ingestion, storage, search, indexing and backups. The 20 to 30 year archive, OpenSearch sizing and bank deployment readiness are beyond MVP and are not in the brief.

## 2. Coverage of the brief

| Brief asks for | PRD v1.0 today |
|---|---|
| Topic + jurisdictions to structured report | Not the entry point. Project-first. |
| Multi-agent workflow | One bounded loop (RA07), no roles |
| Monitor regulators | Manual ingestion jobs, no scheduled or triggered monitoring |
| Business-friendly obligation summaries | Not explicit |
| Track timelines and deadlines | Effective dates stored, no upcoming or consultation tracker |
| Assess impact | Covered by RA05 (risk, urgency, audit work), but no opportunities |
| Compare jurisdictions | Missing. Foreign cases are context only. |
| Analyze trends | Only historical comparisons, no supervisory focus trends |
| Industry best practices and innovations | Missing. Incidents only. |
| Source links and traceability | Strong |
| Completeness guardrail | Coverage register for archive years, but nothing checks jurisdiction x topic coverage of a report |
| Hallucination guardrail | Strong intent (RA06, 95% target), but a stage rather than an independent check |

## 3. Keep these parts of the PRD

- Citations to exact source versions and passages.
- Separation of source facts from inferred risk implications.
- Priority kept separate from evidence confidence.
- As-of dates and effective-period handling.
- Treating retrieved content as data, not instructions.
- Draft versus reviewed report labelling, with reviewer and decision date.
- Revision history and reproducible analysis runs.

These already match the brief's guardrails.

## 4. Recommended changes

### 4.1 Reframe as an agent product
Make the evidence store the agents' memory and audit trail. Agents search stored evidence first, then go to the live web or regulator sites when there is a gap. Retrieval becomes a tool, not the product. The PostgreSQL and source archive work stays, with a clearer job.

### 4.2 Add an agent architecture section
Define each role's inputs, outputs, tools, stop conditions and budget, and log a trace so reviewers can see what happened.

| Role | Copies per run | Job |
|---|---|---|
| Planner | 1, re-runs when gaps appear | Turns topic and jurisdictions into a plan: regulators, sub-questions, budget. Coordinates the others. |
| Regulatory scouts | One per jurisdiction, parallel | Find new, amended and upcoming instruments, consultations and enforcement, starting from regulator sites. |
| Industry scout | 1 | Finds incidents, case studies, best practices and innovations. |
| Reader | One per document, parallel | Extracts obligations, effective dates and deadlines with passage anchors. |
| Analyst | 1, or one per jurisdiction plus a merge | Plain-language summaries, bank impact, cross-jurisdiction comparison, trends. |
| Verifier | One per claim | Independent check that each cited passage supports its claim. |
| Completeness checker | 1 | Compares findings to an expected jurisdiction x regulator x category list. |
| Writer | 1 | Builds the report from verified claims only. |

Notes:

- A role is one job with its own prompt and tools, not necessarily one process.
- Fetching, parsing, saving and rendering are ordinary code called as tools. Use an agent only where judgement is needed.
- The verifier must not share context with the analyst, or it tends to agree with it.
- If time is short, merge the reader into the scouts and the industry scout into the regulatory scout code.

### 4.3 End-to-end flow (target user journey)

1. **Input.** User sets topic, jurisdictions, optional period and as-of date.
2. **Plan.** Planner proposes regulators, questions and budget. User can see it.
3. **Scout.** Scouts run in parallel, one per jurisdiction plus industry.
4. **Read and analyse.** Readers extract passages. Analyst summarises, compares, assesses impact.
5. **Check.** Verifier and completeness checker run. Failures send scouts back out, capped by budget.
6. **Report and review.** Writer builds the cited report. Reviewer accepts, amends or rejects findings.

The evidence store sits under steps 3 to 6.

### 4.4 Verifier rule (core guardrail)
For every material claim:

1. Fetch the cited passage.
2. If it supports the claim, keep it and cite it.
3. If not, search again within the time and cost cap.
4. If budget runs out, drop the claim or mark it unresolved.

A claim never reaches the report unless a passage supports it. This covers the brief's traceability and hallucination guardrails.

### 4.5 Completeness checker
Holds an expected-source list per jurisdiction, for example MAS for Singapore and HKMA for Hong Kong. If a source is missing from the draft, scouts search again. If it is still missing, the report states the gap rather than hiding it.

### 4.6 Make the brief's journey the primary one
- Primary flow: topic + jurisdictions + period, live run view, report, reviewer sign-off.
- A Project becomes a saved, re-runnable brief (topic, jurisdictions, bank context).
- Move ThemeSuggestion, hybrid project creation and curator screens to a later stage.
- OD01 (hybrid creation) is marked confirmed by the product owner, so this needs a conversation rather than a quiet edit.

### 4.7 Add monitoring mode
A scheduled re-run that diffs against the previous report and produces "what changed since". This is the proactive part of the brief, and plain database search cannot do it.

### 4.8 Add the missing report sections
- Jurisdiction comparison matrix
- Upcoming deadlines and consultation timeline
- Supervisory trends and focus areas
- Industry developments, including best practices and innovations
- Plain-language obligation summaries

### 4.9 Measure the report, not just retrieval
The current benchmark (recall at 20, relevance in the top five) tests search. Add:

- Citation precision: share of claims supported by the cited passage.
- Unsupported claims caught by the verifier versus leaked into reports.
- Coverage against a hand-built list of real SG and HK AML developments from the last 12 months.
- A three-way comparison of plain search, single agent and multi-agent, to show whether the multi-agent design earns its cost.
- Time against a manual baseline, plus review effort and errors.

All numerical targets (for example 95% supported material claims) remain proposals to confirm with the team.

### 4.10 Re-cut developer ownership by agent role
Proposal for the team to adjust:

- Dev 1: planner, orchestration, run-view UI, writer.
- Dev 2: scouts, reader, source and fetch tools.
- Dev 3: verifier, completeness checker, evidence store, evaluation harness.

### 4.11 Shrink the MVP
- One topic: AML/CFT.
- Singapore and Hong Kong, a third jurisdiction if time allows.
- Last 12 to 24 months, live retrieval.
- Defer the 30-year archive, OpenSearch evaluation, internal bank data and production hosting.

## 5. Riskiest assumption and cheapest test

Assumption: agents can find the authoritative page for each jurisdiction and know when they have found everything. Completeness is the hardest promise in the brief.

Cheapest test, about one day:

1. Hand-list the AML developments for SG and HK over the last 12 months.
2. Run a one-agent prototype with web search.
3. Measure what fraction it finds.

The result decides how much to invest in curated source lists versus open search.

## 6. Open decisions for the team

- Is the 30-year archive a sponsor requirement or from class discussion? The brief does not mention it. PRD section 16 says later discussions take precedence over earlier proposals. If it is the product owner's, move it to stage 2.
- Confirm with the product owner that hybrid project creation (OD01) moves out of the MVP.
- Confirm pilot topic and jurisdictions (OD02) and the review rubric and reviewer roles (OD08).
- Agree the expected-source list per jurisdiction for the completeness checker.
- Agree model, time and cost budget per run.

## 7. Exec pitch summary (roleplay version)

Auditors spend days tracking regulator sites and industry news across markets and checking sources. Mira does the research and checking first, and the auditor stays in charge.

1. Auditor sets topic, jurisdictions, period.
2. Planner builds a visible research plan.
3. Scouts search in parallel, starting from regulator sites.
4. Readers and an analyst produce summaries, comparisons and impact assessments.
5. Verifier and completeness checker run before anything is shown.
6. Auditor reviews a cited, labelled draft and signs off.

What is deliberately not claimed:

- Mira uses public or licensed material only.
- It does not conclude that the bank complies or fails to comply.
- An external enforcement case alone never becomes a finding about the bank.
- High priority means "look at this soon", not "this is a breach".

Ask to the exec: choose the pilot topic and markets, and nominate two or three auditors to review reports and judge usefulness.

## 8. Suggested next steps

1. Run the section 5 spike on AML for SG and HK.
2. Draft the new agent architecture section and revised user journey in the PRD.
3. Walk the product owner through section 4.6 and 4.11 before editing confirmed requirements.
4. Rework the acceptance and evaluation section around section 4.9.
