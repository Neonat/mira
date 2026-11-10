import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field

from mira.llm import LLMOutputError, ProviderClient, ScriptedClient, call_checked


class Item(BaseModel):
    count: int = Field(gt=0)


class Output(BaseModel):
    items: list[Item]
    mapping: dict[str, int]


def invoke(client, attempts=2):
    return call_checked(client, role='analyst', system='system', user='user', output_type=Output,
                        prompt_version='v1', check=lambda _: None, attempts=attempts)


def test_validation_issues_are_safe_and_used_for_retry():
    client = ScriptedClient({'analyst': [
        {'items': [{'count': 'secret-value'}], 'mapping': {'secret-key': 'secret-value'}},
        {'items': [{'count': 1}], 'mapping': {}},
    ]})
    result = invoke(client)
    prompt = client.calls[1].user
    assert result.tokens_in == 200
    assert '$.items[0].count:int_parsing' in prompt
    assert '$.mapping:int_parsing' in prompt
    assert 'secret' not in prompt


def test_terminal_error_preserves_issues_and_usage():
    client = ScriptedClient({'analyst': [
        {'items': [{'count': 0}], 'mapping': {}},
        {'items': [{'count': 0}], 'mapping': {}},
    ]})
    with pytest.raises(LLMOutputError) as caught:
        invoke(client)
    assert caught.value.validation_issues == ('$.items[0].count:greater_than',)
    assert (caught.value.tokens_in, caught.value.tokens_out) == (200, 100)


def test_unknown_usage_reserve_stops_retry_and_preserves_issues():
    error = LLMOutputError('invalid', request_sent=True, reserved_tokens=300,
                           validation_issues=('$.items[0].count:int_parsing',))
    client = ScriptedClient({'analyst': [error]})
    with pytest.raises(LLMOutputError) as caught:
        invoke(client)
    assert caught.value.validation_issues == error.validation_issues
    assert caught.value.reserved_tokens == 300
    assert caught.value.request_sent is True
    assert len(client.calls) == 1


def test_bounded_transport_revalidates_child_diagnostics(monkeypatch):
    monkeypatch.setenv('MIRA_MODEL_ANALYST', 'openai:fake')
    payload = {'error': True, 'error_code': 'output_validation', 'tokens_in': 10, 'tokens_out': 20,
               'request_sent': True, 'validation_issues': ['$.items[0].count:int_parsing',
               '$.mapping.secret-key:int_parsing', '$.items[0].count:secret', 123]}
    with patch('subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(payload).encode())):
        with pytest.raises(LLMOutputError) as caught:
            ProviderClient().structured_bounded(role='analyst', system='', user='', output_type=Output,
                prompt_version='v1', timeout_seconds=1, max_output_tokens=10)
    assert caught.value.validation_issues == ('$.items[0].count:int_parsing',)
    assert 'secret' not in str(caught.value)


def test_child_emits_only_safe_validation_diagnostics(monkeypatch, capsys):
    import io
    import sys
    import mira.llm as llm

    class FakeProvider:
        def __init__(self, **kwargs):
            self._client = self

        def with_options(self, **kwargs):
            return self

        def structured(self, **kwargs):
            raise LLMOutputError('secret-value', 3, 4, validation_issues=(
                '$.items[0].count:int_parsing', '$.mapping.secret-key:int_parsing'))

    monkeypatch.setenv('MIRA_MODEL_ANALYST', 'openai:fake')
    monkeypatch.setattr(llm, 'OpenAIClient', FakeProvider)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({
        'output_module': __name__, 'output_name': 'Output', 'role': 'analyst',
        'max_output_tokens': 100, 'timeout_seconds': 1, 'system': '', 'user': '', 'prompt_version': 'v1',
    })))
    llm._bounded_child()
    result = json.loads(capsys.readouterr().out)
    assert result['validation_issues'] == ['$.items[0].count:int_parsing']
    assert 'secret' not in json.dumps(result)
    assert (result['tokens_in'], result['tokens_out']) == (3, 4)


def test_json_syntax_and_issue_count_are_bounded():
    from pydantic import ValidationError
    from mira.llm import _validation_issues

    with pytest.raises(ValidationError) as invalid_json:
        Output.model_validate_json('secret-invalid-json')
    assert _validation_issues(invalid_json.value, Output) == ('$:json_invalid',)
    with pytest.raises(ValidationError) as many:
        Output.model_validate({'items': [{'count': 'secret'} for _ in range(20)], 'mapping': {}})
    issues = _validation_issues(many.value, Output)
    assert len(issues) == 8
    assert all('secret' not in issue for issue in issues)


def test_terminal_aggregation_keeps_issues_from_each_attempt():
    client = ScriptedClient({'analyst': [
        {'items': [{'count': 0}], 'mapping': {}},
        {'items': [{'count': 'secret'}], 'mapping': {}},
    ]})
    with pytest.raises(LLMOutputError) as caught:
        invoke(client)
    assert caught.value.validation_issues == ('$.items[0].count:greater_than', '$.items[0].count:int_parsing')


def test_safe_schema_diagnosis_survives_later_local_refusal():
    from mira.llm import LLMError,LLMOutputError,ScriptedClient,call_checked
    from mira.contracts import VerdictDraft
    client=ScriptedClient({'verifier':[LLMOutputError('invalid',2,3,
        validation_issues=('$.verdict:literal_error',)),LLMError('deadline',request_sent=False)]})
    with pytest.raises(LLMError) as error:
        call_checked(client,role='verifier',system='s',user='u',output_type=VerdictDraft,
                     prompt_version='v',check=lambda output:None)
    assert error.value.validation_issues==('$.verdict:literal_error',)
    assert '$.verdict:literal_error' in str(error.value)
    assert (error.value.tokens_in,error.value.tokens_out)==(2,3)

