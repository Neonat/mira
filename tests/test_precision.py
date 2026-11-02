"""Precision is computed only from human labels, and never reports a number while rows are unlabelled."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from precision import SEED, ClaimRow, sample, score, write_worksheet  # noqa: E402


def rows(n):
    return [ClaimRow(f"s{i:03d}", "multi_agent", f"claim {i}", f"passage {i}", f"quote {i}") for i in range(n)]


def labelled_sheet(tmp_path, labels, arm="multi_agent"):
    path = tmp_path / "worksheet.csv"
    write_worksheet(rows(len(labels)), path)
    with path.open(newline="", encoding="utf-8") as handle:
        table = list(csv.DictReader(handle))
    for row, label in zip(table, labels):
        row["label"] = label
        row["arm"] = arm
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=table[0].keys())
        writer.writeheader()
        writer.writerows(table)
    return path


def test_the_same_seed_draws_the_same_sample_every_time():
    claims = rows(50)
    assert [r.sample_id for r in sample(claims, 10)] == [r.sample_id for r in sample(claims, 10)]
    assert [r.sample_id for r in sample(claims, 10, seed=SEED)] == [r.sample_id for r in sample(claims, 10)]


def test_a_sample_larger_than_the_claims_returns_them_all_in_order():
    assert [r.sample_id for r in sample(rows(3), 10)] == ["s000", "s001", "s002"]


def test_the_worksheet_leaves_the_label_blank_for_a_human_to_fill_in(tmp_path):
    path = tmp_path / "worksheet.csv"
    write_worksheet(rows(2), path)
    with path.open(newline="", encoding="utf-8") as handle:
        table = list(csv.DictReader(handle))
    assert all(row["label"] == "" for row in table)


def test_precision_is_the_share_of_supported_labels(tmp_path):
    result = score(labelled_sheet(tmp_path, ["supported", "supported", "unsupported", "supported"]), "multi_agent")
    assert result.labelled == 4 and result.supported == 3 and result.unlabelled == 0
    assert result.rate == 0.75 and result.complete


def test_a_blank_label_is_never_counted_as_supported(tmp_path):
    result = score(labelled_sheet(tmp_path, ["supported", "", "supported"]), "multi_agent")
    assert result.supported == 2 and result.labelled == 2 and result.unlabelled == 1


def test_an_incomplete_sample_reports_no_precision_number(tmp_path):
    result = score(labelled_sheet(tmp_path, ["supported", "", ""]), "multi_agent")
    assert result.rate is None and not result.complete


def test_an_unrecognised_label_is_not_counted_as_supported(tmp_path):
    result = score(labelled_sheet(tmp_path, ["supported", "yes", "Supported "]), "multi_agent")
    assert result.supported == 1 and result.labelled == 1 and result.unlabelled == 2


def test_partially_supported_is_not_counted_as_supported(tmp_path):
    result = score(labelled_sheet(tmp_path, ["supported", "partially_supported"]), "multi_agent")
    assert result.supported == 1 and result.rate == 0.5


def test_only_the_requested_arm_is_scored(tmp_path):
    path = labelled_sheet(tmp_path, ["supported", "unsupported"], arm="single_agent")
    assert score(path, "multi_agent").labelled == 0
    assert score(path, "single_agent").labelled == 2
