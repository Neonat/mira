# Bounded corroboration workload fix

**Latest:** the thirty-second v2 clean run had six timeouts and zero completed corroboration calls. The coordinator subsequently approved the offline v3 single-candidate/sixty-second change described at the end of this handoff. Its 71 focused tests pass; live completion remains unvalidated and the authorized clean run is exhausted. Earlier sections retain the evidence trail.

Objective: reduce actual semantic workload under the existing 30-second claim deadline, preserving original evidence, contradictions and conservative accounting.

Base SHA: `c5542ebbe00b3c39f4d6f5a4c5e75e9a8b9daec3`.

Owned files: `mira/corroboration.py`, `tests/test_corroboration_workload.py`, this handoff. Existing `tests/test_corroboration.py` was read/tested, unchanged. Read-only: AGENTS, handoff README, PRD §5.3/§6 D7, contracts/store/budget/LLM interfaces, [latest run evidence](../../eval/evidence/2026-11-08-hk-exa-run-fe65444d.md). Other workers' edits were preserved.

## Evidence and changes

The previous assessor serialized up to twenty full candidates plus full primaries and allowed 8,192 output tokens. The latest run records five timed-out calls and 270,717 reserved tokens (reservations are not measured consumption).

The assessor now makes one small verifier call per supplied assessment batch: at most two candidates, two primaries and exact contiguous 1,800-character windows. Primary windows anchor the cited quote; generic lexical matching selects candidate windows without preferring matching quantities or benchmark identifiers. The prompt includes original offsets/lengths and omitted counts. Metadata fields are bounded; the factual claim is retained whole or refused above 5,000 serialized characters. Output allowance is 4,096 tokens; preprocessing time is deducted from the unchanged deadline. Model, effort and source permissions are unchanged.

Original full passages remain in the immutable service result. Omitted candidates remain without fabricated decisions. All truncated-context decisions become uncertain, including apparent contradictions: omitted qualifications may change the temporal or material scope. Potential-conflict quotes, propositions and full originals remain retained with an explicit reason. Fully shown validated conflicts survive. Known-dependent candidates still receive relation/contradiction assessment, with instructions to omit unnecessary independence reasoning. Quotes must occur in shown text and subsequently pass existing original-evidence/proposition/origin checks. One invalid decision no longer discards another fully shown valid contradiction. `assessment_workload_limit`, `incomplete_assessment` where applicable, and explanatory reasons expose unassessed evidence. The frozen validator rejects promoting any v2 truncated decision into support, contradiction or irrelevance, even if stop reasons are removed. Legacy prompt versions retain existing validation.

Synthetic offline measurement: twenty originals totaling **528,460 candidate characters** became a **4,679-character user prompt**, two candidates and a 2,314-byte output schema. Conservative input reservation was 12,772 plus 4,096 output allowance = **16,868**. This demonstrates smaller actual requests, not live latency, precision or cost savings. Reported usage and unknown-usage reservation paths remain separate and charge once.

Cited-source verification, publication coverage and independent corroboration remain distinct. This change does not demonstrate better publication coverage or independent support.

## Checks

Red: initial workload tests reproduced twenty full candidates, falsely complete truncated support, and pre-call budget rejection on a very large prompt. Subsequent red tests exposed frozen-status promotion, loss of a valid contradiction beside an invalid quote, and missing explicit workload stop reason. Each passed after its narrow fix. Independent review then identified a contradiction exemption that could validate an apparent conflict despite an omitted qualifying statement. Three red cases reproduced the problem (including candidate-side and primary-side omitted qualifiers); all limited-context relations now become uncertain, and frozen validation rejects attempted conflict promotion. The fully shown contradiction regression remains green.

Final scoped command:

`/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_corroboration_workload.py tests/test_corroboration.py -q -p no:cacheprovider`

Result after review correction: **58 passed in 0.35 seconds**. Scoped `git diff --check` clean. No paid/live calls, commits, pushes, shared contract edits or migrations. Full integration suite belongs to coordinator.

