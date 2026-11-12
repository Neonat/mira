from dataclasses import replace
from datetime import date
from uuid import UUID

from eval.hk_verification_game import check_evidence
from mira.contracts import Brief, ClaimCitation, ClaimDraft
from mira.store import ClaimEvidence, PassageRecord, StoredClaim


def test_training_preflight_uses_saved_quote_and_publication_cutoff():
    passage_id = UUID(int=1)
    passage = PassageRecord(
        id=passage_id, document_version_id=UUID(int=2), document_id=UUID(int=3),
        source_id=UUID(int=4), source_name="HKMA", jurisdiction_code="HK",
        title="Training publication", source_url="https://brdr.hkma.gov.hk/example",
        published_at=date(2026, 3, 16), passage_number=1,
        content="The schedule requires senior management approval.",
    )
    quote = "The schedule requires senior management approval."
    draft = ClaimDraft(
        claim_label="F1", finding_type="regulatory_requirement", title="Testing schedule",
        content=quote, jurisdiction_code="HK", change_type=None, industry_category=None,
        key_date=None, key_date_kind=None, is_inference=False,
        citations=[ClaimCitation(passage_label="P1", supporting_quote=quote)], depends_on=[],
        priority="medium", priority_reason=None, evidence_confidence="high", evidence_confidence_reason=None,
    )
    claim = StoredClaim(UUID(int=5), draft, (ClaimEvidence(passage_id, quote),), ())
    brief = Brief(topic="AML/CFT", jurisdictions=["HK"], period_start=date(2026, 1, 1),
                  period_end=date(2026, 3, 15), as_of_date=date(2026, 3, 15), plan_requires_approval=False)

    assert check_evidence(claim, [passage], brief) == (True, "cited publication is after the brief's as-of date")
    assert check_evidence(claim, [replace(passage, published_at=date(2026, 3, 15))], brief) == (True, None)
    assert check_evidence(claim, [replace(passage, content="Unrelated text.")], brief) == (False, None)
