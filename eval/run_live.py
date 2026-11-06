"""Run the three comparison arms live on one brief, then score them (PRD v2 §11; design sections 5-7).

    python eval/run_live.py run [--jurisdictions SG HK] [--as-of 2026-10-26] [--months 12] [--sample 30]
    python eval/run_live.py score eval/results/<stamp>

``run`` executes, on the trusted worker connection and with the real Claude client:

1. the multi-agent arm (the default orchestrator),
2. the single-agent arm (``mira.single_agent``: code plan, one scout, quote-only verifier, no gap rounds),
3. plain search over the saved passages (``eval/arms.py``), with no model.

The order is deliberate. All arms share one evidence store, and a scout also reads passages earlier runs saved,
so an arm that runs later inherits the pages an earlier arm fetched. The multi-agent arm runs first, so any
advantage goes to the single agent: a multi-agent win under the PRD rule is then a conservative result. Plain
search runs last, over everything the agents saved.

It writes a results folder with each arm's cited URLs, recall on the M0 ground truth, cost and time, the
reports, and one precision worksheet holding both model arms' sampled claims. Rows are ordered by a hash, so the
two arms are interleaved; hide the ``arm`` column while labelling.

``score`` re-reads a results folder once a human has filled in the worksheet's ``label`` column, takes
precision from ``eval/precision.py`` and applies the decision rule again. Whether each arm was live is read
back from the models its ``agent_steps`` recorded, not from the results file.

Stop the worker (``python -m mira worker``) first: the runs are created queued and executed here, and a worker
running at the same time could pick one up as well. The ground truth is read only after the runs finish and is
never passed to Mira.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent))

from arms import Hit, plain_search  # noqa: E402
from compare import Measured, decide  # noqa: E402
from precision import ClaimRow, sample, score as score_precision, write_worksheet  # noqa: E402
from score_recall import load_items, score as score_recall  # noqa: E402

GROUND_TRUTH = Path(__file__).parent / "m0_ground_truth.csv"
RESULTS = Path(__file__).parent / "results"
MODEL_ARMS = ("multi_agent", "single_agent")
WORKSHEET = "precision_worksheet.csv"
PLAIN_SEARCH_LIMIT = 50
QUERIES = {"AML/CFT": "money laundering or terrorist financing or terrorism financing or AML or CFT or sanctions"}


@dataclass(frozen=True)
class Evidence:
    url: str
    quote: str
    passage: str


@dataclass(frozen=True)
class Finding:
    title: str
    content: str
    is_inference: bool


@dataclass(frozen=True)
class RunRecords:
    """What one model arm's run left in the database, keyed by finding ID."""

    findings: Mapping[str, Finding]
    evidence: Mapping[str, Sequence[Evidence]]
    depends_on: Mapping[str, Sequence[str]]


# --- Pure parts: what a report cites ----------------------------------------------------------------------


def report_finding_ids(snapshot: Mapping[str, object]) -> list[str]:
    """Finding IDs the report body cites, in order. Structural sentences cite nothing (AG10)."""
    ids: list[str] = []
    for section in snapshot.get("sections", []):  # type: ignore[union-attr]
        for sentence in section["sentences"]:
            if sentence["structural"]:
                continue
            for finding_id in sentence["finding_ids"]:
                if str(finding_id) not in ids:
                    ids.append(str(finding_id))
    return ids


def _with_facts(finding_ids: Sequence[str], records: RunRecords) -> list[str]:
    """The cited findings plus the facts every cited inference rests on, depth first, without repeats."""
    seen: list[str] = []

    def visit(finding_id: str) -> None:
        if finding_id in seen:
            return
        seen.append(finding_id)
        for dependency in records.depends_on.get(finding_id, ()):
            visit(dependency)

    for finding_id in finding_ids:
        visit(finding_id)
    return seen


def cited_urls(finding_ids: Sequence[str], records: RunRecords) -> list[str]:
    """Source URLs of the passages behind the report's findings, including the facts its inferences rest on."""
    urls: list[str] = []
    for finding_id in _with_facts(finding_ids, records):
        for item in records.evidence.get(finding_id, ()):
            if item.url not in urls:
                urls.append(item.url)
    return urls


def sample_id(arm: str, finding_id: str) -> str:
    """Stable across runs of the script, and mixes the two arms when the worksheet is sorted by it."""
    return hashlib.sha256(f"{arm}:{finding_id}".encode()).hexdigest()[:12]


