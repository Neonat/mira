"""Authenticated, current-permission reads of privately retained original bytes.

Pass the signed-in application's Supabase client. Never pass a privileged worker
connection or a service-role client; row visibility here must be governed by RLS.
The caller supplies only workspace/version IDs, never a storage path or identity.
"""
from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from mira.originals import PrivateOriginalStore, original_identity


_ROLES = {'admin', 'analyst', 'curator', 'reviewer', 'viewer'}


def _row(client, table: str, fields: str, **filters) -> Mapping:
    query = client.table(table).select(fields)
    for key, value in filters.items():
        query = query.eq(key, str(value))
    rows = query.execute().data
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise PermissionError('Original is unavailable')
    return rows[0]


def read_original(client, workspace_id: UUID, version_id: UUID,
                  store: PrivateOriginalStore, *, expected_identity: Mapping | None = None) -> bytes:
    """Read a visible version's original only under the current source approval."""
    try:
        if not isinstance(workspace_id, UUID) or not isinstance(version_id, UUID):
            raise PermissionError('Original is unavailable')
        auth = getattr(client, 'auth', None)
        get_user = getattr(auth, 'get_user', None)
        if not callable(get_user):
            raise PermissionError('Sign in to access originals')
        user = getattr(get_user(), 'user', None)
        user_id = getattr(user, 'id', None)
        if not user_id:
            raise PermissionError('Sign in to access originals')
        member = _row(client, 'workspace_members', 'role', workspace_id=workspace_id, user_id=user_id)
        if member.get('role') not in _ROLES:
            raise PermissionError('Original is unavailable')
        version = _row(client, 'document_versions', 'document_id, metadata',
                       id=version_id, workspace_id=workspace_id)
        document = _row(client, 'documents', 'source_id',
                        id=version.get('document_id'), workspace_id=workspace_id)
        source = _row(client, 'sources', 'is_active, permitted_operations, connector_config',
                      id=document.get('source_id'), workspace_id=workspace_id)
        identity = original_identity(version.get('metadata'))
        # A frozen identity only narrows access. The database still selects the
        # object; callers cannot supply a different object/path for retrieval.
        if expected_identity is not None and identity != expected_identity:
            raise PermissionError('Original is unavailable')
        config = source.get('connector_config')
        grant = config.get('original_retention') if isinstance(config, Mapping) else None
        if (source.get('is_active') is not True
                or 'store_text' not in (source.get('permitted_operations') or [])
                or not isinstance(identity, Mapping) or not isinstance(grant, Mapping)
                or grant.get('approved') is not True
                or not isinstance(grant.get('reference'), str) or not grant['reference'].strip()
                or grant['reference'] != identity.get('approval_reference')):
            raise PermissionError('Original is unavailable')
        return store.read(workspace_id, identity)
    except Exception:
        # Query/auth/filesystem failures all fail closed without exposing local
        # paths, provider responses, credentials or identities in client errors.
        raise PermissionError('Original is unavailable') from None
