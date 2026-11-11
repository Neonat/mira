"""Operator-only byte bridge for full-database evidence recovery.

The coordinator owns the consistent read-only PostgreSQL snapshot and complete
native dump. This inventory is only its external-byte complement. It is not an
application read route, source authorization mechanism, or acquisition workflow.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from uuid import UUID, uuid4

from mira.originals import PrivateOriginalStore, RetentionPolicy, original_identity
from mira.private_objects import ObjectIdentity, PrivateObjectStore

_MAX_BYTES = 20_000_000
_BASE_FIELDS = {'workspace_id', 'purpose', 'sha256', 'size_bytes', 'media_type', 'storage_kind'}
_REPORT_PATH = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/(report-v[1-9][0-9]*(?:-reviewed)?\.html)\Z')


def _workspace(value):
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            parsed = UUID(value)
            if str(parsed) == value:
                return parsed
        except ValueError:
            pass
    raise ValueError('Invalid archive workspace')


def _path(relative):
    match = _REPORT_PATH.fullmatch(relative) if isinstance(relative, str) else None
    if match is None or str(_workspace(match[1])) != match[1]:
        raise ValueError('Invalid archive report path')
    return match[1], match[2]


def _verify(identity, body):
    if (type(body) is not bytes or len(body) != identity['size_bytes']
            or sha256(body).hexdigest() != identity['sha256']):
        raise ValueError('Archive object integrity mismatch')
    return body


class ArchiveObjects:
    def __init__(self, local_originals: PrivateOriginalStore, reports_dir: Path,
                 objects: PrivateObjectStore | None = None):
        self.local_originals = local_originals
        self.reports_dir = Path(reports_dir).absolute()
        self.objects = objects
        # Reuse the existing dirfd-based private publication root walker.
        self._reports = PrivateOriginalStore(self.reports_dir, RetentionPolicy(max_bytes=_MAX_BYTES))

    def _identity(self, value):
        if not isinstance(value, Mapping) or not _BASE_FIELDS <= value.keys():
            raise ValueError('Invalid archive object identity')
        item = dict(value)
        kind, purpose = item['storage_kind'], item['purpose']
        allowed = set(_BASE_FIELDS)
        if kind == 'private_supabase':
            allowed.add('bucket')
            if 'bucket' not in item:
                raise ValueError('Missing archive bucket')
        elif kind != 'private_local':
            raise ValueError('Invalid archive backend')
        if purpose == 'original':
            allowed.add('approval_reference')
        elif purpose == 'report' and kind == 'private_local':
            allowed.add('relative_path')
            if 'relative_path' not in item:
                raise ValueError('Missing archive report path')
            _path(item['relative_path'])
        if item.keys() - allowed:
            raise ValueError('Unexpected archive identity fields')
        if 'approval_reference' in item and (not isinstance(item['approval_reference'], str)
                or not item['approval_reference'].strip() or len(item['approval_reference']) > 2048
                or '\x00' in item['approval_reference']):
            raise ValueError('Invalid archive approval reference')
        # Reuse strict shared UUID/digest/purpose/size/MIME validation, substituting
        # only the known local backend for the common immutable fields.
        ObjectIdentity(item['workspace_id'], purpose, item['sha256'], item['size_bytes'],
                       item['media_type'], bucket=item.get('bucket', 'mira-evidence-private'))
        if not isinstance(item['workspace_id'], str):
            raise ValueError('Archive workspace must be a canonical string')
        limit = self.local_originals.policy.max_bytes if purpose == 'original' and kind == 'private_local' else _MAX_BYTES
        if item['size_bytes'] > limit:
            raise ValueError('Archive object exceeds byte limit')
        return item

    @staticmethod
    def _core(item):
        return {k: v for k, v in item.items() if k != 'approval_reference'}

    def _report_bytes(self, relative):
        run, name = _path(relative)
        # Legacy reports may have ordinary 0644/0755 modes. Read the exact saved
        # bytes without resolving symlinks, while new recovery writes are private.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.reports_dir.anchor, flags)
        try:
            for part in self.reports_dir.parts[1:] + (run,):
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return self._report_load(fd, name)
        finally:
            os.close(fd)

    @staticmethod
    def _report_load(fd, name):
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_BYTES:
                raise ValueError('Invalid archive report file')
            body = stream.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise ValueError('Archive report exceeds byte limit')
        return body

    def collect(self, conn) -> list[dict]:
        """Inventory all workspaces within the caller's consistent DB snapshot."""
        found = {}

        def add(value):
            item = self._identity(value)
            key = (item['workspace_id'], item['purpose'], item['sha256'], item.get('relative_path'))
            previous = found.get(key)
            if previous is not None and self._core(previous) != self._core(item):
                raise ValueError('Conflicting archive object bindings')
            found.setdefault(key, item)

        originals = conn.execute("""select workspace_id, metadata from public.document_versions
            where metadata->'original_retained' = 'true'::jsonb or metadata ? 'recovered_original'""").fetchall()
        for row in originals:
            metadata = row['metadata']
            value = original_identity(metadata)
            if not isinstance(value, Mapping):
                raise ValueError('Malformed retained original metadata')
            value = dict(value)
            if value.get('storage_kind') == 'private_local' and 'purpose' not in value:
                value['purpose'] = 'original'
            item = self._identity(value)
            if item['purpose'] != 'original' or item['workspace_id'] != str(_workspace(row['workspace_id'])):
                raise ValueError('Invalid retained original workspace binding')
            add(item)

        reports = conn.execute("""select r.workspace_id, r.id as report_id,
            a.analysis_run_id, r.report_version, r.review_status, r.artifact_storage_path,
            p.state, p.content_sha256, p.object_identity
            from public.reports r
            join public.analysis_revisions a on a.id=r.analysis_revision_id and a.workspace_id=r.workspace_id
            left join public.report_artifacts p on p.report_id=r.id and p.workspace_id=r.workspace_id""").fetchall()
        for row in reports:
            ws = str(_workspace(row['workspace_id']))
            state, pending_hash = row['state'], row['content_sha256']
            if state not in (None, 'pending', 'failed', 'ready'):
                raise ValueError('Invalid archive publication state')
            if pending_hash is not None and (not isinstance(pending_hash, str) or not re.fullmatch('[0-9a-f]{64}', pending_hash)):
                raise ValueError('Invalid archive publication digest')
            if state == 'ready':
                item = self._identity(row['object_identity'])
                if (item['workspace_id'] != ws or item['purpose'] != 'report'
                        or item['storage_kind'] != 'private_supabase' or item['sha256'] != pending_hash):
                    raise ValueError('Invalid ready report object binding')
                add(item)
                continue
            if row['object_identity'] is not None:
                raise ValueError('Unexpected unpublished object binding')
            relative = row['artifact_storage_path']
            if relative is None:
                continue  # Snapshot remains in the full DB dump; not rendered yet.
            run = str(_workspace(row['analysis_run_id']))
            version = row['report_version']
            if type(version) is not int or version <= 0 or row['review_status'] not in ('draft', 'reviewed'):
                raise ValueError('Invalid archive report binding')
            expected = f"{run}/report-v{version}{'-reviewed' if row['review_status'] == 'reviewed' else ''}.html"
            if relative != expected:
                raise ValueError('Invalid archive report path binding')
            body = self._report_bytes(relative)
            checksum = sha256(body).hexdigest()
            if pending_hash is not None and checksum != pending_hash:
                raise ValueError('Pending report content changed')
            add(dict(workspace_id=ws, purpose='report', sha256=checksum,
                     size_bytes=len(body), media_type='text/html; charset=utf-8',
                     storage_kind='private_local', relative_path=relative))
        return list(found.values())

    def read(self, identity) -> bytes:
        item = self._identity(identity)
        ws = _workspace(item['workspace_id'])
        if item['storage_kind'] == 'private_supabase':
            if self.objects is None:
                raise ValueError('Private remote storage is unavailable')
            body = self.objects.read(ws, self._core(item))
        elif item['purpose'] == 'original':
            body = self.local_originals.read(ws, item)
        else:
            body = self._report_bytes(item['relative_path'])
        return _verify(item, body)

    def write(self, identity, body) -> None:
        item = self._identity(identity)
        _verify(item, body)
        if item['storage_kind'] == 'private_supabase':
            if self.objects is None:
                raise ValueError('Private remote storage is unavailable')
            ws = _workspace(item['workspace_id'])
            created = self.objects.put(ws, item['purpose'], body, item['media_type'])
            if created != self._core(item):
                raise ValueError('Restored remote identity differs')
            self.read(item)
            return
        if item['purpose'] == 'original':
            store, directory, name = self.local_originals, item['workspace_id'], item['sha256'] + '.bin'
            load = lambda fd: store._load(fd, name, item['sha256'], item['size_bytes'])
        else:
            directory, name = _path(item['relative_path'])
            store = self._reports
            load = lambda fd: _verify(item, self._report_load(fd, name))
        with store._directory(directory, create=True) as fd:
            try:
                load(fd)
                return
            except FileNotFoundError:
                pass
            temporary = '.' + uuid4().hex + '.tmp'
            file_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              0o600, dir_fd=fd)
            try:
                with os.fdopen(file_fd, 'wb') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                except FileExistsError:
                    pass
                load(fd)
                os.fsync(fd)
            finally:
                os.unlink(temporary, dir_fd=fd)
