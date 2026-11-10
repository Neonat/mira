# Mira research console, temporary BYOK and money budgets

Date: 10 November 2026, Asia/Singapore. Base: `96173b65a0a717a669de2f71e4749c75833bb167`, PR13. **Proposed design; not implemented or approved yet.**

## Intent and audience

Bank internal-audit analysts need a useful research console with control over research breadth, acquisition and retrieval, a comprehensible spending allowance, and evidence of the methods used. Senior reviewers need visible coverage, unresolved findings, provenance and sign-off. Competition judges should be able to distinguish a working workflow from a synthetic example and measured performance from a recommendation.

User requirements: improve the plain UI and limited controls; address the misleading one-fact Hong Kong demo; report country-specific acquisition/storage/retrieval results; support BYOK; choose a cost allowance rather than model tokens; obtain current provider pricing rather than persisting a price catalog. The user explicitly selected **temporary keys per request**, not saved encrypted credentials.

The current demo contains one synthetic fact and one synthetic inference. It is not a Hong Kong coverage measurement. No minimum finding count will be fabricated; improvements must expose and address discovery, analysis and verification coverage separately.

## Approach and size

This is a coordinated product/backend change. Extend the existing Streamlit app, Supabase Auth/RLS and separate trusted worker. Reuse current reports and review controls; add navigation, hierarchy and real research controls. This is the coordinator's recommended implementation choice, not an approved framework change.

Alternatives considered: a separate React frontend would add another application and duplicate working access/review flows; saving provider keys in a persistent vault would conflict with the selected per-request lifetime. A cosmetic dashboard alone would leave the worker, monetary enforcement and method reporting unchanged. These do not meet the requested scope as efficiently as extending the current app.

## User experience

Visual direction: an editorial research console with a light warm-neutral canvas, institutional navy headings/navigation, teal actions, restrained amber warnings and generous spacing around evidence. Use existing accessible controls, visible labels, responsive columns and a clear primary action per screen. Avoid decorative charts and large technical captions.

Navigation: **Research**, **Runs**, **Reports & review**, **Country methods**. Display the signed-in workspace and a persistent **Synthetic demo** banner for the isolated demo workspace. Never combine its findings with historical measured research. The operator supplies this mode/label; a client cannot relabel arbitrary live research as synthetic.

Research setup has three visible groups:

1. **Scope:** AML/CFT; current SG/HK/AU/AE controls with unavailable sources shown explicitly; preset lookback or custom ordered dates; as-of date; selected approved sources; regulatory/industry focus where supported by the existing planner. No unrestricted free-text question or internal documents in this pass.
2. **Methods & depth:** recommended mixed acquisition using approved official indexes/native APIs/direct publications, optional Exa discovery, optional permitted browser acquisition, keyword or experimental hybrid retrieval; document, duration and whole-passage analysis-batch limits under Advanced. Controls may restrict operator capabilities but never grant blocked acquisition/storage/embedding or activate a disabled source. Full evidence retention remains automatic and independent of these limits. Exa discovers URLs; browser/HTTP acquires publications. These are separate controls rather than exclusive country engines.
3. **Keys & budget:** masked inputs only for providers needed by the unchanged configured role-model profile, plus Exa if selected and the embedding provider if hybrid is selected. Show which provider powers which component. Enter an estimated maximum API cost in **USD**, with source/checked-at for current prices and an itemised estimate. Tokens remain an internal safety limit, not the main user input. No API-key balance or account-specific tariff is inferred from the key.

Before launch, show a review of scope, allowed methods, requested depth, USD allowance, estimated fixed/discretionary charges, time limit and key lifetime. Expose plan approval as a real option. Starting a paid request requires the user's launch action; typing a key or opening a page starts no research. In the local demo, provider execution remains off until intentionally enabled by the operator; synthetic examples can still be explored.

Run view: status, country/source coverage, verified facts and inferences, publications/passages acquired and analysed, failures and deferrals, cost allowance/known estimated cost/unknown reservations, actual methods and source-specific exclusions. Partial or synthetic results are visibly labelled. More generated text or repeated claims is not treated as greater publication coverage.

Reports retain readable citations, corroboration and review. Add a code-generated methods/coverage appendix for new reports; preserve historical HTML/snapshots byte-for-byte. Record acquisition and retrieval choices/outcomes separately from the research findings. If frozen provenance needs a schema extension, use a new version and matching Python/SQL validation; do not backfill historical evidence.

## Temporary keys and the worker boundary

The app currently queues jobs through Supabase as the signed-in user; a separate worker holds the database credential. Session memory alone cannot deliver a key to that process. Do not put provider keys in run rows, JSON settings, logs, artifacts, URLs, persistent storage or `.env`, and do not import worker/database code into the UI.

