# Mira — AI research for bank auditors

Mira helps bank internal auditors answer questions like **“What changed in Hong Kong’s anti-money-laundering rules and guidance over the past year?”** The auditor chooses a topic, market and date range. Mira searches approved public sources, checks which claims the evidence supports, and prepares a draft report with links back to the publications. The auditor can inspect the evidence and decide what to approve.

Read Mira’s [Hong Kong AML/CFT demo report](https://neonat.github.io/mira-smu-ytp-aif-2026/report.html) for 4 November 2025 through 4 November 2026. The public edition includes 138 paraphrased factual findings, nine audit inferences and direct publisher links. The [Hugging Face portfolio dataset](https://huggingface.co/datasets/natsim/mira-hong-kong-aml-cft) contains an 18-publication research sample.

Mira was built for the SMU run of the [Young Talent Programme for AI in Finance](https://www.ibf.org.sg/home/for-financial-institutions/talent-development-and-training-support/develop-young-talent) in response to [DBS Internal Audit’s External Driver Researcher brief](docs/dbs_project_statement.md).

[Download the final demo presentation (PowerPoint)](slides/mira-final-presentation.pptx?raw=true). The deck’s QR code points to the original ChatGPT demo. Use the report and review game links here to open the portfolio versions.

## Gamified evidence review

In **Review the Finding**, you play a compliance reviewer at a fictional Hong Kong bank. Each of the three cases gives you a draft finding, a source excerpt and a date cutoff. Choose **Approve**, **Send back** or **Escalate**, then see how your decision compares with the suggested action and why. You can undo a decision, see your score and copy a case-by-case summary for coaching.

The practice game runs on GitHub Pages and keeps your decisions in the browser session. [Play Review the Finding](https://neonat.github.io/mira-smu-ytp-aif-2026/) · [How the cases work](docs/demo/hk-verification-game.md)

## Engineering highlights

Mira is a collaborative project, with development from
[@Neonat](https://github.com/Neonat), [@ewvnn](https://github.com/ewvnn) and
[@SaaiAravindhRaja](https://github.com/SaaiAravindhRaja) in the recorded history.

Three choices explain the project's engineering direction:

- **Traceable findings:** preserve source passages and connect generated claims
  to their evidence so an auditor can inspect the support.
- **Bounded research:** use typed outputs, explicit allowances and deterministic
  orchestration to make acquisition and follow-up work inspectable.
- **Reviewable releases:** preserve reviewer decisions and frozen evidence with
  reviewed report versions, keeping sign-off with the auditor.

The [validation section](#validation-and-prototype-status) separates recorded
engineering checks from the measured coverage of live research runs.

## From research brief to reviewed evidence

The prototype focuses on anti-money laundering and countering the financing of terrorism (AML/CFT) in Hong Kong, with configured sources for Singapore and scoped research in Australia and the federal UAE. Australia uses Federal Register metadata and publication files, plus AUSTRAC guidance subject to access checks. UAE federal research uses approved CBUAE publication hubs. MAS automated acquisition remains inactive. Malaysia and DIFC/DFSA are outside the enabled source set.

| Auditor's task | Mira's implemented workflow |
|---|---|
| Define the research | Topic, jurisdictions, reporting period, as-of date and run allowances, with optional plan approval |
| Gather relevant developments | Regulatory and industry scouts search approved saved evidence, publication indexes and scoped Exa discovery; permitted dynamic pages can use browser acquisition |
| Preserve article detail | Permitted document text and searchable passages stay alongside derived findings; bounded analysis batches record progress across saved passages |
| Request a report from prepared evidence | Scheduled jobs prepare evidence ahead of time. Requests use a fixed set of completed snapshots and wait if a selected source is refreshing |
| Check source support | Exact passage quotations, numeric checks and a separate-context semantic verifier; facts and inferences remain distinct |
| Inspect corroboration | Claim-level assessments show source independence, supporting or conflicting evidence, quotations and reasons |
| Follow the evidence | Readable source links, direct links to known PDF pages, and private original-file access where separately approved |
| Review and sign off | Finding-level accept/amend/reject/needs-evidence decisions; reviewed versions freeze the evidence, verification and reviewer outcomes |
| Research again | Re-run the saved brief and inspect new, amended and no-longer-supported findings |

Auditors retain ownership of professional judgement, audit actions and sign-off. Mira supplies the sourced developments and contextual risks and trends that support that work.

**Prepared archive report** is the default workflow in Research. A fresh draft
uses saved claims and their original evidence checks. It flags any included facts
that still need human review, both in the console and in the downloaded HTML.
Final approval is a separate reviewer action. **Full research** remains available
for new acquisition and analysis.

The research console lets analysts choose markets, custom dates, approved sources, discovery/browser options, keyword or experimental hybrid retrieval, analysis depth and optional plan approval. A separate review shows the selected request and current price units before masked API-key entry. Temporary per-request keys and a USD allowance support BYOK; provider prices are checked again by the worker and no rate catalogue is stored. Token, time and document limits remain additional safeguards. Users sign in through Supabase Auth with workspace access; a dedicated local demo login needs no hosted paid account. See the [console and BYOK runbook](docs/research-console.md).

The **Country methods** page separates measured results from recommendations and untested comparisons. It distinguishes the synthetic one-fact demo from the historical Hong Kong report’s 19 verified facts, and explains the 153-passage keyword/hybrid experiment. Full permitted evidence stays in PostgreSQL; vectors are an optional search index. No storage or retrieval quality winner is claimed without a comparable labelled evaluation.

## A report designed for auditors

The [Hong Kong report HTML](docs/portfolio/hong-kong-aml-cft-report.html) is a self-contained public edition of the final demo draft. It includes publication dates, links from the eight proof-of-concept inferences to their supporting findings, and two reviewed Wolfsberg paraphrases. Human evidence review is pending. The [public research sample](docs/portfolio/hong-kong-aml-cft.md) is also available as a table.

The report brings together regulatory developments, deadlines, supervisory themes, industry developments, contextual insights and an evidence appendix. Each finding carries its saved wording, fact/inference label, supported date and source references.

The writer returns a compact selection and ordering of verified findings. Code renders their complete saved wording and includes omitted findings in their main sections. Bounded analysis uses smaller whole-passage batches and allows one correction of invalid output within the existing time and token allowance.

New console runs also include selected methods, acquisition representation counts and cost/usage estimates in the coverage appendix. Corroboration appears in the generated report with its assessment, quotations and origin evidence. Passage analysis tracking and the source coverage checklist give reviewers a clear account of the research performed. Reviewed snapshots preserve the evidence and decisions behind the signed version.

Source navigation is built for readers: verified SFC API destinations open the corresponding readable publication page, and known PDF passages link to their page. Permitted original files use integrity checks and authenticated workspace access. Optional private object storage and verified backup/recovery support evidence continuity. Optional hybrid retrieval combines keyword and semantic ranking within source and usage controls.

The experimental hybrid profile uses OpenAI `text-embedding-3-small` with 384-dimensional pgvector storage. Bounded incremental indexing feeds database ranking across the eligible saved archive, with visible indexed/pending counts and the keyword path retained for comparison. See the [archive experiment](eval/evidence/2026-11-10-archive-hybrid-validation.md) for measured scope and usefulness limits.

Native API records and complete permitted extracted text stay in the evidence store independently of findings. Australian registration and effective dates remain separate; discovery metadata and viewer shells do not become legal-text citation passages. Source reuse notices travel with frozen report evidence. CBUAE text remains outside external embedding under the current grant.

## Alignment with the project brief

Sponsor: **DBS Bank, Internal Audit**. Project: *Agentic AI for Audit: External Driver Researcher*.

| Review area | What to inspect |
|---|---|
| Feasibility, value and application | The complete brief-to-reviewed-report workflow for the AML/CFT pilot |
| Governance, risk and ethics | Approved-source acquisition, workspace access controls, traceable evidence and human sign-off |
| Problem framing and industry relevance | Regulatory and industry research organised around an auditor's topic, markets and reporting period |
| Technical design and prototype | Specialist agents coordinated by deterministic code, typed outputs, shared evidence and bounded follow-up |
| Communication and presentation | Readable reports, direct source navigation, [presentation slides](slides/Mira_DBS_Presentation_v2.pptx) and a [recorded workflow showcase](docs/demo/launch-production-handoff.md) |
| Content quality and evidence | Publication-recall scoring, human citation-precision worksheets and preserved run evidence |

## Validation and prototype status

The [recorded engineering validation](docs/agent-handoffs/evidence-completeness.md) reports **691 tests plus 8 subtests, with no skips**, including local PostgreSQL and actual Chromium. Checks cover passage batching, frozen coverage and review, authenticated original-file access, source navigation and optional hybrid retrieval. The report's coverage layout was also inspected at desktop and mobile sizes.

The [prepared-report validation](docs/agent-handoffs/scheduled-evidence-reporting.md) covers refresh coordination, evidence review and asynchronous report assembly. A [local benchmark](eval/evidence/2026-11-10-prepared-report-benchmark.md) preserved all 20 expected facts from four synthetic publications in about 0.09 seconds per report once evidence was ready, with zero provider calls. The measurement excludes evidence preparation and does not measure live country coverage. The earlier [BYOK console validation](docs/agent-handoffs/research-console-byok.md) documents temporary keys, request isolation and spending controls.

The [8 November Hong Kong research follow-up](eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.md) acquired **6 of 18 benchmark publications** and cited **5 of 18**.

The latest scoped Australia/UAE exercise saved a partial draft through the live pipeline, with continuous database availability and exact usage accounting. Its [validation record](eval/evidence/2026-11-10-au-ae-uninterrupted-validation.md) distinguishes acquisition, verified country coverage, bounded analysis and remaining generation limits. The [previous interrupted run and recovered draft](eval/evidence/2026-11-10-generation-reliability-validation.md) remain preserved separately.

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
| Programme assessors, sponsors and pilot auditors | The [DBS brief](docs/dbs_project_statement.md), [slides](slides/Mira_DBS_Presentation_v2.pptx) and [workflow showcase](docs/demo/launch-production-handoff.md) |
| Product owner and technical reviewers | [Current PRD](docs/mira_PRD_v3_draft.md) and [feature status](docs/presentation/feature-status-2026-11-08.md) |
| Developers and source curators | [Setup, configuration and code reference](docs/development.md), [database guide](supabase/README.md) and [ingestion quickstart](docs/ingestion-quickstart.md) |
| Maintainers checking design history | [PRD v2](docs/mira_PRD_v2.md), [archived v1](docs/archive/mira_PRD_v1.md), [change proposal](docs/mira_prd_changes.md) and [coordinator handoff](docs/agent-handoffs/README.md) |