def claim_rows(arm: str, finding_ids: Sequence[str], records: RunRecords) -> list[ClaimRow]:
    """One worksheet row per claim the report cites. An inference has no passage of its own, so its row shows
    the verified facts it rests on, and the reviewer judges whether they support it."""
    rows = []
    for finding_id in finding_ids:
        finding = records.findings.get(finding_id)
        if finding is None:
            continue
        if finding.is_inference:
            facts = [records.findings[d] for d in records.depends_on.get(finding_id, ()) if d in records.findings]
            passage = "Rests on these verified facts:\n" + "\n".join(f"- {f.title}: {f.content}" for f in facts)
            quote = ""
        else:
            items = records.evidence.get(finding_id, ())
            passage = "\n---\n".join(f"[{item.url}]\n{item.passage}" for item in items)
            quote = " | ".join(item.quote for item in items)
        rows.append(ClaimRow(sample_id=sample_id(arm, finding_id), arm=arm,
                             claim=f"{finding.title}: {finding.content}", cited_passage=passage,
                             supporting_quote=quote))
    return rows


def recall_summary(urls: Sequence[str]) -> dict[str, dict[str, int]]:
    recall = score_recall(load_items(GROUND_TRUTH), urls)
    return {label: {"found": r.found, "total": r.total} for label, r in recall.items()}


def coverage_of(arm: Mapping[str, object]) -> float | None:
    """Coverage the rule compares: recall on all ground-truth items. None if the arm produced no report."""
    if arm.get("recall") is None:
        return None
    total = arm["recall"]["all"]  # type: ignore[index]
    return total["found"] / total["total"] if total["total"] else None


