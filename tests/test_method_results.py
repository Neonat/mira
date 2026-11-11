"""Country projections must keep measured denominators and permissions intact."""
import importlib
import json
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "eval" / "evidence"


def evidence(name):
    return json.loads((EVIDENCE / f"{name}.json").read_text())


def results(code):
    # A missing implementation is an explicit red assertion, not a collection error.
    try:
        module = importlib.import_module("mira.method_results")
    except ModuleNotFoundError:
        pytest.fail("country method projection has not been implemented")
    return module.country_method_results(code)


def row(data, section, method):
    return next(item for item in data[section] if item["method"] == method)


def test_hk_keeps_archive_observations_separate_from_historical_research():
    data = results("HK")
    archive = evidence("2026-11-10-archive-hybrid-validation")
    live = evidence("2026-11-08-hk-authorized-followup-7be59cdf")["current"]
    hybrid = row(data, "archive", "hybrid")
    assert hybrid["indexed_passages"] == archive["live_result"]["saved"]["indexed"] == 153
    assert hybrid["eligible_passages"] == 153
    assert hybrid["questions"] == 6
    assert hybrid["latency_seconds"] == archive["latency_summary"]["saved_hybrid_median_seconds"]
    assert row(data, "archive", "keyword")["latency_seconds"] == pytest.approx(0.0084)
    assert data["research"]["verified_facts"] == live["report_facts"] == 19
    assert data["research"]["acquired_benchmark"] == live["acquired"]["recall"]["all"] == {"found": 6, "total": 18}
    assert data["research"]["cited_benchmark"] == {"found": 5, "total": 18}
    assert data["research"]["kind"] == "historical_partial_live_report"
    assert "synthetic" in data["research"]["scope"].lower()


def test_au_representation_comparison_is_not_a_research_or_quality_score():
    data = results("AU")
    pilot = evidence("2026-11-10-country-method-pilot")
    assert row(data, "acquisition", "direct_publication")["sample_prefix_hits"] == pilot["descriptive_summary"]["anchor_pdf_hits"] == 20
    assert row(data, "acquisition", "browser")["sample_prefix_hits"] == 0
    assert row(data, "acquisition", "browser")["sample_prefix_total"] == 20
    assert "representation" in row(data, "acquisition", "browser")["observation"].lower()
    hybrid = row(data, "archive", "hybrid")
    assert hybrid["sample_passages"] == pilot["comparison"]["sample"]["selected_passages"] == 30
    assert hybrid["latency_seconds"] == pilot["descriptive_summary"]["hybrid_median_seconds_including_api"]
    assert "unlabelled" in hybrid["observation"]
    assert data["research"]["verified_facts"] == 3
    assert "acquired_benchmark" not in data["research"]


def test_ae_preserves_federal_scope_and_embedding_refusal():
    data = results("AE")
    pilot = evidence("2026-11-10-country-method-pilot")
    pdf = next(a for a in pilot["acquisitions"] if a["id"] == "ae-sanctions-pdf")
    assert row(data, "acquisition", "direct_publication")["pages"] == pdf["pages"] == 8
    assert "challenge" in row(data, "acquisition", "browser")["observation"]
    assert row(data, "archive", "hybrid")["status"] == "blocked"
    assert data["research"]["verified_facts"] == 0
    assert "federal" in data["research"]["scope"].lower()


@pytest.mark.parametrize("code", ["HK", "AU", "AE", "SG", "MY", "DFSA"])
def test_all_projections_are_scoped_referenced_and_do_not_fabricate_winners(code):
    data = results(code)
    assert data["country_code"] == code
    assert data["country_name"]
    assert data["recommendation"]
    assert "PostgreSQL" in data["storage"]
    assert "experimental" in data["storage"]
    assert data["quality_winner"] is None
    assert data["cost_comparison"] is None
    assert data["storage_size_comparison"] is None
    for section in ("acquisition", "archive"):
        assert data[section]
        assert all(r["status"] in {"measured", "recommended", "not_tested", "blocked"} and r["observation"] for r in data[section])
    for ref in data["references"]:
        assert ref["path"].startswith("eval/evidence/")
        assert (EVIDENCE.parents[1] / ref["path"]).is_file()
    if code in {"MY", "DFSA"}:
        assert all(r["status"] == "blocked" for r in data["acquisition"] + data["archive"])
        assert "verified_facts" not in data["research"]
    if code == "SG":
        assert "MAS automation remains disabled" in data["recommendation"]
        assert "other Singapore sources" in data["recommendation"]
        assert "verified_facts" not in data["research"]


def test_result_mutations_cannot_corrupt_later_calls():
    data = results("HK")
    data["research"]["acquired_benchmark"]["found"] = 999
    data["archive"][1]["status"] = "winner"
    data["references"].clear()
    fresh = results("HK")
    assert fresh["research"]["acquired_benchmark"]["found"] == 6
    assert fresh["archive"][1]["status"] == "measured"
    assert fresh["references"]


@pytest.mark.parametrize("code", ["", "ZZ", "../../private", None, [], "HK/../../secrets"])
def test_unknown_country_cannot_be_used_as_a_path(code):
    with pytest.raises(ValueError, match="Unsupported country"):
        results(code)
