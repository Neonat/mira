"""Pure review-screen projections; reviewed evidence never comes from live rows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mira.contracts import ReportSnapshot
from mira.render import frozen_context

LEGACY_NOTE = (
    "This reviewed report has no full frozen evidence bundle. Keep its existing report file; "
    "regeneration requires fresh verification and review."
)


@dataclass(frozen=True)
class ReviewDisplay:
    findings: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    legacy_note: str | None = None


def dependency_closure(roots: set[str], edges: list[dict[str, Any]]) -> set[str]:
    """Include every transitive supporting finding, tolerating repeated edges/cycles."""
    dependencies: dict[str, set[str]] = {}
    for edge in edges:
        dependencies.setdefault(str(edge["finding_id"]), set()).add(str(edge["depends_on_finding_id"]))
    retained, pending = set(roots), list(roots)
    while pending:
        for dependency in dependencies.get(pending.pop(), set()) - retained:
            retained.add(dependency)
            pending.append(dependency)
    return retained


def pending_review_ids(cited: set[str], edges: list[dict[str, Any]],
                       latest_reviews: dict[str, dict[str, Any]]) -> set[str]:
    """Match sign-off's direct-root gate and retained supporting-finding gate.

    Rejection excludes every dependent finding before choosing retained roots.
    Original roots still need decisions even when a rejected ancestor excludes them.
    """
    original = dependency_closure(cited, edges)
    excluded = {fid for fid in original if latest_reviews.get(fid, {}).get("decision") == "rejected"}
    dependents: dict[str, set[str]] = {}
    for edge in edges:
        child, parent = str(edge["finding_id"]), str(edge["depends_on_finding_id"])
        if child in original:
            dependents.setdefault(parent, set()).add(child)
    pending = list(excluded)
    while pending:
        for child in dependents.get(pending.pop(), set()) - excluded:
            excluded.add(child)
            pending.append(child)
    retained = dependency_closure(cited - excluded, edges)
    return {fid for fid in cited | retained if not latest_reviews.get(fid, {}).get("decision")}


def reviewed_display(raw_snapshot: dict[str, Any], *, workspace_id: str,
                     run_id: str, revision_id: str) -> ReviewDisplay:
    """Validate new bundles and project frozen rows; legacy never reads live evidence."""
    if raw_snapshot.get("evidence_bundle") is None:
        historical = [{"id": fid, "title": "Historical finding", "content": "", "excluded_only": True, "historical_only": True}
                      for fid in raw_snapshot.get("review_outcomes", {})]
        return ReviewDisplay(historical, [], [], LEGACY_NOTE)
    snapshot = ReportSnapshot.model_validate(raw_snapshot)
    bundle = snapshot.evidence_bundle
    assert bundle is not None
    if (str(bundle.workspace_id) != workspace_id or str(bundle.analysis_run_id) != run_id
            or str(bundle.analysis_revision_id) != revision_id):
        raise ValueError("Frozen evidence does not match this report's workspace, run or revision.")
    frozen_context(snapshot, datetime.now(UTC))
    findings, evidence, checks = [], [], []
    for fid, finding in bundle.findings.items():
        row = finding.model_dump(mode="json")
        row["id"] = str(fid)
        findings.append(row)
        for citation in finding.evidence:
            evidence.append({"finding_id": str(fid), **citation.model_dump(mode="json")})
        checks.append({"finding_id": str(fid), **bundle.verifications[fid].model_dump(mode="json")})
    for fid, outcome in snapshot.review_outcomes.items():
        if fid not in bundle.findings:
            # An excluded outcome need not retain the original claim text.
            findings.append({"id": str(fid), "title": "Excluded finding", "content": "",
                             "excluded_only": True})
    return ReviewDisplay(findings, evidence, checks)
