"""Private portable evidence packages, with no database/provider dependencies.

Callers supply a consistent native PostgreSQL dump and immutable object readers.
Restore writers must verify existing immutable identities idempotently. External
object writes and database restore are not a transaction; use a fresh recovery
DB and keep the package exclusively owned throughout restore.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from uuid import UUID

MAX_DATABASE_BYTES = 2 * 1024**3
MAX_OBJECT_BYTES = 20 * 1024**2
MAX_OBJECTS = 100_000
MAX_MANIFEST_BYTES = 8 * 1024**2
_CHUNK = 1024**2


class BackupError(ValueError):
    """Safe, input-free package error."""


class BackupValidationError(BackupError):
    """Package/input validation failed before publication or restoration."""


class BackupRestoreError(BackupError):
    """A restore callback failed; earlier object writes may remain."""


def _invalid():
    raise BackupValidationError('Invalid or incomplete backup package')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _identity(value, max_bytes):
    required = {'workspace_id', 'purpose', 'sha256', 'size_bytes', 'media_type', 'storage_kind'}
    if (not isinstance(value, dict) or not required <= value.keys()
            or value.keys() - required - {'approval_reference', 'bucket', 'relative_path'}):
        _invalid()
    try:
        if str(UUID(value['workspace_id'])) != value['workspace_id']:
            _invalid()
    except (ValueError, TypeError, AttributeError):
        _invalid()
    if (value['purpose'] not in ('original', 'report')
            or value['storage_kind'] not in ('private_local', 'private_supabase')
            or not isinstance(value['sha256'], str)
            or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None
            or type(value['size_bytes']) is not int
            or not 0 <= value['size_bytes'] <= max_bytes):
        _invalid()
    for key in ('media_type', 'approval_reference', 'bucket'):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()
                             or len(value[key]) > 2048 or '\x00' in value[key]):
            _invalid()
    if 'relative_path' in value:
        relative = value['relative_path']
        if (value['purpose'] != 'report' or value['storage_kind'] != 'private_local'
                or not isinstance(relative, str)
                or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/report-v[1-9][0-9]*(-reviewed)?\.html', relative) is None):
            _invalid()
    return dict(value)


@dataclass(frozen=True)
class BackupObject:
    identity: dict

    def __post_init__(self):
        object.__setattr__(self, 'identity', _identity(self.identity, MAX_OBJECT_BYTES))


@contextmanager
def _directory(path):
    """Open every absolute component without following any symlink."""
    path = Path(path)
    if '..' in path.parts:
        _invalid()
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _file(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _invalid()
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)


def _read(directory_fd, name, limit):
    with _file(directory_fd, name) as stream:
        if os.fstat(stream.fileno()).st_size > limit:
            _invalid()
        value = stream.read(limit + 1)
        if len(value) > limit:
            _invalid()
        return value


def _hash(directory_fd, name, limit):
    digest = hashlib.sha256()
    size = 0
    with _file(directory_fd, name) as stream:
        if os.fstat(stream.fileno()).st_size > limit:
            _invalid()
        while body := stream.read(min(_CHUNK, limit - size + 1)):
            size += len(body)
            if size > limit:
                _invalid()
            digest.update(body)
    return digest.hexdigest(), size


def _names(directory_fd, limit):
    names = set()
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > limit:
                _invalid()
    return names


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _limits(*values):
    if any(type(value) is not int or value < 0 for value in values):
        _invalid()


def verify_backup(path: Path, *, max_database_bytes: int = MAX_DATABASE_BYTES,
                  max_object_bytes: int = MAX_OBJECT_BYTES,
                  max_objects: int = MAX_OBJECTS) -> dict:
    """Boundedly verify the complete package without executing any callbacks."""
    try:
        _limits(max_database_bytes, max_object_bytes, max_objects)
        with _directory(path) as root:
            if _names(root, 4) != {'database.dump', 'manifest.json', 'objects', '.complete'}:
                _invalid()
            raw = _read(root, 'manifest.json', MAX_MANIFEST_BYTES)
            manifest = json.loads(raw, object_pairs_hook=_unique_json)
            if (not isinstance(manifest, dict)
                    or set(manifest) != {'schema_version', 'database', 'objects'}
                    or type(manifest['schema_version']) is not int
                    or manifest['schema_version'] != 1 or raw != _canonical(manifest)
                    or _read(root, '.complete', 65) != hashlib.sha256(raw).hexdigest().encode() + b'\n'):
                _invalid()
            database = manifest['database']
            if (not isinstance(database, dict) or set(database) != {'file', 'sha256', 'size_bytes'}
                    or database['file'] != 'database.dump'
                    or type(database['size_bytes']) is not int
                    or not 0 <= database['size_bytes'] <= max_database_bytes
                    or _hash(root, 'database.dump', max_database_bytes)
                    != (database['sha256'], database['size_bytes'])):
                _invalid()
            entries = manifest['objects']
            if not isinstance(entries, list) or len(entries) > max_objects:
                _invalid()
            seen, files = set(), set()
            with _directory_child(root, 'objects') as objects_fd:
                for entry in entries:
                    if not isinstance(entry, dict) or set(entry) != {'identity', 'file'}:
                        _invalid()
                    item = _identity(entry['identity'], max_object_bytes)
                    logical_key = (item['workspace_id'], item['purpose'], item['sha256'], item.get('relative_path'))
                    if logical_key in seen or entry['file'] != 'objects/' + item['sha256'] + '.bin':
                        _invalid()
                    seen.add(logical_key)
                    name = item['sha256'] + '.bin'
                    if _hash(objects_fd, name, max_object_bytes) != (item['sha256'], item['size_bytes']):
                        _invalid()
                    files.add(name)
                if _names(objects_fd, max_objects) != files:
                    _invalid()
            return manifest
    except BackupError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise BackupValidationError('Invalid or incomplete backup package') from None


@contextmanager
def _directory_child(parent_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        yield fd
    finally:
        os.close(fd)


def _write(path, body):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(parent_fd, source, destination):
    """Native atomic directory rename that refuses even an empty destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renameatx_np
        flags = 4  # RENAME_EXCL
    elif sys.platform.startswith('linux'):
        rename = libc.renameat2
        flags = 1  # RENAME_NOREPLACE
    else:
        _invalid()
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), flags) != 0:
        raise OSError(ctypes.get_errno(), 'Backup publication failed')