def write_summary(folder: Path, summary: Mapping[str, object], verdict_message: str,
                  precision: Mapping[str, object] | None = None) -> None:
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# Three-arm comparison, {summary['created_at']}",
        "",
        f"Brief: {summary['brief']['topic']}, {', '.join(summary['brief']['jurisdictions'])}, "  # type: ignore[index]
        f"{summary['brief']['period_start']} to {summary['brief']['period_end']}",  # type: ignore[index]
        f"Run order: {', '.join(summary['order'])} (later arms reuse pages earlier arms saved)",  # type: ignore[arg-type]
        "",
        "| Arm | Status | Recall (all) | Recall (fetchable) | Recall (regulatory) | Precision | Cost (US$) | Minutes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, arm in summary["arms"].items():  # type: ignore[union-attr]
        recall = arm.get("recall")
        cells = ["-", "-", "-"] if recall is None else [
            f"{recall[k]['found']}/{recall[k]['total']}" for k in ("all", "fetchable", "regulatory")]
        prec = "n/a" if name not in MODEL_ARMS else "not labelled"
        if precision and name in precision:
            p = precision[name]
            prec = f"{p['supported']}/{p['labelled']}" if p["rate"] is not None else f"{p['unlabelled']} unlabelled"
        cost = "-" if arm.get("cost_usd") is None else f"{arm['cost_usd']:.2f}"
        minutes = "-" if arm.get("seconds") is None else f"{arm['seconds'] / 60:.1f}"
        lines.append(f"| {name} | {arm['status']} | {' | '.join(cells)} | {prec} | {cost} | {minutes} |")
    lines += [
        "",
        f"**Verdict:** {verdict_message}",
        "",
        "A difference of one or two ground-truth items is within noise on a list this size "
        "(docs/single_agent_arm_design.md section 8).",
    ]
    (folder / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- Database parts ---------------------------------------------------------------------------------------


def load_records(conn, user_id: UUID, run_id: UUID) -> RunRecords:  # noqa: ANN001 (psycopg connection)
    from mira.db import acting_as

    with acting_as(conn, user_id):
        findings = {
            str(row["id"]): Finding(row["title"], row["content"], row["is_inference"])
            for row in conn.execute(
                "select id, title, content, is_inference from public.analysis_findings where analysis_run_id = %s",
                (run_id,),
            ).fetchall()
        }
        evidence: dict[str, list[Evidence]] = {}
        for row in conn.execute(
            """select fe.finding_id, dv.source_url, fe.supporting_quote, p.content
               from public.finding_evidence fe
               join public.analysis_evidence ae on ae.id = fe.analysis_evidence_id
               join public.document_versions dv on dv.id = ae.document_version_id
               left join public.document_passages p on p.id = ae.passage_id
               where fe.analysis_run_id = %s and fe.support_type = 'supports'
               order by fe.created_at""",
            (run_id,),
        ).fetchall():
            evidence.setdefault(str(row["finding_id"]), []).append(
                Evidence(row["source_url"], row["supporting_quote"] or "", row["content"] or ""))
        depends_on: dict[str, list[str]] = {}
        for row in conn.execute(
            "select finding_id, depends_on_finding_id from public.finding_dependencies where analysis_run_id = %s",
            (run_id,),
        ).fetchall():
            depends_on.setdefault(str(row["finding_id"]), []).append(str(row["depends_on_finding_id"]))
    return RunRecords(findings, evidence, depends_on)


def recorded_models(conn, run_id: UUID) -> list[str | None]:  # noqa: ANN001
    rows = conn.execute("select model from public.agent_steps where analysis_run_id = %s", (run_id,)).fetchall()
    return [row["model"] for row in rows]


def passage_search(conn, workspace: UUID, user_id: UUID) -> Callable[[str, int], list[Hit]]:  # noqa: ANN001
    """search_passages as the user, with each passage's source URL, for arm (a)."""
    from mira.db import acting_as

    def search(query: str, limit: int) -> list[Hit]:
        with acting_as(conn, user_id):
            rows = conn.execute(
                """select s.passage_id, dv.source_url, dv.title, s.content
                   from public.search_passages(%s, %s, %s) s
                   join public.document_versions dv on dv.id = s.document_version_id
                   order by s.rank_score desc, s.passage_id""",
                (workspace, query, limit),
            ).fetchall()
        return [Hit(str(r["passage_id"]), r["source_url"], r["title"] or "", r["content"]) for r in rows]

    return search


# --- Commands ---------------------------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    import os

    from mira.budget import RunBudget
    from mira.contracts import Brief
    from mira.db import connect
    from mira.llm import AnthropicClient
    from mira.pg_store import create_run
    from mira.runner import dev_user_id, execute_run, models_from_env, usage_by_role, workspace_id

    client = AnthropicClient()
    dsn = os.environ["MIRA_WORKER_DATABASE_URL"]
    budget = RunBudget.from_env()
    if args.max_documents:
        budget = replace(budget, max_fetched_documents=args.max_documents)
    if args.max_tokens:
        budget = replace(budget, max_llm_tokens=args.max_tokens)
    brief = Brief(topic="AML/CFT", jurisdictions=args.jurisdictions,
                  period_start=args.as_of - timedelta(days=round(args.months * 365 / 12)),
                  period_end=args.as_of, as_of_date=args.as_of, plan_requires_approval=False)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = RESULTS / stamp
    folder.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "created_at": stamp,
        "brief": {"topic": brief.topic, "jurisdictions": brief.jurisdictions,
                  "period_start": brief.period_start, "period_end": brief.period_end},
        "budget": asdict(budget),
        "order": [*MODEL_ARMS, "plain_search"],
        "arms": {},
    }
    arms: dict[str, dict[str, object]] = summary["arms"]  # type: ignore[assignment]
    rows: list[ClaimRow] = []
    measured: dict[str, Measured] = {}

    with connect(dsn) as conn:
        workspace, user = workspace_id(conn), dev_user_id(conn)
        for arm in MODEL_ARMS:
            # The single agent does one pass: no gap rounds (design section 3).
            arm_budget = replace(budget, max_gap_rounds=0) if arm == "single_agent" else budget
            ctx = create_run(conn, workspace, user, brief, arm_budget, models_from_env())
            print(f"{arm}: run {ctx.analysis_run_id}")
            started = time.monotonic()
            outcome = execute_run(conn, dsn, ctx.analysis_run_id, client, arm=arm)
            seconds = time.monotonic() - started
            usage = usage_by_role(conn, ctx.analysis_run_id)
            record: dict[str, object] = {
                "run_id": ctx.analysis_run_id, "status": outcome.status, "reasons": outcome.reasons,
                "seconds": round(seconds, 1), "cost_usd": round(sum(float(u["cost_usd"]) for u in usage), 4),
                "tokens": sum(int(u["tokens_in"]) + int(u["tokens_out"]) for u in usage),
                "recall": None, "cited_urls": [], "report": None,
            }
            if outcome.snapshot is not None:
                snapshot = json.loads(outcome.snapshot.model_dump_json())
                records = load_records(conn, user, ctx.analysis_run_id)
                cited = report_finding_ids(snapshot)
                record["cited_urls"] = cited_urls(cited, records)
                record["recall"] = recall_summary(record["cited_urls"])  # type: ignore[arg-type]
                record["report"] = f"reports/{ctx.analysis_run_id}"
                rows += sample(claim_rows(arm, cited, records), args.sample)
            arms[arm] = record
            measured[arm] = Measured.from_client(arm, client, coverage_of(record), record["cost_usd"],  # type: ignore[arg-type]
                                                 seconds)
            print(f"  {outcome.status}, {len(record['cited_urls'])} cited URLs, US${record['cost_usd']}")  # type: ignore[arg-type]

        started = time.monotonic()
        result = plain_search(QUERIES.get(brief.topic, brief.topic), passage_search(conn, workspace, user),
                              limit=PLAIN_SEARCH_LIMIT)
        seconds = time.monotonic() - started
        arms["plain_search"] = {
            "status": "draft", "reasons": result.notes, "seconds": round(seconds, 1), "cost_usd": 0.0, "tokens": 0,
            "cited_urls": list(result.cited_urls), "recall": recall_summary(result.cited_urls),
        }
        (folder / "plain_search.md").write_text(
            "\n".join([f"# {result.notes[0]}", "", *[f"- {url}" for url in result.cited_urls]]) + "\n",
            encoding="utf-8")
        # Plain search calls no model; it is live when it searched a store the live model arms just filled.
        measured["plain_search"] = Measured.from_client("plain_search", client, coverage_of(arms["plain_search"]),
                                                        0.0, seconds)

    write_worksheet(sorted(rows, key=lambda row: row.sample_id), folder / WORKSHEET)
    verdict = decide(measured)
    write_summary(folder, summary, verdict.message)
    print(f"\nresults: {folder}\nverdict: {verdict.message}")
    print(f"next: label {folder / WORKSHEET}, then run: python eval/run_live.py score {folder}")
    return 0


