"""Frozen sign-off evidence bindings against isolated local PostgreSQL fixtures.

Every run uses fake web pages and ScriptedClient; no paid/live API is called.
"""

from dataclasses import asdict
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from mira.agents.verifier import LlmVerifier
from mira.budget import RunBudget
from mira.contracts import ReportSnapshot
from mira.db import acting_as
from mira.evidence_snapshot import build_verification_input
from mira.llm import ScriptedClient
from mira.pg_store import PostgresStore, create_run
from mira.render import render_signed_off
from mira.render_job import load_findings, pending_signoffs, render_one
from mira.store import StoredClaim
from test_pipeline_db import (
    DSN, analyst, conn, draft_report_row, grounded_inference, insert_reviewed, review_all_findings,
    run_hk, workspace,
)

pytestmark = pytest.mark.skipif(not DSN, reason="MIRA_TEST_DATABASE_URL not set")


@pytest.fixture()
def research(conn, workspace, tmp_path):
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == "draft", outcome.reasons
    return ctx


def sign_off(conn, ctx, draft=None):
    draft = draft or draft_report_row(conn, ctx.analysis_run_id)
    with acting_as(conn, ctx.user_id):
        conn.execute("set local role authenticated")
        insert_reviewed(conn, draft, ctx.user_id, draft["report_version"] + 1)
    pending, = pending_signoffs(conn, ctx.workspace_id)
    return pending


def add_support_as_analyst(conn, ctx, fact_id):
    """Worker saves a synthetic passage; an app analyst adds its evidence edges."""
    current = conn.execute(
        """select ae.document_version_id, p.content from public.finding_evidence e
           join public.analysis_evidence ae on ae.id=e.analysis_evidence_id
           join public.document_passages p on p.id=ae.passage_id
           where e.finding_id=%s and e.support_type='supports' limit 1""", (fact_id,),
    ).fetchone()
    number = conn.execute(
        "select max(passage_number)+1 as n from public.document_passages where document_version_id=%s",
        (current["document_version_id"],),
    ).fetchone()["n"]
    content = current["content"] + " Additional isolated test support."
    with acting_as(conn, ctx.user_id):
        passage_id = conn.execute(
            """insert into public.document_passages
               (workspace_id, document_version_id, passage_number, content, extraction_version)
               values (%s,%s,%s,%s,'test-late-passage-v1') returning id""",
            (ctx.workspace_id, current["document_version_id"], number, content),
        ).fetchone()["id"]
    analyst_id = uuid4()
    conn.execute("insert into auth.users (id,email) values (%s,%s)",
                 (analyst_id, f"{analyst_id}@test.local"))
    conn.execute(
        "insert into public.workspace_members (workspace_id,user_id,role) values (%s,%s,'analyst')",
        (ctx.workspace_id, analyst_id),
    )
    with acting_as(conn, analyst_id):
        conn.execute("set local role authenticated")
        evidence_id = conn.execute(
            """insert into public.analysis_evidence
               (workspace_id,analysis_run_id,document_version_id,passage_id)
               values (%s,%s,%s,%s) returning id""",
            (ctx.workspace_id, ctx.analysis_run_id, current["document_version_id"], passage_id),
        ).fetchone()["id"]
        conn.execute(
            """insert into public.finding_evidence
               (workspace_id,analysis_run_id,finding_id,analysis_evidence_id,support_type,supporting_quote)
               values (%s,%s,%s,%s,'supports',%s)""",
            (ctx.workspace_id, ctx.analysis_run_id, fact_id, evidence_id, current["content"]),
        )
    return passage_id, analyst_id


def reverify_current_inputs(conn, ctx, tmp_path, corroboration=None):
    """Use actual Python inputs and worker save_checks, never server-forged attestations."""
    finding_ids = [row["id"] for row in conn.execute(
        "select id from public.analysis_findings where analysis_run_id=%s", (ctx.analysis_run_id,),
    )]
    saved = load_findings(conn, ctx.workspace_id, finding_ids)
    claims = {f.finding_id: StoredClaim(f.finding_id, f.draft, f.evidence, f.depends_on) for f in saved}
    store = PostgresStore(conn, reports_dir=tmp_path)
    passages = {p.id: p for p in store.get_passages(
        ctx.workspace_id, list({e.passage_id for f in claims.values() for e in f.evidence}),
    )}
    for claim in sorted(claims.values(), key=lambda item: item.draft.is_inference):
        prior = conn.execute(
            """select attempt, agent_step_id from public.claim_checks where finding_id=%s
               order by attempt desc limit 1""", (claim.finding_id,),
        ).fetchone()
        scripted = (grounded_inference if claim.draft.is_inference else
                    {"verdict": "supported", "reason": "both actual supporting passages agree"})
        verifier = LlmVerifier(ScriptedClient({"verifier": [scripted]}))
        actual_input = build_verification_input(ctx, claim, claims, passages, corroboration)
        extra = {"corroboration":actual_input.corroboration} if actual_input.corroboration else {}
        if claim.draft.is_inference:
            dependency_passages = [passages[pid] for pid in actual_input.passages]
            result = verifier.check_inference(claim, [claims[fid] for fid in claim.depends_on],
                                              prior["attempt"] + 1, passages=dependency_passages, **extra)
        else:
            result = verifier.check_fact(claim, [passages[e.passage_id] for e in claim.evidence], prior["attempt"] + 1, **extra)
        assert result.verdict == "supported"
        store.save_checks(ctx, prior["agent_step_id"], result.checks,
                          input_snapshot=actual_input.model_dump(mode="json"))


