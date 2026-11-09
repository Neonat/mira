# Australia/UAE mixed retrieval — 10 November 2026

Implemented source-specific routes for the Australian Federal Register, AUSTRAC public guidance and CBUAE federal publications. Malaysia, DIFC/DFSA and MAS remain disabled in the dedicated validation workspace; no new browser grants or UAE external embedding grant were added. Hybrid remains experimental.

Audience: engineering peers and technical reviewers. These are method/integration results, not signed-off audit findings or competition quality claims.

## Verified implementation

- Controlled AU/AE brief choices with existing SG/HK defaults. UAE is explicitly federal-source scope, not all UAE regulators.
- Federal Register Versions → strictly scoped Documents metadata → supported fixed HTML/PDF. The actual server rejects `$expand`; the corrected flow uses separate collection requests. Complete native records are retained, while API metadata and viewer shells produce no legal-text citation passages.
- Registration/availability dates remain separate from effective dates, including propagation through the file-index metadata. Discovered HTML/PDF counterparts survive alias deduplication and respect reserved document allowance. Their separate capture records are not independent corroboration.
- UAE publication hubs follow only approved same-host files. UAE text remains keyword-searchable without external embeddings. Source notices survive capture, Python/SQL verification inputs and frozen report rendering.
- Seeding forces MAS inactive, preserves operator-disabled sources and preserves existing operation restrictions for the new profiles. Historical report snapshots remain unchanged; the notice migration was applied locally only.

Runtime commits: `a5280fc` initial integration; **`360280e5693516413952ae5d66e5b41b355128f1`** corrected API contract and print layout. Independent focused runtime review found no remaining blockers. The final full suite passed **1,045 tests plus 8 subtests, no skips, in 66.49s**. The earlier full suite's 27 failures exposed a SQL/Python provenance mismatch and a synthetic MAS fixture; both were fixed with regressions. The intermediate 1,039-pass result preceded the API contract fix and is not the final result.

## Single bounded research validation

Actual run: `0451a19c-431b-47aa-848e-d521e3817990`; its dedicated workspace identifier is in the [portable result](2026-11-10-mixed-retrieval-validation.json). The actual run used `a5280fc`, then completed **partial in 246.623 seconds**. Its normal renderer produced a coverage-only draft with **zero verified findings**.

| Check | Recorded result |
|---|---|
| Research acquisition | 12 attempts: 11 saved representations/versions and one HTTP400 native API query |
| Saved evidence | 2,311,175 extracted characters; 2,048 passages; every stored extraction hash and passage offset matches; every extracted non-whitespace character is covered |
| Source mix | Australian legislation HTML, AUSTRAC HTML/PDF and CBUAE federal HTML/PDF; alternate formats/compilations are not separate independent publications |
| Actual Exa | 3 searches |
| Models / embeddings | 11 model requests and 6 embedding requests; 61,277 combined known tokens; 184,241 conservative unknown-call reservations; 245,518 total allowance against 250,000 |
| Experimental vector cache | 27 AU vectors; **0 UAE vectors**; no usefulness claim |
| Disabled-source audit | MAS inactive/zero saved versions; zero active MY/DFSA sources in the dedicated workspace |
| Research output | Partial draft, zero verified findings; not an accepted AU/UAE audit research report |

Two scout calls and one analyst call timed out under the validation wrapper. Further analysis batches were refused by its shared conservative token allowance. Usage for the timed-out calls is unavailable; reservations are not measured/billed tokens. The wrapper bounded ordinary requests by role and analysis requests to 90 seconds, below the production analyst default of 120 seconds. This tests the declared validation envelope, not longer-running model acceptance. No successful analyst/verifier/writer research chain or human precision is claimed.

The preserved draft displays Mira's **internal budget counter of183,654/250,000 model tokens**. This differs from the wrapper's **61,277 known +184,241 reserved =245,518** because they use different scopes/reservation methods. The wrapper ledger is authoritative for the declared validation cap; neither counter establishes complete billed usage. The original HTML is unchanged, and its companion README/validation summary explain the distinction.

The first launch failed locally because the worktree lacked role-model variables. It stopped in `model_for` before provider construction, with **zero provider, Exa or publication requests**. It remains recorded as a failed run; existing main-project role settings were loaded unchanged. The actual network validation retained the original global 20-minute deadline. No `.env`, role-model configuration or historical failed run was rewritten.

## API correction after the run

Three additional public API diagnostics were performed, separately from the research run's 12-document budget: reproduce the HTTP400 error, request corrected Versions (HTTP200), and request scoped Documents (HTTP200). No replacement paid research/model run was started.

The server explicitly disallowed `$expand`. Corrected code passed an offline integration replay using those actual response bytes: 12 document-index links, two fixed full-file links, complete native-record round trips through `EvidenceWriter`, no metadata citation passages, and child availability **10 October 2026** preserved from the API registration record. The replay's database transaction was rolled back and checked. The final full suite includes the corrected code. **A clean paid end-to-end run of that final code remains unvalidated.**

## Reports for peers

The sharing package contains:

1. **Australia_UAE_Validation.html / .pdf:** this integration test's readable method, budget, storage and limitation tables.
2. **Source_Method_Pilot.html / .pdf:** the earlier Malaysia/Australia/DIFC/UAE source-method pilot, retaining its original failed global-fixture assertion and scoped follow-up audit.
3. **Mira_Australia_UAE_Partial_Draft.html:** the exact actual research fallback HTML, clearly partial and containing no verified findings. Its original bytes are preserved.

The PDFs use readable stacked source cards instead of squeezing nine fields into a printed table. The package contains no `.env`, keys, database dumps, original publisher files, raw article bodies, embeddings or private worker logs. CBUAE content remains scoped to private organisational use; these files are engineering review material rather than public audit advice.

Private evidence and raw logs are under `reports/mixed-retrieval-20261110/`. Portable metadata and artifact hashes accompany this record. No remote migration, merge, new paid research run or model-setting change was performed.

## Remaining acceptance work

Model latency/budget tuning and an uninterrupted final-code research validation remain open. The present result establishes acquisition and post-extraction storage behavior, not original PDF/OCR/table/fact completeness, national coverage, Malay/Arabic retrieval, human precision, corroboration quality or hybrid superiority. The live log also records optional CFF font decoding warnings; extracted-text hash preservation does not resolve that independent parsing concern. Private cloud Storage and recovery acceptance remain separate from this source extension.
