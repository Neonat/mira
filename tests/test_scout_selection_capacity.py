"""Selection capacity regressions using synthetic publisher pages."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from mira.agents import scout as module
from mira.agents.scout import WebScout, _ScoutRun
from mira.contracts import LinkSelection
from mira.extract import Extracted, Link
from test_orchestrator import context


def test_selected_publications_get_slots_before_optional_linked_pdf(monkeypatch):
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, source_ids=(), question='audit', role='regulatory_scout')
    run = _ScoutRun(scout, None, context(), uuid4(), task)
    first = 'https://example.org/one'
    second = 'https://example.org/two'
    pdf = 'https://example.org/attachment.pdf'
    run.candidates = [Link(first, 'Audit one', '', date(2025, 12, 1)),
                      Link(second, 'Audit two', '', date(2025, 11, 1))]
    fetched = []
    def fetch(url, link=None):
        if run.allowance <= 0:
            return None
        fetched.append(url)
        run.allowance -= 1
        return Extracted('Publication', 'complete', ['text'], links=[Link(pdf, 'Attachment', '')] if url == first else [])
    monkeypatch.setattr(run, '_fetch', fetch)
    monkeypatch.setattr(module, 'call_checked', lambda *a, **kw: SimpleNamespace(
        output=LinkSelection(link_labels=['L1', 'L2'], notes=None), tokens_in=0, tokens_out=0, model='test'))
    run._select_and_fetch()
    assert fetched == [first, second]
    assert run.allowance == 0


def test_dated_index_alias_is_retained_over_undated_pdf_discovery():
    from mira.agents.scout import distinct_links
    landing = Link('https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260102-1-EN',
                   'Dated audit circular', 'Official index', date(2026, 1, 2), 'index')
    pdf = Link('https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260102-1-EN/20260102-1-EN.pdf',
               'Search title', 'URL discovered by search provider')
    assert distinct_links([landing, pdf]) == [landing]
    assert distinct_links([pdf, landing]) == [landing]


def test_optional_linked_pdf_is_fetched_when_capacity_remains(monkeypatch):
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    run = _ScoutRun(scout, None, context(), uuid4(), SimpleNamespace(max_documents=2, source_ids=()))
    first, pdf = 'https://example.org/one', 'https://example.org/attachment.pdf'
    fetched = []
    def fetch(url, link=None):
        fetched.append(url)
        run.allowance -= 1
        return Extracted('Publication', 'complete', ['text'], links=[Link(pdf, 'Attachment', '')] if url == first else [])
    monkeypatch.setattr(run, '_fetch', fetch)
    run._fetch_document(first)
    assert fetched == [first, pdf]
    assert run.allowance == 0


def test_equally_dated_aliases_still_prefer_pdf():
    from mira.agents.scout import distinct_links
    landing = Link('https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260102-1-EN', 'Title', '')
    pdf = Link('https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260102-1-EN/20260102-1-EN.pdf', 'Title', '')
    assert distinct_links([landing, pdf]) == [pdf]
    assert distinct_links([pdf, landing]) == [pdf]
