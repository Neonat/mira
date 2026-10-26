from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mira.contracts import (
    AnalystOutput,
    Brief,
    ClaimDraft,
    LabelMap,
    ReportSentenceDraft,
    UnknownLabelError,
    check_claim_labels,
)


def fact(label="C1", passage="P1", **overrides):
    fields = dict(
        claim_label=label,
        finding_type="obligation_summary",
        title="MAS amends Notice 626",
        content="Banks must ...",
        jurisdiction_code="SG",
        change_type="amended",
        industry_category=None,
        key_date=None,
        key_date_kind=None,
        is_inference=False,
        citations=[{"passage_label": passage, "supporting_quote": "Banks must"}],
        depends_on=[],
        priority="medium",
        priority_reason=None,
        evidence_confidence="high",
        evidence_confidence_reason=None,
    )
    fields.update(overrides)
    return ClaimDraft(**fields)


def test_brief_rejects_reversed_period():
    with pytest.raises(ValidationError):
        Brief(
            topic="AML/CFT", jurisdictions=["SG"], period_start=date(2026, 10, 1),
            period_end=date(2025, 10, 1), as_of_date=date(2026, 10, 26), plan_requires_approval=False,
        )


def test_fact_needs_citation():
    with pytest.raises(ValidationError):
        fact(citations=[])


def test_inference_needs_dependency_and_inference_type():
    with pytest.raises(ValidationError):
        fact(finding_type="trend", is_inference=True, citations=[], depends_on=[])
    with pytest.raises(ValidationError):
        fact(finding_type="trend", is_inference=False)
    fact(label="C2", finding_type="trend", is_inference=True, citations=[], depends_on=["C1"])


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        ClaimDraft(**fact().model_dump(), invented_field=1)


def test_invented_passage_label_is_rejected():
    passages = LabelMap()
    passages.add("P", uuid4())
    check_claim_labels(AnalystOutput(claims=[fact(passage="P1")]), passages)
    with pytest.raises(UnknownLabelError):
        check_claim_labels(AnalystOutput(claims=[fact(passage="P7")]), passages)


def test_unknown_dependency_is_rejected():
    passages = LabelMap()
    passages.add("P", uuid4())
    inference = fact(label="C2", finding_type="trend", is_inference=True, citations=[], depends_on=["C9"])
    with pytest.raises(UnknownLabelError):
        check_claim_labels(AnalystOutput(claims=[fact(), inference]), passages)


def test_non_structural_sentence_must_cite():
    with pytest.raises(ValidationError):
        ReportSentenceDraft(text="Regulators are busy.", claim_labels=[], structural=False)
    ReportSentenceDraft(text="Section 3", claim_labels=[], structural=True)


def test_ai_facing_schema_has_every_field_required():
    schema = ClaimDraft.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
