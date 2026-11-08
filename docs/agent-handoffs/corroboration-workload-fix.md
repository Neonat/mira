# Bounded corroboration workload fix

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
