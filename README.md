# Mira

Mira is an agentic research assistant for internal auditors. An auditor picks a topic (for example AML/CFT) and the jurisdictions to cover. Mira then plans the research, gathers regulatory and industry developments from authoritative sources, checks every claim against a cited passage, and produces a structured draft report. The auditor reviews and signs off. Every source snapshot, plan, agent step, finding and report version is stored in Supabase Postgres so a reviewer can trace each statement back to its original publication.

**Build status: the current build is a Prototype/Minimum Viable Product (MVP).** It is an academic prototype, not a bank production system. This repository contains the database foundation and the product documents. The agent workflow, source connectors, user interface and report renderer are specified in [PRD v2](docs/mira_PRD_v2.md) and are still to be built.

## Start here

- [PRD v2](docs/mira_PRD_v2.md): the primary, current product requirements, agent architecture, guardrails and MVP scope.
- [`supabase/migrations/`](supabase/migrations/): canonical, ordered schema history.
- [`supabase/config.toml`](supabase/config.toml): local Supabase development configuration.

Background documents: [DBS problem statement](docs/dbs_project_statement.md), [grading rubric](docs/project_grading_rubrics.md) and [proposed PRD changes](docs/mira_prd_changes.md).

Retired documents are kept in [`docs/archive/`](docs/archive/) for history only: PRD v1, the engineering guide and the agentic feasibility analysis. Where they disagree with PRD v2, PRD v2 wins.

## How Mira answers the DBS problem statement

Sponsor: DBS Bank, Internal Audit. Project: *Agentic AI for Audit: External Driver Researcher*.

The brief asks for an agentic tool that lets auditors select a topic and jurisdictions and receive a structured report on regulatory and industry developments, with guardrails for traceability, completeness and hallucinations. The table maps each requirement to Mira's design and its MVP status.

| Brief requirement | How Mira meets it | MVP status |
|---|---|---|
| Select a topic | Research brief form: topic, jurisdictions, period, as-of date | In MVP (AML/CFT only) |
| Define jurisdictions/regions | Jurisdiction picker plus configurable region mapping (`market_region_mappings`) | In MVP (Singapore, Hong Kong) |
| Generate a structured report | Writer agent assembles a fixed-section report from verified claims only; HTML and JSON export | In MVP |
| Multi-agent workflow | Planner, regulatory scouts (one per jurisdiction), industry scout, analyst, verifier, completeness checker, writer, coordinated by a code-level orchestrator | In MVP; the reader role is merged into the scouts |
| **A. Monitor** regulator announcements, consultations, guidelines, enforcement | Scouts start from an allow-listed list of regulator pages (MAS, HKMA, SFC and others) | In MVP (on-demand runs); scheduled monitoring is a stretch goal |
| **A. Identify and summarize** new, amended or upcoming rules | Analyst writes plain-language obligation summaries tagged new, amended or upcoming | In MVP |
| **A. Track timelines** | Deadlines and consultation timeline section built from `regulation_versions` effective dates | In MVP |
| **A. Assess impact** | Risks, opportunities and suggested audit actions, with priority kept separate from evidence confidence | In MVP |
| **A. Compare jurisdictions** | Jurisdiction comparison matrix: common themes and regional differences | In MVP |
| **A. Analyze trends** | Supervisory focus areas over the selected period, with the coverage basis stated | In MVP (12 to 24 months) |
| **A. Verify** with source links | Every claim cites an exact document version and passage with the original URL | In MVP |
| **B. Industry monitoring**: news, events, incidents, case studies | Industry scout plus the existing incident model | In MVP |
| **B. Trends, best practices, innovations** | Industry developments section | In MVP |
| Guardrail: factual accuracy and traceability | Independent verifier agent; a claim with no supporting passage never reaches the report | In MVP |
| Guardrail: completeness | Completeness checker compares findings to an expected-source list per jurisdiction; remaining gaps are printed in the report | In MVP |
| Guardrail: hallucination detection | Verifier, deterministic quote matching and citation-precision evaluation | In MVP |
| Intuitive user interface | Streamlit app: brief form, live run view, report and review screen | In MVP |

## How Mira addresses the grading rubric

| Rubric criterion (weight) | Where to look | What we show |
|---|---|---|
| Feasibility, Value and Application (15%) | PRD v2 §2, §12; feasibility analysis | Business case: auditor hours saved per report, measured against a manual baseline; narrow MVP that a three-person team can deliver |
| Governance, Risk and Ethics (25%) | PRD v2 §7 | Risk register with mitigations: hallucination, incompleteness, prompt injection, data leakage, over-reliance, model drift, cost; human sign-off; no compliance conclusions about the bank |
| Problem Framing and Industry Relevance (20%) | PRD v2 §1, §3 | Scope tied clause by clause to the DBS brief; AML/CFT for Singapore and Hong Kong as the pilot |
| Technical Design and Prototype (15%) | PRD v2 §5, §6, §8 | Role-based multi-agent design, with an LLM used only where judgement is needed; reproducible runs; the Supabase evidence store as agent memory |
| Communication and Presentation (15%) | This README, PRD v2 | One-page journey, architecture diagram, live demo of a run |
| Content Quality and Evidence (10%) | PRD v2 §11 | Citation precision, coverage against a hand-labelled list of real developments, and a comparison of plain search, a single agent and multiple agents |

## Python setup

Python 3.11 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # then add your API key
.venv/bin/python -m pytest
```

[`mira/contracts.py`](mira/contracts.py) defines the data formats passed between agents; [`mira/db.py`](mira/db.py) is the worker's database connection. The database tests in `tests/test_worker_db.py` run only when `MIRA_TEST_DATABASE_URL` points at a disposable local database with all migrations applied.

## Run the schema locally

Install the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) and Docker, then from this repository run:

```sh
supabase start
supabase status
```

The local stack applies the checked-in migrations. To recreate the **local** database from those migrations:

```sh
supabase db reset
```

`db reset` deletes and rebuilds its target database. Use it only with the local stack here. Do not add `--linked`; that targets a remote project. The team’s shared project already has these two migration versions applied. Do not push migrations to a remote project without first confirming the selected account/project and reviewing `supabase db push --dry-run --linked` with the database owner.

Never commit database passwords, access tokens, service-role keys, or real environment files. The service-role key bypasses row-level security and must stay on trusted server processes.
