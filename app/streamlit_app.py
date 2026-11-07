"""Mira web app: research brief, live run view, report and review (PRD v2 §4; AG01, AG12, AG13).

Everything runs as the signed-in user through Supabase Auth with the anon key, so
row-level security applies to every read and write. The app never holds the
worker database URL or the model API key: it queues runs, and the trusted worker
(``python -m mira worker``) executes them.

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from supabase import Client, create_client

from mira.brief import (
    MVP_JURISDICTIONS,
    RERUNNABLE_STATUSES,
    analysis_run_fields,
    check_brief_scope,
    check_rerunnable,
    project_revision_fields,
)
from mira.budget import RunBudget
from mira.config import load_env, report_file, workspace_slug
from mira.contracts import Brief
from mira.coverage_display import CHECKLIST_DESCRIPTION, coverage_label
from mira.llm import ROLE_MODEL_ENV, estimated_cost
from mira.report import TEMPLATE_VERSION
from mira.review_display import dependency_closure, pending_review_ids, reviewed_display

UI_KEYS = {
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "MIRA_DEV_EMAIL", "MIRA_MAX_FETCHED_DOCUMENTS", "MIRA_MAX_LLM_TOKENS",
    "MIRA_MAX_RUN_MINUTES", "MIRA_MAX_GAP_ROUNDS", "MIRA_WORKSPACE_SLUG", *ROLE_MODEL_ENV.values(),
}
DECISIONS = ("accepted", "amended", "rejected", "needs_evidence")
ACTIVE = ("queued", "running")


def client() -> Client:
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    return st.session_state.sb


def rows(query: Any) -> list[dict[str, Any]]:
    return query.execute().data or []


def jsonable(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value.isoformat() if isinstance(value, date) else value for key, value in values.items()}


# --- Sign-in -------------------------------------------------------------------


def sign_in() -> None:
    st.title("Mira")
    st.caption("Agentic external-driver research for internal audit. Academic prototype; public sources only.")
    with st.form("sign_in"):
        email = st.text_input("Email", value=os.environ.get("MIRA_DEV_EMAIL", ""))
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            try:
                response = client().auth.sign_in_with_password({"email": email, "password": password})
            except Exception as exc:  # noqa: BLE001 - shown to the user
                st.error(f"Sign-in failed: {exc}")
                return
            st.session_state.user_id = response.user.id
            st.session_state.email = response.user.email
            st.rerun()


# --- New brief -----------------------------------------------------------------


def queue_run(workspace_id: str, user_id: str, brief: Brief, budget: RunBudget) -> str:
    sb = client()
    project = sb.table("projects").insert(
        {"workspace_id": workspace_id, "owner_id": user_id, "created_by": user_id}
    ).execute().data[0]
    revision = sb.table("project_revisions").insert(jsonable({
        "workspace_id": workspace_id, "project_id": project["id"], "revision_number": 1, "created_by": user_id,
        **project_revision_fields(brief, "Research brief"),
    })).execute().data[0]
    models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
    run = sb.table("analysis_runs").insert(jsonable({
        "workspace_id": workspace_id, "project_revision_id": revision["id"], "idempotency_key": str(uuid.uuid4()),
        "created_by": user_id, **analysis_run_fields(brief, budget, models),
    })).execute().data[0]
    sb.table("analysis_revisions").insert(
        {"workspace_id": workspace_id, "analysis_run_id": run["id"], "revision_number": 1, "created_by": user_id}
    ).execute()
    return run["id"]


def queue_rerun(workspace_id: str, user_id: str, previous: dict[str, Any]) -> str:
    """Queue a re-run of a finished run on the same Project revision (PRD v2 §4, §6.5).

    Only the run row is inserted, so the brief stays the one the auditor approved. The worker
    checks the previous run again before it starts, so this check is not the only guard.
    """
    check_rerunnable(previous["status"])
    sb = client()
    models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
    run = sb.table("analysis_runs").insert(jsonable({
        "workspace_id": workspace_id, "project_revision_id": previous["project_revision_id"],
        "idempotency_key": str(uuid.uuid4()), "created_by": user_id, "previous_run_id": previous["id"],
        "query_mode": previous["query_mode"], "as_of_date": previous["as_of_date"],
        "resolved_markets": previous["resolved_markets"], "source_limits": previous["source_limits"],
        "model_settings": models, "retrieval_settings": previous["retrieval_settings"],
    })).execute().data[0]
    sb.table("analysis_revisions").insert(
        {"workspace_id": workspace_id, "analysis_run_id": run["id"], "revision_number": 1, "created_by": user_id}
    ).execute()
    return run["id"]


def new_brief_page(workspace_id: str, user_id: str) -> None:
    st.header("New research brief")
    st.caption("Topic and jurisdictions come from controlled lists, so no free text reaches a hosted model (risk G4).")
    defaults = RunBudget.from_env()
    with st.form("brief"):
        topic = st.selectbox("Topic", ["AML/CFT"])
        jurisdictions = st.multiselect("Jurisdictions", MVP_JURISDICTIONS, default=list(MVP_JURISDICTIONS))
        months = st.slider("Period: months before the as-of date", 12, 24, 12)
        as_of = st.date_input("As-of date", value=date.today(), max_value=date.today())
        left, right = st.columns(2)
        documents = left.number_input("Max documents fetched", 5, 200, defaults.max_fetched_documents)
        tokens = right.number_input("Max model tokens", 50_000, 2_000_000, defaults.max_llm_tokens, step=50_000)
        submitted = st.form_submit_button("Queue run", type="primary")
    if not submitted:
        return
    try:
        brief = Brief(topic=topic, jurisdictions=jurisdictions, period_start=as_of - timedelta(days=round(months * 365 / 12)),
                      period_end=as_of, as_of_date=as_of, plan_requires_approval=False)
        check_brief_scope(brief)
    except ValueError as exc:
        st.error(str(exc))
        return
    budget = RunBudget(max_fetched_documents=int(documents), max_llm_tokens=int(tokens),
                       max_run_minutes=defaults.max_run_minutes, max_gap_rounds=defaults.max_gap_rounds)
    try:
        run_id = queue_run(workspace_id, user_id, brief, budget)
    except Exception as exc:  # noqa: BLE001 - RLS refusals are shown, not hidden
        st.error(f"Could not queue the run: {exc}")
        return
    st.session_state.selected_run = run_id
    st.success("Run queued. The worker picks it up: `python -m mira worker`. Open **Runs** to follow it.")


# --- Runs ----------------------------------------------------------------------


def run_label(run: dict[str, Any]) -> str:
    created = run["created_at"][:16].replace("T", " ")
    return f"{created} · {', '.join(m.strip() for m in run['resolved_markets'])} · {run['status']}"


def pick_run(workspace_id: str) -> dict[str, Any] | None:
    runs = rows(client().table("analysis_runs").select("*").eq("workspace_id", workspace_id)
                .order("created_at", desc=True).limit(30))
    if not runs:
        st.info("No runs yet. Start one from **New brief**.")
        return None
    ids = [run["id"] for run in runs]
    selected = st.session_state.get("selected_run")
    index = ids.index(selected) if selected in ids else 0
    run_id = st.selectbox("Run", ids, index=index, format_func=lambda i: run_label(next(r for r in runs if r["id"] == i)))
    st.session_state.selected_run = run_id
    return next(run for run in runs if run["id"] == run_id)


def _plan_approval(sb: Client, run: dict[str, Any], plans: list[dict[str, Any]], role: str) -> None:
    """Let an analyst or admin approve the latest plan of a run that waits for approval (PRD v2 §4).

    The approval is written as the signed-in user, and the policy allows it only once, for an
    unapproved plan. The worker then picks the run up from the queue on its own.
    """
    latest = plans[-1]
    if latest.get("approved_at") is not None:
        st.caption(f"Plan approved on {latest['approved_at'][:16].replace('T', ' ')}.")
        return
    if not run["retrieval_settings"].get("plan_requires_approval") or run["status"] != "queued":
        return
    if role not in ("admin", "analyst"):
        st.caption(f"Your role is {role}; analysts and admins approve plans.")
        return
    st.info("This run waits for plan approval before any source is fetched. Review the plan, then approve it.")
    if st.button("Approve plan", type="primary"):
        sb.table("research_plans").update({
            "approved_by": st.session_state.user_id,
            "approved_at": datetime.now(UTC).isoformat(),
        }).eq("analysis_run_id", run["id"]).eq("version", latest["version"]).execute()
        st.rerun()


def runs_page(workspace_id: str, role: str) -> None:
    st.header("Runs")
    run = pick_run(workspace_id)
    if run is None:
        return
    sb = client()
    steps = rows(sb.table("agent_steps").select("*").eq("analysis_run_id", run["id"]).order("step_no"))
    tokens = sum((s["tokens_in"] or 0) + (s["tokens_out"] or 0) for s in steps)
    cost = sum(estimated_cost(s["model"], s["tokens_in"] or 0, s["tokens_out"] or 0) for s in steps)
    limits = run["source_limits"] or {}
    cols = st.columns(4)
    cols[0].metric("Status", run["status"])
    cols[1].metric("Model tokens", f"{tokens:,}", help=f"Run cap {limits.get('max_llm_tokens', 0):,}")
    cols[2].metric("Estimated cost", f"${cost:.2f}", help="List prices; an estimate, not a bill")
    cols[3].metric("Steps", len(steps))
    if run["failure_summary"]:
        (st.error if run["status"] == "failed" else st.warning)(run["failure_summary"])

    if run["status"] in ACTIVE:
        left, right = st.columns([3, 1])
        left.info("Waiting for or running on the worker (`python -m mira worker`).")
        if right.button("Cancel run"):
            sb.table("analysis_runs").update({"status": "cancelled"}).eq("id", run["id"]).execute()
            st.rerun()

    if run["status"] in RERUNNABLE_STATUSES:
        if st.button("Re-run with the same brief", help="Queues a new run on the same Project revision and "
                                                       "shows what changed since this run."):
            new_run = queue_rerun(workspace_id, st.session_state.user_id, run)
            st.session_state.selected_run = new_run
            st.rerun()
    elif run["status"] in ACTIVE:
        st.caption("Re-run is available once this run has finished.")

    st.subheader("Steps")
    st.dataframe([{
        "#": s["step_no"], "role": s["role"], "jurisdiction": (s["jurisdiction_code"] or "").strip(), "status": s["status"],
        "model": s["model"] or "", "tokens in": s["tokens_in"], "tokens out": s["tokens_out"],
        "seconds": _seconds(s), "detail": s["error"] or _detail(s["output_refs"]),
    } for s in steps], hide_index=True, use_container_width=True)

    plans = rows(sb.table("research_plans").select("plan,version,approved_at").eq("analysis_run_id", run["id"]).order("version"))
    if plans:
        with st.expander("Research plan"):
            for task in plans[-1]["plan"]["plan"]["tasks"]:
                st.markdown(f"**{task['task_label']}** · {task['scout'].replace('_', ' ')} · "
                            f"{task['jurisdiction_code'] or 'all'} · up to {task['max_documents']} documents  \n{task['question']}")
        _plan_approval(sb, run, plans, role)

    coverage = rows(sb.table("coverage_results").select("*").eq("analysis_run_id", run["id"]))
    if coverage:
        expected = {e["id"]: e for e in rows(sb.table("expected_sources").select("id,jurisdiction_code,category,document_hint")
                                             .in_("id", [c["expected_source_id"] for c in coverage]))}
        latest = {}
        for row in sorted(coverage, key=lambda c: c["gap_round"]):
            latest[row["expected_source_id"]] = row
        st.subheader("Source coverage checklist")
        st.caption(CHECKLIST_DESCRIPTION)
        st.dataframe([{
            "jurisdiction": expected.get(source_id, {}).get("jurisdiction_code", "").strip(),
            "checklist item": expected.get(source_id, {}).get("document_hint", source_id),
            "outcome": coverage_label(c["status"], c["note"]), "detail": c["note"] or "",
        } for source_id, c in latest.items()], hide_index=True, use_container_width=True)

    if run["status"] in ACTIVE and st.toggle("Refresh every 5 seconds", value=True):
        time.sleep(5)
        st.rerun()


def _seconds(step: dict[str, Any]) -> int | None:
    if not step["started_at"] or not step["finished_at"]:
        return None
    return round((datetime.fromisoformat(step["finished_at"]) - datetime.fromisoformat(step["started_at"])).total_seconds())


def _detail(refs: dict[str, Any]) -> str:
    keep = {k: v for k, v in (refs or {}).items() if not isinstance(v, list)}
    return ", ".join(f"{k}: {v}" for k, v in keep.items())


# --- Report and review ---------------------------------------------------------


def review_page(workspace_id: str, user_id: str, role: str) -> None:
    st.header("Report and review")
    run = pick_run(workspace_id)
    if run is None:
        return
    sb = client()
    revision = rows(sb.table("analysis_revisions").select("id").eq("analysis_run_id", run["id"])
                    .order("revision_number", desc=True).limit(1))
    reports = rows(sb.table("reports").select("*").eq("analysis_revision_id", revision[0]["id"])
                   .order("report_version", desc=True)) if revision else []
    if not reports:
        st.info("This run has no report yet.")
        return
    report = reports[0]
    signed = report["review_status"] == "reviewed"
    if signed:
        st.success(f"Signed off on {report['reviewed_at'][:16].replace('T', ' ')} (report version {report['report_version']}).")
    else:
        st.warning("Draft. Record a review outcome for each finding before sign-off.")

    snapshot = report["evidence_snapshot"]
    if signed:
        try:
            display = reviewed_display(
                snapshot, workspace_id=workspace_id, run_id=run["id"],
                revision_id=report["analysis_revision_id"],
            )
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"The reviewed evidence bundle is invalid: {exc}")
            return
        findings, evidence, checks = display.findings, display.evidence, display.checks
        if display.legacy_note:
            st.info(display.legacy_note)
        reviews = []
        required = {finding["id"] for finding in findings if not finding.get("excluded_only")}
    else:
        cited = {fid for section in snapshot["sections"] for sentence in section["sentences"] for fid in sentence["finding_ids"]}
        unresolved = set(snapshot["unresolved_finding_ids"])
        findings = rows(sb.table("analysis_findings").select("*").eq("analysis_run_id", run["id"]).order("created_at"))
        ids = [f["id"] for f in findings]
        edges = rows(sb.table("finding_dependencies").select("finding_id,depends_on_finding_id")
                     .eq("analysis_run_id", run["id"]))
        required = dependency_closure(cited, edges)
        checks = rows(sb.table("claim_checks").select("finding_id,method,verdict,reason,attempt")
                      .in_("finding_id", ids).order("checked_at")) if ids else []
        evidence = rows(sb.table("finding_evidence").select("finding_id,supporting_quote").in_("finding_id", ids)) if ids else []
        reviews = rows(sb.table("finding_reviews").select("*").in_("finding_id", ids)
                       .order("reviewed_at").order("review_sequence")) if ids else []
    cited = {fid for section in snapshot["sections"] for sentence in section["sentences"] for fid in sentence["finding_ids"]}
    unresolved = set(snapshot["unresolved_finding_ids"])
    latest_reviews = {review["finding_id"]: review for review in reviews}
    frozen_reviews = snapshot.get("review_outcomes", {})

    report_tab, findings_tab = st.tabs(["Report", f"Findings ({len(cited)} in report, {len(unresolved)} unresolved)"])
    with report_tab:
        path = report_file(report["artifact_storage_path"])
        if path is not None:
            components.html(path.read_text(encoding="utf-8"), height=900, scrolling=True)
        else:
            st.info("The report file is not available here.")
    with findings_tab:
        can_review = role in ("admin", "reviewer")
        for finding in findings:
            if finding["id"] not in required | unresolved | set(frozen_reviews):
                continue
            in_report = finding["id"] in cited
            mine = [r for r in reviews if r["finding_id"] == finding["id"]]
            latest = frozen_reviews.get(finding["id"]) if signed else latest_reviews.get(finding["id"])
            decision = latest["decision"].replace("_", " ") if latest and latest.get("decision") else "awaiting review"
            badge = ("in report" if in_report else "supporting finding" if finding["id"] in required
                     else "historical finding" if finding.get("historical_only")
                     else "excluded finding" if finding.get("excluded_only") else "unresolved, not in report")
            with st.expander(f"{finding['title']} · {badge} · {decision}"):
                if finding.get("excluded_only"):
                    st.caption((latest or {}).get("exclusion_reason") or "Original finding content is not frozen in this report.")
                    continue
                kind = "inference" if finding["is_inference"] else "fact"
                st.markdown(f"*{finding['finding_type'].replace('_', ' ')} ({kind})* · priority **{finding['priority']}** · "
                            f"evidence confidence **{finding['evidence_confidence']}**")
                st.write(latest["amended_content"] if latest and latest.get("amended_content") else finding["content"])
                if latest and latest.get("exclusion_reason"):
                    st.caption(latest["exclusion_reason"])
                for item in (e for e in evidence if e["finding_id"] == finding["id"]):
                    st.markdown(f"> {item['supporting_quote']}")
                for check in (c for c in checks if c["finding_id"] == finding["id"]):
                    st.caption(f"Check {check['attempt']} · {check['method'].replace('_', ' ')}: "
                               f"**{check['verdict'].replace('_', ' ')}** · {check['reason']}")
                for review in ([] if signed else mine):
                    st.caption(f"Review: {review['decision'].replace('_', ' ')} · {review['reviewer_note'] or ''}")
                if finding["id"] in required and can_review and not signed:
                    _review_form(workspace_id, user_id, finding)
        if not can_review:
            st.caption(f"Your role is {role}; reviewers and admins record decisions.")

    if not signed and role in ("admin", "reviewer"):
        pending = pending_review_ids(cited, edges, latest_reviews)
        if pending:
            st.caption(f"{len(pending)} finding(s) still need a review outcome before sign-off.")
        elif st.button("Sign off report", type="primary"):
            try:
                _sign_off(workspace_id, user_id, report, run["id"])
            except Exception as exc:
                st.error(f"Could not sign off the report: {exc}")
            else:
                st.rerun()


def _review_form(workspace_id: str, user_id: str, finding: dict[str, Any]) -> None:
    with st.form(f"review-{finding['id']}"):
        decision = st.radio("Review outcome", DECISIONS, horizontal=True, format_func=lambda d: d.replace("_", " "))
        note = st.text_input("Note")
        amended = st.text_area("Amended text (only for 'amended')", value="")
        if decision == "amended":
            st.caption("After amending a supporting fact, review its dependent inferences again.")
        if st.form_submit_button("Save review"):
            if decision == "amended" and not amended.strip():
                st.error("An amended decision needs the amended text.")
                return
            client().table("finding_reviews").insert({
                "workspace_id": workspace_id, "finding_id": finding["id"], "decision": decision,
                "reviewer_note": note or None, "amended_content": amended.strip() if decision == "amended" else None,
                "reviewed_by": user_id,
            }).execute()
            st.rerun()


def _sign_off(workspace_id: str, user_id: str, report: dict[str, Any], run_id: str) -> None:
    sb = client()
    sb.table("reports").insert({
        "workspace_id": workspace_id, "analysis_revision_id": report["analysis_revision_id"],
        "report_version": report["report_version"] + 1, "format": report["format"], "review_status": "reviewed",
        "template_version": TEMPLATE_VERSION, "evidence_snapshot": report["evidence_snapshot"],
        # The database freezes reviewer outcomes and applies them to the snapshot.
        # The worker renders that reviewed version into its own artifact.
        "artifact_storage_path": None, "generated_by": user_id, "reviewed_by": user_id,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }).execute()
    try:
        sb.table("analysis_runs").update({"status": "reviewed"}).eq("id", run_id).execute()
    except Exception:  # noqa: BLE001 - reviewers may not update runs; the reviewed report row is the record
        pass


# --- Page ----------------------------------------------------------------------


def main() -> None:
    load_env(keys=UI_KEYS)
    st.set_page_config(page_title="Mira", layout="wide")
    if "user_id" not in st.session_state:
        sign_in()
        return
    sb = client()
    workspace = rows(sb.table("workspaces").select("id,name").eq("slug", workspace_slug()))
    if not workspace:
        st.error("You are not a member of the configured workspace.")
        return
    workspace_id = workspace[0]["id"]
    member = rows(sb.table("workspace_members").select("role").eq("workspace_id", workspace_id)
                  .eq("user_id", st.session_state.user_id))
    role = member[0]["role"] if member else "none"
    with st.sidebar:
        st.markdown(f"**Mira** · {st.session_state.email}  \nRole: {role}")
        page = st.radio("Page", ["New brief", "Runs", "Report and review"], label_visibility="collapsed")
        if st.button("Sign out"):
            sb.auth.sign_out()
            st.session_state.clear()
            st.rerun()
        st.caption("Draft reports are not compliance conclusions about the bank.")
    if page == "New brief":
        if role in ("admin", "analyst"):
            new_brief_page(workspace_id, st.session_state.user_id)
        else:
            st.info("Only analysts and admins can start runs.")
    elif page == "Runs":
        runs_page(workspace_id, role)
    else:
        review_page(workspace_id, st.session_state.user_id, role)


if __name__ == "__main__":  # `streamlit run` executes the file as __main__
    main()
