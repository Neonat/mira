"""Scouts: find and save the publications for one plan task (PRD v2 §5.2, AG04-AG05).

A scout is a bounded loop with code-owned tools:

1. Fetch the task's sources' feeds and hub pages through ``fetch_allowed`` and
   save every page before any model reads it.
2. Up to ``max_rounds`` times, show the model the new links found (as untrusted
   data, with dates where known) and fetch the ones it picks, within the task's
   document allowance.
3. Add matching passages already in the evidence store (full-text search).
4. Show the model the most relevant saved passages and ask for a ``ScoutReport``:
   documents with the passage labels that matter, and a status for each
   expected source assigned to the task.

Every fetch attempt, refused and failed included, goes into the fetch log. The
scout never writes outside the evidence tables and never sees database IDs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mira.agents.common import NO_CONCLUSIONS_RULE, UNTRUSTED_TEXT_RULE, brief_text, quote_passage
from mira.contracts import FetchAttempt, LabelMap, LinkSelection, ScoutReport, ScoutResult
from mira.db import connect
from mira.evidence import EvidenceWriter
from mira.extract import Link, extract
from mira.fetch import Fetcher, FetchFailed, FetchRefused
from mira.interfaces import ScoutOutcome, ScoutTask
from mira.llm import LLMClient, LLMResult, call_checked
from mira.pg_store import PostgresStore
from mira.store import PassageRecord, RunContext

PROMPT_VERSION = "scout/1"
MAX_LINKS_SHOWN = 120
MAX_PASSAGES_SHOWN = 40
MAX_PASSAGE_CHARS = 60_000
STOPWORDS = {"the", "and", "for", "with", "that", "this", "from", "were", "what", "which", "into", "between",
             "their", "have", "has", "are", "was", "any", "how", "did", "does", "on", "of", "in", "to", "a", "an"}

LINK_SYSTEM = f"""You are a research scout for Mira, a research assistant for bank internal auditors.
You are given a research question, a period and links found on allow-listed regulator and industry pages.
Pick the links most likely to lead to publications that answer the question within the period: rules, guidelines, circulars, consultations, enforcement actions, policy statements, or the documents (often PDFs) they link to.
Skip navigation, unrelated topics and anything clearly outside the period. Pick at most the number allowed; pick none if nothing fits.
- {UNTRUSTED_TEXT_RULE}"""

REPORT_SYSTEM = f"""You are a research scout for Mira, a research assistant for bank internal auditors.
From the saved passages, list the documents that answer the research question within the period, citing the passage labels that matter (P1, P2).
For each document give its instrument type or industry category, title, dates and whether it is new, amended or upcoming, using only what the passages state; use null when unknown.
For each expected source, say found (a relevant development in the period), no_change (the source was read and shows nothing new in the period) or missing (it could not be checked).
Listing nothing is a valid answer. Never fill gaps from memory.
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""


@dataclass
class _Visit:
    url: str
    version_id: UUID | None
    passage_ids: list[UUID] = field(default_factory=list)


