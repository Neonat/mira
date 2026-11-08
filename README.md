# Mira — External Driver Researcher

Mira turns public regulatory and industry developments into cited research reports for bank internal auditors. An auditor sets the topic, markets and reporting period; Mira plans the research, gathers approved evidence, checks claims and source independence, and prepares a report for review and sign-off.

**Audience:** competition judges, DBS Internal Audit stakeholders and pilot auditors. The setup and code-reference sections are for the project team and technical reviewers.

**Delivery:** an academic MVP for AML/CFT research. Ingestion expansion, claim-level corroboration, browser acquisition and readable SFC source links are merged into `main` through [PR7](https://github.com/Neonat/mira/pull/7) and [PR9](https://github.com/Neonat/mira/pull/9). Singapore and Hong Kong are supported brief markets; the current demonstrated research case is Hong Kong.

## What the prototype demonstrates

| Auditor's task | Mira's implemented workflow |
|---|---|
| Define the research | Topic, jurisdictions, period, as-of date and run allowances, with optional plan approval |
| Gather relevant developments | Regulatory and industry scouts search approved saved evidence, publication indexes and scoped Exa discovery; permitted dynamic pages can use browser acquisition |
| Check the source support | Exact passage quotations, numeric checks and a separate-context semantic verifier; facts and inferences remain distinct |
| Inspect independent support | Saved-first corroboration compares the material proposition and source origins, with visible independent, primary-source-only, conflicting, not-checked or inconclusive outcomes |
| Read and follow the evidence | Structured HTML report, dated developments, navigable sections, readable tables, source links and a corroboration section |
| Review and sign off | Finding-level accept/amend/reject/needs-evidence decisions; reviewed versions freeze the retained evidence and review outcomes |
| Research again | Re-run the saved brief and inspect new, amended and no-longer-supported findings |

The auditor decides what the developments mean for the bank and what action to take. Mira provides sourced contextual risks and trends; it does not generate DBS audit actions or compliance conclusions.

## The auditor's report

The report brings together regulatory developments, deadlines, supervisory themes, industry developments, contextual insights and an evidence appendix. Each finding carries its saved wording, fact/inference label, supported date and source references. Coverage and unresolved items are part of the report, so the reviewer can decide where further work is needed.

Source links are written for readers. Verified English SFC circular/news API endpoints open the corresponding public publication page; the original acquisition URL stays in the evidence record. Corroboration displays the status, reasons, quotations and origin evidence separately from primary-source verification and the auditor's decision.

Reports are saved HTML artifacts. Open the latest generated file for the current layout and links; previously exported files keep their original content.

## Alignment with the competition brief

Sponsor: **DBS Bank, Internal Audit**. Project: *Agentic AI for Audit: External Driver Researcher*.

| Judging area | What to inspect |
|---|---|
| Feasibility, value and application | A complete brief-to-reviewed-report workflow, scoped to an AML/CFT pilot, with recorded usage and run allowances |
| Governance, risk and ethics | Approved-source acquisition, workspace access controls, traceable evidence, visible uncertainty and human sign-off |
| Problem framing and industry relevance | Regulatory and industry research organised around an auditor's topic, markets and reporting period |
| Technical design and prototype | Specialist agents coordinated by deterministic code, typed outputs, shared evidence, verification and bounded follow-up |
| Communication and presentation | Readable reports, direct source navigation, [presentation slides](slides/Mira_DBS_Presentation_v2.pptx) and a [recorded workflow showcase](docs/demo/launch-production-handoff.md) |
| Content quality and evidence | Publication-recall scoring, human precision worksheets and preserved run evidence, documented in [PRD v3 §7](docs/mira_PRD_v3_draft.md#7-evaluation-and-release-evidence) |

## Validation

The latest integrated implementation passed **560 tests plus 8 subtests, none skipped**, including local PostgreSQL, actual Chromium fixtures, frozen reviewed evidence and report-source link regressions. The four SFC publications linked by the latest report were also checked in a browser. See the [validation handoff](docs/agent-handoffs/auditor-source-links.md).

Engineering tests establish the exercised implementation behavior. Research coverage, citation precision and auditor usefulness are measured separately in the [evaluation record](docs/mira_PRD_v3_draft.md#7-evaluation-and-release-evidence). The presentation and recording retain their dated evidence; [feature status](docs/presentation/feature-status-2026-11-08.md) identifies the current implementation.

## Read the right document

| Reader | Starting point |
|---|---|
| Judges, sponsors and pilot auditors | This overview, the [DBS brief](docs/dbs_project_statement.md) and the report/review demonstration |
| Product owner and engineering team | [PRD v3](docs/mira_PRD_v3_draft.md): current implementation, pilot requirements, acceptance evidence and decision register |
| Maintainers checking requirement history | [PRD v2](docs/mira_PRD_v2.md): approved baseline; [PRD v1](docs/archive/mira_PRD_v1.md): archived original; [change proposal](docs/mira_prd_changes.md): historical rationale |
| Developers continuing the work | [Coordinator handoff](docs/agent-handoffs/README.md), [ownership rules](AGENTS.md) and [ingestion quickstart](docs/ingestion-quickstart.md) |

PRD v3 records implemented behavior and settled amendments, including the auditor's ownership of actions. V2 remains the approved baseline for unchanged requirements until v3 is adopted. Historical requirements and measured reports are retained rather than rewritten as new results.

## Run locally — project team

Use Python 3.11 or newer and a local Supabase/PostgreSQL stack configured through [the database guide](supabase/README.md). Canonical schema history is in [`supabase/migrations/`](supabase/migrations/).

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,llm,ui]"
cp .env.example .env
```

Configure the ignored `.env` with local connection settings, provider credentials and the agreed run allowances. Keep keys out of reports, logs and Git. The authenticated app uses Supabase Auth and workspace-scoped access; provider and worker database credentials stay on the worker side.

For a new local workspace, initialise the source catalog, then start the worker and app in separate terminals:

```sh
.venv/bin/python -m mira seed
.venv/bin/python -m mira worker
.venv/bin/streamlit run app/streamlit_app.py
```

The source curator must retain workspace-specific permissions when refreshing defaults. **Keep MAS inactive for the current demo/validation configuration.** Manual imports require permission to retain the evidence; importing a document does not grant that permission. See [manual ingestion](data/manual/README.md).

The separate local staging workbench is `streamlit run app.py`; it does not automatically publish evidence to Supabase. `MIRA_WORKSPACE_SLUG` selects the authenticated app's workspace and does not start a worker.

A CLI research run and its usage summary are available when the operator has configured the provider budget:

```sh
.venv/bin/python -m mira run --jurisdictions HK --max-documents 15
.venv/bin/python -m mira usage RUN_ID
```

### Optional acquisition

| Capability | Configuration and boundary |
|---|---|
| Exa URL discovery | `MIRA_ENABLE_EXA_DISCOVERY=1` and `EXA_API_KEY`; results remain task/source/date-scoped metadata until separately permitted acquisition and saving |
| Offline browser extraction | `MIRA_ENABLE_OFFLINE_BROWSER=1`, optional browser dependencies and source opt-in |
| Live browser acquisition | `MIRA_ENABLE_LIVE_BROWSER=1`, compatible Chromium and explicit per-source browser approval/reference; retrying an HTTP block requires separate permission |

Browser acquisition uses deterministic Chromium navigation, JavaScript and at most three configured read-only click/wait actions. It respects source and robots policy, uses fresh sessions and preserves capture/extraction provenance. It does not solve login/CAPTCHA challenges or disguise access. HTTP and browser attempts consume their own allowances. Details: [browser integration](docs/agent-handoffs/live-browser-integration.md).

### Evidence storage and review

Where storage is permitted, Mira saves the complete **extracted text** of a document version and its searchable passages before producing findings. Findings link to those passages; keeping fact A does not replace the saved article with a summary of A. Passage selection for a particular run is bounded by its scope and allowances.

Sign-off freezes the retained claim text, evidence, verification inputs, corroboration and reviewer decisions. Later searches do not change that reviewed version. Technical provenance remains available in the appendix; primary report content is written for auditors. Storage/retention details are in [PRD v3 §8](docs/mira_PRD_v3_draft.md#8-source-permissions-security-and-operational-constraints).

### Tests and evaluation

```sh
.venv/bin/python -m pytest tests eval
```

Database tests require `MIRA_TEST_DATABASE_URL` pointing at an isolated **local** database with current migrations. Browser integration fixtures require the optional browser dependencies and a compatible Chromium executable. Tests use controlled fixtures and scripted models; they do not authorise a paid research run. Do not reset or migrate a shared database as part of local setup.

The three-arm evaluation tools are in [`eval/`](eval/): plain search, single agent and multi-agent use the same scoped publication scorer. Human precision labels are recorded separately. Live comparison runs require their own approved budget; the runner, measurement policy and interpretation are described in [PRD v3 §7](docs/mira_PRD_v3_draft.md#7-evaluation-and-release-evidence).

## Code reference — engineering team

| Area | Modules |
|---|---|
| Typed contracts and orchestration | [`contracts.py`](mira/contracts.py), [`orchestrator.py`](mira/orchestrator.py), [`budget.py`](mira/budget.py) |
| Specialist agents | [`agents/`](mira/agents/), [`interfaces.py`](mira/interfaces.py) |
| Discovery and acquisition | [`discovery.py`](mira/discovery.py), [`fetch.py`](mira/fetch.py), [`live_browser.py`](mira/live_browser.py), [`extract.py`](mira/extract.py) |
| Saved source evidence | [`evidence.py`](mira/evidence.py), [`store.py`](mira/store.py), [`pg_store.py`](mira/pg_store.py) |
| Corroboration | [`corroboration.py`](mira/corroboration.py), [`corroboration_runtime.py`](mira/corroboration_runtime.py), [`corroboration_store.py`](mira/corroboration_store.py) |
| Reports and reader links | [`report.py`](mira/report.py), [`source_links.py`](mira/source_links.py), [`corroboration_display.py`](mira/corroboration_display.py) |
| Frozen review | [`evidence_snapshot.py`](mira/evidence_snapshot.py), [`render.py`](mira/render.py), [`review_display.py`](mira/review_display.py) |
| Runtime and provider adapters | [`runner.py`](mira/runner.py), [`llm.py`](mira/llm.py), [`config.py`](mira/config.py) |
| User interface | [`streamlit_app.py`](app/streamlit_app.py); local staging [`app.py`](app.py) |
| Evaluation and historical evidence | [`eval/`](eval/), [`eval/evidence/`](eval/evidence/) |

The product owner and team maintain pilot acceptance and operating decisions in [PRD v3 §9](docs/mira_PRD_v3_draft.md#9-settled-decisions-and-remaining-policy-work). This documentation update does not change runtime configuration, source permissions, models or deployed services.
