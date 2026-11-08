# Claim-level corroboration module

Objective: Task 3, saved-first independent claim corroboration after Phase-1 exit.
Base SHA: `83c84c19f38fea9fe8ad8ba31fcd13d31d14675d`.
Owned files: `mira/corroboration.py`, `tests/test_corroboration.py`, this handover.
Read-only: AGENTS.md, handoff README, approved ingestion/corroboration spec and plan, PRD §6, contracts, store, budget, llm and verifier. Shared persistence/orchestration/render/migrations remain coordinator-owned.

## Changes and interfaces

- `CorroborationService(assessor=None, discovery=None, clock=monotonic, now=UTC_now).assess(ctx=..., claim=..., base_evidence_input=dict, saved_candidates=..., sources=..., budget=shared_tracker, authoritative_primary=False, limits=SearchLimits())` returns frozen Pydantic `CorroborationAssessment`; serialize with `model_dump(mode="json")`.
- Base evidence remains acyclic and exact; assessment records its snapshot/fingerprint, exact primary/candidate passages, explicit `primary_origins` metadata, proposition, decisions, outcomes/reasons, checked date and usage/stop reasons. Primary passages retain identical acquisition provenance. Coordinator enriches verification input AFTER assessment and binds DB server sequence outside this module.
- `CandidateEvidence(passage=FrozenPassage, workspace_id=UUID, eligible=True, current=True, publication_id=None, organization_id=None, origin_id=None)`. Trusted acquisition/store supplies eligibility; service filters workspace, current flag, approved fetch/store_text sources, jurisdiction and as-of date again. Persistence must independently recheck current eligible saved rows before insert/sign-off.
- `LlmAssessor(client)` uses exactly one `structured_bounded` call on existing verifier role, short passage labels, no retries, conservative UTF-8 input/schema allowance plus envelope and bounded output. Unknown failed-call usage reserves tokens separately (`reserved_tokens`) from reported `tokens_in`/`tokens_out`; module charges shared budget once. Coordinator step ledger must not charge it again.
- Optional `discover(query, *, ctx, source_ids, max_documents, max_passages, timeout_seconds) -> DiscoveryBatch(candidates=[],document_attempts=0,tokens_in=0,tokens_out=0,errors=[])`. `DiscoveryFailure` carries same attempt/token accounting. All results must be saved publisher evidence, not provider snippets. Adapter must honor granted bounds and account completed/failed attempts. No adapter means saved-only; no live calls occurred.
- Default per-claim caps: 2 queries, 5 documents (saved candidates plus acquisition attempts), 20 passages and 30 seconds, further constrained by shared run budget. Failed attempts count; late assessment cannot establish support. Captured contradictions take precedence; authoritative primary-only remains informational.
- Unknown origins never establish independence. Exact original-reporting quotes on primary and candidate sides are required; same document/source/organization/publication, identical text/capture hash, shared origin or explicit derivation remains dependent. Composite extraction content hash is not treated as original capture identity.
- `validate_frozen_assessment(result)` validates only the frozen bundle: base identity/fingerprint, primary citations, exact quotes, proposition scope/dimensions, origin requirements, eligibility and recomputed status. It rejects inconsistent results without live reads. Semantic interpretation itself remains the verifier assessor's responsibility; validators do not pretend to derive semantics from hashes.

## Tests and results

Command: `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_corroboration.py -q`.
Initial red: missing module collection failure. Subsequent targeted red cases exposed out-of-scope discovery sources, forged eligibility, missing-value contradiction and invalid mismatch snapshot; corrected before green. Final scoped result: **43 passed**. No full-suite run, live/API calls, commit or push by this worker.

Coverage includes all five outcomes; exact quotes/unknown origins; mismatched entity/jurisdiction/date/quantity/status/scope; conflict precedence; mirrors/publication aliases/shared announcements/syndication/capture hashes; stale/workspace/source/date boundaries; shared run limits, claim caps, failed acquisition/semantic accounting, late output; short labels; frozen tampering.

Ruling: current implementation checks all factual claims supplied by the orchestrator; inference claims return not_checked. This is a conservative implementation default, not an adopted enterprise sign-off policy. Default semantic assessment requires explicit `LlmAssessor`; absent assessor produces inconclusive or identified authoritative primary-only, never invented independence.

Open risks: live semantic precision and recall are unmeasured; explicit origin judgments depend on verifier semantics plus exact evidence validation. Source-origin metadata is trusted coordinator-supplied provenance and must be frozen/server-protected. The acquisition adapter and shared bounded client own actual network/process deadlines; service also rejects late output. Unknown usage reservations are intentionally conservative, not measured token usage. Source eligibility must be SQL-filtered before candidate limits and revalidated at persistence/sign-off.

Exact next step: coordinator wire saved candidates, optional bounded acquisition, persistence/frozen reviewer inputs; focused independent review, then single integrated offline/local-Postgres suite. Status: module complete, integration/review pending.

## Focused review corrections

Two P1 findings reproduced with six failing regression cases, then corrected in this module only:

- Canonical source `organization_id`/`origin_id` now precedes supplied candidate defaults. Dependency checks independently consult the frozen canonical metadata for both sources, so changing a candidate's supplied IDs cannot erase a known common organization/origin during frozen validation.
- Every accepted candidate requires a validated decision; omitted, rejected or semantically uncertain candidates record `incomplete_assessment` and prevent independent-support status. Validated conflicts retain precedence even when other candidates remain unresolved. Frozen validation recomputes coverage from candidate/decision IDs and rejects forged clean positive status or missing incomplete stop reasons.

Policy clarification: authoritative claims with unassessed candidate evidence are **inconclusive**, because that evidence may conflict. Authoritative primary-source-only remains informational when no candidate is pending, or all candidates were resolved without independent support/conflict. Neither outcome labels the primary statement false.

Scoped command unchanged; final result after review fixes: **49 passed**. Writes stopped for coordinator integration. No live calls, commits or other-role file edits.
