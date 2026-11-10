from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from mira.agents import scout as module
from mira.agents.scout import WebScout, _ScoutRun
from mira.contracts import LinkSelection
from mira.extract import extract_html
from test_orchestrator import context


def test_native_dated_topic_publications_precede_navigation_without_model(monkeypatch):
    listing = extract_html(b'''<table>
      <tr><td>1 Dec 2025</td><td><a href="/one">Money laundering circular for banks</a></td></tr>
      <tr><td>2 Dec 2025</td><td><a href="/two">Money laundering enforcement action</a></td></tr>
      <tr><td>3 Dec 2025</td><td><a href="/other">Market trading circular</a></td></tr>
      </table><a href="/navigation">Money laundering guidance archive</a>''', 'https://example.org/list')
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, source_ids=(),
                           question='money laundering', role='regulatory_scout')
    run = _ScoutRun(scout, None, context(), uuid4(), task)
    run.candidates = listing.links
    run._record_discovery(listing.links, 'https://example.org/list', uuid4())
    fetched = []
    def fetch(url, link, *, reserved=0):
        fetched.append((url, link.published, link.date_source))
        run.allowance -= 1
    monkeypatch.setattr(run, '_fetch_document', fetch)
    monkeypatch.setattr(module, 'call_checked', lambda *a, **k: SimpleNamespace(
        output=LinkSelection(link_labels=['L3', 'L4'], notes=None), tokens_in=0, tokens_out=0, model='test'))
    run._select_and_fetch()
    assert {item[0] for item in fetched} == {'https://example.org/one', 'https://example.org/two'}
    assert {item[1] for item in fetched} == {date(2025, 12, 1), date(2025, 12, 2)}
    assert all('enclosing table/list record' in item[2] for item in fetched)
    assert all(item.get('selection_method') == 'publisher_record' for item in run.selection_diagnostics[-1]['deterministic_selected'] if item['selected'])


def test_listing_container_date_does_not_date_individual_undated_links():
    listing = extract_html(b'''<meta name="date" content="2026-10-01"><h1>Published notices</h1><table>
      <tr><td>1 Dec 2025</td><td><a href="/a">First notice</a></td></tr>
      <tr><td>2 Dec 2025</td><td><a href="/b">Second notice</a></td></tr>
      <tr><td><a href="/c">Undated notice</a></td></tr>
      </table>''', 'https://example.org/list')
    assert listing.metadata['claim_grounding'] == {
        'role': 'listing', 'date_scope': 'container',
        'date_basis': 'publication meta tag in https://example.org/list'}
    assert [link.published for link in listing.links] == [date(2025, 12, 1), date(2025, 12, 2), None]


def test_ambiguous_html_date_is_not_assumed_to_date_a_publication():
    page = extract_html(b'<meta name="date" content="2026-10-01"><h1>Guidance</h1><p>Body text.</p>',
                        'https://example.org/guidance')
    assert page.metadata['claim_grounding'] == {
        'role': 'unknown', 'date_scope': 'unknown', 'date_basis': None}


def test_native_api_distinguishes_listing_from_dated_publication():
    from mira.extract import extract_sfc_json
    index = extract_sfc_json(b'{"items": [], "total": 0}',
        'https://apps.sfc.hk/edistributionWeb/api/news/search?year=2026')
    content = extract_sfc_json(b'{"title":"Notice", "html":"<p>Body</p>", "releasedDate":"2026-01-04"}',
        'https://apps.sfc.hk/edistributionWeb/api/news/content?refNo=XX')
    assert index.metadata['claim_grounding'] == {'role': 'listing', 'date_scope': 'container', 'date_basis': None}
    assert content.metadata['claim_grounding'] == {
        'role': 'publication', 'date_scope': 'publication', 'date_basis': 'SFC public API releasedDate'}


