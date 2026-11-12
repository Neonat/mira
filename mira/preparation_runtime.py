"""Explicitly invoked scheduled preparation worker; no work starts on import."""
from __future__ import annotations

import threading


class PreparationLeaseLost(RuntimeError):
    """The attempt no longer owns the preparation lease."""


def process_job(store, job, *, create_run, execute, payload, frontier=None,
                heartbeat_factory=None, heartbeat_interval=30):
    """Execute a single claimed job; never resume a previously dispatched run.

    ``heartbeat_factory`` opens an independent store/connection for long calls.
    Every publication and progress operation is additionally fenced by the store.
    """
    lost = threading.Event()
    stopped = threading.Event()

    def guard(phase=None):
        try:
            if lost.is_set():
                valid = False
            elif heartbeat_factory is None:
                valid = store.heartbeat_job(job, phase)
            else:
                with heartbeat_factory() as other:
                    valid = other.heartbeat_job(job, phase)
        except Exception as exc:
            lost.set()
            raise PreparationLeaseLost('preparation lease lost') from exc
        if not valid:
            lost.set()
            raise PreparationLeaseLost('preparation lease lost')

    def heartbeat():
        try:
            with heartbeat_factory() as other:
                while not stopped.wait(heartbeat_interval):
                    if not other.heartbeat_job(job, None):
                        lost.set()
                        return
        except Exception:
            lost.set()

    thread = None
    try:
        guard('starting')
        if job.get('analysis_run_id'):
            store.fail_job(job, 'Interrupted preparation requires an explicit new job; prior usage is retained.')
            return 'failed'
        if heartbeat_factory is not None:
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
        run_id = create_run(job)
        guard('starting')
        job['analysis_run_id'] = run_id
        outcome = execute(run_id, guard, frontier)
        guard('publishing')
        if outcome.status not in ('draft', 'partial'):
            store.fail_job(job, 'Preparation did not finish successfully.')
            return 'failed'
        result = payload(run_id, job['source_ids'])
        guard('publishing')
        store.publish_job(job, result)
        return 'published'
    except PreparationLeaseLost:
        return 'lease_lost'
    except Exception:
        try:
            guard('failed')
            store.fail_job(job, 'Preparation failed; inspect the run and start an explicit new job.')
        except Exception:
            pass
        return 'failed'
    finally:
        stopped.set()
        if thread is not None:
            thread.join()


class FrontierAdapter:
    """Scout-facing durable frontier, with a connection per operation."""
    def __init__(self, store_factory, job, allow):
        self.store_factory, self.job, self.allow = store_factory, job, allow

    def record(self, links, request_url, version_id):
        grouped = {}
        from mira.fetch import FetchRefused
        for link in links:
            try:
                source = self.allow.source_for(link.url)
                if str(source.id) not in {str(x) for x in self.job['source_ids']}:
                    continue
            except (FetchRefused, ValueError, PermissionError):
                continue
            grouped.setdefault(source.id, []).append({
                'url': link.url, 'text': link.text, 'context': link.context,
                'published': link.published.isoformat() if link.published else None,
                'date_source': link.date_source,
                'origin': {'request_url': request_url,
                           'document_version_id': str(version_id) if version_id else None},
            })
        with self.store_factory() as store:
            for source_id, entries in grouped.items():
                store.put_frontier(self.job, source_id, entries)

    def pending(self, source_ids, limit, start_date=None, as_of_date=None):
        from datetime import date
        from mira.extract import Link
        with self.store_factory() as store:
            rows = store.pending_frontier(self.job, source_ids, limit, start_date=start_date, as_of_date=as_of_date)
        return [Link(row['url'], row['text'], row['context'],
                     date.fromisoformat(row['published']) if isinstance(row.get('published'), str) else row.get('published'),
                     row.get('date_source')) for row in rows]

    def finish(self, url, status, error=None):
        source = self.allow.source_for(url)
        with self.store_factory() as store:
            store.finish_frontier(self.job, source.id, url, status, error=error)


def create_preparation_run(conn, store, job):
    """Create, mark and attach a run in one transaction before dispatch."""
    from mira.budget import RunBudget
    from mira.contracts import Brief
    from mira.db import acting_as
    from mira.pg_store import create_run
    from mira.research_settings import ResearchSettings
    from mira.runner import models_from_env
    models = job['models']
    if not models or models != models_from_env() or not all(models.values()):
        raise ValueError('Scheduled models differ from the operator profile')
    budget = RunBudget(**job['budget'])
    caps = RunBudget.from_env()
    if not (budget.max_cost_usd is not None and 1 <= budget.max_fetched_documents <= 200
            and 0 < budget.max_llm_tokens <= caps.max_llm_tokens
            and 0 < budget.max_run_minutes <= 240
            and 0 <= budget.max_gap_rounds <= caps.max_gap_rounds):
        raise ValueError('Scheduled resource limits exceed worker limits')
    settings = ResearchSettings.from_dict(job['settings'])
    if settings.credential_mode != 'operator' or set(settings.source_ids or ()) != {str(x) for x in job['source_ids']}:
        raise ValueError('Scheduled source scope and operator settings must match')
    brief = Brief.model_validate(job['brief'])
    with acting_as(conn, job['actor_id']):
        ctx = create_run(conn, job['workspace_id'], job['actor_id'], brief, budget, models, settings=settings)
        conn.execute("""update public.analysis_runs set retrieval_settings=jsonb_set(
            retrieval_settings, '{execution_mode}', '"preparation"'::jsonb)
            where id=%s and workspace_id=%s""", (ctx.analysis_run_id, job['workspace_id']))
        store.set_job_run(job, ctx.analysis_run_id)
    return ctx.analysis_run_id


def run_claimed_job(conn, dsn, store, job):
    """Run one explicit lease using independent scout and heartbeat connections."""
    from contextlib import contextmanager
    from mira.db import connect
    from mira.fetch import AllowList
    from mira.pg_store import PostgresStore
    from mira.preparation_store import PreparationStore
    from mira.research_settings import ResearchSettings, restrict_sources
    from mira.runner import execute_run
    from mira.prepared_reporting import build_prepared_payload

    @contextmanager
    def other_store():
        with connect(dsn) as other:
            yield PreparationStore(other)

    try:
        settings = ResearchSettings.from_dict(job['settings'])
        sources = restrict_sources(PostgresStore(conn).list_sources(job['workspace_id']), settings,
                                   job['brief']['jurisdictions'], topic=job['brief']['topic'])
        frontier = FrontierAdapter(other_store, job, AllowList(sources))
    except Exception:
        try:
            store.fail_job(job, 'Preparation source configuration unavailable.')
        except Exception:
            return 'lease_lost'
        return 'failed'
    return process_job(store, job,
        create_run=lambda item: create_preparation_run(conn, store, item),
        execute=lambda run_id, guard, work: execute_run(conn, dsn, run_id, preparation=True,
                                                        preparation_guard=guard, frontier=work),
        payload=lambda run_id, source_ids: build_prepared_payload(conn, run_id, source_ids),
        frontier=frontier, heartbeat_factory=other_store)
