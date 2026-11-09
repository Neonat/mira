from types import SimpleNamespace
import subprocess

import pytest

from mira.contracts import LinkSelection
from mira.llm import LLMError,ProviderClient,call_checked


def test_bounded_decline_before_launch_does_not_claim_spend():
    with pytest.raises(LLMError) as e:
        ProviderClient().structured_bounded(role='regulatory_scout',system='x',user='y',output_type=LinkSelection,prompt_version='test',timeout_seconds=0,max_output_tokens=100)
    assert e.value.request_sent is False and e.value.reserved_tokens==0


def test_unknown_attempt_timeout_has_consistent_reservation(monkeypatch):
    from mira import llm
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired('fixture',1,stderr=b'MIRA_PROVIDER_REQUEST_STARTED\n')
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(LLMError) as e:
        ProviderClient().structured_bounded(role='regulatory_scout',system='x',user='y',output_type=LinkSelection,prompt_version='test',timeout_seconds=1,max_output_tokens=100)
    assert e.value.request_sent is True
    assert e.value.reserved_tokens==llm.request_token_reservation(system='x',user='y',output_type=LinkSelection,max_output_tokens=100)


def test_local_child_failure_is_not_an_unknown_provider_charge(monkeypatch):
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=b'{"error":true,"error_code":"unknown","tokens_in":0,"tokens_out":0,"request_sent":false}'))
    with pytest.raises(LLMError) as e:
        ProviderClient().structured_bounded(role='regulatory_scout',system='x',user='y',output_type=LinkSelection,prompt_version='test',timeout_seconds=1,max_output_tokens=100)
    assert e.value.request_sent is False and e.value.reserved_tokens==0


def test_call_checked_preserves_unknown_reservation_and_admission_status():
    error=LLMError('unknown',3,4,request_sent=True,reserved_tokens=123)
    def fail(**kwargs):raise error
    with pytest.raises(LLMError) as e:
        call_checked(SimpleNamespace(structured=fail),role='regulatory_scout',system='x',user='y',output_type=LinkSelection,prompt_version='test',check=lambda x:None)
    assert (e.value.tokens_in,e.value.tokens_out,e.value.reserved_tokens,e.value.request_sent)==(3,4,123,True)


def test_output_error_unknown_spend_is_not_dropped_by_retry():
    from mira.llm import LLMOutputError
    count=[]
    def fail(**kw):count.append(1);raise LLMOutputError('unknown usage',request_sent=True,reserved_tokens=77)
    with pytest.raises(LLMError) as e:call_checked(SimpleNamespace(structured=fail),role='writer',system='x',user='y',output_type=LinkSelection,prompt_version='test',check=lambda x:None)
    assert e.value.reserved_tokens==77 and len(count)==1
