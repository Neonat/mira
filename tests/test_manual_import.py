"""Manual import checks, offline."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from mira.fetch import AllowList, Fetcher, RawResponse, SiteBlocked
from mira.manual_import import ImportItem, ImportRefused, prepare_page, read_manifest
from mira.store import SourceRecord

MAS = SourceRecord(uuid4(), "MAS", "regulator", "https://www.mas.gov.sg", "SG",
                   ("metadata", "fetch", "store_text", "quote", "embed"),
                   {"block_markers": ["Sorry, this service is currently unavailable"]})
NOW = datetime(2026, 10, 26, tzinfo=UTC)
URL = "https://www.mas.gov.sg/regulation/notices/notice-626"


def item(path, url=URL):
    return ImportItem(path, url)


def test_accepts_pdf_and_html_from_the_source_site(tmp_path):
    pdf = tmp_path / "notice.pdf"
    pdf.write_bytes(b"%PDF-1.7 example")
    html = tmp_path / "page.HTML"
    html.write_text("<p>Notice 626</p>")
    assert prepare_page(item(pdf), MAS, NOW).kind == "pdf"
    page = prepare_page(item(html), MAS, NOW)
    assert (page.kind, page.url, page.source) == ("html", URL, MAS)


@pytest.mark.parametrize("url, reason", [
    ("http://www.mas.gov.sg/x", "https"),
    ("https://www.hkma.gov.hk/x", "not a MAS URL"),
    ("https://mas.gov.sg.example.com/x", "not a MAS URL"),
    ("not a url", "https"),
])
def test_url_must_be_https_on_the_sources_own_site(tmp_path, url, reason):
    path = tmp_path / "a.html"
    path.write_text("<p>x</p>")
    with pytest.raises(ImportRefused, match=reason):
        prepare_page(item(path, url), MAS, NOW)


def test_refuses_wrong_files_and_saved_block_pages(tmp_path):
    (tmp_path / "a.docx").write_bytes(b"PK")
    (tmp_path / "fake.pdf").write_text("<html>not a pdf</html>")
    (tmp_path / "blocked.html").write_text("<h1>Sorry, this service is currently unavailable.</h1>")
    for name, reason in (("missing.pdf", "not found"), ("a.docx", "only PDF and HTML"),
                         ("fake.pdf", "not a PDF"), ("blocked.html", "block page")):
        with pytest.raises(ImportRefused, match=reason):
            prepare_page(item(tmp_path / name), MAS, NOW)


def test_manifest_rows(tmp_path):
    (tmp_path / "manifest.csv").write_text(
        "file,url,title,published\n"
        "notice.pdf,https://www.mas.gov.sg/n,Notice 626,2026-05-25\n"
        "page.html,https://www.mas.gov.sg/p,,\n"
        ",,,\n"
    )
    items = read_manifest(tmp_path / "manifest.csv")
    assert items == [
        ImportItem(tmp_path / "notice.pdf", "https://www.mas.gov.sg/n", "Notice 626", date(2026, 5, 25)),
        ImportItem(tmp_path / "page.html", "https://www.mas.gov.sg/p", None, None),
    ]
    (tmp_path / "bad.csv").write_text("file,url\nnotice.pdf,\n")
    with pytest.raises(ImportRefused, match="url is required"):
        read_manifest(tmp_path / "bad.csv")


def test_blocked_site_is_not_asked_again_in_the_same_run():
    requests = []

    class Web:
        def get(self, url, headers, timeout, max_bytes):
            requests.append(url)
            if url.endswith("/robots.txt"):
                return RawResponse(404, {}, b"")
            return RawResponse(200, {"content-type": "text/html"}, b"Sorry, this service is currently unavailable")

    fetcher = Fetcher(AllowList([MAS]), transport=Web(), resolver=lambda host: ["93.184.216.34"], sleep=lambda s: None)
    with pytest.raises(SiteBlocked) as first:
        fetcher.fetch("https://www.mas.gov.sg/a")
    sent = len(requests)
    with pytest.raises(SiteBlocked) as second:
        fetcher.fetch("https://www.mas.gov.sg/b")
    assert not first.value.repeated and second.value.repeated and len(requests) == sent
