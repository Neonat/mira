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

from mira.agents.common import NO_CONCLUSIONS_RULE, brief_text
from mira.contracts import Brief, LabelMap, ReportSection, ReportSentence, WriterOutput
from mira.llm import LLMClient, LLMResult, call_checked
from mira.store import StoredClaim

PROMPT_VERSION = "writer/2"

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
Write the report sections from the verified claims given. Return exactly these sections, once each, in this order: {", ".join(WRITER_SECTIONS)}.

Rules:
- Select and order verified claims. Copy their content verbatim; do not paraphrase, infer, or add recommendations. Code renders the saved claim text, not newly generated prose.
- Every sentence must list the claim labels it rests on (C1, C2) and set structural to false. Headings are added for you.
- Keep inferences worded as assessments, not facts.
- regulatory_developments: by jurisdiction, each item's change (new, amended, upcoming) and plain-language obligation.
- deadlines_timeline: one sentence per dated item, sorted by date.
- impact_assessment: only verified inference claims (risks, opportunities and suggested audit actions). Do not derive these from factual claims yourself.
- executive_summary: at most eight sentences.
- If a section has no claims for it, set no_verified_items to true and give no sentences.
- {NO_CONCLUSIONS_RULE}"""


@dataclass(frozen=True)
class WrittenReport:
    sections: list[ReportSection]
    llm: LLMResult[WriterOutput]
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

    def check(output: WriterOutput) -> None:
        keys = [section.section for section in output.sections]
        if tuple(keys) != WRITER_SECTIONS:
            raise ValueError(f"return exactly these sections in order: {', '.join(WRITER_SECTIONS)}")
        for section in output.sections:
            # Structural text comes from code only; an uncited "structural" sentence could carry a fact (C7).
            if any(sentence.structural for sentence in section.sentences):
                raise ValueError("every sentence must cite claims and set structural to false")
            if section.no_verified_items and section.sentences:
                raise ValueError(f"{section.section} is marked no_verified_items but has sentences")
            if not section.no_verified_items and not section.sentences:
                raise ValueError(f"{section.section} has no sentences; set no_verified_items")
            for sentence in section.sentences:
                # AG10: only verified claims were labelled, so this rejects anything else.
                labels.resolve_all(sentence.claim_labels, "C")

    result = call_checked(
        client, role="writer", system=SYSTEM, user=user, output_type=WriterOutput,
        prompt_version=PROMPT_VERSION, check=check,
    )
    sections, replaced = ground_sections(result.output, labels, verified)
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
            if eligible:
                sentences.append(ReportSentence(text=text, finding_ids=[c.finding_id for c in eligible], structural=False))
        sections.append(ReportSection(section=section.section, sentences=sentences, no_verified_items=not sentences))
    return sections, replaced


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
        sentences = [
            ReportSentence(text=f"{claim.draft.title}. {claim.draft.content}", finding_ids=[claim.finding_id], structural=False)
            for claim in claims
        ]
        sections.append(ReportSection(section=key, sentences=sentences, no_verified_items=not claims))
    return sections
