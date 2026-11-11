"""Offline private storage contract, using the installed SDK and HTTP transport."""
from hashlib import sha256
from email.parser import BytesParser
from email.policy import default
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from storage3._sync.client import SyncStorageClient

from mira.private_objects import ObjectIdentity, PrivateObjectStore, PrivateObjectError


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.consumed = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk

    def close(self):
        self.closed = True


class Backend:
    def __init__(self, public=False):
        self.public = public
        self.objects = {}
        self.requests = []
        self.download = None
        self.upload_error = None
        self.stream = None
        self.headers = {}
        self.client = SimpleNamespace(storage=SyncStorageClient(
            'https://storage.invalid/storage/v1/', {'Authorization': 'Bearer test-secret'},
            http_client=httpx.Client(transport=httpx.MockTransport(self.handle)),
        ))

    def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        if '/bucket/' in path:
            return httpx.Response(200, json={'id': 'mira-evidence-private', 'name': 'mira-evidence-private', 'public': self.public, 'created_at': '2026-01-01T00:00:00Z', 'updated_at': '2026-01-01T00:00:00Z', 'owner': 'test', 'file_size_limit': None, 'allowed_mime_types': None})
        if request.method == 'POST':
            if self.upload_error:
                return httpx.Response(self.upload_error, json={'message': 'SECRET provider response', 'error': 'Duplicate', 'statusCode': self.upload_error})
            multipart = BytesParser(policy=default).parsebytes(
                b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.content
            )
            self.uploaded_parts = list(multipart.iter_parts())
            self.objects[path] = next(part.get_payload(decode=True) for part in self.uploaded_parts if part.get_param('name', header='content-disposition') == 'file')
            return httpx.Response(200, json={'Key': path})
        if self.stream:
            return httpx.Response(200, headers=self.headers, stream=self.stream)
        body = self.download if self.download is not None else self.objects.get(path)
        if body is None:
            return httpx.Response(404, text='SECRET missing')
        return httpx.Response(200, stream=httpx.ByteStream(body), headers=self.headers)


def identity(ws, body=b'hello', purpose='original'):
    return ObjectIdentity(ws, purpose, sha256(body).hexdigest(), len(body), 'text/plain').to_dict()


def test_identity_is_derived_and_json_serializable():
    ws = uuid4()
    result = identity(ws)
    assert result['workspace_id'] == str(ws)
    assert ObjectIdentity(**result).object_key == f'{ws}/original/{sha256(b"hello").hexdigest()}.bin'
    assert ObjectIdentity(**identity(ws, purpose='report')).object_key.endswith('.bin')
    assert result['storage_kind'] == 'private_supabase'


def test_put_uploads_immutable_private_object_then_verifies():
    backend, ws = Backend(), uuid4()
    result = PrivateObjectStore(backend.client).put(ws, 'original', b'hello', 'text/plain')
    assert result == identity(ws)
    assert [r.method for r in backend.requests] == ['GET', 'POST', 'GET']
    assert backend.requests[1].headers['x-upsert'] == 'false'
    assert next(part.get_content_type() for part in backend.uploaded_parts if part.get_param('name', header='content-disposition') == 'file') == 'text/plain'
    assert all(r.headers['authorization'] == 'Bearer test-secret' for r in backend.requests)


def test_read_does_not_require_bucket_admin_metadata():
    backend, ws = Backend(), uuid4()
    backend.download = b'hello'
    assert PrivateObjectStore(backend.client).read(ws, identity(ws)) == b'hello'
    assert len(backend.requests) == 1
    assert '/object/mira-evidence-private/' in backend.requests[0].url.path


@pytest.mark.parametrize('public', [True, None])
def test_put_rejects_unconfirmed_private_bucket(public):
    backend = Backend(public)
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).put(uuid4(), 'report', b'hello', 'text/plain')
    assert len(backend.requests) == 1


def test_private_bucket_confirmation_is_instance_cached():
    backend, ws = Backend(), uuid4()
    store = PrivateObjectStore(backend.client)
    store.put(ws, 'report', b'hello', 'text/plain')
    store.put(ws, 'report', b'world', 'text/plain')
    assert len([r for r in backend.requests if '/bucket/' in r.url.path]) == 1


@pytest.mark.parametrize('change', [
    {'workspace_id': str(uuid4())}, {'purpose': '../report'}, {'sha256': 'A'*64},
    {'sha256': '../secret'}, {'size_bytes': -1}, {'size_bytes': True},
    {'media_type': 'text/plain\r\nAuthorization: secret'}, {'media_type': ''},
    {'bucket': 'public'}, {'object_key': '../secret'}, {'storage_kind': 'local'},
    {'url': 'https://evil.invalid'}, {'workspace_id': 'not-a-uuid'},
])
def test_invalid_identity_rejected_before_transport(change):
    backend, ws = Backend(), uuid4()
    value = identity(ws)
    value.update(change)
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).read(ws, value)
    assert backend.requests == []


