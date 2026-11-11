"""Writer: verified claims → report sections (PRD v2 §5.2, §9, AG10).

The writer sees verified claims only, never passages or pages. It selects and
orders them; code renders their complete saved content instead of the writer's
free prose. Every sentence must cite a verified claim, and code rejects unknown
labels before anything is saved. Structural (uncited) text comes from code only. "Coverage and limitations" is built from run
records in code, and "What changed" belongs to the re-run diff, so the writer
fills the other sections.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from mira.agents.common import NO_CONCLUSIONS_RULE, brief_text
from mira.contracts import Brief, LabelMap, ReportSection, ReportSentence, WriterOutput
from mira.llm import LLMClient, LLMResult, call_checked
from mira.store import StoredClaim

PROMPT_VERSION = "writer/4"

WRITER_SECTIONS: tuple[str, ...] = (
    "executive_summary", "regulatory_developments", "deadlines_timeline", "jurisdiction_comparison",
    "supervisory_trends", "industry_developments", "impact_assessment",
)

SECTION_FOR_TYPE: dict[str, str] = {
    "obligation_summary": "regulatory_developments",
    "regulatory_requirement": "regulatory_developments",
    "external_fact": "regulatory_developments",
    "deadline": "deadlines_timeline",
    "jurisdiction_comparison": "jurisdiction_comparison",
    "trend": "supervisory_trends",
    "industry_development": "industry_developments",
    "risk_implication": "impact_assessment",
    "opportunity": "impact_assessment",
    "applicability_assessment": "impact_assessment",
    "audit_question": "impact_assessment",
}

SYSTEM = f"""You are the writer in Mira, a research assistant for bank internal auditors.
Select and order verified claim labels only. Return exactly these sections, once each, in order: {", ".join(WRITER_SECTIONS)}.
Each section contains groups of labels; each group is one summary sentence or ordered set of findings. Do not produce prose or facts. Use only labels provided. Return empty groups for sections without selections.
Select at most eight groups for the executive summary and at most 64 label references total across all sections. Code automatically includes every omitted finding in its main section and renders saved claim content.
Select only relevant labels for each section; impact assessment is limited to verified inference claims. Dated items in the timeline are sorted by code.
{NO_CONCLUSIONS_RULE}"""


class WriterPlanSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: str
    groups: list[Annotated[list[str], Field(min_length=1, max_length=64)]] = Field(max_length=64)


class WriterPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[WriterPlanSection] = Field(min_length=7, max_length=7)


@dataclass(frozen=True)
class WrittenReport:
    sections: list[ReportSection]
    llm: LLMResult[WriterPlan]
    grounded_sentences: int = 0


def _claim_line(label: str, claim: StoredClaim) -> str:
    draft = claim.draft
    fields = {
        "type": draft.finding_type + (" (inference)" if draft.is_inference else ""),
        "jurisdiction": draft.jurisdiction_code,
        "change": draft.change_type,
        "industry_category": draft.industry_category,
        "key_date": f"{draft.key_date.isoformat()} ({draft.key_date_kind})" if draft.key_date else None,
        "priority": f"{draft.priority} ({draft.priority_reason})" if draft.priority_reason else draft.priority,
        "evidence_confidence": (
            f"{draft.evidence_confidence} ({draft.evidence_confidence_reason})"
            if draft.evidence_confidence_reason else draft.evidence_confidence
        ),
    }
    meta = "; ".join(f"{key}: {value}" for key, value in fields.items() if value)
    return f"{label} [{meta}]\n{draft.title}\n{draft.content}"


def write(client: LLMClient, brief: Brief, verified: Sequence[StoredClaim]) -> WrittenReport:
    labels = LabelMap()
    lines = [_claim_line(labels.add("C", claim.finding_id), claim) for claim in verified]
    user = f"{brief_text(brief)}\n\nVerified claims:\n\n" + "\n\n".join(lines)

    def check(output: WriterPlan) -> None:
        keys = [section.section for section in output.sections]
        if tuple(keys) != WRITER_SECTIONS:
            raise ValueError(f"return exactly these sections in order: {', '.join(WRITER_SECTIONS)}")
        if len(output.sections[0].groups) > 8:
            raise ValueError("executive summary may contain at most eight groups")
        if sum(len(group) for section in output.sections for group in section.groups) > 64:
            raise ValueError("plan may contain at most 64 label references")
        for section in output.sections:
            for group in section.groups:
                if not group:
                    raise ValueError("claim label groups must not be empty")
                labels.resolve_all(group, "C")

    result = call_checked(
        client, role="writer", system=SYSTEM, user=user, output_type=WriterPlan,
        prompt_version=PROMPT_VERSION, check=check,
    )
    # Reuse the established grounding gate; placeholders never reach the report.
    draft = WriterOutput(sections=[{
        "section": section.section,
        "sentences": [{"text": "", "claim_labels": group, "structural": False}
                      for group in section.groups],
        "no_verified_items": not section.groups,
    } for section in result.output.sections])
    sections, replaced = ground_sections(draft, labels, verified)
    return WrittenReport(sections, result, replaced)



def ground_sections(output: WriterOutput, labels: LabelMap,
                    verified: Sequence[StoredClaim]) -> tuple[list[ReportSection], int]:
    """Final deterministic support gate: render only complete, verified claim content.

    Citation validity cannot establish entailment. The writer controls selection
    and order, but its free prose never enters a report. Full statements avoid
    changing meaning by removing a negation or condition from a quoted substring.
    Section eligibility also prevents factual claims being presented as newly
    inferred risks or recommendations. The same gate applies to both model arms.
    """
    by_id = {claim.finding_id: claim for claim in verified}
    sections = []
    replaced = 0
    for section in output.sections:
        sentences = []
        seen = set()
        for sentence in section.sentences:
            ids = labels.resolve_all(sentence.claim_labels, "C")
            eligible = []
            for finding_id in ids:
                claim = by_id[finding_id]
                allowed = (section.section == "executive_summary"
                           or SECTION_FOR_TYPE[claim.draft.finding_type] == section.section
                           or (section.section == "deadlines_timeline" and claim.draft.key_date is not None))
                if allowed and finding_id not in seen:
                    eligible.append(claim)
                    seen.add(finding_id)
            text = " ".join(claim.draft.content for claim in eligible)
            if text != sentence.text:
                replaced += 1
            if eligible and section.section == "executive_summary":
                sentences.append(ReportSentence(text=text, finding_ids=[c.finding_id for c in eligible], structural=False))
            elif eligible:
                sentences.extend(_finding_sentence(claim) for claim in eligible)
        if section.section != "executive_summary":
            sentences.extend(
                _finding_sentence(claim) for claim in verified
                if SECTION_FOR_TYPE[claim.draft.finding_type] == section.section and claim.finding_id not in seen
            )
        if section.section == "deadlines_timeline":
            sentences.sort(key=lambda sentence: by_id[sentence.finding_ids[0]].draft.key_date or date.max)
        sections.append(ReportSection(section=section.section, sentences=sentences, no_verified_items=not sentences))
    return sections, replaced


def _finding_sentence(claim: StoredClaim) -> ReportSentence:
    return ReportSentence(text=claim.draft.content, finding_ids=[claim.finding_id], structural=False)


def claim_sections(verified: Sequence[StoredClaim]) -> list[ReportSection]:
    """Report sections without a model: each verified claim becomes one sentence citing itself.

    Used when there is nothing to write or the writer's output was rejected.
    """
    by_section: dict[str, list[StoredClaim]] = {key: [] for key in WRITER_SECTIONS}
    for claim in verified:
        by_section[SECTION_FOR_TYPE[claim.draft.finding_type]].append(claim)
    by_section["deadlines_timeline"].sort(key=lambda claim: claim.draft.key_date or date.max)
    sections = []
    for key, claims in by_section.items():
        if key == "executive_summary":
            note = "No summary was written for this run; the sections below list each verified claim."
            sentences = [ReportSentence(text=note, finding_ids=[], structural=True)] if verified else []
            sections.append(ReportSection(section=key, sentences=sentences, no_verified_items=not verified))
            continue
        sentences = [_finding_sentence(claim) for claim in claims]
        sections.append(ReportSection(section=key, sentences=sentences, no_verified_items=not claims))
    return sections