Add a local **in-memory credential broker** with Unix-domain sockets, bounded messages and private socket permissions. A public-client operation verifies the Supabase access token against the configured Auth service and checks that the caller owns an accessible queued run. It binds credentials to exact user/workspace/run identities and an opaque random handle. The separate worker operation is restricted by an operator-only local capability and rechecks the run's current workspace/actor before redeeming. No list/get-other-user operation exists. The app receives no worker capability or database credential.

Lifetime: pending credentials expire after at most 60 minutes; claimed credentials leave the broker and live only in that run's worker/provider subprocesses. They are discarded in `finally` on completion, failure or cancellation. A broker restart drops all pending keys and never recovers them from disk. Cancellation before claim revokes the handle; it cannot reverse an already sent provider request. An expired/missing handle causes a clear local refusal and a request to re-enter keys, with zero fallback to the operator's key. New BYOK runs never silently borrow server credentials. Existing explicitly operator-managed CLI runs preserve their existing credential path.

Per-run clients receive an explicit immutable credential mapping; do not mutate global environment variables or share credential-bearing client caches between runs. Provider children receive secrets through private process input/configuration, never command arguments or logs. Fixed first-party provider endpoints prevent a user-supplied base URL from receiving keys. The broker is a local deployment boundary, not a hosted multi-machine credential service; remote deployment is outside this pass.

Approval pause: planner execution consumes the first invocation's key lease. When the worker pauses for plan approval it drops those keys. Approve-and-run asks for fresh keys and creates a new bound lease under the remaining allowance; it never renews cost/time budgets. Cancellation, failed queue writes and abandoned preflight handles revoke pending keys. Broker startup and sample-data loading do not start a research worker.

## Dynamic pricing and monetary admission

Fetch provider first-party pricing when preparing/starting a run, using fixed allowlisted HTTPS sources and bounded requests. Initial scope: the existing directly configured OpenAI/Anthropic model profile, OpenAI embeddings if enabled, and the existing Exa Auto URL-discovery endpoint. Do not change role models/effort or global settings. Do not save a provider rate catalog in the database, repository or persistent cache. One validated quote set may live in memory for the active invocation; an approval continuation fetches current quotes again.

Pricing is **an estimated public first-party API cost**, not an invoice or a guarantee about credits, negotiated discounts, taxes or external infrastructure. Show this distinction. A normal project key does not establish a billing plan or exact effective tariff. The current hardcoded model-price dictionary cannot enforce the requested budget and must not be a fallback for money-limited runs.

If a selected model/endpoint cannot be priced unambiguously, currency/units are unsupported, the quote source fails, or required tier information is missing, disable paid launch/refuse the next request before sending it. Never treat an unknown model as zero cost. Current quotes must cover the actual provider/model and service tier, input/output and relevant long-context premiums; cache discounts need not be assumed. No paid built-in search/tool mode is enabled without a priced adapter.

Use `Decimal` money and a thread-safe shared ledger spanning model calls, embeddings and Exa. Admit each outgoing request only when known estimated charges + unknown attempted-charge reservations + pending reservations + the request's conservative maximum fits the USD allowance, while preserving downstream writer/verifier headroom. A single global token conversion using an assumed input/output split is insufficient. Reserve separately for serialized input upper bounds, configured output caps, relevant price tiers and bounded Exa results. Local browser/HTTP has no provider API fee here; its infrastructure cost is outside this allowance and must not be presented as universally free.

Settle successful calls from measured usage at applicable quoted rates (conservative uncached estimates are labelled); retain conservative monetary reservation on unknown sent usage, and charge zero for requests not sent. Retries, corroboration, embedding and concurrent scouts share this same ledger. Account for selected fallback models or refuse an unpriced fallback. Provider error bodies never enter the ledger. Keep the token/time/document caps as additional worker safety bounds.

Persist only the user's USD allowance, actual usage, aggregate estimated charge/reservation totals, source URLs/check timestamps and methods/results needed to explain the run. Do not persist quote tables or individual provider rate values. Historical costs remain labelled estimates calculated during the run; do not silently reprice past work when reopening it. If granular provider usage is unavailable, report that limitation rather than presenting a provider-billed amount.

## Country methods and comparisons

PostgreSQL retains complete permitted extracted text/native records, passages and provenance for all countries. Private original-byte storage remains separately permissioned. pgvector is an optional rebuildable ranking index alongside this evidence, never a replacement for source text. Do not offer a destructive normal-versus-vector storage switch.

