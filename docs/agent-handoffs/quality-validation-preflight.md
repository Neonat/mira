# Offline quality-validation preflight

Objective: prepare a bounded, reviewable validation proposal and offline comparison without spending a new live allowance.
Base SHA: `6e30570`, branch `codex/durable-evidence-recovery`.
Owned: `eval/quality_preflight.py`, `eval/test_quality_preflight.py`, this handoff. Runtime, PRD, permissions, historic evidence and other workers' files are read-only. No commit/push, database access, provider/search/browser call or model setting change.

## Interface and frozen scope

Use `/Users/natsim/Documents/dbsearch/.venv/bin/python` below. Importing the module does nothing beyond defining offline functions/constants. The CLI has only local JSON preflight/comparison/worksheet commands; it cannot launch a run. It does not load `.env` or accept credentials. Exceptions printed by the CLI contain no input values.

The authoritative retained baseline is `eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.json`: HK AML/CFT, period **2025-11-04 through 2026-11-04**, as of **2026-11-04**. The initial worker assignment's October dates were corrected by the coordinator after checking this artifact. Mixed scopes are rejected, never relabelled.

Create `current-settings.json` from a read-only settings/source export, with this structure. Supply the **complete actual** boolean feature flag mapping and source rows, not guessed defaults. The following abbreviated source/flag mapping illustrates the interface, not an assertion about the installed configuration:

```json
{
  "scope": {"topic": "AML/CFT", "jurisdictions": ["HK"], "period_start": "2025-11-04", "period_end": "2026-11-04", "as_of_date": "2026-11-04"},
  "models": {"planner": "openai:gpt-5.4", "regulatory_scout": "openai:gpt-5.4-mini", "industry_scout": "openai:gpt-5.4-mini", "analyst": "openai:gpt-5.4", "verifier": "openai:gpt-5.4", "writer": "openai:gpt-5.4-mini"},
  "sources": [{"source_key": "mas", "is_active": false}],
  "feature_flags": {"hybrid": false, "original_storage": false},
  "budget": {"max_fetched_documents": 30, "max_llm_tokens": 600000, "max_run_minutes": 25, "max_exa_searches": 6}
}
```

Copy this complete export to `planned.json`, set only the proposed budget (positive and at/below caps), then:

```sh
/Users/natsim/Documents/dbsearch/.venv/bin/python eval/quality_preflight.py preflight --planned planned.json --current-settings current-settings.json > proposal.json
```

The proposal explicitly says `authorized: false`, one execution, no continuation. Models must match the baseline, MAS must be explicitly inactive, and sources/flags must match the supplied current mapping exactly. This is a consistency check of supplied mappings, not independent inspection of runtime settings. New flags are never enabled automatically. No benchmark file/items enter the proposal or runtime inputs.

## Retained results and comparison

For a new terminal result export, supply this JSON shape (controlled example only):

```json
{
  "kind": "controlled_fixture", "run_id": "fixture",
  "scope": {"topic": "AML/CFT", "jurisdictions": ["HK"], "period_start": "2025-11-04", "period_end": "2026-11-04", "as_of_date": "2026-11-04"},
  "status": "partial", "outcome_status": "partial",
  "started_at": "2026-11-08T00:00:00+00:00", "finished_at": "2026-11-08T00:01:00+00:00",
  "budget": {"max_fetched_documents": 30, "max_llm_tokens": 600000, "max_run_minutes": 25, "max_exa_searches": 6},
  "models": {"planner": "openai:gpt-5.4", "regulatory_scout": "openai:gpt-5.4-mini", "industry_scout": "openai:gpt-5.4-mini", "analyst": "openai:gpt-5.4", "verifier": "openai:gpt-5.4", "writer": "openai:gpt-5.4-mini"},
  "usage": {"documents": 1, "actual_tokens": 20, "reserved_tokens": 10, "exa_searches": 0},
  "mas": {"active": false, "fetches": 0, "versions": 0},
  "acquired_urls": [], "cited_urls": [],
  "passages": [{"id": "p1", "status": "analysed"}, {"id": "p2", "status": "failed"}, {"id": "p3", "status": "deferred"}],
  "findings": [{"id": "f1", "primary_verification": "supported", "corroboration": "primary_source_only"}]
}
```

