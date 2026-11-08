"""Offline boundaries for targeted corroboration acquisition."""
import sys
import time

import pytest

from mira.corroboration_acquisition import BoundedFetcher


def test_broker_timeout_kills_and_reaps_child():
    broker = BoundedFetcher([], command=[sys.executable, "-c", "import sys,time; sys.stdin.readline(); time.sleep(30)"])
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        broker.fetch("https://example.org/a", set(), timeout_seconds=0.2)
    assert time.monotonic() - started < 3
    assert broker.process.poll() is not None
    with pytest.raises(RuntimeError):
        broker.fetch("https://example.org/a", set(), timeout_seconds=1)


def test_refused_document_does_not_terminate_policy_broker():
    code = "import sys; sys.stdin.readline(); [(print('{\"error\":\"FetchRefused\"}', flush=True)) for line in sys.stdin]"
    broker = BoundedFetcher([], command=[sys.executable, "-u", "-c", code])
    try:
        with pytest.raises(RuntimeError, match="FetchRefused"):
            broker.fetch("https://example.org/a", set(), timeout_seconds=1)
        assert broker.process.poll() is None
        with pytest.raises(RuntimeError, match="FetchRefused"):
            broker.fetch("https://example.org/b", set(), timeout_seconds=1)
    finally:
        broker.close()


def test_broker_returns_scoped_fetched_page_and_extraction():
    import json
    from dataclasses import replace
    from uuid import uuid4
    from test_fetch_extract import HKMA
    source = replace(HKMA, id=uuid4())
    code = '''import json,sys
sources=json.loads(sys.stdin.readline()); req=json.loads(sys.stdin.readline())
s=sources[0]
assert req["source_ids"] == [s["id"]]
p={"url":req["url"],"requested_url":req["url"],"source_id":s["id"],"kind":"html","content_type":"text/html","body":"PHA+eDwvcD4=","fetched_at":"2026-01-01T00:00:00+00:00"}
e={"title":"x","status":"complete","pages":["x"],"links":[],"published":None,"error":None,"published_basis":None}
print(json.dumps({"page":p,"extracted":e}),flush=True)
'''
    broker = BoundedFetcher([source], command=[sys.executable, "-u", "-c", code])
    try:
        page, extracted = broker.fetch("https://www.hkma.gov.hk/a", {source.id}, timeout_seconds=2)
        assert page.source == source
        assert page.body == b"<p>x</p>"
        assert extracted.text == "x"
    finally:
        broker.close()


def test_discovery_saves_before_returning_only_current_scoped_evidence(monkeypatch):
    from contextlib import nullcontext
    from dataclasses import dataclass, replace
    from datetime import UTC, datetime
    from types import SimpleNamespace, ModuleType
    from uuid import uuid4
    from mira import corroboration_acquisition as module
    from mira.extract import Extracted, Link
    from mira.fetch import FetchedPage
    from test_fetch_extract import HKMA
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    url = "https://example.org/a"
    page = FetchedPage(url, url, source, "html", "text/html", b"<p>text</p>", datetime.now(UTC))
    extracted = Extracted("Title", "complete", ["text"])
    passage_id, version_id, doc_id = uuid4(), uuid4(), uuid4()
    @dataclass
    class Record:
        id: object
        source_url: str
        source_id: object
    events = []
    class Writer:
        def __init__(self, *args): pass
        def save(self, *args, **kwargs):
            events.append("save")
            return SimpleNamespace(document_id=doc_id, document_version_id=version_id, passage_ids=[passage_id])
    class Store:
        def __init__(self, *args): pass
        def list_sources(self, *args): return [source]
        def get_passages(self, *args):
            assert events == ["save"]
            return [Record(passage_id, url, source.id)]
    class Conn:
        def transaction(self): return nullcontext()
        def execute(self, query, params):
            if "select" in query.lower():
                return SimpleNamespace(fetchone=lambda: {"id": version_id})
            return None
    fake = ModuleType("mira.corroboration")
    fake.FrozenPassage = lambda **kw: SimpleNamespace(**kw)
    fake.CandidateEvidence = lambda **kw: SimpleNamespace(**kw)
    fake.DiscoveryBatch = lambda **kw: SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "mira.corroboration", fake)
    monkeypatch.setattr(module, "EvidenceWriter", Writer, raising=False)
    monkeypatch.setattr(module, "PostgresStore", Store, raising=False)
    broker = SimpleNamespace(fetch=lambda *a, **kw: (page, extracted))
    search = SimpleNamespace(with_timeout=lambda _: SimpleNamespace(discover=lambda *args: [Link(url, "Title", "")]))
    adapter = module.CorroborationDiscovery(Conn(), [source], search, broker=broker)
    ctx = context()
    batch = adapter.discover("question", ctx=ctx, source_ids=(source.id,), max_documents=1, max_passages=1, timeout_seconds=2)
    assert batch.document_attempts == 1
    assert batch.candidates[0].passage.id == passage_id
    assert batch.candidates[0].workspace_id == ctx.workspace_id


