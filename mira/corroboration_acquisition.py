"""Bounded acquisition primitives for optional targeted corroboration."""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from uuid import UUID

from mira.extract import Extracted, Link, extract
from mira.fetch import AllowList, Fetcher, FetchedPage
from mira.store import SourceRecord
from mira.evidence import EvidenceWriter
from mira.pg_store import PostgresStore
from mira.agents.scout import _safe_url, document_key

_MAX_RESPONSE = 24_000_000


class AcquisitionRefused(RuntimeError):
    """Per-document failure; the broker remains usable."""


class BoundedFetcher:
    """One persistent policy-enforcing broker; timeout permanently closes it."""
    def __init__(self, sources: list[SourceRecord], *, command: list[str] | None = None) -> None:
        self.sources = {str(source.id): source for source in sources}
        self.process = subprocess.Popen(command or [sys.executable, "-m", "mira.corroboration_acquisition", "--broker"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        start_new_session=True, bufsize=0)
        self._init = json.dumps([dataclasses.asdict(s) for s in sources], default=str).encode() + b"\n"
        self._lock = threading.Lock()
        self._buffer = bytearray()
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait()
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()

    def fetch(self, url: str, source_ids: set[UUID], *, timeout_seconds: float) -> tuple[FetchedPage, Extracted]:
        deadline = time.monotonic() + timeout_seconds
        if timeout_seconds <= 0 or not self._lock.acquire(timeout=max(0, timeout_seconds)):
            raise TimeoutError("acquisition deadline reached")
        try:
            if self.process.poll() is not None:
                raise RuntimeError("acquisition broker unavailable")
            request = self._init + json.dumps({"url": url, "source_ids": [str(x) for x in source_ids]}).encode() + b"\n"
            self._init = b""
            selector = selectors.DefaultSelector()
            try:
                selector.register(self.process.stdin, selectors.EVENT_WRITE)
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("acquisition deadline reached")
                    events = selector.select(remaining)
                    if not events:
                        raise TimeoutError("acquisition deadline reached")
                    for key, _ in events:
                        if key.fileobj is self.process.stdin:
                            count = os.write(key.fd, request[:65536])
                            request = request[count:]
                            if not request:
                                selector.unregister(self.process.stdin)
                        else:
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                raise RuntimeError("acquisition broker stopped")
                            self._buffer.extend(chunk)
                            if len(self._buffer) > _MAX_RESPONSE:
                                raise RuntimeError("acquisition response exceeds limit")
                            if b"\n" in self._buffer:
                                line, _, rest = self._buffer.partition(b"\n")
                                self._buffer = bytearray(rest)
                                return self._decode(json.loads(line))
            finally:
                selector.close()
        except AcquisitionRefused:
            raise
        except (TimeoutError, OSError, ValueError, RuntimeError):
            self.close()
            raise
        finally:
            self._lock.release()

    def _decode(self, response: dict) -> tuple[FetchedPage, Extracted]:
        if "error" in response:
            raise AcquisitionRefused(response["error"])
        p, e = response["page"], response["extracted"]
        page = FetchedPage(p["url"], p["requested_url"], self.sources[p["source_id"]], p["kind"],
                           p["content_type"], base64.b64decode(p["body"], validate=True), datetime.fromisoformat(p["fetched_at"]))
        from datetime import date
        links = [Link(x["url"], x["text"], x["context"], date.fromisoformat(x["published"]) if x["published"] else None,
                      x["date_source"]) for x in e["links"]]
        extracted = Extracted(e["title"], e["status"], e["pages"], links,
                              date.fromisoformat(e["published"]) if e["published"] else None,
                              e["error"], e["published_basis"])
        return page, extracted



class CorroborationDiscovery:
    """Discover URLs and return only permitted, current, saved evidence."""
    def __init__(self, conn, sources: list[SourceRecord], discovery, *, broker=None, browser=None) -> None:
        self.conn, self.sources, self.discovery, self.browser = conn, list(sources), discovery, browser
        self.allow = AllowList(self.sources)
        self.broker = broker or BoundedFetcher(self.sources)

    def close(self) -> None:
        self.broker.close()

    def discover(self, query: str, *, ctx, source_ids: tuple[UUID, ...], max_documents: int,
                 max_passages: int, timeout_seconds: float):
        from mira.corroboration import CandidateEvidence, DiscoveryBatch, FrozenPassage
        deadline = time.monotonic() + timeout_seconds
        candidates, errors, attempts = [], [], 0
        allowed_ids = {s.id for s in self.sources if s.id in source_ids
                       and {"fetch", "store_text"} <= set(s.permitted_operations)}
        def remaining():
            return max(0.0, deadline - time.monotonic())
        def result():
            return DiscoveryBatch(candidates=candidates, document_attempts=attempts,
                                  tokens_in=0, tokens_out=0, errors=errors)
        if timeout_seconds <= 0 or max_documents <= 0 or max_passages <= 0 or not allowed_ids:
            return result()
        try:
            links = self.discovery.with_timeout(remaining()).discover(
                query, list(allowed_ids), self.allow, ctx.brief.as_of_date)
        except Exception as exc:
            errors.append(f"discovery: {type(exc).__name__}")
            return result()
        seen = set()
        for link in links:
            if attempts >= max_documents or len(candidates) >= max_passages:
                break
            if remaining() <= 0:
                errors.append("acquisition: time limit")
                break
            try:
                source = self.allow.source_for(link.url)
                if source.id not in allowed_ids or link.url in seen:
                    continue
            except Exception:
                continue
            seen.add(link.url)
            attempts += 1
            try:
                page, extracted = self.broker.fetch(link.url, allowed_ids, timeout_seconds=remaining())
                if page.source.id not in allowed_ids:
                    raise ValueError("source outside scope")
                with self.conn.transaction():
                    millis = max(1, int(remaining() * 1000))
                    self.conn.execute(f"SET LOCAL statement_timeout = {millis}", ())
                    self.conn.execute(f"SET LOCAL lock_timeout = {millis}", ())
                    fresh = {s.id: s for s in PostgresStore(self.conn).list_sources(ctx.workspace_id)}.get(page.source.id)
                if (fresh is None or not {"fetch", "store_text"} <= set(fresh.permitted_operations)
                        or AllowList([fresh]).source_for(page.url).id != fresh.id):
                    errors.append(f"acquisition {_safe_url(link.url)}: source permission revoked")
                    continue
                page = dataclasses.replace(page, source=fresh)
                provenance = {}
                if (self.browser is not None and page.kind == "html" and not extracted.text
                        and remaining() > 0):
                    import hashlib
                    captured = self.browser.with_timeout(remaining()).capture(page)
                    if captured is not None:
                        rendered = extract(captured)
                        if rendered.text:
                            provenance = {"acquisition_method": "offline_browser",
                                          "original_capture_sha256": hashlib.sha256(page.body).hexdigest()}
                            page, extracted = captured, rendered
                if remaining() <= 0:
                    errors.append("acquisition: time limit")
                    break
                if extracted.published and extracted.published > ctx.brief.as_of_date:
                    errors.append("publication after as-of date")
                    continue
                with self.conn.transaction():
                    def limit_sql():
                        left = remaining()
                        if left <= 0:
                            raise TimeoutError("acquisition deadline reached")
                        millis = max(1, int(left * 1000))
                        self.conn.execute(f"SET LOCAL statement_timeout = {millis}", ())
                        self.conn.execute(f"SET LOCAL lock_timeout = {millis}", ())
                    limit_sql()
                    self.conn.execute("select id from public.sources where workspace_id = %s and id = %s for share",
                                      (ctx.workspace_id, page.source.id))
                    limit_sql()
                    fresh = {s.id: s for s in PostgresStore(self.conn).list_sources(ctx.workspace_id)}.get(page.source.id)
                    if fresh is None or not {"fetch", "store_text"} <= set(fresh.permitted_operations):
                        errors.append(f"acquisition {_safe_url(link.url)}: source permission revoked")
                        continue
                    if AllowList([fresh]).source_for(page.url).id != fresh.id:
                        errors.append(f"acquisition {_safe_url(link.url)}: source permission revoked")
                        continue
                    page = dataclasses.replace(page, source=fresh)
                    limit_sql()
                    saved = EvidenceWriter(self.conn, ctx.workspace_id, ctx.user_id).save(page, extracted, provenance, deadline=deadline)
                    limit_sql()
                    if extracted.status not in ("complete", "partial") or extracted.error or not extracted.text:
                        errors.append(f"extraction {_safe_url(link.url)}: {extracted.status}; version {saved.document_version_id}")
                    row = self.conn.execute(
                        """select id from public.document_versions where workspace_id = %s
                           and document_id = %s and (published_at is null or published_at::date <= %s)
                           order by version_number desc limit 1""",
                        (ctx.workspace_id, saved.document_id, ctx.brief.as_of_date)).fetchone()
                    if row is None or row["id"] != saved.document_version_id:
                        errors.append("saved version is not current eligible evidence")
                        continue
                    limit_sql()
                    passages = PostgresStore(self.conn).get_passages(ctx.workspace_id, saved.passage_ids)
                    limit_sql()
                    found = []
                    for passage in passages:
                        if len(candidates) + len(found) >= max_passages:
                            break
                        if passage.source_id not in allowed_ids:
                            continue
                        frozen = FrozenPassage(**dataclasses.asdict(passage))
                        found.append(CandidateEvidence(
                            passage=frozen, workspace_id=ctx.workspace_id, eligible=True, current=True,
                            publication_id=document_key(passage.source_url), organization_id=str(passage.source_id),
                            origin_id=None))
                    if remaining() <= 0:
                        raise TimeoutError("acquisition deadline reached")
                candidates.extend(found)
            except Exception as exc:
                errors.append(f"acquisition {_safe_url(link.url)}: {type(exc).__name__}")
        return result()

def _broker() -> None:
    raw_sources = json.loads(sys.stdin.buffer.readline())
    for source in raw_sources:
        source["id"] = UUID(source["id"])
        source["permitted_operations"] = tuple(source["permitted_operations"])
    fetcher = Fetcher(AllowList(SourceRecord(**source) for source in raw_sources))
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            page = fetcher.fetch(request["url"], source_ids={UUID(x) for x in request["source_ids"]})
            extracted = extract(page)
            payload = {"page": {"url": page.url, "requested_url": page.requested_url,
                                "source_id": str(page.source.id), "kind": page.kind,
                                "content_type": page.content_type, "body": base64.b64encode(page.body).decode(),
                                "fetched_at": page.fetched_at.isoformat()},
                       "extracted": dataclasses.asdict(extracted)}
        except Exception as exc:
            payload = {"error": type(exc).__name__}
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__" and sys.argv[1:] == ["--broker"]:
    _broker()
