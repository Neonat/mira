# Mira — External Driver Researcher

Mira turns public regulatory and industry developments into cited research reports for bank internal auditors. An auditor sets the topic, markets and reporting period; Mira plans the research, gathers approved evidence, checks claims and source independence, and prepares a report for review and sign-off.

**Audience:** competition judges, DBS Internal Audit stakeholders and pilot auditors.

**Scope:** an AML/CFT research prototype supporting Singapore and Hong Kong, with a demonstrated Hong Kong research case. The current workflow includes expanded ingestion, Exa-assisted discovery, permitted browser acquisition, claim-level corroboration and passage-level analysis tracking.

## From research brief to reviewed evidence

| Auditor's task | Mira's implemented workflow |
|---|---|
| Define the research | Topic, jurisdictions, reporting period, as-of date and run allowances, with optional plan approval |
| Gather relevant developments | Regulatory and industry scouts search approved saved evidence, publication indexes and scoped Exa discovery; permitted dynamic pages can use browser acquisition |
| Preserve article detail | Permitted document text and searchable passages stay alongside derived findings; bounded analysis batches record progress across saved passages |
| Check source support | Exact passage quotations, numeric checks and a separate-context semantic verifier; facts and inferences remain distinct |
| Inspect corroboration | Claim-level assessments show source independence, supporting or conflicting evidence, quotations and reasons |
| Follow the evidence | Readable source links, direct links to known PDF pages, and private original-file access where separately approved |
| Review and sign off | Finding-level accept/amend/reject/needs-evidence decisions; reviewed versions freeze the evidence, verification and reviewer outcomes |
| Research again | Re-run the saved brief and inspect new, amended and no-longer-supported findings |

Auditors retain ownership of professional judgement, audit actions and sign-off. Mira supplies the sourced developments and contextual risks and trends that support that work.

## A report designed for auditors

The report brings together regulatory developments, deadlines, supervisory themes, industry developments, contextual insights and an evidence appendix. Each finding carries its saved wording, fact/inference label, supported date and source references.

Corroboration appears in the generated report with its assessment, quotations and origin evidence. Passage analysis tracking and the source coverage checklist give reviewers a clear account of the research performed. Reviewed snapshots preserve the evidence and decisions behind the signed version.

Source navigation is built for readers: verified SFC API destinations open the corresponding readable publication page, and known PDF passages link to their page. Permitted original files use integrity checks and authenticated workspace access. Optional hybrid retrieval combines keyword and semantic ranking within source and usage controls.

## Alignment with the competition brief

Sponsor: **DBS Bank, Internal Audit**. Project: *Agentic AI for Audit: External Driver Researcher*.

| Judging area | What to inspect |
|---|---|
| Feasibility, value and application | The complete brief-to-reviewed-report workflow for the AML/CFT pilot |
| Governance, risk and ethics | Approved-source acquisition, workspace access controls, traceable evidence and human sign-off |
| Problem framing and industry relevance | Regulatory and industry research organised around an auditor's topic, markets and reporting period |
| Technical design and prototype | Specialist agents coordinated by deterministic code, typed outputs, shared evidence and bounded follow-up |
| Communication and presentation | Readable reports, direct source navigation, [presentation slides](slides/Mira_DBS_Presentation_v2.pptx) and a [recorded workflow showcase](docs/demo/launch-production-handoff.md) |
| Content quality and evidence | Publication-recall scoring, human citation-precision worksheets and preserved run evidence |

## Validation and prototype status

The [recorded engineering validation](docs/agent-handoffs/evidence-completeness.md) reports **691 tests plus 8 subtests, with no skips**, including local PostgreSQL and actual Chromium. Checks cover passage batching, frozen coverage and review, authenticated original-file access, source navigation and optional hybrid retrieval. The report's coverage layout was also inspected at desktop and mobile sizes.

These are recorded project results, not a claim of a new test run or live research quality. The latest authorised Hong Kong follow-up remained partial: **6/18 publications acquired and 5/18 cited**; live recall, precision and latency gains from the later completeness extension remain unmeasured. See the [dated run evidence](eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.md).

Research evaluation uses scoped publication-recall scoring and human-labelled citation checks. The [evaluation record](docs/mira_PRD_v3_draft.md#7-evaluation-and-release-evidence) documents the measurement method and dated results; the [implementation handoff](docs/agent-handoffs/evidence-completeness.md) records engineering verification.

## Architecture and local setup

A Python orchestration layer coordinates specialist research agents and typed evidence contracts. Supabase/PostgreSQL stores workspace evidence and review history; a worker processes research runs, and the authenticated Streamlit app presents reports and review controls. The separate root `app.py` is a local staging workbench.

Start with **Python 3.11+**, a local Supabase/PostgreSQL stack and the [development guide](docs/development.md). From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,llm,ui]"
cp .env.example .env
```

Configure the ignored `.env` and apply the database setup in [the database guide](supabase/README.md) before running `.venv/bin/python -m mira seed`. Start `.venv/bin/python -m mira worker` and `.venv/bin/streamlit run app/streamlit_app.py` in separate terminals. Provider credentials, run allowances and source permissions are required for live research. MAS automated acquisition remains inactive in the documented pilot configuration; original-file retention and hybrid retrieval are opt-in.

## Explore the project

| Reader | Starting point |
|---|---|
| Judges, sponsors and pilot auditors | The [DBS brief](docs/dbs_project_statement.md), [slides](slides/Mira_DBS_Presentation_v2.pptx) and [workflow showcase](docs/demo/launch-production-handoff.md) |
| Product owner and technical reviewers | [Current PRD](docs/mira_PRD_v3_draft.md) and [feature status](docs/presentation/feature-status-2026-11-08.md) |
| Developers and source curators | [Setup, configuration and code reference](docs/development.md), [database guide](supabase/README.md) and [ingestion quickstart](docs/ingestion-quickstart.md) |
| Maintainers checking design history | [PRD v2](docs/mira_PRD_v2.md), [archived v1](docs/archive/mira_PRD_v1.md), [change proposal](docs/mira_prd_changes.md) and [coordinator handoff](docs/agent-handoffs/README.md) |