Country methods page has a country selector, acquisition table (official API/direct HTTP/PDF/Exa/browser), archive-search table (keyword/hybrid), and clear status columns: **measured**, **recommended**, **not tested**, **blocked**. Show corpus/date/sample scope, complete-text/offset checks, publication/passage coverage, verified findings when available, latency, request/usage charges where measured, errors and limitations. One result cannot stand in for a national benchmark. Comparisons need the same corpus/query set and declared denominator; acquisition stages that do different jobs are reported separately.

Use approved portable evidence summaries, never private source bodies, keys, raw logs or arbitrary paths. These engineering observations are labelled separately from the signed-in workspace's current run; they confer no access to other workspaces. A winner requires an applicable controlled result and relevant quality labels. Otherwise display **No quality winner established** with the measured tradeoff.

Current evidence to surface:

- **Hong Kong:** the real full-archive experiment indexed 153/153 saved passages. Six frozen questions were unlabelled; median keyword latency 0.0084s and hybrid including query embedding 0.80705s. Controlled synonym tests help demonstrate the mechanism, not human relevance on the real archive. The one-fact demo is separate. Prior research acquisition/citation recall and verified findings remain tied to their individual run/date/profile. Exa/browser ablation is not established.
- **Australia:** Federal Register API for identity/version discovery plus complete direct publication HTML/PDF; in the format pilot 20/20 sampled HTML prefixes appeared in the full PDF and 0/20 in the browser landing page. This compares representations, not universal browser accuracy. AUSTRAC remains subject to live access checks. The 30-passage pilot had unlabelled ranking changes, so no hybrid quality winner.
- **UAE federal:** approved CBUAE hub/direct PDF acquired an eight-page publication; the browser capture encountered an access challenge. Prefer the approved direct route for that tested source. External embedding remains disabled under the grant; no UAE hybrid quality winner.
- **Malaysia, DIFC/DFSA and MAS:** disabled as before. No UI control or BYOK bypasses these restrictions.

Sources: `eval/evidence/2026-11-10-country-method-pilot.{md,json}`, `2026-11-10-archive-hybrid-validation.{md,json}`, `2026-11-10-au-ae-uninterrupted-validation.{md,json}`, and the dated HK evidence. Preserve their original scope and hashes. A curated export should carry references/provenance, not copy fabricated causal claims into reports.

## Research breadth and the Hong Kong concern

The demo must be unmistakably synthetic, and the real measured results must be available separately. Add visible analysis depth/coverage with the ability to fund additional whole-passage batches inside the selected cost/time/document envelope. Explicitly retain deferred/failed passage reasons. A larger batch count can improve opportunity for analysis; it cannot guarantee facts or national recall. Verification, source dates, exact quotations, numeric guards and inference separation remain mandatory. Do not insert hand-picked benchmark findings or increase factual output by weakening verification.

A fresh real Hong Kong report/comparative research run is a separate paid validation with an explicit per-request allowance. Prior consumed test authorizations do not roll over. This design authorizes implementation and automated/offline checks, not an unbounded research campaign.

## Verification and delivery

Build focused failing tests first for money admission/settlement, concurrent reservations, missing/stale/ambiguous quotes, long-context and output charges, Exa/embedding inclusion, unknown usage, local refusals and unchanged legacy runs. Use deterministic quote fixtures and fake providers; never assert zero cost for unknown models.

Credential checks cover cross-user/workspace/run denial, expired/revoked/claimed handles, replay, worker-only redemption, no `.env`/DB/log/artifact leakage, process concurrency and cleanup on failure/cancel/pause/restart. Verify UI import boundaries and normal Supabase Auth/RLS. Test that every visible run control changes the corresponding worker behavior, with unsupported/blocked controls disabled.

Evaluate country summaries against their source artifacts and reject mismatched/unlabelled winner claims. Exercise the full UI with the local synthetic login, masked test keys and fake adapters, with no paid requests. Inspect desktop/mobile layouts, keyboard focus, empty/error/loading states, budget preview, real method controls, run coverage and review. Run one integrated full suite after the changes, preserve Ewen/PR6 ancestry and historical artifacts, and update PR13 without merging. Repeating live proof or enabling a research worker requires a concrete bounded validation request.

## Builder discretion and constraints

Builder may choose small module boundaries, component layout, spacing, labels, pure parsers, defensive message framing and exact internal caps, provided these contracts and source/credential/cost boundaries hold. No new framework, paid subscription, remote deployment, global Codex setting, global role-model/effort change, source grant or historical rewrite. Local SQL migrations, if required for frozen new-report provenance, belong to the coordinator and must pass RLS/evidence tests.

Next step: independent read-only builder check, then user review of this design. Product implementation has not started.
