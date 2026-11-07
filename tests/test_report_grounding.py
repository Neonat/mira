"""The final writer gate must not let a valid citation launder new prose."""
from mira.agents.writer import WRITER_SECTIONS
from test_orchestrator import FakeVerifier, context, make, steps


def test_rejected_inference_cannot_return_as_writer_prose_with_valid_fact_citation():
    def malicious_writer(prompt):
        sections = [{"section": key, "sentences": [], "no_verified_items": True}
                    for key in WRITER_SECTIONS]
        for index in (0, 6):
            sections[index].update(sentences=[{
                "text": "The bank must rebuild onboarding controls by 2027 or face a penalty.",
                "claim_labels": ["C1"], "structural": False}], no_verified_items=False)
        return {"sections": sections}

    orchestrator, store, *_ = make({"writer": [malicious_writer]},
                                  verifier=FakeVerifier({"C4": ["unsupported"]}))
    outcome = orchestrator.run(context())
    body = outcome.snapshot.sections
    assert body[0].sentences[0].text == "C1 content"
    assert body[6].no_verified_items and not body[6].sentences
    assert "2027" not in store.reports[0].html
    assert steps(store)[-1].output_refs["grounded_sentences"] == 2


def test_grounding_keeps_full_condition_and_negation_not_a_supported_substring():
    from mira.agents.writer import ground_sections
    from mira.contracts import ClaimDraft, LabelMap, WriterOutput
    from mira.store import StoredClaim
    from test_orchestrator import claim
    from uuid import uuid4

    fid = uuid4()
    content = "Banks must not apply this measure unless the stated condition is met."
    saved = StoredClaim(fid, ClaimDraft(**claim("C1", "external_fact", "P1", content, content=content)), (), ())
    labels = LabelMap(); labels.add("C", fid)
    output = WriterOutput(sections=[{
        "section": "executive_summary", "no_verified_items": False,
        "sentences": [{"text": "Banks must apply this measure.", "claim_labels": ["C1"], "structural": False}],
    }])
    sections, count = ground_sections(output, labels, [saved])
    assert sections[0].sentences[0].text == content
    assert count == 1


def test_a_generated_audit_action_is_excluded_before_verification():
    from test_orchestrator import analyst_output, finding

    response = analyst_output()
    response["claims"][-1].update(finding_type="audit_question", content="DBS should open an audit review.")
    orchestrator, store, _, verifier = make({"analyst": [response]})

    outcome = orchestrator.run(context())

    assert finding(store, "C4").finding_id in outcome.snapshot.unresolved_finding_ids
    assert all(call[0] != "C4" for call in verifier.calls)
    assert "DBS should open an audit review." not in store.reports[0].html


def test_inference_verifier_rejects_a_recommendation_even_without_new_facts():
    from uuid import uuid4

    from mira.agents.verifier import LlmVerifier
    from mira.contracts import ClaimDraft
    from mira.llm import ScriptedClient
    from mira.store import StoredClaim
    from test_orchestrator import claim

    fact = StoredClaim(uuid4(), ClaimDraft(**claim("C1", "external_fact", "P1", "A notice was issued.")), (), ())
    inference = StoredClaim(uuid4(), ClaimDraft(**claim(
        "C2", "risk_implication", is_inference=True, depends_on=["C1"], content="DBS should open an audit review."
    )), (), (fact.finding_id,))
    verifier = LlmVerifier(ScriptedClient({"verifier": [{
        "introduces_new_fact": False, "new_facts": [], "is_supported_assessment": False,
        "reason": "The statement suggests an audit action.",
    }]}))

    assert verifier.check_inference(inference, [fact], 1).verdict == "unsupported"
