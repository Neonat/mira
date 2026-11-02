"""Manual import: documents a person downloaded by hand become evidence (PRD v1 IN02; approved sources §access).

For sources that refuse automated access (MAS since 26 Oct 2026, Singapore
Statutes Online, HK e-Legislation, FATF, BIS), a curator downloads the document
in a browser and imports it with the URL it came from. The file then goes
through the same extraction and ``EvidenceWriter`` as a fetched page, so it is
content-hashed, versioned and split into passages (when the source permits
``store_text``), and citations point at the original URL.

Checks before anything is saved:

- the URL is https on one of the source's own hosts, so a citation cannot point elsewhere
- the file is a PDF or HTML page within the fetch size cap
- the file is not a saved copy of the site's block page
- the importing user is a curator or admin in the workspace

Each import is recorded as an ``ingestion_runs`` row (mode ``manual_upload``)
with one ``ingestion_run_items`` row per file, so failures stay visible.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from mira.completeness import source_hosts
from mira.db import acting_as, require_role
from mira.evidence import EvidenceWriter
from mira.extract import extract
from mira.fetch import MAX_BYTES, FetchedPage, PageKind
from mira.store import SourceRecord

IMPORT_ROLES = ("admin", "curator")
FILE_KINDS: dict[str, tuple[PageKind, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".html": ("html", "text/html"),
    ".htm": ("html", "text/html"),
}


class ImportRefused(ValueError):
    """The file or its URL fails a check; nothing was saved."""


@dataclass(frozen=True)
class ImportItem:
    path: Path
    url: str
    title: str | None = None
    published: date | None = None


@dataclass(frozen=True)
class ImportResult:
    item: ImportItem
    outcome: str  # saved, unchanged or failed
    document_version_id: UUID | None
    passages: int
    error: str | None


def read_manifest(path: Path) -> list[ImportItem]:
    """Rows of ``file,url,title,published``; ``file`` is relative to the manifest, the last two may be blank."""
    items = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            if not (row.get("file") or "").strip():
                continue
            if not (row.get("url") or "").strip():
                raise ImportRefused(f"{path.name} line {line}: url is required")
            published = (row.get("published") or "").strip()
            items.append(ImportItem(
                path=(path.parent / row["file"].strip()),
                url=row["url"].strip(),
                title=(row.get("title") or "").strip() or None,
                published=date.fromisoformat(published) if published else None,
            ))
    return items


def load_source(conn: psycopg.Connection, workspace_id: UUID, source_key: str) -> SourceRecord:
    row = conn.execute(
        """select id, name, source_type, base_url, jurisdiction_code, permitted_operations, connector_config
           from public.sources where workspace_id = %s and source_key = %s and is_active""",
        (workspace_id, source_key),
    ).fetchone()
    if row is None:
        raise ImportRefused(f"no active source with key {source_key!r}")
    return SourceRecord(row["id"], row["name"], row["source_type"], row["base_url"],
                        (row["jurisdiction_code"] or "").strip() or None, tuple(row["permitted_operations"]),
                        row["connector_config"] or {})


def prepare_page(item: ImportItem, source: SourceRecord, imported_at: datetime) -> FetchedPage:
    """Check one file against the rules above and wrap it as a page; raises ``ImportRefused``."""
    try:
        parts = urlsplit(item.url)
        port = parts.port
    except ValueError as exc:
        raise ImportRefused('Invalid source URL; give a valid https URL.') from exc
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or port not in (None, 443)):
        raise ImportRefused(f"{item.url}: give the https URL the document was downloaded from")
    if parts.hostname.lower() not in source_hosts(source):
        raise ImportRefused(f"{item.url}: not a {source.name} URL ({', '.join(sorted(source_hosts(source)))})")
    if not item.path.is_file():
        raise ImportRefused(f"{item.path}: file not found")
    kind = FILE_KINDS.get(item.path.suffix.lower())
    if kind is None:
        raise ImportRefused(f"{item.path.name}: only PDF and HTML files can be imported")
    if item.path.stat().st_size > MAX_BYTES:
        raise ImportRefused(f"{item.path.name}: larger than {MAX_BYTES} bytes")
    body = item.path.read_bytes()
    if kind[0] == "pdf" and not body.startswith(b"%PDF"):
        raise ImportRefused(f"{item.path.name}: not a PDF file")
    for marker in source.connector_config.get("block_markers", []):
        if marker.encode() in body:
            raise ImportRefused(f"{item.path.name}: this is the site's block page, not the document")
    return FetchedPage(item.url, item.url, source, kind[0], kind[1], body, imported_at)


def import_files(
    conn: psycopg.Connection, workspace_id: UUID, user_id: UUID, source_key: str, items: list[ImportItem]
) -> list[ImportResult]:
    """Import ``items`` into ``source_key`` as ``user_id``; one result per item, failures included."""
    source = load_source(conn, workspace_id, source_key)
    started = datetime.now(UTC)
    with acting_as(conn, user_id):
        require_role(conn, workspace_id, IMPORT_ROLES)
        run_id = conn.execute(
            """insert into public.ingestion_runs
                 (workspace_id, source_id, status, mode, date_basis, idempotency_key, started_at, created_by)
               values (%s, %s, 'running', 'manual_upload', 'retrieval', %s, %s, %s) returning id""",
            (workspace_id, source.id, f"manual-{uuid.uuid4()}", started, user_id),
        ).fetchone()["id"]

    writer = EvidenceWriter(conn, workspace_id, user_id)
    results: list[ImportResult] = []
    for item in items:
        try:
            page = prepare_page(item, source, datetime.now(UTC))
            extracted = extract(page)
            if item.title:
                extracted.title = item.title
            if item.published:
                extracted.published = item.published
            saved = writer.save(page, extracted, {"import": "manual", "file_name": item.path.name,
                                                  "ingestion_run_id": str(run_id)})
            error = extracted.error if extracted.status in ("failed", "unsupported") else None
            results.append(ImportResult(item, "failed" if error else ("unchanged" if saved.unchanged else "saved"), saved.document_version_id,
                                        len(saved.passage_ids), error))
            document_id = saved.document_id
        except (ImportRefused, OSError) as exc:
            results.append(ImportResult(item, "failed", None, 0, str(exc)))
            document_id = None
        with acting_as(conn, user_id):
            conn.execute(
                """insert into public.ingestion_run_items
                     (workspace_id, run_id, source_item_key, item_url, status, document_id, attempt_count, error_message)
                   values (%s, %s, %s, %s, %s, %s, 1, %s)
                   on conflict (run_id, source_item_key) do nothing""",
                (workspace_id, run_id, f"{item.url}#{item.path.name}", item.url, results[-1].outcome, document_id,
                 results[-1].error),
            )

    counts = {"new": sum(r.outcome == "saved" for r in results), "updated": 0,
              "unchanged": sum(r.outcome == "unchanged" for r in results), "skipped": 0,
              "failed": sum(r.outcome == "failed" for r in results)}
    with acting_as(conn, user_id):
        conn.execute(
            """update public.ingestion_runs set status = %s, counts = %s, error_summary = %s, finished_at = now()
               where id = %s""",
            ("completed_with_errors" if counts["failed"] else "completed", Jsonb(counts),
             "; ".join(r.error for r in results if r.outcome == "failed") or None, run_id),
        )
    return results
