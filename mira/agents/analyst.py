"""Analyst: saved passages → typed claims, facts separate from inference (PRD v2 §5.2, AG07).

The analyst sees passages only, never raw pages. Every factual claim cites at
least one passage with a verbatim quote; an inference names the factual claims
it rests on. ``rewrite`` narrows a claim the verifier found partially supported
(§6.3 step 4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
import time

from mira.agents.common import NO_CONCLUSIONS_RULE, UNTRUSTED_TEXT_RULE, brief_text, quote_passage
from mira.agents.temporal import TEMPORAL_RULE, check_claim_period
from mira.contracts import AnalystOutput, Brief, ClaimCitation, ClaimDraft, LabelMap, check_claim_labels
from mira.llm import LLMClient, LLMError, LLMOutputError, LLMResult, call_checked, request_token_reservation
from mira.store import ClaimEvidence, NewClaim, PassageRecord, StoredClaim

PROMPT_VERSION = "analyst/3"
REWRITE_PROMPT_VERSION = "analyst-rewrite/3"

FINDING_TYPES = """Factual claims (is_inference false, cite at least one passage, depends_on empty):
- obligation_summary: plain-language summary of a new, amended or upcoming rule or guideline; set change_type.
- regulatory_requirement: one specific requirement stated in an instrument.
- deadline: a date something takes effect, must be done, or a consultation closes; set key_date and key_date_kind.
- external_fact: another factual development, such as an enforcement action or a supervisory statement.
- industry_development: an incident, case study, best practice or innovation; set industry_category.
Inferences (is_inference true, depends_on lists the factual claim labels they rest on):
- risk_implication, opportunity, jurisdiction_comparison, trend, applicability_assessment."""

SYSTEM = f"""You are the analyst in Mira, a research assistant for bank internal auditors.
From the quoted passages, write claims about developments in the brief's topic, jurisdictions and period.

{FINDING_TYPES}

Rules:
- Each citation's supporting_quote must be copied word for word from the cited passage, and be short.
- Cover each distinct, relevant development evidenced by the passages. Combine duplicate accounts of the same point.
- Explain what changed, who issued it or was affected, and the operative details and qualifications when supported. Preserve distinctions between proposed rules, guidance, and binding obligations. Distinguish publication, effective, consultation and event dates.
- An inference must explain how its cited facts support the assessment and preserve material uncertainty. Describe peer or regulator developments and their relevance without proposing an audit action.
- Rate the urgency of the external development separately from evidence_confidence (how well the passages support the claim), each with a reason.
- Cite passages only by the labels given (P1, P2). Label claims C1, C2 and so on.
- If the passages show no relevant development, return an empty list. Never fill gaps from memory.
- {TEMPORAL_RULE}
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""

