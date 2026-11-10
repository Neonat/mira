"""Bounded analysis repairs schema/label failures without exceeding its budget."""
from types import SimpleNamespace

import pytest

from mira.agents import analyst
from mira.llm import LLMError,LLMOutputError,LLMResult,ScriptedClient
from test_orchestrator import BRIEF,PASSAGES,analyst_output,claim


def bounded(client,**options):
    return analyst.analyse(client,BRIEF,[PASSAGES[0]],timeout_seconds=180,
                           max_output_tokens=16384,**options)


def test_bounded_schema_failure_repairs_once_and_charges_both_attempts():
    client=ScriptedClient({'analyst':[LLMOutputError('schema validation',11,7),{'claims':[]}]})
    result=bounded(client)
    assert len(client.calls)==2
    assert (result.llm.tokens_in,result.llm.tokens_out)==(111,57)
    assert 'rejected' in client.calls[1].user


def test_bounded_unknown_label_is_repaired_without_accepting_the_bad_claim():
    invalid=analyst_output(claim('C1','external_fact','P99','invented'))
    client=ScriptedClient({'analyst':[invalid,{'claims':[]}]})
    assert bounded(client).claims==[]
    assert len(client.calls)==2


def test_repair_does_not_restart_deadline_or_exceed_two_calls(monkeypatch):
    now=[0.];seen=[]
    monkeypatch.setattr(analyst,'time',SimpleNamespace(monotonic=lambda:now[0]))
    class Provider:
        def structured_bounded(self,**kwargs):
            seen.append(kwargs['timeout_seconds'])
            if len(seen)==1:
                now[0]=100
                raise LLMOutputError('schema',2,3)
            return LLMResult(kwargs['output_type'](claims=[]),'unchanged','v',4,5)
    result=bounded(Provider())
    assert seen==[180,80] and result.llm.tokens_in==6


def test_unfunded_repair_is_local_and_keeps_prior_known_usage():
    client=ScriptedClient({'analyst':[LLMOutputError('schema',1000,500),{'claims':[]}]})
    first=analyst.request_reservation(BRIEF,[PASSAGES[0]],16384)
    with pytest.raises(LLMError) as e:bounded(client,max_total_tokens=first)
    assert len(client.calls)==1 and e.value.request_sent is False
    assert (e.value.tokens_in,e.value.tokens_out)==(1000,500)
    assert e.value.reserved_tokens==0


def test_unknown_usage_is_not_retried_or_lost():
    client=ScriptedClient({'analyst':[LLMOutputError('unknown',request_sent=True,reserved_tokens=300),{'claims':[]}]})
    with pytest.raises(LLMError) as e:bounded(client)
    assert len(client.calls)==1 and e.value.reserved_tokens==300


def test_unknown_second_attempt_retains_reservation_and_first_known_usage():
    client=ScriptedClient({'analyst':[LLMOutputError('schema',2,3),LLMOutputError('unknown',request_sent=True)]})
    with pytest.raises(LLMError) as e:bounded(client)
    assert len(client.calls)==2 and e.value.reserved_tokens>0
    assert (e.value.tokens_in,e.value.tokens_out)==(2,3)


def test_persistent_invalid_output_fails_closed_after_two_attempts():
    client=ScriptedClient({'analyst':[LLMOutputError('schema',2,3)]*2})
    with pytest.raises(LLMOutputError) as e:bounded(client)
    assert len(client.calls)==2 and (e.value.tokens_in,e.value.tokens_out)==(4,6)


def test_expired_correction_is_not_sent_and_preserves_safe_diagnosis(monkeypatch):
    now=[0.];calls=[]
    monkeypatch.setattr(analyst,'time',SimpleNamespace(monotonic=lambda:now[0]))
    class Provider:
        def structured_bounded(self,**kwargs):
            calls.append(kwargs)
            now[0]=181
            raise LLMOutputError('schema',2,3,validation_issues=('$.claims:list_type',))
    with pytest.raises(LLMError) as error:
        bounded(Provider())
    assert len(calls)==1 and error.value.request_sent is False
    assert (error.value.tokens_in,error.value.tokens_out)==(2,3)
    assert error.value.validation_issues==('$.claims:list_type',)