Actual new retained exports must use `kind: live_retained`; fixtures cannot be compared with live results. Candidate passage count is the complete unique passage row count, partitioned into analysed/failed/deferred, including never-attempted candidates as deferred. Optional `passage_counts` must exactly match computed counts. Finding rows must include every candidate finding, using `not_checked` where needed. Primary verdicts: supported/partially_supported/unsupported/contradicted/not_checked. Separate corroboration statuses: independent_support/primary_source_only/conflicting/inconclusive/not_checked. Independent support requires nonempty `independence_evidence_refs` identifying retained assessments/evidence; references are **not** independently verified or converted into human quality labels. Optional `corroboration_calls` declares requested/completed/errors/explicitly_reported_timeouts, with consistent sums.

`usage.documents` must count all charged document attempts (including failures/refusals), not only successful acquisitions. Actual tokens include known failed-call usage; reserved tokens represent unknown usage only and are not added again from persisted corroboration reservations. The token cap checks their sum. Timestamps count full elapsed terminal time, including failed/partial outcomes, with one second allowance for terminal persistence. Reserved tokens are not a cost estimate.

```sh
/Users/natsim/Documents/dbsearch/.venv/bin/python eval/quality_preflight.py compare --current retained.json > comparison.json
# Reproduce historical baseline metrics, entirely offline:
/Users/natsim/Documents/dbsearch/.venv/bin/python eval/quality_preflight.py compare --current eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.json > baseline-self-check.json
```

Recall uses existing `score_recall.py` with unchanged canonical publication aliases, truth labels and market/date filters. Acquisition and citation recall, found IDs and missing IDs are separate. Existing portable aggregates are checked against their retained benchmark ID sets and canonical scorer; original URL membership cannot be reverified from aggregates. The historic 7be59cdf remains **6/18 acquired, 5/18 cited**, **12 corroboration requests, 8 completed, 4 errors, zero reported timeouts**, **5 primary_source_only and 7 inconclusive**. Its passage and primary-verification dispositions remain unavailable (`null` plus missing-measurement notes). It recorded 478,544 known tokens and 90,685 unknown-usage reserved tokens. Its saved-version count is only a historical proxy for charged attempts, not proof of complete attempt accounting. No historic data is backfilled.

Equal declared budgets are described as observational, not causal; differing declared budgets are labelled a capacity test. The tool does not certify completeness/authenticity of supplied exports, independence, settings provenance, clean execution, precision or quality improvement. New exports should retain all original events, frozen settings and source approvals alongside this comparison. No exporter or live executor is added.

## Blinded human precision

Supply `claims.json` as an array of objects with only claim/cited_passage/supporting_quote text (extra checker/model/status fields are ignored, never exported):

```sh
/Users/natsim/Documents/dbsearch/.venv/bin/python eval/quality_preflight.py worksheet --claims claims.json --output blind-new.csv
```

This reuses `precision.py` fixed-seed sampling of up to 30 rows, opaque sample IDs and one `blind` arm; no model, checker, run, or assessment status appears. Worksheet labels start blank. Existing output paths are refused, preserving all older human labels. Keep the original export securely for the coordinator's sample-ID mapping; order determines opaque IDs. Do not put model statuses into the three selected text fields. After manual labelling, use existing `precision.score(path, 'blind')`; incomplete/empty worksheets return no numeric precision. Model statuses never fill human labels or certify quality.

## Verification and next step

Scoped command: `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest eval/test_quality_preflight.py -q`.

Tests cover scope mismatch, changed flags/models, MAS activation, terminal outcomes, forged passage/recall counts, document/token/time overrun, unsubstantiated independence status, unchanged 6/18 and 5/18 baseline, blinded blank worksheet and overwrite refusal, import without runtime/provider modules, and credential-shaped input rejection. Controlled fixtures are not live proof.

Exact next step: coordinator exports current settings without credentials and produces/reviews `proposal.json`; obtain **fresh user approval for one uninterrupted HK validation**, no continuation/replacement, ≤30 charged document attempts, ≤600,000 actual-plus-unknown-reserved tokens, ≤25 minutes and ≤6 Exa searches, unchanged role models/source grants/feature flags, MAS inactive. Only after approval may the coordinator execute the existing runner and retain terminal raw evidence plus disposition export for these offline commands. Previous live allowances are consumed; this handoff authorizes none.

Status: complete for offline readiness; live-quality gain and human precision remain unmeasured.

## Read-only database exporter follow-up

Additional ownership: new `eval/quality_export.py`, `eval/test_quality_export.py` and this appended handoff. Coordinator explicitly reassigned the narrow `quality_preflight.py`/test change to preserve `report_exists`: absent reports now produce `cited: null` and no citation delta, rather than zero recall. Existing exports without that field retain their previous behavior.

Public interface:

