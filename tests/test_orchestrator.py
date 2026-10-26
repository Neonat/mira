"""End-to-end runs with a scripted model, a fake scout and a fake verifier."""

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from mira.budget import RunBudget
from mira.contracts import Brief, FetchAttempt, ScoutDocumentDraft, ScoutReport, ScoutResult, Verdict
from mira.interfaces import CheckOutcome, ScoutOutcome
from mira.llm import ScriptedClient
from mira.orchestrator import Orchestrator, split_documents
from mira.report import ReportContext, render_html
from mira.store import (
    ClaimEvidence,
    ExpectedSourceRecord,
    InMemoryStore,
    PassageRecord,
    RunContext,
    SourceRecord,
    StoredClaim,
)

MAS = SourceRecord(uuid4(), "MAS", "regulator", "https://www.mas.gov.sg", "SG", ("metadata", "fetch", "store_text"))
E_RULE = ExpectedSourceRecord(uuid4(), 1, "SG", "rule", MAS.id, "MAS Notice 626 and amendments")
E_ENFORCEMENT = ExpectedSourceRecord(uuid4(), 1, "SG", "enforcement", MAS.id, "MAS enforcement actions")
VERSION_ID, DOCUMENT_ID = uuid4(), uuid4()


def passage(number, content):
    return PassageRecord(
        uuid4(), VERSION_ID, DOCUMENT_ID, MAS.id, "MAS", "SG", "Notice 626 amendments",
        "https://www.mas.gov.sg/notice-626", date(2026, 3, 1), number, content,
    )


PASSAGES = [
    passage(1, "Banks must screen customers against sanctions lists before onboarding."),
    passage(2, "The amended notice takes effect on 1 July 2026."),
    passage(3, "MAS imposed a penalty of S$1 million on Bank X for AML breaches."),
]

BRIEF = Brief(
    topic="AML/CFT", jurisdictions=["SG"], period_start=date(2025, 10, 1), period_end=date(2026, 9, 30),
    as_of_date=date(2026, 10, 26), plan_requires_approval=False,
)


def context(**budget):
    return RunContext(uuid4(), uuid4(), uuid4(), uuid4(), BRIEF, RunBudget(**budget))


def plan_task(label="T1", scout="regulatory_scout", jurisdiction="SG", expected=("E1", "E2"), sources=("S1",)):
    return {
        "task_label": label, "scout": scout, "jurisdiction_code": jurisdiction, "question": "AML changes at MAS",
        "source_labels": list(sources), "expected_source_labels": list(expected), "max_documents": 10,
    }


def claim(label, finding_type, passage_label=None, quote=None, **overrides):
    fields = dict(
        claim_label=label, finding_type=finding_type, title=f"{label} title", content=f"{label} content",
        jurisdiction_code="SG", change_type=None, industry_category=None, key_date=None, key_date_kind=None,
        is_inference=False, citations=[{"passage_label": passage_label, "supporting_quote": quote}] if passage_label else [],
        depends_on=[], priority="medium", priority_reason=None, evidence_confidence="high",
        evidence_confidence_reason=None,
    )
    fields.update(overrides)
    return fields


def analyst_output(*claims_):
    if not claims_:
        claims_ = (
            claim("C1", "obligation_summary", "P1", "Banks must screen customers", change_type="amended"),
            claim("C2", "deadline", "P2", "takes effect on 1 July 2026", key_date=date(2026, 7, 1), key_date_kind="effective"),
            claim("C3", "external_fact", "P3", "penalty of S$1 million"),
            claim("C4", "risk_implication", is_inference=True, depends_on=["C1", "C3"]),
        )
    return {"claims": list(claims_)}


