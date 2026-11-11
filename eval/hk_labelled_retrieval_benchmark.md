# Hong Kong saved-archive retrieval benchmark

Compare Mira’s keyword, vector-only and hybrid retrieval at top 10 for an analyst looking for citable support in the saved Hong Kong archive. The [blind case manifest](hk_blind_review_cases.json) records the questions and their scopes. The coordinator keeps draft labels and expected support in a local answer key. The questions were prepared from saved passage text and provenance before any rankings for them were generated.

## Archive and questions

Use the local workspace from the [November 10 experiment](evidence/2026-11-10-archive-hybrid-validation.md), with HKMA and SFC selected and the baseline as-of date set to 4 November 2026. A read-only inventory found 153 eligible passages across 23 versions, containing 134,015 UTF-8 bytes. All 153 had a matching current vector under `text-embedding-3-small`, 384 dimensions and revision `mira-te3-small-384-v1`. Keep MAS, Malaysia and DFSA disabled. The benchmark is tied to this archive version so newly saved facts can be evaluated in a later edition.

| Cases | What the cases measure |
|---|---|
| 4 exact IDs | Find the right notice or document and its answer-bearing passage |
| 4 paraphrases | Find explicit support from analyst wording that differs from the publisher’s |
| 2 no-answer candidates | Return volume on plausible, unsupported questions close to saved evidence |
| 2 market cases | Hold the question and selected source IDs fixed and change only the task jurisdiction |
| 4 date cases | Hold each question fixed and compare the day before and day of publication |

Two exact IDs occur only in saved source URLs. Report those separately from the two identifiers present in indexed passage text. The current keyword implementation indexes passage content and always includes a `money laundering` search term. Preserve that behavior for the comparison and record the actual parsed keyword query.

## Build the blind review pack

With the pinned archive available in the local database and `MIRA_TEST_DATABASE_URL` set to its loopback connection, run this from the repository root.

```sh
python -m eval.hk_blind_review
```

Open `reports/hk-blind-review/mira-hong-kong-blind-review.html` in a browser. The builder uses a read-only transaction and checks the eligible passages against the frozen fingerprints. The generated file contains saved passage text and belongs in local `reports/`. The coordinator’s local answer key is `eval/hk_labelled_retrieval_cases.json`. The review pack, answer key and reviewer exports are kept out of the public repository.

The first pass offers one passage from each of up to three publications. Those suggestions use local word and phrase matches. **Menu → Options → Case tools** opens the full archive. A first pass with no supporting pick leaves the case open for a full no-answer review. Exported JSON records which suggested passages were reviewed.

### Scope controls

- For the market pair, use the same workspace, selected HKMA/SFC source IDs, allowed brief jurisdictions (`HK`, `AU`), as-of date and question. The HK task has the SFC evidence. The AU task deliberately receives the HK source IDs and its eligible pool must be empty. This tests that the ranking query applies its market filter even when handed the wrong source selection. Market comparison with a populated AU pool would require a different archive design.
- For each date pair, check every passage of the target version is excluded on the preceding day and eligible on the recorded publication day. The HK scope goes from 105 to 109 eligible passages for STREAMS 2 and from 125 to 128 for the PEP update. The STREAMS 2 query asks what the circular announced, so the relevant boundary is the circular’s publication on 26 January, ahead of its stated 2 February launch.
- The runtime retains null publication dates in historical scopes, and the baseline contains 55 such passages. Review their text for possible support when labelling a date control. These controls establish how the filter handles explicit dates in the current archive. The archive snapshot contains one stored version per selected document, so it cannot establish historical reconstruction or superseded-version handling.
- Before scoring, validate all returned passage IDs against the eligible IDs for the case. Report any market or date leakage as a failed control even if the leaked passage does not answer the question. Use the date and market controls outside the primary relevance averages.

## Relevance review

Use binary passage labels. Assign **1** when the passage supplies explicit, citable support for a requested fact in the case’s scope. A multi-part question can have multiple relevant passages. Assign **0** for a topical mention, a link or title without the requested detail, a different obligation or entity, or text that only repeats the question. A correct publication can contain both grades. Reviewers can use the source URL and page to establish provenance, and should require the passage text to substantiate the claim.

