"""Structured model calls for every agent role (PRD v2 §5.1, §5.4).

Each role asks for one contract from ``mira.contracts`` and gets back a validated
instance plus token usage. The output is re-validated with Pydantic after the
call, so constraints the provider schema cannot express (``pattern``, numeric
limits, model validators) are still enforced in Python.

Models are chosen per role from ``MIRA_MODEL_<ROLE>`` as ``provider:model``.
Both ``anthropic`` and ``openai`` providers implement the same contract.
``ProviderClient`` routes each role without changing the agent workflow.

``ScriptedClient`` replays fixed outputs for tests and offline runs.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar
from types import MappingProxyType

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

def estimated_cost(model: str | None, tokens_in: int, tokens_out: int, *, price_book=None) -> float | None:
    """Estimate only from an explicitly supplied current price book."""
    if model == "scripted":
        return 0.0
    if not model or price_book is None:
        return None
    provider, sep, name = model.partition(":")
    if not sep:
        name = provider
        provider = "openai" if name.startswith("gpt-") else "anthropic" if name.startswith("claude-") else ""
    snapshots = {"gpt-5.4-mini-2026-03-17": "gpt-5.4-mini",
                 "gpt-5.4-2026-03-05": "gpt-5.4"}
    if provider == "openai":
        name = snapshots.get(name, name)
    try:
        return float(price_book.token_rate(provider, name).cost(tokens_in, tokens_out))
    except (ValueError, KeyError):
        return None


# Server-side fallback when the requested model declines for policy reasons. The
# model that actually answered is recorded per step, so a fallback stays visible.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """A model call failed. Carries the tokens spent so budgets stay accurate."""

    def __init__(self, message: str, tokens_in: int = 0, tokens_out: int = 0, *, code: str = "unknown",
                 request_sent: bool | None = None, reserved_tokens: int = 0,
                 validation_issues: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.code = code
        self.request_sent = request_sent
        self.reserved_tokens = reserved_tokens
        self.validation_issues = validation_issues


def request_token_reservation(*, system: str, user: str, output_type: type,
                              max_output_tokens: int) -> int:
    """One conservative UTF-8/schema/output allowance, shared by every caller."""
    import json
    return len((system + user + json.dumps(output_type.model_json_schema())).encode('utf-8')) + 1024 + max_output_tokens


class LLMOutputError(LLMError):
    """The model answered, but not with a valid instance of the requested contract."""

    def __init__(self, message: str, tokens_in: int = 0, tokens_out: int = 0, *, code: str = "output_validation",
                 request_sent: bool | None = None,reserved_tokens: int = 0,
                 validation_issues: tuple[str, ...] = ()) -> None:
        super().__init__(message, tokens_in, tokens_out, code="output_validation",
                         request_sent=request_sent,reserved_tokens=reserved_tokens)
        self.validation_issues = validation_issues


# Only fixed Pydantic codes and paths derived from the requested schema are safe.
_VALIDATION_CODES = frozenset({
    "json_invalid", "missing", "extra_forbidden", "model_type", "model_attributes_type",
    "list_type", "dict_type", "string_type", "string_too_short", "string_too_long",
    "string_pattern_mismatch", "int_type", "int_parsing", "int_from_float",
    "float_type", "float_parsing", "bool_type", "bool_parsing", "literal_error",
    "enum", "greater_than", "greater_than_equal", "less_than", "less_than_equal",
    "too_short", "too_long", "finite_number", "date_type", "date_parsing",
    "datetime_type", "datetime_parsing", "uuid_type", "uuid_parsing", "value_error",
})
_PATH_TOKEN = re.compile(r"\.([A-Za-z_][A-Za-z_0-9]*)|\[([0-9]{1,6})\]")


def _schema_path(output_type: type[BaseModel], loc: tuple) -> str:
    schema = output_type.model_json_schema()
    nodes = [schema]
    path = "$"
    for part in loc:
        expanded = []
        pending = list(nodes)
        seen = set()
        while pending:
            node = pending.pop()
            if not isinstance(node, dict) or id(node) in seen:
                continue
            seen.add(id(node))
            ref = node.get("$ref", "")
            if ref.startswith("#/$defs/"):
                pending.append(schema.get("$defs", {}).get(ref[8:], {}))
            for key in ("anyOf", "oneOf", "allOf"):
                pending.extend(node.get(key, []))
            expanded.append(node)
        if isinstance(part, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part):
            nodes = [n["properties"][part] for n in expanded if part in n.get("properties", {})]
            suffix = "." + part
        elif type(part) is int and 0 <= part <= 999999:
            nodes = [n["items"] for n in expanded if isinstance(n.get("items"), dict)]
            suffix = f"[{part}]"
        else:
            break
        if not nodes:
            break
        path += suffix
    return path


def _validation_issues(exc: ValidationError, output_type: type[BaseModel]) -> tuple[str, ...]:
    issues = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        code = error.get("type")
        if code not in _VALIDATION_CODES:
            continue
        path = "$" if code == "json_invalid" else _schema_path(output_type, error.get("loc", ()))
        issue = f"{path}:{code}"
        if issue not in issues:
            issues.append(issue)
        if len(issues) == 8:
            break
    return tuple(issues)


def _safe_child_issues(value: object, output_type: type[BaseModel]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    issues = []
    for issue in value[:8]:
        if not isinstance(issue, str) or len(issue) > 512 or issue.count(":") != 1:
            continue
        path, code = issue.split(":")
        if code not in _VALIDATION_CODES or not path.startswith("$"):
            continue
        rest = path[1:]
        parts = []
        while rest:
            match = _PATH_TOKEN.match(rest)
            if not match:
                break
            parts.append(match.group(1) if match.group(1) is not None else int(match.group(2)))
            rest = rest[match.end():]
        if rest or _schema_path(output_type, tuple(parts)) != path or (code == "json_invalid" and path != "$"):
            continue
        if issue not in issues:
            issues.append(issue)
    return tuple(issues)


def _output_error(exc: ValidationError, output_type: type[BaseModel], tokens_in: int, tokens_out: int) -> LLMOutputError:
    issues = _validation_issues(exc, output_type)
    return LLMOutputError("output failed validation" + (": " + ", ".join(issues) if issues else ""),
                          tokens_in, tokens_out, validation_issues=issues)


# Only categories, never provider bodies, cross the isolated-process boundary.
SAFE_ERROR_CODES = frozenset({"unknown", "output_validation", "output_limit", "incomplete_response",
    "provider_response_failed", "stream_interrupted", "stream_error", "request_timeout",
    "provider_request", "provider_unavailable", "insufficient_quota", "rate_limit_exceeded", "model_not_found",
    "invalid_api_key", "unsupported_parameter", "refusal"})


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

    def __init__(self, client: object | None = None, *, effort: str = "high", max_tokens: int = 64000, models: Mapping[str, str] | None = None, api_key: str | None = None, byok: bool = False) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, base_url="https://api.anthropic.com") if byok else anthropic.Anthropic()
        self._client = client
        self._models = dict(models) if models is not None else None
        self._byok = byok
        self._effort = effort
        self._max_tokens = max_tokens

    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]:
        from anthropic import transform_schema

        spec = ModelSpec.parse(self._models[role]) if self._models is not None else model_for(role)
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
            **({} if self._byok else {"fallbacks": "default", "betas": [FALLBACK_BETA]}),
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
            raise _output_error(exc, output_type, tokens_in, tokens_out) from None
        return LLMResult(output, message.model, prompt_version, tokens_in, tokens_out)


class OpenAIClient:
    """Responses API streaming, followed by the same Pydantic validation as Claude.

    Parse after collecting the raw response so invalid JSON still carries usage.
    No built-in web tools: source acquisition remains in Mira's allow-listed scouts.
    """

    def __init__(self, client: object | None = None, *, effort: str = "high", max_tokens: int = 64000, models: Mapping[str, str] | None = None, api_key: str | None = None, byok: bool = False) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1") if byok else OpenAI()
        self._client = client
        self._models = dict(models) if models is not None else None
        self._byok = byok
        self._effort = effort
        self._max_tokens = max_tokens

    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]:
        from openai import APIConnectionError, APIError, APITimeoutError

        spec = ModelSpec.parse(self._models[role]) if self._models is not None else model_for(role)
        if spec.provider != "openai":
            raise LLMError(f"OpenAI client cannot serve provider {spec.provider!r}")
        try:
            with self._client.responses.stream(
                model=spec.model,
                instructions=system,
                input=[{"role": "user", "content": user}],
                reasoning={"effort": self._effort},
                max_output_tokens=self._max_tokens,
                text={"format": {"type": "json_schema", "name": output_type.__name__,
                                  "schema": output_type.model_json_schema(), "strict": True}},
                store=False,
                **({"service_tier": "default"} if self._byok else {}),
            ) as stream:
                # The SDK's get_final_response only returns response.completed;
                # incomplete/failed events otherwise raise and lose their usage.
                response = None
                for event in stream:
                    if event.type in ("response.completed", "response.incomplete", "response.failed"):
                        response = event.response
                        break
                if response is None:
                    raise LLMError(f"{role} stream ended without a terminal response", code="stream_interrupted")
        except APIError as exc:
            # Never put provider error bodies (which can contain request data) in run logs.
            status = getattr(exc, "status_code", None)
            code = getattr(exc, "code", None)
            safe_code = code if code in ("insufficient_quota", "rate_limit_exceeded", "model_not_found",
                                         "invalid_api_key", "unsupported_parameter") else None
            if safe_code is None:
                if isinstance(exc, APITimeoutError):
                    safe_code = "request_timeout"
                elif isinstance(exc, APIConnectionError) or (status is not None and 500 <= status < 600):
                    safe_code = "provider_unavailable"
            raise LLMError(f"{role} OpenAI request failed: {type(exc).__name__} "
                           f"(HTTP {status}, code {safe_code})", code=safe_code or "provider_request") from None
        except (RuntimeError, ValueError) as exc:
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"{role} OpenAI stream failed", code="stream_error") from None
        usage = response.usage
        tokens_in = usage.input_tokens if usage else 0
        tokens_out = usage.output_tokens if usage else 0
        if response.status != "completed":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            code = "output_limit" if reason == "max_output_tokens" else (
                "incomplete_response" if response.status == "incomplete" else "provider_response_failed")
            raise LLMError(f"{role} OpenAI response {response.status} ({code})", tokens_in, tokens_out, code=code)
        if any(part.type == "refusal" for item in response.output if item.type == "message"
               for part in item.content):
            raise LLMError(f"{role} call refused", tokens_in, tokens_out, code="refusal")
        try:
            output = output_type.model_validate_json(response.output_text)
        except ValidationError as exc:
            raise _output_error(exc, output_type, tokens_in, tokens_out) from None
        return LLMResult(output, response.model, prompt_version, tokens_in, tokens_out)


class ProviderClient:
    """Lazily construct only the providers configured for the requested roles."""

    def __init__(self, *, models: Mapping[str, str] | None = None, api_keys: Mapping[str, str] | None = None) -> None:
        self._models = dict(models) if models is not None else None
        self._api_keys = MappingProxyType(dict(api_keys)) if api_keys is not None else None
        self._byok = api_keys is not None
        self._clients: dict[str, LLMClient] = {}
        self._lock = threading.Lock()

    @property
    def byok(self) -> bool:
        return self._byok

    @property
    def model_settings(self) -> dict[str, str]:
        if self._models is not None:
            return dict(self._models)
        return {role: os.environ[var] for role, var in ROLE_MODEL_ENV.items() if os.environ.get(var)}

    def close(self) -> None:
        with self._lock:
            self._clients.clear()
            self._api_keys = None

    def _spec(self, role: AgentRole) -> ModelSpec:
        try:
            spec = ModelSpec.parse(self._models[role]) if self._models is not None else model_for(role)
        except (KeyError, ValueError):
            raise LLMError("model configuration unavailable", request_sent=False) from None
        if spec.provider not in ("openai", "anthropic"):
            raise LLMError("unsupported provider", request_sent=False)
        if self._byok and not (self._api_keys or {}).get(spec.provider):
            raise LLMError("provider credential unavailable", request_sent=False)
        return spec

    @property
    def live(self) -> bool:
        return bool(self._clients) and all(isinstance(c, (AnthropicClient, OpenAIClient))
                                           for c in self._clients.values())

    def structured(
        self, *, role: AgentRole, system: str, user: str, output_type: type[T], prompt_version: str
    ) -> LLMResult[T]:
        provider = self._spec(role).provider
        factories = {"anthropic": AnthropicClient, "openai": OpenAIClient}
        if provider not in factories:
            raise LLMError(f"unsupported provider {provider!r}")
        with self._lock:
            if provider not in self._clients:
                self._clients[provider] = (factories[provider](models=self._models, api_key=self._api_keys[provider], byok=True)
                                           if self._byok else factories[provider](models=self._models) if self._models is not None
                                           else factories[provider]())
            client = self._clients[provider]
        return client.structured(role=role, system=system, user=user,
                                 output_type=output_type, prompt_version=prompt_version)


    def structured_bounded(self, *, role, system, user, output_type, prompt_version,
                           timeout_seconds: float, max_output_tokens: int):
        """One isolated request; kill its process on deadline, never leave a paid thread running.

        Model and effort configuration are unchanged. Prompts travel on stdin.
        Timeout cannot recover provider usage that was never reported.
        """
        import json
        import subprocess
        import sys
        if timeout_seconds <= 0 or max_output_tokens < 1:
            raise LLMError("bounded request has no remaining allowance", request_sent=False)
        if self._byok or self._models is not None:
            spec = self._spec(role)
        reservation=request_token_reservation(system=system,user=user,output_type=output_type,
                                               max_output_tokens=max_output_tokens)
        payload = dict(role=role, system=system, user=user, prompt_version=prompt_version,
                       output_module=output_type.__module__, output_name=output_type.__name__,
                       timeout_seconds=timeout_seconds, max_output_tokens=max_output_tokens)
        if self._models is not None or self._byok:
            payload["models"] = self.model_settings
        if self._byok:
            payload["api_keys"] = {spec.provider: self._api_keys[spec.provider]}
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE") or k.startswith("LC_")}
        else:
            env = None
        try:
            result = subprocess.run([sys.executable, "-c", "from mira.llm import _bounded_child; _bounded_child()"],
                input=json.dumps(payload).encode(), capture_output=True, timeout=timeout_seconds, check=True, **({"env": env} if env is not None else {}))
            data = json.loads(result.stdout)
        except subprocess.TimeoutExpired as exc:
            sent=b'MIRA_PROVIDER_REQUEST_STARTED' in (exc.stderr or b'')
            raise LLMError("bounded request timed out; provider usage may be unavailable",
                           code='request_timeout',request_sent=sent,reserved_tokens=reservation if sent else 0) from None
        except Exception as exc:
            sent=b'MIRA_PROVIDER_REQUEST_STARTED' in (getattr(exc,'stderr',None) or b'')
            raise LLMError("bounded request failed; provider usage may be unavailable",
                           request_sent=sent,reserved_tokens=reservation if sent else 0) from None
        if "error" in data:
            code = data.get("error_code", "unknown")
            code = code if code in SAFE_ERROR_CODES else "unknown"
            error = LLMOutputError if code == "output_validation" else LLMError
            tin,tout=data.get('tokens_in',0),data.get('tokens_out',0)
            sent=data.get('request_sent',True)
            issues = _safe_child_issues(data.get("validation_issues"), output_type) if code == "output_validation" else ()
            message = f"bounded request failed ({code})" + (": " + ", ".join(issues) if issues else "")
            kwargs = {"validation_issues": issues} if code == "output_validation" else {}
            raise error(message, tin,tout,code=code, request_sent=sent,
                        reserved_tokens=reservation if sent and not (tin or tout) else 0, **kwargs)
        return LLMResult(output_type.model_validate(data["output"]), data["model"], prompt_version,
                         data["tokens_in"], data["tokens_out"])


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
    issues: list[str] = []
    for _ in range(attempts):
        try:
            result = client.structured(
                role=role, system=system, user=prompt, output_type=output_type, prompt_version=prompt_version
            )
        except LLMOutputError as exc:
            for issue in _safe_child_issues(list(exc.validation_issues), output_type):
                if issue not in issues and len(issues) < 8:
                    issues.append(issue)
            tokens_in, tokens_out = tokens_in + exc.tokens_in, tokens_out + exc.tokens_out
            if exc.reserved_tokens:
                raise LLMOutputError(str(exc),tokens_in,tokens_out,request_sent=exc.request_sent,
                                     reserved_tokens=exc.reserved_tokens, validation_issues=tuple(issues)) from exc
            error = exc
        except LLMError as exc:
            message = str(exc) + (f"; earlier output issues: {', '.join(issues)}" if issues else "")
            raise LLMError(message, tokens_in + exc.tokens_in, tokens_out + exc.tokens_out, code=exc.code,
                           request_sent=exc.request_sent,reserved_tokens=exc.reserved_tokens,
                           validation_issues=tuple(issues)) from exc
        else:
            tokens_in, tokens_out = tokens_in + result.tokens_in, tokens_out + result.tokens_out
            try:
                check(result.output)
            except ValueError as exc:
                error = exc
            else:
                return LLMResult(result.output, result.model, prompt_version, tokens_in, tokens_out)
        prompt = f"{user}\n\nYour previous answer was rejected: {error}\nReturn a corrected answer."
    raise LLMOutputError(f"{role} output rejected after {attempts} attempts: {error}", tokens_in, tokens_out,
                         validation_issues=tuple(issues),
                         request_sent=error.request_sent if isinstance(error, LLMOutputError) else None)


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


    def structured_bounded(self, *, timeout_seconds: float, max_output_tokens: int, **kwargs):
        if timeout_seconds <= 0 or max_output_tokens < 1:
            raise LLMError("bounded request has no remaining allowance")
        result = self.structured(**kwargs)
        if result.tokens_out > max_output_tokens:
            raise LLMError("bounded output token limit reached", result.tokens_in, result.tokens_out)
        return result


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
            raise _output_error(exc, output_type, self.tokens_in, self.tokens_out) from None
        return LLMResult(output, self.model, prompt_version, self.tokens_in, self.tokens_out)


def _bounded_child():
    """Internal subprocess entrypoint; emit structured output or safe usage only."""
    import importlib
    import json
    import sys
    value = json.load(sys.stdin)
    output_type = getattr(importlib.import_module(value["output_module"]), value["output_name"])
    sent=False
    try:
        router = ProviderClient(models=value.get("models"), api_keys=value.get("api_keys"))
        spec = router._spec(value["role"])
        factories = {"anthropic": AnthropicClient, "openai": OpenAIClient}
        options = {"max_tokens": value["max_output_tokens"]}
        if router._models is not None:
            options["models"] = router._models
        if router.byok:
            options.update(api_key=router._api_keys[spec.provider], byok=True)
        client = factories[spec.provider](**options)
        client._client = client._client.with_options(timeout=value["timeout_seconds"], max_retries=0)
        # Written before entering provider code; no request text or credential.
        sent=True
        print('MIRA_PROVIDER_REQUEST_STARTED',file=sys.stderr,flush=True)
        result = client.structured(role=value["role"], system=value["system"], user=value["user"],
            output_type=output_type, prompt_version=value["prompt_version"])
        data = dict(output=result.output.model_dump(mode="json"), model=result.model,
                    tokens_in=result.tokens_in, tokens_out=result.tokens_out)
    except LLMError as exc:
        code = exc.code if exc.code in SAFE_ERROR_CODES else "unknown"
        data = dict(error=True, error_code=code, tokens_in=exc.tokens_in, tokens_out=exc.tokens_out,request_sent=sent)
        if code == "output_validation" and isinstance(exc, LLMOutputError):
            issues = _safe_child_issues(list(exc.validation_issues), output_type)
            if issues:
                data["validation_issues"] = list(issues)
    except Exception:
        data = dict(error=True, error_code="unknown", tokens_in=0, tokens_out=0,request_sent=sent)
    sys.stdout.write(json.dumps(data))
