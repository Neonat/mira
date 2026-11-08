# Live browser adapter handoff

Objective: Add permission-gated live Chromium acquisition with bounded resource and policy checks.
Base SHA: `9fc110b91374128a960431f9a55550caae717b44`.
Owned files: `mira/live_browser.py`, `tests/test_live_browser.py`, this handoff.
Read-only files: `AGENTS.md`, `docs/agent-handoffs/README.md`, `mira/fetch.py`, `mira/browser_capture.py`, `mira/evidence.py`, `mira/store.py`, coordinator design and plan.
Sources/commands: `PYTHONPATH=/private/tmp/mira-browser-deps:$PYTHONPATH /Users/natsim/Documents/dbsearch/.venv/bin/python -m unittest tests.test_live_browser`; test Chrome executable `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
Changes: Added pure `permitted` preflight and `LiveBrowserAcquirer(fetcher).acquire(...)` returning page/provenance. Explicit environment and source approvals gate acquisition. Child Chromium navigates with JavaScript and bounded curator actions, pins public DNS, uses pinned robots transport, routes requests through source/task/rate/method policy, aborts unapproved resources, isolates state and monitors resources. Parent coordinates per-source host locks and process-group deadline; interrupted child quarantines its browser channel only. Navigation response metadata is explicitly labeled initial, with final response unknown. Failed attempts carry `request_sent`; optional denied resources are in `denied_requests`.
Scoped checks and results: 13 adapter tests passed (25.66s); after request-count correction, affected Chromium and timeout checks passed (2 tests, 7.31s). Real Chromium fixtures use test-only route fulfillment, not external network; they cover JS and click, unapproved subresource, robots, redirect and challenge. Process tests cover timeout/cancellation reaping and unrelated source isolation. No paid or external acquisition calls and no full suite.
Open risks: Independent review and integration remain necessary. The observed network-byte threshold uses CDP notifications and can overshoot delivered chunks; it is not a pre-receipt cap. WebRTC prevention relies on Chromium flags and initialization script. Browser requires Playwright on the Python path and a compatible Chromium. No live-source success or evidence completeness is established. Parent must honor `min_browser_delay`, use `denied_requests` for partial extraction, and preserve acquisition provenance.
Exact next step: Coordinator integrates the adapter, performs independent security review and runs the single agreed full integration suite; resolve review findings and perform only explicitly authorized, source-permitted live validation.
Status: complete

## Follow-up: timeout diagnostics and rate-state preservation

Objective: Make the coordinator's single 60-second HKMA timeout diagnosable, omit non-text assets, and preserve learned crawl delays across browser failures. The worker made no external requests.

Owned files: this handoff, `mira/live_browser.py`, `tests/test_live_browser.py`. Read-only context: existing adapter handoff and coordinator's bounded assignment. Base remains `9fc110b91374128a960431f9a55550caae717b44`; work continues in the shared checkout.

Changes: Child emits bounded `MIRA_BROWSER_EVENT` JSON on stderr, containing stages and sanitized host/status/resource metadata, without URL paths, queries, headers or cookies. Parent exposes parsed events as `exception.diagnostics` on child failure/timeout and `progress_events` on success. Images, fonts and media are aborted and reported as `omitted_resources`; scripts, stylesheets and XHR remain subject to policy. Per-host `rate_policy` events preserve observed robots crawl delay on failed captures. Hard child interruption or abnormal exit marks only target hosts `browser_policy_unknown`; future browser preflight refuses those hosts. Coordinator owns enforcing the same unknown-policy flag in ordinary HTTP and the corroboration broker.

Scoped checks and results: `PYTHONPATH=/private/tmp/mira-browser-deps:$PYTHONPATH /Users/natsim/Documents/dbsearch/.venv/bin/python -m unittest tests.test_live_browser` passed **16 tests** in 35.355 seconds. After strengthening the assertion to require the actual pending XHR/fetch event, that Chromium hard-timeout fixture passed again in 9.083 seconds. Tests used route-fulfilled fixtures and made no external requests. The previous HKMA timeout's cause is unknown; this change does not claim to diagnose it retrospectively.

Open risks: CDP byte monitoring can overshoot; WebRTC protection and the adapter changes require independent review. A killed child marks policy unknown even when partial progress exists, deliberately failing closed. Dependency and executable requirements remain as above.

Exact next step: Coordinator reviews this diff, integrates unknown-state propagation into Fetcher/broker, then decides whether to use the one explicitly bounded, permitted live validation. No worker live request was made.

Status: complete.

Coordinator integration: source0f9526d, fullsuite487passed+8subtests none skipped50.63s, independent re-review no blockers. Actual permitted HKMA navigation succeeded24.91s; initialunknown-stage timeout preserved. MASdisabled; no paid/modelcalls. Full handoff live-browser-integration.md and portable hkma-live-browser-validation.json supersede the earlier integration-pending status.
