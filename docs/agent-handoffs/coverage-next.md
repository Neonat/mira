# Completed diagnostic assignment: one SFC enforcement miss

**Status:** completed; see [coverage-trace.md](coverage-trace.md). Retain this original brief as provenance, and do not repeat it. The next task is the bounded candidate/selection telemetry described in the result.

**Agent:** `coverage_engineer` — `gpt-6.1-terra`, medium. Fresh context, no inherited chat.

**Base:** coordinator supplies the pushed checkpoint SHA from `git rev-parse HEAD`.

**Objective:** trace one observed publication miss to its earliest evidenced failure stage. Deliver a diagnosis and a single proposed regression before changing retrieval policy.

**Starting evidence:** in the final 30-document run `2f98eaa5-e13c-4cd9-9a6e-66afaf115dd0`, GT20 (SFC Victory Securities enforcement publication, reference `26PR113`) was not saved or cited. The fetch log instead includes SFC news content `26PR117`. The cause is not established: do not assume the connector failed or that changing ranking will fix it.

**Read-only inputs:** `mira/agents/scout.py`, `mira/sfc.py`, `mira/seed.py`, `mira/agents/planner.py`, `mira/orchestrator.py`, `eval/score_recall.py`, `eval/m0_ground_truth.csv`, `tests/test_research_coverage.py`. Use `checkpoint.json` and, when available locally, the final run's `reports/<run-id>/coverage-comparison.json` and `validation-config.json`.

**Owned output:** `docs/agent-handoffs/coverage-trace.md` only. Runtime code, tests, schema, PRD, source permissions and the benchmark are read-only for this diagnostic. Benchmark identifiers are evaluation evidence, never runtime search instructions or hardcoded retrieval targets.

**Steps:**

1. Confirm the publication alias mapping and reporting scope in the evaluation code.
2. Trace discovery, candidate presentation/selection, fetching, extraction, scout inclusion, analysis, verification and report inclusion using retained evidence. Mark unavailable stages explicitly; a saved index hash does not prove which links the model saw.
3. Use existing focused test fixtures if they can reproduce the demonstrated failure. No new live model runs or network research; do not rerun the whole suite.
4. Name one exact next test and owned implementation file if the evidence establishes a cause. Otherwise specify the minimal candidate/selection telemetry needed to establish it. Do not implement a speculative fix.

**Done:** a concise file/line-backed trace, known versus unknown stages, commands/results, and one concrete next task. Return the repository handover template and stop. Suggested initial time box: five minutes; if local run evidence is unavailable, record that limitation instead of regenerating it.