def test_native_publication_can_follow_pdf_when_a_slot_remains(monkeypatch):
    from mira.extract import Extracted, Link
    listing = extract_html(b'<table><tr><td>1 Dec 2025</td><td><a href="/one">Money laundering circular</a></td></tr></table>', 'https://example.org/list')
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, source_ids=(), question='money laundering', role='regulatory_scout')
    run = _ScoutRun(scout, None, context(), uuid4(), task)
    run.candidates = listing.links
    run._record_discovery(listing.links, 'https://example.org/list', uuid4())
    fetched = []
    def fetch(url, link=None):
        fetched.append(url)
        run.allowance -= 1
        return Extracted('Circular', 'complete', ['body'], links=[Link('https://example.org/full.pdf', 'Full text', '')] if url.endswith('/one') else [])
    monkeypatch.setattr(run, '_fetch', fetch)
    run._select_and_fetch()
    assert fetched == ['https://example.org/one', 'https://example.org/full.pdf']


def test_future_and_untrusted_dates_do_not_bypass_model_selection(monkeypatch):
    from mira.extract import Link
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    task = SimpleNamespace(max_documents=2, max_llm_tokens=None, source_ids=(), question='money laundering', role='regulatory_scout')
    run = _ScoutRun(scout, None, context(), uuid4(), task)
    future = Link('https://example.org/future', 'Money laundering circular', '', date(2030, 1, 1), 'SFC public publication listing')
    untrusted = Link('https://example.org/snippet', 'Money laundering circular', '', date(2025, 12, 1), 'search snippet')
    hub = Link('https://example.org/hub', 'Money laundering archive', '')
    run.candidates = [future, untrusted, hub]
    run._record_discovery(run.candidates, 'https://example.org/list', uuid4())
    fetched = []
    monkeypatch.setattr(run, '_fetch_document', lambda url, link, **kw: fetched.append(url))
    monkeypatch.setattr(module, 'call_checked', lambda *a, **k: SimpleNamespace(
        output=LinkSelection(link_labels=['L2'], notes=None), tokens_in=0, tokens_out=0, model='test'))
    run._select_and_fetch()
    assert fetched == ['https://example.org/hub']
    assert any(x['reason'] == 'out_of_as_of' for x in run.selection_diagnostics[-1]['filtered'])
    assert not run.selection_diagnostics[-1].get('deterministic_selected')


def test_feed_is_listing_and_item_date_is_not_container_date():
    from mira.extract import extract_feed
    page = extract_feed(b'<rss><channel><title>News</title><item><title>Notice</title><link>https://example.org/item</link><pubDate>Mon, 01 Dec 2025 00:00:00 GMT</pubDate></item></channel></rss>', 'https://example.org/feed')
    assert page.metadata['claim_grounding'] == {'role': 'listing', 'date_scope': 'container', 'date_basis': None}
    assert page.links[0].published == date(2025, 12, 1)


def test_pdf_date_scope_requires_explicit_circular_header(monkeypatch):
    import pypdf
    from mira.extract import extract_pdf
    class Reader:
        metadata = None
        pages = [SimpleNamespace(extract_text=lambda: 'Circular\n1 Dec 2025\nDear Sir\nBody')]
        def __init__(self, _): pass
    monkeypatch.setattr(pypdf, 'PdfReader', Reader)
    dated = extract_pdf(b'', 'https://brdr.hkma.gov.hk/example.pdf')
    other = extract_pdf(b'', 'https://example.org/example.pdf')
    assert dated.metadata['claim_grounding'] == {'role': 'publication', 'date_scope': 'publication', 'date_basis': 'HKMA circular header: 1 Dec 2025'}
    assert other.metadata['claim_grounding'] == {'role': 'publication', 'date_scope': 'unknown', 'date_basis': None}


def test_pdf_inherits_only_its_own_publisher_record_date(monkeypatch):
    from mira.extract import Extracted, Link
    scout = WebScout('unused', None, SimpleNamespace(allow=SimpleNamespace(allows=lambda url: True)))
    run = _ScoutRun(scout, None, context(), uuid4(), SimpleNamespace(max_documents=2, source_ids=()))
    run.writer = SimpleNamespace(save=lambda *args: SimpleNamespace(unchanged=False, document_version_id=uuid4(), passage_ids=[]))
    url = 'https://example.org/one.pdf'
    page = SimpleNamespace(kind='pdf', url=url, requested_url=url)
    basis = 'publication date in enclosing table/list record at https://example.org/list'
    link = Link(url, 'Notice', '', date(2025, 12, 1), basis)
    extracted = Extracted('Notice', 'complete', ['body'], metadata={'claim_grounding': {'role': 'publication', 'date_scope': 'unknown', 'date_basis': None}})
    run._save_page(page, extracted, {}, link)
    assert extracted.metadata['claim_grounding'] == {'role': 'publication', 'date_scope': 'publication', 'date_basis': basis}
    other = Extracted('Notice', 'complete', ['body'], metadata={'claim_grounding': {'role': 'publication', 'date_scope': 'unknown', 'date_basis': None}})
    run._save_page(page, other, {}, Link('https://example.org/other.pdf', 'Other', '', date(2025, 12, 1), basis))
    assert other.metadata['claim_grounding']['date_scope'] == 'unknown'


