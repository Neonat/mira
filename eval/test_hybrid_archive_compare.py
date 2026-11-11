"""Controlled retrieval fixtures; no archive relevance labels are invented."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.hybrid_archive_compare import compare


def arm(ids):
    return {"passage_ids": ids, "scope": {"market": "fixture", "as_of": "2026-11-10"},
            "corpus_id": "fixture-corpus-v1", "index_id": "fixture-index-v1"}


def case(query_id, lexical, hybrid, grades=None, provenance="controlled_fixture"):
    result = {"id": query_id, "text": "Controlled test question", "lexical": arm(lexical),
              "hybrid": arm(hybrid)}
    if grades is not None:
        result["labels"] = {"frozen": True, "complete": True, "grades": grades,
                            "provenance": {"kind": provenance, "source": "test fixture v1"}}
    return result


def fixture():
    cases = [case("hybrid-win", ["x", "y"], ["r", "x"], {"r": 2}),
             case("lexical-win", ["r", "x"], ["x", "y"], {"r": 1}),
             case("tie", ["x", "r"], ["x", "r"], {"r": 1, "outside": 1}),
             case("zero", ["x", "y"], ["y", "z"], {}),
             case("unlabelled", ["a", "b"], ["b", "c"])]
    return {"schema_version": 1, "kind": "controlled_fixture", "k": 2,
            "expected_query_ids": [q["id"] for q in cases], "queries": cases}


def test_controlled_wins_losses_ties_and_denominators():
    report = compare(fixture())
    rows = {q["id"]: q for q in report["queries"]}
    win = rows["hybrid-win"]
    assert win["hybrid"]["precision_at_k"] == .5
    assert win["hybrid"]["recall_at_k"] == 1
    assert win["hybrid"]["mrr_at_k"] == 1
    assert win["hybrid"]["hit_at_k"] == 1
    assert rows["tie"]["hybrid"]["recall_at_k"] == .5
    assert rows["tie"]["hybrid"]["mrr_at_k"] == .5
    assert win["denominators"] == {"precision": 2, "recall": 1, "mrr_and_hit": 1}
    assert report["aggregate"]["paired"]["precision_at_k"] == {
        "hybrid_wins": 1, "ties": 2, "lexical_wins": 1, "paired_queries": 4}
    assert report["aggregate"]["paired"]["recall_at_k"]["paired_queries"] == 3
    assert report["aggregate"]["labelled_queries"] == 4
    assert report["aggregate"]["unlabelled_query_ids"] == ["unlabelled"]


def test_zero_relevant_and_absent_labels_do_not_fabricate_perfect_scores():
    rows = {q["id"]: q for q in compare(fixture())["queries"]}
    assert rows["zero"]["lexical"] == {"precision_at_k": 0, "recall_at_k": None,
                                              "mrr_at_k": 0, "hit_at_k": 0}
    assert all(v is None for v in rows["unlabelled"]["hybrid"].values())
    assert rows["unlabelled"]["denominators"]["recall"] is None


def test_overlap_rank_movement_and_short_rankings():
    data = fixture()
    data["queries"] = [case("short", ["a", "b"], ["b"], {"b": 1})]
    data["expected_query_ids"] = ["short"]
    row = compare(data)["queries"][0]
    assert row["overlap_count"] == 1
    assert row["overlap_at_k"] == .5
    assert row["jaccard"] == .5
    assert row["rank_movement"] == [{"passage_id": "b", "lexical_rank": 2,
                                      "hybrid_rank": 1, "improvement": 1}]
    assert row["hybrid_only"] == []
    assert row["lexical_only"] == ["a"]
    assert row["hybrid"]["precision_at_k"] == .5


def test_model_labels_remain_separate_from_human_precision():
    data = fixture()
    data["kind"] = "saved_archive"
    for i, q in enumerate(data["queries"]):
        if "labels" in q:
            q["labels"]["provenance"]["kind"] = "human" if i == 0 else "model"
    report = compare(data)
    assert report["aggregate"]["label_provenance_counts"] == {"human": 1, "model": 3}
    assert report["aggregate"]["by_label_provenance"]["human"]["labelled_queries"] == 1
    assert report["queries"][1]["label_provenance"]["kind"] == "model"
    assert "human precision" in report["caveats"][0]


def test_all_unlabelled_saved_results_are_descriptive_only_and_keep_rankings():
    data = fixture()
    data["kind"] = "saved_archive"
    for query in data["queries"]:
        query.pop("labels", None)
    report = compare(data)
    assert report["interpretation"] == "descriptive_only_no_usefulness_winner"
    assert report["aggregate"]["labelled_queries"] == 0
    assert report["aggregate"]["paired"]["precision_at_k"]["paired_queries"] == 0
    assert all(v is None for v in report["aggregate"]["macro_means"]["precision_at_k"].values())
    assert report["queries"][0]["rankings"] == {"lexical": ["x", "y"], "hybrid": ["r", "x"]}


def test_empty_rankings_are_valid_but_not_perfect_overlap():
    data = fixture()
    data["queries"] = [case("empty", [], [], {"r": 1})]
    data["expected_query_ids"] = ["empty"]
    row = compare(data)["queries"][0]
    assert row["jaccard"] is None
    assert row["overlap_at_k"] == 0
    assert row["hybrid"]["precision_at_k"] == 0
    assert row["hybrid"]["recall_at_k"] == 0


def test_finite_integer_grades_do_not_overflow_validation():
    data = fixture()
    data["queries"][0]["labels"]["grades"] = {"r": 10 ** 400}
    assert compare(data)["queries"][0]["hybrid"]["recall_at_k"] == 1


@pytest.mark.parametrize("bad", [None, [], "input", 1])
def test_reject_non_object_input(bad):
    with pytest.raises(ValueError):
        compare(bad)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(k=0),
    lambda d: d.update(k=True),
    lambda d: d.update(kind="live"),
    lambda d: d.update(schema_version=2),
    lambda d: d["queries"][0]["lexical"].update(passage_ids=["x", "x"]),
    lambda d: d["queries"][0]["hybrid"].update(passage_ids=["a", "b", "c"]),
    lambda d: d["queries"][0]["hybrid"].update(passage_ids=[1]),
    lambda d: d["queries"][0]["hybrid"].update(corpus_id="different"),
    lambda d: d["queries"][0]["hybrid"].update(index_id="different"),
    lambda d: d["queries"][0]["hybrid"].update(scope={"market": "different"}),
    lambda d: d["queries"][1]["lexical"].update(corpus_id="other-query-corpus"),
    lambda d: d["queries"][0].pop("hybrid"),
    lambda d: d["queries"].pop(),
    lambda d: d["queries"].append(copy.deepcopy(d["queries"][0])),
    lambda d: d["expected_query_ids"].append("missing"),
    lambda d: d["expected_query_ids"].append("tie"),
    lambda d: d["queries"][0]["labels"].update(frozen=False),
    lambda d: d["queries"][0]["labels"].update(complete=False),
    lambda d: d["queries"][0]["labels"].update(grades={"r": -1}),
    lambda d: d["queries"][0]["labels"].update(grades={"r": float("nan")}),
    lambda d: d["queries"][0]["labels"].update(grades={"r": True}),
    lambda d: d["queries"][0]["labels"].update(provenance={"kind": "human", "source": "x"}),
    lambda d: d.update(queries=[]),
])
def test_reject_invalid_or_unpaired_inputs(mutation):
    data = fixture()
    mutation(data)
    with pytest.raises(ValueError):
        compare(data)


def test_cli_offline_round_trip_and_safe_error(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps(fixture()))
    command = [sys.executable, "-m", "eval.hybrid_archive_compare", "--input", str(source)]
    success = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
    assert success.returncode == 0, success.stderr
    assert json.loads(output.read_text()) == compare(fixture())
    source.write_text('{"secret": "must not echo raw input"')
    failure = subprocess.run(command, capture_output=True, text=True)
    assert failure.returncode == 2
    assert "Traceback" not in failure.stderr
    assert "must not echo" not in failure.stderr


def test_frozen_saved_questions_have_no_invented_labels():
    frozen = json.loads(Path(__file__).with_name("hybrid_archive_queries.json").read_text())
    assert frozen["kind"] == "saved_archive"
    assert frozen["provenance"]["kind"] == "handcrafted_unlabelled_research_questions"
    assert len(frozen["queries"]) == 6
    assert len({q["id"] for q in frozen["queries"]}) == 6
    assert all(set(q) == {"id", "text"} for q in frozen["queries"])
