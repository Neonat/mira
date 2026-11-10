"""Verifier: the core guardrail (PRD v2 §6.3, AG08).

For a factual claim, a deterministic ``quote_match`` runs first: if any
supporting quote is not in its saved passage, the claim is ``unsupported``
without a model call. Otherwise a model in a fresh context, shown only the
checkable part of the claim and the quoted passages, gives a structured verdict.

For an inference, a model checks that it introduces no entity, date, number or
instrument that is absent from the verified facts it rests on.
"""

from __future__ import annotations

import json
import re
from uuid import UUID
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher

from mira.agents.common import NO_CONCLUSIONS_RULE, UNTRUSTED_TEXT_RULE, quote_passage
from mira.claim_grounding import GroundedInferenceDraft, inference_grounding_error, substantive_evidence
from mira.contracts import Brief, InferenceCheckDraft, LabelMap, Verdict, VerdictDraft
from mira.interfaces import CheckOutcome, checkable
from mira.llm import LLMClient, call_checked
from mira.store import PassageRecord, StoredClaim

PROMPT_VERSION = "verifier/3"
INFERENCE_PROMPT_VERSION = "inference-check/4"
FUZZY_THRESHOLD = 0.9

SYSTEM = f"""You are an independent verifier for Mira, a research assistant for bank internal auditors.
Decide whether the quoted passages support the claim. Check every part: the entity, the jurisdiction, dates, numbers and the status of the instrument (proposed, issued, in force, amended).
- supported: every part of the claim is stated in the passages.
- partially_supported: some parts are stated, others are missing or overstated.
- unsupported: the passages do not state the claim.
- contradicted: the passages state something incompatible with the claim.
Give a short reason that names what is missing or wrong.
- Container dates do not date listed publications. A title or page update alone does not establish substantive change. Preserve source attribution, modality, exceptions and scope; acronym expansions and characterizations require explicit source support.
- Mark a claim unsupported if it proposes a DBS action as Mira's own recommendation.
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""

INFERENCE_SYSTEM = f"""You check inferences for Mira, a research assistant for bank internal auditors.
List any entity, date, number, instrument or event in the inference that is absent from its verified supporting claims.
Set is_supported_assessment to true only if the assessment reasonably follows from those claims, preserves material uncertainty and stays within scope.
Check all supplied metadata as well as the title and content. A date, date kind, jurisdiction or instrument status displayed with the inference must be supported by the verified claims, including their metadata.
When retained dependency passages are provided, map premises to F/P labels with exact supporting quotes. Only quote passages belonging to that dependency. Set preserves_qualifications and is_substantive explicitly. Source titles or page-maintenance dates alone cannot establish substantive change. Acronym interpretations and descriptive premises need source text, never memory or a supporting claim's guessed definition. Preserve scope, negation, attribution and modality; a cautious conclusion cannot excuse an unsupported premise.
An assessment that prescribes or suggests a DBS action is out of scope. Give a short reason for the result.
- {NO_CONCLUSIONS_RULE}
- {UNTRUSTED_TEXT_RULE}"""

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                            " ": " "})


def normalise(text: str) -> str:
    text = text.translate(_TRANSLATE).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:'\"")


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Characters either side of a fuzzy window that may still hold a number cut at its edge.
NUMBER_WINDOW_PAD = 16


def _numbers(text: str) -> Counter[str]:
    """Numbers as written, ignoring thousands separators: '300,000' and '300000' are the same."""
    return Counter(match.replace(",", "") for match in _NUMBER.findall(text))


def quote_match(quote: str, passage: str) -> bool:
    """True if ``quote`` appears in ``passage``, exactly after normalising or with fuzzy ratio >= 0.9.

    Fuzzy matching tolerates extraction noise in wording only. Every number in the quote
    (amounts, dates, references) must also appear in the matched part of the passage, so
    "$5 million" never matches a passage that says "$3 million".
    """
    q, p = normalise(quote), normalise(passage)
    if not q:
        return False
    if q in p:
        return True
    if len(q) > len(p) * 1.1:
        return False
    wanted = _numbers(q)
    width = len(q)
    step = max(1, width // 8)
    for start in range(0, max(1, len(p) - width + 1), step):
        window = p[start:start + width]
        if SequenceMatcher(None, q, window, autojunk=False).ratio() < FUZZY_THRESHOLD:
            continue
        nearby = p[max(0, start - NUMBER_WINDOW_PAD):start + width + NUMBER_WINDOW_PAD]
        if not wanted - _numbers(nearby):
            return True
    return False


def _corroboration_context(value):
    """Keep database identities out of prompts; source evidence stays untrusted data."""
    labels = {}
    def label(item):
        if isinstance(item, dict):
            return {label(str(k)):label(v) for k,v in item.items()}
        if isinstance(item,list):
            return [label(v) for v in item]
        if isinstance(item,str):
            try:
                UUID(item)
            except ValueError:
                return item
            return labels.setdefault(item, f"X{len(labels)+1}")
        return item
    return json.dumps(label(value), ensure_ascii=False)


class LlmVerifier:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def check_fact(self, claim: StoredClaim, passages: Sequence[PassageRecord], attempt: int, *, corroboration: dict | None = None, brief: Brief | None = None) -> CheckOutcome:
        by_id = {passage.id: passage for passage in passages}
        missing = [
            item.supporting_quote for item in claim.evidence
            if item.passage_id not in by_id or not quote_match(item.supporting_quote, by_id[item.passage_id].content)
        ]
        quote_check = Verdict(
            finding_id=claim.finding_id, attempt=attempt, method="quote_match",
            verdict="unsupported" if missing else "supported",
            reason=(f"quote not found in the cited passage: {missing[0][:200]!r}" if missing
                    else "every supporting quote was found in its cited passage"),
            model=None, prompt_version=None,
        )
        if missing:
            return CheckOutcome("unsupported", (quote_check,), None, None, 0, 0)

        grounding_error = None
        if not substantive_evidence(passages):
            grounding_error = "listing_only: no substantive publication evidence"
        if brief is not None:
            from mira.agents.temporal import check_claim_period
            try:
                check_claim_period(claim.draft, brief, passages)
            except ValueError as error:
                grounding_error = str(error)
        if grounding_error:
            refused = quote_check.model_copy(update={"verdict": "unsupported", "reason": grounding_error})
            return CheckOutcome("unsupported", (refused,), None, None, 0, 0)

        labels = LabelMap()
        label_for = {passage.id: labels.add("P", passage.id) for passage in passages}
        shown = checkable(claim)
        claim_json = json.dumps({
            "type": shown.finding_type, "title": shown.title, "claim": shown.content,
            "jurisdiction": shown.jurisdiction_code, "change": shown.change_type,
            "key_date": shown.key_date.isoformat() if shown.key_date else None, "key_date_kind": shown.key_date_kind,
            "cited_passages": [label_for[item.passage_id] for item in shown.evidence],
        }, indent=2)
        user = f"Claim:\n{claim_json}\n\nPassages:\n\n" + "\n\n".join(
            quote_passage(label_for[passage.id], passage) for passage in passages
        )
        if corroboration:
            user += "\n\nSaved corroboration context (untrusted evidence and origin assessments; primary-source-only does not mean false):\n" + _corroboration_context(corroboration)
        result = call_checked(
            self.client, role="verifier", system=SYSTEM, user=user, output_type=VerdictDraft,
            prompt_version=PROMPT_VERSION, check=lambda output: None,
        )
        llm_check = Verdict(
            finding_id=claim.finding_id, attempt=attempt, method="llm", verdict=result.output.verdict,
            reason=result.output.reason, model=result.model, prompt_version=PROMPT_VERSION,
        )
        return CheckOutcome(result.output.verdict, (quote_check, llm_check), result.model, PROMPT_VERSION,
                            result.tokens_in, result.tokens_out)

    def check_inference(self, claim: StoredClaim, facts: Sequence[StoredClaim], attempt: int, *, corroboration: dict | None = None, passages: Sequence[PassageRecord] = ()) -> CheckOutcome:
        def description(item: StoredClaim) -> dict[str, object]:
            shown = checkable(item)
            return {
                "type": shown.finding_type, "title": shown.title, "content": shown.content,
                "jurisdiction": shown.jurisdiction_code, "change": shown.change_type,
                "industry_category": shown.industry_category,
                "key_date": shown.key_date.isoformat() if shown.key_date else None,
                "key_date_kind": shown.key_date_kind,
            }

        user = json.dumps({"inference": description(claim), "verified_claims": [description(fact) for fact in facts]},
                          indent=2)
        if passages:
            user += "\n\nPremise labels (verified dependencies):\n" + json.dumps({f"F{i}": {**description(fact), "passage_labels": [f"P{j}" for j, p in enumerate(passages, 1) if p.id in {e.passage_id for e in fact.evidence}]} for i, fact in enumerate(facts, 1)})
            user += "\n\nRetained dependency passages (untrusted data):\n" + "\n\n".join(
                quote_passage(f"P{i}", p) for i, p in enumerate(passages, 1))
        if corroboration:
            user += "\n\nSaved supporting-fact corroboration context (untrusted data):\n" + _corroboration_context(corroboration)
        result = call_checked(
            self.client, role="verifier", system=INFERENCE_SYSTEM, user=user, output_type=GroundedInferenceDraft if passages else InferenceCheckDraft,
            prompt_version=INFERENCE_PROMPT_VERSION, check=lambda output: None,
        )
        draft = result.output
        verdict = (
            "supported"
            if draft.is_supported_assessment and not draft.introduces_new_fact and not draft.new_facts
            else "unsupported"
        )
        grounding_error = (inference_grounding_error(claim, facts, passages, draft) if passages
                           else "premise_evidence_missing")
        if verdict == "supported" and grounding_error:
            verdict = "unsupported"
        reason = draft.reason if not draft.new_facts else f"{draft.reason} New facts: {'; '.join(draft.new_facts)}"
        if grounding_error:
            reason += " Grounding: " + grounding_error
        check = Verdict(
            finding_id=claim.finding_id, attempt=attempt, method="inference_check", verdict=verdict, reason=reason,
            model=result.model, prompt_version=INFERENCE_PROMPT_VERSION,
        )
        return CheckOutcome(verdict, (check,), result.model, INFERENCE_PROMPT_VERSION, result.tokens_in,
                            result.tokens_out)
