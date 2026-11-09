# Generation reliability implementation plan

**Goal:** Fix the observed scout/analysis workload and usage-accounting failures, run one new bounded AU/UAE end-to-end validation, update PR13 and deliver actual reports.

**Base:** `9c2829a`. User authorizes one fresh validation after fixes. Keep Malaysia/DFSA/MAS disabled, UAE external embedding disabled, hybrid experimental, role models/effort unchanged, old run artifacts immutable.

## Evidence and decisions

Prior scout60s/analyst90s failures were imposed by the validation harness. Production analysis allowed120s. Three unknown attempts consumed184,241 outer reservations; the runtime omitted unknown scout reservations and charged two analyst calls that never reached the provider. Two ledgers used different overheads. Of2,048 candidates,1,929 were FRL; all first96 analysis slots belonged to one compilation. The writer was skipped for lack of verified claims.

Use one serialized-request reservation formula, distinguish provider attempts from local refusals, preserve unknown reservations through retries, and share a thread-safe admission ledger across model/embedding calls. Protect downstream headroom. Bound scout summaries to16k whole-passage characters without deleting saved evidence. Rotate analysis across sources/documents and reduce default analysis batches to6 passages/9k characters. Do not solve this by changing models, effort or hiding incomplete coverage.

## Ownership and steps

- [x] Coordinator: runtime accounting, generation ledger/client, runner/orchestrator reserves and focused integration tests implemented. Documentation/push follow validation.
- [x] Coverage worker1: Scout summary bounds and explicit usage diagnostics, owned Scout file/new focused test only.
- [x] Coverage worker2 (explicit assignment): pure source/document-fair analysis batching and existing focused tests only.
- [x] Red/green targeted tests and independent focused runtime review (including four corrected accounting/compatibility findings). Integrated suite: 1,073 tests +8 subtests, no skips,64.82s. An initial full run found two stale default/budget expectations; both were corrected and checked before this final suite.
- [x] Freeze a **25-minute,600k known-plus-unknown-reserved-token,8-document,4-Exa,10-embedding/100k-byte** validation with no gap rounds. One fresh monotonic deadline, no conflicting short wrapper clamps, existing models, one coherent ledger and actor/source preflight before network.
- [x] Execute the single authorized validation `f17f39d0` at `a7ff8af`. **Clean acceptance failed:** one corroboration timeout/two output-limit errors, then Docker/PostgreSQL shutdown before the writer. Four analysis batches succeeded and evidence/4 supported facts survived restart. No paid continuation/replacement. A separate offline recovered draft is clearly labelled; scope/deferrals remain explicit.
- [x] Address observed bounds offline: Scout16,384 output, ordinary verifier120s/8,192, runtime corroboration90s/8,192, explicit timeout classification and journal usage splits. Preserve historical assessment limits. Independent review: no blockers. Final full suite: **1,075 tests +8 subtests, no skips,70.34s**. These final follow-up changes are live-unvalidated.
- [x] Generate the explicitly labelled offline recovered partial draft and validation report (7/6 PDF pages plus HTML); inspect all pages; package seven safe peer files with checksums; track artifact hashes. PR13 updated with pushed runtime/evidence and the measured failed-run/final-bound distinction. Clean live acceptance remains unmet.

No extra paid proof/replacement run on this allowance. If the bounded validation fails, preserve the failure and exact remaining issue rather than relabel it successful.
