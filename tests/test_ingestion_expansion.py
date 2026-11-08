"""Offline tests for bounded, untrusted URL discovery."""
from dataclasses import replace
from datetime import date

from mira.discovery import ExaDiscovery
from mira.fetch import AllowList
from test_fetch_extract import HKMA


def test_discovery_is_bounded_and_rejects_other_sources_and_future_dates():
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=__import__('uuid').uuid4(), base_url="https://other.org", connector_config={})
    calls = []
    def search(query, limit, timeout):
        calls.append((query, limit, timeout))
        return [
            {"url": "https://example.org/a", "title": "Publication", "publishedDate": "2025-10-01"},
            {"url": "https://other.org/a", "title": "Wrong source"},
            {"url": "https://example.org/future", "publishedDate": "2030-01-01"},
        ]
    adapter = ExaDiscovery(search=search, max_results=3, timeout=2)
    links = adapter.discover("AML", [source.id], AllowList([source, other]), date(2026, 1, 1))
    assert [link.url for link in links] == ["https://example.org/a"]
    assert links[0].published is None  # provider dates cannot establish publication date
    assert calls == [("AML", 3, 2)]


def test_scout_adds_discovered_urls_without_provider_content(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun
    from mira.contracts import ScoutReport
    from mira.extract import Link
    from test_orchestrator import context

    source = replace(HKMA, base_url="https://example.org", connector_config={})
    adapter = SimpleNamespace(discover=lambda *args: [Link("https://example.org/publication", "Title", "provider full text")])
    scout = WebScout("unused", None, SimpleNamespace(allow=AllowList([source])), discovery=adapter, max_rounds=0)
    task = SimpleNamespace(max_documents=2, source_ids=(source.id,), expected_source_ids=(), question="AML", role="regulatory_scout", jurisdiction_code="HK")
    run = _ScoutRun(scout, None, context(), uuid4(), task)
    run.store = SimpleNamespace(list_sources=lambda _: [source], list_expected_sources=lambda *args: [])
    monkeypatch.setattr(run, "_report", lambda: (ScoutReport(documents=[], expected_source_statuses=[], notes=None), {}))
    run.execute()
    assert [link.url for link in run.candidates] == ["https://example.org/publication"]
    assert run.discovery[0]["document_version_id"] is None
    assert run.candidates[0].context == "URL discovered by search provider"


def test_exa_http_posts_url_only_request_with_fixed_endpoint():
    import json
    from mira.discovery import ExaHTTP
    seen = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"results": [{"url": "https://example.org/a"}]}'
    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, dict(request.header_items()), json.loads(request.data), timeout))
            return Response()
    result = ExaHTTP("secret", domains=["example.org"], opener=Opener())("AML", 3, 2)
    assert result == [{"url": "https://example.org/a"}]
    assert seen[0][0] == "https://api.exa.ai/search"
    assert seen[0][2] == {"query": "AML", "type": "auto", "numResults": 3, "includeDomains": ["example.org"]}
    assert seen[0][3] == 2


def test_capture_and_extraction_identity_distinguish_same_bytes_different_text():
    from datetime import UTC, datetime
    from mira.evidence import evidence_identity
    from mira.extract import Extracted
    from mira.fetch import FetchedPage
    page = FetchedPage("https://example.org/a", "https://example.org/a", HKMA, "html", "text/html", b"same", datetime.now(UTC))
    first = evidence_identity(page, Extracted("Title", "complete", ["First extraction"]))
    second = evidence_identity(page, Extracted("Title", "complete", ["Second extraction"]))
    assert first["capture_sha256"] == second["capture_sha256"]
    assert first["extraction_sha256"] != second["extraction_sha256"]
    assert first["version_sha256"] != second["version_sha256"]


def test_cached_redirect_cannot_cross_task_source_scope():
    from concurrent.futures import Future
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun, _Visit
    from mira.contracts import FetchAttempt
    from mira.extract import Extracted
    from mira.fetch import Fetcher
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=uuid4(), base_url="https://other.org", connector_config={})
    scout = WebScout("unused", None, Fetcher(AllowList([source, other])))
    ctx = context()
    task = SimpleNamespace(max_documents=1, source_ids=(source.id,))
    run = _ScoutRun(scout, None, ctx, uuid4(), task)
    url = "https://example.org/redirect"
    future = Future()
    future.set_result((Extracted("other", "complete", ["text"]), _Visit("https://other.org/a", uuid4()),
                       FetchAttempt(url=url, outcome="saved", document_version_id=uuid4(), error=None, attempted_at=datetime.now(UTC))))
    scout._pages[(ctx.workspace_id, ctx.analysis_run_id, url)] = future
    assert run._fetch(url) is None
    assert run.log[-1].outcome == "refused"
    assert not run.visits


