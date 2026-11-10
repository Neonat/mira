# Research Console and Temporary BYOK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the approved research console with temporary per-request keys, an enforced USD API allowance, real research controls and measured country-method reporting.

**Architecture:** Extend Streamlit/Supabase RLS and the existing separate worker. A private local in-memory broker binds credentials to a user/workspace/run; immutable per-run clients share money/token/time admission. Current first-party prices live only in memory; approved experiment summaries remain separate from current run evidence.

**Tech Stack:** Existing Python/Streamlit, Supabase Auth/PostgreSQL, Unix sockets, Decimal, existing provider adapters and pytest/Chromium. No new frontend framework.

**Spec:** `docs/superpowers/specs/2026-11-10-research-console-byok-budget-design.md`; user explicitly approved implementation and temporary per-request keys on 10 November 2026.

## Global Constraints

- Keep Malaysia/DFSA/MAS disabled and hybrid experimental. No source permission grant or global model/effort/settings change.
- Preserve Ewen/PR6 ancestry, historic snapshots/HTML and complete saved source text; never inject benchmark facts or fabricate method winners.
- No provider key in database/settings/logs/artifacts/URLs/command arguments/`.env`. No worker database/capability import or credential in the UI.
- Broker pending-key TTL at most 60 minutes; one claim, exact identity binding, cleanup on completion/cancel/failure/approval pause/restart. No operator-key fallback for BYOK.
- USD only, Decimal arithmetic. Price catalogs/individual rates never persist. Unknown/ambiguous/unavailable prices fail before paid requests. All model/embedding/Exa attempts share cost admission.
- Read-only public pricing fetches are allowed; no paid model/embedding/Exa validation or general research worker launch without a new bounded user request.
- Coordinator owns shared contracts, runner/orchestration, migrations, docs, commits and push. One writer/file, max three workers plus root; no recursive delegation. Focused checks first, one final full suite after integration.

## Review Focus

- A queue write races credential binding: the worker must not claim a BYOK run until its handle is ready.
- Broker restart or plan-approval pause loses keys: re-entry is required and no time/cost allowance is renewed.
- Tier premiums, retries, parallel scouts and unknown usage: conservative money reservations must remain within allowance.
- Displayed source/depth/retrieval controls must change actual scoped worker behavior without bypassing grants.
- Synthetic/current/engineering results and unlabelled comparisons must remain visibly distinct; missing telemetry must not become zero cost or a winner.

### Task 1: Live first-party price quotes (bounded specialist)

**Files:** create `mira/pricing.py`, `tests/test_pricing.py`. Read-only existing `mira/llm.py`, `mira/discovery.py`, `mira/hybrid.py`.

**Interfaces:** `PricingError(ValueError)`; frozen `TokenRate(provider: str, model: str, input_per_million: Decimal, output_per_million: Decimal, context_threshold: int | None = None, high_input_multiplier: Decimal = Decimal(1), high_output_multiplier: Decimal = Decimal(1))` with `cost(tokens_in: int, tokens_out: int) -> Decimal`; frozen `PriceBook(rates: Mapping[str, TokenRate], exa_per_request: Decimal | None, exa_additional_result: Decimal | None, checked_at: str, sources: tuple[str, ...])` with `token_rate(provider: str, model: str) -> TokenRate`, `search_cost(result_limit: int) -> Decimal`, `metadata() -> dict` (only checked_at/source URLs, never rates). `load_price_book(models: Mapping[str,str], *, embedding_model: str | None = None, exa_enabled: bool = False, fetch_text: Callable[[str],str] | None = None) -> PriceBook`. Models maps roles to `provider:model`. Unknown/ambiguous models raise PricingError. Dated known model aliases may resolve explicitly; do not infer from arbitrary prefixes.

