"""Pure archive bridge checks; local SQL fixture is independently selectable."""
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mira.originals import PrivateOriginalStore, RetentionPolicy
from mira.recovery_storage import ArchiveObjects
from test_durable_storage_db import conn, workspace, artifact


def ident(ws, body=b'ABC', **changes):
    value = dict(workspace_id=str(ws), purpose='original', sha256=sha256(body).hexdigest(),
                 size_bytes=len(body), media_type='application/octet-stream', storage_kind='private_local',
                 approval_reference='fixture approved retention')
    value.update(changes)
    return value


@pytest.fixture
def archive(tmp_path):
    return ArchiveObjects(PrivateOriginalStore(tmp_path / 'originals', RetentionPolicy()), tmp_path / 'reports')


class Rows:
    def __init__(self, originals=(), reports=()):
        self.originals, self.reports = originals, reports

    def execute(self, sql):
        return SimpleNamespace(fetchall=lambda: self.originals if 'document_versions' in sql else self.reports)


def report(ws, run, path=None, **changes):
    value = dict(workspace_id=ws, report_id=uuid4(), analysis_run_id=run, report_version=1,
                 review_status='draft', artifact_storage_path=path, state=None, content_sha256=None,
                 object_identity=None)
    value.update(changes)
    return value


def local_html(archive, run, body=b'<p>ABC</p>', name='report-v1.html'):
    root = archive.reports_dir / str(run)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(archive.reports_dir, 0o700)
    (root / name).write_bytes(body)
    os.chmod(root / name, 0o600)
    return f'{run}/{name}'


def test_legacy_original_normalization_dedup_and_exact_restore(archive, tmp_path):
    ws, body = uuid4(), b'ABC'
    value = ident(ws, body)
    archive.write(value, body)
    legacy = dict(value)
    legacy.pop('purpose')
    other_grant = dict(legacy, approval_reference='another approved reference')
    rows = [dict(workspace_id=ws, metadata={'original_retained': True, 'retained_original': v}) for v in (legacy, other_grant)]
    result = archive.collect(Rows(originals=rows))
    assert len(result) == 1 and result[0]['purpose'] == 'original'
    assert archive.read(result[0]) == body
    recovered = ArchiveObjects(PrivateOriginalStore(tmp_path / 'restored', RetentionPolicy()), tmp_path / 'restored-reports')
    recovered.write(result[0], body)
    recovered.write(result[0], body)
    assert recovered.read(result[0]) == body
    target = recovered.local_originals.root / str(ws) / (value['sha256'] + '.bin')
    assert target.read_bytes() == body
    assert target.stat().st_mode & 0o777 == 0o600


def test_same_html_multiple_original_paths_are_preserved(archive):
    ws, run = uuid4(), uuid4()
    path = local_html(archive, run)
    reviewed = local_html(archive, run, name='report-v2-reviewed.html')
    values = archive.collect(Rows(reports=[report(ws, run, path), report(ws, run, reviewed, report_version=2, review_status='reviewed')]))
    assert len(values) == 2
    assert {v['relative_path'] for v in values} == {path, reviewed}
    assert values[0]['sha256'] == values[1]['sha256']
    for value in values:
        original = archive.read(value)
        (archive.reports_dir / value['relative_path']).unlink()
        archive.write(value, original)
        archive.write(value, original)
        assert archive.read(value) == original


@pytest.mark.parametrize('value', [None, [], {}, {'workspace_id': 'bad'}, {'purpose': 'report'}])
def test_malformed_retained_original_aborts(archive, value):
    with pytest.raises(ValueError):
        archive.collect(Rows(originals=[{'workspace_id': uuid4(), 'metadata': {'original_retained': True, 'retained_original': value}}]))


def test_original_workspace_binding_is_not_relabelled(archive):
    with pytest.raises(ValueError):
        archive.collect(Rows(originals=[{'workspace_id': uuid4(), 'metadata': {'original_retained': True, 'retained_original': ident(uuid4())}}]))


