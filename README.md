# Mira

Mira is an agentic research assistant for internal auditors. An auditor picks a topic (for example AML/CFT) and the jurisdictions to cover. Mira then plans the research, gathers regulatory and industry developments from authoritative sources, checks every claim against a cited passage, and produces a structured draft report. The auditor reviews and signs off. Every source snapshot, plan, agent step, finding and report version is stored in Supabase Postgres so a reviewer can trace each statement back to its original publication.

**Build status: the current build is a Prototype/Minimum Viable Product (MVP).** It is an academic prototype, not a bank production system. A run works end to end on real regulator content:
- a brief, from the Streamlit app or the command line
- a plan
- scouts that fetch and save allow-listed pages
- a completeness check
- analyst claims
- verification
- a cited HTML report, then finding-level review and sign-off in the app

Still to build are listed under "Not built yet" below. The 24-item ground-truth list for the M0 recall gate (PRD v2 §11) is in [docs/mira_m0_ground_truth.md](docs/mira_m0_ground_truth.md) and needs review by a human auditor; the recall test itself has not been run.

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

The database tests in `tests/test_worker_db.py` and `tests/test_pipeline_db.py` run only when `MIRA_TEST_DATABASE_URL` points at a local database with all migrations applied; each test uses its own throwaway workspace. Every other test runs offline with a scripted model.

## Run Mira

With the local database running (see "Run the schema locally" below) and `.env` filled in:

```sh
.venv/bin/pip install -e ".[dev,llm,ui]"
.venv/bin/python -m mira seed                          # allow-list and expected-source list v1
.venv/bin/python -m mira worker                        # executes runs queued from the app
.venv/bin/streamlit run app/streamlit_app.py           # brief, live run view, report and review
```

The app signs in with Supabase Auth and works under row-level security. It reads only its own settings from `.env` and never the worker's database URL or the API key. The worker is the only process that calls Claude or fetches pages. For a quick run without the app:

```sh
.venv/bin/python -m mira run --jurisdictions HK --max-documents 15
.venv/bin/python -m mira usage RUN_ID                  # tokens and estimated cost per role
```

For sources that refuse automated access, MAS included, download documents in your browser and import them with their original URL. See [data/manual/README.md](data/manual/README.md).

```sh
.venv/bin/python -m mira import mas --manifest data/manual/mas/manifest.csv
```

The development token cap is `MIRA_MAX_LLM_TOKENS=300000` per run. The first live HK run (15 documents) used about 125,000 tokens, roughly US$0.55 at list prices.

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
| [`mira/report.py`](mira/report.py) | HTML report from saved records, with citations, the coverage table and the evidence appendix |
| [`mira/fetch.py`](mira/fetch.py) | `fetch_allowed`: allow-list, redirect re-checks, public addresses only, robots.txt, crawl delay, size and type caps, block-page detection |
| [`mira/extract.py`](mira/extract.py), [`mira/evidence.py`](mira/evidence.py) | Text, links and passages from HTML, PDF and RSS; every fetched page saved as a hashed version before any model reads it |
| [`mira/agents/scout.py`](mira/agents/scout.py), [`mira/agents/verifier.py`](mira/agents/verifier.py) | Scouts (feeds, hub pages, model-chosen links, PDF follow-through); verifier (`quote_match`, then a fresh-context model check) |
| [`mira/completeness.py`](mira/completeness.py) | Code-only coverage check against the expected-source list |
| [`mira/pg_store.py`](mira/pg_store.py), [`mira/runner.py`](mira/runner.py), [`mira/__main__.py`](mira/__main__.py) | Postgres run store, run creation and pick-up, and the `python -m mira` command line |
| [`mira/seed.py`](mira/seed.py) | Allow-list and expected-source list v1 |
| [`mira/manual_import.py`](mira/manual_import.py) | `python -m mira import`: documents downloaded by hand, saved like fetched pages and cited by their original URL |
| [`mira/single_agent.py`](mira/single_agent.py) | Single-agent comparison arm: a code-built plan and a quote-only verifier, run through the same orchestrator ([design](docs/single_agent_arm_design.md)) |
| [`eval/`](eval/) | Ground truth, recall scorer, precision worksheet, the three comparison arms and the decision rule |
| [`app/streamlit_app.py`](app/streamlit_app.py) | Streamlit app: brief, live run view, report, finding review and sign-off |

Models never see database IDs. A label a model invents is rejected in code, and the writer can cite verified claims only. Calls to Claude use server-side fallback (`fallbacks: "default"`) if a model declines, and each step records the model that actually answered.

