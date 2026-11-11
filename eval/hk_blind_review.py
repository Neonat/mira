"""Build the blind Hong Kong review pack from its pinned local archive."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mira.db import connect
from mira.hybrid_archive import POOL


DIRECTORY = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("reports/hk-blind-review/mira-hong-kong-blind-review.html")
INVENTORY = POOL + """
select p.id::text, v.id::text version_id, s.source_key, v.published_at::date published_at,
       p.content_sha256, p.content, v.title, v.source_url, dp.page_number, dp.passage_number
from pool p
join public.document_passages dp on dp.id = p.id
join public.document_versions v on v.id = dp.document_version_id
join public.documents d on d.id = v.document_id
join public.sources s on s.id = d.source_id
order by p.id
"""


def digest(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def local_connection_info(dsn):
    info = conninfo_to_dict(dsn)
    hosts = {"localhost": "127.0.0.1", "127.0.0.1": "127.0.0.1", "::1": "::1"}
    host = info.get("host")
    if host not in hosts or info.get("hostaddr", hosts[host]) not in hosts.values():
        raise ValueError("MIRA_TEST_DATABASE_URL must explicitly name a loopback database host.")
    return make_conninfo(dsn, hostaddr=info.get("hostaddr", hosts[host]), connect_timeout=5)


def load_scopes(conn, manifest):
    workspace_id = manifest["workspace_id"]
    source_keys = manifest["source_keys"]
    with conn.transaction():
        conn.execute("set transaction isolation level repeatable read read only")
        conn.execute("set local statement_timeout = '10s'")
        sources = conn.execute(
            """
            select id, source_key from public.sources
            where workspace_id = %s and source_key = any(%s)
              and is_active and 'quote' = any(permitted_operations)
            """,
            (workspace_id, source_keys),
        ).fetchall()
        if {row["source_key"] for row in sources} != set(source_keys):
            raise ValueError("The pinned local sources or their review permissions are unavailable.")
        source_ids = [row["id"] for row in sources]
        pools = {}
        for key, scope in manifest["scopes"].items():
            params = {
                "ws": workspace_id,
                "sources": source_ids,
                "jurisdiction": scope["jurisdiction"],
                "jurisdictions": scope["brief_jurisdictions"],
                "as_of": scope["as_of"],
            }
            pools[key] = conn.execute(INVENTORY, params).fetchall()
        return pools


def build_pack(manifest, pools):
    publications = {}
    passages = {}
    for key, scope in manifest["scopes"].items():
        rows = pools[key]
        fingerprint = digest([
            [row[field] for field in ("id", "version_id", "source_key", "published_at", "content_sha256")]
            for row in rows
        ])
        if len(rows) != scope["eligible_passages"] or fingerprint != scope["corpus_sha256"]:
            raise ValueError(f"The saved archive has drifted from the pinned fingerprint for scope {key}.")
        for row in rows:
            published_at = row["published_at"]
            publications[row["version_id"]] = {
                "title": row["title"], "source_key": row["source_key"], "source_url": row["source_url"],
                "published_at": str(published_at) if published_at is not None else None,
            }
            passages[row["id"]] = {
                field: row[field] for field in ("version_id", "content", "page_number", "passage_number")
            }

    cases = []
    for case in manifest["cases"]:
        key = case["scope"]
        scope = manifest["scopes"][key]
        cases.append({
            "id": case["id"], "question": case["question"], "jurisdiction": scope["jurisdiction"],
            "as_of": scope["as_of"], "corpus_sha256": scope["corpus_sha256"],
            "passage_ids": [row["id"] for row in pools[key]],
        })
    pack = {"cases": cases, "publications": publications, "passages": passages}
    pack["pack_id"] = digest(pack)
    return pack


def render_review(template, pack, guide):
    context = {version: guide["context"][version] for version in pack["publications"]}
    shortlists = {}
    for case in pack["cases"]:
        ids = guide["shortlists"][case["id"]]
        versions = {pack["passages"][pid]["version_id"] for pid in ids}
        if len(ids) > 3 or len(versions) != len(ids) or not set(ids) <= set(case["passage_ids"]):
            raise ValueError(f"The shortlist is outside the scope for {case['id']}.")
        shortlists[case["id"]] = ids
    data = {
        "{{PACK_DATA}}": pack,
        "{{REVIEW_GUIDE}}": {"selection": guide["selection"], "context": context, "shortlists": shortlists},
    }
    parts = template.split("{{PACK_DATA}}")
    if len(parts) != 2 or parts[1].count("{{REVIEW_GUIDE}}") != 1:
        raise ValueError("The review template is missing its data placeholders.")
    # Escape literal less-than signs so saved HTML cannot terminate a data script.
    return parts[0] + json.dumps(data["{{PACK_DATA}}"], ensure_ascii=False).replace("<", r"\u003c") + parts[1].replace(
        "{{REVIEW_GUIDE}}", json.dumps(data["{{REVIEW_GUIDE}}"], ensure_ascii=False).replace("<", r"\u003c"), 1
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    dsn = os.environ.get("MIRA_TEST_DATABASE_URL")
    if not dsn:
        parser.error("Set MIRA_TEST_DATABASE_URL to the local saved archive database.")
    try:
        manifest = json.loads((DIRECTORY / "hk_blind_review_cases.json").read_text(encoding="utf-8"))
        guide = json.loads((DIRECTORY / "hk_blind_review_guide.json").read_text(encoding="utf-8"))
        template = (DIRECTORY / "hk_blind_review.html").read_text(encoding="utf-8")
        with connect(local_connection_info(dsn)) as conn:
            pools = load_scopes(conn, manifest)
        html = render_review(template, build_pack(manifest, pools), guide)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=args.output.parent, mode="w", encoding="utf-8", delete=False) as temp:
            temp_path = Path(temp.name)
            try:
                temp.write(html)
                temp.close()
                temp_path.replace(args.output)
            finally:
                temp_path.unlink(missing_ok=True)
    except (psycopg.Error, OSError, KeyError, ValueError) as exc:
        # Driver errors can include connection details. Keep the DSN out of output.
        detail = str(exc) if type(exc) is ValueError else "Could not read the local archive or write the pack."
        print(detail, file=sys.stderr)
        return 2
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
