"""Completeness check against the expected-source list (PRD v2 §6.4, AG09).

Code first: a scout's "found" or "no change" counts only if the run actually
read that expected source, either by saving a page from its own hosts in this
run or by citing a passage from it that is already in the evidence store (a
manual import, for example). Everything else is reported as missing, fetch
failed or out of budget, with the reason, so the report never presents partial
coverage as complete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from mira.contracts import CoverageRow, ScoutResult
from mira.interfaces import ScoutTask
from mira.store import ExpectedSourceRecord, PassageRecord, SourceRecord


def source_hosts(source: SourceRecord) -> set[str]:
    hosts = {(urlsplit(source.base_url).hostname or "").lower()} if source.base_url else set()
    hosts.update(host.lower() for host in source.connector_config.get("extra_hosts", []))
    return hosts - {""}


def coverage_rows(
    expected: Sequence[ExpectedSourceRecord],
    sources: Mapping[UUID, SourceRecord],
    tasks: Sequence[ScoutTask],
    results: Mapping[str, ScoutResult],
    skipped: Mapping[str, str],
    gap_round: int = 0,
    passages: Mapping[UUID, PassageRecord] | None = None,
) -> list[CoverageRow]:
    """One row per expected source. ``results`` and ``skipped`` are keyed by task label;
    ``passages`` holds the passages the scouts cited, keyed by ID."""
    passages = passages or {}
    rows = []
    for item in expected:
        source = sources.get(item.source_id)
        if source is None or "fetch" not in source.permitted_operations:
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note="source refuses automated access; needs a manual import"))
            continue
        assigned = [task for task in tasks if item.id in task.expected_source_ids]
        ran = [task for task in assigned if task.task_label in results]
        if not ran:
            reasons = [skipped[task.task_label] for task in assigned if task.task_label in skipped]
            budget = any("budget" in reason for reason in reasons)
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round,
                                    status="out_of_budget" if budget else "missing", document_version_id=None,
                                    note=reasons[0] if reasons else "no scout task covered this item"))
            continue

        hosts = source_hosts(source)
        statuses: set[str] = set()
        attempts = []
        cited: list[PassageRecord] = []
        for task in ran:
            result = results[task.task_label]
            label = next((lab for lab, real in result.labels.items() if lab.startswith("E") and real == item.id), None)
            statuses.update(s.status for s in result.report.expected_source_statuses if s.expected_source_label == label)
            attempts.extend(a for a in result.fetch_log if (urlsplit(a.url).hostname or "").lower() in hosts)
            for document in result.report.documents:
                if label is None or label not in document.expected_source_labels:
                    continue
                for passage_label in document.relevant_passage_labels:
                    passage = passages.get(result.labels.get(passage_label))
                    if passage is not None and passage.source_id == item.source_id:
                        cited.append(passage)
        saved = [a for a in attempts if a.outcome in ("saved", "unchanged", "reused") and a.document_version_id]
        found = bool(cited) and "found" in statuses
        evidence = cited[0].document_version_id if cited else (saved[0].document_version_id if saved else None)
        if evidence and (found or "no_change" in statuses):
            status = "found" if found else "no_change"
            note = "from documents imported by hand" if not saved and any(p.imported for p in cited) else None
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status=status,
                                    document_version_id=evidence, note=note))
        elif attempts and not saved and not cited:
            error = next((a.error for a in attempts if a.error), "every fetch failed")
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="fetch_failed",
                                    document_version_id=None, note=error))
        else:
            note = "pages were read but no matching development was reported" if saved else "no page from this source was read"
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note=note))
    return rows