- [ ] Write failing tests for current-markup synthetic quote fixtures, input/output separation, context tiers, embeddings, Exa extra-result charges, no-rate metadata, unknown model, malformed/missing units, nonfinite/negative rates and bounded fixed-HTTPS transport.
- [ ] Run focused tests and record the expected missing implementation failures.
- [ ] Implement pricing using first-party bounded sources, no disk cache or live API keys. Current configured role models are `openai:gpt-5.4` and `openai:gpt-5.4-mini`; embedding profile is `text-embedding-3-small`. Other existing configured first-party Anthropic models may be supported only when complete prices can be validated. Use fixed provider URLs; provider data is untrusted.
- [ ] Run focused tests; a single read-only public-page contract check may validate adapters without persisting prices. Hand files/results to coordinator; no commit/push/full suite.

### Task 2: Temporary credential broker and client (coordinator)

**Files:** create `mira/credentials.py`, `mira/credential_broker.py`, `mira/credential_worker.py`, `tests/test_credentials.py`, `tests/test_credential_broker.py`; modify `mira/__main__.py` for an explicit broker command only.

**Interfaces:** UI-safe `BrokerClient(socket_path: str)` with `put(access_token: str, workspace_id: str, run_id: str, keys: Mapping[str,str]) -> str`, `revoke(access_token: str, handle: str) -> None`. Worker-only `mira.credential_worker.claim_keys(handle: str, workspace_id: str, user_id: str, run_id: str, *, socket_path: str, capability_path: str) -> dict[str,str]`. Broker validates Auth and queued-run ownership through fixed configured Supabase endpoints. No worker redemption/database import in UI-reachable client.

- [ ] Write failing real-socket/in-memory tests for identity/role/owner binding, expiry, replay, bad token, capability denial, oversize messages, cancellation, restart and safe error messages.
- [ ] Implement separate private client/worker sockets, in-memory entries, max 60-minute expiry, bounded messages/timeouts and no secret persistence. Worker capability is operator-only and contains no provider key.
- [ ] Verify that failed writes revoke handles and no keys escape repr/errors. Run focused tests and independent scoped review.

### Task 3: Money admission and per-run provider configuration (coordinator)

**Files:** create `mira/spending.py`, `tests/test_spending.py`; modify `mira/{generation,llm,discovery,hybrid,runner,budget}.py` and targeted existing accounting tests.

**Interfaces:** `SpendingLedger(max_usd: Decimal, price_book: PriceBook)` exposes reserve/settle/cancel and a safe aggregate snapshot. `RunBudget.max_cost_usd: str | None = None` preserves legacy rows; new BYOK source limits carry a positive decimal string. New provider instances accept explicit per-run immutable models/credentials and disable unpriced server fallback; they never mutate process globals or share credential caches across runs. Existing operator-managed CLI behavior stays compatible.

- [ ] Write failing tests for request reservation at correct model/context rates, concurrent spend, known/unknown costs, zero-cost refusals, retries, embedding/Exa inclusion and insufficient downstream reserve. Pin legacy token accounting.
- [ ] Integrate money reservations atomically with the existing shared GenerationBudget. Use serialized input upper bound and output cap separately; use actual usage for settled estimates, conservative reserves when unknown. A request must pass both money and existing token/time admission.
- [ ] Wrap Exa calls and embeddings in the same run ledger; keep API charges distinct from local browser/HTTP infrastructure. Surface safe aggregate money diagnostics; do not persist rate values.
- [ ] Replace hardcoded price-catalog usage for new runs. Unknown legacy cost is displayed as unavailable rather than $0; synthetic scripted usage stays explicitly synthetic. Preserve old artifact bytes.
- [ ] Run focused accounting/client tests and independent scoped review.

### Task 4: Scoped settings and queued worker integration (coordinator)

**Files:** create `mira/research_settings.py`, `tests/test_research_settings.py`, `tests/test_byok_run.py`; modify `mira/{brief,store,pg_store,runner,__main__,orchestrator}.py` and associated tests.