def writer_output(extra_labels=(), uncited_fact=False):
    """Cites every claim label the writer was shown, plus ``extra_labels``."""

    def respond(prompt):
        labels = re.findall(r"^(C\d+) \[", prompt, flags=re.MULTILINE) + list(extra_labels)
        developments = [{"text": "MAS amended Notice 626.", "claim_labels": labels[:1], "structural": False}]
        if uncited_fact:
            developments.append({"text": "MAS fined Bank Y S$5m.", "claim_labels": [], "structural": True})
        sections = [
            {"section": "executive_summary", "sentences": [{"text": "Summary.", "claim_labels": labels, "structural": False}], "no_verified_items": False},
            {"section": "regulatory_developments", "sentences": developments, "no_verified_items": False},
        ]
        for key in ("deadlines_timeline", "jurisdiction_comparison", "supervisory_trends", "industry_developments", "impact_assessment"):
            sections.append({"section": key, "sentences": [], "no_verified_items": True})
        return {"sections": sections}

    return respond


class FakeScout:
    def __init__(self, labels=None, error=None, on_run=None):
        self.labels = labels or {f"P{i}": p.id for i, p in enumerate(PASSAGES, 1)}
        self.error = error
        self.on_run = on_run
        self.tasks = []

    def run(self, ctx, step_id, task):
        self.tasks.append(task)
        if self.on_run:
            self.on_run()
        if self.error:
            raise self.error
        report = ScoutReport(
            documents=[ScoutDocumentDraft(
                document_label="D1", instrument_type="notice", industry_category=None, title="Notice 626",
                published_date=None, effective_date=None, change_type="amended",
                relevant_passage_labels=list(self.labels), expected_source_labels=[],
            )],
            expected_source_statuses=[], notes=None,
        )
        fetch = FetchAttempt(url="https://www.mas.gov.sg/notice-626", outcome="saved", document_version_id=VERSION_ID, error=None, attempted_at=datetime.now(UTC))
        result = ScoutResult(
            analysis_run_id=ctx.analysis_run_id, agent_step_id=step_id, role=task.role,
            jurisdiction_code=task.jurisdiction_code, report=report, fetch_log=[fetch], labels=self.labels,
        )
        return ScoutOutcome(result, "scripted", "scout/test", 0, 0)


class FakeVerifier:
    """Verdicts by claim label, one per attempt; ``supported`` when not listed."""

    def __init__(self, verdicts=None, tokens=10):
        self.verdicts = verdicts or {}
        self.tokens = tokens
        self.calls = []

    def _outcome(self, claim_, attempt, method):
        self.calls.append((claim_.label, attempt, method))
        verdict = self.verdicts.get(claim_.label, ["supported", "supported"])[attempt - 1]
        check = Verdict(finding_id=claim_.finding_id, attempt=attempt, method=method, verdict=verdict, reason=f"{verdict} by test", model="scripted", prompt_version="verifier/test")
        return CheckOutcome(verdict, (check,), "scripted", "verifier/test", self.tokens, self.tokens)

    def check_fact(self, claim_, passages, attempt):
        assert {p.id for p in passages} == {item.passage_id for item in claim_.evidence}
        return self._outcome(claim_, attempt, "llm")

    def check_inference(self, claim_, facts, attempt):
        return self._outcome(claim_, attempt, "inference_check")


def make(responses=None, scout=None, verifier=None, store=None):
    responses = responses or {}
    responses.setdefault("planner", [{"tasks": [plan_task()], "notes": None}])
    responses.setdefault("analyst", [analyst_output()])
    responses.setdefault("writer", [writer_output()])
    store = store or InMemoryStore(sources=[MAS], expected_sources=[E_RULE, E_ENFORCEMENT], passages=list(PASSAGES))
    client = ScriptedClient(responses)
    verifier = verifier or FakeVerifier()
    orchestrator = Orchestrator(store, client, {"regulatory_scout": scout or FakeScout()}, verifier)
    return orchestrator, store, client, verifier


def steps(store):
    return sorted(store.steps.values(), key=lambda record: record.step_no)


def finding(store, label):
    return next(c for c in store.claims.values() if c.label == label)


