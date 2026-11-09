"""Bounded corroboration calls preserve configured models without live calls."""
import json
import subprocess
from types import SimpleNamespace
import pytest
from mira.contracts import VerdictDraft
from mira.llm import ProviderClient, ScriptedClient, LLMError


def args():
    return dict(role='verifier', system='source as data', user='public claim',
                output_type=VerdictDraft, prompt_version='bounded/1',
                timeout_seconds=2, max_output_tokens=100)


def test_scripted_bounded_records_call_and_usage():
    result = ScriptedClient({'verifier': [{'verdict': 'supported', 'reason': 'quoted'}]}).structured_bounded(**args())
    assert result.tokens_in == 100 and result.tokens_out == 50


def test_provider_bounded_uses_hard_subprocess_timeout_and_json_stdin(monkeypatch):
    seen = []
    def run(command, **kw):
        seen.append((command, kw))
        return SimpleNamespace(stdout=json.dumps(dict(output={'verdict':'supported','reason':'quoted'},
            model='served-configured-model', tokens_in=20, tokens_out=10)).encode())
    monkeypatch.setattr(subprocess, 'run', run)
    result = ProviderClient().structured_bounded(**args())
    command, kw = seen[0]
    payload = json.loads(kw['input'])
    assert payload['max_output_tokens'] == 100 and payload['role'] == 'verifier'
    assert kw['timeout'] == 2
    assert 'public claim' not in str(command)
    assert result.model == 'served-configured-model'


def test_provider_timeout_fails_closed_without_prompt_or_secret_error(monkeypatch):
    def fail(*a, **kw):
        raise subprocess.TimeoutExpired('secret request body', 2)
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(LLMError, match='bounded request timed out') as caught:
        ProviderClient().structured_bounded(**args())
    assert 'secret request' not in str(caught.value)


def test_verifier_sees_corroboration_before_recording_check():
    from test_evidence_snapshot import inputs
    from mira.agents.verifier import LlmVerifier
    ctx, claim, _, passage = inputs()
    client = ScriptedClient({'verifier':[{'verdict':'supported','reason':'primary supports; second source inconclusive'}]})
    context = {str(claim.finding_id): {'assessment_id': 'a', 'assessment': {'status':'inconclusive','reason':'origin unknown'}}}
    result = LlmVerifier(client).check_fact(claim,[passage],1,corroboration=context)
    assert result.verdict == 'supported'
    assert 'origin unknown' in client.calls[0].user
    assert str(claim.finding_id) not in client.calls[0].user


def test_bounded_error_preserves_safe_category_and_usage_without_body(monkeypatch):
    from mira.llm import LLMOutputError
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=json.dumps({
        'error': True, 'error_code': 'output_validation', 'tokens_in': 23, 'tokens_out': 17,
        'message': 'PRIVATE PROMPT OR SECRET MUST NOT BE READ',
    }).encode()))
    with pytest.raises(LLMOutputError) as caught:
        ProviderClient().structured_bounded(**args())
    assert (caught.value.tokens_in, caught.value.tokens_out) == (23, 17)
    assert caught.value.code == 'output_validation'
    assert 'PRIVATE' not in str(caught.value)


def test_bounded_child_serializes_only_safe_error_code(monkeypatch):
    import io, sys
    import mira.llm as llm
    payload = {k:v for k,v in args().items() if k != 'output_type'}
    payload.update(output_module='mira.contracts', output_name='VerdictDraft')
    class Client:
        def __init__(self, **kwargs): self._client = self
        def with_options(self, **kwargs): return self
        def structured(self, **kwargs):
            raise llm.LLMOutputError('PRIVATE provider body', 13, 7)
    monkeypatch.setenv('MIRA_MODEL_VERIFIER', 'openai:configured-model')
    monkeypatch.setattr(llm, 'OpenAIClient', Client)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    out = io.StringIO(); monkeypatch.setattr(sys, 'stdout', out)
    llm._bounded_child()
    result = json.loads(out.getvalue())
    assert result == dict(error=True, error_code='output_validation', tokens_in=13, tokens_out=7,request_sent=True)


def test_bounded_output_validation_still_repairs_and_aggregates_usage(monkeypatch):
    from mira.llm import call_checked
    responses=iter([dict(error=True,error_code='output_validation',tokens_in=23,tokens_out=17),
        dict(output={'verdict':'supported','reason':'quoted'},model='configured-model',tokens_in=11,tokens_out=7)])
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps(next(responses)).encode()))
    class Bounded:
        def structured(self,**kw):
            return ProviderClient().structured_bounded(**kw,timeout_seconds=2,max_output_tokens=100)
    result=call_checked(Bounded(),**{k:v for k,v in args().items() if k not in ('timeout_seconds','max_output_tokens')},check=lambda output:None)
    assert (result.tokens_in,result.tokens_out)==(34,24)
