import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from mira.contracts import VerdictDraft
from mira.llm import AnthropicClient, LLMError, LLMOutputError, ModelSpec, ScriptedClient, call_checked, model_for


def test_model_for_reads_provider_and_model():
    assert model_for("regulatory_scout", {"MIRA_MODEL_SCOUT": "anthropic:claude-sonnet-5-5"}) == ModelSpec(
        "anthropic", "claude-sonnet-5-5"
    )
    with pytest.raises(ValueError):
        model_for("planner", {})
    with pytest.raises(ValueError):
        model_for("planner", {"MIRA_MODEL_PLANNER": "claude-opus-5-5"})


def verdict(value="supported"):
    return {"verdict": value, "reason": "test"}


def call(client, check=lambda output: None):
    return call_checked(
        client, role="verifier", system="s", user="u", output_type=VerdictDraft, prompt_version="v/1", check=check
    )


def test_call_checked_retries_once_and_counts_both_attempts():
    client = ScriptedClient({"verifier": [verdict("contradicted"), verdict()]})

    def check(output):
        if output.verdict != "supported":
            raise ValueError("not supported")

    result = call(client, check)
    assert result.output.verdict == "supported"
    assert (result.tokens_in, result.tokens_out) == (200, 100)
    assert "rejected: not supported" in client.calls[1].user


def test_call_checked_gives_up_with_tokens_attached():
    client = ScriptedClient({"verifier": [{"verdict": "maybe"}, {"verdict": "maybe"}]})
    with pytest.raises(LLMOutputError) as caught:
        call(client)
    assert caught.value.tokens_in == 200


def test_call_checked_keeps_tokens_when_a_retry_is_refused():
    client = ScriptedClient({"verifier": [{"verdict": "maybe"}, LLMError("refused", 7, 0)]})
    with pytest.raises(LLMError) as caught:
        call(client)
    assert not isinstance(caught.value, LLMOutputError)
    assert caught.value.tokens_in == 107


class FakeSDK:
    """Stands in for ``anthropic.Anthropic()``: records the request, returns a fixed message."""

    def __init__(self, text, stop_reason="end_turn", model="claude-opus-5-5"):
        self.requests = []
        message = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            stop_reason=stop_reason,
            stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
            model=model,
        )

        @contextmanager
        def stream(**kwargs):
            self.requests.append(kwargs)
            yield SimpleNamespace(get_final_message=lambda: message)

        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=stream))


