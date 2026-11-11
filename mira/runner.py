"""Wires the real components together for the worker and the command line.

``execute_run`` runs one saved run end to end on the trusted worker connection.
The Streamlit app never imports this module: it queues runs through Supabase
under row-level security and the worker picks them up (PRD v2 §5.1).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit
from typing import Literal
from uuid import UUID

import psycopg

from mira.agents.scout import WebScout
from mira.analysis_batches import AnalysisLimits
from mira.budget import RunBudget
from mira.agents.verifier import LlmVerifier
from mira.db import NotAuthorisedError, acting_as, require_role
from mira.fetch import AllowList, Fetcher
from mira.llm import ROLE_MODEL_ENV, ProviderClient, LLMClient, estimated_cost
from mira.orchestrator import Orchestrator, RunOutcome
from mira.corroboration_runtime import ClaimCorroborator
from mira.pg_store import PostgresStore, load_run
from mira.single_agent import QuoteOnlyVerifier, code_plan
from mira.research_settings import ResearchSettings,restrict_sources
from mira.pricing import load_price_book

def discovery_from_env(sources,*,settings=None,api_keys=None,generation_budget=None):
    """Paid discovery is opt-in; credentials alone never activate it."""
    if settings is not None and not settings.enable_exa:return None
    enabled=os.environ.get('MIRA_ENABLE_EXA_DISCOVERY')=='1'
    key=api_keys.get('exa') if api_keys is not None else os.environ.get('EXA_API_KEY')
    if settings is not None and (not enabled or not key):
        raise ValueError('Exa operator capability or request credential unavailable')
    if not enabled or not key:
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
    search=ExaHTTP(key,domains=sorted(domains))
    if generation_budget is not None:
        from mira.generation import GenerationSearch
        search=GenerationSearch(search,generation_budget)
    return ExaDiscovery(search=search)


def browser_from_env(*,settings=None):
    if settings is not None and not settings.enable_browser:return None
    if os.environ.get("MIRA_ENABLE_OFFLINE_BROWSER") != "1":
        return None
    from mira.browser_capture import OfflineBrowserCapture
    return OfflineBrowserCapture()


def live_browser_from_env(fetcher,*,settings=None):
    if settings is not None and not settings.enable_browser:return None
    if os.environ.get("MIRA_ENABLE_LIVE_BROWSER") != "1":
        return None
    from mira.live_browser import LiveBrowserAcquirer
    return LiveBrowserAcquirer(fetcher)


def hybrid_from_env(generation_budget=None,*,settings=None,api_keys=None):
    """A flag and explicit vector identity are required; a key alone enables nothing."""
    if settings is not None and settings.retrieval!='hybrid':return None
    if os.environ.get("MIRA_ENABLE_HYBRID_RETRIEVAL") != "1":
        if settings is not None:raise ValueError('Hybrid operator capability unavailable')
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
    if api_keys is not None:
        if not api_keys.get('openai'):raise ValueError('Embedding request credential unavailable')
        provider=SimpleNamespace(api_key=api_keys['openai'],base_url='https://api.openai.com/v1',organization=None,project=None)
    else:provider=OpenAI(max_retries=0)
    embedder=OpenAIEmbedder(provider,identity,reserved_tokens=limits.max_tokens)
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


def build_orchestrator(conn: psycopg.Connection, dsn: str, workspace: UUID, client: LLMClient | None = None,
                       *,settings=None,api_keys=None,ctx=None,frontier=None) -> Orchestrator:
    client = client or ProviderClient()
    store = PostgresStore(conn)
    from mira.generation import GenerationClient
    shared_budget=client.budget if isinstance(client,GenerationClient) else None
    sources=restrict_sources(store.list_sources(workspace),settings,ctx.brief.jurisdictions if ctx else [])
    fetcher = Fetcher(AllowList(sources))
    discovery = discovery_from_env(sources,settings=settings,api_keys=api_keys,generation_budget=shared_budget)
    browser = browser_from_env(settings=settings)
    live_browser = live_browser_from_env(fetcher,settings=settings)
    if settings is not None and settings.enable_browser and browser is None and live_browser is None:
        raise ValueError('Browser operator capability unavailable')
    scout = WebScout(dsn, client, fetcher, discovery=discovery, browser=browser, live_browser=live_browser,
                     hybrid=hybrid_from_env(shared_budget,settings=settings,api_keys=api_keys),
                     **({'frontier':frontier} if frontier is not None else {}))
    return Orchestrator(store, client, {"regulatory_scout": scout, "industry_scout": scout}, LlmVerifier(client),
                        max_parallel_analysis=4,max_parallel_checks=4,
                        analysis_limits=replace(AnalysisLimits.from_env(),max_batches=settings.max_analysis_batches)
                            if settings else AnalysisLimits.from_env(),
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
    *, preparation=False, preparation_guard=None, frontier=None,
) -> RunOutcome:
    """Run a saved run, after checking the user who queued it still holds a run role (§5.1)."""
    # A session lock spans journal commits and the whole invocation, including cleanup.
    locked=conn.execute("select pg_try_advisory_lock(hashtextextended(%s,0)) locked",(str(run_id),)).fetchone()['locked']
    if not locked:return RunOutcome('busy',['Run already executing'],None,None)
    try:
        return _execute_locked(conn,dsn,run_id,client,arm,preparation=preparation,
                               preparation_guard=preparation_guard,frontier=frontier)
    finally:
        conn.execute("select pg_advisory_unlock(hashtextextended(%s,0))",(str(run_id),))


def _execute_locked(conn,dsn,run_id,client,arm,*,preparation=False,preparation_guard=None,frontier=None):
    ctx = load_run(conn, run_id)
    status=conn.execute("select status from public.analysis_runs where id=%s",(run_id,)).fetchone()['status']
    if status not in ('queued','running'):
        return RunOutcome(status,['Run no longer available for execution'],None,None)
    store = PostgresStore(conn)
    if preparation_guard is not None:
        preparation_guard()
    try:
        with acting_as(conn, ctx.user_id):
            require_role(conn, ctx.workspace_id)
    except NotAuthorisedError as exc:
        store.set_run_status(ctx, "failed", f"not run: {exc}")
        return RunOutcome("failed", [str(exc)], None, None)
    if ctx.research_settings is not None and ctx.research_settings.credential_mode=='byok':
        from uuid import uuid4
        invocation=str(uuid4())
        with acting_as(conn,ctx.user_id):
            conn.execute("""update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,
                '{worker_invocation}',to_jsonb(%s::text)) where id=%s and workspace_id=%s
                and status in ('queued','running')""",(invocation,run_id,ctx.workspace_id))
        return _execute_byok(conn,dsn,ctx,arm=arm,external_client=client,invocation=invocation,
                             preparation=preparation,preparation_guard=preparation_guard,frontier=frontier)
    if preparation and client is None:
        if preparation_guard is None:
            raise ValueError('Scheduled preparation requires a current job lease')
        from uuid import uuid4
        invocation=str(uuid4())
        with acting_as(conn,ctx.user_id):
            conn.execute("update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,'{worker_invocation}',to_jsonb(%s::text)) where id=%s and workspace_id=%s",
                         (invocation,run_id,ctx.workspace_id))
        return _execute_byok(conn,dsn,ctx,arm=arm,invocation=invocation,enterprise=True,
                             preparation=True,preparation_guard=preparation_guard,frontier=frontier)
    build = build_single_agent_orchestrator if arm == "single_agent" else build_orchestrator
    from mira.generation import GenerationBudget,GenerationClient
    if client is None or (not isinstance(client,GenerationClient) and callable(getattr(client,'structured_bounded',None))):
        client=GenerationClient(client or ProviderClient(),GenerationBudget(ctx.budget.max_llm_tokens,ctx.budget.max_run_minutes*60))
    if ctx.research_settings is not None:
        if arm!='multi_agent':raise ValueError('Per-request controls require the research console execution path')
        worker=build(conn,dsn,ctx.workspace_id,client,settings=ctx.research_settings,ctx=ctx,
                     **({'frontier':frontier} if frontier is not None else {}))
    else:
        worker=build(conn, dsn, ctx.workspace_id, client,
                     **({'frontier':frontier} if frontier is not None else {}))
    return worker.run(ctx,**({'preparation':True,'preparation_guard':preparation_guard} if preparation else {}))


def _journal_usage(dsn,ctx,snapshot,invocation):
    """Commit admission before dispatch, using an independent worker transaction.

    If a settlement write fails, its previous pending reservation remains durable
    and is charged as unknown on continuation. No later provider call is admitted.
    """
    from mira.db import connect
    from psycopg.conninfo import make_conninfo
    from psycopg.types.json import Jsonb
    value={k:v for k,v in snapshot.items() if k!='spending'}
    value.update(snapshot['spending'])
    journal_dsn=make_conninfo(dsn,connect_timeout='5',options='-c statement_timeout=5000 -c lock_timeout=3000')
    with connect(journal_dsn) as journal,acting_as(journal,ctx.user_id):
        row=journal.execute("""update public.analysis_runs set retrieval_settings=
            jsonb_set(retrieval_settings,'{monetary_usage}',%s)
            where id=%s and workspace_id=%s and created_by=%s
              and retrieval_settings->>'worker_invocation'=%s
            returning status,private.has_workspace_role(workspace_id,array['admin','analyst']) allowed""",
            (Jsonb(value),ctx.analysis_run_id,ctx.workspace_id,ctx.user_id,invocation)).fetchone()
    if row is None:raise ValueError('Usage journal unavailable')
    if snapshot.get('pending_tokens',0) or any(c['status']=='pending' for c in snapshot['calls']):
        if row['status']!='running' or not row['allowed']:
            raise ValueError('Run cancelled or access removed; no further request sent')


def _clear_credential_handle(conn,ctx):
    with acting_as(conn,ctx.user_id):
        conn.execute("""update public.analysis_runs set retrieval_settings=jsonb_set(retrieval_settings,
            '{research,credential_handle}','null'::jsonb) where id=%s and workspace_id=%s
            and retrieval_settings->'research'->>'credential_handle' is not distinct from %s""",
            (ctx.analysis_run_id,ctx.workspace_id,ctx.research_settings.credential_handle))


def _execute_byok(conn,dsn,ctx,*,arm,external_client=None,invocation,enterprise=False,
                  preparation=False,preparation_guard=None,frontier=None):
    from mira.credential_worker import claim_keys
    from mira.credentials import CredentialError
    from mira.generation import GenerationBudget,GenerationClient
    from mira.spending import SpendingLedger
    store=PostgresStore(conn);keys={};provider=None;budget=None
    began=time.monotonic()
    try:
        settings=ctx.research_settings
        try:
            if enterprise:
                if os.environ.get('MIRA_ENABLE_SCHEDULED_PREPARATION')!='1' or preparation_guard is None:
                    raise ValueError('Scheduled enterprise preparation is disabled')
                preparation_guard()
                names={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','deepseek':'DEEPSEEK_API_KEY','exa':'EXA_API_KEY'}
                keys={p:os.environ[n] for p,n in names.items() if os.environ.get(n)}
            else:
                keys=claim_keys(settings.credential_handle,str(ctx.workspace_id),str(ctx.user_id),str(ctx.analysis_run_id),
                    socket_path=os.environ.get('MIRA_BROKER_WORKER_SOCKET',''),
                    capability_path=os.environ.get('MIRA_BROKER_CAPABILITY_PATH',''))
        except CredentialError:
            if store.cancel_requested(ctx):return RunOutcome('cancelled',['Run cancelled'],None,None)
            with acting_as(conn,ctx.user_id):
                conn.execute("""update public.analysis_runs set status='queued', failure_summary=%s,
                    retrieval_settings=case when retrieval_settings->'research'->>'credential_handle' is not distinct from %s
                        then jsonb_set(retrieval_settings,'{research,credential_handle}','null'::jsonb) else retrieval_settings end
                    where id=%s and status in ('queued','running') and retrieval_settings->>'worker_invocation'=%s""",
                    ('Temporary keys expired or unavailable. Attach fresh keys to continue.',settings.credential_handle,ctx.analysis_run_id,invocation))
            return RunOutcome('awaiting_credentials',['Attach fresh temporary keys to continue'],None,None)
        if store.cancel_requested(ctx):return RunOutcome('cancelled',['Run cancelled'],None,None)
        if not enterprise and os.environ.get('MIRA_ENABLE_BYOK_RUNS')!='1':raise ValueError('BYOK launch is disabled by the operator')
        if arm!='multi_agent' or external_client is not None:raise ValueError('Unsupported BYOK execution path')
        models=models_from_env()
        if not all(models.values()) or dict(ctx.model_settings or {})!=models:
            raise ValueError('Queued models differ from the current operator profile; queue a fresh request')
        required={model.partition(':')[0] for model in models.values()}
        if settings.enable_exa:required.add('exa')
        if settings.retrieval=='hybrid':required.add('openai')
        if not required<=set(keys):raise ValueError('A required temporary provider credential is missing')
        if ctx.budget.max_cost_usd is None:raise ValueError('A USD cost allowance is required')
        caps=RunBudget.from_env()
        if not (1<=ctx.budget.max_fetched_documents<=200 and 0<ctx.budget.max_run_minutes<=240
                and 0<ctx.budget.max_llm_tokens<=caps.max_llm_tokens
                and 0<=ctx.budget.max_gap_rounds<=caps.max_gap_rounds):
            raise ValueError('Requested resource limits exceed worker limits')
        sources=restrict_sources(store.list_sources(ctx.workspace_id),settings,ctx.brief.jurisdictions)
        if not sources:raise ValueError('No selected source is currently available')
        if settings.enable_exa and os.environ.get('MIRA_ENABLE_EXA_DISCOVERY')!='1':raise ValueError('Exa operator capability unavailable')
        if settings.enable_browser and not any(os.environ.get(k)=='1' for k in ('MIRA_ENABLE_OFFLINE_BROWSER','MIRA_ENABLE_LIVE_BROWSER')):
            raise ValueError('Browser operator capability unavailable')
        if settings.retrieval=='hybrid' and os.environ.get('MIRA_ENABLE_HYBRID_RETRIEVAL')!='1':raise ValueError('Hybrid operator capability unavailable')
        quote=load_price_book(models,embedding_model=os.environ.get('MIRA_EMBEDDING_MODEL') if settings.retrieval=='hybrid' else None,
                              exa_enabled=settings.enable_exa)
        old=dict(ctx.resource_usage or {})
        ledger=SpendingLedger(Decimal(ctx.budget.max_cost_usd),quote,
            known_usd=Decimal(old.get('known_estimated_usd','0')),
            unknown_usd=Decimal(old.get('unknown_reserved_usd','0'))+Decimal(old.get('pending_usd','0')))
        old['elapsed_seconds']=float(old.get('elapsed_seconds',0))+(time.monotonic()-began)
        def journal(value):
            if preparation_guard is not None:
                preparation_guard()
            _journal_usage(dsn,ctx,value,invocation)
        budget=GenerationBudget(ctx.budget.max_llm_tokens,ctx.budget.max_run_minutes*60,
            spending=ledger,models=models,initial_usage=old,on_change=journal)
        with acting_as(conn,ctx.user_id):
            require_role(conn,ctx.workspace_id)
            started=conn.execute("""update public.analysis_runs set status='running',failure_summary=null,
                started_at=coalesce(started_at,now()) where id=%s and workspace_id=%s and status in ('queued','running') returning id""",
                (ctx.analysis_run_id,ctx.workspace_id)).fetchone()
        if started is None:return RunOutcome('cancelled',['Run no longer available for execution'],None,None)
        _journal_usage(dsn,ctx,budget.snapshot(),invocation)
        provider=ProviderClient(models=models,api_keys=keys)
        wrapped=GenerationClient(provider,budget)
        return build_orchestrator(conn,dsn,ctx.workspace_id,wrapped,settings=settings,api_keys=keys,ctx=ctx,
            **({'frontier':frontier} if frontier is not None else {})).run(ctx,
            **({'preparation':True,'preparation_guard':preparation_guard} if preparation else {}))
    except Exception:
        # Provider/credential exceptions can contain request internals. Persist a safe
        # operational message rather than exception strings or request bodies.
        with acting_as(conn,ctx.user_id):
            conn.execute("""update public.analysis_runs set status='failed',failure_summary=%s,finished_at=now() where id=%s
                and status in ('queued','running') and retrieval_settings->>'worker_invocation'=%s""",
                ('Request configuration, current prices or usage journal unavailable; no further requests sent.',ctx.analysis_run_id,invocation))
        return RunOutcome('failed',['Request configuration, current prices or usage journal unavailable'],None,None)
    finally:
        if budget is not None:
            try:_journal_usage(dsn,ctx,budget.snapshot(),invocation)
            except Exception:pass  # the last durable reservation remains conservative
        if provider is not None:provider.close()
        keys.clear()
        if not enterprise:
            _clear_credential_handle(conn,ctx)


def usage_by_role(conn: psycopg.Connection, run_id: UUID) -> list[dict[str, object]]:
    """Tokens and estimated cost per role and model for one run, from agent_steps."""
    rows = conn.execute(
        """select role, coalesce(model, '-') as model, count(*) as steps, coalesce(sum(tokens_in), 0) as tokens_in,
                  coalesce(sum(tokens_out), 0) as tokens_out
           from public.agent_steps where analysis_run_id = %s group by role, model order by min(step_no)""",
        (run_id,),
    ).fetchall()
    for row in rows:
        cost=estimated_cost(row['model'],row['tokens_in'],row['tokens_out'])
        row['cost_usd']=round(cost,4) if cost is not None else None
    return rows
