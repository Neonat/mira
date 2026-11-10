"""Mira web app: research brief, live run view, report and review (PRD v2 §4; AG01, AG12, AG13).

Everything runs as the signed-in user through Supabase Auth with the anon key, so
row-level security applies to every read and write. The app never holds the
worker database URL or the model API key: it queues runs, and the trusted worker
(``python -m mira worker``) executes them.

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from mira.research_settings import ResearchSettings

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
from mira.config import load_env, workspace_slug
from mira.contracts import Brief
from mira.coverage_display import CHECKLIST_DESCRIPTION, coverage_label
from mira.llm import ROLE_MODEL_ENV, estimated_cost
from mira.report import TEMPLATE_VERSION
from mira.review_display import dependency_closure, pending_review_ids, reviewed_display

UI_KEYS = {
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "MIRA_DEV_EMAIL", "MIRA_MAX_FETCHED_DOCUMENTS", "MIRA_MAX_LLM_TOKENS",
    "MIRA_MAX_RUN_MINUTES", "MIRA_MAX_GAP_ROUNDS", "MIRA_WORKSPACE_SLUG", *ROLE_MODEL_ENV.values(),
    "MIRA_ORIGINALS_DIR", "MIRA_ORIGINAL_MAX_BYTES", "MIRA_DEMO_MODE",
    "MIRA_ENABLE_EXA_DISCOVERY", "MIRA_ENABLE_LIVE_BROWSER", "MIRA_ENABLE_OFFLINE_BROWSER",
    "MIRA_ENABLE_HYBRID_RETRIEVAL", "MIRA_BROKER_SOCKET", "MIRA_ENABLE_BYOK_RUNS",
}
DECISIONS = ("accepted", "amended", "rejected", "needs_evidence")
ACTIVE = ("queued", "running")


def is_synthetic_demo(slug: str) -> bool:
    return os.environ.get("MIRA_DEMO_MODE") == "1" and slug == "mira-local-demo"


def monetary_summary(settings: dict[str, Any]) -> str:
    usage = settings.get("monetary_usage") or {}
    value = usage.get("known_estimated_usd")
    return f"${value}" if value is not None else "Unavailable"


def monetary_details(settings: dict[str, Any]) -> list[tuple[str, str]]:
    usage = settings.get("monetary_usage") or {}
    fields = (("Allowance", "max_usd"), ("Known estimate", "known_estimated_usd"),
              ("Unknown reserved", "unknown_reserved_usd"), ("Pending", "pending_usd"),
              ("Allowance used", "allowance_used_usd"))
    return [(label, f"${usage[key]}" if usage.get(key) is not None else "Unavailable") for label, key in fields]


def eligible_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in sources if s.get("is_active") is True]


def source_groups(source_ids: list[str], records: list[dict[str, Any]], markets: list[str]) -> dict[str, set[str]]:
    selected = [r for r in records if r.get("is_active") is True and str(r.get("jurisdiction_code", "")).strip() in markets]
    latest = {}
    for record in selected:
        market = str(record["jurisdiction_code"]).strip()
        version = record.get("list_version")
        if version is not None and (market not in latest or version > latest[market]):
            latest[market] = version
    groups = {source_id: set() for source_id in source_ids}
    regulatory = {"circular", "consultation", "enforcement", "guideline", "legislation", "rule"}
    for record in selected:
        market = str(record["jurisdiction_code"]).strip()
        source_id = str(record.get("source_id"))
        category = record.get("category")
        if source_id in groups and record.get("list_version") == latest.get(market):
            if category == "industry":
                groups[source_id].add("Industry")
            elif category in regulatory:
                groups[source_id].add("Regulatory")
    return {source_id: group or {"Other"} for source_id, group in groups.items()}


def clear_key_widgets(prefix: str, providers: set[str]) -> None:
    epoch_key = f"{prefix}_key_epoch"
    epoch = st.session_state.get(epoch_key, 0)
    st.session_state[epoch_key] = epoch + 1


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


def queue_run(workspace_id: str, user_id: str, brief: Brief, budget: RunBudget,
              settings: ResearchSettings | None = None, provider_keys: Mapping[str, str] | None = None) -> str:
    sb = client()
    project = sb.table("projects").insert(
        {"workspace_id": workspace_id, "owner_id": user_id, "created_by": user_id}
    ).execute().data[0]
    revision = sb.table("project_revisions").insert(jsonable({
        "workspace_id": workspace_id, "project_id": project["id"], "revision_number": 1, "created_by": user_id,
        **project_revision_fields(brief, "Research brief"),
    })).execute().data[0]
    models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
    fields = analysis_run_fields(brief, budget, models)
    if settings is not None:
        if settings.credential_handle is not None:
            raise ValueError("A new run cannot reuse a credential handle.")
        fields["retrieval_settings"]["research"] = settings.as_dict()
    run = sb.table("analysis_runs").insert(jsonable({
        "workspace_id": workspace_id, "project_revision_id": revision["id"], "idempotency_key": str(uuid.uuid4()),
        "created_by": user_id, **fields,
    })).execute().data[0]
    handle = None
    broker = None
    token = None
    try:
        sb.table("analysis_revisions").insert(
            {"workspace_id": workspace_id, "analysis_run_id": run["id"], "revision_number": 1, "created_by": user_id}
        ).execute()
        if settings is not None and settings.credential_mode == "byok":
            if not provider_keys:
                raise ValueError("Fresh credentials are required.")
            from mira.credentials import BrokerClient
            token = sb.auth.get_session().access_token
            broker = BrokerClient(os.environ["MIRA_BROKER_SOCKET"])
            handle = broker.put(token, workspace_id, run["id"], dict(provider_keys))
            sb.rpc("bind_run_credentials", {"p_run_id": run["id"], "p_handle": handle}).execute()
    except Exception:
        if handle and broker and token:
            try:
                broker.revoke(token, handle)
            except Exception:
                pass
        try:
            sb.table("analysis_runs").update({"status": "cancelled"}).eq("id", run["id"]).execute()
        except Exception:
            pass
        raise
    return run["id"]


def queue_rerun(workspace_id: str, user_id: str, previous: dict[str, Any],
                settings: ResearchSettings | None = None, provider_keys: Mapping[str, str] | None = None) -> str:
    """Queue a re-run of a finished run on the same Project revision (PRD v2 §4, §6.5).

    Only the run row is inserted, so the brief stays the one the auditor approved. The worker
    checks the previous run again before it starts, so this check is not the only guard.
    """
    check_rerunnable(previous["status"])
    old_research = (previous.get("retrieval_settings") or {}).get("research", {})
    if old_research.get("credential_mode") == "byok" and (settings is None or not provider_keys):
        raise ValueError("Fresh credentials are required.")
    if settings is not None and settings.credential_handle is not None:
        raise ValueError("A new run cannot reuse a credential handle.")
    sb = client()
    models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
    retrieval_settings = dict(previous["retrieval_settings"])
    retrieval_settings.pop("monetary_usage", None)
    if settings is not None:
        retrieval_settings["research"] = settings.as_dict()
    run = sb.table("analysis_runs").insert(jsonable({
        "workspace_id": workspace_id, "project_revision_id": previous["project_revision_id"],
        "idempotency_key": str(uuid.uuid4()), "created_by": user_id, "previous_run_id": previous["id"],
        "query_mode": previous["query_mode"], "as_of_date": previous["as_of_date"],
        "resolved_markets": previous["resolved_markets"], "source_limits": previous["source_limits"],
        "model_settings": models, "retrieval_settings": retrieval_settings,
    })).execute().data[0]
    handle = None
    try:
        sb.table("analysis_revisions").insert(
            {"workspace_id": workspace_id, "analysis_run_id": run["id"], "revision_number": 1, "created_by": user_id}
        ).execute()
        if settings is not None and settings.credential_mode == "byok":
            from mira.credentials import BrokerClient
            token = sb.auth.get_session().access_token
            broker = BrokerClient(os.environ["MIRA_BROKER_SOCKET"])
            handle = broker.put(token, workspace_id, run["id"], dict(provider_keys or {}))
            sb.rpc("bind_run_credentials", {"p_run_id": run["id"], "p_handle": handle}).execute()
    except Exception:
        if handle:
            try:
                broker.revoke(token, handle)
            except Exception:
                pass
        try:
            sb.table("analysis_runs").update({"status": "cancelled"}).eq("id", run["id"]).execute()
        except Exception:
            pass
        raise
    return run["id"]


def _review_research(workspace_id: str, user_id: str, source_by_id: dict[str, dict[str, Any]],
                     models: dict[str, str], defaults: RunBudget) -> None:
    pending = st.session_state.pending_research
    settings = pending["settings"]
    quote_key = (tuple(sorted(models.items())), settings["retrieval"], settings["enable_exa"])
    quote = st.session_state.get("console_quote")
    valid = bool(quote and quote[0] == quote_key and set(settings["source_ids"]) <= set(source_by_id)
                 and os.environ.get("MIRA_ENABLE_BYOK_RUNS") == "1" and os.environ.get("MIRA_BROKER_SOCKET")
                 and (not settings["enable_exa"] or os.environ.get("MIRA_ENABLE_EXA_DISCOVERY") == "1")
                 and (settings["retrieval"] != "hybrid" or os.environ.get("MIRA_ENABLE_HYBRID_RETRIEVAL") == "1")
                 and (not settings["enable_browser"] or any(os.environ.get(k) == "1" for k in
                      ("MIRA_ENABLE_LIVE_BROWSER", "MIRA_ENABLE_OFFLINE_BROWSER"))))
    st.subheader("Review research")
    st.write(f"AML/CFT · {', '.join(pending['jurisdictions'])} · {pending['start']} to {pending['end']} · as of {pending['as_of']}")
    st.write("Sources: " + ", ".join(source_by_id.get(i, {}).get("name", "Unavailable source") for i in settings["source_ids"]))
    st.write(f"Retrieval: {settings['retrieval']} · Exa: {'on' if settings['enable_exa'] else 'off'} · Browser: {'on' if settings['enable_browser'] else 'off'}")
    st.write(f"Limit: {pending['documents']} documents · {pending['minutes']} minutes · {settings['max_analysis_batches']} whole-passage batches · USD {pending['allowance']}")
    st.write(f"Plan approval: {'required' if pending['approval'] else 'not required'}")
    st.write("Pending keys expire after at most 60 minutes. Claimed keys are discarded when the run finishes, fails, pauses or is cancelled.")
    st.markdown("**Estimated charges**")
    st.write("Public prices are estimates, not an invoice; credits, discounts, taxes and infrastructure costs are not included. Actual variable charges depend on usage and current prices at execution.")
    if valid:
        book = quote[1]
        st.write(f"Price sources and checked time: {book.metadata()}")
        for model in sorted(set(models.values())):
            provider, name = model.split(":", 1)
            rate = book.token_rate(provider, name)
            detail = f"{model}: USD {rate.input_per_million} input / {rate.output_per_million} output per million tokens"
            if rate.context_threshold:
                detail += f"; above {rate.context_threshold} tokens: input ×{rate.high_input_multiplier}, output ×{rate.high_output_multiplier}"
            st.write(detail)
        if settings["retrieval"] == "hybrid":
            rate = book.token_rate("openai", "text-embedding-3-small")
            st.write(f"Embedding: USD {rate.input_per_million} per million input tokens; total depends on usage.")
        if settings["enable_exa"]:
            st.write(f"Exa: estimated USD {book.search_cost(1)} per one-result search; total depends on searches and result limits.")
        st.write("Required model workflow: the total is unavailable before usage; unit rates are shown above.")
        st.write("Discretionary discovery and embedding: " +
                 ("usage-based estimates are shown above." if settings["enable_exa"] or settings["retrieval"] == "hybrid" else "not selected."))
        st.write("No fixed total can be determined before usage. All provider charges share the USD allowance.")
    else:
        st.warning("Prices, source permissions or paid launch availability changed. Return to research setup and check again.")
    if st.button("Edit research"):
        st.session_state.pop("pending_research", None)
        st.rerun()
    providers = {v.split(":", 1)[0] for v in models.values() if ":" in v}
    if settings["retrieval"] == "hybrid":
        providers.add("openai")
    if settings["enable_exa"]:
        providers.add("exa")
    with st.form("launch-credentials", clear_on_submit=True):
        keys = {p: st.text_input(f"{p.title()} API key", type="password", key=f"launch-key-{p}-{st.session_state.get('launch_key_epoch', 0)}") for p in sorted(providers)}
        submitted = st.form_submit_button("Queue research", type="primary", disabled=not valid)
    if not submitted:
        return
    try:
        if not providers or any(not key.strip() for key in keys.values()):
            raise ValueError("Missing credentials")
        brief = Brief(topic="AML/CFT", jurisdictions=pending["jurisdictions"], period_start=pending["start"],
                      period_end=pending["end"], as_of_date=pending["as_of"], plan_requires_approval=pending["approval"])
        check_brief_scope(brief)
        budget = RunBudget(max_fetched_documents=pending["documents"], max_llm_tokens=defaults.max_llm_tokens,
                           max_run_minutes=pending["minutes"], max_gap_rounds=defaults.max_gap_rounds,
                           max_cost_usd=pending["allowance"])
        run_id = queue_run(workspace_id, user_id, brief, budget, settings=ResearchSettings.from_dict(settings), provider_keys=keys)
    except Exception:
        st.session_state.console_notice = ("error", "Could not queue the run. Check settings and credentials, then try again.")
    else:
        st.session_state.pop("pending_research", None)
        st.session_state.selected_run = run_id
        st.session_state.console_notice = ("success", "Research queued. Follow progress in Runs.")
    finally:
        keys.clear()
        clear_key_widgets("launch", providers)
    st.rerun()


def new_brief_page(workspace_id: str, user_id: str) -> None:
    from mira.report import MARKET_NAMES
    from mira.pricing import load_price_book

    st.header("Research")
    defaults = RunBudget.from_env()
    sources = eligible_sources(rows(client().table("sources").select(
        "id,name,source_key,source_type,jurisdiction_code,is_active,permitted_operations,connector_config"
    ).eq("workspace_id", workspace_id).eq("is_active", True)))
    source_by_id = {str(source["id"]): source for source in sources}
    models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
    if "pending_research" in st.session_state:
        _review_research(workspace_id, user_id, source_by_id, models, defaults)
        return
    with st.expander("Configured model profile"):
        for role, model in models.items():
            st.write(f"{role.replace('_', ' ').title()}: {model or 'Not configured'}")
    exa = st.checkbox("Exa discovery", disabled=os.environ.get("MIRA_ENABLE_EXA_DISCOVERY") != "1")
    browser = st.checkbox("Permitted browser access", disabled=not any(os.environ.get(k) == "1" for k in
                          ("MIRA_ENABLE_LIVE_BROWSER", "MIRA_ENABLE_OFFLINE_BROWSER")),
                          help="Only sources with an existing browser permission can use this method.")
    retrieval = st.radio("Archive retrieval", ["keyword", "hybrid"], horizontal=True,
                         format_func=lambda v: "Hybrid (experimental)" if v == "hybrid" else "Keyword",
                         disabled=os.environ.get("MIRA_ENABLE_HYBRID_RETRIEVAL") != "1")
    quote_key = (tuple(sorted(models.items())), retrieval, exa)
    if st.button("Check current prices"):
        try:
            book = load_price_book(models, embedding_model="text-embedding-3-small" if retrieval == "hybrid" else None,
                                   exa_enabled=exa)
            for model in models.values():
                provider, name = model.split(":", 1)
                if book.token_rate(provider, name) is None:
                    raise ValueError("Price unavailable")
            if retrieval == "hybrid" and book.token_rate("openai", "text-embedding-3-small") is None:
                raise ValueError("Embedding price unavailable")
            if exa and book.search_cost(1) is None:
                raise ValueError("Search price unavailable")
            st.session_state.console_quote = (quote_key, book)
        except Exception:
            st.session_state.pop("console_quote", None)
            st.error("Current prices are unavailable for the configured profile. Check the profile and try again.")
    quote = st.session_state.get("console_quote")
    quoted = bool(quote and quote[0] == quote_key)
    if quoted:
        st.success("Current prices checked. Costs are estimates, not a bill.")
        st.caption(str(quote[1].metadata()))
    else:
        st.info("Check current prices before launching a paid run.")
    enabled = os.environ.get("MIRA_ENABLE_BYOK_RUNS") == "1" and bool(os.environ.get("MIRA_BROKER_SOCKET"))
    if not enabled:
        st.warning("Paid launch is disabled by the operator. Existing reports remain available.")
    jurisdictions = st.multiselect("Jurisdictions", MVP_JURISDICTIONS, default=["SG", "HK"],
                                   format_func=lambda code: MARKET_NAMES.get(code, code))
    categories = rows(client().table("expected_sources").select(
        "source_id,jurisdiction_code,category,list_version,is_active").eq("is_active", True))
    groups = source_groups(list(source_by_id), categories, jurisdictions)
    focus = st.multiselect("Source focus", ["Regulatory", "Industry", "Other"],
                           default=["Regulatory", "Industry", "Other"])
    focused_ids = [source_id for source_id, group in groups.items() if group.intersection(focus)]
    period = st.selectbox("Period", ["Last 12 months", "Last 24 months", "Custom"])
    as_of = st.date_input("As-of date", value=date.today(), max_value=date.today())
    start = st.date_input("Period start", value=as_of - timedelta(days=365)) if period == "Custom" else as_of - timedelta(days=365 if period == "Last 12 months" else 730)
    end = st.date_input("Period end", value=as_of, max_value=as_of) if period == "Custom" else as_of
    with st.form("brief"):
        topic = st.selectbox("Topic", ["AML/CFT"])
        if "AE" in jurisdictions:
            st.caption("UAE coverage uses approved federal sources; DFSA is excluded.")
        selected = st.multiselect("Approved active sources", focused_ids, default=focused_ids,
                                  format_func=lambda i: source_by_id[i]["name"] + (" · manual" if source_by_id[i].get("source_type") == "manual" else ""))
        allowance = st.text_input("Maximum estimated cost (USD)", value="10.00")
        approval = st.checkbox("Approve research plan before acquisition")
        with st.expander("Advanced limits"):
            documents = st.number_input("Maximum documents", 5, 200, defaults.max_fetched_documents)
            minutes = st.number_input("Maximum run time (minutes)", 1, 240, int(defaults.max_run_minutes))
            batches = st.number_input("Maximum whole-passage analysis batches", 1, 64, 8)
        submitted = st.form_submit_button("Review research", type="primary", disabled=not (enabled and quoted))
    if not submitted:
        return
    try:
        amount = Decimal(allowance)
        if not amount.is_finite() or amount <= 0 or not selected:
            raise ValueError("Enter a positive allowance and select at least one source.")
        brief = Brief(topic=topic, jurisdictions=jurisdictions, period_start=start, period_end=end,
                      as_of_date=as_of, plan_requires_approval=approval)
        check_brief_scope(brief)
        RunBudget(max_fetched_documents=int(documents), max_llm_tokens=defaults.max_llm_tokens,
                  max_run_minutes=int(minutes), max_gap_rounds=defaults.max_gap_rounds, max_cost_usd=str(amount))
        settings = ResearchSettings(source_ids=tuple(selected), enable_exa=exa, enable_browser=browser,
                                    retrieval=retrieval, max_analysis_batches=int(batches), credential_mode="byok")
        st.session_state.pending_research = {"jurisdictions": jurisdictions, "start": start, "end": end,
            "as_of": as_of, "allowance": str(amount), "approval": approval, "documents": int(documents),
            "minutes": int(minutes), "settings": settings.as_dict()}
    except (ValueError, InvalidOperation) as exc:
        st.error(str(exc))
        return
    st.rerun()

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


def bind_fresh_credentials(sb: Client, workspace_id: str, run_id: str, keys: Mapping[str, str]) -> str:
    from mira.credentials import BrokerClient
    token = sb.auth.get_session().access_token
    broker = BrokerClient(os.environ["MIRA_BROKER_SOCKET"])
    handle = broker.put(token, workspace_id, run_id, dict(keys))
    try:
        sb.rpc("bind_run_credentials", {"p_run_id": run_id, "p_handle": handle}).execute()
    except Exception:
        try:
            broker.revoke(token, handle)
        except Exception:
            pass
        raise
    return handle


def continuation_quote(models: dict[str, str], research: dict[str, Any]) -> bool:
    from mira.pricing import load_price_book
    retrieval = research.get("retrieval", "keyword")
    exa = bool(research.get("enable_exa"))
    quote_key = (tuple(sorted(models.items())), retrieval, exa)
    if st.button("Check current prices for continuation"):
        try:
            book = load_price_book(models, embedding_model="text-embedding-3-small" if retrieval == "hybrid" else None, exa_enabled=exa)
            for model in models.values():
                provider, name = model.split(":", 1)
                if book.token_rate(provider, name) is None:
                    raise ValueError("Missing price")
            if retrieval == "hybrid" and book.token_rate("openai", "text-embedding-3-small") is None:
                raise ValueError("Missing embedding price")
            if exa and book.search_cost(1) is None:
                raise ValueError("Missing search price")
            st.session_state.console_quote = (quote_key, book)
        except Exception:
            st.session_state.pop("console_quote", None)
            st.error("Current prices are unavailable for this run.")
    quote = st.session_state.get("console_quote")
    checked = bool(quote and quote[0] == quote_key)
    if checked:
        st.caption(f"Price sources and checked time: {quote[1].metadata()}")
    else:
        st.info("Check current prices before continuing.")
    return checked and os.environ.get("MIRA_ENABLE_BYOK_RUNS") == "1" and bool(os.environ.get("MIRA_BROKER_SOCKET"))


def _providers(models: dict[str, str], research: dict[str, Any]) -> set[str]:
    providers = {v.split(":", 1)[0] for v in models.values() if ":" in v}
    if research.get("retrieval") == "hybrid":
        providers.add("openai")
    if research.get("enable_exa"):
        providers.add("exa")
    return providers


def _retry_credentials(sb: Client, run: dict[str, Any], role: str) -> None:
    if role not in ("admin", "analyst"):
        return
    research = (run.get("retrieval_settings") or {}).get("research") or {}
    if run["status"] != "queued" or research.get("credential_mode") != "byok":
        return
    st.info("If pending keys expired or the broker restarted, supply fresh keys to continue.")
    models = run.get("model_settings") or {}
    providers = _providers(models, research)
    enabled = continuation_quote(models, research)
    with st.form("retry-credentials", clear_on_submit=True):
        keys = {p: st.text_input(f"{p.title()} API key", type="password", key=f"retry-key-{p}-{st.session_state.get('retry_key_epoch', 0)}") for p in sorted(providers)}
        submit = st.form_submit_button("Supply fresh keys", disabled=not enabled)
    if not submit:
        return
    try:
        if not providers or any(not value.strip() for value in keys.values()):
            raise ValueError("Missing credentials")
        bind_fresh_credentials(sb, run["workspace_id"], run["id"], keys)
        previous = research.get("credential_handle")
        if previous:
            try:
                from mira.credentials import BrokerClient
                BrokerClient(os.environ["MIRA_BROKER_SOCKET"]).revoke(sb.auth.get_session().access_token, previous)
            except Exception:
                st.session_state.console_notice = ("warning", "Fresh keys supplied; the previous lease could not be revoked and expires within 60 minutes.")
        if not st.session_state.get("console_notice"):
            st.session_state.console_notice = ("success", "Fresh keys supplied for the queued run.")
    except Exception:
        st.session_state.console_notice = ("error", "Could not supply fresh keys. Refresh the run and try again.")
    finally:
        keys.clear()
        clear_key_widgets("retry", providers)
    st.rerun()


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
    st.info("Review the plan before approving acquisition.")
    research = (run.get("retrieval_settings") or {}).get("research") or {}
    if research.get("credential_mode") == "byok":
        models = run.get("model_settings") or {}
        providers = _providers(models, research)
        enabled = continuation_quote(models, research)
        with st.form("approve-plan", clear_on_submit=True):
            keys = {p: st.text_input(f"{p.title()} API key", type="password", key=f"approval-key-{p}-{st.session_state.get('approval_key_epoch', 0)}") for p in sorted(providers)}
            approve = st.form_submit_button("Approve plan", type="primary", disabled=not enabled)
        if not enabled:
            st.caption("Check prices and confirm paid launch is enabled before approving.")
        if not approve:
            return
        if not providers or any(not key.strip() for key in keys.values()):
            keys.clear()
            clear_key_widgets("approval", providers)
            st.session_state.console_notice = ("error", "Enter the required provider keys.")
            st.rerun()
        handle = None
        try:
            from mira.credentials import BrokerClient
            token = sb.auth.get_session().access_token
            broker = BrokerClient(os.environ["MIRA_BROKER_SOCKET"])
            handle = broker.put(token, run["workspace_id"], run["id"], keys)
            sb.rpc("bind_run_credentials", {"p_run_id": run["id"], "p_handle": handle}).execute()
            sb.table("research_plans").update({"approved_by": st.session_state.user_id,
                "approved_at": datetime.now(UTC).isoformat()}).eq("analysis_run_id", run["id"]).eq("version", latest["version"]).execute()
        except Exception:
            if handle:
                try:
                    broker.revoke(token, handle)
                except Exception:
                    pass
            st.session_state.console_notice = ("error", "Could not approve the plan. Check access and try again.")
            st.rerun()
        finally:
            keys.clear()
            clear_key_widgets("approval", providers)
        st.rerun()
    elif st.button("Approve plan", type="primary"):
        sb.table("research_plans").update({
            "approved_by": st.session_state.user_id,
            "approved_at": datetime.now(UTC).isoformat(),
        }).eq("analysis_run_id", run["id"]).eq("version", latest["version"]).execute()
        st.rerun()


def cancel_run(sb: Client, run: dict[str, Any]) -> bool:
    """Cancel the observed state, then revoke any still-pending credential lease."""
    result = sb.table("analysis_runs").update({"status": "cancelled"}).eq("id", run["id"]).eq("status", run["status"]).execute()
    if not result.data:
        raise ValueError("Run state changed; refresh and try again.")
    cancelled = result.data[0]
    settings = cancelled.get("retrieval_settings") if "retrieval_settings" in cancelled else run.get("retrieval_settings")
    handle = ((settings or {}).get("research") or {}).get("credential_handle")
    if handle:
        try:
            from mira.credentials import BrokerClient
            BrokerClient(os.environ["MIRA_BROKER_SOCKET"]).revoke(sb.auth.get_session().access_token, handle)
        except Exception:
            return False
    return True


def runs_page(workspace_id: str, role: str) -> None:
    st.header("Runs")
    run = pick_run(workspace_id)
    if run is None:
        return
    sb = client()
    steps = rows(sb.table("agent_steps").select("*").eq("analysis_run_id", run["id"]).order("step_no"))
    tokens = sum((s["tokens_in"] or 0) + (s["tokens_out"] or 0) for s in steps)
    cost = monetary_summary(run.get("retrieval_settings") or {})
    limits = run["source_limits"] or {}
    cols = st.columns(4)
    cols[0].metric("Status", run["status"])
    cols[1].metric("Model tokens", f"{tokens:,}", help=f"Run cap {limits.get('max_llm_tokens', 0):,}")
    cols[2].metric("Estimated cost", cost, help="List prices; an estimate, not a bill")
    cols[3].metric("Steps", len(steps))
    if (run.get("retrieval_settings") or {}).get("monetary_usage"):
        with st.expander("Cost estimate details"):
            for label, value in monetary_details(run["retrieval_settings"]):
                st.write(f"{label}: {value}")
            usage = run["retrieval_settings"]["monetary_usage"]
            if usage.get("elapsed_seconds") is not None:
                st.write(f"Elapsed: {usage['elapsed_seconds']} seconds")
            if usage.get("pricing"):
                st.write(usage["pricing"])
    if run["failure_summary"]:
        (st.error if run["status"] == "failed" else st.warning)(run["failure_summary"])

    plans = rows(sb.table("research_plans").select("plan,version,approved_at").eq("analysis_run_id", run["id"]).order("version"))
    waiting_approval = bool(plans and not plans[-1].get("approved_at") and
                            (run.get("retrieval_settings") or {}).get("plan_requires_approval"))
    if not waiting_approval:
        _retry_credentials(sb, run, role)
    if run["status"] in ACTIVE:
        left, right = st.columns([3, 1])
        left.info("Waiting for or running on the worker (`python -m mira worker`).")
        if right.button("Cancel run"):
            try:
                revoked = cancel_run(sb, run)
            except Exception:
                st.session_state.console_notice = ("error", "Could not cancel the run. Refresh and try again.")
            else:
                st.session_state.console_notice = (("success", "Run cancelled.") if revoked else
                    ("warning", "Run cancelled, but the pending credential lease could not be revoked. It expires within 60 minutes."))
            st.rerun()

    if run["status"] in RERUNNABLE_STATUSES:
        research = (run.get("retrieval_settings") or {}).get("research") or {}
        byok = research.get("credential_mode") == "byok"
        if byok:
            models = {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}
            providers = {v.split(":", 1)[0] for v in models.values() if ":" in v}
            if research.get("retrieval") == "hybrid":
                providers.add("openai")
            if research.get("enable_exa"):
                providers.add("exa")
            quote_key = (tuple(sorted(models.items())), research.get("retrieval", "keyword"), bool(research.get("enable_exa")))
            quote = st.session_state.get("console_quote")
            enabled = (os.environ.get("MIRA_ENABLE_BYOK_RUNS") == "1" and bool(os.environ.get("MIRA_BROKER_SOCKET"))
                       and bool(quote and quote[0] == quote_key))
            if not enabled:
                st.info("Check current prices in Research and confirm paid launch is enabled before re-running.")
            with st.form("rerun-credentials", clear_on_submit=True):
                keys = {p: st.text_input(f"{p.title()} API key", type="password", key=f"rerun-key-{p}-{st.session_state.get('rerun_key_epoch', 0)}") for p in sorted(providers)}
                rerun = st.form_submit_button("Re-run with the same brief", disabled=not enabled)
            if rerun:
                try:
                    if not providers or any(not v.strip() for v in keys.values()):
                        raise ValueError("Enter the required provider keys.")
                    clean = dict(research)
                    clean["credential_handle"] = None
                    new_run = queue_rerun(workspace_id, st.session_state.user_id, run,
                                          settings=ResearchSettings.from_dict(clean), provider_keys=keys)
                except Exception:
                    st.session_state.console_notice = ("error", "Could not queue the run. Check settings and credentials, then try again.")
                    st.rerun()
                else:
                    st.session_state.selected_run = new_run
                    st.rerun()
                finally:
                    keys.clear()
                    clear_key_widgets("rerun", providers)
        elif st.button("Re-run with the same brief", help="Queues a new run on the same project revision."):
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

    if run["status"] in ACTIVE and st.toggle("Refresh every 5 seconds", value=True, key="refresh-run"):
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
        corroboration = display.corroboration
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
        assessments = rows(sb.table("corroboration_assessments").select("id,sequence,finding_id,result")
                           .eq("workspace_id",workspace_id).eq("analysis_run_id",run["id"]).order("sequence"))
        corroboration = {row["finding_id"]:{"assessment_id":row["id"],"sequence":row["sequence"],
                          "assessment":row["result"]} for row in assessments}
        reviews = rows(sb.table("finding_reviews").select("*").in_("finding_id", ids)
                       .order("reviewed_at").order("review_sequence")) if ids else []
    cited = {fid for section in snapshot["sections"] for sentence in section["sentences"] for fid in sentence["finding_ids"]}
    unresolved = set(snapshot["unresolved_finding_ids"])
    latest_reviews = {review["finding_id"]: review for review in reviews}
    frozen_reviews = snapshot.get("review_outcomes", {})

    report_tab, findings_tab = st.tabs(["Report", f"Findings ({len(cited)} in report, {len(unresolved)} unresolved)"])
    with report_tab:
        from mira.artifact_access import read_report
        try:
            html = read_report(sb,uuid.UUID(workspace_id),uuid.UUID(report['id'])).decode('utf-8')
        except (PermissionError,UnicodeError):
            st.info("The report file is currently unavailable. Saved findings remain available for review.")
        else:
            components.html(html,height=900,scrolling=True)
        _original_downloads(sb,workspace_id,run['id'],snapshot,signed)
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
                assessment = corroboration.get(finding["id"])
                if assessment:
                    from mira.corroboration_display import assessment_html
                    components.html(assessment_html(assessment),height=380,scrolling=True)
                else:
                    st.caption("Corroboration: Not checked.")
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


def _original_downloads(sb: Client, workspace_id: str, run_id: str, snapshot: dict, signed: bool) -> None:
    """Load private bytes only after a deliberate request under the signed-in client."""
    from mira.original_access import read_original
    frozen = (snapshot.get('evidence_bundle') or {}).get('passages',{})
    if signed:
        expected = {p['document_version_id']:p.get('acquisition_provenance',{}).get('retained_original')
                    for p in frozen.values() if p.get('acquisition_provenance',{}).get('original_retained') is True}
        ids = list(expected)
    else:
        expected = {}
        ids = list({r['document_version_id'] for r in rows(sb.table('analysis_evidence').select('document_version_id')
                    .eq('workspace_id',workspace_id).eq('analysis_run_id',run_id))})
    versions = rows(sb.table('document_versions').select('id,title,metadata')
                    .eq('workspace_id',workspace_id).in_('id',ids)) if ids else []
    versions = [v for v in versions if (v.get('metadata') or {}).get('original_retained') is True
                and (not signed or v['metadata'].get('retained_original') == expected.get(v['id']))]
    if not versions:
        return
    with st.expander('Original source files'):
        st.caption('Retained copies are available where the source permits them. Access is checked when you open a file.')
        for version in versions:
            st.write(version['title'])
            key = f"original-{workspace_id}-{version['id']}"
            if st.button('Prepare download',key=key):
                try:
                    from mira.artifact_storage import original_store_from_env
                    storage = original_store_from_env(client=sb)
                    data = read_original(sb,uuid.UUID(workspace_id),uuid.UUID(version['id']),storage,
                                         expected_identity=expected.get(version['id']) if signed else None)
                except (PermissionError,ValueError,OSError):
                    st.info('This original is currently unavailable. You can still review its saved evidence in the report.')
                    continue
                identity = version['metadata']['retained_original']
                suffix = '.pdf' if identity.get('media_type') == 'application/pdf' else '.bin'
                name = re.sub(r'[^\w .-]','',version['title'])[:70].strip() or 'Source'
                st.download_button('Download original',data,file_name=name+suffix,
                                   mime='application/octet-stream',key=key+'-download')


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


def country_methods_page() -> None:
    from mira.method_results import country_method_results
    st.header("Country methods")
    st.caption("Public engineering results and recommendations; separate from workspace reports.")
    country = st.selectbox("Country or regulator", ["HK", "AU", "AE", "SG", "MY", "DFSA"])
    result = country_method_results(country)
    st.subheader(result.get("country_name", country))
    st.write(result.get("recommendation") or "Not available")
    for key in ("storage", "acquisition", "archive", "research", "quality_winner", "cost_comparison", "storage_size_comparison", "references"):
        value = result.get(key)
        with st.expander(key.replace("_", " ").title()):
            if value is None:
                st.write("Not available")
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and "method" in entry:
                        status = str(entry.get("status", "not_tested")).replace("_", " ").capitalize()
                        st.markdown(f"**{entry['method'].replace('_', ' ').title()} · {status}**")
                        st.write(entry.get("observation") or "Not available")
                        details = {k.replace("_", " "): v for k, v in entry.items()
                                   if k not in {"method", "status", "observation"}}
                        if details:
                            st.json(details)
                    elif isinstance(entry, dict):
                        st.write(entry.get("label", "Reference"), entry.get("path", ""))
                    else:
                        st.write(entry)
            elif isinstance(value, dict):
                st.json(value)
            else:
                st.write(value)


# --- Page ----------------------------------------------------------------------


def main() -> None:
    load_env(keys=UI_KEYS)
    st.set_page_config(page_title="Mira", layout="wide")
    from mira.console_style import apply_console_style
    apply_console_style()
    notice = st.session_state.pop("console_notice", None)
    if notice:
        getattr(st, notice[0])(notice[1])
    if "user_id" not in st.session_state:
        sign_in()
        return
    sb = client()
    workspace = rows(sb.table("workspaces").select("id,name").eq("slug", workspace_slug()))
    if not workspace:
        st.error("You are not a member of the configured workspace.")
        return
    workspace_id = workspace[0]["id"]
    if is_synthetic_demo(workspace_slug()):
        st.info("Synthetic demo data: one sample fact and one sample inference. These are separate from measured Hong Kong results.")
    member = rows(sb.table("workspace_members").select("role").eq("workspace_id", workspace_id)
                  .eq("user_id", st.session_state.user_id))
    role = member[0]["role"] if member else "none"
    with st.sidebar:
        st.markdown(f"**Mira** · {workspace[0]['name']}  \n{st.session_state.email} · {role}")
        page = st.radio("Page", ["Research", "Runs", "Reports & review", "Country methods"], label_visibility="collapsed")
        if st.button("Sign out"):
            sb.auth.sign_out()
            st.session_state.clear()
            st.rerun()
        st.caption("Draft reports are not compliance conclusions about the bank.")
    if page == "Research":
        if role in ("admin", "analyst"):
            new_brief_page(workspace_id, st.session_state.user_id)
        else:
            st.info("Only analysts and admins can start runs.")
    elif page == "Runs":
        runs_page(workspace_id, role)
    elif page == "Reports & review":
        review_page(workspace_id, st.session_state.user_id, role)
    else:
        country_methods_page()


if __name__ == "__main__":  # `streamlit run` executes the file as __main__
    main()
