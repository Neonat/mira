"""Review display uses frozen rows and includes indirect review dependencies."""
from copy import deepcopy
from uuid import uuid4

import pytest

from mira.review_display import LEGACY_NOTE, dependency_closure, pending_review_ids, reviewed_display
from test_render import fixture, freeze


def frozen_fixture():
    snapshot, finding, passage = fixture()
    snapshot = freeze(snapshot, [finding], [passage])
    bundle = snapshot.evidence_bundle
    scope = dict(workspace_id=str(bundle.workspace_id), run_id=str(bundle.analysis_run_id),
                 revision_id=str(bundle.analysis_revision_id))
    return snapshot.model_dump(mode="json"), scope


def test_frozen_display_uses_snapshot_content_and_checks():
    raw, scope = frozen_fixture()
    original = deepcopy(raw)
    display = reviewed_display(raw, **scope)
    fid, frozen = next(iter(raw["evidence_bundle"]["findings"].items()))
    # Changed live inputs are deliberately absent from the projection API.
    live = {"id": fid, "content": "Changed live claim", "supporting_quote": "Changed quote"}
    assert display.findings[0]["content"] == frozen["content"] != live["content"]
    assert display.evidence[0]["supporting_quote"] == frozen["evidence"][0]["supporting_quote"]
    assert display.checks[0]["reason"] == raw["evidence_bundle"]["verifications"][fid]["reason"]
    assert raw == original


def test_transitive_supporting_findings_and_cycles():
    edges = [dict(finding_id=a, depends_on_finding_id=b)
             for a, b in [("root", "inference"), ("inference", "fact"), ("fact", "root"), ("other", "unused")]]
    assert dependency_closure({"root"}, edges) == {"root", "inference", "fact"}


def test_legacy_has_no_live_rows_and_actionable_note():
    display = reviewed_display({"evidence_bundle": None}, workspace_id="w", run_id="r", revision_id="v")
    assert display.legacy_note == LEGACY_NOTE
    assert display.findings == display.evidence == display.checks == []


@pytest.mark.parametrize("corruption", ["shape", "missing_passage", "missing_verification", "scope"])
def test_invalid_new_bundle_fails_closed(corruption):
    raw, scope = frozen_fixture()
    bundle = raw["evidence_bundle"]
    if corruption == "shape":
        raw["evidence_bundle"] = {}
    elif corruption == "missing_passage":
        bundle["passages"] = {}
    elif corruption == "missing_verification":
        bundle["verifications"] = {}
    else:
        scope["workspace_id"] = str(uuid4())
    with pytest.raises(ValueError):
        reviewed_display(raw, **scope)


def test_excluded_outcome_has_generic_frozen_entry():
    raw, scope = frozen_fixture()
    outcome = deepcopy(next(iter(raw["review_outcomes"].values())))
    excluded = str(uuid4())
    outcome.update(decision="rejected", exclusion_reason="Excluded by reviewer")
    raw["review_outcomes"][excluded] = outcome
    display = reviewed_display(raw, **scope)
    row = next(row for row in display.findings if row["id"] == excluded)
    assert row == dict(id=excluded, title="Excluded finding", content="", excluded_only=True)



def test_rejected_inference_does_not_require_unused_support_reviews():
    edges = [dict(finding_id="root", depends_on_finding_id="fact")]
    reviews = {"root": {"decision": "rejected"}}
    assert pending_review_ids({"root"}, edges, reviews) == set()
    # Display/forms retain the original closure so users can change decisions.
    assert dependency_closure({"root"}, edges) == {"root", "fact"}


def test_rejected_support_still_requires_direct_root_decision():
    edges = [dict(finding_id="root", depends_on_finding_id="middle"),
             dict(finding_id="middle", depends_on_finding_id="fact")]
    reviews = {"fact": {"decision": "rejected"}}
    assert pending_review_ids({"root"}, edges, reviews) == {"root"}
    reviews["root"] = {"decision": "accepted"}
    assert pending_review_ids({"root"}, edges, reviews) == set()


def test_shared_support_remains_required_by_retained_root():
    edges = [dict(finding_id=root, depends_on_finding_id="shared") for root in ("rejected", "retained")]
    reviews = {"rejected": {"decision": "rejected"}, "retained": {"decision": "accepted"}}
    assert pending_review_ids({"rejected", "retained"}, edges, reviews) == {"shared"}
    reviews["shared"] = {"decision": "accepted"}
    assert pending_review_ids({"rejected", "retained"}, edges, reviews) == set()