def score(args: argparse.Namespace) -> int:
    import os

    from mira.db import connect

    folder: Path = args.folder
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    arms: dict[str, dict[str, object]] = summary["arms"]
    precision = {arm: asdict(score_precision(folder / WORKSHEET, arm)) for arm in MODEL_ARMS}
    measured: dict[str, Measured] = {}
    with connect(os.environ["MIRA_WORKER_DATABASE_URL"]) as conn:
        models = {arm: recorded_models(conn, UUID(str(arms[arm]["run_id"]))) for arm in MODEL_ARMS}
    for arm in MODEL_ARMS:
        measured[arm] = Measured.from_recorded_models(
            arm, models[arm], coverage_of(arms[arm]), arms[arm]["cost_usd"], arms[arm]["seconds"],  # type: ignore[arg-type]
            precision[arm]["rate"])  # type: ignore[arg-type]
    # Plain search ran in the same session over the store the model arms filled; it is live if both were.
    measured["plain_search"] = Measured.from_recorded_models(
        "plain_search", [*models["multi_agent"], *models["single_agent"]], coverage_of(arms["plain_search"]),
        0.0, arms["plain_search"]["seconds"])  # type: ignore[arg-type]
    verdict = decide(measured)
    write_summary(folder, summary, verdict.message, precision)
    for arm, p in precision.items():
        state = f"{p['supported']}/{p['labelled']} supported" if p["rate"] is not None else f"{p['unlabelled']} rows unlabelled"
        print(f"{arm}: precision {state}")
    print(f"verdict: {verdict.message}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from mira.config import load_env

    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    live = commands.add_parser("run", help="run all three arms live and write a results folder")
    live.add_argument("--jurisdictions", nargs="+", default=["SG", "HK"])
    # The M0 ground truth window ends on 26 October 2026; keep the as-of date there so recall is comparable.
    live.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 10, 26))
    live.add_argument("--months", type=int, default=12)
    live.add_argument("--max-documents", type=int)
    live.add_argument("--max-tokens", type=int)
    live.add_argument("--sample", type=int, default=30, help="claims sampled per model arm for precision")
    rescore = commands.add_parser("score", help="add labelled precision to a results folder and re-decide")
    rescore.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    return run(args) if args.command == "run" else score(args)


if __name__ == "__main__":
    sys.exit(main())
