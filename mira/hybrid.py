"""Opt-in, bounded passage fusion. Callers must prefilter every eligible passage.

The caller owns permission/as-of filtering and must reserve the provider allowance
before invocation; this module does not grant access or persist vectors.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
import re
from typing import Callable, Protocol, Sequence
from uuid import UUID


@dataclass(frozen=True)
class EmbeddingIdentity:
    model: str
    revision: str
    dimensions: int = 384


@dataclass(frozen=True)
class PassageVector:
    passage_id: UUID
    identity: EmbeddingIdentity
    values: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    tokens: int


class Embedder(Protocol):
    def embed(self, texts: Sequence[str], *, timeout_seconds: float) -> EmbeddingResult: ...


@dataclass(frozen=True)
class HybridLimits:
    max_index_passages: int = 40
    max_characters: int = 60000
    max_tokens: int = 20000
    timeout_seconds: float = 20
    result_limit: int = 20
    max_index_batches: int = 4


@dataclass(frozen=True)
class HybridResult:
    passages: list
    vectors: tuple[PassageVector, ...]
    tokens: int = 0
    reserved_tokens: int = 0
    fallback_reason: str | None = None


class EmbeddingError(Exception):
    def __init__(self, message: str, reserved_tokens: int = 0, *, tokens: int | None = None, request_sent: bool | None = None):
        super().__init__(message)
        self.tokens = tokens
        self.request_sent = request_sent
        self.reserved_tokens = reserved_tokens if tokens is None else 0


def _valid(values, identity):
    if len(values) != identity.dimensions or not all(isinstance(x, (int, float)) and isfinite(x) for x in values):
        raise ValueError('invalid embedding dimensions or values')
    if not any(values):
        raise ValueError('zero embedding')
    return tuple(float(x) for x in values)


def _lexical(query, eligible):
    words = set(re.findall(r'\w+', query.casefold()))
    scored = [(len(words & set(re.findall(r'\w+', p.content.casefold()))), str(p.id), p) for p in eligible]
    return [p for score, _, p in sorted(scored, key=lambda x: (-x[0], x[1])) if score]


def rank(query, eligible, lexical, query_vector, vectors, identity, limit):
    """Fuse eligible lexical and cosine ranks using RRF (k=60)."""
    if limit < 0 or identity.dimensions <= 0:
        raise ValueError('invalid limit or dimensions')
    pool = {p.id: p for p in eligible}
    if len(pool) != len(eligible):
        raise ValueError('duplicate eligible passage')
    q = _valid(query_vector, identity)
    seen = set()
    candidates = []
    for vector in vectors:
        if vector.passage_id not in pool:
            continue
        if vector.passage_id in seen or vector.identity != identity:
            raise ValueError('duplicate or incompatible passage vector')
        seen.add(vector.passage_id)
        v = _valid(vector.values, identity)
        score = sum((a / hypot(*q)) * (b / hypot(*v)) for a, b in zip(q, v))
        candidates.append((score, str(vector.passage_id), vector.passage_id))
    scores = {}
    lexical_ids = []
    for passage in lexical:
        if passage.id in pool and passage.id not in lexical_ids:
            lexical_ids.append(passage.id)
    for ordered in (lexical_ids, [item[2] for item in sorted(candidates, key=lambda x: (-x[0], x[1]))]):
        for position, passage_id in enumerate(ordered, 1):
            scores[passage_id] = scores.get(passage_id, 0.0) + 1 / (60 + position)
    return [pool[i] for i in sorted(scores, key=lambda i: (-scores[i], str(i)))[:limit]]


def retrieve(eligible, query, embedder, identity, limits=HybridLimits(), existing_vectors=(), *, reserve: Callable[[int], None] | None = None):
    """Embed whole eligible passages once; on errors return the lexical baseline.

    ``reserve`` must atomically reserve max_tokens in the caller's budget or
    raise. On success caller reconciles that reservation with result.tokens; on
    unknown usage it retains result.reserved_tokens. No reservation is made for
    preflight refusals. Existing vectors must be for the current passage content.
    """
    if (limits.max_index_passages < 0 or limits.max_characters < 0 or limits.max_tokens <= 0
            or limits.timeout_seconds <= 0 or limits.result_limit < 0 or identity.dimensions <= 0):
        raise ValueError('invalid hybrid limits')
    pool = {p.id: p for p in eligible}
    if len(pool) != len(eligible):
        raise ValueError('duplicate eligible passage')
    lexical = _lexical(query, eligible)
    baseline = lexical[:limits.result_limit]
    def fallback(reason, reserved=0, tokens=0):
        return HybridResult(baseline, (), tokens=tokens, reserved_tokens=reserved, fallback_reason=reason)
    if len(eligible) > limits.max_index_passages:
        return fallback('passage_limit')
    current = []
    seen = set()
    for vector in existing_vectors:
        if vector.passage_id not in pool:
            continue
        if vector.passage_id in seen or vector.identity != identity:
            raise ValueError('duplicate or incompatible passage vector')
        _valid(vector.values, identity)
        current.append(vector)
        seen.add(vector.passage_id)
    missing = [p for p in eligible if p.id not in seen]
    texts = [query] + [p.content for p in missing]
    if sum(len(s) for s in texts) > limits.max_characters:
        return fallback('character_limit')
    # Byte count is a conservative local guard, not provider token accounting.
    if sum(len(s.encode('utf-8')) for s in texts) > limits.max_tokens:
        return fallback('token_limit')
    if reserve is not None:
        reserve(limits.max_tokens)
    try:
        result = embedder.embed(texts, timeout_seconds=limits.timeout_seconds)
    except EmbeddingError as exc:
        if isinstance(exc.tokens, int) and not isinstance(exc.tokens, bool) and exc.tokens >= 0:
            reason = 'token_limit_exceeded' if exc.tokens > limits.max_tokens else 'embedding_failed'
            return fallback(reason, tokens=exc.tokens)
        return fallback('embedding_failed', limits.max_tokens)
    except Exception:
        return fallback('embedding_failed', limits.max_tokens)
    tokens = getattr(result, 'tokens', None)
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        return fallback('embedding_failed', limits.max_tokens)
    if tokens > limits.max_tokens:
        return fallback('token_limit_exceeded', tokens=tokens)
    try:
        if len(result.vectors) != len(texts):
            raise ValueError('invalid provider vector count')
        q = _valid(result.vectors[0], identity)
        for passage, vector in zip(missing, result.vectors[1:]):
            current.append(PassageVector(passage.id, identity, _valid(vector, identity)))
        passages = rank(query, eligible, lexical, q, current, identity, limits.result_limit)
        return HybridResult(passages, tuple(current), tokens=tokens)
    except (ValueError, TypeError, AttributeError, IndexError, OverflowError):
        return fallback('embedding_failed', tokens=tokens)


class OpenAIEmbedder:
    """Hard-deadline adapter; the injected SDK client is never forked or used for requests."""
    def __init__(self, client, identity: EmbeddingIdentity, *, reserved_tokens: int, runner=None):
        if reserved_tokens <= 0:
            raise ValueError('reserved_tokens must be positive')
        from mira.embedding_request import bounded_request
        self.runner = runner or bounded_request
        self.client = client
        self.identity = identity
        self.reserved_tokens = reserved_tokens

    def embed(self, texts: Sequence[str], *, timeout_seconds: float) -> EmbeddingResult:
        tokens = None
        try:
            payload = {'api_key': self.client.api_key, 'base_url': str(self.client.base_url),
                       'organization': getattr(self.client, 'organization', None),
                       'project': getattr(self.client, 'project', None),
                       'model': self.identity.model, 'dimensions': self.identity.dimensions,
                       'texts': list(texts), 'timeout_seconds': timeout_seconds}
            response = self.runner(payload, timeout_seconds=timeout_seconds)
            reported = response.get('tokens')
            if isinstance(reported, int) and not isinstance(reported, bool) and reported >= 0:
                tokens = reported
            if tokens is None or response.get('error'):
                raise ValueError('provider request failed')
            data = sorted(response['data'], key=lambda item: item['index'])
            if [item['index'] for item in data] != list(range(len(texts))):
                raise ValueError('invalid vector indices')
            vectors = tuple(_valid(item['values'], self.identity) for item in data)
            return EmbeddingResult(vectors, tokens)
        except Exception as exc:
            raise EmbeddingError('embedding request failed', self.reserved_tokens, tokens=tokens) from exc
