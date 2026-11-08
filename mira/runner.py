"""Wires the real components together for the worker and the command line.

``execute_run`` runs one saved run end to end on the trusted worker connection.
The Streamlit app never imports this module: it queues runs through Supabase
under row-level security and the worker picks them up (PRD v2 §5.1).
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit
from typing import Literal
from uuid import UUID

import psycopg

from mira.agents.scout import WebScout
from mira.agents.verifier import LlmVerifier
from mira.db import NotAuthorisedError, acting_as, require_role
from mira.fetch import AllowList, Fetcher
from mira.llm import ROLE_MODEL_ENV, ProviderClient, LLMClient, estimated_cost
from mira.orchestrator import Orchestrator, RunOutcome
from mira.corroboration_runtime import ClaimCorroborator
from mira.pg_store import PostgresStore, load_run
from mira.single_agent import QuoteOnlyVerifier, code_plan

def discovery_from_env(sources):
    """Paid discovery is opt-in; credentials alone never activate it."""
    if os.environ.get("MIRA_ENABLE_EXA_DISCOVERY") != "1" or not os.environ.get("EXA_API_KEY"):
        return None
    from mira.discovery import ExaDiscovery, ExaHTTP
    domains = set()
    for source in sources:
        if not {"fetch", "store_text"} <= set(source.permitted_operations) or not source.base_url:
            continue
        host = urlsplit(source.base_url).hostname
        if host:
            domains.add(host)
        domains.update(source.connector_config.get("extra_hosts", []))
    if not domains:
        return None
    return ExaDiscovery(search=ExaHTTP(os.environ["EXA_API_KEY"], domains=sorted(domains)))


def browser_from_env():
    if os.environ.get("MIRA_ENABLE_OFFLINE_BROWSER") != "1":
        return None
    from mira.browser_capture import OfflineBrowserCapture
    return OfflineBrowserCapture()


Arm = Literal["multi_agent", "single_agent"]


def workspace_id(conn: psycopg.Connection, slug: str = "mira") -> UUID:
    return conn.execute("select id from public.workspaces where slug = %s", (slug,)).fetchone()["id"]


def dev_user_id(conn: psycopg.Connection) -> UUID:
    email = os.environ.get("MIRA_DEV_EMAIL")
    if not email:
        raise SystemExit("MIRA_DEV_EMAIL is not set (see README: local login)")
    row = conn.execute("select id from auth.users where email = %s", (email,)).fetchone()
    if row is None:
        raise SystemExit(f"no Auth user with email {email}")
    return row["id"]


def models_from_env() -> dict[str, str]:
    return {role: os.environ.get(var, "") for role, var in ROLE_MODEL_ENV.items()}


def build_orchestrator(conn: psycopg.Connection, dsn: str, workspace: UUID, client: LLMClient | None = None) -> Orchestrator:
    client = client or ProviderClient()
    store = PostgresStore(conn)
    fetcher = Fetcher(AllowList(store.list_sources(workspace)))
    discovery = discovery_from_env(store.list_sources(workspace))
    browser = browser_from_env()
    scout = WebScout(dsn, client, fetcher, discovery=discovery, browser=browser)
    return Orchestrator(store, client, {"regulatory_scout": scout, "industry_scout": scout}, LlmVerifier(client),
                        corroborator=ClaimCorroborator(conn,client,discovery=discovery,browser=browser))


def build_single_agent_orchestrator(
    conn: psycopg.Connection, dsn: str, workspace: UUID, client: LLMClient | None = None,
) -> Orchestrator:
    """The single-agent comparison arm (docs/single_agent_arm_design.md §5): same store, scout and fetcher;
    a code-built plan, one scout and the quote-only verifier. Its runs must be created with no gap rounds."""
    client = client or ProviderClient()
    store = PostgresStore(conn)
    fetcher = Fetcher(AllowList(store.list_sources(workspace)))
    return Orchestrator(
        store, client, {"regulatory_scout": WebScout(dsn, client, fetcher)}, QuoteOnlyVerifier(),
        plan_strategy=lambda client, brief, sources, expected, max_documents: code_plan(
            brief, sources, expected, max_documents),
    )


def execute_run(
    conn: psycopg.Connection, dsn: str, run_id: UUID, client: LLMClient | None = None, arm: Arm = "multi_agent",
) -> RunOutcome:
    """Run a saved run, after checking the user who queued it still holds a run role (§5.1)."""
    ctx = load_run(conn, run_id)
    store = PostgresStore(conn)
    try:
        with acting_as(conn, ctx.user_id):
            require_role(conn, ctx.workspace_id)
    except NotAuthorisedError as exc:
        store.set_run_status(ctx, "failed", f"not run: {exc}")
        return RunOutcome("failed", [str(exc)], None, None)
    build = build_single_agent_orchestrator if arm == "single_agent" else build_orchestrator
    return build(conn, dsn, ctx.workspace_id, client).run(ctx)


def usage_by_role(conn: psycopg.Connection, run_id: UUID) -> list[dict[str, object]]:
    """Tokens and estimated cost per role and model for one run, from agent_steps."""
    rows = conn.execute(
        """select role, coalesce(model, '-') as model, count(*) as steps, coalesce(sum(tokens_in), 0) as tokens_in,
                  coalesce(sum(tokens_out), 0) as tokens_out
           from public.agent_steps where analysis_run_id = %s group by role, model order by min(step_no)""",
        (run_id,),
    ).fetchall()
    for row in rows:
        row["cost_usd"] = round(estimated_cost(row["model"], row["tokens_in"], row["tokens_out"]), 4)
    return rows
