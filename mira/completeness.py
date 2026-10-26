"""Completeness check against the expected-source list (PRD v2 §6.4, AG09).

Code first: a scout's "found" or "no change" counts only if a page from that
expected source's own hosts was actually saved in this run. Everything else is
reported as missing, fetch failed or out of budget, with the reason, so the
report never presents partial coverage as complete.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from uuid import UUID

from mira.contracts import CoverageRow, ScoutResult
from mira.interfaces import ScoutTask
from mira.store import ExpectedSourceRecord, SourceRecord


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
) -> list[CoverageRow]:
    """One row per expected source. ``results`` and ``skipped`` are keyed by task label."""
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
        for task in ran:
            result = results[task.task_label]
            label = next((lab for lab, real in result.labels.items() if lab.startswith("E") and real == item.id), None)
            statuses.update(s.status for s in result.report.expected_source_statuses if s.expected_source_label == label)
            attempts.extend(a for a in result.fetch_log if (urlsplit(a.url).hostname or "").lower() in hosts)
        saved = [a for a in attempts if a.outcome in ("saved", "unchanged") and a.document_version_id]
        if saved and statuses & {"found", "no_change"}:
            status = "found" if "found" in statuses else "no_change"
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status=status,
                                    document_version_id=saved[0].document_version_id, note=None))
        elif attempts and not saved:
            error = next((a.error for a in attempts if a.error), "every fetch failed")
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="fetch_failed",
                                    document_version_id=None, note=error))
        else:
            note = "pages were read but no matching development was reported" if saved else "no page from this source was read"
            rows.append(CoverageRow(expected_source_id=item.id, gap_round=gap_round, status="missing",
                                    document_version_id=None, note=note))
    return rows
