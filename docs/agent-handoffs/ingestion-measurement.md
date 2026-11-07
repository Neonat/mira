# Ingestion measurement

Objective: trace retained publication stages and measure the generic candidate-retention effect offline, without benchmark input to retrieval.

Base SHA: `392f61740556d0c942f4be53f05fd9b980cfc9b9`.

Owned files: `eval/test_ingestion_effects.py` (new), this handoff. Read-only: runtime code, contracts, source permissions, PRD, benchmark truth labels, historical reports and other workers' files. No commit, network/model/API call, database mutation or historical report edit.

## Retained evidence

Source: ignored `/Users/natsim/Documents/dbsearch/reports/e2fda30f-36f9-4aa3-83c3-d78b81671b83/{telemetry-audit,validation-config,validation-result}.json`. Scope is HK, AML/CFT, 2025-11-04 through 2026-11-04, as-of 2026-11-04. Offline scorer uses existing explicit official publication aliases and unchanged truth labels.

| Measure | All | Fetchable | Regulatory |
|---|---|---|---|
| Acquired benchmark publications (retained saved version URLs) | 9/18 | 9/18 | 9/14 |
| Report citation recall | 9/18 | 9/18 | 9/14 |

The independent checklist measure contains 13 rows: 4 `found`, 3 `no_change`, 6 `missing`. These are retained machine statuses, not human labels or publication recall. Human precision remains unlabelled. The two MAS items remain in the scoped benchmark because its labels explicitly include HK; publisher location alone does not override those labels.

Portable stage summary below. Numbers count retained records, not exhaustive provider or billing observations. “Unknown” discovery means no matching successful-scout record; the failed scout has no retained partial telemetry. A zero downstream count cannot prove rejection at that stage.

| Item | Discovery | Saved versions | Analyst passage IDs | Supporting finding IDs | Cited |
|---|---|---:|---:|---:|---|
| GT02 | Unknown | 0 | 0 | 0 | No |
| GT03 | Observed | 1 | 16 | 4 | Yes |
| GT04 | Observed | 1 | 3 | 2 | Yes |
| GT05 | Observed | 1 | 4 | 2 | Yes |
| GT06 | Observed | 1 | 4 | 4 | Yes |
| GT07 | Unknown | 0 | 0 | 0 | No |
| GT08 | Observed | 0 | 0 | 0 | No |
| GT09 | Unknown | 0 | 0 | 0 | No |
| GT11 | Observed | 1 | 3 | 3 | Yes |
| GT16 | Observed | 1 | 3 | 2 | Yes |
| GT17 | Unknown | 0 | 0 | 0 | No |
| GT18 | Unknown | 0 | 0 | 0 | No |
| GT19 | Unknown | 0 | 0 | 0 | No |
| GT20 | Observed | 0 | 0 | 0 | No |
| GT21 | Observed | 1 | 3 | 4 | Yes |
| GT22 | Observed | 1 | 4 | 5 | Yes |
| GT23 | Observed | 0 | 0 | 0 | No |
| GT24 | Observed | 1 | 3 | 4 | Yes |

GT08/GT20/GT23 were presented in gap round 2 at ranks 11/32/21 with one remaining slot, and were not selected. Their earlier initial scout discovered them on its final fetch; the later gap scout had no selection round at zero allowance. This establishes a selection/capacity boundary for these three only. GT02/07/09/17/18/19 cannot be attributed to discovery failure. MAS access blocks and Wolfsberg fetch-only permissions remain known source limitations; permission changes were not attempted.

The historical run saved 32 versions against 30 requested documents; failed-scout usage is incomplete. Its 9/18 versus earlier 7/18 is neither a post-fix gain nor an equal-enforced-budget comparison. Model verifier outcomes printed by the command below are provenance only and cannot establish human precision.

## Offline effect

A generic synthetic fixture supplies 123 dated publication candidates to the actual `_ScoutRun._select_and_fetch` at the real 120-link prompt cap. Both arms have the same 123-document allowance and two-round ceiling. The deterministic selector selects all presented labels. Acquisition is replaced by a local attempt recorder, so these are **selection-frontier attempts**, not saved versions/passages or report citations.

| Explicit policy ablation | Distinct attempts | Allowance left | Selection calls |
|---|---:|---:|---:|
| Discard candidates after selection (legacy counterfactual) | 120 | 3 | 1 |
| Current candidate retention | 123 | 0 | 2 |

The comparator shares current ranking and explicitly clears candidates after a selection; it is not a replay of the historical runtime or HK run. The result isolates retention, with three additional reachable attempts at equal document allowance. It uses extra selection work: token, time, cost and whole-run budgets are not equalized. This is not a live coverage, saving, discovery/browser or report-quality gain. The test imports no benchmark publications into scout inputs. Other runtime additions are outside this measurement's proof.

## Reproduction and checks

From the isolated worktree `/Users/natsim/.codex/worktrees/ingestion-corroboration/dbsearch`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest eval/test_ingestion_effects.py -q -s -p no:cacheprovider --basetemp=/tmp/mira-ingestion-measurement --tb=short
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/natsim/Documents/dbsearch/.venv/bin/python eval/test_ingestion_effects.py --retained-run /Users/natsim/Documents/dbsearch/reports/e2fda30f-36f9-4aa3-83c3-d78b81671b83
```

Scoped result: **2 passed** in 0.18 seconds. Saved evidence CLI independently reproduced the tables and printed per-item presented ranks, allowance, verifier verdict counts, plus any absent eligible trace IDs (none). The measurement test verifies scope filtering, explicit landing/PDF aliases, acquisition/citation separation, checklist separation and unknown discovery with synthetic evidence. No full suite run. An initial fixture check failed on the required `plan_requires_approval` field; corrected before the passing check. System Python lacked project dependencies, so all scored/tested commands use the assigned main `.venv`.

Changes: added the offline trace summarizer/CLI and equal-document-allowance retention ablation; preserved existing scorer/truth labels and all runtime files.

Open risks: no post-fix live recall, human precision, complete billing, original captures, or browser/discovery adapter effect measured. Ignored report files may be absent elsewhere; the portable table above remains usable. The selection fixture uses a private runtime hook and stub acquisition; actual save/passages/verification/frozen-render acceptance needs coverage/coordinator integration tests.

Exact next step: coordinator runs the integration acceptance checks after coverage interfaces land and includes this measurement in its single full suite. Keep any additional live validation behind a new explicit bounded authorization.

Status: complete for assigned retained trace and generic offline measurement; runtime integration and live gains remain unmeasured.
