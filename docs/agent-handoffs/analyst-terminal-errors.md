# Analyst terminal-response fix

Objective: repair the reproduced loss of model error/usage information before one newly authorized bounded HK validation with actual Exa HTTP transport, browser fallback and corroboration enabled; MAS inactive.

Base: `14199765b56c9381624b8d0f00c3fa3eec35cc77`. Fix: `b8b81341bdcff7cf023afae683c03ae479995990` on `codex/ingestion-corroboration`. Coordinator owns `mira/llm.py`, focused tests and integration/evidence. Reviewer inspected read-only; no other worker edits, model changes, migrations or deployment.

## Reproduction and fix

The previous run (`a88dd20e`) retained only `bounded request failed`, with unavailable usage. Its exact analyst/provider cause cannot be recovered, and the approximately 170-second duration does not prove a timeout or output-limit failure.

Offline investigation found a concrete failure path in the installed OpenAI SDK: `get_final_response()` returns only a completed response, while failed/incomplete lifecycle events carry response objects and usage. Calling the helper on an incomplete stream raises before Mira reads its terminal status/usage. The child then discarded the exception category. Output validation errors also became ordinary `LLMError`, disabling the existing bounded-call repair path.

`OpenAIClient` now consumes completed/incomplete/failed terminal events directly, preserves their reported usage, and fails closed on interrupted streams. Incomplete output limits, failed responses, stream errors and refusals have safe categories. The bounded subprocess transmits only allowlisted error categories and token counts, never provider bodies or prompts; output-validation errors retain their subtype so the existing repair attempt and aggregate usage accounting work. `call_checked` preserves the category when aggregating prior usage. No missing provider usage is invented; an interrupted stream before its terminal event remains unmeasured.

Sources: installed `openai/lib/streaming/responses/_responses.py`; [official Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events). Model names, reasoning effort, source permissions, evidence/quote guards and historical reports remain unchanged.

## Verification

- Red reproduction: six focused failures before the fix, including terminal usage loss and discarded child error category/type.
- Focused tests cover actual installed SDK + `httpx.MockTransport` for completed, failed and incomplete SSE, interrupted streams, body redaction, child serialization, bounded output repair and combined usage. Network fixtures make no live API calls.
- Full integration command: `PYTHONPATH=/private/tmp/mira-browser-deps:. MIRA_BROWSER_EXECUTABLE=<existing Chromium> MIRA_TEST_DATABASE_URL=<local PostgreSQL> PYTHONDONTWRITEBYTECODE=1 /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests eval -q -p no:cacheprovider --basetemp=/private/tmp/mira-analyst-fix-full --tb=short` → **495 passed + 8 subtests, none skipped, 51.61 seconds**. Includes real Chromium fixtures and local PostgreSQL. No repeat full suite required for subsequent evidence-only edits.
- Independent reviewer found no blockers in runtime/test diff and checked installed SDK lifecycle semantics; coordinator subsequently added real-SDK completed/failed cases, included in the full suite.

## Live validation and limits

Exactly one newly user-authorized run, `fe65444d-589c-4a76-b3db-c216d76757ae`, uses the ordinary Exa API-key transport behind its normal runner factory, with validation-only query counting. It does not use the earlier plugin relay. Its fresh evidence store receives no benchmark material. Nominal limits and HK brief match `e2fda30f`; browser is a permission-controlled fallback and may not trigger. MAS is inactive, and temporary HKMA browser approval is removed after the run.

The validation harness restores the runtime's normal 64,000-output-token ceiling, replacing the previous harness's 16,000-token ceiling, and allows up to 360 seconds per call within a shared 25-minute/600,000-token allowance. These harness differences are disclosed; they are not global model settings or a claim that the old failure was definitively output-limited. Unknown-usage reservations remain separate from reported tokens/cost.

See [live outcome and coverage comparison](../../eval/evidence/2026-11-08-hk-exa-run-fe65444d.md) for the run result, feature exercise counts, historical comparison and exact next step. Full original response retention, enterprise access decisions, human precision labels and remote deployment remain separate work. PR7 is updated without merging/deploying.

## Further defects found in the same bounded validation

The successful analyst response contained 21,687 output tokens, above the previous harness ceiling; this supports restoring the normal ceiling, but does not recover the historical missing terminal event. The first verification stage then exposed two separate integration defects:

1. Non-exact primary quotations raised before the existing quote verifier. `35103a9` marks factual corroboration not checked for those quotations, removes any stale same-ID assessment after a rewrite, and still runs the original PR6 fuzzy/numeric/semantic verification. It does not relax strict corroboration evidence validation. Two red regressions cover fabricated numbers and extraction whitespace; an additional regression covers stale assessment removal. Full suite at this point: 498 + 8, none skipped.
2. Multiple quotations from one passage compared differently in Python and PostgreSQL because SQL used locale collation while Python uses ordinal order. Same citation objects and counts, different array order, caused `corroboration base evidence changed`. `0172344` adds migration `20261108110000_mira_evidence_quote_order.sql`, replacing only the current capture function's quote sort with `COLLATE "C"`. It is applied to local PostgreSQL only. Applied migrations and historical evidence rows/snapshots are untouched. Red DB regression reproduced the error; after the fix, the actual run's Python/SQL bases compare equal and all 20 candidate-current checks pass.

Final integrated suite: **499 tests + 8 subtests, none skipped, 54.84 seconds**. Independent reviewer found no remaining blocker in either fix. An additional full-suite run was justified by each newly reproduced runtime/database defect; no extra paid diagnostic or research run was used.

The single validation ID was continued twice from persisted checkpoints, with its initial analysis and acquisition retained, existing checks reused only for matching frozen inputs, failed steps preserved and prior reported/unknown-reserved usage charged forward. The original 25-minute deadline, 30-document allowance and six-query Exa cap remain in force. This is explicitly a resumed partial validation, not an uninterrupted clean end-to-end run. The outcome artifact records all source segments and interruptions.
