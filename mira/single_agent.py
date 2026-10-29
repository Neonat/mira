"""The single-agent arm of PRD v2 §11, built from the same parts as the multi-agent system.

See docs/single_agent_arm_design.md. The orchestrator, tools, analyst, writer, budgets and report
renderer are shared. Only two things change: the plan is built by code (no planner model), and the
verifier checks quotes deterministically without a second model (no independent meaning check).

Nothing here calls a model. The arm runs through the same Orchestrator as the multi-agent system, so a
live run uses the real code path and only the difference described in the design is measured.
"""

from __future__ import annotations

from collections.abc import Sequence

from mira.agents.planner import PlannedRun
from mira.agents.verifier import quote_match
from mira.contracts import Brief, LabelMap, ResearchPlan, Verdict
from mira.interfaces import CheckOutcome, ScoutTask
from mira.llm import LLMResult
from mira.store import ExpectedSourceRecord, PassageRecord, SourceRecord, StoredClaim

SINGLE_TASK_LABEL = "T1"
PROMPT_VERSION = "single-agent/1"


def code_plan(
    brief: Brief,
    sources: Sequence[SourceRecord],
    expected: Sequence[ExpectedSourceRecord],
    max_documents: int,
) -> PlannedRun:
    """One regulatory scout task covering every allow-listed source and expected item for the brief.

    Built by code, so no planner model is called. The labels follow the planner's scheme (S1, E1 and so on),
    so the stored plan and the completeness check work unchanged.
    """
    if not sources:
        raise ValueError("the single-agent arm needs at least one allow-listed source")
    labels = LabelMap()
    for source in sources:
        labels.add("S", source.id)
    for row in expected:
        labels.add("E", row.id)
    source_labels = [f"S{number}" for number in range(1, len(sources) + 1)]
    expected_labels = [f"E{number}" for number in range(1, len(expected) + 1)]
    plan = ResearchPlan.model_validate({
        "tasks": [{
            "task_label": SINGLE_TASK_LABEL,
            "scout": "regulatory_scout",
            "jurisdiction_code": brief.jurisdictions[0] if len(brief.jurisdictions) == 1 else None,
            "question": f"Developments in {brief.topic} for {', '.join(brief.jurisdictions)} in the period",
            "source_labels": source_labels,
            "expected_source_labels": expected_labels,
            "max_documents": max(1, min(50, max_documents)),
        }],
        "notes": "single-agent arm: plan built by code",
    })
    task = plan.tasks[0]
    tasks = (ScoutTask(
        task_label=task.task_label, role="regulatory_scout", jurisdiction_code=task.jurisdiction_code,
        question=task.question, source_ids=tuple(labels.resolve_all(task.source_labels, "S")),
        expected_source_ids=tuple(labels.resolve_all(task.expected_source_labels, "E")),
        max_documents=task.max_documents,
    ),)
    no_model = LLMResult(output=plan, model=None, prompt_version=PROMPT_VERSION, tokens_in=0, tokens_out=0)
    return PlannedRun(plan=plan, tasks=tasks, labels=labels.as_dict(), llm=no_model)


class QuoteOnlyVerifier:
    """Verifier for the single-agent arm: the deterministic quote check and nothing else (design §3).

    A fact is ``supported`` only if every supporting quote appears in its cited passage. There is no second
    model, so a claim that quotes real text but overstates it passes here. That is the cost being measured.
    """

    def check_fact(self, claim: StoredClaim, passages: Sequence[PassageRecord], attempt: int) -> CheckOutcome:
        by_id = {passage.id: passage for passage in passages}
        missing = [
            item.supporting_quote for item in claim.evidence
            if item.passage_id not in by_id or not quote_match(item.supporting_quote, by_id[item.passage_id].content)
        ]
        verdict = "unsupported" if missing else "supported"
        check = Verdict(
            finding_id=claim.finding_id, attempt=attempt, method="quote_match", verdict=verdict,
            reason=(f"quote not found in the cited passage: {missing[0][:200]!r}" if missing
                    else "every supporting quote was found in its cited passage"),
            model=None, prompt_version=None,
        )
        return CheckOutcome(verdict, (check,), None, None, 0, 0)

    def check_inference(self, claim: StoredClaim, facts: Sequence[StoredClaim], attempt: int) -> CheckOutcome:
        """An inference is supported only if it rests on at least one verified fact.

        This does not look for new facts in the inference's wording. Without a second model that check does
        not exist in this arm, and the reason says so, so a reader cannot take the verdict for more than it is.
        """
        if not facts:
            verdict = "unsupported"
            reason = "an inference with no verified facts to rest on"
        else:
            verdict = "supported"
            reason = (f"rests on {len(facts)} verified fact(s); single-agent arm does not check the wording "
                      "for new facts")
        # Recorded as the deterministic method. The inference rule here checks only that the claim rests on
        # verified facts, which is code, not a model; the contract allows no model-free inference method, so
        # the label must not claim an inference model ran.
        check = Verdict(
            finding_id=claim.finding_id, attempt=attempt, method="quote_match", verdict=verdict,
            reason=reason, model=None, prompt_version=None,
        )
        return CheckOutcome(verdict, (check,), None, None, 0, 0)
