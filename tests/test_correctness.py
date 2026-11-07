"""Regression checks for reviewed evidence and checklist outcomes."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

from mira.agents.verifier import LlmVerifier
from mira.completeness import coverage_rows
from mira.contracts import ClaimDraft, ExpectedSourceStatusDraft, ScoutReport
from mira.interfaces import ScoutTask
from mira.llm import ScriptedClient
from mira.store import StoredClaim
from test_orchestrator import E_RULE, MAS, PASSAGES, ExpectedScout, FakeScout, claim, context


def test_no_change_requires_evidence_linked_to_the_checklist_item():
    task = ScoutTask("T1", "regulatory_scout", "SG", "Check Notice 626", (MAS.id,), (E_RULE.id,), 1)
    result = FakeScout().run(context(), uuid4(), task).result
    result = result.model_copy(update={
        "labels": {**result.labels, "E1": E_RULE.id},
        "report": result.report.model_copy(update={"documents": [], "expected_source_statuses": [
            ExpectedSourceStatusDraft(expected_source_label="E1", status="no_change", note=None),
        ]}),
        "fetch_log": [result.fetch_log[0].model_copy(update={"url": "https://www.mas.gov.sg/unrelated"})],
    })

    row, = coverage_rows([E_RULE], {MAS.id: MAS}, [task], {"T1": result}, {})

    assert row.status == "missing"


def test_matching_manual_import_resolves_a_source_that_disallows_fetching():
    task = ScoutTask("T1", "regulatory_scout", "SG", "Check Notice 626", (MAS.id,), (E_RULE.id,), 1)
    imported = replace(PASSAGES[0], imported=True)
    result = ExpectedScout(found_in=lambda task: True).run(context(), uuid4(), task).result
    result = result.model_copy(update={"fetch_log": []})
    source = replace(MAS, permitted_operations=("metadata", "store_text", "quote"))

    row, = coverage_rows([E_RULE], {MAS.id: source}, [task], {"T1": result}, {},
                         passages={imported.id: imported})

    assert row.status == "found"
    assert row.document_version_id == imported.document_version_id
    assert row.note == "from documents imported by hand"


def test_inference_verification_sees_rendered_dates_and_supporting_metadata():
    fact = StoredClaim(uuid4(), ClaimDraft(**claim(
        "C1", "external_fact", "P1", "A notice was issued.", key_date=date(2026, 3, 1), key_date_kind="published",
    )), (), ())
    inference = StoredClaim(uuid4(), ClaimDraft(**claim(
        "C2", "risk_implication", is_inference=True, depends_on=["C1"],
        content="The notice may signal supervisory attention.", key_date=date(2099, 1, 1), key_date_kind="deadline",
    )), (), (fact.finding_id,))
    client = ScriptedClient({"verifier": [{
        "introduces_new_fact": True, "new_facts": ["2099 deadline"], "is_supported_assessment": False,
        "reason": "The deadline is absent from the supporting facts.",
    }]})

    outcome = LlmVerifier(client).check_inference(inference, [fact], 1)

    assert "2099-01-01" in client.calls[0].user
    assert "2026-03-01" in client.calls[0].user
    assert '"jurisdiction": "SG"' in client.calls[0].user
    assert outcome.verdict == "unsupported"


def test_inspection_references_are_required_in_model_output_and_optional_in_old_records():
    schema = ScoutReport.model_json_schema()["$defs"]["ExpectedSourceStatusDraft"]
    assert set(schema["required"]) == set(schema["properties"])
    saved = ExpectedSourceStatusDraft.model_validate({"expected_source_label": "E1", "status": "missing", "note": None})
    assert saved.inspected_passage_labels == []