def test_signoff_freezes_complete_metadata_and_verification_provenance(conn, research, tmp_path):
    ctx = research
    fact_id, inference_id = review_all_findings(conn, ctx, ctx.user_id)
    pending = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(pending["evidence_snapshot"])
    bundle = snapshot.evidence_bundle
    assert bundle is not None and bundle.brief == ctx.brief
    assert bundle.workspace_id == ctx.workspace_id
    assert set(bundle.findings) == {fact_id, inference_id}
    assert bundle.findings[inference_id].depends_on == [fact_id]
    assert bundle.reviewer_display_name == f"{ctx.user_id}@test.local"
    assert bundle.reviewed_at == pending["reviewed_at"]
    records = PostgresStore(conn, reports_dir=tmp_path).get_passages(ctx.workspace_id, list(bundle.passages))
    assert records
    for passage in records:
        assert bundle.passages[passage.id].model_dump() == asdict(passage)
        assert passage.content_sha256 and passage.extraction_version
    for finding_id, finding in bundle.findings.items():
        for citation in finding.evidence:
            assert citation.document_version_id == bundle.passages[citation.passage_id].document_version_id
        frozen_check = bundle.verifications[finding_id]
        check = conn.execute("select * from public.claim_checks where id=%s", (frozen_check.check_id,)).fetchone()
        assert frozen_check.method == ("inference_check" if finding.is_inference else "llm")
        assert frozen_check.verdict == "supported" and frozen_check.model == check["model"]
        assert frozen_check.input_fingerprint == check["input_fingerprint"]
        assert check["input_snapshot"]["workspace_id"] == str(ctx.workspace_id)
        assert snapshot.review_outcomes[finding_id].decision == "accepted"
    assert set(bundle.expected_sources) == {row.expected_source_id for row in snapshot.coverage}


def test_signoff_overwrites_caller_forged_bundle_with_server_capture(conn, research):
    ctx = research
    review_all_findings(conn, ctx, ctx.user_id)
    draft = draft_report_row(conn, ctx.analysis_run_id)
    draft["evidence_snapshot"]["evidence_bundle"] = {"workspace_id": str(uuid4()), "forged": True}
    pending = sign_off(conn, ctx, draft)
    bundle = pending["evidence_snapshot"]["evidence_bundle"]
    assert "forged" not in bundle and bundle["workspace_id"] == str(ctx.workspace_id)
    assert bundle["passages"] and bundle["verifications"]


@pytest.mark.parametrize("field", ["analysis_run_id", "analysis_revision_id"])
def test_foreign_snapshot_run_or_revision_is_rejected(conn, research, field):
    ctx = research
    review_all_findings(conn, ctx, ctx.user_id)
    other = create_run(conn, ctx.workspace_id, ctx.user_id, ctx.brief, RunBudget(), {})
    draft = draft_report_row(conn, ctx.analysis_run_id)
    draft["evidence_snapshot"][field] = str(getattr(other, field))
    with pytest.raises(psycopg.errors.CheckViolation, match="identity"):
        sign_off(conn, ctx, draft)
    assert not pending_signoffs(conn, ctx.workspace_id)


def test_post_verification_support_addition_requires_new_verification(conn, research):
    ctx = research
    fact_id = conn.execute(
        "select id from public.analysis_findings where analysis_run_id=%s and not is_inference",
        (ctx.analysis_run_id,),
    ).fetchone()["id"]
    add_support_as_analyst(conn, ctx, fact_id)
    review_all_findings(conn, ctx, ctx.user_id)  # Review sees the new edge; checks do not.
    with pytest.raises(psycopg.errors.CheckViolation, match="verification"):
        sign_off(conn, ctx)
    assert not pending_signoffs(conn, ctx.workspace_id)