def _terms(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", text.lower()) if word not in STOPWORDS}


class WebScout:
    def __init__(self, dsn: str, client: LLMClient, fetcher: Fetcher, *, max_rounds: int = 2,
                 links_per_round: int = 8) -> None:
        self.dsn = dsn
        self.client = client
        self.fetcher = fetcher
        self.max_rounds = max_rounds
        self.links_per_round = links_per_round

    def run(self, ctx: RunContext, step_id: UUID, task: ScoutTask) -> ScoutOutcome:
        with connect(self.dsn) as conn:
            return _ScoutRun(self, conn, ctx, step_id, task).execute()


class _ScoutRun:
    def __init__(self, scout: WebScout, conn, ctx: RunContext, step_id: UUID, task: ScoutTask) -> None:  # noqa: ANN001
        self.scout = scout
        self.conn = conn
        self.ctx = ctx
        self.step_id = step_id
        self.task = task
        self.store = PostgresStore(conn)
        self.writer = EvidenceWriter(conn, ctx)
        self.log: list[FetchAttempt] = []
        self.visits: list[_Visit] = []
        self.seen: set[str] = set()
        self.candidates: list[Link] = []
        self.allowance = task.max_documents
        self.tokens_in = self.tokens_out = 0
        self.model: str | None = None

    # --- Fetching -------------------------------------------------------------

    def _fetch(self, url: str) -> None:
        if url in self.seen or self.allowance <= 0:
            return
        self.seen.add(url)
        now = datetime.now(UTC)
        try:
            page = self.scout.fetcher.fetch(url)
        except FetchRefused as exc:
            self.log.append(FetchAttempt(url=url, outcome="refused", document_version_id=None, error=str(exc), attempted_at=now))
            return
        except FetchFailed as exc:
            self.allowance -= 1
            self.log.append(FetchAttempt(url=url, outcome="failed", document_version_id=None, error=str(exc), attempted_at=now))
            return
        self.allowance -= 1
        extracted = extract(page)
        saved = self.writer.save(page, extracted)
        self.log.append(FetchAttempt(
            url=page.url, outcome="unchanged" if saved.unchanged else "saved",
            document_version_id=saved.document_version_id, error=extracted.error, attempted_at=now,
        ))
        self.seen.add(page.url)
        self.visits.append(_Visit(page.url, saved.document_version_id, saved.passage_ids))
        for link in extracted.links:
            if link.url not in self.seen and self.scout.fetcher.allow.allows(link.url):
                self.candidates.append(link)

    def _within_tokens(self) -> bool:
        limit = self.task.max_llm_tokens
        return limit is None or self.tokens_in + self.tokens_out < limit

    def _used(self, result: LLMResult) -> None:
        self.tokens_in += result.tokens_in
        self.tokens_out += result.tokens_out
        self.model = result.model

    # --- Steps ----------------------------------------------------------------

    def execute(self) -> ScoutOutcome:
        sources = {source.id: source for source in self.store.list_sources(self.ctx.workspace_id)}
        queues = []
        for source_id in self.task.source_ids:
            source = sources.get(source_id)
            if source is not None and "fetch" in source.permitted_operations:
                config = source.connector_config
                queues.append([*config.get("feeds", []), *config.get("start_urls", [])])
        # Seed pages take turns across sources and use at most half the allowance,
        # so the rest is left for the documents they link to.
        seed_limit = max(1, (self.allowance + 1) // 2)
        stop_at = self.allowance - seed_limit
        while queues and self.allowance > stop_at:
            for queue in list(queues):
                if self.allowance <= stop_at:
                    break
                self._fetch(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        for _ in range(self.scout.max_rounds):
            if self.allowance <= 0 or not self.candidates or not self._within_tokens():
                break
            self._select_and_fetch()
        report, labels = self._report()
        result = ScoutResult(
            analysis_run_id=self.ctx.analysis_run_id, agent_step_id=self.step_id, role=self.task.role,
            jurisdiction_code=self.task.jurisdiction_code, report=report, fetch_log=self.log, labels=labels,
        )
        return ScoutOutcome(result, self.model, PROMPT_VERSION, self.tokens_in, self.tokens_out)

    def _select_and_fetch(self) -> None:
        brief = self.ctx.brief
        earliest = brief.period_start - timedelta(days=31)
        fresh: list[Link] = []
        urls: set[str] = set()
        for link in self.candidates:
            if link.url in self.seen or link.url in urls:
                continue
            if link.published and not (earliest <= link.published <= brief.as_of_date):
                continue
            urls.add(link.url)
            fresh.append(link)
        self.candidates = []
        if not fresh:
            return
        fresh.sort(key=lambda link: link.published is None)
        fresh = fresh[:MAX_LINKS_SHOWN]
        labels = LabelMap()
        label_to_link: dict[str, Link] = {}
        lines = []
        for link in fresh:
            label = labels.add("L", UUID(int=len(label_to_link) + 1))
            label_to_link[label] = link
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

        def check(output: LinkSelection) -> None:
            if len(output.link_labels) > allowed:
                raise ValueError(f"pick at most {allowed} links")
            for label in output.link_labels:
                labels.resolve(label, "L")

        result = call_checked(self.scout.client, role=self.task.role, system=LINK_SYSTEM, user=user,
                              output_type=LinkSelection, prompt_version=PROMPT_VERSION, check=check)
        self._used(result)
        for label in result.output.link_labels:
            self._fetch(label_to_link[label].url)

    def _passages(self) -> list[PassageRecord]:
        ids = [passage_id for visit in self.visits for passage_id in visit.passage_ids]
        # Evidence store first (§5.1 principle 4): passages saved by earlier runs count too.
        words = sorted(_terms(self.task.question))[:12]
        query = " or ".join(['"money laundering"', *words])
        found = self.conn.execute(
            "select passage_id from public.search_passages(%s, %s, %s)", (self.ctx.workspace_id, query, 15)
        ).fetchall()
        ids.extend(row["passage_id"] for row in found if row["passage_id"] not in ids)
        passages = self.store.get_passages(self.ctx.workspace_id, ids)
        terms = _terms(f"{self.ctx.brief.topic} money laundering terrorism financing {self.task.question}")
        feed_urls = {visit.url for visit in self.visits if visit.url.endswith(".xml") or "/rss" in visit.url.lower()}
        # Documents first; feed lines (titles and dates only) rank below them.
        passages.sort(key=lambda p: (p.source_url in feed_urls, -len(terms & _terms(p.content))))
        chosen, total = [], 0
        for passage in passages:
            if len(chosen) >= MAX_PASSAGES_SHOWN or total + len(passage.content) > MAX_PASSAGE_CHARS:
                break
            chosen.append(passage)
            total += len(passage.content)
        return chosen

    def _report(self) -> tuple[ScoutReport, dict[str, UUID]]:
        expected = {row.id: row for row in self.store.list_expected_sources(
            self.ctx.workspace_id, self.ctx.brief.topic, self.ctx.brief.jurisdictions)}
        labels = LabelMap()
        expected_labels = {labels.add("E", expected_id): expected[expected_id]
                           for expected_id in self.task.expected_source_ids if expected_id in expected}
        passages = self._passages()
        if not passages:
            statuses = [{"expected_source_label": label, "status": "missing", "note": "no readable pages were saved"}
                        for label in expected_labels]
            return ScoutReport(documents=[], expected_source_statuses=statuses, notes="no passages"), labels.as_dict()
        quoted = [quote_passage(labels.add("P", passage.id), passage) for passage in passages]
        expected_lines = [f"{label}: {row.jurisdiction_code} | {row.category} | {row.document_hint}"
                          for label, row in expected_labels.items()]
        user = "\n\n".join([
            brief_text(self.ctx.brief),
            f"Research question: {self.task.question}",
            "Expected sources for this task:\n" + ("\n".join(expected_lines) or "none"),
            "Passages:\n\n" + "\n\n".join(quoted),
        ])

        def check(output: ScoutReport) -> None:
            for document in output.documents:
                labels.resolve_all(document.relevant_passage_labels, "P")
                labels.resolve_all(document.expected_source_labels, "E")
            for status in output.expected_source_statuses:
                labels.resolve(status.expected_source_label, "E")

        result = call_checked(self.scout.client, role=self.task.role, system=REPORT_SYSTEM, user=user,
                              output_type=ScoutReport, prompt_version=PROMPT_VERSION, check=check)
        self._used(result)
        return result.output, labels.as_dict()
