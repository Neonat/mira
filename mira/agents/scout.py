"""Scouts: find and save the publications for one plan task (PRD v2 §5.2, AG04-AG05).

A scout is a bounded loop with code-owned tools:

1. Fetch the task's sources' feeds and hub pages through ``fetch_allowed`` and
   save every page before any model reads it.
2. Up to ``max_rounds`` times, show the model the new links found (as untrusted
   data, with dates where known) and fetch the ones it picks, within the task's
   document allowance.
3. Add passages already in the evidence store: a full-text search, plus the
   task's own sources' documents published in the period or imported by hand.
4. Show the model the most relevant saved passages and ask for a ``ScoutReport``:
   documents with the passage labels that matter, and a status for each
   expected source assigned to the task.

Every fetch attempt, refused and failed included, goes into the fetch log. The
scout never writes outside the evidence tables and never sees database IDs.
"""

from __future__ import annotations

import re
import hashlib
import threading
import time
from html import escape
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID
from urllib.parse import urldefrag, urlsplit, urlunsplit, parse_qsl, urlencode

from mira.agents.common import NO_CONCLUSIONS_RULE, UNTRUSTED_TEXT_RULE, brief_text, quote_passage
from mira.agents.temporal import TEMPORAL_RULE
from mira.contracts import FetchAttempt, LabelMap, LinkSelection, ScoutReport, ScoutResult
from mira.db import connect
from mira.evidence import EvidenceWriter
from mira.extract import Extracted, Link, extract
from mira.fetch import Fetcher, FetchFailed, FetchRefused, SiteBlocked
from mira.interfaces import ScoutFailure, ScoutOutcome, ScoutTask
from mira.llm import LLMClient, LLMError, LLMResult, call_checked
from mira.pg_store import PostgresStore
from mira.store import PassageRecord, RunContext
from mira.sfc import search_payload
from mira.topics import AML_TERMS, CYBER_TERMS, CYBERSECURITY, CYBER_SOURCE_ROUTES

PROMPT_VERSION = "scout/7"
MAX_LINKS_SHOWN = 120
MAX_DIAGNOSTIC_RECORDS = 300


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode([(k[:80], v[:200] if k.lower() in {"refno", "lang", "year", "category"} else "[redacted]")
                       for k, v in parse_qsl(parts.query, keep_blank_values=True)[:20]])
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path[:1000], query, ""))

MAX_PASSAGES_SHOWN = 40
MAX_PASSAGE_CHARS = 16_000
# Token-cap enforcement. A task's max_llm_tokens is checked before each call using a
# size estimate, so the cap holds approximately rather than only between calls.
CHARS_PER_TOKEN = 4
SELECTION_OUTPUT_TOKENS = 500
REPORT_OUTPUT_TOKENS = 16_384
# The report call always runs, so pages already fetched are not wasted. Below this
# many passage characters it would have too little evidence to be useful.
MIN_PASSAGE_CHARS = 8_000
# Splitting selection is useful only when there is time for another model call.
MIN_TWO_ROUND_SECONDS = 60


def estimate_tokens(text: str) -> int:
    """Rough prompt size; deliberately simple, used only to stay within a task's cap."""
    return len(text) // CHARS_PER_TOKEN + 1
STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "were", "what", "which", "into", "between",
             "their", "have", "has", "are", "was", "any", "how", "did", "does", "on", "of", "in", "to", "a", "an"}

LINK_SYSTEM = f"""You are a research scout for Mira, a research assistant for bank internal auditors.
You are given a research question, a period and links found on allow-listed regulator and industry pages.
Pick the links most likely to lead to publications that answer the question within the period: rules, guidelines, circulars, consultations, enforcement actions, policy statements, or the documents (often PDFs) they link to.
Skip navigation, unrelated topics and anything clearly outside the period. Pick at most the number allowed; pick none if nothing fits.
Prefer primary documents over RSS summaries or duplicate landing pages. Cover different assigned sources and missing categories before opening more documents about an already covered item.
When dated publications in the requested period are available, read those before more hubs, navigation pages, or general guidelines without a recent change. Select several distinct relevant publications when the allowance permits.
- {UNTRUSTED_TEXT_RULE}"""

