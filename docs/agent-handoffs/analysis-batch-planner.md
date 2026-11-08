# Analysis batch planner handoff

Objective: Implement pure bounded whole-passage planning and claim label namespacing for coordinator integration.

Base SHA: `e4ad439f77bae4ad8d41097251011d3bfaeeeb7c`.

Owned files: `mira/analysis_batches.py`, `tests/test_analysis_batches.py`, this handoff. Read-only: `AGENTS.md`, `docs/agent-handoffs/README.md`, evidence-completeness spec and plan, `mira/store.py`, `mira/contracts.py`.

Sources/commands: Assignment and Task 1 of `docs/superpowers/plans/2026-11-08-evidence-completeness.md`; `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_analysis_batches.py -q -p no:cacheprovider`.

Changes: Frozen validated limits, optional `MIRA_ANALYSIS_*` environment configuration, ordered whole-passage batches with explicit oversized and capacity deferrals, conflicting identity rejection, and sequential claim-label remapping with resolved intra-batch dependencies. The planner stops filling batches once the batch limit prevents the next eligible passage; oversized records retain `input_limit` precedence. Claim drafts are revalidated against existing contracts; evidence and citations are preserved.

Scoped checks and results: Initial red was missing module at collection; a second red demonstrated backfilling after batch overflow. Final scoped run: 6 passed in 0.08s. No full suite, provider calls, or paid runs.

Open risks: Pure planner is not integrated; eligibility, durable ledger, run allowances, and actual model execution remain coordinator responsibilities. Global labels remain subject to existing contract's four-digit limit.

Exact next step: Coordinator reviews this diff and integrates the planner with eligible passage selection, budget accounting, persistence, and per-batch claim handling.

Status: complete.
