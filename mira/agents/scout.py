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
import threading
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

PROMPT_VERSION = "scout/5"
MAX_LINKS_SHOWN = 120
MAX_DIAGNOSTIC_RECORDS = 300


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode([(k[:80], v[:200] if k.lower() in {"refno", "lang", "year", "category"} else "[redacted]")
                       for k, v in parse_qsl(parts.query, keep_blank_values=True)[:20]])
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path[:1000], query, ""))

MAX_PASSAGES_SHOWN = 40
MAX_PASSAGE_CHARS = 60_000
# Token-cap enforcement. A task's max_llm_tokens is checked before each call using a
# size estimate, so the cap holds approximately rather than only between calls.
CHARS_PER_TOKEN = 4
SELECTION_OUTPUT_TOKENS = 500
REPORT_OUTPUT_TOKENS = 2_000
# The report call always runs, so pages already fetched are not wasted. Below this
# many passage characters it would have too little evidence to be useful.
MIN_PASSAGE_CHARS = 8_000


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
Listing nothing is a valid answer. Never fill gaps from memory.
- {TEMPORAL_RULE}
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""


@dataclass
class _Visit:
    url: str
    version_id: UUID | None
    passage_ids: list[UUID] = field(default_factory=list)


def _is_pdf(url: str) -> bool:
    lowered = url.lower()
    return lowered.split("?")[0].endswith(".pdf") or "getpdf" in lowered


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", text.lower()) if word not in STOPWORDS}


def document_key(url: str) -> str:
    """Only collapse explicitly recognised HKMA landing/PDF aliases, never whole feeds."""
    url = urldefrag(url)[0]
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
    """Prefer the original PDF when its known landing-page alias is also available."""
    selected: dict[str, Link] = {}
    for link in links:
        key = document_key(link.url)
        if key not in selected or (_is_pdf(link.url) and not _is_pdf(selected[key].url)):
            selected[key] = link
    return list(selected.values())


class WebScout:
    def __init__(self, dsn: str, client: LLMClient, fetcher: Fetcher, *, max_rounds: int = 2,
                 links_per_round: int = 8) -> None:
        self.dsn = dsn
        self.client = client
        self.fetcher = fetcher
        self.max_rounds = max_rounds
        self.links_per_round = links_per_round
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
                               "remaining_allowance": run.allowance}
                raise ScoutFailure(exc, run.log, diagnostics, run.model, PROMPT_VERSION,
                                   tokens_in, tokens_out) from exc