def test_offline_browser_requires_source_opt_in_and_never_sees_non_html():
    from datetime import UTC, datetime
    from mira.browser_capture import OfflineBrowserCapture
    from mira.fetch import FetchedPage
    calls = []
    adapter = OfflineBrowserCapture(renderer=lambda body, timeout: calls.append(body) or b"<p>Rendered</p>")
    def page(source, kind="html"):
        return FetchedPage("https://example.org/a", "https://example.org/a", source, kind, "text/html", b"<p>source</p>", datetime.now(UTC))
    assert adapter.capture(page(HKMA)) is None
    permitted = replace(HKMA, connector_config={"allow_browser": True})
    assert adapter.capture(page(permitted, "pdf")) is None
    assert adapter.capture(page(permitted)).body == b"<p>Rendered</p>"
    assert calls == [b"<p>source</p>"]


def test_scout_saves_offline_capture_with_original_hash():
    import hashlib
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun
    from mira.browser_capture import OfflineBrowserCapture
    from mira.fetch import FetchedPage
    from test_orchestrator import context
    source = replace(HKMA, connector_config={"allow_browser": True})
    url = "https://www.hkma.gov.hk/a"
    page = FetchedPage(url, url, source, "html", "text/html", b"<script>data</script>", datetime.now(UTC))
    fetcher = SimpleNamespace(fetch=lambda _: page, allow=SimpleNamespace(allows=lambda _: True))
    browser = OfflineBrowserCapture(renderer=lambda body, timeout: b"<p>Rendered publication</p>")
    scout = WebScout("unused", None, fetcher, browser=browser)
    run = _ScoutRun(scout, None, context(), uuid4(), SimpleNamespace(max_documents=1, source_ids=(source.id,)))
    saved = []
    run.writer = SimpleNamespace(save=lambda page, extracted, provenance: saved.append((page, extracted, provenance)) or SimpleNamespace(unchanged=False, document_version_id=uuid4(), passage_ids=[]))
    run._fetch_new(url)
    assert saved[0][1].text == "Rendered publication"
    assert saved[0][2]["original_capture_sha256"] == hashlib.sha256(page.body).hexdigest()
    assert saved[0][2]["acquisition_method"] == "offline_browser"


def test_refusal_in_one_task_does_not_poison_other_task_cache():
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun
    from mira.fetch import FetchedPage, Fetcher, RawResponse
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=uuid4(), base_url="https://other.org", connector_config={})
    class Web:
        def get(self, url, headers, timeout, max_bytes):
            return RawResponse(404, {}, b"") if url.endswith("robots.txt") else RawResponse(200, {"content-type": "text/html"}, b"<p>Allowed</p>")
    scout = WebScout("unused", None, Fetcher(AllowList([source, other]), transport=Web(), resolver=lambda _: ["93.184.216.34"], sleep=lambda _: None))
    ctx = context()
    denied = _ScoutRun(scout, None, ctx, uuid4(), SimpleNamespace(max_documents=1, source_ids=(source.id,)))
    allowed = _ScoutRun(scout, None, ctx, uuid4(), SimpleNamespace(max_documents=1, source_ids=(other.id,)))
    allowed.writer = SimpleNamespace(save=lambda *args: SimpleNamespace(unchanged=False, document_version_id=uuid4(), passage_ids=[]))
    url = "https://other.org/a"
    assert denied._fetch(url) is None
    assert allowed._fetch(url).text == "Allowed"


def test_exa_query_domains_are_limited_to_the_task_sources():
    import json
    from mira.discovery import ExaHTTP
    from uuid import uuid4
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=uuid4(), base_url="https://other.org", connector_config={})
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"results": []}'
    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return Response()
    adapter = ExaDiscovery(search=ExaHTTP("secret", domains=["example.org", "other.org"], opener=Opener()))
    adapter.discover("AML", [source.id], AllowList([source, other]), date(2026, 1, 1))
    assert requests[0]["includeDomains"] == ["example.org"]


