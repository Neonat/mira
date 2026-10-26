# Mira

Mira is an agentic research assistant for internal auditors. An auditor picks a topic (for example AML/CFT) and the jurisdictions to cover. Mira then plans the research, gathers regulatory and industry developments from authoritative sources, checks every claim against a cited passage, and produces a structured draft report. The auditor reviews and signs off. Every source snapshot, plan, agent step, finding and report version is stored in Supabase Postgres so a reviewer can trace each statement back to its original publication.

**Build status: the current build is a Prototype/Minimum Viable Product (MVP).** It is an academic prototype, not a bank production system. This repository contains the database foundation, the product documents and the first M1 code: the orchestrator, the planner, analyst and writer agents, and the HTML report renderer. The scouts and fetch tools, the verifier, the Postgres run store and the user interface are specified in [PRD v2](docs/mira_PRD_v2.md) and are still to be built. The 24-item ground-truth list for the M0 recall gate (PRD v2 §11) is in [docs/mira_m0_ground_truth.md](docs/mira_m0_ground_truth.md) and needs review by a human auditor; the recall test itself has not been run.

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

The database tests in `tests/test_worker_db.py` run only when `MIRA_TEST_DATABASE_URL` points at a disposable local database with all migrations applied. Every other test runs offline with a scripted model. To call Claude, also install the `llm` extra: `.venv/bin/pip install -e ".[dev,llm]"`.

## Code layout

| Module | What it does |
|---|---|
| [`mira/contracts.py`](mira/contracts.py) | Data formats passed between agents, and the short labels models cite |
| [`mira/db.py`](mira/db.py) | The worker's direct Postgres connection, acting as the initiating user |
| [`mira/orchestrator.py`](mira/orchestrator.py) | State machine: plan, scout, analyse, verify, write; budgets, cancellation, one `agent_steps` row per step |
| [`mira/agents/`](mira/agents/) | Planner, analyst (including the rewrite of a partially supported claim) and writer prompts, with code checks on their output |
| [`mira/interfaces.py`](mira/interfaces.py) | `Scout` and `Verifier` interfaces the orchestrator calls |
| [`mira/store.py`](mira/store.py) | `RunStore` interface to the evidence store, and an in-memory version for tests |
| [`mira/llm.py`](mira/llm.py) | Structured-output calls to Claude per role (`MIRA_MODEL_<ROLE>`), one repair retry, and a scripted client |
| [`mira/budget.py`](mira/budget.py), [`mira/brief.py`](mira/brief.py) | Run budgets (§6.2); brief scope and storage (AG01) |
| [`mira/report.py`](mira/report.py) | HTML report from saved records, with citations and the evidence appendix |

Models never see database IDs. A label a model invents is rejected in code, and the writer can cite verified claims only. Calls to Claude use server-side fallback (`fallbacks: "default"`) if a model declines, and each step records the model that actually answered.

Not built yet: waiting for plan approval, gap-filling rounds and the completeness check (M2), and the re-run diff (M3).

## Run the schema locally

Install the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) (`brew install supabase/tap/supabase`) and Docker, then from this repository run:

```sh
supabase start -x realtime,storage-api,imgproxy,edge-runtime,logflare,vector,supavisor,mailpit
supabase status
```

The `-x` list skips services Mira does not use, so the stack fits in about 0.5 GB of Docker memory. Mira's local ports are in the 55xxx range so it can run beside another project on the CLI defaults: API 55421, database 55432, Studio 55423.

The local stack applies the checked-in migrations. Database tests run against it with:

```sh
MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres .venv/bin/python -m pytest
```

For a local login, create a user in Studio (http://127.0.0.1:55423, Authentication) and add it to the `mira` workspace as `admin` with the SQL in the [engineering guide](docs/archive/mira-engineering-guide.md#roles-and-access). Keep its email and password in `.env` as `MIRA_DEV_EMAIL` and `MIRA_DEV_PASSWORD`.

To recreate the **local** database from those migrations:

```sh
supabase db reset
```

`db reset` deletes and rebuilds its target database. Use it only with the local stack here. Do not add `--linked`; that targets a remote project. The team’s shared project already has these two migration versions applied. Do not push migrations to a remote project without first confirming the selected account/project and reviewing `supabase db push --dry-run --linked` with the database owner.

Never commit database passwords, access tokens, service-role keys, or real environment files. The service-role key bypasses row-level security and must stay on trusted server processes.

## Additional notes to address

Bookmarks for decisions and gaps deferred during the MVP build. Each needs a decision before the prototype is presented as complete.

1. **Manual downloads for sources that refuse automated access.** These sources block automated fetching through `robots.txt` or HTTP 403, and Mira does not work around that:
   - Singapore Statutes Online: CDSA, Terrorism (Suppression of Financing) Act, FSMA 2022
   - HK e-Legislation: AMLO, Cap. 615
   - FATF
   - BIS

   Until someone downloads the needed documents and imports them as `manual` sources, their expected-source rows appear in every report as gaps, and the [M0 ground truth](docs/mira_m0_ground_truth.md) reports recall with and without them. Still open: who downloads them, and how often they are refreshed. Details: [approved sources](docs/mira_approved_sources.md#access-summary).
2. **Full-text search now; local embeddings later.** The MVP finds saved passages with Postgres full-text search (`search_passages`) only. The schema also supports semantic search with local `all-MiniLM-L6-v2` embeddings (`passage_embeddings`, `match_passages`, PRD v2 §5.4). That needs `sentence-transformers`, which installs about 2 GB of PyTorch, so it was left out. Without it, a scout misses passages that use different wording from its query; for example, it may not match "customer due diligence" to "CDD" or "know your customer". Revisit after measuring M0 recall: add embeddings if missed items trace back to wording.
3. **MAS permission to store text.** MAS's terms forbid storing or reproducing its content without prior written permission. On 26 October 2026 the team decided the prototype stores MAS text anyway, because the verifier needs saved passages. Still open: request written permission from MAS for the academic prototype, and keep report quotes short and attributed until it is granted (risk G7).
