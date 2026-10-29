"""The plain-search baseline: no model, cited URLs de-duplicated in rank order (PRD v2 §11)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

from arms import Hit, plain_search  # noqa: E402


def hit(url, n=1):
    return Hit(passage_id=f"p{n}", source_url=url, title="t", content="c")


def test_plain_search_cites_each_url_once_in_rank_order():
    hits = [hit("https://a.gov/1", 1), hit("https://a.gov/1", 2), hit("https://b.gov/2", 3)]
    result = plain_search("aml", lambda q, limit: hits, limit=20)
    assert result.arm == "plain_search"
    assert result.cited_urls == ("https://a.gov/1", "https://b.gov/2")


def test_plain_search_never_uses_a_model_so_it_costs_no_tokens():
    result = plain_search("aml", lambda q, limit: [hit("https://a.gov/1")])
    assert result.llm_tokens == 0


def test_plain_search_respects_the_limit():
    hits = [hit(f"https://a.gov/{i}", i) for i in range(50)]
    result = plain_search("aml", lambda q, limit: hits, limit=5)
    assert len(result.cited_urls) == 5


def test_plain_search_with_no_hits_cites_nothing():
    result = plain_search("aml", lambda q, limit: [])
    assert result.cited_urls == ()