def test_full_run_produces_a_verified_draft_report():
    orchestrator, store, client, verifier = make()
    outcome = orchestrator.run(context())

    assert outcome.status == "draft" and outcome.reasons == []
    assert [status for status, _ in store.statuses] == ["running", "draft"]
    records = steps(store)
    assert [r.step_no for r in records] == list(range(1, len(records) + 1))
    assert [r.role for r in records] == ["planner", "regulatory_scout", "analyst"] + ["verifier"] * 4 + ["writer"]
    assert all(r.status == "succeeded" and r.finished_at for r in records)
    assert records[0].model == "scripted" and records[0].tokens_in == 100
    # Facts are checked before the inference that rests on them.
    assert [call[0] for call in verifier.calls] == ["C1", "C2", "C3", "C4"]
    assert verifier.calls[-1][2] == "inference_check"

    snapshot = store.reports[0].snapshot
    verified = {finding(store, label).finding_id for label in ("C1", "C2", "C3", "C4")}
    cited = {fid for section in snapshot.sections for s in section.sentences for fid in s.finding_ids}
    assert cited and cited <= verified
    assert snapshot.unresolved_finding_ids == []
    assert snapshot.sections[-1].section == "coverage_limitations"
    assert store.plans[0]["labels"]["S1"] == str(MAS.id)
    html = store.reports[0].html
    assert "Draft, not reviewed" in html and "https://www.mas.gov.sg/notice-626" in html
    assert 'class="tag">includes inference' in html


def test_invented_passage_label_fails_the_analyst_and_the_run():
    bad = analyst_output(claim("C1", "obligation_summary", "P9", "Banks must"))
    orchestrator, store, *_ = make({"analyst": [bad, bad]})
    outcome = orchestrator.run(context())

    assert outcome.status == "failed" and store.status == "failed"
    analyst_step = next(r for r in steps(store) if r.role == "analyst")
    assert analyst_step.status == "failed" and "P9" in analyst_step.error
    assert analyst_step.tokens_in == 200  # both attempts are charged
    assert store.reports == [] and store.claims == {}


def test_analyst_gets_one_repair_attempt():
    bad = analyst_output(claim("C1", "obligation_summary", "P9", "Banks must"))
    orchestrator, store, client, _ = make({"analyst": [bad, analyst_output()]})
    assert orchestrator.run(context()).status == "draft"
    analyst_prompts = [call.user for call in client.calls if call.role == "analyst"]
    assert "rejected" in analyst_prompts[1] and "P9" in analyst_prompts[1]


def test_plan_must_assign_every_expected_source():
    incomplete = {"tasks": [plan_task(expected=("E1",))], "notes": None}
    orchestrator, store, *_ = make({"planner": [incomplete, incomplete]})
    outcome = orchestrator.run(context())
    assert outcome.status == "failed"
    assert "E2" in store.statuses[-1][1]


def test_writer_cannot_cite_an_unverified_claim():
    verifier = FakeVerifier({"C3": ["unsupported"]})
    orchestrator, store, *_ = make({"writer": [writer_output(["C3"]), writer_output(["C3"])]}, verifier=verifier)
    outcome = orchestrator.run(context())

    assert outcome.status == "partial"
    assert any("writer failed" in reason for reason in outcome.reasons)
    # The inference resting on the dropped fact is dropped without a verifier call.
    assert [call[0] for call in verifier.calls] == ["C1", "C2", "C3"]
    unresolved = {finding(store, "C3").finding_id, finding(store, "C4").finding_id}
    snapshot = store.reports[0].snapshot
    assert set(snapshot.unresolved_finding_ids) == unresolved
    cited = {fid for section in snapshot.sections for s in section.sentences for fid in s.finding_ids}
    assert cited == {finding(store, "C1").finding_id, finding(store, "C2").finding_id}
    assert "rests on a claim that was not verified" in store.reports[0].html


def test_writer_cannot_slip_in_an_uncited_structural_sentence():
    orchestrator, store, *_ = make({"writer": [writer_output(uncited_fact=True), writer_output(uncited_fact=True)]})
    outcome = orchestrator.run(context())
    assert outcome.status == "partial" and any("writer failed" in reason for reason in outcome.reasons)
    assert "Bank Y" not in store.reports[0].html


