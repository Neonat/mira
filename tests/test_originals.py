"""Offline contract checks for private, explicitly permitted original bytes."""
import json
import stat
from dataclasses import replace
from uuid import uuid4

import pytest

from mira.store import SourceRecord


def source():
    return SourceRecord(uuid4(), 'Fixture', 'website', 'https://example.test', None,
                        ('store_text',), {'original_retention': {
                            'approved': True, 'reference': 'fixture-only-approval'}})


def adapter(root, **kwargs):
    from mira.originals import PrivateOriginalStore, RetentionPolicy
    return PrivateOriginalStore(root, RetentionPolicy(enabled=True, **kwargs))


def retain(store, workspace, src=None, body=b'abc', method='http_fetch'):
    return store.retain(workspace, src or source(), body,
                        acquisition_method=method, content_type='application/pdf')


def test_opt_in_and_explicit_grant_are_both_required(tmp_path):
    from mira.originals import PrivateOriginalStore, RetentionPolicy
    root = tmp_path / 'originals'
    assert retain(PrivateOriginalStore(root, RetentionPolicy()), uuid4()) is None
    store = adapter(root)
    for config in ({}, {'original_retention': True},
                   {'original_retention': {'approved': 'true', 'reference': 'x'}},
                   {'original_retention': {'approved': True, 'reference': '  '}}):
        assert retain(store, uuid4(), replace(source(), connector_config=config)) is None
    assert retain(store, uuid4(), replace(source(), permitted_operations=('fetch',))) is None
    assert not root.exists()


def test_env_policy_is_off_by_default_and_bounded(monkeypatch):
    from mira.originals import RetentionPolicy
    monkeypatch.delenv('MIRA_RETAIN_ORIGINALS', raising=False)
    monkeypatch.delenv('MIRA_ORIGINAL_MAX_BYTES', raising=False)
    assert RetentionPolicy.from_env() == RetentionPolicy()
    monkeypatch.setenv('MIRA_RETAIN_ORIGINALS', 'true')
    monkeypatch.setenv('MIRA_ORIGINAL_MAX_BYTES', '3')
    assert RetentionPolicy.from_env() == RetentionPolicy(enabled=True, max_bytes=3)
    monkeypatch.setenv('MIRA_ORIGINAL_MAX_BYTES', '-1')
    with pytest.raises(ValueError):
        RetentionPolicy.from_env()


@pytest.mark.parametrize('method', ['live_browser', 'browser', 'unknown'])
def test_rendered_dom_and_unknown_acquisitions_are_not_originals(tmp_path, method):
    root = tmp_path / 'private'
    assert retain(adapter(root), uuid4(), method=method) is None
    assert not root.exists()


@pytest.mark.parametrize('method', ['http_fetch', 'manual_import'])
def test_roundtrip_private_identity_idempotence_and_permissions(tmp_path, method):
    root, workspace = tmp_path / 'private', uuid4()
    store = adapter(root)
    identity = retain(store, workspace, method=method)
    assert identity == {'sha256': 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
                        'size_bytes': 3, 'media_type': 'application/pdf',
                        'approval_reference': 'fixture-only-approval',
                        'storage_kind': 'private_local', 'workspace_id': str(workspace)}
    json.dumps(identity)
    path = root / str(workspace) / (identity['sha256'] + '.bin')
    before = path.stat().st_ino
    assert retain(store, workspace, method=method) == identity
    assert path.stat().st_ino == before
    assert store.read(workspace, identity) == b'abc'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert list(path.parent.iterdir()) == [path]


def test_oversize_never_writes(tmp_path):
    root = tmp_path / 'private'
    with pytest.raises(ValueError):
        retain(adapter(root, max_bytes=2), uuid4())
    assert not root.exists()


def test_reads_and_repeat_retains_reject_corruption(tmp_path):
    store, workspace = adapter(tmp_path / 'private'), uuid4()
    identity = retain(store, workspace)
    path = tmp_path / 'private' / str(workspace) / (identity['sha256'] + '.bin')
    path.write_bytes(b'xyz')
    with pytest.raises(ValueError):
        store.read(workspace, identity)
    with pytest.raises(ValueError):
        retain(store, workspace)
    assert path.read_bytes() == b'xyz'


def test_read_rejects_workspace_and_untrusted_identity_fields(tmp_path):
    store, workspace = adapter(tmp_path / 'private'), uuid4()
    identity = retain(store, workspace)
    for target, altered in [(uuid4(), identity), (workspace, dict(identity, sha256='../escape')),
                            (workspace, dict(identity, size_bytes=4)),
                            (workspace, dict(identity, storage_kind='external')),
                            (workspace, dict(identity, workspace_id=str(uuid4())))]:
        with pytest.raises(ValueError):
            store.read(target, altered)
    with pytest.raises(ValueError):
        retain(store, '../escape')


@pytest.mark.parametrize('level', ['ancestor', 'root', 'workspace', 'file'])
def test_symlink_escape_is_rejected_on_write_and_read(tmp_path, level):
    root, workspace = tmp_path / 'private', uuid4()
    store = adapter(root)
    identity = retain(store, workspace)
    original = root / str(workspace) / (identity['sha256'] + '.bin')
    if level == 'ancestor':
        linked = tmp_path / 'linked'
        linked.symlink_to(tmp_path, target_is_directory=True)
        store = adapter(linked / 'private')
    else:
        victim = {'root': root, 'workspace': original.parent, 'file': original}[level]
        moved = tmp_path / ('moved-' + level)
        victim.rename(moved)
        victim.symlink_to(moved, target_is_directory=level != 'file')
    with pytest.raises((OSError, ValueError)):
        retain(store, workspace)
    with pytest.raises((OSError, ValueError)):
        store.read(workspace, identity)


@pytest.mark.parametrize('config', [[1], 'invalid'])
def test_malformed_source_config_denies_retention_without_writes(tmp_path, config):
    root = tmp_path / 'private'
    assert retain(adapter(root), uuid4(), replace(source(), connector_config=config)) is None
    assert not root.exists()
