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
from mira.analysis_batches import AnalysisLimits
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
        approved = {urlsplit(source.base_url).hostname, *source.connector_config.get("extra_hosts", [])}
        selected = source.connector_config.get("discovery_hosts", approved)
        domains.update(host for host in selected if isinstance(host,str) and host in approved)
    if not domains:
        return None
    return ExaDiscovery(search=ExaHTTP(os.environ["EXA_API_KEY"], domains=sorted(domains)))


def browser_from_env():
    if os.environ.get("MIRA_ENABLE_OFFLINE_BROWSER") != "1":
        return None
    from mira.browser_capture import OfflineBrowserCapture
    return OfflineBrowserCapture()


def live_browser_from_env(fetcher):
    if os.environ.get("MIRA_ENABLE_LIVE_BROWSER") != "1":
        return None
    from mira.live_browser import LiveBrowserAcquirer
    return LiveBrowserAcquirer(fetcher)


def hybrid_from_env(generation_budget=None):
    """A flag and explicit vector identity are required; a key alone enables nothing."""
    if os.environ.get("MIRA_ENABLE_HYBRID_RETRIEVAL") != "1":
        return None
    from mira.hybrid import EmbeddingIdentity, HybridLimits, OpenAIEmbedder
    from mira.hybrid_runtime import HybridRetriever
    from openai import OpenAI
    model = os.environ.get('MIRA_EMBEDDING_MODEL','').strip()
    revision = os.environ.get('MIRA_EMBEDDING_REVISION','').strip()
    if not model or not revision:
        raise ValueError('hybrid retrieval requires an explicit embedding model and revision')
    identity = EmbeddingIdentity(model,revision,int(os.environ.get('MIRA_EMBEDDING_DIMENSIONS','384')))
    limits = HybridLimits(
        max_index_passages=int(os.environ.get('MIRA_HYBRID_MAX_PASSAGES','40')),
        max_characters=int(os.environ.get('MIRA_HYBRID_MAX_CHARACTERS','60000')),
        max_tokens=int(os.environ.get('MIRA_HYBRID_MAX_TOKENS','20000')),
        timeout_seconds=float(os.environ.get('MIRA_HYBRID_TIMEOUT_SECONDS','20')),
        result_limit=int(os.environ.get('MIRA_HYBRID_RESULT_LIMIT','20')),
        max_index_batches=int(os.environ.get('MIRA_HYBRID_MAX_INDEX_BATCHES','4')))
    embedder=OpenAIEmbedder(OpenAI(max_retries=0),identity,reserved_tokens=limits.max_tokens)
    if generation_budget is not None:
        from mira.generation import GenerationEmbedder
        embedder=GenerationEmbedder(embedder,generation_budget)
    return HybridRetriever(embedder,identity,limits)


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
    live_browser = live_browser_from_env(fetcher)
    from mira.generation import GenerationClient
    shared_budget=client.budget if isinstance(client,GenerationClient) else None
    scout = WebScout(dsn, client, fetcher, discovery=discovery, browser=browser, live_browser=live_browser,
                     hybrid=hybrid_from_env(shared_budget))
    return Orchestrator(store, client, {"regulatory_scout": scout, "industry_scout": scout}, LlmVerifier(client),
                        analysis_limits=AnalysisLimits.from_env(),
                        corroborator=ClaimCorroborator(conn,client,discovery=discovery,browser=browser,live_browser=live_browser))


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
    from mira.generation import GenerationBudget,GenerationClient
    if client is None or (not isinstance(client,GenerationClient) and callable(getattr(client,'structured_bounded',None))):
        client=GenerationClient(client or ProviderClient(),GenerationBudget(ctx.budget.max_llm_tokens,ctx.budget.max_run_minutes*60))
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