@pytest.fixture()
def verifier_model(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("MIRA_MODEL_VERIFIER", "anthropic:claude-opus-5-5")


def structured(sdk):
    return AnthropicClient(sdk).structured(
        role="verifier", system="s", user="u", output_type=VerdictDraft, prompt_version="verifier/1"
    )


def test_anthropic_client_requests_json_schema_and_records_served_model(verifier_model):
    sdk = FakeSDK(json.dumps(verdict()), model="claude-opus-5")
    result = structured(sdk)
    assert result.output == VerdictDraft(verdict="supported", reason="test")
    assert (result.model, result.tokens_in, result.tokens_out) == ("claude-opus-5", 11, 7)
    request = sdk.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert request["fallbacks"] == "default"
    assert "temperature" not in request


def test_anthropic_client_raises_on_refusal_and_invalid_output(verifier_model):
    with pytest.raises(LLMError) as refused:
        structured(FakeSDK("", stop_reason="refusal"))
    assert refused.value.tokens_in == 11
    with pytest.raises(LLMOutputError):
        structured(FakeSDK('{"verdict": "maybe", "reason": "x"}'))


class FakeResponseStream:
    def __init__(self, message): self.message = message
    def __iter__(self):
        yield SimpleNamespace(type='response.' + self.message.status, response=self.message)
    def get_final_response(self):
        if self.message.status != 'completed':
            raise RuntimeError("Didn't receive a `response.completed` event.")
        return self.message


class FakeOpenAISDK:
    def __init__(self, text=None, status='completed', refusal=False):
        self.requests = []
        message = SimpleNamespace(
            output=[SimpleNamespace(type='message',content=[SimpleNamespace(type='refusal' if refusal else 'output_text')])],
            output_text=json.dumps(verdict()) if text is None else text,
            usage=SimpleNamespace(input_tokens=13,output_tokens=9),status=status,model='gpt-5.4-mini-2026-03-17')
        @contextmanager
        def stream(**kwargs):
            self.requests.append(kwargs)
            yield FakeResponseStream(message)
        self.responses = SimpleNamespace(stream=stream)


@pytest.fixture()
def openai_sdk():
    pytest.importorskip("openai")


def test_openai_streaming_contract_and_usage(monkeypatch, openai_sdk):
    from mira.llm import OpenAIClient, estimated_cost
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    sdk=FakeOpenAISDK()
    result=call(OpenAIClient(sdk))
    assert result.output == VerdictDraft(**verdict())
    assert (result.tokens_in,result.tokens_out)==(13,9)
    assert result.model=='gpt-5.4-mini-2026-03-17'
    assert estimated_cost(result.model,1_000_000,1_000_000) is None
    request=sdk.requests[0]
    assert request['instructions']=='s' and request['input']==[{'role':'user','content':'u'}]
    assert request['store'] is False and 'tools' not in request
    assert request['text']['format']['strict'] is True
    assert request['text']['format']['schema']['additionalProperties'] is False
    assert request['max_output_tokens']==64000 and request['reasoning']=={'effort':'high'}


@pytest.mark.parametrize('status,refusal',[('incomplete',False),('failed',False),('completed',True)])
def test_openai_terminal_errors_preserve_usage(monkeypatch,status,refusal,openai_sdk):
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    sdk=FakeOpenAISDK(status=status,refusal=refusal)
    with pytest.raises(LLMError) as caught:
        call(OpenAIClient(sdk))
    assert (caught.value.tokens_in,caught.value.tokens_out)==(13,9)
    assert len(sdk.requests)==1


def test_openai_invalid_output_uses_existing_repair_and_token_accounting(monkeypatch,openai_sdk):
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    sdk=FakeOpenAISDK('{"verdict":"maybe","reason":"x"}')
    with pytest.raises(LLMOutputError) as caught:
        call(OpenAIClient(sdk))
    assert (caught.value.tokens_in,caught.value.tokens_out)==(26,18)
    assert 'previous answer was rejected' in sdk.requests[1]['input'][0]['content']


def test_provider_router_supports_mixed_roles_without_unused_credentials(monkeypatch):
    import mira.llm as llm
    monkeypatch.setenv('MIRA_MODEL_ANALYST','anthropic:claude-opus-5-5')
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    clients={}
    def factory(name):
        clients[name]=ScriptedClient({'analyst':[verdict()],'verifier':[verdict(),verdict()]})
        return clients[name]
    monkeypatch.setattr(llm,'AnthropicClient',lambda: factory('anthropic'))
    monkeypatch.setattr(llm,'OpenAIClient',lambda: factory('openai'))
    router=llm.ProviderClient()
    for role in ('verifier','verifier','analyst'):
        router.structured(role=role,system='s',user='u',output_type=VerdictDraft,prompt_version='v/1')
        if role=='verifier': assert set(clients)=={'openai'}
    assert len(clients['openai'].calls)==2
    assert len(clients['anthropic'].calls)==1


@pytest.mark.parametrize("status,error_class,expected_code", [
    (400, "BadRequestError", "provider_request"),
    (503, "InternalServerError", "provider_unavailable"),
])
def test_openai_api_errors_do_not_expose_provider_error_body(monkeypatch,openai_sdk,status,error_class,expected_code):
    import httpx
    import openai
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    def fail(**kwargs):
        raise getattr(openai, error_class)('sensitive request data',
            response=httpx.Response(status, request=httpx.Request('POST','https://api.openai.com/v1/responses')),
            body=None)
    sdk=SimpleNamespace(responses=SimpleNamespace(stream=fail))
    with pytest.raises(LLMError) as caught:
        call(OpenAIClient(sdk))
    assert caught.value.code == expected_code
    assert f'HTTP {status}' in str(caught.value) and 'sensitive' not in str(caught.value)


def test_openai_and_router_liveness():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).parents[1]/'eval'))
    from compare import Measured
    from mira.llm import OpenAIClient,ProviderClient
    client=OpenAIClient(object())
    assert Measured.from_client('single_agent',client,0.5,1.0,2.0).live
    router=ProviderClient()
    assert not Measured.from_client('single_agent',router,0.5,1.0,2.0).live
    router._clients['openai']=client
    assert Measured.from_client('single_agent',router,0.5,1.0,2.0).live
    router._clients['other']=ScriptedClient({})
    assert not Measured.from_client('single_agent',router,0.5,1.0,2.0).live


