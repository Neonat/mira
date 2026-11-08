"""Immutable objects in the reserved private Supabase bucket.

Callers must enforce current source grants; workspace binding alone is not read
permission. Database/storage RLS must independently enforce the same grants.
Credentials are inherited from the supplied SDK client, never manufactured here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256 as digest
import re
from time import monotonic
from typing import Literal
from uuid import UUID


BUCKET = 'mira-evidence-private'
_KIND = 'private_supabase'
_MEDIA = re.compile(r'[A-Za-z0-9!#$&^_.+\-]+/[A-Za-z0-9!#$&^_.+\-]+(?:;[ \t]*[A-Za-z0-9!#$&^_.+\-]+=(?:[A-Za-z0-9!#$&^_.+\-]+|"[A-Za-z0-9 ._+\-]+"))*\Z')


class PrivateObjectError(ValueError):
    """Secret-safe validation, transport or integrity failure."""


def _uuid(value):
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            result = UUID(value)
            if str(result) == value:
                return result
        except ValueError:
            pass
    raise PrivateObjectError('Invalid workspace identity')


@dataclass(frozen=True)
class ObjectIdentity:
    workspace_id: UUID
    purpose: Literal['original', 'report']
    sha256: str
    size_bytes: int
    media_type: str
    storage_kind: str = _KIND
    bucket: str = BUCKET

    def __post_init__(self):
        object.__setattr__(self, 'workspace_id', _uuid(self.workspace_id))
        if self.purpose not in ('original', 'report'):
            raise PrivateObjectError('Invalid object purpose')
        if not isinstance(self.sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.sha256):
            raise PrivateObjectError('Invalid object digest')
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise PrivateObjectError('Invalid object size')
        if not isinstance(self.media_type, str) or len(self.media_type) > 255 or not _MEDIA.fullmatch(self.media_type):
            raise PrivateObjectError('Invalid media type')
        if self.storage_kind != _KIND or self.bucket != BUCKET:
            raise PrivateObjectError('Invalid storage identity')

    @property
    def object_key(self) -> str:
        return f'{self.workspace_id}/{self.purpose}/{self.sha256}.bin'

    def to_dict(self) -> dict:
        return {
            'workspace_id': str(self.workspace_id), 'purpose': self.purpose,
            'sha256': self.sha256, 'size_bytes': self.size_bytes,
            'media_type': self.media_type, 'storage_kind': self.storage_kind,
            'bucket': self.bucket,
        }


class PrivateObjectStore:
    """Use a worker client for uploads, a normal signed-in client for app reads.

    The streaming boundary uses storage3's bucket proxy internals because its
    download() eagerly buffers. Unsupported SDK shapes fail closed. No redirect
    is followed, and no URL or provider exception is exposed to the caller.
    """

    def __init__(self, client, bucket=BUCKET, max_bytes=20_000_000):
        if bucket != BUCKET:
            raise PrivateObjectError('Only the reserved private bucket is allowed')
        if type(max_bytes) is not int or max_bytes <= 0:
            raise PrivateObjectError('Invalid object byte limit')
        self._client = client
        self._bucket = bucket
        self._max_bytes = max_bytes
        self._private_checked = False

    def _identity(self, ws, value):
        if not isinstance(value, Mapping) or set(value) != {
            'workspace_id', 'purpose', 'sha256', 'size_bytes',
            'media_type', 'storage_kind', 'bucket',
        }:
            raise PrivateObjectError('Invalid object identity fields')
        item = ObjectIdentity(**value)
        if item.workspace_id != _uuid(ws):
            raise PrivateObjectError('Object belongs to another workspace')
        if item.size_bytes > self._max_bytes:
            raise PrivateObjectError('Object exceeds byte limit')
        return item

    def _confirm_private(self):
        if self._private_checked:
            return
        try:
            bucket = self._client.storage.get_bucket(self._bucket)
            public = bucket.get('public') if isinstance(bucket, Mapping) else bucket.public
            valid = public is False
        except Exception:
            valid = False
        if not valid:
            raise PrivateObjectError('Private bucket configuration unavailable')
        self._private_checked = True

    def put(self, ws, purpose, body: bytes, media_type) -> dict:
        if type(body) is not bytes or len(body) > self._max_bytes:
            raise PrivateObjectError('Invalid object body or byte limit')
        item = ObjectIdentity(_uuid(ws), purpose, digest(body).hexdigest(), len(body), media_type)
        self._confirm_private()
        failed = False
        try:
            self._client.storage.from_(self._bucket).upload(
                item.object_key, body,
                file_options={'content-type': item.media_type, 'upsert': 'false'},
            )
        except Exception as exc:
            # storage3 exposes status as int or str across supported releases.
            # Only a conflict may represent an immutable idempotent retry.
            status = str(getattr(exc, 'status', getattr(exc, 'status_code', '')))
            duplicate = status == '409' or (status == '400' and getattr(exc, 'code', '') in ('Duplicate', 'ResourceAlreadyExists'))
            failed = not duplicate
        if failed:
            raise PrivateObjectError('Private object upload failed')
        self.read(ws, item.to_dict())
        return item.to_dict()

    def read(self, ws, identity: Mapping) -> bytes:
        item = self._identity(ws, identity)
        failed = False
        body = None
        try:
            proxy = self._client.storage.from_(self._bucket)
            url = str(proxy._base_url.joinpath('object', self._bucket, *item.object_key.split('/')))
            headers = dict(proxy._headers)
            headers['Accept-Encoding'] = 'identity'
            deadline = monotonic() + 30.0
            with proxy._client.stream('GET', url, headers=headers, timeout=10.0, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise PrivateObjectError('Private object unavailable')
                encoding = response.headers.get('content-encoding', 'identity').lower()
                length = response.headers.get('content-length')
                if encoding != 'identity' or (length is not None and (not length.isascii() or not length.isdigit() or int(length) != item.size_bytes)):
                    raise PrivateObjectError('Invalid object response metadata')
                chunks = bytearray()
                # Keep native transport chunks so slow trickles cannot postpone
                # the elapsed-time check while HTTPX aggregates a larger chunk.
                for chunk in response.iter_raw():
                    if monotonic() > deadline or len(chunks) + len(chunk) > item.size_bytes:
                        raise PrivateObjectError('Object read limit exceeded')
                    chunks.extend(chunk)
                if monotonic() > deadline or len(chunks) != item.size_bytes or digest(chunks).hexdigest() != item.sha256:
                    raise PrivateObjectError('Object integrity check failed')
                body = bytes(chunks)
        except Exception:
            failed = True
        if failed:
            raise PrivateObjectError('Private object read failed integrity or transport checks')
        return body
