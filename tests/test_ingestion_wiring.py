"""No credential alone enables optional paid URL discovery."""
from dataclasses import replace
from mira.runner import discovery_from_env
from test_fetch_extract import HKMA


def test_discovery_requires_explicit_enable_and_key(monkeypatch):
    monkeypatch.delenv('MIRA_ENABLE_EXA_DISCOVERY', raising=False)
    monkeypatch.setenv('EXA_API_KEY', 'not-a-real-key')
    assert discovery_from_env([HKMA]) is None
    monkeypatch.setenv('MIRA_ENABLE_EXA_DISCOVERY', '1')
    monkeypatch.delenv('EXA_API_KEY')
    assert discovery_from_env([HKMA]) is None
    monkeypatch.setenv('EXA_API_KEY', 'not-a-real-key')
    adapter = discovery_from_env([HKMA])
    assert adapter is not None
    assert adapter.search._domains == ['brdr.hkma.gov.hk', 'www.hkma.gov.hk']
    denied = replace(HKMA, permitted_operations=('metadata', 'fetch'))
    assert discovery_from_env([denied]) is None


def test_offline_browser_requires_explicit_enable(monkeypatch):
    from mira.runner import browser_from_env
    monkeypatch.delenv('MIRA_ENABLE_OFFLINE_BROWSER', raising=False)
    assert browser_from_env() is None
    monkeypatch.setenv('MIRA_ENABLE_OFFLINE_BROWSER', '1')
    assert browser_from_env() is not None
