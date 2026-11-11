import json
import subprocess
from types import SimpleNamespace

import pytest
from mira.contracts import VerdictDraft
from mira.llm import ProviderClient, LLMError, estimated_cost


def args():
    return dict(role='verifier', system='s', user='u', output_type=VerdictDraft,
                prompt_version='v', timeout_seconds=2, max_output_tokens=100)


def test_bounded_clients_isolate_keys_and_models(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'operator-secret')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://bad.invalid')
    seen = []
    def run(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(dict(output={'verdict':'supported','reason':'ok'}, model='m', tokens_in=1, tokens_out=1)).encode())
    monkeypatch.setattr(subprocess, 'run', run)
    keys = {'openai':'fake-one'}
    one = ProviderClient(models={'verifier':'openai:first'}, api_keys=keys)
    two = ProviderClient(models={'verifier':'openai:second'}, api_keys={'openai':'fake-two'})
    keys['openai'] = 'mutated'
    one.structured_bounded(**args()); two.structured_bounded(**args())
    for i, expected in enumerate(('fake-one','fake-two')):
        command, kw = seen[i]
        payload = json.loads(kw['input'])
        assert payload['api_keys'] == {'openai': expected}
        assert payload['models']['verifier'] == ('openai:first','openai:second')[i]
        assert expected not in str(command) and 'operator-secret' not in str(kw['env'])
        assert 'OPENAI_BASE_URL' not in kw['env']
    assert one.byok and one.model_settings == {'verifier':'openai:first'}
    one.close()
    assert keys == {'openai':'mutated'}
    with pytest.raises(LLMError) as exc:
        one.structured_bounded(**args())
    assert exc.value.request_sent is False


def test_missing_key_never_starts_child(monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('child started'))
    with pytest.raises(LLMError) as exc:
        ProviderClient(models={'verifier':'openai:model'}, api_keys={}).structured_bounded(**args())
    assert exc.value.request_sent is False and exc.value.reserved_tokens == 0


def test_unquoted_models_are_not_free():
    assert estimated_cost('gpt-5.4', 100, 100) is None
    assert estimated_cost('scripted', 100, 100) == 0


def test_provider_sdk_configuration_and_tier(monkeypatch):
    import openai
    from test_llm import FakeOpenAISDK
    created = []
    def factory(**kwargs):
        sdk = FakeOpenAISDK()
        created.append((kwargs, sdk))
        return sdk
    monkeypatch.setattr(openai, 'OpenAI', factory)
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://bad.invalid')
    a = ProviderClient(models={'verifier':'openai:first'}, api_keys={'openai':'fake-a'})
    b = ProviderClient(models={'verifier':'openai:second'}, api_keys={'openai':'fake-b'})
    kwargs = {k:v for k,v in args().items() if k not in ('timeout_seconds','max_output_tokens')}
    a.structured(**kwargs); b.structured(**kwargs)
    assert [x[0] for x in created] == [dict(api_key='fake-a',base_url='https://api.openai.com/v1'), dict(api_key='fake-b',base_url='https://api.openai.com/v1')]
    assert [x[1].requests[0]['model'] for x in created] == ['first','second']
    assert all(x[1].requests[0]['service_tier'] == 'default' for x in created)


def test_anthropic_byok_disables_fallback(monkeypatch):
    import anthropic
    from test_llm import FakeSDK
    sdk = FakeSDK('{"verdict":"supported","reason":"ok"}')
    created = []
    monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: (created.append(kw), sdk)[1])
    client = ProviderClient(models={'verifier':'anthropic:model'}, api_keys={'anthropic':'fake'})
    client.structured(**{k:v for k,v in args().items() if k not in ('timeout_seconds','max_output_tokens')})
    assert created == [dict(api_key='fake', base_url='https://api.anthropic.com')]
    assert 'fallbacks' not in sdk.requests[0] and 'betas' not in sdk.requests[0]


def test_price_book_requires_known_snapshot_and_uses_quote():
    from decimal import Decimal
    from mira.pricing import PriceBook, TokenRate
    rate = TokenRate('openai', 'gpt-5.4-mini', Decimal('1'), Decimal('2'))
    book = PriceBook({'openai:gpt-5.4-mini':rate}, None, None, 'fixture', ())
    assert estimated_cost('gpt-5.4-mini-2026-03-17', 1000000, 1000000, price_book=book) == 3
    assert estimated_cost('gpt-5.4-mini-2099-01-01', 1000000, 1000000, price_book=book) is None


def test_child_builds_explicit_provider_without_environment_mutation(monkeypatch):
    import io
    import sys
    import mira.llm as llm
    payload = dict(role='verifier',system='s',user='u',prompt_version='v',
                   output_module='mira.contracts',output_name='VerdictDraft',timeout_seconds=2,
                   max_output_tokens=100, models={'verifier':'openai:chosen'},api_keys={'openai':'fake-child'})
    seen = []
    class Client:
        def __init__(self, **kw):
            seen.append(kw)
            self._client = self
        def with_options(self, **kw): return self
        def structured(self, **kw):
            raise LLMError('fake-child must never be printed', request_sent=True)
    monkeypatch.setattr(llm, 'OpenAIClient', Client)
    monkeypatch.setenv('OPENAI_API_KEY', 'operator-secret')
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    output = io.StringIO(); monkeypatch.setattr(sys, 'stdout', output)
    llm._bounded_child()
    assert seen == [dict(max_tokens=100, models={'verifier':'openai:chosen'}, api_key='fake-child', byok=True)]
    assert 'fake-child' not in output.getvalue()
    assert json.loads(output.getvalue())['request_sent'] is True


def test_only_requested_provider_key_goes_to_child(monkeypatch):
    seen = []
    def run(command, **kw):
        seen.append(json.loads(kw['input']))
        return SimpleNamespace(stdout=json.dumps(dict(output={'verdict':'supported','reason':'ok'},model='m',tokens_in=1,tokens_out=1)).encode())
    monkeypatch.setattr(subprocess, 'run', run)
    ProviderClient(models={'verifier':'openai:m'}, api_keys={'openai':'fake-a','anthropic':'fake-b'}).structured_bounded(**args())
    assert seen[0]['api_keys'] == {'openai':'fake-a'}
