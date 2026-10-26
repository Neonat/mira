"""Database access for the trusted orchestrator worker (PRD v2 §5.1).

The worker connects straight to Postgres with elevated rights, so row-level
security does not apply to it. Three rules make that safe:

1. Every write happens inside ``acting_as(conn, user_id)``. It sets the request
   claims for the transaction so ``auth.uid()`` returns the user who started the
   run, and the audit trigger records them as the actor.
2. Before a run starts, ``require_role`` checks that user's workspace role with
   the database's own ``private.has_workspace_role``.
3. Worker code fills actor columns (``created_by``, ``generated_by`` ...) with that
   user and filters every query by ``workspace_id`` itself.

Do not ``set role authenticated`` inside ``acting_as``: that turns RLS back on and
blocks the scouts from saving source documents. Never use this connection from
Streamlit or anything that runs in the browser.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

RUN_ROLES: tuple[str, ...] = ("admin", "analyst")


class NotAuthorisedError(PermissionError):
    """The initiating user lacks the workspace role for this operation."""


def connect(dsn: str | None = None) -> psycopg.Connection:
    """Open a worker connection. Transactions are explicit via ``acting_as``."""
    dsn = dsn or os.environ["MIRA_WORKER_DATABASE_URL"]
    return psycopg.connect(dsn, autocommit=True, row_factory=dict_row)


@contextmanager
def acting_as(conn: psycopg.Connection, user_id: UUID) -> Iterator[psycopg.Connection]:
    """Run one transaction on behalf of ``user_id``; commits on success, rolls back on error."""
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"})
    with conn.transaction():
        # auth.uid() reads request.jwt.claim.sub on some Supabase images and
        # request.jwt.claims on others, so set both, transaction-local.
        conn.execute(
            "select set_config('request.jwt.claim.sub', %s, true), set_config('request.jwt.claims', %s, true)",
            (str(user_id), claims),
        )
        yield conn


def require_role(conn: psycopg.Connection, workspace_id: UUID, roles: Sequence[str] = RUN_ROLES) -> None:
    """Raise unless the acting user holds one of ``roles``. Call inside ``acting_as``."""
    row = conn.execute(
        "select private.has_workspace_role(%s, %s::text[]) as allowed",
        (workspace_id, list(roles)),
    ).fetchone()
    if not row or not row["allowed"]:
        raise NotAuthorisedError(f"user lacks one of {list(roles)} in workspace {workspace_id}")