def test_browser_timeout_kills_the_subprocess_group(monkeypatch):
    import subprocess
    from mira import browser_capture
    killed = []
    class Process:
        pid = 12345
        returncode = None
        def communicate(self, input=None, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("browser", timeout)
            return (b"", b"")
    monkeypatch.setattr(browser_capture.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(browser_capture.os, "killpg", lambda pid, sig: killed.append(pid))
    import pytest
    with pytest.raises(subprocess.TimeoutExpired):
        browser_capture._render(b"<p>x</p>", 1)
    assert killed == [12345]


def test_exa_real_transport_has_hard_timeout_and_sends_key_via_stdin(monkeypatch):
    import json
    from types import SimpleNamespace
    from mira import discovery
    seen = []
    def run(args, **kwargs):
        seen.append((args, kwargs))
        return SimpleNamespace(stdout=b'{"results": []}')
    monkeypatch.setattr(discovery.subprocess, "run", run)
    assert discovery.ExaHTTP("secret", domains=["example.org"])("AML", 2, 3) == []
    args, kwargs = seen[0]
    assert "secret" not in str(args)
    assert json.loads(kwargs["input"])["key"] == "secret"
    assert kwargs["timeout"] == 3


def test_scout_stops_before_fetch_when_task_time_is_exhausted(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents import scout as module
    from mira.agents.scout import WebScout, _ScoutRun
    from test_orchestrator import context
    clock = iter([0.0, 61.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    run = _ScoutRun(WebScout("unused", None, SimpleNamespace()), None, context(), uuid4(),
                    SimpleNamespace(max_documents=1, max_minutes=1, source_ids=()))
    assert run._fetch("https://example.org/a") is None
    assert run.log[-1].outcome == "refused"
    assert run.allowance == 1


def test_overlapping_task_scopes_share_concurrent_acquisition():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun
    from mira.fetch import Fetcher, RawResponse
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=uuid4(), base_url="https://other.org", connector_config={})
    entered, release = Event(), Event()
    calls, saves = [], []
    class Web:
        def get(self, url, headers, timeout, max_bytes):
            if url.endswith("robots.txt"):
                return RawResponse(404, {}, b"")
            calls.append(url)
            entered.set()
            assert release.wait(5)
            return RawResponse(200, {"content-type": "text/html"}, b"<p>Allowed</p>")
    scout = WebScout("unused", None, Fetcher(AllowList([source, other]), transport=Web(), resolver=lambda _: ["93.184.216.34"], sleep=lambda _: None))
    ctx = context()
    runs = [_ScoutRun(scout, None, ctx, uuid4(), SimpleNamespace(max_documents=1, source_ids=ids))
            for ids in ((source.id,), (source.id, other.id))]
    for run in runs:
        run.writer = SimpleNamespace(save=lambda *a: saves.append(1) or SimpleNamespace(unchanged=False, document_version_id=uuid4(), passage_ids=[]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runs[0]._fetch, "https://example.org/a")
        assert entered.wait(5)
        second = pool.submit(runs[1]._fetch, "https://example.org/a")
        release.set()
        assert first.result().text == second.result().text == "Allowed"
    assert len(calls) == len(saves) == 1
    assert sorted(run.allowance for run in runs) == [0, 1]


def test_redirect_refusal_does_not_poison_wider_task():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from uuid import uuid4
    from mira.agents.scout import WebScout, _ScoutRun
    from mira.fetch import Fetcher, RawResponse
    from test_orchestrator import context
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    other = replace(HKMA, id=uuid4(), base_url="https://other.org", connector_config={})
    entered, release = Event(), Event()
    class Web:
        def get(self, url, headers, timeout, max_bytes):
            if url.endswith("robots.txt"): return RawResponse(404, {}, b"")
            if url == "https://example.org/a":
                entered.set()
                assert release.wait(5)
                return RawResponse(302, {"location": "https://other.org/b"}, b"")
            return RawResponse(200, {"content-type": "text/html"}, b"<p>Allowed</p>")
    scout = WebScout("unused", None, Fetcher(AllowList([source, other]), transport=Web(), resolver=lambda _: ["93.184.216.34"], sleep=lambda _: None))
    ctx = context()
    narrow = _ScoutRun(scout, None, ctx, uuid4(), SimpleNamespace(max_documents=1, source_ids=(source.id,)))
    wide = _ScoutRun(scout, None, ctx, uuid4(), SimpleNamespace(max_documents=1, source_ids=(source.id, other.id)))
    wide.writer = SimpleNamespace(save=lambda *args: SimpleNamespace(unchanged=False, document_version_id=uuid4(), passage_ids=[]))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(narrow._fetch, "https://example.org/a")
        assert entered.wait(5)
        second = pool.submit(wide._fetch, "https://example.org/a")
        release.set()
        assert first.result() is None
        assert second.result().text == "Allowed"


def test_exa_applies_as_of_before_provider_result_limit():
    import json
    from mira.discovery import ExaHTTP
    requests = []
    source = replace(HKMA, base_url="https://example.org", connector_config={})
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return b'{"results": []}'
    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return Response()
    ExaDiscovery(search=ExaHTTP("secret", domains=["example.org"], opener=Opener())).discover(
        "AML", [source.id], AllowList([source]), date(2026, 1, 1))
    assert requests[0]["endPublishedDate"] == "2026-01-01T23:59:59.999Z"
