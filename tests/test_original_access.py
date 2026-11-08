"""Signed-in original access with RLS-shaped row visibility and real byte storage."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mira.originals import PrivateOriginalStore, RetentionPolicy
from mira.store import SourceRecord


class Client:
    def __init__(self, tables, user_id):
        self.tables = tables
        self.auth = SimpleNamespace(get_user=lambda: SimpleNamespace(
            user=SimpleNamespace(id=str(user_id)) if user_id else None))

    def table(self, name):
        return Query(deepcopy(self.tables.get(name, [])))


class Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, fields):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


@pytest.fixture
def access_fixture(tmp_path):
    ws, user, source_id, doc, version_id = [uuid4() for _ in range(5)]
    grant = {'original_retention': {'approved': True, 'reference': 'fixture-approval'}}
    source = SourceRecord(source_id, 'Fixture', 'website', None, None, ('store_text',), grant)
    store = PrivateOriginalStore(tmp_path.resolve() / 'originals', RetentionPolicy(enabled=True))
    identity = store.retain(ws, source, b'original', acquisition_method='http_fetch', content_type='application/pdf')
    tables = {
        'workspace_members': [{'workspace_id': str(ws), 'user_id': str(user), 'role': 'viewer'}],
        'document_versions': [{'id': str(version_id), 'workspace_id': str(ws), 'document_id': str(doc),
                               'metadata': {'original_retained': True, 'retained_original': identity}}],
        'documents': [{'id': str(doc), 'workspace_id': str(ws), 'source_id': str(source_id)}],
        'sources': [{'id': str(source_id), 'workspace_id': str(ws), 'is_active': True,
                     'permitted_operations': ['store_text'], 'connector_config': grant}],
    }
    return ws, user, version_id, store, tables


def test_signed_in_member_reads_database_selected_original(access_fixture):
    from mira.original_access import read_original
    ws, user, version_id, store, tables = access_fixture
    assert read_original(Client(tables, user), ws, version_id, store) == b'original'


@pytest.mark.parametrize('denial', ['anonymous', 'no_auth', 'foreign_workspace', 'version_hidden',
                                   'document_hidden', 'source_hidden', 'inactive', 'revoked',
                                   'reference_changed', 'permission', 'membership', 'not_retained',
                                   'bad_identity'])
def test_current_auth_visibility_and_source_permission_are_required(access_fixture, denial):
    from mira.original_access import read_original
    ws, user, version_id, store, tables = access_fixture
    if denial == 'anonymous':
        user = None
    elif denial == 'foreign_workspace':
        ws = uuid4()
    elif denial.endswith('_hidden'):
        table = {'version_hidden': 'document_versions', 'document_hidden': 'documents', 'source_hidden': 'sources'}[denial]
        tables[table] = []
    elif denial == 'inactive':
        tables['sources'][0]['is_active'] = False
    elif denial == 'revoked':
        tables['sources'][0]['connector_config'] = {}
    elif denial == 'reference_changed':
        tables['sources'][0]['connector_config']['original_retention']['reference'] = 'new-grant'
    elif denial == 'permission':
        tables['sources'][0]['permitted_operations'] = ['fetch']
    elif denial == 'membership':
        tables['workspace_members'] = []
    elif denial == 'not_retained':
        tables['document_versions'][0]['metadata']['original_retained'] = False
    elif denial == 'bad_identity':
        tables['document_versions'][0]['metadata']['retained_original']['sha256'] = '../secret'
    client = Client(tables, user)
    if denial == 'no_auth':
        client.auth = None
    with pytest.raises(PermissionError):
        read_original(client, ws, version_id, store)


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_unavailable_or_corrupt_original_fails_closed(access_fixture, damage):
    from mira.original_access import read_original
    ws, user, version_id, store, tables = access_fixture
    identity = tables['document_versions'][0]['metadata']['retained_original']
    path = store.root / str(ws) / (identity['sha256'] + '.bin')
    if damage == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'corrupte')
    with pytest.raises(PermissionError):
        read_original(Client(tables, user), ws, version_id, store)


def test_storage_permission_error_does_not_expose_private_path(access_fixture):
    from mira.original_access import read_original
    ws, user, version_id, _, tables = access_fixture

    class UnavailableStore:
        def read(self, workspace_id, identity):
            raise PermissionError('/private/secret/credential-bearing-path')

    with pytest.raises(PermissionError) as error:
        read_original(Client(tables, user), ws, version_id, UnavailableStore())
    assert '/private/' not in str(error.value)


def test_signed_expected_identity_is_checked_at_actual_storage_read(access_fixture):
    from mira.original_access import read_original
    ws,user,vid,store,tables=access_fixture
    old=deepcopy(tables['document_versions'][0]['metadata']['retained_original'])
    tables['document_versions'][0]['metadata']['retained_original']['sha256']='b'*64
    with pytest.raises(PermissionError):
        read_original(Client(tables,user),ws,vid,store,expected_identity=old)
