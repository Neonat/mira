from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from threading import Event
from uuid import uuid4

from mira.agents.scout import WebScout, _ScoutRun, _Visit, distinct_links, document_key
from mira.contracts import FetchAttempt
from mira.extract import Extracted, Link, extract_feed, extract_pdf
from test_orchestrator import context


def test_aliases_collapse_only_same_hkma_document_and_language():
    landing = "https://brdr.hkma.gov.hk/eng/doc-ldg/current/ABC"
    pdf = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/ABC/ABC.pdf"
    other = landing.replace("ABC", "DEF")
    feed = "https://www.hkma.gov.hk/rss.xml"
    links = [Link(u, "title", "") for u in (landing, pdf, other, feed)]
    assert [l.url for l in distinct_links(links)] == [pdf, other, feed]
    assert document_key(landing) != document_key(landing.replace("/eng/", "/chi/"))
    assert document_key(pdf.replace("brdr.hkma.gov.hk", "example.org")) != document_key(pdf)


def test_concurrent_tasks_share_one_fetch_and_do_not_spend_twice(monkeypatch):
    from datetime import UTC, datetime
    scout = WebScout("unused", None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    ctx = context()
    task = SimpleNamespace(max_documents=2)
    runs = [_ScoutRun(scout, None, ctx, uuid4(), task) for _ in range(2)]
    started, release = Event(), Event()
    calls = []
    url = "https://www.hkma.gov.hk/doc"
    def fetch_new(self, url, link=None):
        calls.append(url); started.set(); assert release.wait(3)
        self.allowance -= 1
        visit = _Visit(url, uuid4(), [uuid4()]); self.visits.append(visit)
        self.log.append(FetchAttempt(url=url, outcome="saved", document_version_id=visit.version_id,
                                    error=None, attempted_at=datetime.now(UTC)))
        return Extracted("Title", "complete", ["Evidence"])
    monkeypatch.setattr(_ScoutRun, "_fetch_new", fetch_new)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(runs[0]._fetch, url)
        assert started.wait(3)
        second = pool.submit(runs[1]._fetch, url)
        release.set()
        assert first.result().text == second.result().text == "Evidence"
    assert calls == [url]
    assert sum(2 - r.allowance for r in runs) == 1
    assert sorted(r.log[0].outcome for r in runs) == ["reused", "saved"]
    assert runs[0].visits[0].passage_ids == runs[1].visits[0].passage_ids
    # A different run cannot use the previous run's cache.
    third = _ScoutRun(scout, None, context(), uuid4(), task)
    third._fetch(url)
    assert len(calls) == 2


def test_feed_publication_is_distinct_from_update_or_context_date():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Rule</title>
    <link href="https://example.org/rule"/><updated>2026-01-01</updated></entry></feed>'''
    assert extract_feed(atom, "https://example.org/feed").links[0].published is None
    rss = b'''<rss><channel><item><title>Rule</title><link>https://example.org/rule</link>
    <pubDate>Thu, 03 Sep 2026 08:00:00 +0800</pubDate></item></channel></rss>'''
    link = extract_feed(rss, "https://example.org/feed").links[0]
    assert link.published == date(2026, 9, 3) and "RSS pubDate" in link.date_source


def test_pdf_publication_requires_unambiguous_official_header(monkeypatch):
    import pypdf
    page = SimpleNamespace(extract_text=lambda: "HKMA\n28 August 2026\nDear Sir or Madam\nEffective 1 January 2027")
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: SimpleNamespace(pages=[page], metadata=None))
    url = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/X/X.pdf"
    extracted = extract_pdf(b"fake", url)
    assert extracted.published == date(2026, 8, 28)
    assert "28 August 2026" in extracted.published_basis
    assert extract_pdf(b"fake", "https://example.org/20260828.pdf").published is None
    page.extract_text = lambda: "HKMA\nDear Sir or Madam\nEffective\n1 January 2027"
    assert extract_pdf(b"fake", url).published is None
    page.extract_text = lambda: "HKMA\n28 August 2026\n1 September 2026\nDear Sir or Madam"
    assert extract_pdf(b"fake", url).published is None


def test_found_requires_item_specific_evidence_not_just_a_fetched_hub():
    from mira.completeness import coverage_rows
    from mira.interfaces import ScoutTask
    from test_orchestrator import ExpectedScout, E_RULE, MAS, PASSAGES
    ctx = context()
    task = ScoutTask("T1", "regulatory_scout", "SG", "AML", (MAS.id,), (E_RULE.id,), 2)
    result = ExpectedScout(found_in=lambda task: True).run(ctx, uuid4(), task).result
    kwargs = dict(expected=[E_RULE], sources={MAS.id: MAS}, tasks=[task], skipped={},
                  passages={p.id: p for p in PASSAGES})
    assert coverage_rows(results={"T1": result}, **kwargs)[0].status == "found"
    unlinked = result.report.documents[0].model_copy(update={"expected_source_labels": []})
    result = result.model_copy(update={"report": result.report.model_copy(update={"documents": [unlinked]})})
    assert coverage_rows(results={"T1": result}, **kwargs)[0].status == "missing"
