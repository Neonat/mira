"""Bounded URL-only discovery. Results are untrusted and never evidence."""
from __future__ import annotations

from datetime import date
import subprocess
import sys
import os
from typing import Callable
from uuid import UUID

from mira.extract import Link, parse_date
from mira.fetch import AllowList, FetchRefused


class ExaDiscovery:
    """Adapt an explicitly supplied search callable; no network access by default.

    The callable receives (query, result_limit, timeout_seconds). It must enforce
    its own timeout and return metadata dictionaries, not publisher content.
    """
    def __init__(self, *, search: Callable, max_results: int = 10, timeout: float = 5) -> None:
        if not 1 <= max_results <= 25 or not 0 < timeout <= 10:
            raise ValueError("discovery bounds exceeded")
        self.search, self.max_results, self.timeout = search, max_results, timeout

    def with_timeout(self, remaining: float) -> "ExaDiscovery":
        return ExaDiscovery(search=self.search, max_results=self.max_results, timeout=min(self.timeout, remaining))

    def discover(self, query: str, source_ids: list[UUID], allow: AllowList, as_of: date) -> list[Link]:
        search = self.search
        if hasattr(search, "for_domains"):
            domains = allow.domains_for_sources(source_ids)
            if not domains:
                return []
            search = search.for_domains(domains, as_of)
        results = search(query[:1000], self.max_results, self.timeout)
        links = []
        for item in results[:self.max_results]:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            url = item["url"]
            try:
                source = allow.source_for(url)
            except (FetchRefused, ValueError):
                continue
            if source.id not in source_ids or not {"fetch", "store_text"} <= set(source.permitted_operations):
                continue
            published = parse_date(str(item.get("publishedDate") or ""))
            if published and published > as_of:
                continue
            title = str(item.get("title") or "")[:200]
            links.append(Link(url, title, "URL discovered by search provider"))
        return links


class ExaHTTP:
    """Fixed-endpoint, URL-only Exa transport; enabled only when constructed."""
    def __init__(self, api_key: str, *, domains: list[str], opener=None, as_of: date | None = None) -> None:
        import urllib.request
        if not api_key or not domains:
            raise ValueError("API key and allowed domains required")
        self._key = api_key
        self._domains = list(domains)
        self._as_of = as_of
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self._opener = opener

    def for_domains(self, domains: list[str], as_of: date) -> "ExaHTTP":
        selected = sorted(set(domains) & set(self._domains))
        if not selected:
            raise ValueError("no task domains are enabled")
        return ExaHTTP(self._key, domains=selected, opener=self._opener, as_of=as_of)

    def __call__(self, query: str, limit: int, timeout: float) -> list[dict]:
        import json
        import urllib.request
        data = json.dumps({"query": query, "type": "auto", "numResults": limit,
                           "includeDomains": self._domains}).encode()
        if self._as_of is not None:
            payload = json.loads(data)
            payload["endPublishedDate"] = self._as_of.isoformat() + "T23:59:59.999Z"
            data = json.dumps(payload).encode()
        request = urllib.request.Request("https://api.exa.ai/search", data=data, method="POST",
                                         headers={"x-api-key": self._key, "Content-Type": "application/json"})
        try:
            if self._opener is None:
                payload = json.dumps({"key": self._key, "data": json.loads(data), "timeout": timeout}).encode()
                completed = subprocess.run([sys.executable, "-c", _EXA_SCRIPT], input=payload,
                                           capture_output=True, timeout=timeout, check=True,
                                           env={"PATH": os.defpath})
                body = completed.stdout
            else:
                with self._opener.open(request, timeout=timeout) as response:
                    body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("response exceeds limit")
            result = json.loads(body)
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise ValueError("invalid response")
            return result["results"][:limit]
        except Exception:
            raise RuntimeError("Exa discovery failed") from None


_EXA_SCRIPT = r"""
import json, sys, urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
try:
    value = json.load(sys.stdin)
    req = urllib.request.Request("https://api.exa.ai/search", data=json.dumps(value["data"]).encode(),
        method="POST", headers={"x-api-key": value["key"], "Content-Type": "application/json"})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=value["timeout"]) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000: raise ValueError("oversize")
    sys.stdout.buffer.write(data)
except Exception:
    sys.exit(1)
"""
