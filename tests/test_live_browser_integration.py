"""Real acquisition adapter integration: separate attempts, permissions and frozen evidence."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
import pytest
from mira.agents.scout import WebScout, _ScoutRun
from mira.fetch import AllowList, FetchFailed, FetchRefused, FetchedPage
from test_fetch_extract import HKMA
from test_orchestrator import context


def source():
    return replace(HKMA,connector_config={**HKMA.connector_config,'allow_live_browser':True,
        'browser_access_approval':{'reference':'Fixture-only browser permission','allow_http_block_fallback':True}})


def scout_run(*, allowance=2, approved=True, status=403):
    current=source() if approved else HKMA
    def failed(url, **kwargs):
        exc=FetchFailed(f'HTTP {status}');exc.status_code=status
        raise exc
    fetcher=SimpleNamespace(allow=AllowList([current]),fetch=failed)
    calls=[]
    class Browser:
        def acquire(self,url,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(page=FetchedPage(url,url,current,'html','text/html',
                b'<main><h1>Browser publication</h1><p>Public browser-acquired AML evidence.</p></main>',datetime.now(UTC)),
                provenance={'acquisition_method':'live_browser','browser_context':{'javascript_enabled':True,'approval_reference':'Fixture-only browser permission'}})
    web=WebScout('unused',None,fetcher,live_browser=Browser())
    run=_ScoutRun(web,None,context(),uuid4(),SimpleNamespace(max_documents=allowance,source_ids=(current.id,)))
    run.store=SimpleNamespace(list_sources=lambda ws:[current])
    saved=[]
    run.writer=SimpleNamespace(save=lambda page,extracted,provenance,**kwargs:saved.append((page,extracted,provenance)) or
        SimpleNamespace(unchanged=False,document_version_id=uuid4(),passage_ids=[]))
    return run,calls,saved


def test_http_failure_and_live_browser_are_separate_saved_attempts():
    run,calls,saved=scout_run()
    result=run._fetch_new('https://www.hkma.gov.hk/fixture')
    assert result and 'browser-acquired' in result.text
    assert [item.outcome for item in run.log]==['failed','saved']
    assert [item.acquisition_method for item in run.log]==['http_fetch','live_browser']
    assert run.allowance==0 and len(calls)==len(saved)==1
    assert saved[0][2]['acquisition_method']=='live_browser'


@pytest.mark.parametrize('settings',[{'approved':False},{'allowance':1},{'status':429}])
def test_no_grant_no_slot_or_rate_limit_never_uses_browser(settings):
    run,calls,saved=scout_run(**settings)
    assert run._fetch_new('https://www.hkma.gov.hk/fixture') is None
    assert not calls and not saved
    assert len(run.log)==1


def test_robots_refusal_never_triggers_browser():
    run,calls,saved=scout_run()
    run.scout.fetcher.fetch=lambda *a,**kw:(_ for _ in ()).throw(FetchRefused('robots denied'))
    assert run._fetch_new('https://www.hkma.gov.hk/fixture') is None
    assert not calls and not saved and run.allowance==2


def test_live_browser_runtime_requires_global_enable(monkeypatch):
    from mira.runner import live_browser_from_env
    from mira.fetch import Fetcher
    fetcher=Fetcher(AllowList([source()]))
    monkeypatch.delenv('MIRA_ENABLE_LIVE_BROWSER',raising=False)
    assert live_browser_from_env(fetcher) is None
    monkeypatch.setenv('MIRA_ENABLE_LIVE_BROWSER','1')
    assert live_browser_from_env(fetcher) is not None


from test_pipeline_db import DSN, conn, workspace


@pytest.mark.skipif(not DSN,reason='MIRA_TEST_DATABASE_URL not set')
def test_http_block_browser_evidence_is_verified_and_frozen(conn,workspace,tmp_path,monkeypatch):
    from functools import partial
    from psycopg.types.json import Jsonb
    import test_pipeline_db as fixtures
    from mira.contracts import ReportSnapshot
    from mira.render import render_signed_off
    from test_evidence_integrity_db import sign_off
    ws,user=workspace
    conn.execute("update public.sources set connector_config=connector_config || %s where workspace_id=%s and source_key='hkma'",
                 (Jsonb({'allow_live_browser':True,'browser_access_approval':{'reference':'Fixture-only browser permission','allow_http_block_fallback':True}}),ws))
    target='https://brdr.hkma.gov.hk/eng/doc-ldg/current/TEST-1'
    original=fixtures.PAGES[target]
    from mira.fetch import RawResponse
    monkeypatch.setitem(fixtures.PAGES,target,RawResponse(403,fixtures.HTML,b'HTTP client unavailable'))
    class Browser:
        def acquire(self,url,*,sources,**kwargs):
            assert url==target
            current=next(s for s in sources if s.name=='HKMA')
            return SimpleNamespace(page=FetchedPage(url,url,current,'html','text/html',original.body,datetime.now(UTC)),
                provenance={'acquisition_method':'live_browser','javascript_enabled':True,'browser_engine':'chromium',
                    'approval_reference':'Fixture-only browser permission','actions':[{'type':'click','selector':'#publications'}],
                    'initial_navigation_response_sha256':'a'*64,'final_navigation_response_sha256':None,
                    'denied_requests':[],'original_retained':False})
    monkeypatch.setattr(fixtures,'WebScout',partial(WebScout,max_rounds=1,live_browser=Browser()))
    ctx,outcome=fixtures.run_hk(conn,workspace,tmp_path,fixtures.analyst)
    assert outcome.status=='draft',outcome.reasons
    row=conn.execute('select metadata from public.document_versions where workspace_id=%s and source_url=%s',(ws,target)).fetchone()
    assert row['metadata']['acquisition_method']=='live_browser'
    assert row['metadata']['browser_context']['approval_reference']=='Fixture-only browser permission'
    fixtures.review_all_findings(conn,ctx,user)
    signed=sign_off(conn,ctx)
    snapshot=ReportSnapshot.model_validate(signed['evidence_snapshot'])
    frozen=next(p for p in snapshot.evidence_bundle.passages.values() if p.source_url==target)
    assert frozen.acquisition_provenance['browser_context']['javascript_enabled'] is True
    html=render_signed_off(snapshot,generated_at=signed['generated_at'])
    assert 'Fixture-only browser permission' in html
    conn.execute("update public.document_versions set metadata='{}'::jsonb where workspace_id=%s",(ws,))
    assert render_signed_off(snapshot,generated_at=signed['generated_at'])==html


@pytest.mark.skipif(not DSN,reason='MIRA_TEST_DATABASE_URL not set')
@pytest.mark.parametrize("revoke",[False,True])
def test_corroboration_fallback_counts_both_attempts_and_keeps_http_failure(conn,workspace,monkeypatch,revoke):
    from psycopg.types.json import Jsonb
    from mira.corroboration_acquisition import AcquisitionRefused,CorroborationDiscovery
    from mira.pg_store import PostgresStore
    from mira.extract import Link
    ws,user=workspace
    config={'allow_live_browser':True,'browser_access_approval':{'reference':'Fixture-only browser permission','allow_http_block_fallback':True}}
    conn.execute("update public.sources set connector_config=connector_config || %s where workspace_id=%s and source_key='hkma'",(Jsonb(config),ws))
    current=next(s for s in PostgresStore(conn).list_sources(ws) if s.name=='HKMA')
    url='https://www.hkma.gov.hk/live-corroboration-fixture'
    calls=[]
    class Broker:
        def fetch(self,*args,**kwargs):
            raise AcquisitionRefused('FetchFailed',status_code=403,request_sent=True)
    class Browser:
        def acquire(self,url,**kwargs):
            calls.append(kwargs)
            if revoke:
                conn.execute("update public.sources set connector_config=connector_config || %s where workspace_id=%s and id=%s",
                             (Jsonb({'browser_access_approval':{'reference':'Fixture-only browser permission','allow_http_block_fallback':False}}),ws,current.id))
            return SimpleNamespace(page=FetchedPage(url,url,current,'html','text/html',b'<main><p>Live browser corroboration passage.</p></main>',datetime.now(UTC)),
                provenance={'acquisition_method':'live_browser','javascript_enabled':True,'approval_reference':'Fixture-only browser permission'})
    search=SimpleNamespace(with_timeout=lambda _:SimpleNamespace(discover=lambda *a:[Link(url,'','')]))
    adapter=CorroborationDiscovery(conn,[current],search,broker=Broker(),live_browser=Browser())
    ctx=replace(context(),workspace_id=ws,user_id=user)
    first=adapter.discover('fixture',ctx=ctx,source_ids=(current.id,),max_documents=1,max_passages=2,timeout_seconds=5)
    assert first.document_attempts==1 and not first.candidates and not calls
    second=adapter.discover('fixture',ctx=ctx,source_ids=(current.id,),max_documents=2,max_passages=2,timeout_seconds=5)
    assert second.document_attempts==2 and len(calls)==1
    assert any('HTTP acquisition' in error for error in second.errors)
    if revoke:
        assert not second.candidates
        assert conn.execute('select count(*) as n from public.document_versions where workspace_id=%s and source_url=%s',(ws,url)).fetchone()['n']==0
    else:
        assert second.candidates[0].passage.acquisition_provenance['acquisition_method']=='live_browser'


def test_unapproved_live_channel_does_not_suppress_offline_extraction():
    run,calls,saved=scout_run(approved=False)
    page=FetchedPage('https://www.hkma.gov.hk/fixture','https://www.hkma.gov.hk/fixture',HKMA,'html','text/html',b'<script>empty</script>',datetime.now(UTC))
    run.scout.fetcher.fetch=lambda *a,**kw:page
    offline=[]
    run.scout.browser_adapter=SimpleNamespace(capture=lambda page:offline.append(page) or replace(page,body=b'<main>Offline readable evidence.</main>'))
    result=run._fetch_new(page.url)
    assert result and result.text=='Offline readable evidence.'
    assert len(offline)==1 and not calls and len(saved)==1


def test_browser_failure_keeps_progress_and_charges_its_attempt():
    run,calls,saved=scout_run()
    def failure(*args,**kwargs):
        exc=TimeoutError('deadline')
        exc.diagnostics=[{'stage':'main_response','status':200}]
        raise exc
    run.scout.live_browser_adapter.acquire=failure
    assert run._fetch_new('https://www.hkma.gov.hk/fixture') is None
    assert run.allowance==0 and [item.outcome for item in run.log]==['failed','failed']
    assert run.log[-1].diagnostics==[{'stage':'main_response','status':200}]


def test_unknown_browser_policy_stops_http_without_claiming_server_block():
    from mira.fetch import Fetcher
    fetcher=Fetcher(AllowList([HKMA]),resolver=lambda host:(_ for _ in ()).throw(AssertionError('must not request')))
    fetcher._state('www.hkma.gov.hk').browser_policy_unknown=True
    with pytest.raises(FetchRefused,match='policy state is unknown'):
        fetcher.fetch('https://www.hkma.gov.hk/fixture')
    assert fetcher._state('www.hkma.gov.hk:443') is fetcher._state('www.hkma.gov.hk')