**Interfaces:** frozen `ResearchSettings` with `source_ids: tuple[str,...] | None`, `enable_exa: bool`, `enable_browser: bool`, `retrieval: str` (`keyword`/`hybrid`), `max_analysis_batches: int` (1..64), `credential_mode: str` (`operator`/`byok`), `credential_handle: str | None`; `from_dict(mapping)` and `as_dict()` reject secrets/unsupported fields. Settings live in retrieval_settings, with money/time/docs in source_limits and approval in Brief. Optional RunContext fields preserve old callers. User source IDs only restrict the workspace's current approved active set.

- [ ] Write failing tests for source subset gates, disabled grants, real method/depth switches, BYOK handle-ready claim filter, wrong/missing handles, no operator fallback and queue/claim races.
- [ ] Wire settings through queued run creation/loading and the normal worker; derive per-run adapters and analysis limits from allowed operator capabilities intersected with user restrictions. Keep exact current role models.
- [ ] Claim/release credentials after current workspace-role checks and before provider construction. Revoke at cancellation/failure; on plan pause drop keys and require a fresh lease for approval continuation without resetting spent allowance.
- [ ] Add deterministic per-run method/coverage/spend diagnostics for new report appendix; if frozen provenance requires new version/migration, implement matching SQL/Python validation with legacy-read compatibility.
- [ ] Run focused database and legacy pipeline checks plus scoped review.

### Task 5: Country results and the actual research console (bounded specialists, sequential ownership)

**Files:** create `mira/method_results.py`, `tests/test_method_results.py`; then modify `app/streamlit_app.py`, create `app/console_style.py`, `tests/test_research_console.py`. Shared backend files remain coordinator-only.

**Interfaces:** `country_method_results(country: str) -> dict` returns country/storage/acquisition/archive/research/references sourced only from approved portable evidence, with measured/recommended/not_tested/blocked and no_quality_winner statuses. UI consumes Task 1 price preview, Task 2 BrokerClient and Task 4 ResearchSettings; it uses normal Supabase user access for all run writes.

- [ ] Build failing evidence-integrity tests against source summaries: HK 153/153 archive and unlabelled 6-question latency comparison; real HK run's 19 facts/6-of-18 acquisition; AU format comparison; CBUAE direct-versus-challenged-browser observation; blocked countries and unmeasured storage costs. Do not expose other workspaces/source bodies or infer winners.
- [ ] Implement the curated results module and focused tests; hand ownership back before UI starts.
- [ ] Build UI regressions for synthetic labels, visible date/source/depth/retrieval/approval controls, USD instead of token primary input, missing-price/key disabled launch, clear-on-submit masked keys and queue failure cleanup. Existing review controls remain functional.
- [ ] Implement Research/Runs/Reports & review/Country methods using navy/teal/light evidence-console direction. Use current Streamlit controls and scoped RLS; show workspace identity and real worker/key/cost status. All exposed settings must reach actual run fields.
- [ ] Run focused UI/import-boundary tests; inspect the real local app in browser at desktop/mobile, including forms, navigation, quote errors, sample run/report and review. Use fake providers and synthetic keys only; do not click a paid research launch.

### Task 6: Integration, verification and PR delivery (coordinator)

**Files:** current README/PRD/development, new runbook/handoff, portable verification record; PR13 description.

- [ ] Independently review each task diff for spec and quality, resolve blockers, then obtain one final integrated review focusing credentials, money and evidence integrity.
- [ ] Run the full `pytest tests eval -q -p no:cacheprovider` suite once after integration with local PostgreSQL/actual Chromium. New failures/changes justify focused fixes and necessary recheck; no repeated unchanged proof runs.
- [ ] Validate the full new local console with the demo login and a bounded fake end-to-end worker invocation; keep research worker off afterward. Check broker cleanup and zero paid calls.
- [ ] Update README/current PRD/runbook and handoff with audience, controls, temporary-key lifecycle, current-pricing failure behavior, actual test results and remaining live uncertainty.
- [ ] Commit/push PR13, verify clean merge status/Ewen ancestry, preserve historical reports, provide UI link and report/comparison results. No merge, remote deployment or paid run implied.