@pytest.mark.parametrize('path', ['../report.html', '/tmp/report.html', 'notuuid/report-v1.html', '00000000-0000-0000-0000-000000000000/report-v1.html'])
def test_foreign_or_noncanonical_report_paths_abort(archive, path):
    with pytest.raises(ValueError):
        archive.collect(Rows(reports=[report(uuid4(), uuid4(), path)]))


def test_null_unrendered_report_is_skipped_and_local_missing_aborts(archive):
    ws, run = uuid4(), uuid4()
    assert archive.collect(Rows(reports=[report(ws, run)])) == []
    with pytest.raises((ValueError, OSError)):
        archive.collect(Rows(reports=[report(ws, run, f'{run}/report-v1.html')]))


def test_pending_publication_hash_must_match_local_bytes(archive):
    ws, run = uuid4(), uuid4()
    path = local_html(archive, run)
    value = report(ws, run, path, state='pending', content_sha256='0'*64)
    with pytest.raises(ValueError):
        archive.collect(Rows(reports=[value]))
    value['content_sha256'] = sha256(b'<p>ABC</p>').hexdigest()
    assert archive.collect(Rows(reports=[value]))[0]['sha256'] == value['content_sha256']


def test_corrupt_local_original_read_and_overwrite_rejected(archive):
    value = ident(uuid4())
    archive.write(value, b'ABC')
    target = archive.local_originals.root / value['workspace_id'] / (value['sha256'] + '.bin')
    target.write_bytes(b'XYZ')
    for action in (lambda: archive.read(value), lambda: archive.write(value, b'ABC')):
        with pytest.raises(ValueError):
            action()
    assert target.read_bytes() == b'XYZ'


@pytest.mark.parametrize('changes', [{'workspace_id': 'bad'}, {'purpose': 'report'}, {'sha256': 'bad'}, {'size_bytes': 2}, {'bucket': 'public'}, {'relative_path': '../x'}, {'storage_kind': 'public'}, {'media_type': 'text/plain\r\nsecret'}])
def test_write_rejects_invalid_identity_before_creating_files(archive, changes):
    with pytest.raises(ValueError):
        archive.write(ident(uuid4(), **changes), b'ABC')
    assert not archive.local_originals.root.exists()
    assert not archive.reports_dir.exists()


def test_remote_original_strips_only_approval_reference(archive):
    value = ident(uuid4(), storage_kind='private_supabase', bucket='mira-evidence-private')
    calls = []
    core = {k: v for k, v in value.items() if k != 'approval_reference'}
    class Remote:
        def read(self, ws, item):
            calls.append(('read', ws, item))
            assert item == core
            return b'ABC'
        def put(self, ws, purpose, body, media_type):
            calls.append(('put', ws, purpose, body, media_type))
            return core
    archive.objects = Remote()
    archive.write(value, b'ABC')
    assert archive.read(value) == b'ABC'
    assert len(calls) >= 3
    with pytest.raises(ValueError):
        archive.read(dict(value, unexpected='injected'))


def test_ready_remote_report_never_uses_local_fallback(archive):
    ws, run = uuid4(), uuid4()
    value = ident(ws, purpose='report', storage_kind='private_supabase', bucket='mira-evidence-private', media_type='text/html')
    value.pop('approval_reference')
    result = archive.collect(Rows(reports=[report(ws, run, '../foreign.html', state='ready', content_sha256=value['sha256'], object_identity=value)]))
    assert result == [value]
    with pytest.raises(ValueError):
        archive.read(value)


