"""Saves fetched pages to the evidence store before any agent reads them (PRD v2 §5.1 principle 4).

Every fetched page, listing pages and feeds included, becomes a ``documents`` row
and a content-hashed ``document_versions`` row. Passages are stored only when the
source permits ``store_text`` (risk G7); otherwise the version keeps metadata and
the page cannot be cited. An unchanged page reuses its existing version.

Each scout thread uses its own connection and writes inside ``acting_as`` for the
user who started the run. Manual imports (``mira.manual_import``) use the same
writer, so a document downloaded by hand is stored exactly like a fetched one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, time
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from mira.db import acting_as
from mira.extract import EXTRACTION_VERSION, Extracted, split_passages
from mira.fetch import FetchedPage

DOCUMENT_TYPES = {"regulator": "regulation", "website": "guidance", "rss": "news"}


@dataclass(frozen=True)
class SavedPage:
    document_id: UUID
    document_version_id: UUID
    passage_ids: list[UUID]
    unchanged: bool
    text_stored: bool


class EvidenceWriter:
    def __init__(self, conn: psycopg.Connection, workspace_id: UUID, user_id: UUID) -> None:
        self.conn = conn
        self.workspace_id = workspace_id
        self.user_id = user_id

    def save(self, page: FetchedPage, extracted: Extracted, provenance: dict[str, object] | None = None) -> SavedPage:
        """Save ``page``; ``provenance`` (for example a manual import) is kept in the version metadata."""
        ws, user = self.workspace_id, self.user_id
        source = page.source
        store_text = "store_text" in source.permitted_operations and extracted.status in ("complete", "partial")
        digest = hashlib.sha256(page.body).hexdigest()
        with acting_as(self.conn, user):
            document = self.conn.execute(
                "select id from public.documents where workspace_id = %s and source_id = %s and canonical_url = %s",
                (ws, source.id, page.url),
            ).fetchone()
            if document is None:
                document = self.conn.execute(
                    """insert into public.documents (workspace_id, source_id, document_type, canonical_url, title, created_by)
                       values (%s, %s, %s, %s, %s, %s) returning id""",
                    (ws, source.id, "other" if page.kind == "feed" else DOCUMENT_TYPES.get(source.source_type, "other"),
                     page.url, extracted.title[:500] or page.url, user),
                ).fetchone()
            document_id = document["id"]
            existing = self.conn.execute(
                "select id from public.document_versions where document_id = %s and content_sha256 = %s",
                (document_id, digest),
            ).fetchone()
            if existing:
                passages = self.conn.execute(
                    "select id from public.document_passages where document_version_id = %s order by passage_number",
                    (existing["id"],),
                ).fetchall()
                return SavedPage(document_id, existing["id"], [row["id"] for row in passages], True, bool(passages))
            latest = self.conn.execute(
                "select id, version_number from public.document_versions where document_id = %s order by version_number desc limit 1",
                (document_id,),
            ).fetchone()
            published = datetime.combine(extracted.published, time(), UTC) if extracted.published else None
            version_id = self.conn.execute(
                """insert into public.document_versions
                     (workspace_id, document_id, version_number, content_sha256, source_url, title, published_at,
                      retrieved_at, extraction_status, extracted_text, extraction_version, metadata, supersedes_version_id)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (ws, document_id, (latest["version_number"] + 1) if latest else 1, digest, page.url,
                 extracted.title[:500] or page.url, published, page.fetched_at, extracted.status,
                 extracted.text if store_text else None, EXTRACTION_VERSION,
                 Jsonb({"content_type": page.content_type, "requested_url": page.requested_url, "kind": page.kind,
                        "text_stored": store_text, "links": len(extracted.links), "error": extracted.error,
                        **(provenance or {})}),
                 latest["id"] if latest else None),
            ).fetchone()["id"]
            passage_ids: list[UUID] = []
            if store_text:
                for span in split_passages(extracted):
                    passage_ids.append(self.conn.execute(
                        """insert into public.document_passages
                             (workspace_id, document_version_id, passage_number, content, page_number, char_start,
                              char_end, extraction_version)
                           values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                        (ws, version_id, span.number, span.content, span.page_number, span.char_start, span.char_end,
                         EXTRACTION_VERSION),
                    ).fetchone()["id"])
        return SavedPage(document_id, version_id, passage_ids, False, store_text)
