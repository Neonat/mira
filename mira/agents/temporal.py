"""Date checks on saved evidence; publication dates are not retrieval dates."""
from collections.abc import Sequence

from mira.contracts import Brief, ClaimDraft
from mira.store import PassageRecord

TEMPORAL_RULE = (
    "Use saved publication dates, never import/retrieval dates, to assess recency. "
    "Older publications are background, not new developments. An older rule may support an "
    "effective date or deadline relevant to the brief, but that date must be stated in the evidence. "
    "Unknown publication dates are not proof of recency. Never invent a date to fit the period."
)


def check_claim_period(claim: ClaimDraft, brief: Brief, evidence: Sequence[PassageRecord]) -> None:
    """Reject known date contradictions; semantic date support still needs the verifier.

    Unknown dates remain eligible for verification. Historical sources may explain a
    current or upcoming effective date/deadline, but cannot alone establish a new event.
    """
    from mira.claim_grounding import check_date_grounding
    if claim.is_inference:
        return  # verified dependencies control whether an inference survives
    if any(p.published_at and p.published_at > brief.as_of_date for p in evidence):
        raise ValueError("cited publication is after the brief's as-of date")
    if claim.key_date_kind in ("published", "event") and claim.key_date is not None:
        if not brief.period_start <= claim.key_date <= brief.period_end:
            raise ValueError("publication/event date is outside the research period")
    outside = evidence and all(
        p.published_at is not None and not brief.period_start <= p.published_at <= brief.period_end
        for p in evidence
    )
    dated_obligation = (
        claim.key_date_kind in ("effective", "deadline", "consultation_close")
        and claim.key_date is not None
        and (brief.period_start <= claim.key_date <= brief.period_end
             or (claim.change_type == "upcoming" and claim.key_date > brief.period_end))
    )
    if outside and not dated_obligation:
        raise ValueError("only out-of-period publications cited; use as background, not a current development")
    check_date_grounding(claim, brief, evidence)
