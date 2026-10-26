"""Wires the real components together for the worker and the command line.

``execute_run`` runs one saved run end to end on the trusted worker connection.
The Streamlit app never imports this module: it queues runs through Supabase
under row-level security and the worker picks them up (PRD v2 §5.1).
"""

from __future__ import annotations

import os
from uuid import UUID

import psycopg

from mira.agents.scout import WebScout
from mira.agents.verifier import LlmVerifier
from mira.db import NotAuthorisedError, acting_as, require_role
from mira.fetch import AllowList, Fetcher
from mira.llm import ROLE_MODEL_ENV, AnthropicClient, LLMClient, estimated_cost
from mira.orchestrator import Orchestrator, RunOutcome
from mira.pg_store import PostgresStore, load_run


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
    client = client or AnthropicClient()
    store = PostgresStore(conn)
    fetcher = Fetcher(AllowList(store.list_sources(workspace)))
    scout = WebScout(dsn, client, fetcher)
    return Orchestrator(store, client, {"regulatory_scout": scout, "industry_scout": scout}, LlmVerifier(client))


def execute_run(conn: psycopg.Connection, dsn: str, run_id: UUID, client: LLMClient | None = None) -> RunOutcome:
    """Run a saved run, after checking the user who queued it still holds a run role (§5.1)."""
    ctx = load_run(conn, run_id)
    store = PostgresStore(conn)
    try:
        with acting_as(conn, ctx.user_id):
            require_role(conn, ctx.workspace_id)
    except NotAuthorisedError as exc:
        store.set_run_status(ctx, "failed", f"not run: {exc}")
        return RunOutcome("failed", [str(exc)], None, None)
    return build_orchestrator(conn, dsn, ctx.workspace_id, client).run(ctx)


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
