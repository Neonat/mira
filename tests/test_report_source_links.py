"""Reader links must not expose SFC JSON or retarget saved evidence."""
from copy import deepcopy
from dataclasses import replace
from html.parser import HTMLParser

import pytest

from mira.corroboration_display import assessment_html
from mira.render import render_signed_off
from mira.report import ReportContext, render_html
from test_render import AT, BRIEF, _stored, fixture, freeze


class Anchors(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))


@pytest.mark.parametrize("source_url, reader_url", [
    ("https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC69"),
    ("https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC2&lang=EN",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC2"),
    ("https://apps.sfc.hk/edistributionWeb/api/circular/content?lang=EN&refNo=26EC39",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC39"),
    ("https://apps.sfc.hk/edistributionWeb/api/news/content?refNo=26PR19&lang=EN",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR19"),
])
@pytest.mark.parametrize("reviewed", [False, True])
def test_source_links_open_readable_publication_without_mutating_evidence(source_url, reader_url, reviewed):
    snapshot, saved, passage = fixture()
    passage = replace(passage, source_url=source_url)
    snapshot = freeze(snapshot, [saved], [passage])
    frozen_before = snapshot.model_dump_json()
    if reviewed:
        html = render_signed_off(snapshot, generated_at=AT)
    else:
        html = render_html(snapshot, ReportContext(
            BRIEF, "draft", {saved.finding_id: _stored(saved)}, {passage.id: passage}, {}, AT,
        ))
    links = Anchors(html).hrefs
    assert reader_url in links
    assert source_url not in links
    assert reader_url in html  # The appendix's visible URL also matches its destination.
    assert source_url not in html
    assert snapshot.model_dump_json() == frozen_before
    assert passage.source_url == source_url


def test_corroboration_and_origin_links_use_reader_pages_without_mutating_assessment():
    envelope = {"assessment": {"status": "inconclusive", "checked_at": "2026-11-08T09:00:00Z",
        "base_evidence_input": {"passages": {"primary": {
            "source_url": "https://apps.sfc.hk/edistributionWeb/api/news/content?refNo=26PR19&lang=EN",
            "title": "Primary publication"}}},
        "candidates": [{"passage": {"id": "candidate",
            "source_url": "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN",
            "title": "Candidate publication"}}],
        "decisions": [{"passage_id": "candidate", "quote": "Saved candidate text.",
            "relation": "uncertain", "origin_relation": "unknown", "reason": "Origin unconfirmed.",
            "origin_evidence": [{"passage_id": "primary", "quote": "Saved origin text.", "reason": "Source account."}]}]}}
    before = deepcopy(envelope)
    html = assessment_html(envelope)
    links = Anchors(html).hrefs
    assert "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC69" in links
    assert "https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR19" in links
    assert "/api/" not in html
    assert "Saved candidate text." in html and "Saved origin text." in html
    assert envelope == before


@pytest.mark.parametrize("source_url", [
    "https://www.hkma.gov.hk/publication.pdf",
    "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC69",
    "https://apps.sfc.hk/edistributionWeb/api/circular/openFile?lang=EN&refNo=26EC69",
    "https://apps.sfc.hk/edistributionWeb/api/circular/search?year=2026",
    "https://apps.sfc.hk/edistributionWeb/api/consultation/content?refNo=26CP1&lang=EN",
    "https://apps.sfc.hk.evil.example/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN",
    "https://evil.example@apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&refNo=26EC2&lang=EN",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN&lang=TC",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=TC",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69%26refNo%3D26EC2&lang=EN",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26PR19&lang=EN",
    "https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN&attachment=1",
])
def test_unrelated_or_ambiguous_links_are_not_retargeted(source_url):
    snapshot, saved, passage = fixture()
    passage = replace(passage, source_url=source_url)
    html = render_html(snapshot, ReportContext(
        BRIEF, "draft", {saved.finding_id: _stored(saved)}, {passage.id: passage}, {}, AT,
    ))
    assert source_url in Anchors(html).hrefs
