# Offline archive retrieval evaluation

Objective: provide a prospective, equal-output-budget lexical/hybrid comparison without retrieval, invented relevance labels or benchmark injection.

Base SHA: `4eb63707ef8ecdaecf9c472f46be18c81691b6c1`.

Owned files: `eval/hybrid_archive_compare.py`, `eval/test_hybrid_archive_compare.py`, `eval/hybrid_archive_queries.json`, this handoff. All runtime, contracts, migrations, PRD, source permissions, other workers' files and historical evidence were read-only. No commits, push, provider/Exa/browser/network/DB calls or credential reads.

Sources: repository `AGENTS.md`, `docs/agent-handoffs/README.md`, the 2026-11-10 archive-hybrid design/plan, coordinator's explicit bounded assignment. Questions are handcrafted unlabelled research prompts, frozen before retrieval; no saved archive was inspected to select them. Their content is not accepted ground truth.

Changes: pure JSON `compare(data)` and offline CLI; deterministic controlled fixtures for hybrid win, lexical win, tie, zero-relevant and absent labels; input validation and provenance-separated metrics. Six mixed literal/paraphrased AML questions are frozen in `eval/hybrid_archive_queries.json`, SHA-256 `3323d3709f5a09c0f5293832eb02ee2bbb711fec693520d1254c53e9b9b4cf48`. Do not edit questions after observing rankings.

## Export input schema (version 1)

The following example is schematic, not an observed result. Export all six frozen query IDs and exact texts. Each query requires both arms, including empty `passage_ids` if no results. Root `k` is the same requested positive integer top-k for both arms; each ranking has zero through k unique nonempty string IDs in descending rank order. Fewer results retain the requested-k precision denominator. Do not pad rankings with invented IDs.

```json
{
  "schema_version": 1,
  "kind": "saved_archive",
  "k": 10,
  "expected_query_ids": ["aml-01", "aml-02", "aml-03", "aml-04", "aml-05", "aml-06"],
  "queries": [
    {
      "id": "aml-01",
      "text": "What checks identify the people who ultimately control a corporate customer?",
      "lexical": {
        "passage_ids": ["passage-uuid-1", "passage-uuid-2"],
        "scope": {
          "workspace_id": "workspace-uuid",
          "jurisdiction": "HK",
          "as_of": "2026-11-10",
          "source_set_sha256": "hash-of-eligible-source-set",
          "mas_enabled": false
        },
        "corpus_id": "sha256-of-frozen-eligible-passage-identities-and-content-hashes",
        "index_id": "sha256-of-frozen-index-state-and-model-revision-coverage"
      },
      "hybrid": {
        "passage_ids": ["passage-uuid-2", "passage-uuid-3"],
        "scope": {
          "workspace_id": "workspace-uuid",
          "jurisdiction": "HK",
          "as_of": "2026-11-10",
          "source_set_sha256": "hash-of-eligible-source-set",
          "mas_enabled": false
        },
        "corpus_id": "sha256-of-frozen-eligible-passage-identities-and-content-hashes",
        "index_id": "sha256-of-frozen-index-state-and-model-revision-coverage"
      }
    }
  ]
}
```

The example omits the remaining five query objects for space; the evaluator rejects that omission. `expected_query_ids` must exactly match unique query cases. Output order follows that manifest. `scope` must be a nonempty JSON object, exactly equal for every arm/query (object-key order ignored). Include actual market/date/workspace/source-set selection in it; the evaluator cannot independently prove those declarations. `corpus_id` and `index_id` must be nonempty strings equal across every arm/query. They are opaque fingerprints, not checked for SHA syntax. `index_id` is the frozen **comparison-state fingerprint** attached equally to both arms; lexical retrieval does not require vectors. Record partial/blocked index counts and elapsed/usage measurements in the coordinator's accompanying evidence. Equality of output k is not proof of equal compute or semantic index coverage. Keep the corpus/index fixed during all queries and retain the actual export.

`kind` is either `saved_archive` or `controlled_fixture`. Optional additional export metadata is allowed but is not interpreted or copied into the comparison output. The output retains comparison identity, texts, rankings and label provenance; retain the input alongside it for grade/source reproducibility.

### Optional relevance labels