def test_planner_is_told_the_document_budget():
    orchestrator, store, client, _ = make()
    orchestrator.run(context(max_fetched_documents=25))
    assert "at most 25 pages" in client.calls[0].user


def test_international_sources_go_to_one_jurisdiction_free_task():
    apg = SourceRecord(uuid4(), "APG", "website", "https://apgml.org", None, ("metadata", "fetch"))
    e_apg = ExpectedSourceRecord(uuid4(), 1, "SG", "industry", apg.id, "APG mutual evaluation reports")
    store = InMemoryStore(sources=[MAS, apg], expected_sources=[E_RULE, E_ENFORCEMENT, e_apg], passages=list(PASSAGES))
    per_jurisdiction = {"tasks": [plan_task(), plan_task("T2", "industry_scout", "SG", ("E3",), ("S2",))], "notes": None}
    shared = {"tasks": [plan_task(), plan_task("T2", "industry_scout", None, ("E3",), ("S2",))], "notes": None}
    orchestrator, store, client, _ = make({"planner": [per_jurisdiction, shared]}, store=store)

    assert orchestrator.run(context()).status == "partial"  # no industry scout in this test
    assert "international source S2" in client.calls[1].user
    assert store.plans[0]["plan"]["tasks"][1]["jurisdiction_code"] is None


def test_plan_task_must_be_able_to_read_its_expected_sources():
    sso = SourceRecord(uuid4(), "Singapore Statutes Online", "manual", None, "SG", ("metadata",))
    store = InMemoryStore(sources=[MAS, sso], expected_sources=[E_RULE, E_ENFORCEMENT], passages=list(PASSAGES))
    wrong = {"tasks": [plan_task(sources=("S2",))], "notes": None}
    orchestrator, store, *_ = make({"planner": [wrong, wrong]}, store=store)
    assert orchestrator.run(context()).status == "failed"
    assert "not its source S1" in store.statuses[-1][1]


def test_verifier_input_leaves_out_the_analysts_ratings():
    from mira.interfaces import checkable

    orchestrator, store, *_ = make()
    orchestrator.run(context())
    shown = checkable(finding(store, "C1"))
    assert shown.content == "C1 content" and shown.evidence
    assert not any("priority" in name or "confidence" in name for name in vars(shown))


def test_partially_supported_fact_is_rewritten_and_checked_again():
    narrowed = claim("C1", "obligation_summary", "P1", "Banks must screen customers", content="narrowed", change_type="amended")
    verifier = FakeVerifier({"C1": ["partially_supported", "supported"]})
    orchestrator, store, client, _ = make({"analyst": [analyst_output(), narrowed]}, verifier=verifier)
    assert orchestrator.run(context()).status == "draft"

    c1 = finding(store, "C1")
    assert c1.draft.content == "narrowed"
    assert [(v.attempt, v.verdict) for _, v in store.checks if v.finding_id == c1.finding_id] == [(1, "partially_supported"), (2, "supported")]
    assert [call.output_type.__name__ for call in client.calls if call.role == "analyst"] == ["AnalystOutput", "ClaimDraft"]


def test_budget_exhaustion_still_produces_a_partial_report():
    # planner 150 + analyst 150 + one verifier call 200 = 500 tokens >= 450 before the second check.
    orchestrator, store, *_ = make(verifier=FakeVerifier(tokens=100))
    outcome = orchestrator.run(context(max_llm_tokens=450))

    assert outcome.status == "partial" and "token budget" in outcome.reasons[0]
    assert len(store.checks) == 1
    snapshot = store.reports[0].snapshot
    assert len(snapshot.unresolved_finding_ids) == 3
    assert "not checked" in store.reports[0].html
    assert steps(store)[-1].role == "writer"