The local answer key records provisional positive anchors and some near misses. A `null` expected answer is a candidate for zero support. Review the complete eligible pool for each case in a fixed passage order with method and rank hidden. Have a second reviewer check all positives, disagreements and zero-answer cases, then reconcile and freeze the query texts, final labels, rationale, reviewer provenance and manifest hash before any ranking is run. For a complete query, every omitted passage is judged nonrelevant. Keep unresolved labels marked incomplete and withhold metrics that require complete judgements. In particular, never treat a partially reviewed empty label set as a confirmed no-answer case.

## Comparison protocol

1. Resolve the same authorized actor and source grants for all arms. Use a read-only, repeatable-read view of the pinned archive and cache, or a faithful frozen local copy with the same eligibility rules. Select the latest eligible version as of the case’s date before ranking. Verify each scope’s corpus and index hashes against the manifest. If the archive or permissions change, recover the authorized snapshot or version the benchmark and re-review affected labels.
2. Use the current keyword path with English full-text matching and `ts_rank_cd`, vector-only exact cosine from the semantic arm, and the current RRF hybrid with constant 60 and 40 candidates per input list. Return up to 10 distinct passage IDs per arm with the existing passage-ID tie break. Use the same compatible cached passage vectors and the same query embedding for vector-only and hybrid. Preserve genuine short or empty outputs. A `no_eligible_passages` outcome with zero results and an independently verified empty pool passes the exclusion check without an embedding request. Record errors and fallbacks in a populated scope as failed or unavailable arms.
3. Keep benchmark ranking export and scoring in `eval/`. The [existing comparator](hybrid_archive_compare.py) checks two arms under one shared scope. A later benchmark runner needs a three-arm export with per-case scope equality. Record exact text, scope, eligible passage IDs, hashes, ranked IDs, method settings, timing and coverage. Store validated query vector identities tied to exact text, model, dimensions and revision if provider use is separately authorized. Benchmark labels and IDs do not become runtime search hints.
4. This design phase uses the database only for a read-only inventory and passage review. The existing passage vectors do not provide query embeddings for the new prompts. Review and freeze the labels offline now. A later comparison requires compatible saved query embeddings or a separately authorized bounded query-embedding run. A local proxy embedding would answer a different experiment.

### Metrics and decision rules

| Measure | Report |
|---|---|
| Answerable exact-ID and paraphrase cases | Per query and per group, report hit@10, MRR@10, recall@10 and precision@10. Precision uses a denominator of 10, and recall uses all reviewed relevant passage IDs. Show paired wins, ties and losses and the number of judged pairs for each method comparison. |
| No-answer cases | Report the count of queries returning any candidates, mean candidates returned and the per-query counts. Recall is undefined. A candidate count measures unsupported retrieval workload. Any later claim about false answers or abstention requires its own evaluation. |
| Market and date controls | Report excluded passage count returned, any ineligible result and whether the expected support was retrieved in the paired eligible case. A scope leak fails that method’s control regardless of relevance scores. |
| Latency, cost and coverage | Report warm database rank time separately from the query-embedding request time. Attribute that request to both semantic methods when estimating their standalone end-to-end times and costs, while counting actual shared usage once. Report historical cold indexing (29,443 tokens for this archive) and any separately authorized query usage independently, with actual tokens and the recorded rate for any dollar estimate. Track keyword-eligible, embedding-eligible, current indexed, pending and blocked passages by scope. |

Retain per-case results for all three arms, including mixed outcomes. The hand-selected sample measures passage retrieval on the pinned archive. Publication acquisition, evidence completeness and report quality require their own measurements.

### Snapshot fingerprints

In the manifest, hash compact UTF-8 JSON with no whitespace, preserving array order. Sort rows by passage ID. For `corpus_sha256` use arrays of `[passage_id, version_id, source_key, publication_date_or_null, content_sha256]`. Compute `content_sha256` on the exact UTF-8 passage text. For `index_sha256` use arrays of `[passage_id, content_sha256, vector_sha256]` from the eligible cache rows at the recorded model, dimensions and revision, with `vector_sha256` computed over PostgreSQL’s `embedding::text` in UTF-8. The manifest pins the identity of the local data without copying the full text or vector values into the repository.
