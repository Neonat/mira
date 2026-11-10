# Local development and operations

**Audience:** project developers, source curators and technical reviewers. Run commands from the repository root. The [README](../README.md) introduces the demonstrated product workflow to judges, DBS stakeholders and pilot auditors.

Use Python 3.11 or newer and a local Supabase/PostgreSQL stack configured through [the database guide](../supabase/README.md). Canonical schema history is in [`supabase/migrations/`](../supabase/migrations/).

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,llm,ui]"
cp .env.example .env
```

Configure the ignored `.env` with local connection settings, provider credentials and the agreed run allowances. Keep keys out of reports, logs and Git. The authenticated app uses Supabase Auth and workspace-scoped access; provider and worker database credentials stay on the worker side.

The sign-in password belongs to a Supabase Auth user, separately from the Supabase dashboard login, database password and API keys. `MIRA_DEV_EMAIL` only prefills the email field; it does not create a user or password. Provision the user and workspace membership through the operator's existing Auth setup, using an invitation or a configured [password-reset flow](https://supabase.com/docs/guides/auth/passwords). Existing passwords cannot be retrieved. The current app provides sign-in only, so invitations/reset links and their redirect handling must be configured separately for the intended local or hosted Auth instance.

For a new local workspace, initialise the source catalog, then start the worker and app in separate terminals:

```sh
.venv/bin/python -m mira seed
.venv/bin/python -m mira worker
.venv/bin/streamlit run app/streamlit_app.py
```

The source curator must retain workspace-specific permissions when refreshing defaults. **Keep MAS inactive for the current demo/validation configuration.** Manual imports require permission to retain the evidence; importing a document does not grant that permission. See [manual ingestion](../data/manual/README.md).

The separate local staging workbench is `streamlit run app.py`; it does not automatically publish evidence to Supabase. `MIRA_WORKSPACE_SLUG` selects the authenticated app's workspace and does not start a worker.

The client form accepts AML/CFT, controlled SG/HK/AU/AE choices (AE federal only), a 12–24-month lookback, an as-of date and document/token limits. It does not expose a free-text question, source/hybrid controls or a plan-approval switch. Queueing creates a run immediately; a trusted worker executes it. Reviewer/admin access remains separate from analyst/admin submission access.

Normal analysis defaults are eight whole passages/12,000 content characters per batch, eight batches maximum, 16,384 output tokens and a shared 180-second batch ceiling. One invalid-output correction may fit inside that ceiling and the remaining token allowance; it does not renew either. Explicit environment overrides still apply. A completed empty response means the batch was analysed, not that every fact was extracted. Complete saved text remains intact with explicit deferrals. The writer requests a bounded label plan rather than prose and allows 16,384 output tokens/120 seconds, subject to the shared run ledger. See [follow-up validation](agent-handoffs/analysis-writer-followup.md).

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

The recommended embedding profile is now configured and enabled in the two existing local development environment files. New installations keep the template flag off until explicitly enabled with an authorized run budget:

```dotenv
MIRA_ENABLE_HYBRID_RETRIEVAL=1
MIRA_EMBEDDING_MODEL=text-embedding-3-small
MIRA_EMBEDDING_REVISION=mira-te3-small-384-v1
MIRA_EMBEDDING_DIMENSIONS=384
```

The revision is an application-managed cache version, not an immutable provider snapshot. Change it when rebuilding embeddings after changing the model/profile. The OpenAI key and database worker connection stay server-side; the separate Supabase Storage upload key is not needed for pgvector retrieval. Restart an already-running worker to load changed environment settings. No worker was automatically started by this configuration update.

The normal worker now uses 40 passages **per indexing batch**, at most4 batches,60,000 cumulative input characters,20,000 embedding tokens,20 seconds and 20 results per task. Archive cardinality no longer disables semantic search. PostgreSQL ranks all compatible/current indexed eligible passages; the lexical arm searches eligible saved text using the existing scout full-text query. Only bounded top candidates/results are loaded into Python. Partial indexing is explicit in `embedding_usage`: eligible/indexed/pending/blocked passages, batches, stop reason, request/character/byte counts and known/unknown usage. Repeated jobs resume missing content-bound vectors. No whole-archive re-embedding is required for a query.

Index coverage counts refer to embedding-eligible passages. Text from sources without embedding permission may still be retrieved by the lexical path; no permission is expanded to improve semantic coverage.

An explicit worker-side backfill can prepare a larger archive independently of a research run. Preview makes no DB/provider call; `--execute` requires the existing enable flag/key and a current workspace analyst/admin actor:

```sh
python -m mira.hybrid_index --workspace WORKSPACE_UUID --actor ACTOR_UUID \
  --jurisdiction HK --as-of 2026-11-04 \
  --max-tokens 20000 --max-seconds 60 --max-batches 4 --max-characters 60000
# Add --execute to allow the explicitly budgeted cache writes and embedding requests.
```

This command never fetches pages or starts a research worker. A partial result retains completed batches and reports what remains. Whole passages above the conservative 8,192UTF-8-byte per-input bound remain stored/keyword-searchable and are counted as blocked; they are not truncated. Provider failures and database deadlines preserve measured usage/unknown reservations. Query statements use exact filtered pgvector ranking, not approximate nearest-neighbor recall claims; archive-scale latency is still unmeasured. The new source-validation migration also refuses cache publication after an embedding grant is revoked. Existing source `embed` permission, workspace, jurisdiction, selected version and as-of checks apply before provider work/ranking; MAS is excluded even from the archive path. Never enable MAS acquisition to populate the cache.

The [controlled live validation](../eval/evidence/2026-11-10-hybrid-embedding-validation.md) exercised the actual API, PostgreSQL cache and scout bridge with synthetic passages. It establishes integration behavior, not a new Hong Kong publication-recall or human-precision result.

The subsequent [archive experiment](../eval/evidence/2026-11-10-archive-hybrid-validation.md) compares the unchanged keyword query/ranking with hybrid at equal top-k on frozen saved-corpus questions. Hybrid remains experimental and optional; rank differences alone do not establish better relevance, report quality or research coverage.

## Durable storage and recovery

Private Supabase object copies and consistent full-database/object backup recovery are implemented as optional operator paths. See the [storage and recovery runbook](backup-recovery.md) for credential separation, verified publication, complete backup checks and fresh-local-target recovery. The anon key remains app-only. Configure a worker storage credential separately before enabling uploads.

Offline quality-validation preparation is in `eval/quality_preflight.py` and the read-only `eval/quality_export.py` adapter. Historical Hong Kong measurements keep their original Nov4 scope; proposals require a new bounded live-run authorization and do not invoke providers.

## Research console and per-request BYOK

See [the console runbook](research-console.md) for the local in-memory broker, UI/worker environment separation, current-price checks, USD admission and fresh-key approval continuation. Apply migration `20261110160000_mira_byok_resources.sql` before enabling new console runs. Operator CLI credentials remain separate; keys entered for one UI request never fall back to them. The UI loads only its anon/Auth configuration, role-model names and non-secret capability flags/socket path. Never start a research worker merely to inspect the demo.