REPORT_SYSTEM = f"""You are a research scout for Mira, a research assistant for bank internal auditors.
From the saved passages, list the documents that answer the research question within the period, citing the passage labels that matter (P1, P2).
For each document give its instrument type or industry category, title, dates and whether it is new, amended or upcoming, using only what the passages state; use null when unknown.
For each expected source, say found (a relevant development in the period), no_change (the relevant publication or category was inspected and shows nothing new in the period) or missing (it could not be checked).
For no_change, list the inspected_passage_labels that show the relevant publication, index or category you actually checked for this specific checklist item. A page from the same publisher on another subject is insufficient. If that evidence is unavailable, use missing. You may list inspection evidence even when there are no relevant developments to put in documents.
The passages are a bounded selection and do not represent all saved evidence. Do not infer found or no_change from omitted evidence; use missing when the shown passages do not establish the status.
Listing nothing is a valid answer. Never fill gaps from memory.
- {TEMPORAL_RULE}
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""


class _SummaryClient:
    """Keep report generation bounded without changing the shared client contract."""

    def __init__(self, run):
        self.run = run

    def structured(self, **kwargs):
        client = self.run.scout.client
        try:
            if not hasattr(client, "structured_bounded"):
                return client.structured(**kwargs)
            remaining = self.run._remaining_seconds()
            timeout = 120 if remaining is None else min(120, remaining)
            if timeout <= 0:
                error = LLMError("report time limit reached")
                error.request_sent = False
                raise error
            from mira.llm import request_token_reservation
            remaining_tokens = self.run._remaining_tokens()
            reservation = request_token_reservation(system=kwargs["system"], user=kwargs["user"],
                                                    output_type=kwargs["output_type"],
                                                    max_output_tokens=REPORT_OUTPUT_TOKENS)
            if remaining_tokens is not None and reservation > remaining_tokens:
                error = LLMError("report token limit reached")
                error.request_sent = False
                raise error
            return client.structured_bounded(timeout_seconds=timeout,
                                             max_output_tokens=REPORT_OUTPUT_TOKENS, **kwargs)
        except LLMError as exc:
            if getattr(exc, "request_sent", None) is not False:
                reserved = getattr(exc, "reserved_tokens", 0) or 0
                if not reserved and not (exc.tokens_in or exc.tokens_out):
                    from mira.llm import request_token_reservation
                    reserved = request_token_reservation(system=kwargs["system"], user=kwargs["user"],
                                                         output_type=kwargs["output_type"],
                                                         max_output_tokens=REPORT_OUTPUT_TOKENS)
                self.run.generation_reserved_tokens += reserved
            raise


@dataclass
class _Visit:
    url: str
    version_id: UUID | None
    passage_ids: list[UUID] = field(default_factory=list)


def _is_pdf(url: str) -> bool:
    from mira.publication_routes import is_publication_pdf
    lowered = url.lower()
    return lowered.split("?")[0].endswith(".pdf") or "getpdf" in lowered or is_publication_pdf(url)


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", text.lower()) if word not in STOPWORDS}


def document_key(url: str) -> str:
    """Only collapse explicitly recognised HKMA landing/PDF aliases, never whole feeds."""
    url = urldefrag(url)[0]
    from mira.publication_routes import register_document_key
    register_key=register_document_key(url)
    if register_key is not None:
        return 'au-register:'+register_key
    parts = urlsplit(url)
    if parts.hostname == "brdr.hkma.gov.hk":
        match = re.fullmatch(r"/(eng|chi)/doc-ldg/(?:(?:current|docId)/([^/]+)|docId/getPdf/([^/]+)/[^/]+\.pdf)", parts.path)
        if match:
            return f"hkma:{match[1]}:{match[2] or match[3]}"
    return url


def seed_plan(config: dict[str, object], categories: list[str], years: range) -> tuple[list[list[str]], list[str]]:
    """Index pages code opens before the model chooses anything, and the rest as candidates.

    Each assigned checklist category gets its own queue: that category's configured
    index pages for every requested year. Code opens the queues in turn, so a task
    covering circulars, guidelines and enforcement starts on all three indexes rather
    than relying on the model to pick the second and third. Feeds and start pages stay
    candidates; with no category pages configured, the first of them is the seed.
    """
    category_urls = config.get("category_urls", {})
    queues: list[list[str]] = []
    seen: set[str] = set()
    for category in categories:
        urls = [url.format(year=year) for url in category_urls.get(category, []) for year in years]
        urls = [url for url in dict.fromkeys(urls) if url not in seen]
        if urls:
            queues.append(urls)
            seen.update(urls)
    others = [url for url in dict.fromkeys([*config.get("feeds", []), *config.get("start_urls", [])])
              if url not in seen]
    if not queues and others:
        queues.append([others.pop(0)])
    return queues, others


def distinct_links(links: list[Link]) -> list[Link]:
    """Retain dated metadata for known aliases, preferring PDFs when equally dated."""
    selected: dict[str, Link] = {}
    for link in links:
        key = document_key(link.url)
        if key not in selected or (link.published is not None, _is_pdf(link.url)) > (
                selected[key].published is not None, _is_pdf(selected[key].url)):
            selected[key] = link
    return list(selected.values())


class WebScout:
    def __init__(self, dsn: str, client: LLMClient, fetcher: Fetcher, *, max_rounds: int = 2,
                 links_per_round: int = 8, discovery=None, browser=None, live_browser=None, hybrid=None, frontier=None,
                 archive_only: bool = False) -> None:
        self.dsn = dsn
        self.client = client
        self.fetcher = fetcher
        self.max_rounds = max_rounds
        self.links_per_round = links_per_round
        self.discovery_adapter = discovery
        self.browser_adapter = browser
        self.live_browser_adapter = live_browser
        self.hybrid = hybrid
        self.frontier = frontier
        self.archive_only = archive_only
        self._fetch_lock = threading.Lock()
        # Futures let concurrent tasks share one fetch/save, scoped to workspace and run.
        self._pages: dict[tuple[UUID, UUID, str], Future] = {}

    def run(self, ctx: RunContext, step_id: UUID, task: ScoutTask) -> ScoutOutcome:
        with connect(self.dsn) as conn:
            run = _ScoutRun(self, conn, ctx, step_id, task)
            try:
                return run.execute()
            except Exception as exc:
                tokens_in = run.tokens_in + (exc.tokens_in if isinstance(exc, LLMError) else 0)
                tokens_out = run.tokens_out + (exc.tokens_out if isinstance(exc, LLMError) else 0)
                diagnostics = {"discovered": run.discovery, "discovered_omitted": run.discovery_omitted,
                               "rounds": run.selection_diagnostics, "stop_reason": "exception",
                               "remaining_allowance": run.allowance, "hybrid": run.hybrid_diagnostics,
                               "summary": run.summary_diagnostics,
                               "generation_usage": {"reserved_tokens": run.generation_reserved_tokens or
                                                    (getattr(exc, "reserved_tokens", 0) if getattr(exc, "request_sent", None) is not False else 0)}}
                raise ScoutFailure(exc, run.log, diagnostics, run.model, PROMPT_VERSION,
                                   tokens_in, tokens_out) from exc


class _ScoutRun:
    archive_versions: list[UUID] | None = None

    def __init__(self, scout: WebScout, conn, ctx: RunContext, step_id: UUID, task: ScoutTask) -> None:  # noqa: ANN001
        self._started = time.monotonic()
        self.scout = scout
        self.conn = conn
        self.ctx = ctx
        self.step_id = step_id
        self.task = task
        self.store = PostgresStore(conn)
        self.writer = EvidenceWriter(conn, ctx.workspace_id, ctx.user_id)
        self.log: list[FetchAttempt] = []
        self.visits: list[_Visit] = []
        self.seen: set[str] = set()
        self.candidates: list[Link] = []
        self.publication_variants: dict[str, Link] = {}
        self.allowance = task.max_documents
        self.tokens_in = self.tokens_out = 0
        self.hybrid_tokens = 0
        self.hybrid_reserved_tokens = 0
        self.generation_reserved_tokens = 0
        self.summary_diagnostics = None
        self.hybrid_diagnostics = None
        self.token_stop = False
        self.model: str | None = None
        self.selection_diagnostics: list[dict] = []
        self.prior_selections: list[Link] = []
        self.deferred_alias_pdfs: set[str] = set()
        self.discovery: list[dict] = []
        self.discovery_omitted = 0
        self.origins: dict[int, tuple[Link, dict]] = {}

    def _record_discovery(self, links: list[Link], request_url: str, version_id: UUID | None) -> None:
        if self.scout.frontier is not None:
            self.scout.frontier.record(links, request_url, version_id)
        for link in links:
            origin = {"request_url": _safe_url(request_url), "document_version_id": str(version_id) if version_id else None}
            record = {"url": _safe_url(link.url), "date": link.published.isoformat() if link.published else None,
                      "reason": "seen" if link.url in self.seen else ("source_not_allowed" if not self.scout.fetcher.allow.allows(link.url) else "candidate"), **origin}
            if len(self.discovery) < MAX_DIAGNOSTIC_RECORDS:
                self.discovery.append(record)
                self.origins[id(link)] = (link, origin)
            else:
                self.discovery_omitted += 1

    def _remaining_seconds(self) -> float | None:
        minutes = getattr(self.task, "max_minutes", None)
        return None if minutes is None else max(0.0, minutes * 60 - (time.monotonic() - self._started))

    # --- Fetching -------------------------------------------------------------

    def _fetch(self, url: str, link: Link | None = None) -> Extracted | None:
        url = urldefrag(url)[0]
        if url in self.seen:
            return None
        remaining = self._remaining_seconds()
        if remaining is not None and remaining <= 0:
            self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None,
                                         error="task time limit reached", attempted_at=datetime.now(UTC)))
            return None
        scope = frozenset(getattr(self.task, "source_ids", ()))
        if isinstance(self.scout.fetcher, Fetcher):
            try:
                source = self.scout.fetcher.allow.source_for(url)
                if source.id not in scope:
                    raise FetchRefused("URL is outside the task source scope")
            except (FetchRefused, ValueError) as exc:
                self.seen.add(url)
                self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None,
                                             error=str(exc), attempted_at=datetime.now(UTC)))
                return None
        key = (self.ctx.workspace_id, self.ctx.analysis_run_id, url)
        with self.scout._fetch_lock:
            pending = self.scout._pages.get(key)
            owner = pending is None
            if owner:
                if self.allowance <= 0:
                    return None
                pending = Future()
                pending.source_scope = scope
                self.scout._pages[key] = pending
        if owner:
            allowance_start = self.allowance
            log_start = len(self.log)
            attempted_at = datetime.now(UTC)
            try:
                extracted = self._fetch_new(url, link)
                visit = self.visits[-1] if extracted is not None else None
                attempt = self.log[-1]
                with self.scout._fetch_lock:
                    if attempt.outcome == "refused" and self.scout._pages.get(key) is pending:
                        del self.scout._pages[key]
                    pending.set_result((extracted, visit, attempt))
                return extracted
            except BaseException as exc:
                if isinstance(exc, Exception) and len(self.log) == log_start:
                    # Unexpected transport/extraction/storage failures may occur
                    # before the normal fetch log is written. Retain and charge
                    # this owned attempt once, even if allowance was already used.
                    self.allowance = min(self.allowance, allowance_start - 1)
                    self.log.append(FetchAttempt(
                        url=url, outcome="failed", document_version_id=None,
                        error=f"unexpected fetch error: {type(exc).__name__}", attempted_at=attempted_at,
                    ))
                pending.set_exception(exc)
                raise
        extracted, visit, attempt = pending.result()
        if attempt.outcome == "refused":
            if getattr(pending, "source_scope", scope) != scope:
                return self._fetch(url, link)
            self.seen.add(url)
            self.log.append(attempt.model_copy(update={"attempted_at": datetime.now(UTC)}))
            return None
        if visit is not None and isinstance(self.scout.fetcher, Fetcher):
            try:
                source = self.scout.fetcher.allow.source_for(visit.url)
                if source.id not in self.task.source_ids:
                    raise FetchRefused("cached page is outside the task source scope")
            except (FetchRefused, ValueError) as exc:
                self.seen.add(url)
                self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None,
                                             error=str(exc), attempted_at=datetime.now(UTC)))
                return None
        self.seen.add(url)
        self.log.append(attempt.model_copy(update={"outcome": "reused", "attempted_at": datetime.now(UTC)}))
        if visit is not None:
            self.visits.append(visit)
            self.seen.add(visit.url)
        if extracted is not None:
            self._record_discovery(extracted.links, url, visit.version_id if visit else None)
            self.candidates.extend(link for link in extracted.links
                                   if link.url not in self.seen and self.scout.fetcher.allow.allows(link.url))
        return extracted

    def _fetch_new(self, url: str, link: Link | None = None) -> Extracted | None:
        if url in self.seen or self.allowance <= 0:
            return None
        self.seen.add(url)
        now = datetime.now(UTC)
        payload = search_payload(url)
        try:
            options = {"source_ids": set(self.task.source_ids)} if isinstance(self.scout.fetcher, Fetcher) else {}
            if payload is not None:
                options["json_body"] = payload
            page = self.scout.fetcher.fetch(url, **options)
        except FetchRefused as exc:
            self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None, error=str(exc), attempted_at=now))
            return None
        except FetchFailed as exc:
            if not (isinstance(exc, SiteBlocked) and exc.repeated):  # no request was sent
                self.allowance -= 1
            self.log.append(FetchAttempt(url=url, outcome="failed", document_version_id=None, error=str(exc), attempted_at=now,
                acquisition_method="http_fetch", request_sent=not (isinstance(exc,SiteBlocked) and exc.repeated)))
            if getattr(exc,"status_code",None) != 429:
                return self._acquire_live(url, "http_blocked", link)
            return None
        self.allowance -= 1
        extracted = extract(page)
        provenance = {"request_method": "POST", "request_json": payload} if payload is not None else {}
        if self.scout.live_browser_adapter is not None and page.kind == "html" and not extracted.text and self.allowance>0:
            from mira.live_browser import permitted
            remaining=self._remaining_seconds()
            if (remaining is None or remaining>0) and permitted(url,sources=self.store.list_sources(self.ctx.workspace_id),source_ids=set(self.task.source_ids),reason="js"):
                self._save_page(page,extracted,provenance,link)
                return self._acquire_live(url,"js",link) or extracted
        if self.scout.browser_adapter is not None and page.kind == "html" and not extracted.text:
            try:
                remaining = self._remaining_seconds()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("task time limit reached")
                adapter = self.scout.browser_adapter
                if remaining is not None and hasattr(adapter, "with_timeout"):
                    adapter = adapter.with_timeout(remaining)
                captured = adapter.capture(page)
                if captured is not None:
                    rendered = extract(captured)
                    if rendered.text:
                        provenance.update(acquisition_method="offline_browser",
                                          original_capture_sha256=hashlib.sha256(page.body).hexdigest())
                        page, extracted = captured, rendered
            except Exception as exc:
                extracted.error = f"offline browser failed: {type(exc).__name__}"
        return self._save_page(page,extracted,provenance,link)

    def _acquire_live(self, url, reason, link=None):
        adapter=self.scout.live_browser_adapter
        remaining=self._remaining_seconds()
        if adapter is None or self.allowance<=0 or (remaining is not None and remaining<=0):
            return None
        from mira.live_browser import permitted
        sources=self.store.list_sources(self.ctx.workspace_id)
        scope=set(self.task.source_ids)
        if not permitted(url,sources=sources,source_ids=scope,reason=reason):
            return None
        timeout=min(30.,remaining) if remaining is not None else 30.
        deadline=time.monotonic()+timeout
        self.allowance-=1
        navigated=False
        try:
            result=adapter.acquire(url,sources=sources,source_ids=scope,timeout_seconds=timeout,reason=reason)
            navigated=True
            def save():
                fresh=self.store.list_sources(self.ctx.workspace_id)
                if not permitted(url,sources=fresh,source_ids=scope,reason=reason):
                    raise FetchRefused("live-browser source permission changed")
                final=self.scout.fetcher.allow.source_for(result.page.url)
                current=next((s for s in fresh if s.id==final.id),None)
                if current is None or not permitted(result.page.url,sources=fresh,source_ids=scope,reason="js"):
                    raise FetchRefused("live-browser final source is no longer permitted")
                from dataclasses import replace
                page=replace(result.page,source=current)
                extracted=extract(page)
                if result.provenance.get("denied_requests"):
                    extracted.status="partial"
                    extracted.error="Browser subresources refused by source policy; rendered capture may be incomplete"
                return self._save_page(page,extracted,result.provenance,link,deadline=deadline)
            if self.conn is None:
                return save()
            with self.conn.transaction():
                left=deadline-time.monotonic()
                if left<=0:
                    raise TimeoutError("live-browser deadline reached")
                self.conn.execute("select set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                                  (str(max(1,int(left*1000))),str(max(1,int(left*1000)))))
                self.conn.execute("select id from public.sources where workspace_id=%s and id=any(%s) order by id for share",
                                  (self.ctx.workspace_id,list(scope)))
                return save()
        except FetchRefused as exc:
            sent=navigated or getattr(exc,"request_sent",True)
            if not sent:
                self.allowance+=1
            self.log.append(FetchAttempt(url=url,outcome="failed" if sent else "refused",document_version_id=None,error=str(exc),
                attempted_at=datetime.now(UTC),acquisition_method="live_browser",request_sent=sent,
                diagnostics=getattr(exc,"diagnostics",[])[:200]))
        except Exception as exc:
            self.log.append(FetchAttempt(url=url,outcome="failed",document_version_id=None,
                error=f"live browser failed: {type(exc).__name__}",attempted_at=datetime.now(UTC),acquisition_method="live_browser",
                diagnostics=getattr(exc,"diagnostics",[])[:200]))
        return None

    def _save_page(self,page,extracted,provenance,link=None,*,deadline=None):
        from mira.australia import is_register_api_url
        if (page.kind=='json' and urlsplit(page.url).path=='/v1/Documents'
                and is_register_api_url(page.url) and extracted.metadata.get('role')=='discovery_metadata'
                and link is not None and link.published and isinstance(link.date_source,str)
                and link.date_source.startswith('Federal Register API registeredAt in ')):
            extracted.links=[Link(child.url,child.text,child.context,link.published,link.date_source)
                             if child.published is None else child for child in extracted.links]
            extracted.metadata['availability']={'registered_at':link.published.isoformat(),'evidence':link.date_source}
        from mira.publication_routes import register_publication
        publication=register_publication(page.url)
        if publication is not None:
            publication=dict(publication)
            if (link is not None and link.published and isinstance(link.date_source,str)
                    and link.date_source.startswith('Federal Register API registeredAt in ')):
                if extracted.published is not None:
                    publication['extracted_date']=extracted.published.isoformat()
                publication['registered_at']=link.published.isoformat()
                extracted.published=link.published
                extracted.published_basis=link.date_source
            extracted.metadata['publication']=publication
        if extracted.published is None and link is not None and link.published and link.date_source:
            extracted.published = link.published
            extracted.published_basis = link.date_source
            grounding = extracted.metadata.get("claim_grounding")
            native_basis = (link.date_source.startswith("publication date in enclosing table/list record at ")
                            or link.date_source in {"SFC public publication listing", "SFC public conclusions listing"})
            if (page.kind == "pdf" and isinstance(grounding, dict) and grounding.get("role") == "publication"
                    and native_basis and document_key(link.url) == document_key(page.requested_url)):
                grounding.update(date_scope="publication", date_basis=link.date_source)
        saved = (self.writer.save(page,extracted,provenance,deadline=deadline) if deadline is not None
                 else self.writer.save(page,extracted,provenance))
        self.log.append(FetchAttempt(
            url=page.url, outcome="unchanged" if saved.unchanged else "saved",
            document_version_id=saved.document_version_id, error=extracted.error, attempted_at=datetime.now(UTC),
            acquisition_method=provenance.get("acquisition_method","http_fetch"),
        ))
        self.seen.add(page.url)
        self.visits.append(_Visit(page.url, saved.document_version_id, saved.passage_ids))
        self._record_discovery(extracted.links, page.requested_url, saved.document_version_id)
        for link in extracted.links:
            if link.url not in self.seen and self.scout.fetcher.allow.allows(link.url):
                self.candidates.append(link)
        return extracted

    def _fetch_document(self, url: str, link: Link | None = None, *, reserved: int = 0) -> None:
        """Fetch a chosen page and, if it is a landing page for a PDF, the PDF it links to."""
        key = document_key(url)
        if key.startswith('au-register:'):
            # Only follow the verified counterpart actually discovered by the
            # native API. Never turn a viewer URL into a guessed publication.
            matches=[candidate for candidate in [*getattr(self,'publication_variants',{}).values(),*self.candidates]
                     if document_key(candidate.url)==key and self.scout.fetcher.allow.allows(candidate.url)]
            html=next((candidate for candidate in matches if not _is_pdf(candidate.url)),None)
            pdf=next((candidate for candidate in matches if _is_pdf(candidate.url)),None)
            if html is not None and pdf is not None and self.allowance>reserved+1:
                self._fetch(html.url,html)
                if self.allowance>reserved:
                    self._fetch(pdf.url,pdf)
                return
        if key.startswith("hkma:"):
            _, language, reference = key.split(":")
            if re.fullmatch(r"\d{8}-\d+-(?:EN|CHI)", reference):
                pdf_url = f"https://brdr.hkma.gov.hk/{language}/doc-ldg/docId/getPdf/{reference}/{reference}.pdf"
                if self.scout.fetcher.allow.allows(pdf_url):
                    pdf = self._fetch(pdf_url, link)
                    if pdf is not None and pdf.status in ("complete", "partial") and pdf.text:
                        return
                    if self.allowance <= reserved:
                        return
        extracted = self._fetch(url, link)
        if extracted is None:
            return
        pdf = next((link for link in extracted.links if _is_pdf(link.url) and self.scout.fetcher.allow.allows(link.url)), None)
        if pdf is not None and self.allowance > reserved:
            # A parent's publication date applies only to a recognised alias of that document.
            dated = (Link(pdf.url, pdf.text, pdf.context, extracted.published, extracted.published_basis)
                     if document_key(pdf.url) == document_key(url) else pdf)
            if document_key(pdf.url).startswith('au-register:'):
                self._fetch_document(pdf.url,dated,reserved=reserved)
            else:
                self._fetch(pdf.url, dated)
        elif (pdf is not None and self.allowance > 0 and reserved > 0
              and document_key(pdf.url) == key and pdf.url not in self.seen):
            # This exact full-content follow-up was deferred by the round quota.
            # Its saved landing page must not suppress it as an acquired alias.
            self.deferred_alias_pdfs.add(pdf.url)
            if extracted.published is not None:
                dated = Link(pdf.url, pdf.text, pdf.context, extracted.published, extracted.published_basis)
                self.candidates = [dated if candidate is pdf else candidate for candidate in self.candidates]
                if id(pdf) in self.origins:
                    self.origins[id(dated)] = (dated, self.origins[id(pdf)][1])

    def _within_tokens(self) -> bool:
        limit = self.task.max_llm_tokens
        return limit is None or self.tokens_in + self.tokens_out + self.hybrid_tokens + self.hybrid_reserved_tokens + self.generation_reserved_tokens < limit

    def _remaining_tokens(self) -> int | None:
        limit = getattr(self.task, "max_llm_tokens", None)
        return None if limit is None else limit - self.tokens_in - self.tokens_out - self.hybrid_tokens - self.hybrid_reserved_tokens - self.generation_reserved_tokens

    def _report_reserve(self) -> int:
        """Tokens kept back so the final report call fits with a minimal set of passages."""
        from mira.llm import request_token_reservation
        return request_token_reservation(system=REPORT_SYSTEM, user="x" * MIN_PASSAGE_CHARS,
                                         output_type=ScoutReport, max_output_tokens=REPORT_OUTPUT_TOKENS)

    def _passage_char_budget(self, prompt_without_passages: str) -> int:
        remaining = self._remaining_tokens()
        if remaining is None:
            return MAX_PASSAGE_CHARS
        from mira.llm import request_token_reservation
        base = request_token_reservation(system=REPORT_SYSTEM, user=prompt_without_passages,
                                         output_type=ScoutReport, max_output_tokens=REPORT_OUTPUT_TOKENS)
        # UTF-8 can use four bytes per character. Quoted passage metadata is
        # checked against the actual reservation immediately before the call.
        return max(0, min(MAX_PASSAGE_CHARS, (remaining - base) // 4))

    def _used(self, result: LLMResult) -> None:
        self.tokens_in += result.tokens_in
        self.tokens_out += result.tokens_out
        self.model = result.model

    # --- Steps ----------------------------------------------------------------

    def _acquire(self) -> str:
        sources = {source.id: source for source in self.store.list_sources(self.ctx.workspace_id)}
        expected = self.store.list_expected_sources(self.ctx.workspace_id, self.ctx.brief.topic, self.ctx.brief.jurisdictions)
        categories = list(dict.fromkeys(item.category for item in expected if item.id in self.task.expected_source_ids))
        queues = []
        other_indexes = []
        years = range(self.ctx.brief.period_end.year, self.ctx.brief.period_start.year - 1, -1)
        for source_id in self.task.source_ids:
            source = sources.get(source_id)
            if source is not None and {"fetch", "store_text"} <= set(source.permitted_operations):
                config = source.connector_config
                if self.ctx.brief.topic == CYBERSECURITY:
                    config = {"category_urls": CYBER_SOURCE_ROUTES,
                              "start_urls": [url for routes in CYBER_SOURCE_ROUTES.values() for url in routes]}
                source_queues, source_others = seed_plan(config, categories, years)
                queues.extend(source_queues)
                other_indexes.extend(source_others)
        # Give previously discovered, unconsumed work a bounded share before
        # refreshing indexes. The store checks the current attempt's fence.
        if self.scout.frontier is not None and self.allowance > 1:
            pending = self.scout.frontier.pending(self.task.source_ids, self.allowance // 2,
                start_date=self.ctx.brief.period_start - timedelta(days=31), as_of_date=self.ctx.brief.as_of_date)
            for link in pending:
                if link.published and (link.published > self.ctx.brief.as_of_date or link.published < self.ctx.brief.period_start - timedelta(days=31)):
                    continue
                if self.allowance <= 0:
                    break
                start = len(self.log)
                self._fetch_document(link.url, link, reserved=0)
                attempts = self.log[start:]
                if attempts:
                    attempt = attempts[0]
                    status = 'acquired' if attempt.outcome in ('saved', 'unchanged', 'reused') and not attempt.error else 'failed'
                    self.scout.frontier.finish(link.url, status, error=attempt.error)
        # Open each assigned category's index in turn, most recent year first.
        # Bound seed pages to roughly half the allowance, preserving room for
        # the publications themselves when the task can fetch multiple pages.
        seed_limit = min(max(1, (self.allowance + 1) // 2), sum(map(len, queues)))
        stop_at = self.allowance - seed_limit
        while queues and self.allowance > stop_at:
            for queue in list(queues):
                if self.allowance <= stop_at:
                    break
                self._fetch(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        other_indexes.extend(url for queue in queues for url in queue)
        self.candidates.extend(Link(url, "Additional approved publication index", self.task.question)
                               for url in other_indexes if url not in self.seen)
        if self.scout.discovery_adapter is not None and self.allowance > 0 and (self._remaining_seconds() is None or self._remaining_seconds() > 0):
            try:
                adapter = self.scout.discovery_adapter
                remaining = self._remaining_seconds()
                if remaining is not None and hasattr(adapter, "with_timeout"):
                    adapter = adapter.with_timeout(remaining)
                links = adapter.discover(
                    self.task.question, list(self.task.source_ids), self.scout.fetcher.allow, self.ctx.brief.as_of_date)
                safe = []
                for link in links[:25]:
                    try:
                        source = self.scout.fetcher.allow.source_for(link.url)
                        if source.id in self.task.source_ids and {"fetch", "store_text"} <= set(source.permitted_operations):
                            if link.published is None or link.published <= self.ctx.brief.as_of_date:
                                safe.append(Link(link.url, link.text[:200], "URL discovered by search provider"))
                    except (FetchRefused, ValueError):
                        continue
                self._record_discovery(safe, "discovery", None)
                self.candidates.extend(safe)
            except Exception as exc:
                self.discovery.append({"reason": "discovery_failed", "error": type(exc).__name__})
        stop_reason = "round_limit"
        for round_index in range(self.scout.max_rounds):
            if self._remaining_seconds() is not None and self._remaining_seconds() <= 0:
                stop_reason = "time_limit"
                break
            if self.allowance <= 0:
                stop_reason = "document_allowance"
                break
            if not self.candidates:
                stop_reason = "no_candidates"
                break
            if not self._within_tokens():
                stop_reason = "token_limit"
                break
            self._select_and_fetch(rounds_left=self.scout.max_rounds - round_index)
            if self.token_stop:
                stop_reason = "token_limit"
                break
        else:
            if self.allowance <= 0:
                stop_reason = "document_allowance"
            elif not self.candidates:
                stop_reason = "no_candidates"
            elif self.scout.max_rounds and not self._within_tokens():
                stop_reason = "token_limit"
        return stop_reason

    def _reuse_archive(self) -> None:
        rows = self.conn.execute("""
            select v.id, v.source_url
            from public.document_versions v
            join public.documents d on d.id = v.document_id and d.workspace_id = v.workspace_id
            join public.sources s on s.id = d.source_id and s.workspace_id = d.workspace_id
            where v.workspace_id = %s and d.source_id = any(%s)
              and s.permitted_operations @> array['quote']::text[]
              and private.analysis_coverage_document_reason(%s, %s, %s, v.id) is null
            order by v.published_at desc nulls last, v.retrieved_at desc, v.id
            limit %s
        """, (self.ctx.workspace_id, list(self.task.source_ids), self.ctx.workspace_id,
              self.ctx.analysis_run_id, self.ctx.analysis_revision_id, self.allowance)).fetchall()
        self.archive_versions = [row["id"] for row in rows]
        now = datetime.now(UTC)
        self.log.extend(
            FetchAttempt(url=row["source_url"], outcome="reused", document_version_id=row["id"],
                         error=None, attempted_at=now, request_sent=False)
            for row in rows
        )

    def execute(self) -> ScoutOutcome:
        if self.scout.archive_only:
            self._reuse_archive()
            stop_reason = "saved_archive_only"
        else:
            stop_reason = self._acquire()
        report, labels = self._report()
        result = ScoutResult(
            analysis_run_id=self.ctx.analysis_run_id, agent_step_id=self.step_id, role=self.task.role,
            jurisdiction_code=self.task.jurisdiction_code, report=report, fetch_log=self.log, labels=labels,
            selection_diagnostics={"discovered": self.discovery, "discovered_omitted": self.discovery_omitted,
                                   "rounds": self.selection_diagnostics, "stop_reason": stop_reason,
                                   "remaining_allowance": self.allowance, "hybrid": self.hybrid_diagnostics,
                                   "summary": self.summary_diagnostics,
                                   "generation_usage": {"reserved_tokens": self.generation_reserved_tokens}},
        )
        return ScoutOutcome(result, self.model, PROMPT_VERSION, self.tokens_in, self.tokens_out)

    def _select_and_fetch(self, *, rounds_left: int = 1) -> None:
        brief = self.ctx.brief
        earliest = brief.period_start - timedelta(days=31)
        fresh: list[Link] = []
        urls: set[str] = set()
        with self.scout._fetch_lock:
            completed = {document_key(key[2]) for key, future in self.scout._pages.items()
                         if key[:2] == (self.ctx.workspace_id, self.ctx.analysis_run_id)
                         and future.done() and future.exception() is None
                         and future.result()[1] is not None}
        diagnostic = {"round": len(self.selection_diagnostics) + 1, "filtered": [], "filtered_omitted": 0,
                      "presented": [], "prompt_cap_omitted": 0, "remaining_allowance_start": self.allowance}
        self.selection_diagnostics.append(diagnostic)

        def filtered(link: Link, reason: str) -> None:
            record = {"url": _safe_url(link.url), "date": link.published.isoformat() if link.published else None,
                      "reason": reason, **self.origins.get(id(link), (link, {}))[1]}
            if len(diagnostic["filtered"]) < MAX_DIAGNOSTIC_RECORDS:
                diagnostic["filtered"].append(record)
            else:
                diagnostic["filtered_omitted"] += 1

        # Keep full-file counterparts before alias deduplication removes them.
        # The bounded cache survives selection clearing its candidate queue.
        for link in self.candidates:
            if (document_key(link.url).startswith('au-register:')
                    and (link.published is None or earliest<=link.published<=brief.as_of_date)
                    and (link.url in self.publication_variants or len(self.publication_variants)<2000)):
                old=self.publication_variants.get(link.url)
                if old is None or (old.published is None and link.published is not None):
                    self.publication_variants[link.url]=link
        distinct = distinct_links(self.candidates)
        retained_ids = {id(link) for link in distinct}
        accounted_ids: set[int] = set()
        for link in self.candidates:
            if id(link) not in retained_ids or id(link) in accounted_ids:
                filtered(link, "duplicate_or_alias")
            else:
                accounted_ids.add(id(link))
        for link in distinct:
            if link.url in self.seen or link.url in urls:
                filtered(link, "seen")
                continue
            if document_key(link.url) in completed and link.url not in self.deferred_alias_pdfs:
                filtered(link, "known_alias")
                continue
            if link.published and not (earliest <= link.published <= brief.as_of_date):
                filtered(link, "out_of_as_of" if link.published > brief.as_of_date else "before_period")
                continue
            urls.add(link.url)
            fresh.append(link)
        self.candidates = []
        if not fresh:
            diagnostic.update(stop_reason="no_candidates", remaining_allowance=self.allowance)
            return
        terms = _terms(f"{self.task.question} {self._topic_terms()}")
        fresh.sort(key=lambda link: (link.published is None,
                                     -len(terms & _terms(link.text + " " + link.context)),
                                     -(link.published.toordinal() if link.published else 0)))
        # A dated publisher record with a topic-bearing publication title is a
        # stronger acquisition candidate than another navigation page. Only
        # use dates attached by recognised native record extractors; provider
        # search snippets and inferred page dates do not qualify.
        native = []
        topic_terms = _terms(self.task.question)
        publication_words = {"circular", "notice", "statement", "guideline", "guidance", "enforcement",
                             "consultation", "policy", "action", "review", "report", "amendment"}
        navigation_words = {"archive", "index", "navigation", "feed", "search", "faq"}
        # Generic publisher and document-kind vocabulary cannot establish
        # subject relevance, even if several such words match the task.
        generic_terms = publication_words | navigation_words | {
            "sfc", "hkma", "regulator", "regulatory", "authority", "commission",
            "circulars", "notices", "statements", "guidelines", "actions", "reports",
            "consultations", "papers", "paper", "news", "releases", "release",
            "find", "published", "issued", "involving", "including", "licensed",
            "corporations", "cases", "case", "fine", "fines", "reprimands", "disciplinary",
        }
        for link in fresh:
            origin = self.origins.get(id(link), (link, {}))[1]
            basis = link.date_source or ""
            native_date = (basis.startswith("publication date in enclosing table/list record at ")
                           or basis in {"SFC public publication listing", "SFC public conclusions listing"})
            title_terms = _terms(link.text)
            if (link.published and brief.period_start <= link.published <= brief.as_of_date
                    and native_date and origin.get("request_url") not in (None, "discovery")
                    and len(topic_terms & title_terms) >= 2
                    and any(not word.isdigit() for word in (topic_terms & title_terms) - generic_terms)
                    and publication_words & title_terms and not navigation_words & title_terms):
                native.append(link)
        if native:
            capacity = min(self.scout.links_per_round, self.allowance)
            if rounds_left > 1 and self.allowance > 1:
                capacity = min(capacity, (self.allowance + rounds_left - 1) // rounds_left)
            chosen = native[:capacity]
            self.candidates.extend(link for link in fresh if link not in chosen)
            self.prior_selections.extend(chosen)
            reserved = self.allowance - capacity
            diagnostic["deterministic_selected"] = []
            for index, link in enumerate(chosen):
                item = {"rank": index + 1, "url": _safe_url(link.url),
                        "date": link.published.isoformat(), "selected": True,
                        "selection_method": "publisher_record",
                        **self.origins.get(id(link), (link, {}))[1]}
                diagnostic["deterministic_selected"].append(item)
                self.deferred_alias_pdfs.discard(link.url)
                start = len(self.log)
                before = self.allowance
                self._fetch_document(link.url, link, reserved=reserved + len(chosen) - index - 1)
                item["fetch_attempts"] = [
                    {"url": _safe_url(a.url), "outcome": a.outcome,
                     "document_version_id": str(a.document_version_id) if a.document_version_id else None}
                    for a in self.log[start:]]
                item["fetch_status"] = ("attempted" if len(self.log) > start else
                                        "allowance_exhausted" if before <= 0 else "not_attempted")
            diagnostic.update(stop_reason="selected", remaining_allowance=self.allowance)
            return
        # Round-robin hosts so a large feed cannot crowd other sources out of the prompt.
        groups: dict[str, list[Link]] = {}
        for link in fresh:
            groups.setdefault(urlsplit(link.url).hostname or "", []).append(link)
        fresh = []
        while groups and len(fresh) < MAX_LINKS_SHOWN:
            for host in list(groups):
                if len(fresh) < MAX_LINKS_SHOWN:
                    fresh.append(groups[host].pop(0))
                if not groups[host]:
                    del groups[host]
        diagnostic["prompt_cap_omitted"] = sum(len(group) for group in groups.values())
        # Continue the same host rotation only for diagnostic ranks; do not change the prompt.
        remaining = {host: list(links) for host, links in groups.items()}
        rank = len(fresh)
        deferred: list[Link] = []
        while remaining:
            for host in list(remaining):
                rank += 1
                link = remaining[host].pop(0)
                deferred.append(link)
                before = len(diagnostic["filtered"])
                filtered(link, "prompt_cap")
                if len(diagnostic["filtered"]) > before:
                    diagnostic["filtered"][-1]["rank"] = rank
                if not remaining[host]:
                    del remaining[host]
        labels = LabelMap()
        label_to_link: dict[str, Link] = {}
        lines = []
        for link in fresh:
            label = labels.add("L", UUID(int=len(label_to_link) + 1))
            label_to_link[label] = link
            diagnostic["presented"].append({"label": label, "rank": len(label_to_link), "url": _safe_url(link.url),
                "date": link.published.isoformat() if link.published else None, "selected": False,
                **self.origins.get(id(link), (link, {}))[1]})
            date_text = link.published.isoformat() if link.published else "date unknown"
            context = link.context.replace("<", "(").replace(">", ")")[:200]
            lines.append(f'<link label="{label}" date="{date_text}" url="{link.url}">{link.text[:200]} | {context}</link>')
        prior = "\n".join(
            f"{link.published.isoformat() if link.published else 'date unknown'} | "
            f"{escape(link.text[:200]).replace(chr(10), '&#10;').replace(chr(13), '&#13;')}"
            for link in self.prior_selections
        )
        def prompt(allowed: int) -> str:
            return "\n\n".join([
                brief_text(brief),
                f"Research question: {self.task.question}",
                "Links selected in earlier rounds (untrusted, not necessarily acquired):\n"
                + "<prior_selections>\n" + (prior or "none") + "\n</prior_selections>",
                f"Pick at most {allowed} links.",
                "Links:\n" + "\n".join(lines),
            ])
        allowed = min(self.scout.links_per_round, self.allowance)
        user = prompt(allowed)
        remaining = self._remaining_tokens()
        seconds = self._remaining_seconds()
        # Estimate a second prompt of this size plus titles for this round's
        # selections. A later, larger candidate set can still exhaust the cap.
        two_round_tokens = (2 * (estimate_tokens(LINK_SYSTEM + user) + SELECTION_OUTPUT_TOKENS)
                            + self._report_reserve() + allowed * 320)
        can_split = (rounds_left > 1 and self.allowance > 1
                     and (seconds is None or seconds >= MIN_TWO_ROUND_SECONDS)
                     and (remaining is None or remaining >= two_round_tokens))
        round_capacity = ((self.allowance + rounds_left - 1) // rounds_left
                          if can_split else self.allowance)
        reserved_for_later = self.allowance - round_capacity
        allowed = min(self.scout.links_per_round, round_capacity)
        user = prompt(allowed)
        needed = estimate_tokens(LINK_SYSTEM + user) + SELECTION_OUTPUT_TOKENS + self._report_reserve()
        if remaining is not None and needed > remaining:
            # Another selection round would leave too little for the report: stop here.
            self.candidates.extend(fresh)
            self.token_stop = True
            diagnostic.update(stop_reason="token_limit", remaining_allowance=self.allowance,
                              presented=[], not_sent=len(fresh))
            return

        def check(output: LinkSelection) -> None:
            if len(output.link_labels) > allowed:
                raise ValueError(f"pick at most {allowed} links")
            for label in output.link_labels:
                labels.resolve(label, "L")

        result = call_checked(self.scout.client, role=self.task.role, system=LINK_SYSTEM, user=user,
                              output_type=LinkSelection, prompt_version=PROMPT_VERSION, check=check)
        self._used(result)
        selected_urls = {label_to_link[label].url for label in result.output.link_labels}
        self.prior_selections.extend(label_to_link[label] for label in result.output.link_labels)
        self.candidates.extend(link for link in fresh if link.url not in selected_urls)
        self.candidates.extend(deferred)
        for item in diagnostic["presented"]:
            item["selected"] = item["label"] in result.output.link_labels
        for index, label in enumerate(result.output.link_labels):
            link = label_to_link[label]
            self.deferred_alias_pdfs.discard(link.url)
            item = next(item for item in diagnostic["presented"] if item["label"] == label)
            start = len(self.log)
            allowance_before = self.allowance
            self._fetch_document(link.url, link, reserved=reserved_for_later + len(result.output.link_labels) - index - 1)
            if self.scout.frontier is not None and len(self.log) > start:
                attempt = self.log[start]
                status = 'acquired' if attempt.outcome in ('saved', 'unchanged', 'reused') and not attempt.error else 'failed'
                self.scout.frontier.finish(link.url, status, error=attempt.error)
            item.setdefault("fetch_attempts", []).extend(
                {"url": _safe_url(a.url), "outcome": a.outcome,
                 "document_version_id": str(a.document_version_id) if a.document_version_id else None}
                for a in self.log[start:])
            if len(self.log) > start:
                item["fetch_status"] = "attempted"
            else:
                item.setdefault("fetch_status", "allowance_exhausted" if allowance_before <= 0 else "not_attempted")
        diagnostic.update(stop_reason="selected" if result.output.link_labels else "no_selection",
                          remaining_allowance=self.allowance)

    def _topic_terms(self) -> str:
        return CYBER_TERMS if self.ctx.brief.topic == CYBERSECURITY else AML_TERMS

    def _passages(self, max_chars: int | None = None) -> list[PassageRecord]:
        max_chars = MAX_PASSAGE_CHARS if max_chars is None else max_chars
        ids = [passage_id for visit in self.visits for passage_id in visit.passage_ids]
        with self.scout._fetch_lock:
            for key, future in self.scout._pages.items():
                if (key[:2] == (self.ctx.workspace_id, self.ctx.analysis_run_id)
                        and future.done() and future.exception() is None):
                    visit = future.result()[1]
                    if visit:
                        ids.extend(p for p in visit.passage_ids if p not in ids)
        # Pick an eligible version before ranking or applying any candidate limit.
        # Publication date controls eligibility; retrieval time does not establish
        # what a page contained historically.
        brief = self.ctx.brief
        eligible = """with eligible as (
            select distinct on (v.document_id) v.id, v.published_at, v.metadata
            from public.document_versions v
            join public.documents d on d.id = v.document_id and d.workspace_id = v.workspace_id
            join public.sources s on s.id = d.source_id and s.workspace_id = d.workspace_id
            where s.is_active and 'store_text' = any(s.permitted_operations)
              and ('fetch' = any(s.permitted_operations) or v.metadata->>'import' = 'manual')
              and ((%s::text is null or %s::text = 'INT') and coalesce(trim(s.jurisdiction_code), '') in ('', 'INT')
                   or %s::text is not null and %s::text <> 'INT' and s.jurisdiction_code = %s and s.jurisdiction_code = any(%s))
              and d.workspace_id = %s and v.workspace_id = %s
              and d.source_id = any(%s)
              and (v.published_at is null or v.published_at::date <= %s)
              and (%s::uuid[] is null or v.id = any(%s::uuid[]))
            order by v.document_id, v.version_number desc
        ) """
        scope = (self.task.jurisdiction_code, self.task.jurisdiction_code, self.task.jurisdiction_code,
                 self.task.jurisdiction_code, self.task.jurisdiction_code, list(brief.jurisdictions), self.ctx.workspace_id, self.ctx.workspace_id,
                 list(self.task.source_ids), brief.as_of_date, self.archive_versions, self.archive_versions)
        # Match the public search function's ranking, but only after version
        # and source eligibility, so obsolete passages cannot consume its cap.
        words = sorted(_terms(self.task.question))[:12]
        defaults = ['"money laundering"'] if brief.topic != CYBERSECURITY else CYBER_TERMS.split()
        query = " or ".join([*defaults, *words])
        found = self.conn.execute(
            eligible + """select p.id as passage_id
                from public.document_passages p
                join eligible v on v.id = p.document_version_id
                where p.workspace_id = %s
                  and p.search_vector @@ websearch_to_tsquery('english'::regconfig, %s)
                order by ts_rank_cd(p.search_vector, websearch_to_tsquery('english'::regconfig, %s)) desc, p.id
                limit 15""", (*scope, self.ctx.workspace_id, query, query)
        ).fetchall()
        ids.extend(row["passage_id"] for row in found if row["passage_id"] not in ids)
        # Include period publications and manual imports using the same selected version.
        stored = self.conn.execute(
            eligible + """select p.id from public.document_passages p
                join eligible v on v.id = p.document_version_id
                where p.workspace_id = %s
                  and (v.published_at::date between %s and %s or v.metadata->>'import' = 'manual')
                order by v.published_at desc nulls last, p.passage_number
                limit 300""",
            (*scope, self.ctx.workspace_id, brief.period_start, brief.period_end),
        ).fetchall()
        ids.extend(row["id"] for row in stored if row["id"] not in ids)
        hybrid_order = {}
        if getattr(self.scout, "hybrid", None) is not None and self.hybrid_diagnostics is None:
            remaining = self._remaining_tokens()
            available = None if remaining is None else max(0, remaining - self._report_reserve())
            try:
                hybrid = self.scout.hybrid.retrieve(self.conn, self.ctx, self.task,
                    remaining_tokens=available, remaining_seconds=self._remaining_seconds())
                self.hybrid_tokens += hybrid.tokens
                self.hybrid_reserved_tokens += hybrid.reserved_tokens
                identity = getattr(self.scout.hybrid, "identity", None)
                self.hybrid_diagnostics = {"model": getattr(identity, "model", None),
                                           "revision": getattr(identity, "revision", None),
                                           "dimensions": getattr(identity, "dimensions", None),
                                           "fallback_reason": hybrid.fallback_reason,
                                           "tokens": hybrid.tokens, "reserved_tokens": hybrid.reserved_tokens,
                                           "cache_error": getattr(hybrid, "cache_error", None)}
                for field in ('eligible_passages','indexed_passages','pending_passages','blocked_passages',
                              'index_batches','indexing_stop_reason','coverage_known',
                              'input_characters','input_bytes','embedding_requests'):
                    self.hybrid_diagnostics[field] = getattr(hybrid,field,None)
                if hybrid.fallback_reason is None:
                    hybrid_order = {p.id: i for i, p in enumerate(hybrid.passages)}
                    ids.extend(p.id for p in hybrid.passages if p.id not in ids)
            except Exception:
                self.hybrid_diagnostics = {"fallback_reason": "runtime_error", "tokens": 0, "reserved_tokens": 0}
        # Fresh and reused visits must obey the same eligibility as stored results.
        selected = self.conn.execute(
            eligible + """select p.id from public.document_passages p
                join eligible v on v.id = p.document_version_id
                where p.workspace_id = %s and p.id = any(%s)""",
            (*scope, self.ctx.workspace_id, ids),
        ).fetchall()
        selected_ids = {row["id"] for row in selected}
        passages = [p for p in self.store.get_passages(self.ctx.workspace_id, ids)
                    if p.id in selected_ids and p.source_id in self.task.source_ids
                    and (p.published_at is None or p.published_at <= brief.as_of_date)]
        terms = _terms(f"{self.ctx.brief.topic} {self._topic_terms()} {self.task.question}")
        feed_urls = {p.source_url for p in passages if p.source_url.endswith(".xml") or "/rss" in p.source_url.lower()}
        # Documents first; feed lines (titles and dates only) rank below them.
        passages.sort(key=lambda p: (p.source_url in feed_urls,
                                    0 if p.id in hybrid_order else 1,
                                    hybrid_order.get(p.id, 0), -len(terms & _terms(p.content))))
        # Collapse exact passages and known document aliases; RSS remains a discovery
        # source, not an alias for all the distinct publications it lists.
        pdf_keys = {document_key(p.source_url) for p in passages if _is_pdf(p.source_url)}
        by_document: dict[str, list[PassageRecord]] = {}
        content_seen = set()
        for passage in passages:
            if not _is_pdf(passage.source_url) and document_key(passage.source_url) in pdf_keys:
                continue
            content_key = (document_key(passage.source_url), passage.published_at, " ".join(passage.content.split()))
            if content_key in content_seen:
                continue
            content_seen.add(content_key)
            by_document.setdefault(document_key(passage.source_url), []).append(passage)
        candidate_count = sum(map(len, by_document.values()))
        chosen, total = [], 0
        while by_document and len(chosen) < MAX_PASSAGES_SHOWN:
            for key in list(by_document):
                if len(chosen) >= MAX_PASSAGES_SHOWN:
                    break
                passage = by_document[key].pop(0)
                if total + len(passage.content) <= max_chars:
                    chosen.append(passage)
                    total += len(passage.content)
                if not by_document[key]:
                    del by_document[key]
        self.summary_diagnostics = {"passage_char_limit": max_chars, "shown_passages": len(chosen),
                                    "shown_characters": total, "eligible_candidates": candidate_count,
                                    "omitted_passages": candidate_count - len(chosen),
                                    "omission_reason": "summary_passage_or_character_limit" if candidate_count > len(chosen) else None}
        return chosen

    def _report(self) -> tuple[ScoutReport, dict[str, UUID]]:
        expected = {row.id: row for row in self.store.list_expected_sources(
            self.ctx.workspace_id, self.ctx.brief.topic, self.ctx.brief.jurisdictions)}
        labels = LabelMap()
        expected_labels = {labels.add("E", expected_id): expected[expected_id]
                           for expected_id in self.task.expected_source_ids if expected_id in expected}
        expected_lines = [f"{label}: {row.jurisdiction_code} | {row.category} | {row.document_hint}"
                          for label, row in expected_labels.items()]
        header = "\n\n".join([
            brief_text(self.ctx.brief),
            f"Research question: {self.task.question}",
            "Expected sources for this task:\n" + ("\n".join(expected_lines) or "none"),
        ])
        # Show as many passages as the task's remaining tokens allow, within the usual cap.
        passages = self._passages(self._passage_char_budget(header))
        if not passages:
            reason = ("summary passage limit excluded available evidence"
                      if self.summary_diagnostics and self.summary_diagnostics["omitted_passages"]
                      else "no readable pages were saved")
            statuses = [{"expected_source_label": label, "status": "missing", "note": reason}
                        for label in expected_labels]
            return ScoutReport(documents=[], expected_source_statuses=statuses, notes=reason), labels.as_dict()
        quoted = [quote_passage(labels.add("P", passage.id), passage) for passage in passages]
        user = header + "\n\n" + "Passages:\n\n" + "\n\n".join(quoted)

        def check(output: ScoutReport) -> None:
            for document in output.documents:
                labels.resolve_all(document.relevant_passage_labels, "P")
                labels.resolve_all(document.expected_source_labels, "E")
            for status in output.expected_source_statuses:
                labels.resolve(status.expected_source_label, "E")
                labels.resolve_all(status.inspected_passage_labels, "P")

        result = call_checked(_SummaryClient(self), role=self.task.role, system=REPORT_SYSTEM, user=user,
                              output_type=ScoutReport, prompt_version=PROMPT_VERSION, check=check)
        self._used(result)
        # The model cannot establish coverage from passages it did not see.
        statuses = []
        for status in result.output.expected_source_statuses:
            supported = (status.status != "no_change" or bool(status.inspected_passage_labels))
            if status.status == "found":
                supported = any(status.expected_source_label in doc.expected_source_labels
                                and doc.relevant_passage_labels for doc in result.output.documents)
            if not supported:
                status = status.model_copy(update={"status": "missing",
                                                   "note": "no shown passage establishes this status"})
            statuses.append(status)
        return result.output.model_copy(update={"expected_source_statuses": statuses}), labels.as_dict()
