"""Recall scoring against the M0 ground truth (PRD v2 §11). Run explicitly: ``pytest eval/``."""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from score_recall import HALT_THRESHOLD, Item, canonical, gate, load_items, main, score  # noqa: E402

GROUND_TRUTH = Path(__file__).parent / "m0_ground_truth.csv"


def item(id_, url, kind="regulatory", reach="fetchable"):
    return Item(id_, kind, reach, url)


ITEMS = [
    item("A", "https://www.hkma.gov.hk/a", reach="fetchable"),
    item("B", "https://www.hkma.gov.hk/b", reach="fetchable"),
    item("C", "https://www.mas.gov.sg/c", reach="blocked"),
    item("D", "https://wolfsberg-group.org/d", kind="international", reach="fetchable"),
]


def test_an_item_counts_once_however_many_findings_match_it():
    recall = score(ITEMS, ["https://www.hkma.gov.hk/a", "https://www.hkma.gov.hk/a", "https://www.hkma.gov.hk/a"])
    assert recall["all"].found == 1


def test_an_unmatched_item_does_not_count():
    recall = score(ITEMS, ["https://www.hkma.gov.hk/unrelated"])
    assert recall["all"].found == 0 and recall["all"].total == 4


def test_official_publication_aliases_count_as_the_same_document():
    landing = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251210-1-EN"
    pdf = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20251210-1-EN/20251210-1-EN.pdf"
    assert score([item("A", landing)], [pdf])["all"].found == 1
    news = "https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=26PR19&lang=EN"
    content = "https://apps.sfc.hk/edistributionWeb/api/news/content?lang=EN&refNo=26PR19"
    assert score([item("B", news)], [content])["all"].found == 1
    circular = "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/doc?refNo=25EC62"
    api = "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=25EC62&lang=EN"
    assert score([item("C", circular)], [api])["all"].found == 1


def test_recall_denominator_matches_the_brief_market_and_dates():
    items = [
        Item("HK", "regulatory", "fetchable", "https://example.org/hk", ("HK",), date(2026, 1, 1)),
        Item("SG", "regulatory", "fetchable", "https://example.org/sg", ("SG",), date(2026, 1, 1)),
        Item("OLD", "regulatory", "fetchable", "https://example.org/old", ("HK",), date(2020, 1, 1)),
    ]
    result = score(items, ["https://example.org/hk"], jurisdictions=["HK"],
                   period_start=date(2025, 11, 4), period_end=date(2026, 11, 4))
    assert (result["all"].found, result["all"].total) == (1, 1)


def test_hk_scope_uses_hong_kong_copies_of_shared_fatf_publications():
    items = load_items(GROUND_TRUTH)
    mas_urls = [i.url for i in items if "mas.gov.sg" in i.url]
    sfc_urls = [
        "https://apps.sfc.hk/edistributionWeb/api/circular/openFile?lang=EN&refNo=26EC13",
        "https://apps.sfc.hk/edistributionWeb/api/circular/list-content/circular/aml/doc?lang=EN&refNo=26EC39",
    ]
    hk = score(items, sfc_urls, jurisdictions=["HK"])
    assert (hk["all"].found, hk["all"].total) == (2, 18)
    assert (hk["regulatory"].found, hk["regulatory"].total) == (0, 14)
    assert score(items, mas_urls, jurisdictions=["HK"])["all"].found == 0
    assert score(items, sfc_urls, jurisdictions=["SG"])["all"].found == 0
    assert score(items, mas_urls, jurisdictions=["SG"])["all"].found == 7
    assert score(items, sfc_urls + mas_urls, jurisdictions=["SG", "HK"])["all"].found == 7


def test_title_alone_is_not_a_match_only_the_canonical_url_is():
    # Same name, different URL: rule 5 needs the same publication, identified by its canonical URL.
    recall = score([item("A", "https://www.hkma.gov.hk/circulars/a")], ["https://www.hkma.gov.hk/circulars/a-copy"])
    assert recall["all"].found == 0


