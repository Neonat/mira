# Full eligible archive hybrid experiment

The user requested removing the 40-passage corpus fallback, proper testing, MAS disablement and an update to PR13, explicitly noting that hybrid usefulness is experimental. Runtime `eb83d0e` implements bounded incremental indexing plus exact PostgreSQL keyword/cosine ranking over the eligible saved archive. The existing OpenAI model/key/cache identity and agent role models stay unchanged. [Portable evidence](2026-11-10-archive-hybrid-validation.json) contains the frozen corpus/index identities, query rankings, controlled labels, request totals and local evidence hashes.

**Mechanical result:** all **153 eligible saved Hong Kong passages** were indexed in five batches, with **zero pending**. The archive's **134,015 UTF-8 bytes** were unchanged before/after indexing. Query size is no longer the whole-corpus cutoff;40 is now per indexing batch. A separate 47-passage synthetic archive also completed indexing, with its deliberately late passage searchable beyond the old cutoff. The synthetic rows/cache were rolled back; the real archive's approved, immutable vectors remain cached for reuse. Historical reports/findings/passages were not rewritten.

One coordinator-authorized embedding-only validation was capped at 20 requests,50,000actual-plus-unknown-reserved tokens,200,000input bytes and 5minutes. It completed with **16 requests,29,949 measured tokens,137,040 input bytes and 16.797 seconds**, zero provider errors or unknown reservations. Cold indexing used 29,443 tokens for the 153 saved passages. No new research, publisher fetch, Exa, browser, generative-role call or MAS activity occurred. MAS stayed inactive with zero cached vectors. This allowance is consumed; no continuation/replacement was started.

## Same-corpus comparison, without assuming a winner

Six prospective AML questions were frozen **before retrieval** in `eval/hybrid_archive_queries.json` (SHA256 `3323d3709f5a09c0f5293832eb02ee2bbb711fec693520d1254c53e9b9b4cf48`). Both arms used the same source/workspace/jurisdiction/as-of selection, frozen corpus/index snapshot and requested top10. The keyword arm reuses the pre-existing scout full-text query/ranking. Hybrid adds cosine rankings with deterministic RRF60. No facts, URLs or targets from M0 were injected into runtime.

| Question | Shared passages in top10 | Same first passage? |
|---|---:|---|
| Corporate customer controllers | 5 | No |
| Suspicious-report submission platform | 7 | Yes |
| Sanctions screening | 5 | Yes |
| Account-opening identity checks | 8 | No |
| Supervisory training | 7 | Yes |
| Expensive property/luxury proceeds | 4 | Yes |

These rankings are **unlabelled**: all relevance/precision/recall/MRR/hit scores remain unavailable. Changes and overlap cannot establish usefulness. Warm median elapsed time, including the embedding HTTP request, was **0.80705 seconds hybrid versus 0.0084 seconds keyword**, across six queries. This small observational sample is not an archive-scale performance claim or equal-compute experiment; only output budgets were equal. Cold indexing is an additional upfront cost.

## Controlled cases show both benefit and drawbacks

The47-passage controlled corpus and complete relevance labels were declared in the harness before retrieval; these are synthetic ground truth, not human precision on regulatory research. At requested top3:

- **Synonym:** “automobile” found the car passage first in hybrid; keyword returned nothing. Hybrid recall/MRR/hit were1, versus 0 for keyword; fixed-k precision was1/3versus0.
- **Exact identifier:** both paths put the correct `ZXQ481` passage first and retrieved the single relevant passage. Hybrid also returned two irrelevant candidates; keyword returned only the correct one. Fixed-k metrics tie because both use denominator3.
- **No answer:** “volcanic eruption monitoring” has no relevant passage in this controlled corpus. Hybrid still returned three irrelevant candidates; keyword returned none. Precision/MRR/hit were0 for both, and recall is undefined with zero relevant labels. Semantic ranking has no relevance/abstention guarantee.

The offline evaluator additionally tests explicit hybrid wins, lexical wins and ties, with strict corpus/scope/index/query identity checks and no invented labels. These cases support keeping hybrid optional and experimental, with normal evidence verification downstream. They do not justify replacing the keyword path or claiming a research-quality gain. A blinded qualitative paired review is retained at `reports/archive-hybrid-20261110/review.md`; its top-k samples alone are not a complete relevance judgement set.

## Engineering validation and limits

**74 focused tests passed** before the live validation. Red/green regressions cover122 passages and a late semantic target; incremental resume and warm query-only requests; stale/future/hash/workspace/source gates; MAS exclusion; oversized-input starvation; actor/grant revocation; known usage through cache failure, deadline and non-timeout database disconnection; cumulative characters and per-request provider ceilings; truthful token-stop reasons; offline CLI preview/bounds; and the evaluator's positive/negative/tie/unlabelled cases.

Independent runtime review found two issues—usage lost after a database error and characters counted separately per batch. Both were fixed with regressions and re-reviewed. The final complete suite ran once and passed **997 tests + 8 subtests, none skipped,in 71.56 seconds**, including local PostgreSQL and actual Chromium. The live embeddings were exercised separately; full-suite API opt-ins were off. Raw proof is retained in `reports/archive-hybrid-20261110/` with its SHA inventory in the portable evidence.

The default worker indexing envelope remains40 passages per batch,4 batches,60,000 cumulative characters,20,000 tokens and 20 seconds; these bound work, not archive cardinality. Larger backfills use explicit finite CLI budgets and resume missing vectors. Partial/blocked coverage is exposed. Whole passages above the conservative 8,192-byte per-input bound remain stored and keyword-searchable; they are not silently truncated. Exact filtered SQL uses statement deadlines; very large-archive latency, concurrent indexer duplication and concurrent metadata/source changes remain unmeasured. The new cache source-gate migration was applied only locally. No merge or remote deployment occurred.