def test_symlinks_rejected_for_report_file_and_ancestors(archive, tmp_path):
    ws, run = uuid4(), uuid4()
    path = local_html(archive, run)
    value = archive.collect(Rows(reports=[report(ws, run, path)]))[0]
    target = archive.reports_dir / path
    target.unlink()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'<p>ABC</p>')
    target.symlink_to(outside)
    for action in (lambda: archive.read(value), lambda: archive.write(value, b'<p>ABC</p>')):
        with pytest.raises((ValueError, OSError)):
            action()
    target.unlink()
    target.parent.rmdir()
    target.parent.symlink_to(tmp_path)
    with pytest.raises((ValueError, OSError)):
        archive.write(value, b'<p>ABC</p>')


@pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'), reason='local PostgreSQL fixture required')
def test_collect_actual_sql_rows_and_restore_legacy_html(conn, workspace, artifact, tmp_path):
    ws, actor, report_id, _ = artifact
    row = conn.execute('select r.artifact_storage_path,a.analysis_run_id from public.reports r join public.analysis_revisions a on a.id=r.analysis_revision_id where r.id=%s', (report_id,)).fetchone()
    archive = ArchiveObjects(PrivateOriginalStore(tmp_path / 'originals', RetentionPolicy()), tmp_path)
    # The shared local test DB contains historical evidence; scope only fixture
    # rows without changing the adapter's production SELECTs or stored evidence.
    class ScopedSnapshot:
        def execute(self, sql):
            return conn.execute('select * from (' + sql + ') fixture_snapshot where workspace_id=%s', (ws,))
    values = archive.collect(ScopedSnapshot())
    assert len(values) == 1
    value = values[0]
    assert value['relative_path'] == row['artifact_storage_path']
    body = archive.read(value)
    assert body == b'<p>fixture</p>'
    (tmp_path / value['relative_path']).unlink()
    archive.write(value, body)
    assert archive.read(value) == body


def test_archive_package_restores_same_blob_to_both_report_paths(archive, tmp_path):
    from mira.recovery import create_backup, restore_backup
    ws, run = uuid4(), uuid4()
    first = local_html(archive, run)
    second = local_html(archive, run, name='report-v2.html')
    original = ident(ws)
    archive.write(original, b'ABC')
    values = archive.collect(Rows(
        originals=[{'workspace_id': ws, 'metadata': {'original_retained': True, 'retained_original': original}}],
        reports=[report(ws, run, first), report(ws, run, second, report_version=2)],
    ))
    dump = tmp_path / 'fixture.dump'
    dump.write_bytes(b'operator-native-dump-fixture')
    package = tmp_path / 'package'
    manifest = create_backup(package, dump, values, archive.read)
    assert len(manifest['objects']) == 3
    assert len(list((package / 'objects').iterdir())) == 2
    restored = ArchiveObjects(PrivateOriginalStore(tmp_path / 'recovered-originals', RetentionPolicy()), tmp_path / 'recovered-reports')
    published = []
    def publish_database(path):
        assert all(restored.read(value) == archive.read(value) for value in values)
        published.append(path.read_bytes())
    restore_backup(package, write_object=restored.write, restore_database=publish_database)
    assert published == [dump.read_bytes()]
    assert (restored.reports_dir / first).read_bytes() == b'<p>ABC</p>'
    assert (restored.reports_dir / second).read_bytes() == b'<p>ABC</p>'


@pytest.mark.parametrize('kind', ['report-root', 'original-root', 'original-file'])
def test_restoration_rejects_local_root_and_original_symlinks(archive, tmp_path, kind):
    ws, run = uuid4(), uuid4()
    outside = tmp_path / 'unrelated'
    outside.mkdir(mode=0o700)
    if kind == 'report-root':
        archive.reports_dir.symlink_to(outside, target_is_directory=True)
        value = ident(ws, purpose='report', relative_path=f'{run}/report-v1.html', media_type='text/html')
        value.pop('approval_reference')
    elif kind == 'original-root':
        archive.local_originals.root.symlink_to(outside, target_is_directory=True)
        value = ident(ws)
    else:
        value = ident(ws)
        directory = archive.local_originals.root / str(ws)
        directory.mkdir(parents=True, mode=0o700)
        os.chmod(archive.local_originals.root, 0o700)
        target = outside / 'blob'
        target.write_bytes(b'ABC')
        (directory / (value['sha256'] + '.bin')).symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        archive.write(value, b'ABC')
    assert not (outside / str(ws)).exists()


