"""Private original bytes, separate from extracted text and browser captures.

Callers must validate the current source is active and authorized in the workspace
before retaining, and authenticate workspace/role/source permissions before reads.
This adapter has no database, provider, network or public URL behavior.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4

from mira.store import SourceRecord


def original_identity(metadata: Mapping | None) -> Mapping | None:
    """Get the retained object, including exact bytes recovered after ingestion."""
    if not isinstance(metadata, Mapping):
        return None
    if metadata.get('original_retained') is True:
        identity = metadata.get('retained_original')
        return identity if isinstance(identity, Mapping) else None
    recovery = metadata.get('recovered_original')
    identity = recovery.get('identity') if isinstance(recovery, Mapping) else None
    digest = metadata.get('capture_sha256')
    if isinstance(identity, Mapping) and isinstance(digest, str) and identity.get('sha256') == digest:
        return identity
    return None


@dataclass(frozen=True)
class RetentionPolicy:
    enabled: bool = False
    max_bytes: int = 20_000_000

    def __post_init__(self):
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError('Original byte limit must be a positive integer')

    @classmethod
    def from_env(cls) -> RetentionPolicy:
        return cls(
            enabled=os.environ.get('MIRA_RETAIN_ORIGINALS', '').strip().lower()
            in {'1', 'true', 'yes', 'on'},
            max_bytes=int(os.environ.get('MIRA_ORIGINAL_MAX_BYTES', '20000000')),
        )


class PrivateOriginalStore:
    def __init__(self, root: Path, policy: RetentionPolicy):
        self.root = Path(root).absolute()
        if '..' in self.root.parts or self.root == Path(self.root.anchor):
            raise ValueError('Original root must be a dedicated directory')
        self.policy = policy

    @staticmethod
    def _workspace(workspace_id: UUID) -> str:
        if not isinstance(workspace_id, UUID):
            raise ValueError('Workspace must be a UUID')
        return str(workspace_id)

    @contextmanager
    def _directory(self, workspace: str, *, create: bool):
        # Walk every component with dirfds and O_NOFOLLOW: resolving a Path first
        # would silently accept a symlink root or ancestor. Descendant operations
        # stay relative to the opened directory, including atomic publication.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root.anchor, flags)
        try:
            parts = self.root.parts[1:] + (workspace,)
            for index, part in enumerate(parts):
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                if index >= len(parts) - 2:
                    if create:
                        os.fchmod(fd, 0o700)
                    elif stat.S_IMODE(os.fstat(fd).st_mode) & 0o077:
                        raise ValueError('Original directory is not private')
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def _load(fd: int, filename: str, digest: str, size: int) -> bytes:
        file_fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=fd)
        with os.fdopen(file_fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != size:
                raise ValueError('Original file type or size mismatch')
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError('Original file is not private')
            body = stream.read(size + 1)
        if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
            raise ValueError('Original digest or size mismatch')
        return body

    def retain(self, workspace_id: UUID, source: SourceRecord, body: bytes, *,
               acquisition_method: str, content_type: str) -> dict | None:
        if not isinstance(source.connector_config, Mapping):
            return None
        grant = source.connector_config.get('original_retention')
        if (not self.policy.enabled or 'store_text' not in source.permitted_operations
                or acquisition_method not in {'http_fetch', 'manual_import'}
                or not isinstance(grant, Mapping) or grant.get('approved') is not True
                or not isinstance(grant.get('reference'), str)
                or not grant['reference'].strip()):
            return None
        workspace = self._workspace(workspace_id)
        if not isinstance(body, bytes):
            raise ValueError('Original body must be bytes')
        if len(body) > self.policy.max_bytes:
            raise ValueError('Original exceeds byte limit')
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError('Original media type is required')
        digest = hashlib.sha256(body).hexdigest()
        filename = digest + '.bin'
        with self._directory(workspace, create=True) as fd:
            try:
                self._load(fd, filename, digest, len(body))
            except FileNotFoundError:
                temporary = '.' + uuid4().hex + '.tmp'
                temp_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                  | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                try:
                    with os.fdopen(temp_fd, 'wb') as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        stream.write(body)
                        stream.flush()
                        os.fsync(stream.fileno())
                    try:
                        # Hard-link publication is atomic and never replaces an
                        # existing object, unlike rename/replace.
                        os.link(temporary, filename, src_dir_fd=fd, dst_dir_fd=fd,
                                follow_symlinks=False)
                    except FileExistsError:
                        pass
                finally:
                    os.unlink(temporary, dir_fd=fd)
                self._load(fd, filename, digest, len(body))
                os.fsync(fd)
        return {'sha256': digest, 'size_bytes': len(body), 'media_type': content_type,
                'approval_reference': grant['reference'], 'storage_kind': 'private_local',
                'workspace_id': workspace}

    def read(self, workspace_id: UUID, identity: Mapping) -> bytes:
        workspace = self._workspace(workspace_id)
        digest, size = identity.get('sha256'), identity.get('size_bytes')
        if (identity.get('workspace_id') != workspace
                or identity.get('storage_kind') != 'private_local'
                or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None
                or type(size) is not int or not 0 <= size <= self.policy.max_bytes):
            raise ValueError('Invalid original identity or workspace')
        with self._directory(workspace, create=False) as fd:
            return self._load(fd, digest + '.bin', digest, size)
