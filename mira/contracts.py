"""Shared data formats passed between Mira's agents (PRD v2 §5, §6, §9).

Two kinds of model live here:

- AI-facing models (``*Draft``, ``ResearchPlan``, ``ScoutReport``, ``AnalystOutput``,
  ``WriterOutput``) are what a model is asked to return through structured output.
  They contain only what the model writes. Models never see or write database IDs:
  the orchestrator hands them short labels (``P1`` for passages, ``D1`` documents,
  ``E1`` expected sources, ``S1`` sources, ``C1`` claims) and resolves the labels
  in code with ``LabelMap``. A cited label that was not handed out is rejected,
  so an invented citation never reaches the database.
- Stored models (``Brief``, ``ScoutResult``, ``Verdict``, ``GapTask``,
  ``CoverageRow``, ``ReportSnapshot``, ``StepRecord``) are filled by code and carry
  real IDs and metadata.

Rules for AI-facing models, designed so one schema can serve both Anthropic and
OpenAI strict structured-output modes: every field is required (use ``X | None``
for "may be empty", never a default), extra fields are forbidden, and choices are
enums. Not yet checked against either API: confirm on the first real call that the
provider accepts ``pattern``, ``minItems`` and numeric limits. Pydantic enforces
them in Python either way.

Enum values are copied from the check constraints in ``supabase/migrations``.
Change both together, and bump ``CONTRACT_VERSION`` when a shape changes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, model_serializer

CONTRACT_VERSION = "1.4"

# --- Enums (mirror the database check constraints) ---------------------------

JurisdictionCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Topic = Literal["AML/CFT"]

FindingType = Literal[
    "external_fact", "regulatory_requirement", "applicability_assessment", "risk_implication",
    "audit_question", "obligation_summary", "deadline", "jurisdiction_comparison", "trend",
    "industry_development", "opportunity",
]
# Finding types that are inferences (§6.3): they rest on verified facts, not on one passage.
INFERENCE_FINDING_TYPES: frozenset[str] = frozenset(
    {"applicability_assessment", "risk_implication", "audit_question", "jurisdiction_comparison", "trend", "opportunity"}
)
ChangeType = Literal["new", "amended", "upcoming", "unchanged"]
IndustryCategory = Literal["incident", "case_study", "best_practice", "innovation"]
KeyDateKind = Literal["published", "effective", "deadline", "consultation_close", "event"]
Rating = Literal["high", "medium", "low", "unrated"]
InstrumentType = Literal["act", "regulation", "notice", "guideline", "consultation", "enforcement", "other"]
VerdictLabel = Literal["supported", "partially_supported", "unsupported", "contradicted"]
CheckMethod = Literal["quote_match", "llm", "inference_check"]
CoverageStatus = Literal["found", "no_change", "missing", "fetch_failed", "out_of_budget"]
AgentRole = Literal[
    "orchestrator", "planner", "regulatory_scout", "industry_scout", "analyst", "verifier",
    "completeness_checker", "writer",
]
StepStatus = Literal["queued", "running", "succeeded", "failed", "skipped", "cancelled"]
RunStatus = Literal["queued", "running", "partial", "failed", "cancelled", "draft", "reviewed", "superseded"]
PermittedOperation = Literal["metadata", "fetch", "store_text", "quote", "embed"]
ReportSectionKey = Literal[
    "executive_summary", "regulatory_developments", "deadlines_timeline", "jurisdiction_comparison",
    "supervisory_trends", "industry_developments", "impact_assessment", "what_changed",
    "coverage_limitations",
]

Label = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{1,4}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Brief (UI → planner) ------------------------------------------------------


class Brief(Contract):
    """Research brief from the form; saved as a Project revision (AG01)."""

    topic: Topic
    jurisdictions: list[JurisdictionCode] = Field(min_length=1)
    period_start: date
    period_end: date
    as_of_date: date
    plan_requires_approval: bool

    @model_validator(mode="after")
    def _period_order(self) -> Brief:
        if self.period_end < self.period_start:
            raise ValueError("period_end is before period_start")
        if self.as_of_date < self.period_end:
            raise ValueError("as_of_date is before period_end")
        return self


# --- Planner (AI) --------------------------------------------------------------


class PlanTask(Contract):
    task_label: Label
    scout: Literal["regulatory_scout", "industry_scout"]
    jurisdiction_code: JurisdictionCode | None
    question: str
    source_labels: list[Label] = Field(min_length=1)
    expected_source_labels: list[Label]
    max_documents: int = Field(ge=1, le=50)


class ResearchPlan(Contract):
    tasks: list[PlanTask] = Field(min_length=1)
    notes: str | None


# --- Scouts (AI report + code fetch log) ---------------------------------------


class LinkSelection(Contract):
    """Scout model output: which candidate links (``L1``...) to open next."""

    link_labels: list[Label]
    notes: str | None


class ScoutDocumentDraft(Contract):
    document_label: Label
    instrument_type: InstrumentType | None
    industry_category: IndustryCategory | None
    title: str
    published_date: date | None
    effective_date: date | None
    change_type: ChangeType | None
    relevant_passage_labels: list[Label] = Field(min_length=1)
    expected_source_labels: list[Label]


class ExpectedSourceStatusDraft(Contract):
    # Old saved scout reports omit inspection references. Require the field in
    # new strict model output while retaining those records' parseability.
    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra={
        "required": ["expected_source_label", "status", "note", "inspected_passage_labels"],
    })
    expected_source_label: Label
    status: Literal["found", "no_change", "missing"]
    note: str | None
    inspected_passage_labels: list[Label] = Field(default_factory=list)


class ScoutReport(Contract):
    """What the scout model returns. An empty ``documents`` list is a valid answer (AG05)."""

    documents: list[ScoutDocumentDraft]
    expected_source_statuses: list[ExpectedSourceStatusDraft]
    notes: str | None


class FetchAttempt(Contract):
    """Written by fetch_allowed, never by a model. Failures stay visible (AG06)."""

    url: str
    outcome: Literal["saved", "unchanged", "refused", "failed", "reused"]
    document_version_id: UUID | None
    error: str | None
    attempted_at: datetime


class ScoutResult(Contract):
    analysis_run_id: UUID
    agent_step_id: UUID
    role: Literal["regulatory_scout", "industry_scout"]
    jurisdiction_code: JurisdictionCode | None
    report: ScoutReport
    fetch_log: list[FetchAttempt]
    labels: dict[str, UUID]
    selection_diagnostics: dict = Field(default_factory=dict)


# --- Analyst (AI) --------------------------------------------------------------


class ClaimCitation(Contract):
    passage_label: Label
    supporting_quote: str = Field(min_length=1)


class ClaimDraft(Contract):
    claim_label: Label
    finding_type: FindingType
    title: str
    content: str
    jurisdiction_code: JurisdictionCode | None
    change_type: ChangeType | None
    industry_category: IndustryCategory | None
    key_date: date | None
    key_date_kind: KeyDateKind | None
    is_inference: bool
    citations: list[ClaimCitation]
    depends_on: list[Label]
    priority: Rating
    priority_reason: str | None
    evidence_confidence: Rating
    evidence_confidence_reason: str | None

    @model_validator(mode="after")
    def _facts_and_inference(self) -> ClaimDraft:
        if self.is_inference:
            if self.finding_type not in INFERENCE_FINDING_TYPES:
                raise ValueError(f"{self.finding_type} cannot be an inference")
            if not self.depends_on:
                raise ValueError("an inference must depend on at least one factual claim")
        else:
            if self.finding_type in INFERENCE_FINDING_TYPES:
                raise ValueError(f"{self.finding_type} must be marked as an inference")
            if not self.citations:
                raise ValueError("a factual claim must cite at least one passage")
            if self.depends_on:
                raise ValueError("only inferences may depend on other claims")
        if self.claim_label in self.depends_on:
            raise ValueError("a claim cannot depend on itself")
        if (self.key_date is None) != (self.key_date_kind is None):
            raise ValueError("key_date and key_date_kind must be set together")
        if self.industry_category is not None and self.finding_type != "industry_development":
            raise ValueError("industry_category is only for industry_development")
        return self


class AnalystOutput(Contract):
    claims: list[ClaimDraft]


# --- Verifier (code, then AI) --------------------------------------------------


class VerdictDraft(Contract):
    """Verifier model output for one claim against its cited passages."""

    verdict: VerdictLabel
    reason: str


class InferenceCheckDraft(Contract):
    """Model output for grounding and scope checks on an inference."""

    introduces_new_fact: bool
    new_facts: list[str]
    is_supported_assessment: bool
    reason: str


class Verdict(Contract):
    """One row of claim_checks."""

    finding_id: UUID
    attempt: int = Field(ge=1)
    method: CheckMethod
    verdict: VerdictLabel
    reason: str
    model: str | None
    prompt_version: str | None

    @model_validator(mode="after")
    def _model_for_llm(self) -> Verdict:
        if self.method != "quote_match" and self.model is None:
            raise ValueError("LLM checks must record the model")
        return self


# --- Gap filling and completeness (code) ---------------------------------------


class GapTask(Contract):
    """Sends a scout back for a better source (§6.3 step 4, §6.4 step 3)."""

    reason: Literal["unsupported_claim", "missing_expected_source"]
    gap_round: int = Field(ge=1)
    jurisdiction_code: JurisdictionCode | None
    finding_id: UUID | None
    expected_source_id: UUID | None
    question: str

    @model_validator(mode="after")
    def _target(self) -> GapTask:
        if self.reason == "unsupported_claim" and self.finding_id is None:
            raise ValueError("unsupported_claim gap needs finding_id")
        if self.reason == "missing_expected_source" and self.expected_source_id is None:
            raise ValueError("missing_expected_source gap needs expected_source_id")
        return self


class CoverageRow(Contract):
    """One row of coverage_results."""

    expected_source_id: UUID
    gap_round: int = Field(ge=0)
    status: CoverageStatus
    document_version_id: UUID | None
    note: str | None


# --- Writer (AI) and report snapshot (code) ------------------------------------


class ReportSentenceDraft(Contract):
    text: str
    claim_labels: list[Label]
    structural: bool

    @model_validator(mode="after")
    def _cited(self) -> ReportSentenceDraft:
        if not self.structural and not self.claim_labels:
            raise ValueError("a non-structural sentence must cite at least one verified claim (AG10)")
        return self


class ReportSectionDraft(Contract):
    section: ReportSectionKey
    sentences: list[ReportSentenceDraft]
    no_verified_items: bool


class WriterOutput(Contract):
    sections: list[ReportSectionDraft]


class ReportSentence(Contract):
    text: str
    finding_ids: list[UUID]
    structural: bool


class ReportSection(Contract):
    section: ReportSectionKey
    sentences: list[ReportSentence]
    no_verified_items: bool


class ReviewOutcome(Contract):
    review_id: UUID | None
    decision: Literal["accepted", "amended", "rejected", "needs_evidence"] | None
    reviewed_at: datetime | None
    reviewed_by: UUID | None
    review_sequence: int | None = None
    amended_content: str | None
    exclusion_reason: str | None


class FrozenCitation(Contract):
    passage_id: UUID
    document_version_id: UUID
    supporting_quote: str
    support_type: Literal["supports", "contradicts", "context"]


class FrozenFinding(Contract):
    finding_id: UUID
    finding_type: FindingType
    title: str
    content: str
    priority: Rating
    evidence_confidence: Rating
    priority_reason: str | None
    jurisdiction_code: JurisdictionCode | None
    change_type: ChangeType | None
    industry_category: IndustryCategory | None
    is_inference: bool
    evidence_confidence_reason: str | None
    key_date: date | None
    key_date_kind: KeyDateKind | None
    depends_on: list[UUID]
    evidence: list[FrozenCitation]


class FrozenPassage(Contract):
    id: UUID
    document_version_id: UUID
    document_id: UUID
    source_id: UUID
    source_name: str
    jurisdiction_code: str | None
    title: str
    source_url: str
    published_at: date | None
    passage_number: int
    content: str
    imported: bool = False
    content_sha256: str | None = None
    extraction_version: str | None = None
    page_number: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    acquisition_provenance: dict = Field(default_factory=dict)


class EvidenceInput(Contract):
    schema_version: Literal[1] = 1
    workspace_id: UUID
    analysis_run_id: UUID
    analysis_revision_id: UUID
    findings: dict[UUID, FrozenFinding]
    passages: dict[UUID, FrozenPassage]
    corroboration: dict[UUID, dict] | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_corroboration(self, handler):
        payload = handler(self)
        if not self.corroboration:
            payload.pop("corroboration", None)
        return payload


class FrozenExpectedSource(Contract):
    id: UUID
    list_version: int
    jurisdiction_code: str
    category: str
    source_id: UUID
    document_hint: str


class FrozenVerification(Contract):
    check_id: UUID
    method: CheckMethod
    verdict: VerdictLabel
    reason: str
    model: str | None
    prompt_version: str | None
    checked_at: datetime
    input_fingerprint: str
    attempt: int = Field(ge=1)
    agent_step_id: UUID | None


class FrozenEvidenceBundle(EvidenceInput):
    verifications: dict[UUID, FrozenVerification]
    brief: Brief
    expected_sources: dict[UUID, FrozenExpectedSource]
    reviewer_display_name: str
    reviewed_at: datetime


class ReportSnapshot(Contract):
    """Shape of reports.evidence_snapshot: the sentence-to-claim mapping (AG10)."""

    contract_version: str
    analysis_run_id: UUID
    analysis_revision_id: UUID
    sections: list[ReportSection]
    coverage: list[CoverageRow]
    unresolved_finding_ids: list[UUID]
    review_outcomes: dict[UUID, ReviewOutcome] = Field(default_factory=dict)
    evidence_bundle: FrozenEvidenceBundle | None = None


# --- Run trace (code) ----------------------------------------------------------


class StepRecord(Contract):
    """One row of agent_steps."""

    analysis_run_id: UUID
    step_no: int = Field(ge=1)
    role: AgentRole
    jurisdiction_code: JurisdictionCode | None
    gap_round: int = Field(ge=0)
    status: StepStatus
    contract_version: str
    model: str | None
    prompt_version: str | None
    temperature: float | None
    input_refs: dict[str, object]
    output_refs: dict[str, object]
    tokens_in: int | None
    tokens_out: int | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


# --- Labels --------------------------------------------------------------------


class UnknownLabelError(ValueError):
    """A model cited a label it was never given."""


class LabelMap:
    """Hands out short labels for real IDs and resolves them back.

    Create one per model call, label everything the model is shown, then resolve
    whatever it cites. Resolving a label that was not handed out raises
    ``UnknownLabelError``.
    """

    def __init__(self) -> None:
        self._ids: dict[str, UUID] = {}
        self._counters: dict[str, int] = {}

    def add(self, prefix: str, real_id: UUID) -> str:
        if len(prefix) != 1 or not prefix.isupper():
            raise ValueError("label prefix must be one capital letter")
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        label = f"{prefix}{number}"
        self._ids[label] = real_id
        return label

    def resolve(self, label: str, prefix: str) -> UUID:
        if not label.startswith(prefix) or label not in self._ids:
            raise UnknownLabelError(f"label {label!r} was not provided to the model")
        return self._ids[label]

    def resolve_all(self, labels: list[str], prefix: str) -> list[UUID]:
        return [self.resolve(label, prefix) for label in labels]

    def as_dict(self) -> dict[str, UUID]:
        return dict(self._ids)


def check_claim_labels(output: AnalystOutput, passages: LabelMap) -> None:
    """Reject claims citing unknown passages or depending on unknown claims."""
    claim_labels = {claim.claim_label for claim in output.claims}
    if len(claim_labels) != len(output.claims):
        raise ValueError("duplicate claim_label")
    for claim in output.claims:
        for citation in claim.citations:
            passages.resolve(citation.passage_label, "P")
        unknown = set(claim.depends_on) - claim_labels
        if unknown:
            raise UnknownLabelError(f"{claim.claim_label} depends on unknown claims {sorted(unknown)}")