def test_operative_article_with_dated_related_links_remains_publication():
    article = extract_html(b'''<meta property="article:published_time" content="2026-01-10">
      <article><h1>Risk controls notice</h1><p>Institutions must review their customer risk controls and document their decisions.</p>
      <p>Senior management must approve the resulting remediation plan and review progress regularly.</p></article>
      <section><h2>Related notices</h2><ul><li>1 Dec 2025 <a href="/a">First notice</a></li>
      <li>2 Dec 2025 <a href="/b">Second notice</a></li></ul></section>''', 'https://example.org/article')
    assert article.metadata['claim_grounding'] == {'role': 'publication', 'date_scope': 'publication',
        'date_basis': 'publication meta tag in https://example.org/article'}
    assert 'Institutions must review' in article.text


def test_dated_index_remains_listing_with_introductory_prose():
    index = extract_html(b'''<meta property="article:published_time" content="2026-01-10">
      <h1>Regulatory notices</h1><p>Browse recent notices published by the regulator.</p><ul>
      <li>1 Dec 2025 <a href="/a">First notice</a></li><li>2 Dec 2025 <a href="/b">Second notice</a></li>
      </ul>''', 'https://example.org/index')
    assert index.metadata['claim_grounding']['role'] == 'listing'
    assert index.metadata['claim_grounding']['date_scope'] == 'container'


def test_dated_article_links_without_list_or_table_are_not_listing_proof():
    page = extract_html(b'''<article>1 Dec 2025 <a href="/a">First notice</a></article>
        <article>2 Dec 2025 <a href="/b">Second notice</a></article>''', 'https://example.org/ambiguous')
    assert page.metadata['claim_grounding']['role'] == 'unknown'
    assert page.metadata['claim_grounding']['date_scope'] == 'unknown'


def test_single_operative_paragraph_with_related_dated_links_is_not_listing():
    page = extract_html(b'''<meta property="article:published_time" content="2026-01-10">
      <h1>Risk controls notice</h1><p>Institutions must review customer risk controls and document their decisions.</p>
      <ul><li>1 Dec 2025 <a href="/a">Related notice A</a></li>
      <li>2 Dec 2025 <a href="/b">Related notice B</a></li></ul>''', 'https://example.org/notice')
    assert page.metadata['claim_grounding']['role'] in ('unknown', 'publication')
    assert page.metadata['claim_grounding']['date_scope'] != 'container'


def test_substantive_body_under_plural_title_remains_ambiguous():
    page = extract_html(b'''<meta property="article:published_time" content="2026-01-10"><h1>Regulatory notices</h1>
      <p>The regulator issued a revised framework for customer risk assessment and provided detailed implementation guidance.</p>
      <ul><li>1 Dec 2025 <a href="/a">Related notice A</a></li><li>2 Dec 2025 <a href="/b">Related notice B</a></li></ul>''', 'https://example.org/notice')
    assert page.metadata['claim_grounding']['role'] == 'unknown'


def test_reviewers_original_screening_notice_is_not_listing():
    page = extract_html(b'''<meta property="article:published_time" content="2026-05-01">
      <h1>New screening requirements</h1><p>Banks must screen customers effective 1 June 2026.</p>
      <h2>Related notices</h2><ul><li>1 May 2025 <a href="/a">Earlier notice</a></li>
      <li>2 May 2025 <a href="/b">Other notice</a></li></ul>''', 'https://example.org/notice')
    assert page.metadata['claim_grounding']['role'] == 'unknown'
    assert page.metadata['claim_grounding']['date_scope'] == 'unknown'
