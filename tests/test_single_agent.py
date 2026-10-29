"""The single-agent arm (PRD v2 §11, arm b): its guarantees, checked directly (docs/single_agent_arm_design.md)."""

from datetime import date
from uuid import uuid4

import pytest

from mira.contracts import Brief, ClaimDraft
from mira.single_agent import QuoteOnlyVerifier, code_plan
from mira.store import ClaimEvidence, ExpectedSourceRecord, PassageRecord, SourceRecord, StoredClaim

MAS = SourceRecord(uuid4(), "MAS", "regulator", "https://www.mas.gov.sg", "SG", ("metadata", "fetch", "store_text"))
HKMA = SourceRecord(uuid4(), "HKMA", "regulator", "https://www.hkma.gov.hk", "HK", ("metadata", "fetch", "store_text"))
E_SG = ExpectedSourceRecord(uuid4(), 1, "SG", "rule", MAS.id, "MAS Notice 626")
E_HK = ExpectedSourceRecord(uuid4(), 1, "HK", "guideline", HKMA.id, "HKMA guideline")
BRIEF = Brief(topic="AML/CFT", jurisdictions=["SG", "HK"], period_start=date(2025, 10, 1), period_end=date(2026, 9, 30),
              as_of_date=date(2026, 10, 26), plan_requires_approval=False)
PASSAGE = PassageRecord(uuid4(), uuid4(), uuid4(), MAS.id, "MAS", "SG", "Notice 626", "https://www.mas.gov.sg/n626",
                        date(2026, 3, 1), 1, "Banks must screen customers against sanctions lists before onboarding.")


def fact(quote, passage_id=PASSAGE.id, label="C1"):
    draft = ClaimDraft(
        claim_label=label, finding_type="obligation_summary", title="Screening", content="Banks must screen customers.",
        jurisdiction_code="SG", change_type="new", industry_category=None, key_date=None, key_date_kind=None,
        is_inference=False, citations=[{"passage_label": "P1", "supporting_quote": quote}], depends_on=[],
        priority="high", priority_reason="x", evidence_confidence="high", evidence_confidence_reason="quote",
    )
    return StoredClaim(uuid4(), draft, (ClaimEvidence(passage_id, quote),), ())


def test_the_single_agent_plan_is_one_task_built_without_a_model():
    planned = code_plan(BRIEF, [MAS, HKMA], [E_SG, E_HK], max_documents=12)
    assert len(planned.tasks) == 1
    assert planned.llm.model is None and planned.llm.tokens_in == 0 and planned.llm.tokens_out == 0
    task = planned.tasks[0]
    assert set(task.source_ids) == {MAS.id, HKMA.id}
    assert set(task.expected_source_ids) == {E_SG.id, E_HK.id}  # every expected item is covered


def test_the_single_agent_plan_covers_both_jurisdictions_in_one_task_so_it_has_no_jurisdiction():
    planned = code_plan(BRIEF, [MAS, HKMA], [E_SG, E_HK], max_documents=12)
    assert planned.tasks[0].jurisdiction_code is None


def test_a_single_jurisdiction_brief_gets_that_jurisdiction_on_its_task():
    one = BRIEF.model_copy(update={"jurisdictions": ["SG"]})
    planned = code_plan(one, [MAS], [E_SG], max_documents=5)
    assert planned.tasks[0].jurisdiction_code == "SG"


def test_the_plan_respects_the_document_budget_within_the_schema_limits():
    planned = code_plan(BRIEF, [MAS], [E_SG], max_documents=500)
    assert planned.tasks[0].max_documents == 50  # capped at the plan schema's limit
    assert code_plan(BRIEF, [MAS], [E_SG], max_documents=0).tasks[0].max_documents == 1


def test_the_single_agent_needs_at_least_one_allow_listed_source():
    with pytest.raises(ValueError, match="at least one allow-listed source"):
        code_plan(BRIEF, [], [E_SG], max_documents=5)


def test_the_quote_only_verifier_accepts_a_real_quote_and_refuses_a_fabricated_one():
    verifier = QuoteOnlyVerifier()
    good = verifier.check_fact(fact("Banks must screen customers against sanctions lists"), [PASSAGE], attempt=1)
    bad = verifier.check_fact(fact("MAS requires banks to report every transaction over S$8,000"), [PASSAGE], attempt=1)
    assert good.verdict == "supported" and good.checks[0].method == "quote_match"
    assert bad.verdict == "unsupported"


def test_the_quote_only_verifier_never_calls_a_model():
    # The single agent's verifier has no client at all, so it cannot reach a model by construction.
    verifier = QuoteOnlyVerifier()
    assert not hasattr(verifier, "client")
    outcome = verifier.check_fact(fact("Banks must screen customers"), [PASSAGE], attempt=1)
    assert outcome.model is None and outcome.tokens_in == 0 and outcome.tokens_out == 0


def test_an_overstated_claim_with_a_real_quote_passes_the_quote_check_which_is_the_measured_limit():
    # The single agent cannot catch meaning. A real quote with a false claim is supported here, by design.
    verifier = QuoteOnlyVerifier()
    overstated = fact("Banks must screen customers against sanctions lists")
    assert verifier.check_fact(overstated, [PASSAGE], attempt=1).verdict == "supported"


def test_an_inference_with_no_verified_facts_is_refused():
    verifier = QuoteOnlyVerifier()
    inference = fact("Banks must screen customers", label="C2")
    assert verifier.check_inference(inference, [], attempt=1).verdict == "unsupported"


def test_an_inference_resting_on_verified_facts_is_supported_and_says_its_limit():
    verifier = QuoteOnlyVerifier()
    outcome = verifier.check_inference(fact("Banks must screen customers", label="C2"), [fact("x")], attempt=1)
    assert outcome.verdict == "supported"
    assert "does not check the wording" in outcome.checks[0].reason
