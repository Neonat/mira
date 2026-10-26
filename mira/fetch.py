"""``fetch_allowed``: the only way Mira reaches the web (PRD v2 §5.3; checker finding C2).

A URL is fetched only if all of these hold, and they are checked again on every
redirect hop:

- scheme is http or https, with no credentials and a default port
- the host is the base host of an active source permitted to ``fetch``, or one
  of that source's ``connector_config.extra_hosts``
- every address the host resolves to is public (no private, loopback,
  link-local or reserved ranges)
- ``robots.txt`` allows our user agent; an unreachable ``robots.txt`` (5xx)
  means disallow, a missing one (4xx) means allow (RFC 9309)

Requests to one host are spaced by the larger of the source's crawl delay, the
robots.txt crawl delay and one second. Responses are capped in size and limited
to HTML, PDF and RSS/Atom. The user agent is honest and never disguised.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

from mira.store import SourceRecord

USER_AGENT = "MiraResearchPrototype/0.1"
MAX_BYTES = 15_000_000
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 30.0
MIN_DELAY_SECONDS = 1.0

PageKind = Literal["html", "pdf", "feed"]
CONTENT_KINDS: dict[str, PageKind] = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/pdf": "pdf",
    "application/rss+xml": "feed",
    "application/atom+xml": "feed",
    "application/xml": "feed",
    "text/xml": "feed",
}


class FetchRefused(Exception):
    """The URL is outside policy. Logged as ``refused``; never retried."""


class FetchFailed(Exception):
    """The fetch was allowed but did not produce a usable page. Logged as ``failed``."""


class SiteBlocked(FetchFailed):
    """The site served a block page. ``repeated`` means no request was sent this time."""

    def __init__(self, message: str, repeated: bool) -> None:
        super().__init__(message)
        self.repeated = repeated


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> RawResponse: ...


class UrllibTransport:
    """Plain GET that never follows redirects itself, so each hop is re-checked."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            return None

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(self._NoRedirect())

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> RawResponse:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            response = self._opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read(max_bytes + 1) if exc.fp else b""
            return RawResponse(exc.code, {k.lower(): v for k, v in exc.headers.items()}, body)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchFailed(f"network error: {exc}") from exc
        with response:
            body = response.read(max_bytes + 1)
            return RawResponse(response.status, {k.lower(): v for k, v in response.headers.items()}, body)


Resolver = Callable[[str], Iterable[str]]