Omit `labels` entirely for these six prospective archive questions. `labels: null` is invalid. Only attach labels when a complete relevant set for the frozen corpus is actually available, with provenance; do not derive labels from the retrieved rankings. For a labelled query:

```json
"labels": {
  "frozen": true,
  "complete": true,
  "provenance": {"kind": "human", "source": "immutable-review-artifact-and-version"},
  "grades": {"relevant-passage-uuid": 2, "another-relevant-uuid": 1, "reviewed-nonrelevant-uuid": 0}
}
```

Grades must be finite nonnegative numbers (binary 0/1 is valid). Any grade >0 counts as relevant for these metrics; grade magnitude is not weighted. The complete/frozen flags are assertions by the exporter: every omitted passage ID is nonrelevant, and all relevant IDs, including those outside top-k, must appear. `{}` explicitly asserts **zero relevant passages**, not an unknown set. A partial judgement pool cannot use this complete-label interface. Saved-archive label provenance is `human` or `model`; controlled fixtures require `controlled_fixture`. Model/self-provided labels never become human precision. Provenance groups have separate aggregates, in addition to explicitly provenance-mixed overall descriptive counts.

## Metrics and interpretation

- Per query: overlap count, overlap/k, intersection/union Jaccard (null for two empty rankings), ranked-only IDs, shared-ID rank movement (`lexical_rank - hybrid_rank`, positive means movement upward in hybrid).
- With labels: precision@k = retrieved relevant/k; recall@k = retrieved relevant/all positive labels; MRR@k = reciprocal first relevant rank, else 0; hit@k = 1 if any positive label is retrieved, else 0. MRR/hit are per query with denominator 1. No labels means all four metrics null.
- Explicit zero relevant labels: precision/MRR/hit are 0; recall is null because its denominator is 0. No perfect scores are fabricated. Output includes requested k and per-query denominators.
- Aggregate: metric-specific paired hybrid wins/ties/lexical wins and paired-query denominators; macro means over the same available pairs; separate unlabelled IDs/count by list length; separate provenance counts/groups. No applicable labels means zero paired queries and null macro means, not ties.
- Completely unlabelled output is `descriptive_only_no_usefulness_winner`. Controlled fixtures establish only that the evaluator distinguishes positive/negative/tie mechanisms. Neither establishes archive usefulness, publication acquisition/report recall, human precision, or generalization.

## Commands and scoped checks

```sh
PYTHONPATH=.:eval /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest eval/test_hybrid_archive_compare.py -q -p no:cacheprovider
/Users/natsim/Documents/dbsearch/.venv/bin/python -m eval.hybrid_archive_compare --input exported-rankings.json --output comparison.json
```

Omit `--output` to emit JSON on stdout. Bad schema, malformed JSON and file errors exit 2 with a concise error and no traceback/raw input echo. The pure API raises `ValueError` for schema errors.

TDD evidence: missing module initially failed collection; with an explicit unimplemented API, **28 failed, 1 passed** for the intended absent comparison behavior. Implementation then **29 passed**. Added preservation/descriptive-output coverage failed **1 failed, 34 passed** on missing `rankings`; implementation then **35 passed**. A large finite integer-grade safety test exposed float-conversion overflow (**1 failed, 35 passed**); integer-safe validation then **36 passed in 0.17s**, no skips. Tests cover incomplete/duplicate queries, duplicate/oversized rankings, scope/corpus/index mismatch, invalid k/labels/grades/provenance, empty rankings, absent labels, known metrics/rank movement and CLI round-trip/safe malformed-input errors. Default shell Python lacked pytest; reused the repository's existing venv without installation. `git diff --check` for owned code/query files passed. No full suite was run; coordinator owns the single integration run.

Open risks: no actual archive SQL results or quality labels available in this task; observational usefulness remains unknown. The evaluator verifies equality of exported declarations, not actual database eligibility, fingerprint construction, query freezing, source gates or label correctness. Partial index coverage can disadvantage hybrid. Six handcrafted queries are a modest prospective sample with no statistical efficacy claim.

Exact next step: coordinator exports both arms for the six frozen questions at equal k from one unchanged eligible corpus/index snapshot, retains hashes/coverage/usage, runs the offline CLI above, and reports mixed/negative/unlabelled outcomes with their limits. No further provider run is authorized by this handoff.

Status: complete (bounded evaluator and frozen questions); actual archive observation remains coordinator-owned.
