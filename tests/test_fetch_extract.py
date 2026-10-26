"""fetch_allowed, extraction and quote matching, with a fake web."""

from datetime import date
from uuid import uuid4

import pytest

from mira.agents.verifier import quote_match
from mira.extract import extract_feed, extract_html
from mira.fetch import AllowList, Fetcher, FetchFailed, FetchRefused, RawResponse
from mira.store import SourceRecord

HKMA = SourceRecord(uuid4(), "HKMA", "regulator", "https://www.hkma.gov.hk", "HK",
                    ("metadata", "fetch", "store_text"),
                    {"extra_hosts": ["brdr.hkma.gov.hk"], "crawl_delay_seconds": 2,
                     "block_markers": ["Sorry, this service is currently unavailable"]})
MANUAL = SourceRecord(uuid4(), "FATF", "manual", "https://www.fatf-gafi.org", None, ("metadata",))
HTML = {"content-type": "text/html; charset=utf-8"}


class FakeWeb:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def get(self, url, headers, timeout, max_bytes):
        self.requests.append(url)
        assert headers["User-Agent"].startswith("MiraResearchPrototype")
        if url.endswith("/robots.txt"):
            return self.pages.get(url, RawResponse(404, {}, b""))
        return self.pages.get(url, RawResponse(404, HTML, b"not found"))


def fetcher(pages, addresses=("93.184.216.34",)):
    web = FakeWeb(pages)
    times = [0.0]
    sleeps = []
    f = Fetcher(AllowList([HKMA, MANUAL]), transport=web, resolver=lambda host: list(addresses),
                clock=lambda: times[0], sleep=lambda s: sleeps.append(s) or times.__setitem__(0, times[0] + s))
    return f, web, sleeps


def test_fetches_allowed_page_and_respects_crawl_delay():
    f, web, sleeps = fetcher({"https://www.hkma.gov.hk/a": RawResponse(200, HTML, b"<p>AML</p>"),
                              "https://www.hkma.gov.hk/b": RawResponse(200, HTML, b"<p>CFT</p>")})
    assert f.fetch("https://www.hkma.gov.hk/a").kind == "html"
    f.fetch("https://www.hkma.gov.hk/b")
    assert sleeps and all(s <= 2 for s in sleeps) and sum(sleeps) >= 2


def test_refuses_hosts_schemes_and_manual_sources():
    f, _, _ = fetcher({})
    for url in ("https://evil.example/x", "ftp://www.hkma.gov.hk/x", "https://user:pw@www.hkma.gov.hk/",
                "https://www.hkma.gov.hk:8443/", "https://www.fatf-gafi.org/en/publications.html"):
        with pytest.raises(FetchRefused):
            f.fetch(url)


def test_redirect_to_another_host_is_refused():
    f, _, _ = fetcher({"https://www.hkma.gov.hk/r": RawResponse(302, {"location": "http://169.254.169.254/latest"}, b"")})
    with pytest.raises(FetchRefused):
        f.fetch("https://www.hkma.gov.hk/r")


def test_redirect_within_allow_list_is_followed():
    f, _, _ = fetcher({
        "https://www.hkma.gov.hk/r": RawResponse(301, {"location": "https://brdr.hkma.gov.hk/doc"}, b""),
        "https://brdr.hkma.gov.hk/doc": RawResponse(200, {"content-type": "application/octet-stream"}, b"%PDF-1.7 ..."),
    })
    page = f.fetch("https://www.hkma.gov.hk/r")
    assert page.url == "https://brdr.hkma.gov.hk/doc" and page.kind == "pdf"


def test_private_addresses_are_refused():
    f, _, _ = fetcher({}, addresses=("10.0.0.5",))
    with pytest.raises(FetchRefused, match="non-public"):
        f.fetch("https://www.hkma.gov.hk/a")


def test_robots_rules():
    disallow = RawResponse(200, {}, b"User-agent: *\nDisallow: /private\n")
    f, _, _ = fetcher({"https://www.hkma.gov.hk/robots.txt": disallow,
                       "https://www.hkma.gov.hk/ok": RawResponse(200, HTML, b"<p>x</p>")})
    f.fetch("https://www.hkma.gov.hk/ok")
    with pytest.raises(FetchRefused, match="robots"):
        f.fetch("https://www.hkma.gov.hk/private/x")
    unreachable, _, _ = fetcher({"https://www.hkma.gov.hk/robots.txt": RawResponse(503, {}, b"")})
    with pytest.raises(FetchRefused):
        unreachable.fetch("https://www.hkma.gov.hk/ok")


def test_block_pages_unsupported_types_and_errors_fail_visibly():
    f, _, _ = fetcher({
        "https://www.hkma.gov.hk/blocked": RawResponse(200, HTML, b"<h1>Sorry, this service is currently unavailable.</h1>"),
        "https://www.hkma.gov.hk/zip": RawResponse(200, {"content-type": "application/zip"}, b"PK.."),
    })
    for url, message in (("blocked", "block page"), ("zip", "not supported"), ("missing", "HTTP 404")):
        with pytest.raises(FetchFailed, match=message):
            f.fetch(f"https://www.hkma.gov.hk/{url}")


def test_html_extraction_keeps_text_links_and_dates_but_drops_chrome():
    body = b"""<html><head><title>AML circulars</title><script>var x = 1;</script></head><body>
      <nav><a href="/home">Home</a></nav>
      <main><h1>Circulars</h1>
        <ul><li>12 Dec 2025 <a href="/doc/1">Example circular on AML controls</a></li></ul>
        <p>Banks should apply enhanced due diligence.</p></main>
      <footer>Copyright</footer></body></html>"""
    page = extract_html(body, "https://www.hkma.gov.hk/list")
    assert page.title == "Circulars"
    assert "enhanced due diligence" in page.text and "var x" not in page.text and "Copyright" not in page.text
    assert [(link.url, link.published) for link in page.links] == [("https://www.hkma.gov.hk/doc/1", date(2025, 12, 12))]


def test_feed_extraction():
    body = b"""<rss><channel><title>HKMA: Circulars</title>
      <item><title>Example feed item</title><link>https://brdr.hkma.gov.hk/x</link>
      <pubDate>Thu, 03 Sep 2026 08:00:00 +0800</pubDate></item></channel></rss>"""
    page = extract_feed(body, "https://www.hkma.gov.hk/rss.xml")
    assert page.links[0].published == date(2026, 9, 3) and page.links[0].text == "Example feed item"


def test_quote_match():
    passage = "Authorized institutions should apply enhanced due diligence to high-risk customers."
    assert quote_match("apply enhanced due diligence", passage)
    assert quote_match("apply  “enhanced” due-diligence", passage.replace("due diligence", "due-diligence"))
    assert quote_match("Authorized institutions should apply enhanced due dilligence", passage)  # typo, fuzzy
    assert not quote_match("must report every transaction above HK$8,000", passage)
    assert not quote_match("", passage)
