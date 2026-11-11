"""Signed-in prepared evidence console; all writes use authenticated RPCs.

The UI never chooses a latest snapshot or starts acquisition. The server pins the
manifest atomically and enforces workspace membership, source policy and roles.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from secrets import token_hex
from typing import Any
import uuid

import streamlit as st
import streamlit.components.v1 as components

from mira.brief import MVP_TOPICS
from mira.topics import CYBERSECURITY, CYBER_SOURCE_KEY


def _rows(query) -> list[dict[str, Any]]:
    return query.execute().data or []


def submit_request(sb, workspace: str, brief: dict, source_ids: list[str], idempotency_key: str) -> str:
    return sb.rpc("request_prepared_report", {"p_workspace": workspace, "p_brief": brief,
        "p_source_ids": source_ids, "p_idempotency_key": idempotency_key}).execute().data


def cancel_request(sb, request_id: str) -> None:
    sb.rpc("cancel_prepared_report_request", {"p_request": request_id}).execute()


def review_fact(sb, snapshot_id: str, finding_id: str, decision: str, comment: str) -> None:
    if decision not in {"accepted", "rejected", "correction_requested"}:
        raise ValueError("Choose accept, reject or request correction.")
    sb.rpc("review_prepared_fact", {"p_snapshot": snapshot_id, "p_finding": finding_id,
        "p_decision": decision, "p_comment": comment or None}).execute()


def evidence_review_label(state: str | None) -> str:
    return "Human evidence checked" if state == "human_checked" else "Human evidence review pending"


def prepared_sources(sources: list[dict]) -> list[dict]:
    return [s for s in sources if s.get("is_active") is True
            and {"fetch", "store_text"} <= set(s.get("permitted_operations") or [])
            and str(s.get("jurisdiction_code", "")).strip() != "MY"
            and not any(route in str(s.get("source_key", "")).upper() for route in ("MAS", "DFSA"))]


def _time(value) -> str:
    if not value:
        return "Unavailable"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return str(value)


def request_page(sb, workspace_id: str, sources: list[dict]) -> None:
    """Request a new report; the RPC decides which scopes wait or pin."""
    from mira.report import MARKET_NAMES

    sources = prepared_sources(sources)

    pending = st.session_state.get("pending_prepared_request")
    if pending:
        st.subheader("Review report request")
        brief = pending["brief"]
        st.write(f"{brief['topic']} · {', '.join(brief['jurisdictions'])} · {brief['period_start']} to {brief['period_end']}")
        st.caption(f"As of {brief['as_of_date']}")
        names = {str(s["id"]): s["name"] for s in sources}
        st.write("Sources: " + ", ".join(names.get(i, "Unavailable source") for i in pending["source_ids"]))
        st.info("A completed refresh is used. If a selected source is being prepared, this request waits for that refresh.")
        st.caption("The draft will identify any evidence still awaiting human review. Evidence review and final report approval are separate.")
        if st.button("Edit request"):
            st.session_state.pop("pending_prepared_request", None)
            st.rerun()
        if st.button("Queue report", type="primary"):
            try:
                request_id = submit_request(sb, workspace_id, brief, pending["source_ids"], pending["idempotency_key"])
            except Exception:
                st.error("Could not queue this report. Check the selected sources and try again.")
            else:
                st.session_state.selected_prepared_request = request_id
                st.session_state.pop("pending_prepared_request", None)
                st.session_state.console_notice = ("success", "Report queued. Follow its progress in Prepared reports.")
                st.rerun()
        return
    st.caption("Generate a new draft from prepared evidence. Coverage and human-review status are shown with each report.")
    available = sorted({str(s["jurisdiction_code"]).strip() for s in sources if s.get("jurisdiction_code")})
    cyber_sources = [s for s in sources if s.get("source_key") == CYBER_SOURCE_KEY]
    topic = st.selectbox("Topic", MVP_TOPICS if cyber_sources else ("AML/CFT",), key="prepared-topic")
    if topic == CYBERSECURITY:
        markets = ["AE"]
        sources = cyber_sources
        st.caption("Cybersecurity covers UAE federal sources and common threats to financial institutions.")
    else:
        markets = st.multiselect("Jurisdictions", available, default=["HK"] if "HK" in available else available[:1],
                                format_func=lambda code: MARKET_NAMES.get(code, code), key="prepared-markets")
    scoped = {str(s["id"]): s for s in sources if not s.get("jurisdiction_code") or str(s["jurisdiction_code"]).strip() in markets}
    if "AE" in markets:
        st.caption("UAE coverage uses approved federal sources; DFSA is excluded.")
    period = st.selectbox("Period", ["Last 12 months", "Last 24 months", "Custom"], key="prepared-period")
    as_of = st.date_input("As-of date", value=date.today(), max_value=date.today(), key="prepared-as-of")
    start = st.date_input("Period start", value=as_of - timedelta(days=365), key="prepared-start") if period == "Custom" else as_of - timedelta(days=365 if period == "Last 12 months" else 730)
    end = st.date_input("Period end", value=as_of, max_value=as_of, key="prepared-end") if period == "Custom" else as_of
    with st.form("prepared-request"):
        selected = st.multiselect("Approved active sources", list(scoped), default=list(scoped),
                                  format_func=lambda i: scoped[i]["name"])
        submitted = st.form_submit_button("Review request", type="primary", disabled=not scoped)
    if submitted:
        if not topic.strip() or not markets or not selected or start > end or end > as_of:
            st.error("Enter a topic, select jurisdictions and sources, and check the period and as-of date.")
            return
        st.session_state.pending_prepared_request = {"brief": {"topic": topic.strip(), "jurisdictions": markets,
            "period_start": start.isoformat(), "period_end": end.isoformat(), "as_of_date": as_of.isoformat(),
            "plan_requires_approval": False},
            "source_ids": selected, "idempotency_key": str(uuid.uuid4())}
        st.rerun()


def _refresh(key: str) -> None:
    # A manual refresh keeps cancellation and navigation immediately available.
    if st.button("Refresh status", key=key):
        st.rerun()


def reports_page(sb, workspace_id: str, role: str) -> None:
    st.header("Prepared reports")
    requests = _rows(sb.table("prepared_report_requests").select("*").eq("workspace_id", workspace_id)
                     .order("created_at", desc=True).limit(30))
    if not requests:
        st.info("No prepared report requests yet. Start one from Research.")
        return
    by_id = {r["id"]: r for r in requests}
    selected = st.session_state.get("selected_prepared_request")
    ids = list(by_id)
    request_id = st.selectbox("Report request", ids, index=ids.index(selected) if selected in ids else 0,
        format_func=lambda i: f"{_time(by_id[i].get('created_at'))} · {by_id[i].get('brief', {}).get('topic', 'Report')} · {by_id[i]['status']}")
    st.session_state.selected_prepared_request = request_id
    request = by_id[request_id]
    labels = {"queued": "Queued", "waiting": "Waiting for evidence", "waiting_for_evidence": "Waiting for evidence",
              "generating": "Generating", "ready": "Draft ready", "draft_ready": "Draft ready", "evidence_failed": "Evidence refresh failed", "failed": "Failed", "cancelled": "Cancelled"}
    st.subheader(labels.get(request["status"], request["status"].replace("_", " ").title()))
    st.caption(f"Requested {_time(request.get('created_at'))}")
    _timing(request)
    if request["status"] in {"waiting", "waiting_for_evidence"}:
        st.info("Waiting for the scheduled evidence refresh to finish. Machine processing must finish before evidence is available.")
    if request.get("reason"):
        st.error("This request could not proceed: " + str(request["reason"]))
    own_request = request.get("actor_id") == st.session_state.get("user_id")
    _manifest(sb, workspace_id, request_id, can_choose=own_request and role in {"admin", "analyst"})
    if own_request and request["status"] in {"queued", "waiting", "waiting_for_evidence", "evidence_failed", "generating"}:
        if st.button("Cancel report request"):
            try:
                cancel_request(sb, request_id)
            except Exception:
                st.error("Could not cancel this request. Refresh and try again.")
            else:
                st.rerun()
    _refresh("prepared-report-refresh")
    reports = _rows(sb.table("prepared_reports").select("*").eq("workspace_id", workspace_id)
                    .eq("request_id", request_id).order("created_at", desc=True))
    for report in reports:
        _report(sb, workspace_id, report, role, request)


def guest_demo_page(sb, workspace_id: str, guest_url: str) -> None:
    st.header("Guest demo")
    st.write("Open a one-hour link for visitors to generate a draft from a saved report's evidence.")
    try:
        active = sb.rpc("guest_demo_admin_status", {"p_workspace": workspace_id}).execute().data
    except Exception:
        st.error("Could not check guest access. Try refreshing this page.")
        return
    if active:
        st.success(f"Guest access is open until {_time(active['expires_at'])}.")
        shared = st.session_state.get("guest_demo_link") or {}
        if shared.get("id") == active["id"]:
            st.code(shared["url"], language=None, wrap_lines=True)
            st.link_button("Try guest link", shared["url"])
        else:
            st.caption("To get a new shareable link, close this window and open another.")
        if st.button("Close guest access"):
            try:
                sb.rpc("close_guest_demo", {"p_workspace": workspace_id}).execute()
            except Exception:
                st.error("Could not close guest access. Try again.")
            else:
                st.session_state.pop("guest_demo_link", None)
                st.rerun()
        if st.button("Refresh guest status"):
            st.rerun()
        return

    st.info("Guest access is closed.")
    requests = _rows(sb.table("prepared_report_requests").select("id,brief,finished_at")
        .eq("workspace_id", workspace_id).eq("status", "ready")
        .not_.like("idempotency_key", "guest-demo:%").order("finished_at", desc=True).limit(25))
    if not requests:
        st.caption("Generate a prepared report to use as the demo template.")
        return
    request = st.selectbox("Saved report to use", requests, format_func=lambda item:
        f"{item['brief']['topic']} · {', '.join(item['brief']['jurisdictions'])} · {_time(item['finished_at'])}")
    if st.button("Open guest access for one hour", type="primary"):
        link = token_hex(32)
        try:
            reports = _rows(sb.table("prepared_reports").select("id").eq("workspace_id", workspace_id)
                .eq("request_id", request["id"]).limit(1))
            if not reports:
                st.error("The saved report is unavailable.")
                return
            opened = sb.rpc("open_guest_demo", {"p_report": reports[0]["id"], "p_link": link}).execute().data
        except Exception:
            st.error("Could not open guest access. Check that the report's evidence is still available.")
        else:
            st.session_state.guest_demo_link = {"id": opened["id"], "url": f"{guest_url.rstrip('/')}/#{link}"}
            st.rerun()


def _timing(request: dict) -> None:
    def parsed(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    created = parsed(request.get("created_at"))
    generation = parsed(request.get("generation_started_at"))
    finished = parsed(request.get("finished_at"))
    now = datetime.now(UTC)
    def elapsed(start, end):
        if not start or not end:
            return "Not started"
        seconds = max(0, round((end - start).total_seconds()))
        return f"{seconds // 60}m {seconds % 60}s"
    cols = st.columns(3)
    cols[0].metric("Total elapsed", elapsed(created, finished or now))
    cols[1].metric("Evidence wait", elapsed(created, generation or finished or now))
    cols[2].metric("Report generation", elapsed(generation, finished or now))


def _manifest(sb, workspace_id: str, request_id: str, *, can_choose: bool) -> None:
    manifest = _rows(sb.table("prepared_report_request_scopes").select("*").eq("workspace_id", workspace_id).eq("request_id", request_id))
    if not manifest:
        return
    sources = {str(s["id"]): s["name"] for s in _rows(sb.table("sources").select("id,name").eq("workspace_id", workspace_id))}
    scope_ids = [entry["scope_id"] for entry in manifest if str(entry["scope_id"]) not in sources]
    source_by_scope = {}
    if scope_ids:
        scope_rows = _rows(sb.table("preparation_scopes").select("id,source_id")
                           .eq("workspace_id", workspace_id).in_("id", scope_ids))
        source_by_scope = {str(row["id"]): str(row["source_id"]) for row in scope_rows}
    st.subheader("Evidence freshness by source")
    for entry in manifest:
        scope_id = entry["scope_id"]
        source_id = source_by_scope.get(str(scope_id), str(scope_id))
        failed = False
        st.markdown(f"**{sources.get(source_id, 'Source')}**")
        if entry.get("snapshot_id"):
            snapshots = _rows(sb.table("prepared_snapshots").select("*").eq("workspace_id", workspace_id).eq("id", entry["snapshot_id"]))
            if snapshots:
                _snapshot_summary(sb, workspace_id, snapshots[0], source_id=source_id)
        elif entry.get("job_id"):
            jobs = _rows(sb.table("preparation_jobs").select("*").eq("workspace_id", workspace_id).eq("id", entry["job_id"]))
            if jobs:
                job = jobs[0]
                st.write(f"Preparation: {str(job.get('status', 'waiting')).replace('_', ' ')} · {job.get('phase') or 'Queued'}")
                st.caption(f"Queued {_time(job.get('created_at'))} · Finished {_time(job.get('finished_at'))}")
                failed = job.get("status") in {"failed", "cancelled"}
                if failed:
                    st.error("The refresh failed. Partial preparation is unavailable for reports.")
                    if job.get("reason"):
                        st.caption(str(job["reason"]))
                elif job.get("status") == "preparing" and job.get("lease_until"):
                    lease = datetime.fromisoformat(job["lease_until"].replace("Z", "+00:00"))
                    if lease < datetime.now(UTC):
                        st.warning("Evidence preparation was interrupted. This request continues waiting for its original refresh to recover.")
        else:
            st.info("No completed evidence is available for this source.")
        if failed and not entry.get("snapshot_id") and entry.get("previous_snapshot_id"):
            previous = _rows(sb.table("prepared_snapshots").select("*").eq("workspace_id", workspace_id).eq("id", entry["previous_snapshot_id"]))
            st.caption(f"Previous completed snapshot: {entry['previous_snapshot_id']} · Published {_time(previous[0].get('published_at')) if previous else 'Unavailable'}")
            if can_choose and st.button("Use previous completed snapshot", key=f"previous-{request_id}-{scope_id}"):
                try:
                    sb.rpc("choose_prepared_previous", {"p_request": request_id, "p_scope": scope_id}).execute()
                except Exception:
                    st.error("Could not choose the previous snapshot. Refresh and try again.")
                else:
                    st.rerun()


def _snapshot_summary(sb, workspace_id: str, snapshot: dict, *, source_id: str | None = None) -> None:
    payload = snapshot.get("payload") or {}
    brief = payload.get("brief") or {}
    st.caption(f"Snapshot {snapshot['id']} · Prepared through {payload.get('prepared_through', 'Unavailable')} · Published {_time(snapshot.get('published_at'))}")
    st.caption(f"Evidence period {brief.get('period_start', 'Unavailable')} to {brief.get('period_end', 'Unavailable')}")
    facts, reviews, _ = _snapshot_facts(sb, workspace_id, snapshot["id"])
    if source_id:
        passages = (payload.get("evidence_input") or {}).get("passages") or {}
        facts = [row for row in facts if any(
            str((passages.get(item.get("passage_id")) or {}).get("source_id")) == str(source_id)
            for item in (row.get("fact") or {}).get("evidence", []))]
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "correction_requested": 0}
    for fact in facts:
        decision = reviews.get(fact["finding_id"], {}).get("decision", "pending")
        counts[decision if decision in counts else "pending"] += 1
    st.write(f"Evidence decisions: {counts['pending']} pending · {counts['accepted']} accepted · {counts['rejected']} rejected · {counts['correction_requested']} correction requested")
    st.caption("Human checking does not certify complete publication coverage.")
    if payload.get("coverage") or payload.get("analysis_coverage") or payload.get("reasons"):
        with st.expander("Preparation coverage and limitations"):
            for reason in payload.get("reasons", []):
                st.write(reason)
            if payload.get("coverage"):
                st.dataframe(payload["coverage"], hide_index=True, use_container_width=True)
            if payload.get("analysis_coverage"):
                st.json(payload["analysis_coverage"])


def _snapshot_facts(sb, workspace_id: str, snapshot_id: str):
    facts = _rows(sb.table("prepared_facts").select("*").eq("workspace_id", workspace_id).eq("snapshot_id", snapshot_id))
    history = _rows(sb.table("prepared_fact_reviews").select("*").eq("workspace_id", workspace_id)
                    .eq("snapshot_id", snapshot_id).order("sequence"))
    return facts, {r["finding_id"]: r for r in history}, history


def evidence_page(sb, workspace_id: str, role: str) -> None:
    st.header("Prepared evidence")
    snapshots = _rows(sb.table("prepared_snapshots").select("*").eq("workspace_id", workspace_id)
                      .order("published_at", desc=True).limit(50))
    if not snapshots:
        st.info("No completed evidence snapshots yet.")
        return
    by_id = {s["id"]: s for s in snapshots}
    snapshot_id = st.selectbox("Completed snapshot", list(by_id), format_func=lambda i: f"{_time(by_id[i].get('published_at'))} · {i}")
    _snapshot_summary(sb, workspace_id, by_id[snapshot_id])
    facts, latest, history = _snapshot_facts(sb, workspace_id, snapshot_id)
    if role not in {"admin", "reviewer"}:
        st.caption("Reviewers and admins record evidence decisions. You can inspect the evidence below.")
    status = st.selectbox("Evidence decisions", ["All", "pending", "accepted", "rejected", "correction_requested"],
                          format_func=lambda x: x.replace("_", " ").title())
    for row in facts:
        finding_id = row["finding_id"]
        decision = latest.get(finding_id, {}).get("decision", "pending")
        if status != "All" and status != decision:
            continue
        fact = row.get("fact") or {}
        with st.expander(f"{fact.get('title', 'Prepared fact')} · {decision.replace('_', ' ')}"):
            st.write(fact.get("content", ""))
            st.caption(f"Snapshot {snapshot_id} · Finding {finding_id}")
            _fact_evidence(fact, by_id[snapshot_id].get("payload") or {}, finding_id)
            if latest.get(finding_id):
                st.caption("Latest decision: " + decision.replace("_", " ") + " · " + (latest[finding_id].get("comment") or ""))
            with st.expander("Evidence review history"):
                for review in history:
                    if review["finding_id"] == finding_id:
                        st.caption(f"{_time(review.get('created_at'))} · {review['decision'].replace('_', ' ')} · {review.get('comment') or ''}")
            if role in {"admin", "reviewer"}:
                with st.form(f"prepared-fact-{snapshot_id}-{finding_id}"):
                    choice = st.radio("Evidence decision", ["accepted", "rejected", "correction_requested"],
                        format_func=lambda x: {"accepted": "Accept", "rejected": "Reject", "correction_requested": "Request correction"}[x], horizontal=True)
                    comment = st.text_area("Review note")
                    st.caption("A correction request excludes this version from new reports. Corrected evidence requires machine checks and a new decision.")
                    if st.form_submit_button("Save evidence decision"):
                        try:
                            review_fact(sb, snapshot_id, finding_id, choice, comment)
                        except Exception:
                            st.error("Could not save this decision. Refresh and try again.")
                        else:
                            st.rerun()
    _refresh("prepared-evidence-refresh")


def _fact_evidence(fact: dict, payload: dict, finding_id: str) -> None:
    evidence_input = payload.get("evidence_input") or {}
    passages = evidence_input.get("passages") or {}
    for item in fact.get("evidence", []):
        if item.get("supporting_quote"):
            st.markdown("> " + item["supporting_quote"])
        st.caption(f"Document version {item.get('document_version_id', 'Unavailable')} · Passage {item.get('passage_id', 'Unavailable')}")
        passage = passages.get(item.get("passage_id")) or {}
        if passage:
            st.write(passage.get("title", "Publication"))
            st.caption(f"Published {passage.get('published_at', 'Unavailable')} · {passage.get('source_name', 'Source')}")
            st.write(passage.get("source_url", ""))
            st.write(passage.get("content", ""))
    check = (payload.get("verifications") or {}).get(finding_id)
    if check:
        st.caption(f"Machine check: {check.get('verdict', 'Unavailable')} · {check.get('method', 'Unavailable').replace('_', ' ')}")
        if check.get("reason"):
            st.write(check["reason"])
    with st.expander("Exact evidence and check provenance"):
        st.json({"fact": fact, "verification": check, "passages": {
            item["passage_id"]: passages.get(item["passage_id"]) for item in fact.get("evidence", [])},
            "corroboration": (evidence_input.get("corroboration") or {}).get(finding_id)})


def _report(sb, workspace_id: str, report: dict, role: str, request: dict) -> None:
    st.divider()
    label = evidence_review_label(report.get("review_state"))
    if report.get("review_state") == "human_checked":
        st.success(label + ". Final report approval is separate.")
    else:
        st.warning("Draft — " + label.lower() + ". This label records the evidence state when this report was generated.")
    capture = report.get("capture") or {}
    captured_reviews = []
    for binding in capture.get("prepared_bindings", []):
        finding_id = binding["finding_id"]
        fact = (capture.get("selected_findings") or {}).get(finding_id) or {}
        snapshot = (capture.get("snapshots") or {}).get(binding["snapshot_id"]) or {}
        passages = (snapshot.get("evidence_input") or {}).get("passages") or {}
        publications = []
        for citation in fact.get("evidence", []):
            passage = passages.get(citation.get("passage_id")) or {}
            name = " · ".join(str(passage[k]) for k in ("title", "source_name") if passage.get(k))
            if name and name not in publications:
                publications.append(name)
        captured_reviews.append({"Finding": fact.get("title") or "Included finding",
            "Captured evidence decision": {"accepted": "Accepted", "rejected": "Rejected",
                "correction_requested": "Correction requested"}.get(binding.get("decision"), "Pending"),
            "Publications": "; ".join(publications) or "Publication details unavailable",
            "Snapshot": binding["snapshot_id"], "Finding version": finding_id})
    if captured_reviews:
        st.subheader("Evidence decisions at report generation")
        st.caption("These decisions are frozen with this report. Later rejection or correction is shown separately below.")
        st.dataframe(captured_reviews, hide_index=True, use_container_width=True)
    alerts = _rows(sb.table("prepared_report_alerts").select("*").eq("workspace_id", workspace_id).eq("report_id", report["id"]))
    if alerts:
        st.error("Later evidence rejection or correction affects this report. Its original content is preserved; request a corrected revision.")
        with st.expander("Later evidence alerts"):
            for alert in alerts:
                st.write(alert.get("message") or alert.get("reason") or alert.get("decision", "Evidence changed after generation"))
    html = report.get("html")
    if html:
        components.html(html, height=850, scrolling=True)
        st.download_button("Download report HTML", html.encode("utf-8"), file_name=f"mira-prepared-{report['id']}.html", mime="text/html", key=f"download-{report['id']}")
    else:
        st.info("The report artifact is currently unavailable.")
    approvals = _rows(sb.table("prepared_report_approvals").select("*").eq("workspace_id", workspace_id).eq("report_id", report["id"]))
    if approvals:
        st.success("Final report approval recorded.")
    elif role in {"reviewer", "admin"}:
        with st.form(f"approve-prepared-{report['id']}"):
            comment = st.text_input("Final approval note")
            submitted = st.form_submit_button("Approve prepared report", disabled=report.get("review_state") != "human_checked" or bool(alerts))
        if report.get("review_state") != "human_checked":
            st.caption("Complete the evidence check, then request a new report revision before final approval.")
        if submitted:
            try:
                sb.rpc("approve_prepared_report", {"p_report": report["id"], "p_comment": comment or None}).execute()
            except Exception:
                st.error("Could not approve this report. Refresh to check evidence decisions and alerts.")
            else:
                st.rerun()
    if role in {"admin", "analyst"} and st.button("Request new report revision", key=f"revise-{report['id']}"):
        try:
            request_id = submit_request(sb, workspace_id, request["brief"], request["source_ids"], str(uuid.uuid4()))
        except Exception:
            st.error("Could not queue a new revision. Start a new request from Research.")
        else:
            st.session_state.selected_prepared_request = request_id
            st.rerun()
