"""Portable package tests use synthetic bytes only, never a production backup."""
import hashlib
import json
import stat
from uuid import uuid4

import pytest

DUMP = b'PGDMP\x00full passages: fact A; fact B; fact C\xff\n'
BODY = b'abc'
DIGEST = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'


def identity(**changes):
    result = dict(workspace_id=str(uuid4()), purpose='original', sha256=DIGEST,
                  size_bytes=3, media_type='application/pdf', storage_kind='private_local',
                  approval_reference='fixture approval')
    result.update(changes)
    return result


def package(tmp_path, identities=None):
    from mira.recovery import create_backup
    tmp_path = tmp_path.resolve()
    source = tmp_path / 'input.dump'
    source.write_bytes(DUMP)
    target = tmp_path / 'backup'
    manifest = create_backup(target, source, identities or [identity()], lambda _: BODY)
    return target, manifest


def rewrite_manifest(root, manifest):
    body = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    (root / 'manifest.json').write_bytes(body)
    (root / '.complete').write_text(hashlib.sha256(body).hexdigest() + '\n')


def test_complete_dump_roundtrip_and_private_deduplicated_objects(tmp_path):
    from mira.recovery import BackupObject, restore_backup, verify_backup
    original = identity()
    report = identity(purpose='report', media_type='text/html', storage_kind='private_supabase', bucket='reports')
    assert BackupObject(original).identity == original
    root, manifest = package(tmp_path, [original, report])
    assert verify_backup(root) == manifest
    assert len(list((root / 'objects').iterdir())) == 1
    assert [entry['identity'] for entry in manifest['objects']] == [original, report]
    for path in [root, root / 'objects']:
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    for path in [root / 'database.dump', root / 'manifest.json', root / '.complete', root / 'objects' / (DIGEST + '.bin')]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    restored = {}
    order = []
    def write_object(item, data):
        restored[(item['workspace_id'], item['purpose'])] = data
        order.append('object')
    def restore_database(path):
        assert path.read_bytes() == DUMP
        order.append('database')
    restore_backup(root, write_object=write_object, restore_database=restore_database)
    assert list(restored.values()) == [BODY, BODY]
    assert order == ['object', 'object', 'database']


@pytest.mark.parametrize('member', ['database.dump', 'objects/' + DIGEST + '.bin', 'manifest.json', '.complete'])
@pytest.mark.parametrize('damage', ['missing', 'corrupt', 'symlink'])
def test_invalid_member_rejected_before_any_restore_callback(tmp_path, member, damage):
    from mira.recovery import BackupValidationError, restore_backup
    root, _ = package(tmp_path)
    path = root / member
    path.unlink()
    if damage == 'corrupt':
        path.write_bytes(b'corrupt')
    elif damage == 'symlink':
        outside = tmp_path / 'outside'
        outside.write_bytes(DUMP)
        path.symlink_to(outside)
    mutations = []
    with pytest.raises(BackupValidationError):
        restore_backup(root, write_object=lambda *args: mutations.append('object'),
                       restore_database=lambda *args: mutations.append('db'))
    assert mutations == []


@pytest.mark.parametrize('change', ['duplicate', 'traversal', 'wrong_size', 'bad_uuid', 'extra_identity_key', 'incompatible', 'unknown_version'])
def test_manifest_rejects_invalid_identity_paths_and_duplicates(tmp_path, change):
    from mira.recovery import BackupValidationError, verify_backup
    root, manifest = package(tmp_path)
    entry = manifest['objects'][0]
    if change == 'duplicate':
        manifest['objects'].append(entry)
    elif change == 'traversal':
        entry['file'] = '../input.dump'
    elif change == 'wrong_size':
        entry['identity']['size_bytes'] = True
    elif change == 'bad_uuid':
        entry['identity']['workspace_id'] = 'not-a-uuid'
    elif change == 'extra_identity_key':
        entry['identity']['service_key'] = 'secret'
    elif change == 'incompatible':
        other = json.loads(json.dumps(entry))
        other['identity']['media_type'] = 'text/plain'
        manifest['objects'].append(other)
    else:
        manifest['schema_version'] = 2
    rewrite_manifest(root, manifest)
    with pytest.raises(BackupValidationError):
        verify_backup(root)