def test_openai_incomplete_terminal_usage_is_not_lost_by_stream_helper(monkeypatch, openai_sdk):
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    sdk = FakeOpenAISDK(status='incomplete')
    with pytest.raises(LLMError) as caught:
        call(OpenAIClient(sdk))
    assert (caught.value.tokens_in,caught.value.tokens_out) == (13,9)
    assert caught.value.code == 'incomplete_response'


def test_openai_unterminated_stream_fails_closed_without_error_body(monkeypatch, openai_sdk):
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    @contextmanager
    def stream(**kwargs):
        yield iter([SimpleNamespace(type='response.in_progress')])
    sdk = SimpleNamespace(responses=SimpleNamespace(stream=stream))
    with pytest.raises(LLMError) as caught:
        call(OpenAIClient(sdk))
    assert caught.value.code == 'stream_interrupted'
    assert caught.value.tokens_in == caught.value.tokens_out == 0


def test_real_openai_sdk_incomplete_sse_preserves_reported_usage(monkeypatch, openai_sdk):
    import httpx
    from openai import OpenAI
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    response = dict(id='resp_offline',object='response',created_at=1,model='gpt-5.4-mini',
        status='incomplete',output=[],incomplete_details={'reason':'max_output_tokens'},
        usage={'input_tokens':31,'output_tokens':19,'total_tokens':50,
               'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':19}})
    events = [dict(type='response.created',sequence_number=0,response={**response,'status':'in_progress'}),
              dict(type='response.incomplete',sequence_number=1,response=response)]
    def serve(request):
        assert request.url.path == '/v1/responses'
        body = ''.join('data: '+json.dumps(event)+'\n\n' for event in events)
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=body.encode())
    with httpx.Client(transport=httpx.MockTransport(serve)) as transport:
        sdk=OpenAI(api_key='offline-fixture-only',http_client=transport,max_retries=0)
        with pytest.raises(LLMError) as caught:
            call(OpenAIClient(sdk))
    assert (caught.value.tokens_in,caught.value.tokens_out)==(31,19)
    assert caught.value.code=='output_limit'


@pytest.mark.parametrize('status',['completed','failed'])
def test_real_openai_sdk_other_terminal_events(monkeypatch, openai_sdk, status):
    import httpx
    from openai import OpenAI
    from mira.llm import OpenAIClient
    monkeypatch.setenv('MIRA_MODEL_VERIFIER','openai:gpt-5.4-mini')
    output=[{'id':'msg_fixture','type':'message','status':'completed','role':'assistant',
             'content':[{'type':'output_text','text':json.dumps(verdict()),'annotations':[],'logprobs':[]}]}]
    response=dict(id='resp_offline',object='response',created_at=1,model='gpt-5.4-mini',
        status=status,output=output if status=='completed' else [],error=None,
        usage={'input_tokens':31,'output_tokens':19,'total_tokens':50,
               'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}})
    events=[dict(type='response.created',sequence_number=0,response={**response,'status':'in_progress','output':[]}),
            dict(type='response.'+status,sequence_number=1,response=response)]
    def serve(request):
        return httpx.Response(200,headers={'content-type':'text/event-stream'},
            content=''.join('data: '+json.dumps(event)+'\n\n' for event in events).encode())
    with httpx.Client(transport=httpx.MockTransport(serve)) as transport:
        client=OpenAIClient(OpenAI(api_key='offline-fixture-only',http_client=transport,max_retries=0))
        if status=='completed':
            result=call(client)
            assert result.output==VerdictDraft(**verdict())
            assert (result.tokens_in,result.tokens_out)==(31,19)
        else:
            with pytest.raises(LLMError) as caught:call(client)
            assert caught.value.code=='provider_response_failed'
            assert (caught.value.tokens_in,caught.value.tokens_out)==(31,19)
