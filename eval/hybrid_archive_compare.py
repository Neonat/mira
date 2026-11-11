"""Pure offline, equal-top-k comparison. See archive-hybrid-evaluation.md for schema.

No retrieval, provider, credential, database or runtime imports are used here.
Grades > 0 count as relevant; these binary metrics do not weight positive grades.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


METRICS = ("precision_at_k", "recall_at_k", "mrr_at_k", "hit_at_k")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _unique_ids(value):
    return (isinstance(value, list) and all(_string(v) for v in value)
            and len(value) == len(set(value)))


def _validate(data):
    _require(isinstance(data, dict), "input must be an object")
    _require(type(data.get("schema_version")) is int and data["schema_version"] == 1,
             "schema_version must be 1")
    _require(data.get("kind") in ("saved_archive", "controlled_fixture"), "invalid comparison kind")
    _require(type(data.get("k")) is int and data["k"] > 0, "k must be a positive integer")
    expected = data.get("expected_query_ids")
    _require(_unique_ids(expected) and bool(expected), "expected_query_ids must be unique nonempty IDs")
    queries = data.get("queries")
    _require(isinstance(queries, list) and bool(queries), "queries must be a nonempty array")
    ids = [q.get("id") if isinstance(q, dict) else None for q in queries]
    _require(_unique_ids(ids) and set(ids) == set(expected), "queries must exactly match expected_query_ids")
    identity = None
    for query in queries:
        _require(_string(query.get("text")), "each query needs text")
        for name in ("lexical", "hybrid"):
            arm = query.get(name)
            _require(isinstance(arm, dict), "each query needs both ranking arms")
            ranked = arm.get("passage_ids")
            _require(_unique_ids(ranked), "ranked passage IDs must be unique nonempty strings")
            _require(len(ranked) <= data["k"], "ranked passage count exceeds k")
            scope = arm.get("scope")
            _require(isinstance(scope, dict) and bool(scope), "each arm needs a nonempty scope object")
            _require(_string(arm.get("corpus_id")) and _string(arm.get("index_id")),
                     "each arm needs corpus_id and index_id")
            try:
                scope_json = json.dumps(scope, sort_keys=True, allow_nan=False)
            except (TypeError, ValueError):
                raise ValueError("scope must contain finite JSON values") from None
            current = (scope_json, arm["corpus_id"], arm["index_id"])
            if identity is None:
                identity = current
            _require(current == identity, "all arms and queries must share scope, corpus_id and index_id")
        if "labels" not in query:
            continue
        labels = query["labels"]
        _require(isinstance(labels, dict), "labels must be an object or omitted")
        _require(labels.get("frozen") is True and labels.get("complete") is True,
                 "labels must be explicitly frozen and complete")
        provenance = labels.get("provenance")
        _require(isinstance(provenance, dict), "labels need provenance")
        allowed = ("controlled_fixture",) if data["kind"] == "controlled_fixture" else ("human", "model")
        _require(provenance.get("kind") in allowed and _string(provenance.get("source")),
                 "label provenance must match comparison kind and include source")
        grades = labels.get("grades")
        _require(isinstance(grades, dict), "labels need a grades object")
        _require(all(_string(pid) and type(grade) in (int, float)
                     and (type(grade) is int or math.isfinite(grade))
                     and grade >= 0 for pid, grade in grades.items()),
                 "grades must map passage IDs to finite nonnegative numbers")


def _metrics(ids, relevant, k):
    if relevant is None:
        return dict.fromkeys(METRICS)
    hits = [rank for rank, pid in enumerate(ids, 1) if pid in relevant]
    return {"precision_at_k": len(hits) / k,
            "recall_at_k": len(hits) / len(relevant) if relevant else None,
            "mrr_at_k": 1 / hits[0] if hits else 0,
            "hit_at_k": int(bool(hits))}


def _aggregate(rows):
    paired, means = {}, {}
    for metric in METRICS:
        eligible = [r for r in rows if r["lexical"][metric] is not None
                    and r["hybrid"][metric] is not None]
        paired[metric] = {
            "hybrid_wins": sum(r["hybrid"][metric] > r["lexical"][metric] for r in eligible),
            "ties": sum(r["hybrid"][metric] == r["lexical"][metric] for r in eligible),
            "lexical_wins": sum(r["hybrid"][metric] < r["lexical"][metric] for r in eligible),
            "paired_queries": len(eligible)}
        means[metric] = {
            name: sum(r[name][metric] for r in eligible) / len(eligible) if eligible else None
            for name in ("lexical", "hybrid")}
    return {"labelled_queries": sum(r["label_provenance"] is not None for r in rows),
            "unlabelled_query_ids": [r["id"] for r in rows if r["label_provenance"] is None],
            "paired": paired, "macro_means": means}


def compare(data):
    """Return JSON-serializable evidence; raise ValueError for invalid/unpaired input.

    Complete labels assert that all omitted IDs are nonrelevant. An empty grades
    object explicitly means zero relevant passages, never perfect recall.
    """
    _validate(data)
    k, rows = data["k"], []
    by_id = {q["id"]: q for q in data["queries"]}
    for query_id in data["expected_query_ids"]:
        query = by_id[query_id]
        lexical, hybrid = (query[n]["passage_ids"] for n in ("lexical", "hybrid"))
        lex_ranks = {pid: i for i, pid in enumerate(lexical, 1)}
        hyb_ranks = {pid: i for i, pid in enumerate(hybrid, 1)}
        common = set(lexical) & set(hybrid)
        union = set(lexical) | set(hybrid)
        labels = query.get("labels")
        relevant = {pid for pid, g in labels["grades"].items() if g > 0} if labels is not None else None
        rows.append({
            "id": query_id, "text": query["text"],
            "label_provenance": labels["provenance"] if labels is not None else None,
            "denominators": {"precision": k, "recall": len(relevant) if relevant is not None else None,
                             "mrr_and_hit": 1 if relevant is not None else None},
            "lexical": _metrics(lexical, relevant, k), "hybrid": _metrics(hybrid, relevant, k),
            "rankings": {"lexical": list(lexical), "hybrid": list(hybrid)},
            "returned_counts": {"lexical": len(lexical), "hybrid": len(hybrid)},
            "overlap_count": len(common), "overlap_at_k": len(common) / k,
            "jaccard": len(common) / len(union) if union else None,
            "rank_movement": [{"passage_id": pid, "lexical_rank": lex_ranks[pid],
                               "hybrid_rank": hyb_ranks[pid],
                               "improvement": lex_ranks[pid] - hyb_ranks[pid]}
                              for pid in hybrid if pid in common],
            "lexical_only": [pid for pid in lexical if pid not in common],
            "hybrid_only": [pid for pid in hybrid if pid not in common]})
    aggregate = _aggregate(rows)
    groups = sorted({r["label_provenance"]["kind"] for r in rows if r["label_provenance"] is not None})
    aggregate["label_provenance_counts"] = {
        group: sum(r["label_provenance"] is not None and r["label_provenance"]["kind"] == group for r in rows)
        for group in groups}
    aggregate["by_label_provenance"] = {
        group: _aggregate([r for r in rows if r["label_provenance"] is not None
                           and r["label_provenance"]["kind"] == group]) for group in groups}
    first_arm = data["queries"][0]["lexical"]
    return {"schema_version": 1, "kind": data["kind"], "k": k,
            "interpretation": "descriptive_only_no_usefulness_winner" if not groups else
                "controlled_mechanism_only" if data["kind"] == "controlled_fixture" else
                "label_dependent_observation_no_generalized_winner",
            "comparison_identity": {key: first_arm[key] for key in ("scope", "corpus_id", "index_id")},
            "queries": rows, "aggregate": aggregate,
            "caveats": [
                "Model labels and controlled fixtures are not human precision; provenance groups remain separate.",
                "Unlabelled overlap and rank movement describe retrieval changes, not relevance or usefulness.",
                "Precision divides by requested k even with fewer results; recall divides by all positive labels.",
                "MRR and hit are per-query truncated at k; recall is null for zero relevant labels.",
                "Complete labels assume omitted passage IDs are nonrelevant; positive grade magnitude is ignored.",
                "Identity equality checks exported declarations, not database eligibility or label correctness.",
                "Equal top-k is an equal output budget, not proof of equal compute, indexing coverage or cost."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Previously exported JSON rankings")
    parser.add_argument("--output", type=Path, help="JSON destination; stdout if omitted")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        encoded = json.dumps(compare(data), indent=2, allow_nan=False) + "\n"
        if args.output is not None:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    except (OSError, UnicodeError, ValueError) as exc:
        # Do not echo raw inputs, scope contents, paths or traceback on malformed exports.
        message = "invalid JSON input" if isinstance(exc, json.JSONDecodeError) else (
            str(exc) if type(exc) is ValueError else "could not read or write comparison JSON")
        print(f"comparison error: {message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
