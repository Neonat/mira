from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from mira.agents.scout import _ScoutRun
from mira.extract import Extracted, Link
from mira.fetch import FetchedPage
from mira.store import SourceRecord

STEM='https://www.legislation.gov.au/C2006A00169/2026-07-01/2026-07-01/text/original/'


def run_fixture():
    run=_ScoutRun.__new__(_ScoutRun)
    source=SourceRecord(uuid4(),'Register','regulator','https://www.legislation.gov.au','AU',('fetch','store_text'),{'acquisition_profile':'register_api_files'})
    run.scout=SimpleNamespace(fetcher=SimpleNamespace(allow=SimpleNamespace(allows=lambda url:True)))
    run.allowance=3;run.candidates=[];run.seen=set();run.log=[];run.visits=[]
    run._record_discovery=lambda *args:None
    return run,source


def test_registration_overrides_compilation_date_and_keeps_both():
    run,source=run_fixture()
    page=FetchedPage(STEM+'pdf',STEM+'pdf',source,'pdf','application/pdf',b'pdf',datetime.now(UTC))
    ex=Extracted('Act','complete',['Text'],published=date(2026,7,1),published_basis='Compilation date')
    link=Link(page.url,'Act','',date(2026,7,10),'Federal Register API registeredAt in official API')
    run.writer=SimpleNamespace(save=lambda *args,**kw:SimpleNamespace(unchanged=False,document_version_id=uuid4(),passage_ids=[]))
    run._save_page(page,ex,{},link)
    assert ex.published==date(2026,7,10)
    assert ex.metadata['publication']['start']=='2026-07-01'
    assert ex.metadata['publication']['registered_at']=='2026-07-10'
    assert ex.metadata['publication']['representation']=='pdf'


def test_known_australian_files_use_html_then_pdf_without_browser_or_viewer():
    run,source=run_fixture()
    html=Link(STEM+'epub/OEBPS/document_1/document_1.html','Act HTML','',date(2026,7,10),'Federal Register API registeredAt in official API')
    pdf=Link(STEM+'pdf','Act PDF','',html.published,html.date_source)
    run.candidates=[html,pdf]
    calls=[]
    def fetch(url,link=None):
        calls.append((url,link.published if link else None));run.allowance-=1;run.seen.add(url)
        return Extracted('Act','complete',['Full text'])
    run._fetch=fetch
    run._fetch_document(pdf.url,pdf)
    assert calls==[(html.url,html.published),(pdf.url,pdf.published)]


def test_australian_dual_acquisition_preserves_reserved_document_allowance():
    run,_=run_fixture();run.allowance=2
    html=Link(STEM+'epub/OEBPS/document_1/document_1.html','HTML','')
    pdf=Link(STEM+'pdf','PDF','');run.candidates=[html,pdf]
    calls=[]
    def fetch(url,link=None):
        calls.append(url);run.allowance-=1;return Extracted('Act','complete',['Text'])
    run._fetch=fetch
    run._fetch_document(pdf.url,pdf,reserved=1)
    assert calls==[pdf.url]


def test_actual_selection_keeps_the_discarded_australian_counterpart(monkeypatch):
    from mira.agents import scout as module
    from mira.agents.scout import WebScout
    from mira.contracts import LinkSelection
    from test_orchestrator import context
    task=SimpleNamespace(max_documents=3,max_llm_tokens=None,source_ids=(),expected_source_ids=(),question='AML Act',role='regulatory_scout')
    scout=WebScout('unused',None,SimpleNamespace(allow=SimpleNamespace(allows=lambda url:True)))
    run=_ScoutRun(scout,None,context(),uuid4(),task)
    html=Link(STEM+'epub/OEBPS/document_1/document_1.html','Act HTML','',date(2026,7,10),'Federal Register API registeredAt in official API')
    pdf=Link(STEM+'pdf','Act PDF','',html.published,html.date_source)
    run.candidates=[html,pdf]
    monkeypatch.setattr(module,'call_checked',lambda *a,**kw:SimpleNamespace(output=LinkSelection(link_labels=['L1'],notes=None),tokens_in=0,tokens_out=0,model='fixture'))
    calls=[]
    def fetch(url,link=None):
        calls.append(url);run.allowance-=1;run.seen.add(url)
        return Extracted('Act','complete',['Full text'])
    run._fetch=fetch
    run._select_and_fetch()
    assert calls==[html.url,pdf.url]
