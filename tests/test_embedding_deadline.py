import os
import sys
import time

import pytest

from mira.embedding_request import bounded_request, RequestTimeout


def test_child_is_killed_and_reaped_on_deadline(tmp_path):
    path = tmp_path / 'pid'
    script = "import os,sys,time; open(sys.argv[1],'w').write(str(os.getpid())); sys.stdin.read(); time.sleep(5)"
    started = time.monotonic()
    with pytest.raises(RequestTimeout):
        bounded_request({'api_key':'secret'}, timeout_seconds=0.3,
                        command=[sys.executable, '-c', script, str(path)])
    assert time.monotonic() - started < 2
    pid = int(path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_timeout_reserves_unknown_usage_and_returns_lexical():
    from dataclasses import dataclass
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.hybrid import EmbeddingIdentity, HybridLimits, OpenAIEmbedder, retrieve
    @dataclass
    class Passage:
        id: object
        content: str
    item = Passage(uuid4(), 'car')
    def timeout(payload, *, timeout_seconds):
        raise RequestTimeout()
    embedder = OpenAIEmbedder(SimpleNamespace(api_key='secret', base_url='https://example.test'),
                              EmbeddingIdentity('m','1',2), reserved_tokens=100, runner=timeout)
    result = retrieve([item], 'car', embedder, embedder.identity, HybridLimits(max_tokens=100))
    assert result.passages == [item]
    assert result.tokens == 0 and result.reserved_tokens == 100