class _ScoutRun:
    def __init__(self, scout: WebScout, conn, ctx: RunContext, step_id: UUID, task: ScoutTask) -> None:  # noqa: ANN001
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
        self.allowance = task.max_documents
        self.tokens_in = self.tokens_out = 0
        self.token_stop = False
        self.model: str | None = None
        self.selection_diagnostics: list[dict] = []
        self.discovery: list[dict] = []
        self.discovery_omitted = 0
        self.origins: dict[int, tuple[Link, dict]] = {}

    def _record_discovery(self, links: list[Link], request_url: str, version_id: UUID | None) -> None:
        for link in links:
            origin = {"request_url": _safe_url(request_url), "document_version_id": str(version_id) if version_id else None}
            record = {"url": _safe_url(link.url), "date": link.published.isoformat() if link.published else None,
                      "reason": "seen" if link.url in self.seen else ("source_not_allowed" if not self.scout.fetcher.allow.allows(link.url) else "candidate"), **origin}
            if len(self.discovery) < MAX_DIAGNOSTIC_RECORDS:
                self.discovery.append(record)
                self.origins[id(link)] = (link, origin)
            else:
                self.discovery_omitted += 1

    # --- Fetching -------------------------------------------------------------

    def _fetch(self, url: str, link: Link | None = None) -> Extracted | None:
        url = urldefrag(url)[0]
        if url in self.seen:
            return None
        key = (self.ctx.workspace_id, self.ctx.analysis_run_id, url)
        with self.scout._fetch_lock:
            pending = self.scout._pages.get(key)
            owner = pending is None
            if owner:
                if self.allowance <= 0:
                    return None
                pending = Future()
                self.scout._pages[key] = pending
        if owner:
            allowance_start = self.allowance
            log_start = len(self.log)
            attempted_at = datetime.now(UTC)
            try:
                extracted = self._fetch_new(url, link)
                visit = self.visits[-1] if extracted is not None else None
                pending.set_result((extracted, visit, self.log[-1]))
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
            page = self.scout.fetcher.fetch(url, json_body=payload) if payload is not None else self.scout.fetcher.fetch(url)
        except FetchRefused as exc:
            self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None, error=str(exc), attempted_at=now))
            return None
        except FetchFailed as exc:
            if not (isinstance(exc, SiteBlocked) and exc.repeated):  # no request was sent
                self.allowance -= 1
            self.log.append(FetchAttempt(url=url, outcome="failed", document_version_id=None, error=str(exc), attempted_at=now))
            return None
        self.allowance -= 1
        extracted = extract(page)
        if extracted.published is None and link is not None and link.published and link.date_source:
            extracted.published = link.published
            extracted.published_basis = link.date_source
        provenance = {"request_method": "POST", "request_json": payload} if payload is not None else None
        saved = self.writer.save(page, extracted, provenance)
        self.log.append(FetchAttempt(
            url=page.url, outcome="unchanged" if saved.unchanged else "saved",
            document_version_id=saved.document_version_id, error=extracted.error, attempted_at=now,
        ))
        self.seen.add(page.url)
        self.visits.append(_Visit(page.url, saved.document_version_id, saved.passage_ids))
        self._record_discovery(extracted.links, url, saved.document_version_id)
        for link in extracted.links:
            if link.url not in self.seen and self.scout.fetcher.allow.allows(link.url):
                self.candidates.append(link)
        return extracted

    def _fetch_document(self, url: str, link: Link | None = None) -> None:
        """Fetch a chosen page and, if it is a landing page for a PDF, the PDF it links to."""
        key = document_key(url)
        if key.startswith("hkma:"):
            _, language, reference = key.split(":")
            if re.fullmatch(r"\d{8}-\d+-(?:EN|CHI)", reference):
                pdf_url = f"https://brdr.hkma.gov.hk/{language}/doc-ldg/docId/getPdf/{reference}/{reference}.pdf"
                if self.scout.fetcher.allow.allows(pdf_url):
                    pdf = self._fetch(pdf_url, link)
                    if pdf is not None and pdf.status in ("complete", "partial") and pdf.text:
                        return
        extracted = self._fetch(url, link)
        if extracted is None:
            return
        pdf = next((link for link in extracted.links if _is_pdf(link.url) and self.scout.fetcher.allow.allows(link.url)), None)
        if pdf is not None:
            # A parent's publication date applies only to a recognised alias of that document.
            dated = (Link(pdf.url, pdf.text, pdf.context, extracted.published, extracted.published_basis)
                     if document_key(pdf.url) == document_key(url) else pdf)
            self._fetch(pdf.url, dated)

    def _within_tokens(self) -> bool:
        limit = self.task.max_llm_tokens
        return limit is None or self.tokens_in + self.tokens_out < limit

    def _remaining_tokens(self) -> int | None:
        limit = getattr(self.task, "max_llm_tokens", None)
        return None if limit is None else limit - self.tokens_in - self.tokens_out

    def _report_reserve(self) -> int:
        """Tokens kept back so the final report call fits with a minimal set of passages."""
        return estimate_tokens(REPORT_SYSTEM) + MIN_PASSAGE_CHARS // CHARS_PER_TOKEN + REPORT_OUTPUT_TOKENS

    def _passage_char_budget(self, prompt_without_passages: str) -> int:
        remaining = self._remaining_tokens()
        if remaining is None:
            return MAX_PASSAGE_CHARS
        spare = remaining - estimate_tokens(REPORT_SYSTEM + prompt_without_passages) - REPORT_OUTPUT_TOKENS
        return max(MIN_PASSAGE_CHARS, min(MAX_PASSAGE_CHARS, spare * CHARS_PER_TOKEN))

    def _used(self, result: LLMResult) -> None:
        self.tokens_in += result.tokens_in
        self.tokens_out += result.tokens_out
        self.model = result.model

    # --- Steps ----------------------------------------------------------------

    def execute(self) -> ScoutOutcome:
        sources = {source.id: source for source in self.store.list_sources(self.ctx.workspace_id)}
        expected = self.store.list_expected_sources(self.ctx.workspace_id, self.ctx.brief.topic, self.ctx.brief.jurisdictions)
        categories = list(dict.fromkeys(item.category for item in expected if item.id in self.task.expected_source_ids))
        queues = []
        other_indexes = []
        years = range(self.ctx.brief.period_end.year, self.ctx.brief.period_start.year - 1, -1)
        for source_id in self.task.source_ids:
            source = sources.get(source_id)
            if source is not None and {"fetch", "store_text"} <= set(source.permitted_operations):
                source_queues, source_others = seed_plan(source.connector_config, categories, years)
                queues.extend(source_queues)
                other_indexes.extend(source_others)
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
        stop_reason = "round_limit"
        for _ in range(self.scout.max_rounds):
            if self.allowance <= 0:
                stop_reason = "document_allowance"
                break
            if not self.candidates:
                stop_reason = "no_candidates"
                break
            if not self._within_tokens():
                stop_reason = "token_limit"
                break
            self._select_and_fetch()
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
        report, labels = self._report()
        result = ScoutResult(
            analysis_run_id=self.ctx.analysis_run_id, agent_step_id=self.step_id, role=self.task.role,
            jurisdiction_code=self.task.jurisdiction_code, report=report, fetch_log=self.log, labels=labels,
            selection_diagnostics={"discovered": self.discovery, "discovered_omitted": self.discovery_omitted,
                                   "rounds": self.selection_diagnostics, "stop_reason": stop_reason,
                                   "remaining_allowance": self.allowance},
        )
        return ScoutOutcome(result, self.model, PROMPT_VERSION, self.tokens_in, self.tokens_out)

    def _select_and_fetch(self) -> None:
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
            if document_key(link.url) in completed:
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
        terms = _terms(self.task.question + " money laundering terrorism financing AML CFT")
        fresh.sort(key=lambda link: (link.published is None,
                                     -len(terms & _terms(link.text + " " + link.context)),
                                     -(link.published.toordinal() if link.published else 0)))
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
        while remaining:
            for host in list(remaining):
                rank += 1
                link = remaining[host].pop(0)
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
        allowed = min(self.scout.links_per_round, self.allowance)
        user = "\n\n".join([
            brief_text(brief),
            f"Research question: {self.task.question}",
            f"Pick at most {allowed} links.",
            "Links:\n" + "\n".join(lines),
        ])
        remaining = self._remaining_tokens()
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
        self.candidates.extend(link for link in fresh if link.url not in selected_urls)
        for item in diagnostic["presented"]:
            item["selected"] = item["label"] in result.output.link_labels
        for label in result.output.link_labels:
            link = label_to_link[label]
            item = next(item for item in diagnostic["presented"] if item["label"] == label)
            start = len(self.log)
            allowance_before = self.allowance
            self._fetch_document(link.url, link)
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
            join public.documents d on d.id = v.document_id
            where d.workspace_id = %s and v.workspace_id = %s
              and d.source_id = any(%s)
              and (v.published_at is null or v.published_at::date <= %s)
            order by v.document_id, v.version_number desc
        ) """
        scope = (self.ctx.workspace_id, self.ctx.workspace_id,
                 list(self.task.source_ids), brief.as_of_date)
        # Match the public search function's ranking, but only after version
        # and source eligibility, so obsolete passages cannot consume its cap.
        words = sorted(_terms(self.task.question))[:12]
        query = " or ".join(['"money laundering"', *words])
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
        terms = _terms(f"{self.ctx.brief.topic} money laundering terrorism financing {self.task.question}")
        feed_urls = {p.source_url for p in passages if p.source_url.endswith(".xml") or "/rss" in p.source_url.lower()}
        # Documents first; feed lines (titles and dates only) rank below them.
        passages.sort(key=lambda p: (p.source_url in feed_urls, -len(terms & _terms(p.content))))
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
            statuses = [{"expected_source_label": label, "status": "missing", "note": "no readable pages were saved"}
                        for label in expected_labels]
            return ScoutReport(documents=[], expected_source_statuses=statuses, notes="no passages"), labels.as_dict()
        quoted = [quote_passage(labels.add("P", passage.id), passage) for passage in passages]
        user = header + "\n\n" + "Passages:\n\n" + "\n\n".join(quoted)

        def check(output: ScoutReport) -> None:
            for document in output.documents:
                labels.resolve_all(document.relevant_passage_labels, "P")
                labels.resolve_all(document.expected_source_labels, "E")
            for status in output.expected_source_statuses:
                labels.resolve(status.expected_source_label, "E")
                labels.resolve_all(status.inspected_passage_labels, "P")

        result = call_checked(self.scout.client, role=self.task.role, system=REPORT_SYSTEM, user=user,
                              output_type=ScoutReport, prompt_version=PROMPT_VERSION, check=check)
        self._used(result)
        return result.output, labels.as_dict()
