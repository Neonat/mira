# Local development and operations

**Audience:** project developers, source curators and technical reviewers. Run commands from the repository root. The [README](../README.md) introduces the demonstrated product workflow to judges, DBS stakeholders and pilot auditors.

Use Python 3.11 or newer and a local Supabase/PostgreSQL stack configured through [the database guide](../supabase/README.md). Canonical schema history is in [`supabase/migrations/`](../supabase/migrations/).

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

The source curator must retain workspace-specific permissions when refreshing defaults. **Keep MAS inactive for the current demo/validation configuration.** Manual imports require permission to retain the evidence; importing a document does not grant that permission. See [manual ingestion](../data/manual/README.md).

The separate local staging workbench is `streamlit run app.py`; it does not automatically publish evidence to Supabase. `MIRA_WORKSPACE_SLUG` selects the authenticated app's workspace and does not start a worker.

A CLI research run and its usage summary are available when the operator has configured the provider budget:

```sh
.venv/bin/python -m mira run --jurisdictions HK --max-documents 15
.venv/bin/python -m mira usage RUN_ID
```

## Optional acquisition

| Capability | Configuration and boundary |
|---|---|
| Exa URL discovery | `MIRA_ENABLE_EXA_DISCOVERY=1` and `EXA_API_KEY`; results remain task/source/date-scoped metadata until separately permitted acquisition and saving |
| Offline browser extraction | `MIRA_ENABLE_OFFLINE_BROWSER=1`, optional browser dependencies and source opt-in |
| Live browser acquisition | `MIRA_ENABLE_LIVE_BROWSER=1`, compatible Chromium and explicit per-source browser approval/reference; retrying an HTTP block requires separate permission |

Browser acquisition uses deterministic Chromium navigation, JavaScript and at most three configured read-only click/wait actions. It respects source and robots policy, uses fresh sessions and preserves capture/extraction provenance. It does not solve login/CAPTCHA challenges or disguise access. HTTP and browser attempts consume their own allowances. Details: [browser integration](agent-handoffs/live-browser-integration.md).

## Evidence storage and review

Where storage is permitted, Mira saves the complete **extracted text** of a document version and its searchable passages before producing findings. Findings link to those passages; keeping fact A does not replace the saved article with a summary of A. Passage selection for a particular run is bounded by its scope and allowances.

Sign-off freezes the retained claim text, evidence, verification inputs, corroboration and reviewer decisions. Later searches do not change that reviewed version. Technical provenance remains available in the appendix; primary report content is written for auditors. Storage/retention details are in [PRD v3 §8](mira_PRD_v3_draft.md#8-source-permissions-security-and-operational-constraints).

## Tests and evaluation

```sh
.venv/bin/python -m pytest tests eval
```

Database tests require `MIRA_TEST_DATABASE_URL` pointing at an isolated **local** database with current migrations. Browser integration fixtures require the optional browser dependencies and a compatible Chromium executable. Tests use controlled fixtures and scripted models; they do not authorise a paid research run. Do not reset or migrate a shared database as part of local setup.

The three-arm evaluation tools are in [`eval/`](../eval/): plain search, single agent and multi-agent use the same scoped publication scorer. Human precision labels are recorded separately. Live comparison runs require their own approved budget; the runner, measurement policy and interpretation are described in [PRD v3 §7](mira_PRD_v3_draft.md#7-evaluation-and-release-evidence).

## Code reference — engineering team

| Area | Modules |
|---|---|
| Typed contracts and orchestration | [`contracts.py`](../mira/contracts.py), [`orchestrator.py`](../mira/orchestrator.py), [`budget.py`](../mira/budget.py) |
| Specialist agents | [`agents/`](../mira/agents/), [`interfaces.py`](../mira/interfaces.py) |
| Discovery and acquisition | [`discovery.py`](../mira/discovery.py), [`fetch.py`](../mira/fetch.py), [`live_browser.py`](../mira/live_browser.py), [`extract.py`](../mira/extract.py) |
| Saved source evidence | [`evidence.py`](../mira/evidence.py), [`store.py`](../mira/store.py), [`pg_store.py`](../mira/pg_store.py) |
| Corroboration | [`corroboration.py`](../mira/corroboration.py), [`corroboration_runtime.py`](../mira/corroboration_runtime.py), [`corroboration_store.py`](../mira/corroboration_store.py) |
| Reports and reader links | [`report.py`](../mira/report.py), [`source_links.py`](../mira/source_links.py), [`corroboration_display.py`](../mira/corroboration_display.py) |
| Frozen review | [`evidence_snapshot.py`](../mira/evidence_snapshot.py), [`render.py`](../mira/render.py), [`review_display.py`](../mira/review_display.py) |
| Runtime and provider adapters | [`runner.py`](../mira/runner.py), [`llm.py`](../mira/llm.py), [`config.py`](../mira/config.py) |
| User interface | [`streamlit_app.py`](../app/streamlit_app.py); local staging [`app.py`](../app.py) |
| Evaluation and historical evidence | [`eval/`](../eval/), [`eval/evidence/`](../eval/evidence/) |

The product owner and team maintain pilot acceptance and operating decisions in [PRD v3 §9](mira_PRD_v3_draft.md#9-settled-decisions-and-remaining-policy-work). This documentation update does not change runtime configuration, source permissions, models or deployed services.

## Evidence completeness — worker configuration

Normal workers analyse up to 12 whole passages and 18,000 content characters per batch, with eight batches maximum and shared run limits taking precedence. Unprocessed work remains stored and appears in the frozen coverage summary; a valid response does not certify exhaustive fact extraction. The comparison arm retains its existing policy. See `.env.example` for limits and verification/report reserves.

Original retention and hybrid retrieval are off by default. Retention additionally requires a source `connector_config.original_retention` approval and reference, private storage shared by worker and authenticated app, and a backup policy for deployment. Hybrid retrieval requires an explicit embedding model/revision, compatible 384-dimensional vectors and the source `embed` permission. Its bounded candidate pool falls back to keyword retrieval when limits or acquisition errors prevent semantic ranking. MAS automated acquisition remains disabled; no new source grants are supplied by this update. Apply the new migrations locally before running the updated worker.
