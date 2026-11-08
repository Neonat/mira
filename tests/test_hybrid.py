from dataclasses import dataclass
from uuid import uuid4

import pytest

from mira.hybrid import (EmbeddingIdentity, EmbeddingResult, HybridLimits,
                         PassageVector, rank, retrieve)


@dataclass(frozen=True)
class Passage:
    id: object
    content: str


def p(text):
    return Passage(uuid4(), text)


class Embed:
    def embed(self, texts, *, timeout_seconds):
        def vec(text):
            return (1.0, 0.0) if any(w in text for w in ('car', 'automobile')) else (0.0, 1.0)
        return EmbeddingResult(tuple(vec(t) for t in texts), len(texts) * 2)


def test_synonym_fusion_and_eligibility():
    identity = EmbeddingIdentity('fixture', '1', 2)
    relevant, irrelevant, outside = p('automobile policy'), p('unrelated'), p('car outside')
    result = retrieve([relevant, irrelevant], 'car', Embed(), identity, HybridLimits(result_limit=1))
    assert result.passages == [relevant]
    assert result.tokens == 6
    assert outside not in result.passages


def test_rank_filters_cross_pool_and_rejects_incompatible_vectors():
    identity = EmbeddingIdentity('fixture', '1', 2)
    allowed, outside = p('car'), p('car')
    query = (1.0, 0.0)
    assert rank('car', [allowed], [outside, allowed], query, [], identity, 1) == [allowed]
    with pytest.raises(ValueError):
        rank('car', [allowed], [], query, [PassageVector(allowed.id, EmbeddingIdentity('other', '1', 2), query)], identity, 1)


def test_oversize_and_failure_fall_back_without_truncation():
    item = p('car policy')
    class Failed:
        def embed(self, texts, *, timeout_seconds):
            raise TimeoutError()
    limits = HybridLimits(max_characters=3, result_limit=1)
    result = retrieve([item], 'car', Failed(), EmbeddingIdentity('f', '1', 2), limits)
    assert result.passages == [item]
    assert result.fallback_reason == 'character_limit'
    assert result.reserved_tokens == 0
    result = retrieve([item], 'car', Failed(), EmbeddingIdentity('f', '1', 2), HybridLimits(result_limit=1))
    assert result.passages == [item]
    assert result.fallback_reason == 'embedding_failed'
    assert result.reserved_tokens > 0


def test_equal_cap_exact_term_and_synonym_comparison():
    identity = EmbeddingIdentity('fixture', '1', 2)
    synonym, exact, irrelevant = p('automobile policy'), p('car policy'), p('unrelated')
    synonym_result = retrieve([synonym, irrelevant], 'car', Embed(), identity, HybridLimits(result_limit=1))
    exact_result = retrieve([exact, irrelevant], 'car', Embed(), identity, HybridLimits(result_limit=1))
    assert synonym_result.passages == [synonym]
    assert exact_result.passages == [exact]
    assert retrieve([synonym, irrelevant], 'car', Embed(), identity, HybridLimits(max_index_passages=0, result_limit=1)).passages == []


def test_reservation_and_reused_vectors():
    identity = EmbeddingIdentity('fixture', '1', 2)
    item = p('automobile')
    vector = PassageVector(item.id, identity, (1., 0.))
    reservations = []
    result = retrieve([item], 'car', Embed(), identity, HybridLimits(max_tokens=100), [vector], reserve=reservations.append)
    assert reservations == [100]
    assert result.tokens == 2 and result.reserved_tokens == 0
    assert result.vectors == (vector,)
    with pytest.raises(ValueError):
        retrieve([item], 'car', Embed(), identity, HybridLimits(), [vector, vector])
    with pytest.raises(ValueError):
        retrieve([item], 'car', Embed(), identity, HybridLimits(), [PassageVector(item.id, EmbeddingIdentity('fixture', '2', 2), (1., 0.))])


def test_adapter_single_attempt_and_unknown_usage():
    from types import SimpleNamespace
    from mira.hybrid import EmbeddingError, OpenAIEmbedder
    client = SimpleNamespace(api_key='secret', base_url='https://example.test')
    def runner(payload, *, timeout_seconds):
        assert timeout_seconds == 4 and payload['dimensions'] == 2
        return {'error': True, 'tokens': None}
    with pytest.raises(EmbeddingError) as error:
        OpenAIEmbedder(client, EmbeddingIdentity('fixture', '1', 2), reserved_tokens=100, runner=runner).embed(['car'], timeout_seconds=4)
    assert error.value.reserved_tokens == 100


def test_invalid_vectors_and_cross_pool_cannot_enter_results():
    identity = EmbeddingIdentity('fixture', '1', 2)
    allowed, outside = p('car'), p('car')
    for values in ((1.,), (float('nan'), 1.), (0., 0.)):
        with pytest.raises(ValueError):
            rank('car', [allowed], [], (1., 0.), [PassageVector(allowed.id, identity, values)], identity, 2)
    assert rank('car', [allowed], [outside], (1., 0.), [PassageVector(outside.id, identity, (1., 0.))], identity, 2) == []


def test_budget_refusal_never_invokes_embedder_or_reservation():
    item = p('car policy')
    reservations = []
    result = retrieve([item], 'car', Embed(), EmbeddingIdentity('f', '1', 2), HybridLimits(max_tokens=2), reserve=reservations.append)
    assert result.fallback_reason == 'token_limit'
    assert result.passages == [item]
    assert reservations == []


def test_known_usage_survives_bad_vectors_and_over_limit():
    class Invalid:
        def embed(self, texts, *, timeout_seconds):
            return EmbeddingResult(((0., 0.),), 100)
    item = p('car')
    result = retrieve([item], 'car', Invalid(), EmbeddingIdentity('m','1',2), HybridLimits(max_tokens=200))
    assert (result.tokens, result.reserved_tokens, result.fallback_reason) == (100, 0, 'embedding_failed')
    result = retrieve([item], 'car', Invalid(), EmbeddingIdentity('m','1',2), HybridLimits(max_tokens=50))
    assert (result.tokens, result.reserved_tokens, result.fallback_reason) == (100, 0, 'token_limit_exceeded')


def test_adapter_invalid_indices_preserve_known_usage():
    from types import SimpleNamespace
    from mira.hybrid import EmbeddingError, OpenAIEmbedder
    client = SimpleNamespace(api_key='secret', base_url='https://example.test')
    adapter = OpenAIEmbedder(client, EmbeddingIdentity('m','1',2), reserved_tokens=200,
                            runner=lambda payload, **kw: {'tokens': 100, 'data': [{'index': 9, 'values': [1, 0]}]})
    with pytest.raises(EmbeddingError) as error:
        adapter.embed(['car'], timeout_seconds=1)
    assert error.value.tokens == 100 and error.value.reserved_tokens == 0
