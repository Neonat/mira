from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from threading import Event
from uuid import uuid4

import pytest

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


def test_failed_scout_preserves_partial_fetches_and_llm_usage(monkeypatch):
    from datetime import UTC, datetime
    from contextlib import nullcontext
    import pytest
    from mira.interfaces import ScoutFailure
    from mira.llm import LLMError
    from mira import agents

    monkeypatch.setattr(agents.scout, 'connect', lambda _: nullcontext(None))
    def fail_after_work(run):
        run.log.append(FetchAttempt(url='https://www.hkma.gov.hk/doc', outcome='saved',
                                    document_version_id=uuid4(), error=None, attempted_at=datetime.now(UTC)))
        run.discovery.append({'url': 'https://www.hkma.gov.hk/doc'})
        run.tokens_in, run.tokens_out, run.model = 3, 4, 'scripted'
        raise LLMError('model failed', 5, 6)
    monkeypatch.setattr(_ScoutRun, 'execute', fail_after_work)
    scout = WebScout('unused', None, SimpleNamespace())
    with pytest.raises(ScoutFailure) as caught:
        scout.run(context(), uuid4(), SimpleNamespace(max_documents=2))
    failure = caught.value
    assert [a.outcome for a in failure.fetch_log] == ['saved']
    assert failure.selection_diagnostics['discovered'][0]['url'].endswith('/doc')
    assert (failure.tokens_in, failure.tokens_out) == (8, 10)
    assert isinstance(failure.cause, LLMError)


@pytest.mark.parametrize('response_received', [False, True])
def test_unexpected_error_during_owned_fetch_records_one_charged_attempt(monkeypatch, response_received):
    scout = WebScout('unused', None, SimpleNamespace())
    run = _ScoutRun(scout, None, context(), uuid4(), SimpleNamespace(max_documents=2))
    def fails_after_response(run, url, link=None):
        if response_received:
            run.allowance -= 1
        raise ValueError('extraction failed')
    monkeypatch.setattr(_ScoutRun, '_fetch_new', fails_after_response)
    with pytest.raises(ValueError, match='extraction failed'):
        run._fetch('https://www.hkma.gov.hk/a')
    assert run.allowance == 1
    assert len(run.log) == 1 and run.log[0].outcome == 'failed'
    reuser = _ScoutRun(scout, None, run.ctx, uuid4(), SimpleNamespace(max_documents=2))
    with pytest.raises(ValueError, match='extraction failed'):
        reuser._fetch('https://www.hkma.gov.hk/a')
    assert reuser.allowance == 2 and reuser.log == []
