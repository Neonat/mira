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

from mira.config import REPORTS_DIR, load_env


def _table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "(none)"
    keys = list(rows[0])
    widths = {k: max(len(k), *(len(str(r[k])) for r in rows)) for k in keys}
    lines = ["  ".join(k.ljust(widths[k]) for k in keys)]
    lines += ["  ".join(str(r[k]).ljust(widths[k]) for k in keys) for r in rows]
    return "\n".join(lines)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(prog="mira")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed")
    run = commands.add_parser("run")
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
    if args.command == "import" and not args.manifest and (len(args.files) != 1 or not args.url):
        parser.error("import one file with --url, or several with --manifest")

    from mira.db import connect

    dsn = os.environ["MIRA_WORKER_DATABASE_URL"]
    with connect(dsn) as conn:
        if args.command == "seed":
            from mira.runner import workspace_id
            from mira.seed import seed

            result = seed(conn, workspace_id(conn))
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
                brief = Brief(topic="AML/CFT", jurisdictions=args.jurisdictions,
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
        elif args.command == "worker":
            from mira.pg_store import claim_next_run
            from mira.runner import execute_run, workspace_id

            workspace = workspace_id(conn)
            while True:
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
