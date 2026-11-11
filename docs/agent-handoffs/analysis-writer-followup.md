# Analysis and writer follow-up — 10 November 2026

Objective: address the two analysis failures and writer truncation observed in run `5fad1aa1`, and show the actual client query options without requiring a password. Base SHA: `bd6db19fdc06b5ce1d65cb79e5ead6a8728381d1`; branch `codex/durable-evidence-recovery`, PR13. Ewen/PR6 guards remain intact. This is a separate engineering follow-up; the original report and measured run remain unchanged.

## Diagnosis and changes

- Saved B1 reached the validation profile's 8,192 output limit; B3 failed structured-output validation below that limit. The historical isolated-process payload discarded the precise schema issue and raw response, so the exact B3 invalid field cannot be reconstructed. No factual diagnosis of that missing field is claimed.
- Whole-passage defaults are now 3 passages/4,500 content characters, 8 batches, 16,384 output tokens per attempt and 180 seconds total per batch. The environment template matches. A bounded analysis can correct invalid schema/labels once, sharing its original deadline and remaining token allowance. Admission includes serialized input/schema/output headroom. An unfunded/expired retry is not sent. Unknown usage retains its reservation and is not retried. Generic provider/output-limit errors are not automatically replayed.
- The writer previously generated prose that deterministic grounding always replaced with complete saved claim text. `writer/4` now requests only seven ordered sections of claim-label groups (at most 8 executive groups/64 references). Extra prose, unknown labels and excess output are rejected. Existing grounding still renders full saved text, restores omitted main-section findings, restricts inference placement and orders dates. Writer generation allows 16,384 output tokens/120 seconds within the shared run budget; other ordinary roles retain 8,192/120.
- Safe validation diagnostics carry at most eight schema-derived paths and allowlisted error codes across the provider boundary. Values, dynamic map keys, raw provider bodies and error context are excluded. Issues survive later local refusal/timeout, aggregate across attempts and reach failed-step metadata alongside usage.

Owned changes: coordinator integrated `mira/agents/{analyst,writer}.py`, `mira/{analysis_batches,generation,llm,orchestrator}.py`, associated tests, `.env.example` and current documentation. Bounded writer/diagnostic specialists handed back their files before integration; an independent read-only reviewer found no blockers, including the final diagnostic-retention follow-up. No migration, role-model/effort, global settings or source-permission edit. Historical evidence/reports were read-only.

## Validation

Final integrated command: `pytest tests eval -q -p no:cacheprovider --tb=short`, with local PostgreSQL and the configured actual Chromium executable. **1,100 tests plus 8 subtests passed; no skips, 64.94 seconds.** Narrow regressions ran first; the full suite ran once after integration. The [portable check record](../../eval/evidence/2026-11-10-analysis-writer-checks.json) retains log identity.

New checks cover known-usage corrections, a single shared deadline, zero-cost local refusals, unknown second-attempt reservations, persistent invalid output, safe diagnostics and their transport, omitted full claim text, malicious prose/unknown labels, section eligibility and writer headroom. Existing database pipeline, evidence/review and browser checks pass with the compact writer contract. No paid model, Exa or embedding execution occurred in this follow-up. The prior paid AU/UAE allowance remains consumed.

## UI and account access

The actual form was rendered in a local read-only preview and inspected with Australia/UAE selected. Queue run was disabled and forced to return false; it cannot submit research or access workspace data. The normal app still uses Supabase Auth/RLS unchanged. Existing local database/Auth/REST/gateway containers were started or left running without reset; no worker was started. Preview files and screenshots remain ignored local artifacts under `reports/generation-ui-fix-20261110/`.

Current options: AML/CFT; SG/HK/AU/AE controlled choices (AE federal only); 12–24-month lookback; as-of date; document/token allowances. There is no free-text question, source/hybrid toggle or plan-approval switch in this form. The production workflow's configurable approval pause is separate. Analyst/admin roles submit; reviewer/admin roles review.

The configured email is only a sign-in prefill. Its Supabase Auth user password is separate from database/API/dashboard credentials. The saved local rehearsal login belongs to another workspace and was not repurposed. No password was displayed, reset or changed, no user/grant was created, and no authenticated account was bypassed. Provisioned users need the appropriate workspace membership; invitations/reset handling require the operator's configured Auth flow.

## Remaining validation and next step

Private concerns for the user: smaller inputs reduce the maximum default passages attempted from 48 to 24 across eight full batches, and whole passages above 4,500 characters are explicitly deferred. Saved text is not lost, but exhaustive fact extraction remains unproven. Corrections consume remaining time and usage; larger output headroom can still be exhausted. These fixes pass automated checks but have not been checked against live generation. Prior UAE coverage and independent-corroboration gaps remain as measured; no quality win or clean end-to-end acceptance is claimed.

Exact next step: if a new paid validation is authorized, replay a tightly bounded set of saved failed analysis inputs plus the saved verified writer facts, without acquisition or changing historical reports, before relying on them in the demo. Do not resume/replace the prior run or launch another full research run on its consumed allowance. Keep Malaysia/DFSA/MAS disabled, hybrid experimental and role models/effort unchanged.

Status: implementation, integrated checks and UI preview complete; live generation confirmation remains outstanding. Update PR13; do not merge or deploy without a new instruction.
