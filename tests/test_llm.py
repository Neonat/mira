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
