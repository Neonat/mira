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
import json
import os
import time as time_module
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from mira.config import REPO_ROOT
from mira.db import acting_as
from mira.extract import EXTRACTION_VERSION, Extracted, split_passages
from mira.fetch import FetchedPage
from mira.originals import PrivateOriginalStore, RetentionPolicy
from mira.store import SourceRecord

DOCUMENT_TYPES = {"regulator": "regulation", "website": "guidance", "rss": "news"}


@dataclass(frozen=True)
class SavedPage:
    document_id: UUID
    document_version_id: UUID
    passage_ids: list[UUID]
    unchanged: bool
    text_stored: bool


def evidence_identity(page: FetchedPage, extracted: Extracted, method: str = "http_fetch") -> dict[str, str]:
    capture = hashlib.sha256(page.body).hexdigest()
    extraction = hashlib.sha256(extracted.text.encode("utf-8")).hexdigest()
    material = json.dumps([capture, method, EXTRACTION_VERSION, extracted.status, extraction], separators=(",", ":"))
    return {"capture_sha256": capture, "extraction_sha256": extraction,
            "version_sha256": hashlib.sha256(material.encode()).hexdigest()}


class EvidenceWriter:
    def __init__(self, conn: psycopg.Connection, workspace_id: UUID, user_id: UUID,
                 originals: PrivateOriginalStore | None = None) -> None:
        self.conn = conn
        self.workspace_id = workspace_id
        self.user_id = user_id
        self._original_config_failed = False
        self.originals = originals
        if originals is None:
            try:
                self.originals = PrivateOriginalStore(
                    Path(os.environ.get("MIRA_ORIGINALS_DIR", str(REPO_ROOT / "private-originals"))),
                    RetentionPolicy.from_env())
            except (ValueError, OSError):
                # Retention configuration cannot prevent saving extracted text.
                self._original_config_failed = True

    def _retain_original(self, execute, page: FetchedPage, method: str,
                         capture_sha256: str) -> dict[str, object]:
        result: dict[str, object] = {"original_retained": False, "retained_original": None,
                                    "original_retention_status": "not_enabled"}
        if self._original_config_failed:
            return {**result, "original_retention_status": "failed"}
        if self.originals is None or not self.originals.policy.enabled:
            return result
        result["original_retention_status"] = "not_permitted"
        if method not in {"http_fetch", "manual_import"}:
            return result
        # Page/source records can outlive permission changes. Re-read the actual
        # workspace-bound source rather than trusting supplied connector grants.
        row = execute(
            """select id, name, source_type, base_url, jurisdiction_code,
                      permitted_operations, connector_config
               from public.sources where id = %s and workspace_id = %s and is_active""",
            (page.source.id, self.workspace_id),
        ).fetchone()
        if row is None:
            return result
        source = SourceRecord(row["id"], row["name"], row["source_type"], row["base_url"],
                              row["jurisdiction_code"], tuple(row["permitted_operations"]),
                              row["connector_config"] or {})
        try:
            retained = self.originals.retain(self.workspace_id, source, page.body,
                                             acquisition_method=method, content_type=page.content_type)
            if retained is None:
                return result
            if (retained.get("sha256") != capture_sha256
                    or retained.get("size_bytes") != len(page.body)
                    or retained.get("workspace_id") != str(self.workspace_id)):
                raise ValueError("Original identity does not match acquisition")
            return {"original_retained": True, "retained_original": retained,
                    "original_retention_status": "retained"}
        except Exception:
            # The pure storage boundary cannot roll back already permitted text.
            return {**result, "original_retention_status": "failed"}

    def save(self, page: FetchedPage, extracted: Extracted, provenance: dict[str, object] | None = None,
             *, deadline: float | None = None) -> SavedPage:
        """Save ``page``; ``provenance`` (for example a manual import) is kept in the version metadata."""
        ws, user = self.workspace_id, self.user_id
        source = page.source
        store_text = "store_text" in source.permitted_operations and extracted.status in ("complete", "partial")
        supplied_method = (provenance or {}).get("acquisition_method")
        method = (supplied_method if supplied_method in ("live_browser", "offline_browser") else
                  "manual_import" if (provenance or {}).get("import") == "manual" else "http_fetch")
        retention_method = method if supplied_method in (None, "http_fetch", "manual_import",
                                                         "live_browser", "offline_browser") else "unknown"
        if method == "live_browser":
            details=dict(provenance or {})
            details["capture_kind"]="rendered_dom"
            provenance={**details,"browser_context":{k:v for k,v in details.items()
                        if k not in {"acquisition_method","requested_url"}}}
        identity = evidence_identity(page, extracted, method)
        digest = identity["version_sha256"]
        def execute(query, params):
            if deadline is not None:
                for setting in ("statement_timeout", "lock_timeout"):
                    remaining = deadline - time_module.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("evidence save deadline reached")
                    self.conn.execute(f"SET LOCAL {setting} = {max(1, int(remaining * 1000))}", ())
                if deadline - time_module.monotonic() <= 0:
                    raise TimeoutError("evidence save deadline reached")
            return self.conn.execute(query, params)
        with acting_as(self.conn, user):
            original_metadata = self._retain_original(execute, page, retention_method, identity["capture_sha256"])
            document = execute(
                "select id from public.documents where workspace_id = %s and source_id = %s and canonical_url = %s",
                (ws, source.id, page.url),
            ).fetchone()
            if document is None:
                document = execute(
                    """insert into public.documents (workspace_id, source_id, document_type, canonical_url, title, created_by)
                       values (%s, %s, %s, %s, %s, %s) returning id""",
                    (ws, source.id, "other" if page.kind == "feed" else DOCUMENT_TYPES.get(source.source_type, "other"),
                     page.url, extracted.title[:500] or page.url, user),
                ).fetchone()
            document_id = document["id"]
            existing = execute(
                "select id from public.document_versions where document_id = %s and content_sha256 = %s",
                (document_id, digest),
            ).fetchone()
            if existing:
                if original_metadata["original_retained"]:
                    execute(
                        """update public.document_versions set metadata = metadata || %s
                           where id = %s and workspace_id = %s""",
                        (Jsonb(original_metadata), existing["id"], ws),
                    )
                if extracted.published and extracted.published_basis:
                    execute(
                        """update public.document_versions set published_at = %s,
                           metadata = metadata || %s where id = %s and workspace_id = %s
                           and published_at is null""",
                        (datetime.combine(extracted.published, time(), UTC),
                         Jsonb({"publication_date_evidence": extracted.published_basis}), existing["id"], ws),
                    )
                passages = execute(
                    "select id from public.document_passages where document_version_id = %s order by passage_number",
                    (existing["id"],),
                ).fetchall()
                return SavedPage(document_id, existing["id"], [row["id"] for row in passages], True, bool(passages))
            latest = execute(
                "select id, version_number from public.document_versions where document_id = %s order by version_number desc limit 1",
                (document_id,),
            ).fetchone()
            published = datetime.combine(extracted.published, time(), UTC) if extracted.published else None
            version_id = execute(
                """insert into public.document_versions
                     (workspace_id, document_id, version_number, content_sha256, source_url, title, published_at,
                      retrieved_at, extraction_status, extracted_text, extraction_version, metadata, supersedes_version_id)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (ws, document_id, (latest["version_number"] + 1) if latest else 1, digest, page.url,
                 extracted.title[:500] or page.url, published, page.fetched_at, extracted.status,
                 extracted.text if store_text else None, EXTRACTION_VERSION,
                 Jsonb({"content_type": page.content_type, "requested_url": page.requested_url, "kind": page.kind,
                        "text_stored": store_text, "links": len(extracted.links), "error": extracted.error,
                        "publication_date_evidence": extracted.published_basis,
                        **(provenance or {}), "acquisition_method": method,
                        "capture_sha256": identity["capture_sha256"], **original_metadata,
                        "extraction_sha256": identity["extraction_sha256"]}),
                 latest["id"] if latest else None),
            ).fetchone()["id"]
            passage_ids: list[UUID] = []
            if store_text:
                for span in split_passages(extracted):
                    passage_ids.append(execute(
                        """insert into public.document_passages
                             (workspace_id, document_version_id, passage_number, content, page_number, char_start,
                              char_end, extraction_version)
                           values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                        (ws, version_id, span.number, span.content, span.page_number, span.char_start, span.char_end,
                         EXTRACTION_VERSION),
                    ).fetchone()["id"])
        return SavedPage(document_id, version_id, passage_ids, False, store_text)
