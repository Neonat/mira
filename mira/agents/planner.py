"""Planner: brief + allow-list + expected sources → research plan (PRD v2 §5.2, AG02).

Code, not the model, decides whether the plan is acceptable: every label must
resolve, regulatory tasks stay inside their jurisdiction, every expected source
for the brief's jurisdictions is assigned to a task that may read its source,
and expected items from international sources go to jurisdiction-free tasks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from mira.agents.common import brief_text
from mira.contracts import Brief, LabelMap, ResearchPlan
from mira.interfaces import ScoutTask
from mira.llm import LLMClient, LLMResult, call_checked
from mira.store import ExpectedSourceRecord, SourceRecord

PROMPT_VERSION = "planner/3"

SYSTEM = """You plan research for Mira, a research assistant for bank internal auditors.
Given a research brief, the allow-listed sources and the expected-source checklist, return a research plan made of scout tasks.

Rules:
- Give each jurisdiction the plan must cover at least one regulatory_scout task with jurisdiction_code set. A regulatory task may use only sources from its own jurisdiction or international sources.
- Use industry_scout tasks for industry developments: incidents, case studies, best practices and innovations. Their jurisdiction_code may be null.
- Put every expected source in expected_source_labels of at least one task, and give that task the expected source's own source. A task with a jurisdiction_code may list only expected sources of that jurisdiction.
- International sources serve every jurisdiction in the brief. Cover all expected sources that come from international sources in one industry_scout task with jurisdiction_code null, and do not repeat those sources in per-jurisdiction tasks.
- Write specific questions: name the instrument or publication type and the period.
- Refer to sources and expected sources only by the labels given (S1, E1). Label tasks T1, T2 and so on.
- max_documents is how many pages the scout may fetch for the task. Together, the tasks' max_documents must stay within the run's document budget; give more to the sources most likely to hold new rules."""


@dataclass(frozen=True)
class PlannedRun:
    plan: ResearchPlan
    tasks: tuple[ScoutTask, ...]
    labels: dict[str, UUID]
    llm: LLMResult[ResearchPlan]

    def stored_plan(self) -> dict[str, object]:
        """research_plans.plan: the model's plan and the labels it used."""
        return {
            "plan": self.plan.model_dump(mode="json"),
            "labels": {label: str(real_id) for label, real_id in self.labels.items()},
        }


def plan(
    client: LLMClient,
    brief: Brief,
    sources: Sequence[SourceRecord],
    expected: Sequence[ExpectedSourceRecord],
    max_documents: int,
    *,
    gap_round: int = 0,
) -> PlannedRun:
    """Ask for a plan within ``max_documents`` pages in total.

    The total is guidance for the model, not a check: the orchestrator shares the
    run's real document budget across tasks whatever the plan asks for.

    In a gap round (``gap_round`` >= 1), ``expected`` holds only the items still missing,
    and the plan must cover those items and the jurisdictions they belong to.
    """
    labels = LabelMap()
    source_labels = {labels.add("S", source.id): source for source in sources}
    expected_labels = {labels.add("E", row.id): row for row in expected}
    label_of_source = {source.id: label for label, source in source_labels.items()}

    source_lines = [
        f"{label}: {source.name} | jurisdiction {source.jurisdiction_code or 'international'} | "
        f"type {source.source_type} | {source.base_url or 'manual import'}"
        for label, source in source_labels.items()
    ]
    expected_lines = [
        f"{label}: {row.jurisdiction_code} | {row.category} | {row.document_hint} | "
        f"source {label_of_source.get(row.source_id, 'not on the allow-list')}"
        for label, row in expected_labels.items()
    ]
    list_version = max((row.list_version for row in expected), default=0)
    # A gap round needs regulatory coverage only for jurisdictions with a missing regulatory item.
    regulatory_gap_jurisdictions = {
        row.jurisdiction_code for row in expected
        if (label_of_source.get(row.source_id) is not None
            and source_labels[label_of_source[row.source_id]].jurisdiction_code is not None)
    }
    jurisdictions = (
        sorted(regulatory_gap_jurisdictions & set(brief.jurisdictions)) if gap_round else list(brief.jurisdictions)
    )
    gap_note = [
        f"Gap round {gap_round}: an earlier round did not find the expected sources listed below. "
        "Plan tasks only for them, and write each question so it names the item it targets.",
    ] if gap_round else []
    user = "\n\n".join([
        brief_text(brief),
        *gap_note,
        f"Document budget: the run may fetch at most {max_documents} pages in total.",
        "Sources:\n" + "\n".join(source_lines),
        f"Expected sources (checklist v{list_version}):\n" + ("\n".join(expected_lines) or "none"),
    ])

    def check(output: ResearchPlan) -> None:
        task_labels = [task.task_label for task in output.tasks]
        if len(set(task_labels)) != len(task_labels):
            raise ValueError("duplicate task_label")
        covered: set[str] = set()
        regulatory_jurisdictions: set[str] = set()
        for task in output.tasks:
            code = task.jurisdiction_code
            if code is not None and code not in brief.jurisdictions:
                raise ValueError(f"{task.task_label} uses jurisdiction {code}, which is not in the brief")
            if task.scout == "regulatory_scout":
                if code is None:
                    raise ValueError(f"{task.task_label}: a regulatory task needs a jurisdiction_code")
                regulatory_jurisdictions.add(code)
            for label in task.source_labels:
                labels.resolve(label, "S")
                source = source_labels[label]
                if task.scout == "regulatory_scout" and source.jurisdiction_code not in (None, code):
                    raise ValueError(f"{task.task_label} uses {label}, a {source.jurisdiction_code} source")
            for label in task.expected_source_labels:
                labels.resolve(label, "E")
                row = expected_labels[label]
                if code is not None and row.jurisdiction_code != code:
                    raise ValueError(f"{task.task_label} is for {code} but lists {label}, a {row.jurisdiction_code} item")
                # The scout can only find the item if it may read the item's source.
                source_label = label_of_source.get(row.source_id)
                if source_label is not None and source_label not in task.source_labels:
                    raise ValueError(f"{task.task_label} lists {label} but not its source {source_label}")
                # One jurisdiction-free task per international source, not a copy per jurisdiction.
                if code is not None and source_label is not None and source_labels[source_label].jurisdiction_code is None:
                    raise ValueError(
                        f"{task.task_label} lists {label} from international source {source_label}; "
                        "cover it in a task with jurisdiction_code null"
                    )
                covered.add(label)
        missing = sorted(set(expected_labels) - covered, key=lambda label: int(label[1:]))
        if missing:
            raise ValueError(f"expected sources not assigned to any task: {', '.join(missing)}")
        uncovered = sorted(set(jurisdictions) - regulatory_jurisdictions)
        if uncovered:
            raise ValueError(f"no regulatory task for {', '.join(uncovered)}")

    result = call_checked(
        client, role="planner", system=SYSTEM, user=user, output_type=ResearchPlan,
        prompt_version=PROMPT_VERSION, check=check,
    )
    tasks = tuple(
        ScoutTask(
            task_label=task.task_label,
            role=task.scout,
            jurisdiction_code=task.jurisdiction_code,
            question=task.question,
            source_ids=tuple(labels.resolve_all(task.source_labels, "S")),
            expected_source_ids=tuple(labels.resolve_all(task.expected_source_labels, "E")),
            max_documents=task.max_documents,
        )
        for task in result.output.tasks
    )
    return PlannedRun(result.output, tasks, labels.as_dict(), result)