def test_post_review_support_addition_requires_new_review_even_after_worker_recheck(conn, research, tmp_path):
    ctx = research
    fact_id, _ = review_all_findings(conn, ctx, ctx.user_id)
    add_support_as_analyst(conn, ctx, fact_id)
    reverify_current_inputs(conn, ctx, tmp_path)
    with pytest.raises(psycopg.errors.CheckViolation, match="changed since review"):
        sign_off(conn, ctx)
    review_all_findings(conn, ctx, ctx.user_id)
    assert sign_off(conn, ctx)["evidence_snapshot"]["evidence_bundle"]["passages"]


@pytest.mark.parametrize("binding", ["missing", "unbound"])
def test_legacy_checks_require_fresh_verification(conn, research, binding):
    ctx = research
    review_all_findings(conn, ctx, ctx.user_id)
    # Only this test's synthetic rows are altered, inside a rollback transaction.
    with conn.transaction(force_rollback=True):
        if binding == "missing":
            conn.execute("delete from public.claim_checks where analysis_run_id=%s", (ctx.analysis_run_id,))
        else:
            conn.execute("update public.claim_checks set input_snapshot=null, input_fingerprint=null where analysis_run_id=%s",
                         (ctx.analysis_run_id,))
        with pytest.raises(psycopg.errors.CheckViolation, match="verification is unbound"):
            with conn.transaction():
                sign_off(conn, ctx)


def test_app_analyst_cannot_forge_verification_bindings(conn, research):
    ctx = research
    fact_id, _ = review_all_findings(conn, ctx, ctx.user_id)
    _, analyst_id = add_support_as_analyst(conn, ctx, fact_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with acting_as(conn, analyst_id):
            conn.execute("set local role authenticated")
            conn.execute(
                """insert into public.claim_checks
                   (workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,input_snapshot)
                   values (%s,%s,%s,2,'llm','supported','forged','forged',%s)""",
                (ctx.workspace_id, ctx.analysis_run_id, fact_id, Jsonb({"forged": True})),
            )


@pytest.mark.parametrize("field", ["evidence_snapshot", "template_version", "reviewed_by", "report_version"])
def test_reviewed_snapshot_and_identity_cannot_be_replaced(conn, research, field):
    ctx = research
    review_all_findings(conn, ctx, ctx.user_id)
    pending = sign_off(conn, ctx)
    replacement = {
        "evidence_snapshot": Jsonb({"tampered": True}), "template_version": "forged-template",
        "reviewed_by": uuid4(), "report_version": pending["report_version"] + 1,
    }[field]
    # Worker-level access is still bound by the immutable reviewed-row trigger.
    with pytest.raises(psycopg.errors.CheckViolation, match="immutable"):
        with acting_as(conn, ctx.user_id):
            conn.execute(f"update public.reports set {field}=%s where id=%s", (replacement, pending["id"]))
    unchanged = conn.execute("select evidence_snapshot from public.reports where id=%s", (pending["id"],)).fetchone()
    assert unchanged["evidence_snapshot"] == pending["evidence_snapshot"]


def test_frozen_rerender_survives_live_citation_source_label_changes_and_unavailable_retrieval(
    conn, research, tmp_path, monkeypatch,
):
    from mira import render_job

    ctx = research
    fact_id, _ = review_all_findings(conn, ctx, ctx.user_id)
    pending = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(pending["evidence_snapshot"])
    original = render_signed_off(snapshot, generated_at=pending["generated_at"])
    add_support_as_analyst(conn, ctx, fact_id)
    with acting_as(conn, ctx.user_id):
        conn.execute("update public.sources set name='Changed live source' where workspace_id=%s", (ctx.workspace_id,))
        conn.execute("update public.expected_sources set document_hint='Changed live label ' || id::text where workspace_id=%s",
                     (ctx.workspace_id,))
        conn.execute("update auth.users set email=%s where id=%s",
                     (f"changed-{ctx.user_id}@test.local", ctx.user_id))
    def unavailable(*args, **kwargs):
        raise AssertionError("reviewed rendering must not retrieve mutable evidence or labels")
    monkeypatch.setattr(PostgresStore, "get_passages", unavailable)
    monkeypatch.setattr(render_job, "load_findings", unavailable)
    monkeypatch.setattr(render_job, "reviewer_name", unavailable)
    assert render_one(conn, ctx.workspace_id, pending, tmp_path / "reviewed") == pending["id"]
    path = conn.execute("select artifact_storage_path from public.reports where id=%s", (pending["id"],)).fetchone()
    rendered = (tmp_path / "reviewed" / path["artifact_storage_path"]).read_text()
    assert rendered == original
    assert "Changed live source" not in rendered and "Changed live label" not in rendered
    assert f"{ctx.user_id}@test.local" in rendered


@pytest.mark.parametrize("distinct_quotes", [True, False], ids=["distinct-quotes", "identical-duplicate"])
def test_same_passage_quotes_survive_verified_signoff(conn, workspace, tmp_path, distinct_quotes):
    expected_quotes = []

    def analyst_with_two_quotes(prompt):
        response = analyst(prompt)
        fact = response["claims"][0]
        original = fact["citations"][0]
        quote = original["supporting_quote"]
        quotes = [quote[:30], quote[30:]] if distinct_quotes else [quote, quote]
        expected_quotes.extend(sorted(set(quotes)))
        fact["citations"] = [dict(original, supporting_quote=text) for text in quotes]
        return response

    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst_with_two_quotes)
    assert outcome.status == "draft", outcome.reasons
    fact_id, _ = review_all_findings(conn, ctx, ctx.user_id)
    stored = conn.execute(
        """select e.supporting_quote, ae.passage_id from public.finding_evidence e
           join public.analysis_evidence ae on ae.id=e.analysis_evidence_id
           where e.finding_id=%s and e.support_type='supports' order by e.supporting_quote""", (fact_id,),
    ).fetchall()
    assert [row["supporting_quote"] for row in stored] == expected_quotes
    assert len({row["passage_id"] for row in stored}) == 1
    pending = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(pending["evidence_snapshot"])
    frozen = snapshot.evidence_bundle.findings[fact_id].evidence
    assert [citation.supporting_quote for citation in frozen] == expected_quotes
    assert len(frozen) == (2 if distinct_quotes else 1)
    assert render_one(conn, ctx.workspace_id, pending, tmp_path / "reviewed") == pending["id"]
    path = conn.execute("select artifact_storage_path from public.reports where id=%s", (pending["id"],)).fetchone()
    html = (tmp_path / "reviewed" / path["artifact_storage_path"]).read_text()
    assert 'class="watermark"' not in html and "Reviewed by" in html