@pytest.mark.parametrize('body', [b'jello', b'', b'hello!'])
def test_every_successful_upload_requires_exact_readback(body):
    backend = Backend()
    backend.download = body
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).put(uuid4(), 'report', b'hello', 'text/plain')


def test_duplicate_upload_accepts_only_matching_existing_bytes():
    backend, ws = Backend(), uuid4()
    backend.upload_error, backend.download = 409, b'hello'
    assert PrivateObjectStore(backend.client).put(ws, 'original', b'hello', 'text/plain') == identity(ws)
    backend.download = b'jello'
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).put(ws, 'original', b'hello', 'text/plain')


def test_non_duplicate_provider_failure_is_safe_and_not_accepted():
    backend = Backend()
    backend.upload_error, backend.download = 403, b'hello'
    with pytest.raises(PrivateObjectError) as exc:
        PrivateObjectStore(backend.client).put(uuid4(), 'original', b'hello', 'text/plain')
    assert 'SECRET' not in str(exc.value)
    assert exc.value.__cause__ is None
    assert [r.method for r in backend.requests] == ['GET', 'POST']


def test_stream_overflow_aborts_early_and_closes_response():
    backend, ws = Backend(), uuid4()
    backend.stream = Stream([b'hello!', b'x'*20, b'never'])
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client, max_bytes=5).read(ws, identity(ws))
    assert backend.stream.consumed == 1
    assert backend.stream.closed


@pytest.mark.parametrize('headers', [{'content-length': '999999999'}, {'content-length': 'garbage'}, {'content-encoding': 'gzip'}])
def test_untrusted_response_headers_rejected_without_reading(headers):
    backend, ws = Backend(), uuid4()
    backend.headers, backend.stream = headers, Stream([b'hello'])
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).read(ws, identity(ws))
    assert backend.stream.consumed == 0
    assert backend.stream.closed


def test_body_and_configuration_limits_rejected_before_io():
    backend = Backend()
    for kwargs in ({'bucket': 'public'}, {'max_bytes': 0}, {'max_bytes': True}):
        with pytest.raises(PrivateObjectError):
            PrivateObjectStore(backend.client, **kwargs)
    store = PrivateObjectStore(backend.client, max_bytes=4)
    with pytest.raises(PrivateObjectError):
        store.put(uuid4(), 'original', b'hello', 'text/plain')
    assert backend.requests == []


def test_deadline_checked_between_each_transport_chunk(monkeypatch):
    import mira.private_objects as module
    backend, ws = Backend(), uuid4()
    backend.stream = Stream([b'h', b'ello'])
    times = iter([0.0, 31.0, 31.0])
    monkeypatch.setattr(module, 'monotonic', lambda: next(times))
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).read(ws, identity(ws))
    assert backend.stream.consumed == 1
    assert backend.stream.closed


def test_duplicate_400_is_verified_when_sdk_error_code_is_duplicate():
    backend, ws = Backend(), uuid4()
    backend.upload_error, backend.download = 400, b'hello'
    assert PrivateObjectStore(backend.client).put(ws, 'original', b'hello', 'text/plain') == identity(ws)


def test_redirect_never_forwards_authentication():
    backend, ws = Backend(), uuid4()
    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={'location': 'https://foreign.invalid/steal'})

    backend.client.storage.session = httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True)
    backend.client.storage._client = backend.client.storage.session
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).read(ws, identity(ws))
    assert len(requests) == 1


def test_empty_object_roundtrip():
    backend, ws = Backend(), uuid4()
    value = PrivateObjectStore(backend.client).put(ws, 'report', b'', 'text/html; charset=utf-8')
    assert PrivateObjectStore(backend.client).read(ws, value) == b''


def test_full_installed_supabase_client_uses_same_authenticated_boundary():
    from supabase import ClientOptions, create_client
    backend, ws = Backend(), uuid4()
    # Local fabricated credentials only; all requests terminate at MockTransport.
    client = create_client('https://storage.invalid', 'fabricated-test-key', options=ClientOptions(
        auto_refresh_token=False, persist_session=False,
        httpx_client=httpx.Client(transport=httpx.MockTransport(backend.handle)),
    ))
    result = PrivateObjectStore(client).put(ws, 'report', b'hello', 'text/plain')
    assert result == identity(ws, purpose='report')
    assert PrivateObjectStore(client).read(ws, result) == b'hello'
    assert all(r.headers['authorization'] == 'Bearer fabricated-test-key' for r in backend.requests)


@pytest.mark.parametrize('change', [{'size_bytes': 6}, {'sha256': '0'*64}])
def test_bounded_read_checks_exact_declared_integrity(change):
    backend, ws = Backend(), uuid4()
    backend.download = b'hello'
    value = identity(ws)
    value.update(change)
    with pytest.raises(PrivateObjectError):
        PrivateObjectStore(backend.client).read(ws, value)
