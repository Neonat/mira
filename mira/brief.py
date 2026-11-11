"""Research brief scope and storage (PRD v2 §4, AG01; risk G4).

Topic and jurisdictions come from controlled lists so no free text reaches a
hosted model. A brief is saved as a Project revision plus the run's own columns,
and a re-run rebuilds the same brief from those rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import get_args

from mira.budget import RunBudget
from mira.contracts import Brief, Topic
from mira.research_settings import ResearchSettings

from mira.topics import CYBERSECURITY

MVP_TOPICS: tuple[str, ...] = get_args(Topic)
MVP_JURISDICTIONS: tuple[str, ...] = ("SG", "HK", "AU", "AE")


def check_brief_scope(brief: Brief) -> None:
    """Raise unless the brief stays inside the MVP's controlled lists."""
    if brief.topic not in MVP_TOPICS:
        raise ValueError(f"topic {brief.topic!r} is not offered")
    unknown = sorted(set(brief.jurisdictions) - set(MVP_JURISDICTIONS))
    if unknown:
        raise ValueError(f"jurisdictions not offered: {unknown}")
    if brief.topic == CYBERSECURITY and brief.jurisdictions != ["AE"]:
        raise ValueError("Cybersecurity currently covers UAE federal sources. Select UAE only.")
    if len(set(brief.jurisdictions)) != len(brief.jurisdictions):
        raise ValueError("jurisdictions are repeated")


def project_revision_fields(brief: Brief, change_reason: str) -> dict[str, object]:
    """Columns for public.project_revisions."""
    markets = ", ".join(brief.jurisdictions)
    return {
        "title": f"{brief.topic} developments: {markets}",
        "objective": f"Regulatory and industry developments in {brief.topic} for {markets}",
        "risk_topics": [brief.topic],
        "markets": list(brief.jurisdictions),
        "reporting_period_start": brief.period_start,
        "reporting_period_end": brief.period_end,
        "change_reason": change_reason,
    }


def analysis_run_fields(brief: Brief, budget: RunBudget, models: Mapping[str, str], *, settings: ResearchSettings | None = None) -> dict[str, object]:
    """Columns for public.analysis_runs that pin the brief and settings for this run."""
    values = {
        "query_mode": "current",
        "as_of_date": brief.as_of_date,
        "resolved_markets": list(brief.jurisdictions),
        "source_limits": budget.as_source_limits(),
        "model_settings": dict(models),
        "retrieval_settings": {"plan_requires_approval": brief.plan_requires_approval},
    }
    if settings is not None:
        values['retrieval_settings']['research'] = settings.as_dict()
    return values


def brief_from_rows(revision: Mapping[str, object], run: Mapping[str, object]) -> Brief:
    """Rebuild the brief a run used, for a re-run of the same revision."""
    topics = list(revision["risk_topics"])
    if len(topics) != 1:
        raise ValueError("a brief has exactly one topic")
    return Brief(
        topic=topics[0],
        jurisdictions=[str(code).strip() for code in revision["markets"]],
        period_start=revision["reporting_period_start"],
        period_end=revision["reporting_period_end"],
        as_of_date=run["as_of_date"],
        plan_requires_approval=bool(run["retrieval_settings"].get("plan_requires_approval", False)),
    )


RERUNNABLE_STATUSES: frozenset[str] = frozenset({"draft", "reviewed", "superseded"})


def check_rerunnable(previous_status: str) -> None:
    """Raise unless the previous run finished with a report, so the diff has something complete to compare.

    A queued, running, failed or cancelled run has no complete findings, so a re-run must not diff against it.
    """
    if previous_status not in RERUNNABLE_STATUSES:
        raise ValueError(f"a run with status {previous_status!r} cannot be re-run; re-run a finished run")