REWRITE_SYSTEM = f"""You are the analyst in Mira, a research assistant for bank internal auditors.
A verifier found that the claim below is only partly supported by the passages it cites.
Rewrite it so that it states only what those passages support. Keep claim_label and finding_type.
Cite only the passages given, copying each supporting_quote word for word.
- {TEMPORAL_RULE}
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""


@dataclass(frozen=True)
class Analysis:
    claims: list[NewClaim]
    llm: LLMResult[AnalystOutput]


def _check_jurisdiction(claim: ClaimDraft, brief: Brief) -> None:
    if claim.jurisdiction_code is not None and claim.jurisdiction_code not in brief.jurisdictions:
        raise ValueError(f"{claim.claim_label} is about {claim.jurisdiction_code}, which is not in the brief")


def _resolve(claim: ClaimDraft, labels: LabelMap) -> NewClaim:
    evidence = tuple(
        ClaimEvidence(labels.resolve(citation.passage_label, "P"), citation.supporting_quote)
        for citation in claim.citations
    )
    return NewClaim(claim, evidence)


def analysis_prompt(brief: Brief, passages: Sequence[PassageRecord]) -> tuple[LabelMap, str]:
    labels = LabelMap()
    quoted = [quote_passage(labels.add("P", passage.id), passage) for passage in passages]
    return labels, f"{brief_text(brief)}\n\nPassages:\n\n" + "\n\n".join(quoted)


def request_reservation(brief: Brief, passages: Sequence[PassageRecord], max_output_tokens: int) -> int:
    # UTF-8 bytes are a conservative token upper bound, including schema/protocol overhead.
    _, user = analysis_prompt(brief, passages)
    from mira.llm import request_token_reservation
    return request_token_reservation(system=SYSTEM,user=user,output_type=AnalystOutput,max_output_tokens=max_output_tokens)


def analyse(client: LLMClient, brief: Brief, passages: Sequence[PassageRecord], *,
            timeout_seconds: float | None = None, max_output_tokens: int | None = None,
            max_total_tokens: int | None = None) -> Analysis:
    by_id = {p.id: p for p in passages}
    labels, user = analysis_prompt(brief, passages)

    def check(output: AnalystOutput) -> None:
        check_claim_labels(output, labels)
        for claim in output.claims:
            _check_jurisdiction(claim, brief)
            check_claim_period(claim, brief, [by_id[labels.resolve(c.passage_label, "P")] for c in claim.citations])

    if timeout_seconds is not None and max_output_tokens is not None:
        bounded = _BoundedAnalysisClient(client,timeout_seconds,max_output_tokens,max_total_tokens)
        result = call_checked(bounded,role="analyst",system=SYSTEM,user=user,output_type=AnalystOutput,
                              prompt_version=PROMPT_VERSION,check=check,attempts=2)
    else:
        result = call_checked(
            client, role="analyst", system=SYSTEM, user=user, output_type=AnalystOutput,
            prompt_version=PROMPT_VERSION, check=check,
        )
    return Analysis([_resolve(claim, labels) for claim in result.output.claims], result)


class _BoundedAnalysisClient:
    """A correction shares the original deadline and remaining analysis allowance."""
    def __init__(self,client,seconds,output_tokens,total_tokens):
        self.client=client
        self.deadline=time.monotonic()+seconds
        self.output_tokens=output_tokens
        self.total_tokens=total_tokens
        self.spent=0

    def structured(self,**kwargs):
        seconds=self.deadline-time.monotonic()
        reservation=request_token_reservation(system=kwargs['system'],user=kwargs['user'],
            output_type=kwargs['output_type'],max_output_tokens=self.output_tokens)
        if seconds<=0 or (self.total_tokens is not None and self.spent+reservation>self.total_tokens):
            raise LLMError('analysis correction has no remaining time/token allowance',request_sent=False)
        method=getattr(self.client,'structured_bounded',None)
        if method is None:raise LLMError('bounded analysis invocation unavailable',request_sent=False)
        try:
            result=method(timeout_seconds=seconds,max_output_tokens=self.output_tokens,**kwargs)
        except LLMError as error:
            self.spent+=error.tokens_in+error.tokens_out
            if (isinstance(error,LLMOutputError) and not (error.tokens_in or error.tokens_out) and not error.reserved_tokens
                    and error.request_sent is not False):
                error.reserved_tokens=reservation
            raise
        self.spent+=result.tokens_in+result.tokens_out
        return result


def rewrite(
    client: LLMClient, brief: Brief, claim: StoredClaim, passages: Sequence[PassageRecord], reason: str
) -> tuple[NewClaim, LLMResult[ClaimDraft]]:
    """Narrow a partially supported factual claim to what its cited passages support."""
    by_id = {p.id: p for p in passages}
    labels = LabelMap()
    label_for = {passage.id: labels.add("P", passage.id) for passage in passages}
    shown = claim.draft.model_copy(update={
        "citations": [
            ClaimCitation(passage_label=label_for[item.passage_id], supporting_quote=item.supporting_quote)
            for item in claim.evidence
        ]
    })
    user = "\n\n".join([
        brief_text(brief),
        f"Verifier's reason: {reason}",
        f"Claim:\n{shown.model_dump_json(indent=2)}",
        "Passages:\n\n" + "\n\n".join(quote_passage(label_for[p.id], p) for p in passages),
    ])

    def check(output: ClaimDraft) -> None:
        if output.claim_label != claim.draft.claim_label or output.finding_type != claim.draft.finding_type:
            raise ValueError("keep the original claim_label and finding_type")
        if output.is_inference:
            raise ValueError("a factual claim cannot become an inference")
        _check_jurisdiction(output, brief)
        for citation in output.citations:
            labels.resolve(citation.passage_label, "P")
        check_claim_period(output, brief, [by_id[labels.resolve(c.passage_label, "P")] for c in output.citations])

    result = call_checked(
        client, role="analyst", system=REWRITE_SYSTEM, user=user, output_type=ClaimDraft,
        prompt_version=REWRITE_PROMPT_VERSION, check=check,
    )
    return _resolve(result.output, labels), result