def test_three_recall_groups_follow_the_ground_truth_reporting_rule():
    recall = score(ITEMS, ["https://www.hkma.gov.hk/a", "https://www.mas.gov.sg/c", "https://wolfsberg-group.org/d"])
    assert (recall["all"].found, recall["all"].total) == (3, 4)
    assert (recall["fetchable"].found, recall["fetchable"].total) == (2, 3)
    assert (recall["regulatory"].found, recall["regulatory"].total) == (2, 3)


def test_canonical_urls_ignore_case_in_scheme_and_host_fragment_and_trailing_slash():
    assert canonical("HTTPS://WWW.MAS.gov.sg/publications/x/#frag") == "https://www.mas.gov.sg/publications/x"
    assert canonical("https://a.gov/x/") == canonical("https://a.gov/x")


def test_a_run_that_cites_the_canonical_url_in_another_form_still_matches():
    recall = score([item("A", "https://www.hkma.gov.hk/a")], ["HTTPS://WWW.HKMA.gov.hk/a/"])
    assert recall["all"].found == 1


def test_gate_proceeds_at_or_above_the_threshold_and_halts_below_it():
    assert HALT_THRESHOLD == 0.5
    proceed, _ = gate(score(ITEMS, ["https://www.hkma.gov.hk/a", "https://www.hkma.gov.hk/b"]))
    assert proceed  # 2 of 3 fetchable
    proceed, message = gate(score(ITEMS, ["https://www.hkma.gov.hk/a"]))
    assert not proceed and message.startswith("HALT")  # 1 of 3 fetchable


def test_empty_fetchable_set_has_zero_rate_and_halts():
    recall = score([item("C", "https://www.mas.gov.sg/c", reach="blocked")], [])
    assert recall["fetchable"].total == 0 and recall["fetchable"].rate == 0.0
    proceed, _ = gate(recall)
    assert not proceed


def test_the_real_ground_truth_loads_with_24_items_in_the_documented_split():
    items = load_items(GROUND_TRUTH)
    assert len(items) == 24
    assert sum(1 for i in items if i.reach == "fetchable") == 18
    assert sum(1 for i in items if i.kind == "regulatory") == 20


def test_cli_exit_code_is_nonzero_on_halt(tmp_path):
    run = tmp_path / "urls.txt"
    run.write_text("https://www.hkma.gov.hk/unrelated\n", encoding="utf-8")
    assert main([str(GROUND_TRUTH), "--run-urls", str(run)]) == 1


def test_cli_exit_code_is_zero_when_recall_clears_the_gate(tmp_path):
    items = load_items(GROUND_TRUTH)
    fetchable = [i.url for i in items if i.reach == "fetchable"]
    run = tmp_path / "urls.txt"
    run.write_text("\n".join(fetchable), encoding="utf-8")
    assert main([str(GROUND_TRUTH), "--run-urls", str(run)]) == 0


def test_cli_can_reproduce_a_market_and_period_scoped_score(tmp_path, capsys):
    truth = tmp_path / "truth.csv"
    truth.write_text("id,kind,reach,url,jurisdiction,published,effective\n"
                     "HK,regulatory,fetchable,https://example.org/hk,HK,2026-01-01,\n"
                     "SG,regulatory,fetchable,https://example.org/sg,SG,2026-01-01,\n"
                     "OLD,regulatory,fetchable,https://example.org/old,HK,2020-01-01,\n")
    run = tmp_path / "urls.txt"
    run.write_text("https://example.org/hk\n")
    assert main([str(truth), "--run-urls", str(run), "--jurisdictions", "HK",
                 "--period-start", "2025-11-04", "--period-end", "2026-11-04",
                 "--as-of", "2026-11-04"]) == 0
    assert "1/1" in capsys.readouterr().out