def test_failed_scout_is_recorded_and_the_run_is_partial():
    orchestrator, store, *_ = make(scout=FakeScout(error=RuntimeError("MAS returned 503")))
    outcome = orchestrator.run(context())

    assert outcome.status == "partial"
    scout_step = next(r for r in steps(store) if r.role == "regulatory_scout")
    assert scout_step.status == "failed" and "503" in scout_step.error
    assert [r.status for r in steps(store) if r.role in ("analyst", "writer")] == ["skipped", "skipped"]
    assert store.reports[0].snapshot.sections[0].no_verified_items


def test_scout_citing_an_unsaved_passage_fails_its_step():
    labels = {"P1": PASSAGES[0].id, "P2": uuid4()}
    orchestrator, store, *_ = make(scout=FakeScout(labels=labels))
    outcome = orchestrator.run(context())
    assert outcome.status == "partial"
    assert "not saved" in next(r for r in steps(store) if r.role == "regulatory_scout").error


def test_task_without_a_scout_is_skipped():
    plan = {"tasks": [plan_task(), plan_task("T2", "industry_scout", None, expected=())], "notes": None}
    orchestrator, store, *_ = make({"planner": [plan]})
    outcome = orchestrator.run(context())
    assert outcome.status == "partial"
    skipped = [r for r in steps(store) if r.status == "skipped"]
    assert [r.role for r in skipped] == ["industry_scout"]


def test_cancel_stops_the_run_without_a_report():
    store = InMemoryStore(sources=[MAS], expected_sources=[E_RULE, E_ENFORCEMENT], passages=list(PASSAGES))
    scout = FakeScout(on_run=lambda: setattr(store, "cancel", True))
    orchestrator, store, *_ = make(scout=scout, store=store)
    outcome = orchestrator.run(context())
    assert outcome.status == "cancelled" and store.status == "cancelled"
    assert store.reports == []


def test_scouts_get_a_share_of_the_document_budget():
    orchestrator, store, _, _ = make()
    scout = orchestrator.scouts["regulatory_scout"]
    orchestrator.run(context(max_fetched_documents=4, max_llm_tokens=1000))
    assert scout.tasks[0].max_documents == 4
    assert scout.tasks[0].max_llm_tokens == 850  # what the planner left
    assert scout.tasks[0].max_minutes > 0
    assert split_documents([10, 10], 5) == [3, 2]
    assert split_documents([1, 10], 5) == [1, 4]
    assert split_documents([5], 0) == [0]


def test_brief_outside_controlled_lists_or_needing_approval_is_refused():
    orchestrator, *_ = make()
    with pytest.raises(ValueError):
        orchestrator.run(replace(context(), brief=BRIEF.model_copy(update={"jurisdictions": ["US"]})))
    with pytest.raises(NotImplementedError):
        orchestrator.run(replace(context(), brief=BRIEF.model_copy(update={"plan_requires_approval": True})))


def test_report_escapes_source_text_and_refuses_non_http_links():
    hostile = replace(PASSAGES[0], title="<script>alert(1)</script>", source_url="javascript:alert(1)")
    from mira.contracts import ClaimDraft, ReportSection, ReportSentence, ReportSnapshot

    draft = ClaimDraft(**claim("C1", "obligation_summary", "P1", "x", content="<img src=x onerror=alert(1)>"))
    stored = StoredClaim(uuid4(), draft, (ClaimEvidence(hostile.id, "x"),), ())
    snapshot = ReportSnapshot(
        contract_version="1.0", analysis_run_id=uuid4(), analysis_revision_id=uuid4(), coverage=[],
        unresolved_finding_ids=[],
        sections=[ReportSection(section="regulatory_developments", no_verified_items=False, sentences=[
            ReportSentence(text=draft.content, finding_ids=[stored.finding_id], structural=False)
        ])],
    )
    html = render_html(snapshot, ReportContext(
        BRIEF, "draft", {stored.finding_id: stored}, {hostile.id: hostile}, {}, datetime.now(UTC)
    ))
    assert "<script>" not in html and "<img" not in html
    assert 'href="javascript' not in html