Built since the first MVP:
- re-run from the app (Runs page) and the CLI (`python -m mira run --previous RUN_ID`): the same brief on the same Project revision, linked to the run it re-runs (PRD v2 §4 step 8, §6.5)
- a "what changed since the previous run" section: new, amended and no-longer-supported findings, built from verified claims only (PRD v2 §6.5, AG11)
- gap rounds: missing expected sources are re-planned and re-scouted, up to `MIRA_MAX_GAP_ROUNDS` (PRD v2 §6.4, AG09)
- plan approval: a run that needs approval stops after planning, before any source is fetched; an analyst or admin approves the plan on the Runs page, and the worker then resumes it on the approved plan, without planning again (PRD v2 §4)
- sign-off enforced in the database: a `reviewed` report cannot be inserted while a finding it cites has no reviewer decision (PRD v2 §6.6; migration `20261029120000`)
- reviewed reports rendered by the worker from the saved snapshot: no DRAFT watermark, the reviewer named by email, and the decision date shown (PRD v2 §6.6)
- guardrail fixtures: injected instructions in a fetched page have no effect, and seeded fabricated claims are caught by the quote check (PRD v2 §10 AG08, AG14)
- M0 recall scorer with the 50% gate (`eval/score_recall.py`, run with `pytest eval/`)
- the agent-design comparison harness: all three arms of PRD v2 §11 are built. Plain search is in `eval/arms.py`. The single agent is in `mira/single_agent.py`: a code-built plan and a quote-only verifier, run through the same orchestrator, as set out in the [single-agent design](docs/single_agent_arm_design.md). The multi-agent system is the default orchestrator. `eval/run_comparison.py` scores every arm with the same recall scorer, and `eval/compare.py` applies the decision rule. It refuses a verdict unless every arm ran with a live model client.
- precision worksheet (`eval/precision.py`): a fixed-seed sample of report claims with their cited passages. It is scored from human labels only, and reports no figure while any row is unlabelled.

Not built yet, or not yet proven:
- the **comparison itself**: the three arms have not been run against the briefs, so there is no verdict.
- **measured results**: the only live run so far was a development run on Hong Kong (15 documents, about 125,000 tokens; see "Run Mira"). It was made to check cost, not scored. There is no recall figure yet, and the M0 gate has not been passed or failed.
- **precision labels** (PRD v2 §11): the sample and worksheet are built, but no human has labelled any claims yet, so there is no precision figure.
- **the reviewed-report migration on a fresh Supabase stack**: migration `20261029120000` was applied to the local database and tested there, not yet to a freshly built stack.

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

   The import command exists (`python -m mira import`, see [data/manual/README.md](data/manual/README.md)). Until someone downloads the needed documents and imports them, their expected-source rows appear in every report as gaps, and the [M0 ground truth](docs/mira_m0_ground_truth.md) reports recall with and without them. Still open: who downloads them, and how often they are refreshed. Details: [approved sources](docs/mira_approved_sources.md#access-summary).
2. **Full-text search now; local embeddings later.** The MVP finds saved passages with Postgres full-text search (`search_passages`) only. The schema also supports semantic search with local `all-MiniLM-L6-v2` embeddings (`passage_embeddings`, `match_passages`, PRD v2 §5.4). That needs `sentence-transformers`, which installs about 2 GB of PyTorch, so it was left out. Without it, a scout misses passages that use different wording from its query; for example, it may not match "customer due diligence" to "CDD" or "know your customer". Revisit after measuring M0 recall: add embeddings if missed items trace back to wording.
3. **MAS permission to store text.** MAS's terms forbid storing or reproducing its content without prior written permission. On 26 October 2026 the team decided the prototype stores MAS text anyway, because the verifier needs saved passages. Still open: request written permission from MAS for the academic prototype, and keep report quotes short and attributed until it is granted (risk G7).
4. **MAS blocks automated access.** Since at least 26 October 2026, `www.mas.gov.sg` serves a "service unavailable" page with HTTP 200 to Mira's honest automated client: pages, `sitemap.xml` and PDFs all get it, although `robots.txt` allows all. Mira detects the page and reports MAS items as `fetch_failed`; it does not disguise itself or work around the block. Until this is resolved, Singapore regulatory coverage depends on MAS documents imported by hand with `python -m mira import mas` ([how](data/manual/README.md)), or on access agreed with MAS. Access can be raised together with the permission request in item 3.
5. **Sources Mira can read but not cite.** Wolfsberg, APG, Egmont, ABS, HKAB, JFIU, FSTB and the Basel Institute have `metadata` and `fetch` only, until their terms are reviewed for `store_text`. Their pages are saved as metadata, but no passages are stored, so no claim can cite them. Industry developments stay thin until this review is done.
