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