def resolve_addresses(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror as exc:
        raise FetchFailed(f"cannot resolve {host}: {exc}") from exc


@dataclass(frozen=True)
class FetchedPage:
    url: str
    requested_url: str
    source: SourceRecord
    kind: PageKind
    content_type: str
    body: bytes
    fetched_at: datetime


class AllowList:
    """Maps each permitted host to the source it belongs to."""

    def __init__(self, sources: Iterable[SourceRecord]) -> None:
        self._hosts: dict[str, SourceRecord] = {}
        for source in sources:
            if "fetch" not in source.permitted_operations or not source.base_url:
                continue
            hosts = {urlsplit(source.base_url).hostname or ""}
            hosts.update(source.connector_config.get("extra_hosts", []))
            for host in hosts:
                if host:
                    self._hosts[host.lower()] = source

    def source_for(self, url: str) -> SourceRecord:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise FetchRefused(f"scheme {parts.scheme!r} is not allowed")
        if parts.username or parts.password:
            raise FetchRefused("URLs with credentials are not allowed")
        if parts.port not in (None, 80, 443):
            raise FetchRefused(f"port {parts.port} is not allowed")
        host = (parts.hostname or "").lower()
        if host not in self._hosts:
            raise FetchRefused(f"host {host!r} is not on the allow-list")
        return self._hosts[host]

    def allows(self, url: str) -> bool:
        try:
            self.source_for(url)
        except FetchRefused:
            return False
        return True


@dataclass
class _HostState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_request: float | None = None
    robots: urllib.robotparser.RobotFileParser | None = None


class Fetcher:
    """Thread-safe; share one per run so per-host spacing holds across scouts."""

    def __init__(
        self,
        allow: AllowList,
        *,
        transport: Transport | None = None,
        resolver: Resolver = resolve_addresses,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.allow = allow
        self._transport = transport or UrllibTransport()
        self._resolver = resolver
        self._clock = clock
        self._sleep = sleep
        self._now = now
        self._hosts: dict[str, _HostState] = {}
        self._hosts_lock = threading.Lock()
        self._blocked: set[str] = set()

    def fetch(self, url: str) -> FetchedPage:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            source = self.allow.source_for(current)
            host = (urlsplit(current).hostname or "").lower()
            if host in self._blocked:
                raise SiteBlocked(f"{host} served a block page earlier in this run; not asked again", repeated=True)
            self._check_addresses(current)
            if not self._robots_allow(current, source):
                raise FetchRefused(f"robots.txt disallows {current}")
            response = self._get(current, source)
            if 300 <= response.status < 400:
                location = response.headers.get("location")
                if not location:
                    raise FetchFailed(f"HTTP {response.status} without a Location header")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise FetchFailed(f"HTTP {response.status}")
            if len(response.body) > MAX_BYTES:
                raise FetchFailed(f"response larger than {MAX_BYTES} bytes")
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            kind = CONTENT_KINDS.get(content_type)
            if kind is None and response.body.startswith(b"%PDF"):
                kind = "pdf"
            if kind is None:
                raise FetchFailed(f"content type {content_type or 'missing'!r} is not supported")
            # Some sites answer automated clients with HTTP 200 and a block page. It must
            # never be saved as evidence, and Mira does not try to get around it.
            for marker in source.connector_config.get("block_markers", []):
                if marker.encode() in response.body:
                    self._blocked.add(host)
                    raise SiteBlocked("the site served a block page to automated requests", repeated=False)
            return FetchedPage(current, url, source, kind, content_type, response.body, self._now())
        raise FetchFailed(f"more than {MAX_REDIRECTS} redirects")

    # --- Checks ---------------------------------------------------------------

    def _check_addresses(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        addresses = list(self._resolver(host))
        if not addresses:
            raise FetchFailed(f"{host} has no addresses")
        for address in addresses:
            if not ipaddress.ip_address(address.split("%")[0]).is_global:
                raise FetchRefused(f"{host} resolves to non-public address {address}")

    def _state(self, host: str) -> _HostState:
        with self._hosts_lock:
            return self._hosts.setdefault(host, _HostState())

    def _robots_allow(self, url: str, source: SourceRecord) -> bool:
        parts = urlsplit(url)
        state = self._state(parts.netloc.lower())
        if state.robots is None:
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            parser = urllib.robotparser.RobotFileParser(robots_url)
            response = self._get(robots_url, source)
            if response.status == 200:
                parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
            elif response.status >= 500:
                parser.disallow_all = True
            else:
                parser.allow_all = True
            state.robots = parser
        return state.robots.can_fetch(USER_AGENT, url)

    def _get(self, url: str, source: SourceRecord) -> RawResponse:
        parts = urlsplit(url)
        state = self._state(parts.netloc.lower())
        with state.lock:
            delay = max(MIN_DELAY_SECONDS, float(source.connector_config.get("crawl_delay_seconds", 0) or 0))
            if state.robots is not None:
                delay = max(delay, float(state.robots.crawl_delay(USER_AGENT) or 0))
            if state.last_request is not None:
                wait = state.last_request + delay - self._clock()
                if wait > 0:
                    self._sleep(wait)
            try:
                return self._transport.get(
                    url,
                    {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,application/rss+xml,application/xml;q=0.9,*/*;q=0.1"},
                    TIMEOUT_SECONDS,
                    MAX_BYTES,
                )
            finally:
                state.last_request = self._clock()