```python
from eval.quality_export import export_retained

# conn is an already-open trusted psycopg dict-row connection, outside a transaction.
# telemetry is parsed local retained JSON. No connection configuration is read here.
retained = export_retained(conn, run_id, telemetry=telemetry)
# Write retained using json.dumps; then run the existing offline compare/worksheet CLI.
```

The function opens a repeatable-read **read-only** transaction and uses SELECTs plus the existing `run_live.load_records` helper's transaction-local actor claims. It never creates/updates a run or calls `load_run` (which can write a revision and read environment defaults). There is deliberately no connection/credential CLI: a coordinator-owned adapter must supply the existing connection. No runner/provider/search execution or environment access is added.

Exact retained telemetry contract:

```json
{
  "run_id": "ACTUAL-RUN-UUID",
  "outcome_status": "partial",
  "max_exa_searches": 6,
  "corroboration_document_attempts": 0,
  "corroboration_mas_fetches": 0,
  "events": [
    {"kind": "run_started", "run_id": "ACTUAL-RUN-UUID"},
    {"kind": "model_started", "run_id": "ACTUAL-RUN-UUID", "id": "request-1", "step_id": "ACTUAL-STEP-UUID", "model": "openai:gpt-5.4", "prompt_version": "analyst/retained-version"},
    {"kind": "model_completed", "run_id": "ACTUAL-RUN-UUID", "id": "request-1", "tokens_in": 10, "tokens_out": 2},
    {"kind": "run_finished", "run_id": "ACTUAL-RUN-UUID"}
  ]
}
```

Every event must have the matching run ID. One `run_started` must be first, one `run_finished` last, with no `run_resumed`. Every model/embedding start needs a unique `id` and persisted `step_id`, and exactly one terminal event with the same ID/channel. Every model start also needs `model`; corroboration starts must retain a `prompt_version` beginning `corroboration/`. `model_completed`/`embedding_completed` require integer nonnegative `tokens_in`/`tokens_out`. `model_error`/`embedding_error` require boolean `usage_known` and integer `charged_or_reserved`: known errors count as actual usage, unknown errors as reservations. Optional `error_code` identifies only explicitly reported timeout codes. Exa requests are counted from distinct `exa_requested` event IDs, never inferred from search results or model requests. Keep error messages/credentials out of this input.

`corroboration_document_attempts` must equal the sum of **all** persisted assessment `document_attempts`, including superseded assessments, because each was charged against the shared document budget. It can be omitted only when that sum is zero. When the sum is nonzero, `corroboration_mas_fetches` is required from the retained machine journal and must be zero for acceptance; unavailable proof causes refusal. Detailed targeted per-URL logs are not currently persisted in these assessment rows: the export explicitly records `corroboration_per_url_logs_available: false`. This does not invent a per-URL acquisition trace. Latest assessment **status** remains separate from the all-assessment budget counter.

Per-step model known usage must exactly match `agent_steps.tokens_in + tokens_out`; per-step unknown reservation must exactly match `output_refs.reserved_tokens`. Embedding events form a separate channel matched to `output_refs.embedding_usage.tokens` and `.reserved_tokens`, preventing double counting. Unknown reservations without persisted accounting (for example a writer error lacking a corresponding DB reservation) are an explicit readiness gap and refuse export. Missing request usage, duplicate/foreign/uncompleted requests, differing totals and mismatched model identities are rejected.

The export requires the frozen November scope, terminal timestamps/status and matching saved outcome, one run/one analysis revision in its disposable workspace, no prior-run linkage, actual inactive MAS source row with zero logged/targeted MAS fetches and zero MAS versions, and an existing coverage policy. It reads configured role IDs **and** actual step/request model IDs. Only exact prefixed/bare equivalents (`openai:gpt-5.4` / `gpt-5.4`) are accepted; differing models are rejected and original actual step strings remain in `actual_step_models`. Unset/old-format/mismatched frozen role settings refuse; the adapter does not repair settings or change configuration. A one-run workspace is required for attribution; it remains the coordinator's responsibility to create it without preloaded publications.

Latest passage events retain passage ID, terminal status, batch/step IDs and sequence and must agree with canonical `private.capture_analysis_coverage`. Candidate/attempted rows remain pending and fail measurement, rather than silently becoming deferred. Latest final report coverage must match the same snapshot. Multiple distinct analysis batches are legitimate; `unique_batch_ids` and one ledger policy/unresumed journal proof replace the historical one-initial-step heuristic. Duplicate batch identities refuse.