def test_future_dated_check_cannot_be_frozen_as_signoff_verification(conn, research, tmp_path):
    ctx = research
    fact_id, _ = review_all_findings(conn, ctx, ctx.user_id)
    original = conn.execute(
        """select id from public.claim_checks where finding_id=%s and method='llm'
           order by checked_at desc, attempt desc limit 1""", (fact_id,),
    ).fetchone()["id"]
    with acting_as(conn, ctx.user_id):
        future_id = conn.execute(
            """insert into public.claim_checks
               (workspace_id,analysis_run_id,finding_id,attempt,method,verdict,reason,model,
                prompt_version,agent_step_id,checked_at,input_snapshot,input_fingerprint)
               select workspace_id,analysis_run_id,finding_id,attempt+1,method,verdict,reason,model,
                      prompt_version,agent_step_id,clock_timestamp()+interval '1 day',input_snapshot,input_fingerprint
               from public.claim_checks where id=%s returning id""", (original,),
        ).fetchone()["id"]
    pending = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(pending["evidence_snapshot"])
    selected = snapshot.evidence_bundle.verifications[fact_id]
    assert selected.check_id != future_id
    assert selected.check_id == original
    assert selected.checked_at <= pending["reviewed_at"]
    assert render_one(conn, ctx.workspace_id, pending, tmp_path / "reviewed") == pending["id"]


def test_long_supporting_quote_persists_and_identical_candidate_deduplicates(conn, research):
    import random
    import string

    ctx = research
    quote = "".join(random.Random(20261107).choices(string.ascii_letters + string.digits, k=12000))
    existing = conn.execute(
        """select e.finding_id,e.analysis_evidence_id from public.finding_evidence e
           where e.analysis_run_id=%s and e.support_type='supports' limit 1""", (ctx.analysis_run_id,),
    ).fetchone()
    sql = """insert into public.finding_evidence
             (workspace_id,analysis_run_id,finding_id,analysis_evidence_id,support_type,supporting_quote)
             values (%s,%s,%s,%s,'supports',%s) on conflict do nothing returning id"""
    params = (ctx.workspace_id, ctx.analysis_run_id, existing["finding_id"], existing["analysis_evidence_id"], quote)
    with acting_as(conn, ctx.user_id):
        conn.execute("set local role authenticated")
        first = conn.execute(sql, params).fetchone()
        assert first is not None
        assert conn.execute(sql, params).fetchone() is None
    saved = conn.execute(
        """select supporting_quote from public.finding_evidence
           where workspace_id=%s and finding_id=%s and analysis_evidence_id=%s and supporting_quote=%s""",
        (ctx.workspace_id, existing["finding_id"], existing["analysis_evidence_id"], quote),
    ).fetchall()
    assert saved == [{"supporting_quote": quote}]