## Risks and next exact task

Live high-reasoning completion within 30 seconds and 4,096 output tokens remains unproven. Excerpts deliberately reduce completeness: unassessed text can contain contradictions or qualifications, so long passages cannot yield a definitive support or contradiction relation. Lexical selection can miss paraphrases. Existing full originals still enlarge downstream verification context if the caller retrieves twenty candidates; coordinator owns the proposed explicit two-passage retrieval/search limit and associated documentation/tests. This worker did not change runtime retrieval.

Next: independently review these three files; coordinator integrates the explicit runtime allowance if desired, runs the full suite once, then executes the single separately authorized clean bounded HK Exa validation with MAS off. Report actual semantic decisions, output/deadline failures and usage separately from coverage. Do not infer live success from these fixtures.

Status: complete for assigned implementation and offline checks; live acceptance pending coordinator.

## Clean-run result and offline follow-up proposal (not implemented)

The subsequent clean run at `43a7b1c1c25003ec63cac8dc27a2aa5ce59ffc10` **did not resolve corroboration timeouts**. Read-only analysis of `/private/tmp/mira-hk-clean-20261108/events.jsonl` found six starts, six hard timeout errors and zero completed corroboration calls. Inputs were 7,711–9,126 characters (mean 8,613.8), output ceilings 4,096, allotted time approximately 29.998 seconds, observed duration 30.012–30.023 seconds. Unknown-usage reservations totalled **139,295**, not measured consumption. These live results supersede any expectation that the smaller workload would fit thirty seconds.

The same journal shows ordinary primary verification completing in 4.059–20.324 seconds, while two inference checks using the same verifier model completed in 32.279 and 33.153 seconds; the former had a 4,122-character input. This demonstrates that some small verifier requests exceed thirty seconds. It does **not** establish a universal minimum or prove sixty seconds sufficient. Source inspection of `mira/llm.py` confirms the bounded subprocess is killed at the outer deadline and receives the unchanged high reasoning setting; it returns usage only after a terminal response. Existing metadata cannot distinguish provider reasoning, first-response/network waiting, schema processing or child startup. There is no evidence of throttling, output-limit termination, or a parsing failure for these six calls.

Recommended concrete next change, **pending coordinator agreement**:

- One candidate per claim/search allowance, selected through the existing eligible-version generic retrieval; at most two primary excerpts and one candidate excerpt, each 1,800 characters. Keep the full claim and immutable originals; retain explicit incompleteness for any truncated/omitted context. This is narrower search coverage and must be documented, not represented as two-source proof.
- One structured call, no retry. A new prompt version and compact root schema `{proposition: Proposition, decision: SingleDecision}`. `SingleDecision` retains candidate proposition, exact quote, relation, origin relation, origin evidence with primary/candidate labels, and reason; code binds its candidate ID because exactly one is supplied. Do not collapse the two propositions into a guessed equality or omit independence evidence. Bound quotation/reason output lengths through the proposal schema, e.g. quote ≤400 characters and reason ≤240, with at most three origin records. Missing exact evidence produces uncertainty.
- Retain the 4,096 output-token ceiling; reducing it further risks exhausting reasoning allowance before structured output. An illustrative independent fixture serializes to 841 JSON characters with this single-decision shape versus 1,542 for two labelled decisions. These are character measurements, not token measurements or a prediction of high-reasoning usage. Excerpt content ceiling drops from 7,200 to 5,400 characters; metadata/schema and the unchanged whole-claim bound still count in reservations.
- Adapt the **total** claim deadline to `min(60 seconds, shared run remaining seconds)` before any preparation or acquisition, subtract every elapsed stage, and pass only the remainder to the subprocess. No second sixty-second window, timeout retry or increase to the shared 25-minute/600,000-token envelope. This is a revised per-claim policy, requiring coordinator-owned runtime/PRD updates; it is not merely a payload fix. `SearchLimits` currently enforces a maximum of thirty and would need explicit widening. Preserve frozen historical thirty-second limits; version-specific validation must retain the v2 excerpt semantics.
- Offline tests before implementation: one-candidate schema/prompt count and reservation; exact label/quote/proposition checks; origin evidence on both sides; retained uncertainty for omitted qualifications; all existing fully shown conflict cases; fake-clock completion at 45 seconds accepted under the agreed sixty-second total; completion after sixty rejected with usage charged; a run with only twelve seconds remaining gets at most twelve; preparation/discovery consume the same deadline; unknown cancellation reserved once; no timeout retry; legacy thirty-second frozen results unchanged. Coordinator should independently test runtime retrieval limit and shared envelope accounting.