def test_discovery_counts_refusals_and_obeys_document_cap():
    from dataclasses import replace
    from types import SimpleNamespace
    from mira.corroboration_acquisition import CorroborationDiscovery, AcquisitionRefused
    from mira.extract import Link
    from test_fetch_extract import HKMA
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    calls = []
    def fetch(url, source_ids, timeout_seconds):
        calls.append(url)
        raise AcquisitionRefused("FetchRefused")
    search = SimpleNamespace(with_timeout=lambda _: SimpleNamespace(discover=lambda *args: [
        Link("https://example.org/a", "", ""), Link("https://example.org/b", "", "")]))
    adapter = CorroborationDiscovery(None, [source], search, broker=SimpleNamespace(fetch=fetch))
    batch = adapter.discover("question", ctx=context(), source_ids=(source.id,), max_documents=1, max_passages=3, timeout_seconds=2)
    assert calls == ["https://example.org/a"]
    assert batch.document_attempts == 1
    assert batch.errors == ["acquisition https://example.org/a: AcquisitionRefused"]
    assert not batch.candidates


def test_expired_after_save_does_not_load_or_return_passages(monkeypatch):
    from contextlib import nullcontext
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    from mira import corroboration_acquisition as module
    from mira.extract import Extracted, Link
    from mira.fetch import FetchedPage
    from test_fetch_extract import HKMA
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    page = FetchedPage("https://example.org/a", "https://example.org/a", source, "html", "text/html", b"body", datetime.now(UTC))
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    class Writer:
        def __init__(self, *args): pass
        def save(self, *args, **kwargs):
            clock[0] = 2.0
            return SimpleNamespace(document_id=uuid4(), document_version_id=uuid4(), passage_ids=[uuid4()])
    class Conn:
        def transaction(self): return nullcontext()
        def execute(self, *args):
            if clock[0]: raise AssertionError("unexpected query after expiry")
    monkeypatch.setattr(module, "EvidenceWriter", Writer)
    monkeypatch.setattr(module, "PostgresStore", lambda *args: SimpleNamespace(list_sources=lambda *args: [source]))
    discovery = SimpleNamespace(with_timeout=lambda _: SimpleNamespace(discover=lambda *args: [Link(page.url, "", "")]))
    broker = SimpleNamespace(fetch=lambda *args, **kwargs: (page, Extracted("title", "complete", ["body"])))
    batch = module.CorroborationDiscovery(Conn(), [source], discovery, broker=broker).discover(
        "question", ctx=context(), source_ids=(source.id,), max_documents=1, max_passages=1, timeout_seconds=1)
    assert batch.document_attempts == 1
    assert batch.errors == ["acquisition https://example.org/a: TimeoutError"]
    assert not batch.candidates


# Import existing disposable-workspace fixtures; no network or model calls.
from test_pipeline_db import conn, workspace


@pytest.mark.skipif(not __import__("os").environ.get("MIRA_TEST_DATABASE_URL"), reason="local test database unavailable")
def test_saved_targeted_evidence_uses_current_version_and_provenance(conn, workspace):
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from mira.corroboration_acquisition import CorroborationDiscovery
    from mira.extract import Link, extract
    from mira.fetch import FetchedPage
    from mira.pg_store import PostgresStore
    from test_orchestrator import context
    workspace_id, user_id = workspace
    ctx = replace(context(), workspace_id=workspace_id, user_id=user_id)
    source = next(s for s in PostgresStore(conn).list_sources(workspace_id)
                  if s.base_url and "hkma.gov.hk" in s.base_url and {"fetch", "store_text"} <= set(s.permitted_operations))
    url = source.base_url.rstrip("/") + "/corroboration-fixture"
    pages = [FetchedPage(url, url, source, "html", "text/html", body, datetime.now(UTC)) for body in
             (b"<p>First publication text.</p>", b"<p>Second publication text.</p>", b"<p>First publication text.</p>", b"<script>empty</script>")]
    def fetch(*args, **kwargs):
        page = pages.pop(0)
        return page, extract(page)
    search = SimpleNamespace(with_timeout=lambda _: SimpleNamespace(discover=lambda *args: [Link(url, "", "")]))
    adapter = CorroborationDiscovery(conn, [source], search, broker=SimpleNamespace(fetch=fetch))
    def discover():
        return adapter.discover("fixture", ctx=ctx, source_ids=(source.id,), max_documents=1, max_passages=2, timeout_seconds=5)
    first, second, old, empty = discover(), discover(), discover(), discover()
    assert first.document_attempts == second.document_attempts == old.document_attempts == 1
    assert first.candidates[0].passage.content == "First publication text."
    assert second.candidates[0].passage.content == "Second publication text."
    assert second.candidates[0].passage.acquisition_provenance["capture_sha256"]
    assert old.candidates == []
    assert "saved version is not current eligible evidence" in old.errors
    assert empty.candidates == []
    assert any("extraction " in item and "version " in item for item in empty.errors)