The export distinguishes saved versions from **charged requests**: machine scout logs count `request_sent=true` excluding refused/reused, plus the separately reconciled all-assessment targeted counter. MAS checks cover both acquired URLs/source IDs and logged/retained targeted attempts. It uses latest final-report finding IDs plus supporting inference facts through the existing read-only citation helpers; report ID/version, full finding primary/corroboration dispositions, latest bound primary check metadata and latest bound corroboration assessment metadata are retained. Stale/unbound evidence becomes `not_checked`. Supported primary verdicts require the correct final verifier method/model. Independent statuses require retained original-reporting quotations on both primary and candidate sides, with assessment/passage references; these remain model assessments, never human labels or a new independence certification.

Scoped verification command:

```sh
MIRA_TEST_DATABASE_URL="$LOCAL_TEST_DATABASE_URL" /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest eval/test_quality_export.py eval/test_quality_preflight.py -q
```

Use the existing local test connection setting for `LOCAL_TEST_DATABASE_URL`; do not log it. The authorized fixture validation used local PostgreSQL at `127.0.0.1:55432` with new random test workspaces only. **29 checks passed**: no provider/search/browser/model calls, no historical database export, no old manifests or evidence changes. Tests include scope/terminal/foreign/missing usage refusals, reservation and model mismatches, actual typed coverage with two legitimate batches, final report citations, latest primary/corroboration and stale bindings, embedding accounting, targeted all-assessment counters/MAS proof, absent report, charged attempts vs versions and unsubstantiated independent status. These are controlled fixture results, not live-quality proof.

Next bounded step: coordinator reviews the supplied journal contract and config/unknown-reservation readiness gaps, prepares the credential-free settings proposal, and seeks fresh user authorization before one actual bounded HK run. Existing consumed allowances are not renewed by this export work. No shared runtime files, root CLI, old runs, manifests or truth labels were changed. Status: exporter and scoped fixture verification complete; actual live proof and manual labels remain outstanding.

### Final review corrections: report-time binding and request provenance

Independent review identified two exporter blockers, corrected only in the owned exporter/tests and this handoff. **40 scoped checks passed in 2.60 seconds** with the same local PostgreSQL command above; no full suite or live call was run by this worker.

Report citations and precision rows now use `report_binding`, separately from current finding disposition metadata:

- **Reviewed reports:** hydrate only the protected `evidence_bundle` with the existing strict `mira.render.frozen_context` validator. This performs no rendering or model call. Citations, dependency facts, claim text, reviewer amendments, passage text and quotations come from frozen context. Current mutable findings are used only for separately labelled current primary/corroboration dispositions. Frozen reviewed metadata must match the report row.
- **Draft reports:** every cited root and recursive dependency must have a latest native `claim_checks` row **at or before `reports.generated_at`**, with supported verdict, appropriate final method/model, valid stored fingerprint and complete `input_snapshot` equal to the current native recursive evidence capture. Missing, conflicting, unbound or changed input refuses export. The comparison does not skip an invalid latest as-of check to find a convenient older one. A check created after report generation cannot repair the old report's binding. `report_binding` retains the actual report generation timestamp and check IDs, check timestamps and fingerprints used for this proof. Uncited stale findings may still be `not_checked`; cited report recall/precision cannot silently use their changed inputs.

New PostgreSQL regressions mutate a finding, evidence quotation or dependency after draft generation, create fresh verification, and confirm the old report still refuses. A report with verification only after generation also refuses. A reviewed report's claim text/quotation/citation metrics remain frozen after current finding/evidence mutations and fresh checks. Fresh, correctly bound draft exports still pass.

Request prompt provenance is now stricter than the original telemetry example above: every model request's `prompt_version` must be nonempty and **exactly match its persisted `agent_steps.prompt_version`**. A corroboration call requires both persisted verifier purpose `corroboration` and one explicitly supported retained prompt (`corroboration/3-single-candidate`, or the existing bounded legacy `corroboration/2-bounded-excerpts`). Matching is enforced in both directions; a normal verifier cannot become corroboration through a journal prefix. Current scout request prompts additionally use the explicit allowlist `scout/6`, matching the current scout module's selection/report prompt. No generic prefix grants scout eligibility. Other role prompts must exactly equal their persisted step prompt. The telemetry JSON's illustrative analyst prompt must therefore use the real retained step value (currently `analyst/3`), not the placeholder `analyst/retained-version`.

Classification tests reject forged normal-verifier-as-corroboration requests, purpose/prompt disagreement in both directions, forged exact-version strings and an unsupported scout prompt; valid persisted corroboration and scout requests remain accepted. Existing old journals without matching per-step prompt provenance remain an explicit readiness gap rather than reconstructed evidence.

Status: both review blockers corrected and scoped proof complete. Coordinator owns integration, the single final full suite and any separately approved future live validation.
