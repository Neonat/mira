"""Completeness check against the expected-source list (PRD v2 §6.4, AG09).

Code first: a scout's "found" or "no change" requires saved passages linked
to that particular checklist item, including existing manual imports.
Domain-level fetch success alone does not establish coverage. Everything else is reported as missing, fetch
failed or out of budget, with the reason, so the report never presents partial
coverage as complete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from mira.contracts import CoverageRow, ScoutResult
from mira.coverage_display import EXTRACTION_ERROR_PREFIX, MANUAL_IMPORT_NOTE
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
        if source is None:
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note="source is unavailable to this brief"))
            continue
        if "fetch" in source.permitted_operations and "store_text" not in source.permitted_operations:
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None,
                                    note="source does not permit stored evidence; citation coverage cannot be established"))
            continue
        assigned = [task for task in tasks if item.id in task.expected_source_ids]
        ran = [task for task in assigned if task.task_label in results]
        if not ran:
            reasons = [skipped[task.task_label] for task in assigned if task.task_label in skipped]
            budget = any("budget" in reason for reason in reasons)
            if "fetch" not in source.permitted_operations:
                reasons = [MANUAL_IMPORT_NOTE]
                budget = False
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round,
                                    status="out_of_budget" if budget else "missing", document_version_id=None,
                                    note=reasons[0] if reasons else "no scout task covered this item"))
            continue

        hosts = source_hosts(source)
        statuses: set[str] = set()
        attempts = []
        cited: list[PassageRecord] = []
        inspected: list[PassageRecord] = []
        for task in ran:
            result = results[task.task_label]
            label = next((lab for lab, real in result.labels.items() if lab.startswith("E") and real == item.id), None)
            statuses.update(s.status for s in result.report.expected_source_statuses if s.expected_source_label == label)
            for status in result.report.expected_source_statuses:
                if status.expected_source_label != label or status.status != "no_change":
                    continue
                for passage_label in status.inspected_passage_labels:
                    passage = passages.get(result.labels.get(passage_label))
                    if passage is not None and passage.source_id == item.source_id:
                        inspected.append(passage)
            attempts.extend(a for a in result.fetch_log if (urlsplit(a.url).hostname or "").lower() in hosts)
            for document in result.report.documents:
                if label is None or label not in document.expected_source_labels:
                    continue
                for passage_label in document.relevant_passage_labels:
                    passage = passages.get(result.labels.get(passage_label))
                    if passage is not None and passage.source_id == item.source_id:
                        cited.append(passage)
        readable = [a for a in attempts
                    if a.outcome in ("saved", "unchanged", "reused") and a.document_version_id and not a.error]
        found = bool(cited) and "found" in statuses
        checked = cited if found else inspected or cited
        evidence = (cited[0].document_version_id if found else
                    checked[0].document_version_id if checked else None)
        if found or (checked and "no_change" in statuses):
            status = "found" if found else "no_change"
            note = "from documents imported by hand" if not readable and any(p.imported for p in checked) else None
            if status == "no_change":
                note = f"Inspected {checked[0].title}, passage {checked[0].passage_number}: {checked[0].source_url}"
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status=status,
                                    document_version_id=evidence, note=note))
        elif "fetch" not in source.permitted_operations:
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note=MANUAL_IMPORT_NOTE))
        elif attempts and not readable and not checked:
            extraction_error = next((a.error for a in attempts if a.document_version_id and a.error), None)
            error = (
                EXTRACTION_ERROR_PREFIX + extraction_error if extraction_error
                else next((a.error for a in attempts if a.error), "every fetch failed")
            )
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="fetch_failed",
                                    document_version_id=None, note=error))
        else:
            note = ("pages were read but checklist-specific coverage was not established" if readable or checked
                    else "no page from this source was read")
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note=note))
    return rows
