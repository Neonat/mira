"""Structured model calls for every agent role (PRD v2 §5.1, §5.4).

Each role asks for one contract from ``mira.contracts`` and gets back a validated
instance plus token usage. The output is re-validated with Pydantic after the
call, so constraints the provider schema cannot express (``pattern``, numeric
limits, model validators) are still enforced in Python.

Models are chosen per role from ``MIRA_MODEL_<ROLE>`` as ``provider:model``.
Only the ``anthropic`` provider is implemented; ``openai`` is reserved for the
independent verifier (§5.4) once a key is available.

``ScriptedClient`` replays fixed outputs for tests and offline runs.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from mira.contracts import AgentRole

T = TypeVar("T", bound=BaseModel)

ROLE_MODEL_ENV: dict[str, str] = {
    "planner": "MIRA_MODEL_PLANNER",
    "regulatory_scout": "MIRA_MODEL_SCOUT",
    "industry_scout": "MIRA_MODEL_SCOUT",
    "analyst": "MIRA_MODEL_ANALYST",
    "verifier": "MIRA_MODEL_VERIFIER",
    "writer": "MIRA_MODEL_WRITER",
}

# List prices in US dollars per million tokens (input, output), October 2026.
# Used only to estimate run cost for people; check current pricing before relying on it.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def estimated_cost(model: str | None, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = MODEL_PRICES.get(model or "", (0.0, 0.0))
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


# Server-side fallback when the requested model declines for policy reasons. The
# model that actually answered is recorded per step, so a fallback stays visible.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """A model call failed. Carries the tokens spent so budgets stay accurate."""

    def __init__(self, message: str, tokens_in: int = 0, tokens_out: int = 0) -> None:
        super().__init__(message)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


class LLMOutputError(LLMError):
    """The model answered, but not with a valid instance of the requested contract."""


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ModelSpec:
        provider, sep, model = value.partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"model setting {value!r} must look like provider:model")
        return cls(provider, model)


def model_for(role: AgentRole, env: Mapping[str, str] = os.environ) -> ModelSpec:
    """The configured model for ``role``. Raises if the setting is missing."""
    var = ROLE_MODEL_ENV.get(role)
    if var is None:
        raise ValueError(f"no model setting for role {role!r}")
    value = env.get(var)
    if not value:
        raise ValueError(f"{var} is not set (see .env.example)")
    return ModelSpec.parse(value)


@dataclass(frozen=True)
class LLMResult(Generic[T]):
    output: T
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int


class LLMClient(Protocol):
    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]: ...


class AnthropicClient:
    """Anthropic Messages API with structured output. Needs ``pip install -e ".[llm]"``."""

    def __init__(self, client: object | None = None, *, effort: str = "high", max_tokens: int = 64000) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._effort = effort
        self._max_tokens = max_tokens

    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]:
        from anthropic import transform_schema

        spec = model_for(role)
        if spec.provider != "anthropic":
            raise LLMError(f"provider {spec.provider!r} is not implemented yet")
        # Streaming: adaptive thinking shares max_tokens with the answer, so the
        # limit is high enough to hit the non-streaming timeout.
        with self._client.beta.messages.stream(
            model=spec.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": transform_schema(output_type)},
            },
            fallbacks="default",
            betas=[FALLBACK_BETA],
        ) as stream:
            message = stream.get_final_message()
        tokens_in, tokens_out = message.usage.input_tokens, message.usage.output_tokens
        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            raise LLMError(f"{role} call refused (category {category})", tokens_in, tokens_out)
        if message.stop_reason == "max_tokens":
            raise LLMError(f"{role} call hit max_tokens", tokens_in, tokens_out)
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            output = output_type.model_validate_json(text)
        except ValidationError as exc:
            raise LLMOutputError(f"{role} output failed validation: {exc}", tokens_in, tokens_out) from exc
        return LLMResult(output, message.model, prompt_version, tokens_in, tokens_out)


def call_checked(
    client: LLMClient,
    *,
    role: AgentRole,
    system: str,
    user: str,
    output_type: type[T],
    prompt_version: str,
    check: Callable[[T], None],
    attempts: int = 2,
) -> LLMResult[T]:
    """Call the model and run ``check`` on the output, re-asking once with the error.

    ``check`` raises ``ValueError`` (including ``UnknownLabelError``) to reject an
    output. Tokens from rejected attempts are included in the result, or in the
    ``LLMOutputError`` raised when every attempt is rejected.
    """
    tokens_in = tokens_out = 0
    prompt = user
    error: Exception | None = None
    for _ in range(attempts):
        try:
            result = client.structured(
                role=role, system=system, user=prompt, output_type=output_type, prompt_version=prompt_version
            )
        except LLMOutputError as exc:
            tokens_in, tokens_out = tokens_in + exc.tokens_in, tokens_out + exc.tokens_out
            error = exc
        except LLMError as exc:
            raise LLMError(str(exc), tokens_in + exc.tokens_in, tokens_out + exc.tokens_out) from exc
        else:
            tokens_in, tokens_out = tokens_in + result.tokens_in, tokens_out + result.tokens_out
            try:
                check(result.output)
            except ValueError as exc:
                error = exc
            else:
                return LLMResult(result.output, result.model, prompt_version, tokens_in, tokens_out)
        prompt = f"{user}\n\nYour previous answer was rejected: {error}\nReturn a corrected answer."
    raise LLMOutputError(f"{role} output rejected after {attempts} attempts: {error}", tokens_in, tokens_out)


@dataclass
class ScriptedCall:
    role: str
    system: str
    user: str
    output_type: type[BaseModel]


@dataclass
class ScriptedClient:
    """Replays queued outputs per role, in order.

    A queued item is a contract instance, a dict validated into the requested
    contract, a callable ``(user_prompt) -> instance | dict``, or an exception to raise.
    """

    responses: dict[str, list[object]]
    tokens_in: int = 100
    tokens_out: int = 50
    model: str = "scripted"
    calls: list[ScriptedCall] = field(default_factory=list)

    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]:
        self.calls.append(ScriptedCall(role, system, user, output_type))
        queue = self.responses.get(role)
        if not queue:
            raise LLMError(f"no scripted response left for {role}")
        item = queue.pop(0)
        if callable(item) and not isinstance(item, BaseModel):
            item = item(user)
        if isinstance(item, Exception):
            raise item
        try:
            output = output_type.model_validate(item.model_dump() if isinstance(item, BaseModel) else item)
        except ValidationError as exc:
            raise LLMOutputError(str(exc), self.tokens_in, self.tokens_out) from exc
        return LLMResult(output, self.model, prompt_version, self.tokens_in, self.tokens_out)
