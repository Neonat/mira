# Single-agent arm: design

Status: design for PRD v2 §11, "Agent design value", arm (b). Companion to [PRD v2](mira_PRD_v2.md) §5 and §11 and to the comparison harness in `eval/compare.py`.

## 1. The question

PRD v2 §11 asks whether the multi-agent system earns its cost. The test is a comparison of the same briefs through three arms, and the rule is: **multi-agent must beat the single agent on coverage or precision to justify its cost.** For that rule to mean anything, arm (b) must be a real single-agent system built from the same parts, differing only where "single agent" says it should. Otherwise any difference measures the implementation, not the architecture.

## 2. What is held constant

Everything except the architecture is shared with the multi-agent arm:

- the same allow-list, the same saved passages and the same `fetch_allowed` path (§5.3);
- the same scout tool and fetch budget (`max_fetched_documents`, `max_llm_tokens`, `max_run_minutes`);
- the same analyst prompt rules and the same quote rules (the analyst module's `analyse`);
- the same deterministic quote check (`quote_match`) and the same report renderer (`render_html`);
- the same models per role, and the same cost accounting (`estimated_cost`).

Holding these fixed is the point. The arms may not differ in data, tools, budget or rendering.

## 3. What the single agent changes

The multi-agent system has seven roles: planner, scouts, analyst, verifier, completeness checker, writer and the code orchestrator. The single agent keeps the code orchestrator and the tools, and collapses the model roles as follows.

| Role | Multi-agent | Single agent |
|---|---|---|
| Planner | a model writes the task plan | **none**: one scout task covers the brief's jurisdictions and expected sources, built by code |
| Scouts | one per jurisdiction, parallel, plus an industry scout | **one** scout, all sources, sequential |
| Analyst | separate analyst call per run | the same analyst call, unchanged |
| Verifier | separate model call in a fresh context, plus inference check | **deterministic checks only**: `quote_match` for facts; an inference is kept only if every fact it rests on is verified |
| Gap rounds | re-plan and re-scout missing sources | **none**: one pass |
| Completeness checker | code, after scouting | the same code check, unchanged |
| Writer | separate writer call | the same writer call, unchanged |

The verifier change is the substantive one. The multi-agent arm asks a second model, in a fresh context, whether the passage supports the claim (§6.3 step 3). The single agent does not. It relies on the verbatim quote check alone, so a claim that quotes real text but overstates it is **not** caught. That is the known limit the test `test_claim_that_quotes_real_text_but_overstates_it_is_a_known_limit` already records, and it is the main place precision can differ between arms.

## 4. Guardrails the single agent keeps

Some guardrails are part of the product, not of the architecture, and the single agent keeps them:

- a claim with no quote that appears in its saved passage is `unsupported` and never reaches the report (deterministic);
- an inference reaches the report only when every fact it rests on is verified (§6.3);
- the writer sees verified claims only, and every non-structural sentence cites a verified claim (AG10);
- final report text is assembled from complete saved claim content; the writer controls selection and order but cannot add prose or new inferences. This deterministic guard is shared by both arms and adds no verifier model call to the single-agent arm;
- source text is quoted as data, never as instructions (AG14);
- a fetch is refused for any URL off the allow-list (AG04).

What the single agent gives up is an independent check of *meaning*. That is a deliberate, measurable cost, and the comparison exists to measure it.

## 5. Interface

The single-agent arm is a run of the existing `Orchestrator` with:

- a planner that returns one fixed task, built by code from the brief (no model call);
- one scout registered for both roles;
- a verifier that implements `check_fact` with the quote check only, and `check_inference` with the "every fact verified" rule.

Because the orchestrator is unchanged, the single-agent arm exercises the same state machine, budgets, step records and report path as the multi-agent arm. The only code that changes is the planner and the verifier.

`agent_steps.role` is restricted to the existing `AgentRole` values. The single agent therefore records its scout and verifier steps under the existing roles, so its steps stay comparable in the database. It does not add a role.

## 6. Metrics

Each arm reports, over the same briefs:

- **Coverage**: the share of ground-truth items whose canonical URL is cited (`eval/score_recall.py`).
- **Precision**: the share of sampled report claims a human marks as supported by their cited passage. Computed only from labelled rows (section 7).
- **Cost**: model tokens and the estimated price per run, from `agent_steps` and `estimated_cost`.
- **Time**: wall-clock seconds per run.

The decision rule is the PRD's and is applied by `eval/compare.py` only to live, measured arms.

## 7. Precision

Precision needs a human. The harness does not estimate it. It does three things:

1. **Samples** claims deterministically (a fixed seed over the report's claim list), so two reviewers and two runs draw the same sample.
2. **Writes a worksheet** with each claim, its cited passage and its quote, with a blank label column.
3. **Scores** only rows with a label of `supported`, `partially_supported`, `unsupported` or `contradicted`. A blank label is not counted as supported, and a sample with unlabelled rows reports precision as incomplete.

## 8. What the comparison can and cannot show

- It can show whether the multi-agent arm finds more of the ground truth than one agent, and whether its claims are better supported. Both are measurable on the same briefs.
- It cannot show that the ground truth is complete. The 24-item list (`docs/mira_m0_ground_truth.md`) is a sample of real developments and needs human review.
- It cannot show a result from scripted models. The harness refuses a verdict unless both LLM arms are live (`eval/compare.py`).
- A small base is noisy. Twelve months of briefs from two jurisdictions is about two dozen items, so a difference of one or two items is within noise and must be reported as such.

## 9. Open decisions

- **D6, the verifier model.** The PRD leaves open whether the multi-agent verifier uses the same model as the analyst or a different one. The single agent has no verifier model, so D6 changes only the multi-agent arm.
- **The fixed task.** The single agent scouts every allow-listed source for the brief's jurisdictions in one task. A reviewer may prefer one task per jurisdiction. That would make the single agent closer to the multi-agent arm and should be a deliberate choice, recorded here.
