"""Restrictions must reach real components, without dispatching providers."""
from dataclasses import replace
from uuid import uuid4
from types import SimpleNamespace
import pytest

from mira.research_settings import ResearchSettings
from mira import runner
from mira.store import SourceRecord

def source(country='HK'):
    return SourceRecord(uuid4(),'test','regulator','https://example.gov',country,('fetch','store_text'))

def test_selected_sources_refuse_missing_or_outside_country():
    from mira.research_settings import restrict_sources
    hk,au=source(),source('AU')
    assert restrict_sources([hk,au],ResearchSettings(source_ids=(str(hk.id),)),['HK'])==[hk]
    for selected in (au.id,uuid4()):
        with pytest.raises(ValueError,match='source'):
            restrict_sources([hk,au],ResearchSettings(source_ids=(str(selected),)),['HK'])

def test_acquisition_switches_do_not_reuse_operator_keys(monkeypatch):
    monkeypatch.setenv('MIRA_ENABLE_EXA_DISCOVERY','1')
    monkeypatch.setenv('EXA_API_KEY','operator-key')
    assert runner.discovery_from_env([source()],settings=ResearchSettings(),api_keys={}) is None
    with pytest.raises(ValueError,match='credential'):
        runner.discovery_from_env([source()],settings=ResearchSettings(enable_exa=True),api_keys={})
    found=runner.discovery_from_env([source()],settings=ResearchSettings(enable_exa=True),api_keys={'exa':'request-key'})
    assert found.search._key=='request-key'

def test_browser_and_hybrid_switches_restrict_operator_capabilities(monkeypatch):
    monkeypatch.setenv('MIRA_ENABLE_OFFLINE_BROWSER','1')
    monkeypatch.setenv('MIRA_ENABLE_LIVE_BROWSER','1')
    monkeypatch.setenv('MIRA_ENABLE_HYBRID_RETRIEVAL','1')
    assert runner.browser_from_env(settings=ResearchSettings()) is None
    assert runner.live_browser_from_env(None,settings=ResearchSettings()) is None
    assert runner.hybrid_from_env(settings=ResearchSettings()) is None
    monkeypatch.delenv('MIRA_ENABLE_HYBRID_RETRIEVAL')
    with pytest.raises(ValueError,match='operator'):
        runner.hybrid_from_env(settings=ResearchSettings(retrieval='hybrid'),api_keys={})

def test_depth_reaches_actual_orchestrator(monkeypatch):
    class Store:
        def __init__(self,conn):pass
        def list_sources(self,w):return [source()]
    monkeypatch.setattr(runner,'PostgresStore',Store)
    monkeypatch.setattr(runner,'hybrid_from_env',lambda *a,**k:None)
    ctx=SimpleNamespace(brief=SimpleNamespace(jurisdictions=['HK']))
    result=runner.build_orchestrator(None,'unused',uuid4(),object(),
         settings=ResearchSettings(max_analysis_batches=2),ctx=ctx)
    assert result.analysis_limits.max_batches==2

def test_historical_usage_cost_is_unknown_without_current_quote(monkeypatch):
    class Conn:
        def execute(self,*args):return self
        def fetchall(self):return [{'role':'planner','model':'gpt-5.4','steps':1,'tokens_in':50,'tokens_out':10}]
    assert runner.usage_by_role(Conn(),uuid4())[0]['cost_usd'] is None