@pytest.mark.parametrize('location', ['root', 'ancestor', 'objects', 'extra', 'duplicate_json'])
def test_symlink_directories_and_extraneous_or_repeated_json_rejected(tmp_path, location):
    from mira.recovery import BackupValidationError, verify_backup
    root, _ = package(tmp_path)
    if location == 'root':
        alias = tmp_path / 'alias'
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif location == 'ancestor':
        alias = tmp_path / 'alias'
        alias.symlink_to(tmp_path.resolve(), target_is_directory=True)
        root = alias / 'backup'
    elif location == 'objects':
        (root / 'objects').rename(tmp_path / 'outside')
        (root / 'objects').symlink_to(tmp_path / 'outside', target_is_directory=True)
    elif location == 'extra':
        (root / '.env').write_text('secrets must not enter backups')
    else:
        (root / 'manifest.json').write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(BackupValidationError):
        verify_backup(root)


def test_bounds_and_incomplete_or_existing_destination_fail_closed(tmp_path):
    from mira.recovery import BackupValidationError, create_backup, verify_backup
    root, _ = package(tmp_path)
    for options in ({'max_database_bytes': 3}, {'max_object_bytes': 2}, {'max_objects': 0}):
        with pytest.raises(BackupValidationError):
            verify_backup(root, **options)
    with pytest.raises(BackupValidationError):
        create_backup(root, tmp_path / 'input.dump', [], lambda _: BODY)
    assert (root / 'database.dump').read_bytes() == DUMP
    target = tmp_path.resolve() / 'failed'
    with pytest.raises(BackupValidationError):
        create_backup(target, tmp_path.resolve() / 'input.dump', [identity()], lambda _: b'bad')
    assert not target.exists()
    assert not list(tmp_path.glob('.failed.*'))


def test_failed_object_restore_stops_before_database_and_hides_callback_details(tmp_path):
    from mira.recovery import BackupRestoreError, restore_backup
    root, _ = package(tmp_path)
    mutations = []
    def fail(*args):
        raise RuntimeError('postgres://secret-password')
    with pytest.raises(BackupRestoreError) as failure:
        restore_backup(root, write_object=fail, restore_database=lambda _: mutations.append('db'))
    assert 'secret-password' not in str(failure.value)
    assert mutations == []


def test_symlink_hidden_by_parent_traversal_is_rejected(tmp_path):
    from mira.recovery import BackupValidationError, verify_backup
    root, _ = package(tmp_path)
    alias = tmp_path / 'alias'
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(BackupValidationError):
        verify_backup(alias / '..' / 'backup')


@pytest.mark.parametrize('source_kind', ['symlink', 'directory', 'too_large', 'read_failure', 'duplicate', 'destination_empty'])
def test_failed_creation_never_publishes_or_replaces(tmp_path, source_kind):
    from mira.recovery import BackupValidationError, create_backup
    tmp_path = tmp_path.resolve()
    source = tmp_path / 'source'
    source.write_bytes(DUMP)
    target = tmp_path / 'output'
    objects = [identity()]
    options = {}
    def read_object(_):
        if source_kind == 'read_failure':
            raise RuntimeError('credential-do-not-expose')
        return BODY
    if source_kind == 'symlink':
        alias = tmp_path / 'source-alias'
        alias.symlink_to(source)
        source = alias
    elif source_kind == 'directory':
        source = tmp_path
    elif source_kind == 'too_large':
        options['max_database_bytes'] = 3
    elif source_kind == 'duplicate':
        objects.append(dict(objects[0]))
    elif source_kind == 'destination_empty':
        target.mkdir()
    with pytest.raises(BackupValidationError) as failure:
        create_backup(target, source, objects, read_object, **options)
    assert 'credential' not in str(failure.value)
    assert not target.exists() or (source_kind == 'destination_empty' and not list(target.iterdir()))
    assert not list(tmp_path.glob('.output.*'))


