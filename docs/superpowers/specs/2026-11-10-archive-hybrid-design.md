# Experimental hybrid retrieval over the eligible saved archive

User request: remove the whole-corpus40-passage fallback, test properly, keep MAS disabled and update PR13. The user explicitly treats usefulness as experimental. Existing OpenAI key/model/384-dimensional cache identity stay unchanged; no role-model or source-grant change.

## Approach

Coordinator choice: bounded incremental indexing plus exact PostgreSQL ranking. Raising the old cap still reloads/re-embeds a whole corpus and eventually fails; an approximate vector index introduces extra filtering/recall uncertainty before usefulness is measured. Exact pgvector search over an eligibility-filtered cache gives an honest baseline with statement deadlines and bounded returned candidates. No claim of unlimited size/latency.

Forty becomes **index batch size**, not searchable archive size. Persist each successful content/model/revision-bound batch; subsequent calls resume missing embeddings. Full archive eligibility is workspace, active source, store_text, manual import or fetch permission, task source/jurisdiction, latest published version as of the brief. MAS is excluded. Embeddings additionally require embed permission. Oversized whole passages stay stored/keyword-searchable and are counted explicitly; no truncation.

Query all eligible stored text for the lexical arm and all compatible/current indexed eligible passages for the cosine arm, taking bounded top candidates only after filtering. Fuse ranks with deterministic RRF(k60), return saved passage records and source/page provenance. Recheck eligibility/hash in SQL rather than loading all vectors into Python. Partial cache coverage is reported, never described as full semantic coverage. The switch still permits keyword-only use.

## Contracts

`HybridRetriever.retrieve(conn,ctx,task,*,remaining_tokens,remaining_seconds,index_missing=True)` returns existing passage/usage fields plus `eligible_passages,indexed_passages,pending_passages,blocked_passages,index_batches,indexing_stop_reason,cache_error`. The existing `.vectors` return stays compatible but archive results do not materialize the entire cache. `HybridRetriever.index(conn,ctx,task,*,remaining_tokens,remaining_seconds)` performs bounded indexing only. `HybridRetriever.keyword(conn,ctx,task,*,limit=None,timeout_seconds=None)` performs full-archive lexical retrieval without any provider request. All paths retain current actor/workspace checks.

`HybridLimits.max_index_passages=40` is per batch; add `max_index_batches=4`. Existing character/token/time limits remain request/job bounds and result_limit20. Query embeddings are budgeted before optional indexing; indexing/query known usage and conservative unknown reservations are aggregated and retained through cache failures/deadlines. Database phases use savepoints/transaction-local deadlines, preserving earlier successful batches. No new task retries automatically after a failed provider call.

Add an explicit bounded worker-side backfill command, separate from paid research, so an archive can finish indexing across jobs. Require workspace/actor/jurisdiction/as-of selection, existing enable flag and finite token/time/batch bounds. Do not start a research worker or fetch missing pages. Only a new migration may strengthen current cache-write source gates; no historical migration rewrite or remote deployment.

## Evaluation and acceptance

Before paid validation, tests must prove >40 eligible passages searchable, a late-in-order semantic target retrievable, partial indexing resumes, warm query-only embedding, exact version/content/permission/source filtering, MAS exclusion, deadlines/cancellation of provider children, usage through failures and bounded result counts. Include a lexical winner/tie in controlled relevance fixtures; compare equal top-k and do not pick queries after results.

Use a frozen saved corpus/query set for a modest observational lexical-vs-hybrid comparison where practical, retaining query labels and corpus/index hashes. Unlabelled overlap/rank movement is not precision. Controlled synthetic fixtures establish mechanism; no benchmark facts enter runtime.

Coordinator authorizes one new bounded embedding-only validation after offline tests/review: maximum20requests,50,000actual-plus-unknown-reserved tokens,200,000UTF-8 input bytes,5minutes; existing key, no Exa/publisher/browser/generative-role calls, no continuation/replacement. This is distinct from consumed earlier allowances. Report mixed/negative results and remaining indexing explicitly. Run the complete suite once after integration; update PR13 without merging/deploying.