def create_backup(destination: Path, database_dump: Path, objects: Sequence[dict],
                  read_object: Callable[[dict], bytes], *,
                  max_database_bytes: int = MAX_DATABASE_BYTES,
                  max_object_bytes: int = MAX_OBJECT_BYTES,
                  max_objects: int = MAX_OBJECTS) -> dict:
    """Publish a new private package only after verifying every copied member."""
    staging = None
    try:
        _limits(max_database_bytes, max_object_bytes, max_objects)
        destination, database_dump = Path(destination).absolute(), Path(database_dump).absolute()
        if len(objects) > max_objects:
            _invalid()
        with _directory(destination.parent) as parent_fd:
            try:
                os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _invalid()
            staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '.', dir=destination.parent))
            os.chmod(staging, 0o700)
            (staging / 'objects').mkdir(mode=0o700)
            fd = os.open(staging / 'database.dump', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as target, _directory(database_dump.parent) as dump_parent:
                os.fchmod(target.fileno(), 0o600)
                with _file(dump_parent, database_dump.name) as source:
                    size, digest = 0, hashlib.sha256()
                    if os.fstat(source.fileno()).st_size > max_database_bytes:
                        _invalid()
                    while body := source.read(min(_CHUNK, max_database_bytes - size + 1)):
                        size += len(body)
                        if size > max_database_bytes:
                            _invalid()
                        digest.update(body)
                        target.write(body)
                target.flush()
                os.fsync(target.fileno())
            manifest = {'schema_version': 1, 'database': {
                'file': 'database.dump', 'sha256': digest.hexdigest(), 'size_bytes': size}, 'objects': []}
            for value in objects:
                item = _identity(value, max_object_bytes)
                body = read_object(dict(item))
                if (not isinstance(body, bytes) or len(body) != item['size_bytes']
                        or hashlib.sha256(body).hexdigest() != item['sha256']):
                    _invalid()
                relative = 'objects/' + item['sha256'] + '.bin'
                if not (staging / relative).exists():
                    _write(staging / relative, body)
                manifest['objects'].append({'identity': item, 'file': relative})
            raw = _canonical(manifest)
            if len(raw) > MAX_MANIFEST_BYTES:
                _invalid()
            _write(staging / 'manifest.json', raw)
            _write(staging / '.complete', hashlib.sha256(raw).hexdigest().encode() + b'\n')
            verify_backup(staging, max_database_bytes=max_database_bytes,
                          max_object_bytes=max_object_bytes, max_objects=max_objects)
            with _directory(staging / 'objects') as objects_fd:
                os.fsync(objects_fd)
            with _directory(staging) as staging_fd:
                os.fsync(staging_fd)
            _publish(parent_fd, staging.name, destination.name)
            staging = None
            os.fsync(parent_fd)
            return manifest
    except BackupError:
        raise
    except Exception:
        raise BackupValidationError('Backup creation failed') from None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def restore_backup(path: Path, *, write_object: Callable[[dict, bytes], None],
                   restore_database: Callable[[Path], None]) -> None:
    """Verify all bytes first, restore objects, then call the DB publisher once.

    The caller owns the fresh-local-target guard, consistent dump creation,
    exclusive package access and idempotent immutable object writes.
    """
    manifest = verify_backup(path)
    try:
        with _directory(path) as root, _directory_child(root, 'objects') as objects_fd:
            for entry in manifest['objects']:
                item = entry['identity']
                body = _read(objects_fd, item['sha256'] + '.bin', MAX_OBJECT_BYTES)
                if len(body) != item['size_bytes'] or hashlib.sha256(body).hexdigest() != item['sha256']:
                    _invalid()
                write_object(dict(item), body)
        restore_database(Path(path) / 'database.dump')
    except BackupError:
        raise
    except Exception:
        raise BackupRestoreError('Backup restore callback failed') from None