def test_manifest_bound_and_extraneous_object_are_rejected(tmp_path):
    from mira.recovery import BackupValidationError, verify_backup
    root, _ = package(tmp_path)
    extra = root / 'objects' / 'unexpected.bin'
    extra.write_bytes(b'not referenced')
    with pytest.raises(BackupValidationError):
        verify_backup(root)
    extra.unlink()
    with (root / 'manifest.json').open('wb') as stream:
        stream.truncate(8 * 1024**2 + 1)
    with pytest.raises(BackupValidationError):
        verify_backup(root)


def test_atomic_publication_does_not_overwrite_destination_created_during_read(tmp_path):
    from mira.recovery import BackupValidationError, create_backup
    tmp_path = tmp_path.resolve()
    dump = tmp_path / 'source'
    dump.write_bytes(DUMP)
    target = tmp_path / 'backup'
    def concurrent_destination(_):
        target.mkdir()
        return BODY
    with pytest.raises(BackupValidationError):
        create_backup(target, dump, [identity()], concurrent_destination)
    assert target.is_dir() and not list(target.iterdir())
    assert not list(tmp_path.glob('.backup.*'))


def test_dump_only_backup_retains_full_bytes_with_zero_object_allowance(tmp_path):
    from mira.recovery import create_backup, restore_backup, verify_backup
    tmp_path = tmp_path.resolve()
    dump = tmp_path / 'source'
    dump.write_bytes(DUMP)
    root = tmp_path / 'backup'
    manifest = create_backup(root, dump, [], lambda _: pytest.fail('no object read'), max_objects=0)
    assert verify_backup(root, max_objects=0) == manifest
    recovered = []
    restore_backup(root, write_object=lambda *args: pytest.fail('no object write'),
                   restore_database=lambda path: recovered.append(path.read_bytes()))
    assert recovered == [DUMP]


def test_database_callback_failure_is_typed_and_secret_safe(tmp_path):
    from mira.recovery import BackupRestoreError, restore_backup
    root, _ = package(tmp_path)
    def fail(_):
        raise OSError('postgres://credential')
    with pytest.raises(BackupRestoreError) as failure:
        restore_backup(root, write_object=lambda *args: None, restore_database=fail)
    assert 'credential' not in str(failure.value)


def test_identical_legacy_report_html_keeps_each_original_relative_path(tmp_path):
    from mira.recovery import restore_backup
    run_id = str(uuid4())
    first = identity(purpose='report', media_type='text/html', relative_path=run_id + '/report-v1.html')
    second = first | {'relative_path': run_id + '/report-v2-reviewed.html'}
    root, manifest = package(tmp_path, [first, second])
    assert len(list((root / 'objects').iterdir())) == 1
    restored = {}
    restore_backup(root, write_object=lambda item, body: restored.update({item['relative_path']: body}),
                   restore_database=lambda _: None)
    assert restored == {run_id + '/report-v1.html': BODY, run_id + '/report-v2-reviewed.html': BODY}
    assert len(manifest['objects']) == 2


@pytest.mark.parametrize('path', [
    '../report-v1.html', '/tmp/report-v1.html', 'not-a-uuid/report-v1.html',
    '00000000-0000-0000-0000-000000000000/../report-v1.html',
    '00000000-0000-0000-0000-000000000000/report-v0.html',
    '00000000-0000-0000-0000-000000000000/report-v1.json',
    '00000000-0000-0000-0000-000000000000/report-v01.html',
    '00000000-0000-0000-0000-000000000000/other/report-v1.html',
])
def test_local_report_relative_path_rejects_traversal_and_foreign_file_forms(tmp_path, path):
    from mira.recovery import BackupValidationError
    with pytest.raises(BackupValidationError):
        package(tmp_path, [identity(purpose='report', relative_path=path)])


@pytest.mark.parametrize('changes', [{'purpose': 'original'}, {'purpose': 'report', 'storage_kind': 'private_supabase'}])
def test_relative_path_allowed_only_for_private_local_reports(tmp_path, changes):
    from mira.recovery import BackupValidationError
    item = identity(relative_path=str(uuid4()) + '/report-v1.html', **changes)
    with pytest.raises(BackupValidationError):
        package(tmp_path, [item])