def test_corrupt_existing_report_is_never_replaced(archive):
    ws, run = uuid4(), uuid4()
    path = local_html(archive, run)
    value = archive.collect(Rows(reports=[report(ws, run, path)]))[0]
    target = archive.reports_dir / path
    target.write_bytes(b'<p>XYZ</p>')
    with pytest.raises(ValueError):
        archive.read(value)
    with pytest.raises(ValueError):
        archive.write(value, b'<p>ABC</p>')
    assert target.read_bytes() == b'<p>XYZ</p>'


def test_remote_restore_must_return_exact_backend_identity(archive):
    value = ident(uuid4(), storage_kind='private_supabase', bucket='mira-evidence-private')
    class Remote:
        def put(self, ws, purpose, body, media_type):
            return dict(value, workspace_id=str(uuid4()))
    archive.objects = Remote()
    with pytest.raises(ValueError):
        archive.write(value, b'ABC')


def test_conflicting_original_metadata_is_not_silently_deduplicated(archive):
    ws = uuid4()
    values = [ident(ws), ident(ws, size_bytes=2)]
    with pytest.raises(ValueError):
        archive.collect(Rows(originals=[{'workspace_id': ws, 'metadata': {'original_retained': True, 'retained_original': item}} for item in values]))


def test_reports_over_configured_byte_limit_abort_before_reading(archive, monkeypatch):
    import mira.recovery_storage as module
    monkeypatch.setattr(module, '_MAX_BYTES', 4)
    ws, run = uuid4(), uuid4()
    path = local_html(archive, run)
    with pytest.raises(ValueError):
        archive.collect(Rows(reports=[report(ws, run, path)]))


@pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'), reason='local PostgreSQL fixture required')
def test_collect_actual_sql_retained_original_and_ready_report(conn, workspace, artifact, tmp_path):
    from psycopg.types.json import Jsonb
    from mira.db import acting_as
    ws, actor, report_id, _ = artifact
    archive = ArchiveObjects(PrivateOriginalStore(tmp_path / 'originals', RetentionPolicy()), tmp_path)
    original = ident(ws)
    archive.write(original, b'ABC')
    legacy = dict(original)
    legacy.pop('purpose')
    source = conn.execute('select id from public.sources where workspace_id=%s limit 1', (ws,)).fetchone()['id']
    document = conn.execute("insert into public.documents(workspace_id,source_id,title) values(%s,%s,'recovery fixture') returning id", (ws, source)).fetchone()['id']
    conn.execute("""insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,
        source_url,title,extraction_status,metadata) values(%s,%s,1,%s,'https://fixture.invalid/original','Recovery fixture','complete',%s)""",
        (ws, document, sha256(b'extracted-text').hexdigest(), Jsonb({'original_retained': True, 'retained_original': legacy})))
    remote = ident(ws, b'<p>fixture</p>', purpose='report', storage_kind='private_supabase', bucket='mira-evidence-private', media_type='text/html')
    remote.pop('approval_reference')
    with acting_as(conn, actor):
        conn.execute("""insert into public.report_artifacts(workspace_id,report_id,state,content_sha256,
            object_identity,created_by) values(%s,%s,'ready',%s,%s,%s)""", (ws, report_id, remote['sha256'], Jsonb(remote), actor))
    class ScopedSnapshot:
        def execute(self, sql):
            return conn.execute('select * from (' + sql + ') fixture_snapshot where workspace_id=%s', (ws,))
    values = archive.collect(ScopedSnapshot())
    assert len(values) == 2
    assert original in values and remote in values
    assert archive.read(original) == b'ABC'