def test_real_broker_rejects_unpermitted_scheme_without_network():
    from test_fetch_extract import HKMA
    from mira.corroboration_acquisition import AcquisitionRefused
    broker = BoundedFetcher([HKMA])
    try:
        with pytest.raises(AcquisitionRefused, match="FetchRefused"):
            broker.fetch("ftp://www.hkma.gov.hk/no", {HKMA.id}, timeout_seconds=3)
        assert broker.process.poll() is None
    finally:
        broker.close()


def test_revoked_storage_permission_is_rechecked_before_save(monkeypatch):
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from mira import corroboration_acquisition as module
    from mira.extract import Extracted, Link
    from mira.fetch import FetchedPage
    from test_fetch_extract import HKMA
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    revoked = replace(source, permitted_operations=("fetch",))
    page = FetchedPage("https://example.org/a", "https://example.org/a", source, "html", "text/html", b"body", datetime.now(UTC))
    writes = []
    class Store:
        def __init__(self, *args): pass
        def list_sources(self, workspace_id): return [revoked]
    class Writer:
        def __init__(self, *args): pass
        def save(self, *args, **kwargs): writes.append(1)
    monkeypatch.setattr(module, "PostgresStore", Store)
    monkeypatch.setattr(module, "EvidenceWriter", Writer)
    discovery = SimpleNamespace(with_timeout=lambda _: SimpleNamespace(discover=lambda *args: [Link(page.url, "", "")]))
    broker = SimpleNamespace(fetch=lambda *args, **kwargs: (page, Extracted("title", "complete", ["body"])))
    from contextlib import nullcontext
    conn = SimpleNamespace(transaction=lambda: nullcontext(), execute=lambda *args: None)
    adapter = module.CorroborationDiscovery(conn, [source], discovery, broker=broker)
    batch = adapter.discover("question", ctx=context(), source_ids=(source.id,), max_documents=1, max_passages=1, timeout_seconds=1)
    assert writes == []
    assert any("permission" in item for item in batch.errors)


def test_evidence_writer_stops_between_passage_inserts_after_deadline(monkeypatch):
    from contextlib import nullcontext
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    from mira import evidence
    from mira.extract import Extracted
    from mira.fetch import FetchedPage
    from test_fetch_extract import HKMA

    clock, inserts = [0.0], []
    monkeypatch.setattr(evidence, "acting_as", lambda *args: nullcontext())
    import time as clock_module
    monkeypatch.setattr(clock_module, "monotonic", lambda: clock[0])
    class Conn:
        def execute(self, query, params=()):
            sql = " ".join(query.lower().split())
            if "insert into public.document_passages" in sql:
                inserts.append(query)
                clock[0] = 2.0
                return SimpleNamespace(fetchone=lambda: {"id": uuid4()})
            if "insert into public.documents" in sql or "insert into public.document_versions" in sql:
                return SimpleNamespace(fetchone=lambda: {"id": uuid4()})
            return SimpleNamespace(fetchone=lambda: None)
    page = FetchedPage("https://www.hkma.gov.hk/a", "https://www.hkma.gov.hk/a", HKMA,
                       "html", "text/html", b"body", datetime.now(UTC))
    body = "First " + "a" * 1300 + "\n\nSecond " + "b" * 1300
    with pytest.raises(TimeoutError):
        evidence.EvidenceWriter(Conn(), uuid4(), uuid4()).save(page, Extracted("title", "complete", [body]), deadline=1.0)
    assert len(inserts) == 1


@pytest.mark.skipif(not __import__("os").environ.get("MIRA_TEST_DATABASE_URL"), reason="local test database unavailable")
def test_expired_evidence_save_rolls_back_all_versions_and_passages(conn, workspace, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from mira import evidence
    from mira.extract import Extracted, split_passages
    from mira.fetch import FetchedPage
    from mira.pg_store import PostgresStore
    workspace_id, user_id = workspace
    source = next(s for s in PostgresStore(conn).list_sources(workspace_id)
                  if s.base_url and "hkma.gov.hk" in s.base_url and {"fetch", "store_text"} <= set(s.permitted_operations))
    url = source.base_url.rstrip("/") + "/deadline-fixture"
    page = FetchedPage(url, url, source, "html", "text/html", b"body", datetime.now(UTC))
    extracted = Extracted("title", "complete", ["First " + "a" * 1300 + "\n\nSecond " + "b" * 1300])
    spans = split_passages(extracted)
    clock = [0.0]
    monkeypatch.setattr(evidence, "time_module", SimpleNamespace(monotonic=lambda: clock[0]))
    def interrupted(_):
        yield spans[0]
        clock[0] = 2.0
        yield spans[1]
    monkeypatch.setattr(evidence, "split_passages", interrupted)
    with pytest.raises(TimeoutError), conn.transaction():
        evidence.EvidenceWriter(conn, workspace_id, user_id).save(page, extracted, deadline=1.0)
    assert conn.execute("select id from public.documents where workspace_id = %s and canonical_url = %s",
                        (workspace_id, url)).fetchone() is None