No runtime change, deadline change, new test execution, paid call or full-suite run was made for this diagnosis; only this handoff was appended. The one authorized clean run is used. A future live measurement needs new authorization, and an offline implementation must be described as unvalidated live behavior.

Next exact task: coordinator agrees or revises the single-candidate/sixty-second policy and assigns its runtime/PRD integration; then implement the scoped schema/deadline tests and code offline, independently review, and stop without another live call. Status: diagnosis/proposal complete; implementation awaits design agreement.


## Approved offline v3 implementation

Objective/base: implement the coordinator-approved proposal after the failed thirty-second clean run, based on `43a7b1c1c25003ec63cac8dc27a2aa5ce59ffc10`. Owned edits: `mira/corroboration.py`, `tests/test_corroboration_workload.py`, this handoff, and explicitly assigned fixture updates in `tests/test_corroboration.py`. Runtime/PRD and all other files remain coordinator-owned.

Implemented: `corroboration/3-single-candidate` selects one candidate and binds its passage ID in code. Its single-decision proposal retains both propositions and exact origin records; quote/reason strings are bounded to 400/240 characters and origin records to three. Output ceiling remains 4,096 tokens. The runtime imports the shared one-candidate constant; runtime policy/integration is coordinator-owned.

`SearchLimits.max_seconds` now defaults to and caps at sixty. The service clock starts before base-evidence preparation; the model receives only the lesser of the claim allowance and shared remaining time, less elapsed preparation/acquisition. One assessor attempt is allowed per claim, with no retry or discovery after that attempt. Optional discovery before an assessment still consumes the same deadline. Reported usage and unknown reservations charge once; late results cannot contribute decisions. Shared run limits/model/effort/source permissions are unchanged.

All truncated relations remain uncertain, with potential-conflict evidence retained. The frozen guard explicitly recognizes **both v2 and v3**, so changing the prompt version cannot bypass v2 truncation checks. Original v1/v2 thirty-second snapshots retain their own stored limits. No historical records or applied migrations were modified.

Red/green: fake-clock tests initially exposed the old thirty-second ceiling and three possible assessor calls after an early failure. Payload/schema tests exposed the two-candidate/list output. The approved implementation resolves those failures. Existing client fixtures now emit the single-decision schema; the historical 31-second late-response test explicitly requests its original thirty-second limit, without changing its assertions. Additional tests cover a fully shown conflict with an unknown origin label, primary/candidate omitted qualifiers, v2 promotion rejection, single-candidate identity, whole-claim preparation, acquisition, and shared twelve-second remaining time.

Final command: `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_corroboration_workload.py tests/test_corroboration.py -q -p no:cacheprovider` → **71 passed in 0.31 seconds**. Scoped `git diff --check` clean. No full suite, paid/live calls, commits or pushes.

Risk: sixty seconds and the compact single-candidate request may still fail under high reasoning. The change is offline validated only; it also narrows candidate coverage, and long/excerpted evidence remains inconclusive by design. There is no new precision, latency or publication-coverage claim.

Exact next task: independent review of the four owned files, coordinator runtime/PRD integration and scoped integration checks. Stop without further live calls: another live acceptance measurement needs new user authorization. Status: assigned offline implementation complete; live acceptance unvalidated.
