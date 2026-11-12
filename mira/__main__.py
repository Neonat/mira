"""Command line for the trusted worker side of Mira.

    python -m mira seed                      upsert the allow-list and expected sources
    python -m mira run --jurisdictions HK    create a run as the dev user and execute it
    python -m mira worker [--once]           execute runs queued by the Streamlit app
    python -m mira usage RUN_ID              tokens and estimated cost per role
    python -m mira import mas FILE --url URL [--title T] [--published YYYY-MM-DD]
    python -m mira import mas --manifest data/manual/mas/manifest.csv
                                             load documents you downloaded by hand

Uses MIRA_WORKER_DATABASE_URL, so run it only on a trusted machine.
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

from mira.config import REPORTS_DIR, load_env, workspace_slug


def _table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "(none)"
    keys = list(rows[0])
    widths = {k: max(len(k), *(len(str(r[k])) for r in rows)) for k in keys}
    lines = ["  ".join(k.ljust(widths[k]) for k in keys)]
    lines += ["  ".join(str(r[k]).ljust(widths[k]) for k in keys) for r in rows]
    return "\n".join(lines)


def main() -> None:
    import sys
    command = sys.argv[1] if len(sys.argv)>1 else ''
    load_env(keys={'SUPABASE_URL','SUPABASE_ANON_KEY'} if command=='broker' else
             {'MIRA_WORKER_DATABASE_URL','MIRA_WORKSPACE_SLUG'} if command=='prepared-report-worker' else None)
    parser = argparse.ArgumentParser(prog="mira")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_cmd = commands.add_parser("seed")
    broker=commands.add_parser('broker',help='start the private local in-memory BYOK service; no research worker')
    broker.add_argument('--directory',type=Path,help='new short private directory, normally under /tmp')
    from mira.recovery_cli import add_backup_commands
    add_backup_commands(commands)
    run = commands.add_parser("run")
    from mira.brief import MVP_TOPICS
    seed_cmd.add_argument("--topic", choices=MVP_TOPICS, default="AML/CFT")
    run.add_argument("--topic", choices=MVP_TOPICS, default="AML/CFT")
    run.add_argument("--jurisdictions", nargs="+", default=["SG", "HK"])
    run.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    run.add_argument("--months", type=int, default=12)
    run.add_argument("--max-documents", type=int)
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--previous", type=UUID, metavar="RUN_ID",
                     help="re-run a finished run with the same brief and show what changed (PRD v2 §6.5)")
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=5.0)
    prep_worker = commands.add_parser('preparation-worker', help='poll explicitly enabled scheduled preparation')
    prep_worker.add_argument('--once', action='store_true')
    prep_worker.add_argument('--poll-seconds', type=float, default=5.0)
    report_worker = commands.add_parser('prepared-report-worker', help='assemble ready reports independently of preparation')
    report_worker.add_argument('--once', action='store_true')
    report_worker.add_argument('--poll-seconds', type=float, default=1.0)
    prepare = commands.add_parser('prepare', help='queue one explicit preparation from a JSON configuration')
    prepare.add_argument('configuration', type=Path)
    schedule = commands.add_parser('configure-schedule', help='register a schedule; disabled unless explicitly enabled')
    schedule.add_argument('configuration', type=Path)
    schedule.add_argument('--frequency-seconds', type=int, required=True)
    schedule.add_argument('--next-due', required=True, help='ISO 8601 timestamp with timezone')
    schedule.add_argument('--enable', action='store_true')
    usage = commands.add_parser("usage")
    usage.add_argument("run_id", type=UUID)
    manual = commands.add_parser("import", help="load documents you downloaded by hand into a source")
    manual.add_argument("source_key", help="for example mas, sso, fatf")
    manual.add_argument("files", nargs="*", type=Path, help="one file, with --url")
    manual.add_argument("--url", help="the https URL the file was downloaded from")
    manual.add_argument("--title")
    manual.add_argument("--published", type=date.fromisoformat, help="publication date, YYYY-MM-DD")
    manual.add_argument("--manifest", type=Path, help="CSV of file,url,title,published for several files")
    args = parser.parse_args()
    if args.command=='broker':
        from mira.credential_broker import run_broker
        run_broker(args.directory)
        return
    if args.command == "import" and not args.manifest and (len(args.files) != 1 or not args.url):
        parser.error("import one file with --url, or several with --manifest")

    if args.command == "backup":
        from mira.recovery_cli import execute_backup
        raise SystemExit(execute_backup(args))

    from mira.db import connect

    dsn = os.environ["MIRA_WORKER_DATABASE_URL"]
    with connect(dsn) as conn:
        if args.command == "seed":
            from mira.runner import workspace_id
            from mira.seed import seed

            result = seed(conn, workspace_id(conn), args.topic)
            print(f"{result.sources} sources and {result.expected_sources} expected sources upserted")
        elif args.command == "run":
            from mira.budget import RunBudget
            from mira.contracts import Brief
            from mira.pg_store import create_run
            from mira.runner import dev_user_id, execute_run, models_from_env, usage_by_role, workspace_id

            budget = RunBudget.from_env()
            if args.max_documents:
                budget = replace(budget, max_fetched_documents=args.max_documents)
            if args.max_tokens:
                budget = replace(budget, max_llm_tokens=args.max_tokens)
            if args.previous:
                from mira.pg_store import create_rerun

                ctx = create_rerun(conn, workspace_id(conn), dev_user_id(conn), args.previous, models_from_env())
                brief = ctx.brief
            else:
                brief = Brief(topic=args.topic, jurisdictions=args.jurisdictions,
                              period_start=args.as_of - timedelta(days=round(args.months * 365 / 12)),
                              period_end=args.as_of, as_of_date=args.as_of, plan_requires_approval=False)
                ctx = create_run(conn, workspace_id(conn), dev_user_id(conn), brief, budget, models_from_env())
            print(f"run {ctx.analysis_run_id}: {brief.jurisdictions} {brief.period_start} to {brief.period_end}, "
                  f"budget {budget.max_llm_tokens} tokens / {budget.max_fetched_documents} documents")
            outcome = execute_run(conn, dsn, ctx.analysis_run_id)
            print(f"status: {outcome.status}")
            for reason in outcome.reasons:
                print(f"  - {reason}")
            if outcome.report_id:
                print(f"report: {REPORTS_DIR / str(ctx.analysis_run_id)}")
            print(_table(usage_by_role(conn, ctx.analysis_run_id)))
        elif args.command in ('prepare', 'configure-schedule'):
            import json
            from datetime import datetime
            from uuid import uuid4
            from mira.preparation_store import PreparationStore
            from mira.runner import workspace_id, dev_user_id
            config = json.loads(args.configuration.read_text())
            required = {'source_ids', 'brief', 'budget', 'models', 'settings'}
            if set(config) != required:
                raise ValueError('Configuration must contain source_ids, brief, budget, models and settings')
            store = PreparationStore(conn)
            workspace, actor = workspace_id(conn, workspace_slug()), dev_user_id(conn)
            if args.command == 'prepare':
                result = store.enqueue_job(workspace, actor, **config, idempotency_key=str(uuid4()))
            else:
                next_due = datetime.fromisoformat(args.next_due)
                if next_due.tzinfo is None or args.frequency_seconds <= 0:
                    raise ValueError('A positive frequency and timezone-aware next due are required')
                result = store.configure_schedule(workspace, actor, **config,
                    frequency_seconds=args.frequency_seconds, next_due=next_due, enabled=args.enable)
            print(result)
        elif args.command == 'preparation-worker':
            from uuid import uuid4
            from mira.preparation_runtime import run_claimed_job
            from mira.preparation_store import PreparationStore
            from mira.runner import workspace_id
            if os.environ.get('MIRA_ENABLE_SCHEDULED_PREPARATION')!='1':
                raise SystemExit('Scheduled preparation is disabled')
            if args.poll_seconds <= 0:
                raise ValueError('poll interval must be positive')
            workspace, owner = workspace_id(conn,workspace_slug()), uuid4()
            store = PreparationStore(conn)
            while True:
                store.tick_schedules(workspace)
                job = store.claim_job(workspace, owner)
                if job:
                    print(f"preparation {job['id']}: {run_claimed_job(conn, dsn, store, job)}")
                if args.once:
                    break
                time.sleep(args.poll_seconds)
        elif args.command == 'prepared-report-worker':
            from mira.runner import workspace_id
            from mira.prepared_reporting import execute_prepared_request
            if args.poll_seconds<=0:raise ValueError('poll interval must be positive')
            workspace=workspace_id(conn,workspace_slug())
            while True:
                try:
                    outcome=execute_prepared_request(conn,dsn,workspace_id=workspace)
                    if outcome.get('status') not in ('idle','waiting'):print(f"report request: {outcome}")
                except Exception as exc:
                    if args.once:raise
                    print(f"Prepared report worker error: {type(exc).__name__}")
                if args.once:break
                time.sleep(args.poll_seconds)
        elif args.command == "worker":
            from mira.pg_store import claim_next_run
            from mira.runner import execute_run, workspace_id

            from mira.render_job import render_pending

            workspace = workspace_id(conn)
            while True:
                # Sign-offs first: a reviewed file is a small render, and the reviewer is waiting for it.
                try:
                    for report_id in render_pending(conn, workspace):
                        print(f"rendered reviewed report {report_id}")
                except Exception as exc:  # one bad sign-off must not stop the worker or other sign-offs
                    print(f"render failed with {type(exc).__name__}: {exc}")
                if os.environ.get('MIRA_ARTIFACT_STORAGE','local')!='local':
                    from mira.artifact_jobs import retry_publications
                    try:
                        retry_publications(conn,workspace)
                    except Exception as exc:
                        print(f"artifact publication retry failed: {type(exc).__name__}")
                run_id = claim_next_run(conn, workspace)
                if run_id:
                    print(f"running {run_id}")
                    try:
                        outcome = execute_run(conn, dsn, run_id)
                        print(f"{run_id}: {outcome.status}")
                    except Exception as exc:  # one broken run must not stop the worker
                        print(f"{run_id}: failed with {type(exc).__name__}: {exc}")
                elif args.once:
                    break
                else:
                    time.sleep(args.poll_seconds)
                if args.once:
                    break
        elif args.command == "usage":
            from mira.runner import usage_by_role

            print(_table(usage_by_role(conn, args.run_id)))
        elif args.command == "import":
            from mira.manual_import import ImportItem, ImportRefused, import_files, load_source, read_manifest
            from mira.runner import dev_user_id, workspace_id

            workspace = workspace_id(conn)
            try:
                source = load_source(conn, workspace, args.source_key)
                items = read_manifest(args.manifest) if args.manifest else [
                    ImportItem(args.files[0], args.url, args.title, args.published)]
                results = import_files(conn, workspace, dev_user_id(conn), args.source_key, items)
            except ImportRefused as exc:
                raise SystemExit(f"import refused: {exc}") from exc
            if "store_text" not in source.permitted_operations:
                print(f"note: {source.name} does not permit store_text, so only metadata was saved and "
                      "nothing from it can be cited")
            print(_table([{
                "file": r.item.path.name, "outcome": r.outcome, "passages": r.passages,
                "url": r.item.url, "error": r.error or "",
            } for r in results]))
            if any(r.outcome == "failed" for r in results):
                raise SystemExit(1)


if __name__ == "__main__":
    main()
