"""Native PostgreSQL recovery drills against disposable, synthetic databases."""
import hashlib
import os
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from mira.recovery import BackupValidationError, create_backup

DSN = os.environ.get('MIRA_TEST_DATABASE_URL')
BODY = b'abc'
DIGEST = hashlib.sha256(BODY).hexdigest()


def tools():
    from mira.database_recovery import PgTools
    prefix = ('docker', 'exec', '-i', 'supabase_db_mira-dbsearch')
    connection = ('--host=/var/run/postgresql', '--port=5432', '--username=postgres')
    return PgTools(dump_command=prefix + ('pg_dump',) + connection,
                   restore_command=prefix + ('pg_restore',) + connection)


@pytest.fixture
def databases():
    if not DSN:
        pytest.skip('MIRA_TEST_DATABASE_URL not configured')
    admin = psycopg.connect(DSN, autocommit=True, connect_timeout=5)
    names = ['mira_recovery_test_' + uuid4().hex for _ in range(2)]
    params = conninfo_to_dict(DSN)
    source_dsn, target_dsn = [make_conninfo(**(params | {'dbname': name})) for name in names]
    source = None
    try:
        for name in names:
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        source = psycopg.connect(source_dsn, autocommit=True)
        source.execute('CREATE TABLE facts (id integer PRIMARY KEY, body text NOT NULL)')
        source.execute("INSERT INTO facts VALUES (1,'fact A'),(2,'fact B'),(3,'fact C')")
        source.execute('ALTER TABLE facts ENABLE ROW LEVEL SECURITY')
        source.execute('CREATE POLICY fixture_read ON facts FOR SELECT USING (true)')
        source.execute('GRANT SELECT ON facts TO authenticated')
        source.execute('CREATE TABLE objects (identity jsonb NOT NULL, body bytea NOT NULL)')
        item = dict(workspace_id=str(uuid4()), purpose='original', sha256=DIGEST,
                    size_bytes=3, media_type='application/pdf', storage_kind='private_local')
        source.execute('INSERT INTO objects VALUES (%s,%s)', (psycopg.types.json.Jsonb(item), BODY))
        source.execute('CREATE TABLE frozen (bundle jsonb NOT NULL)')
        bundle = {'facts': ['fact A', 'fact B', 'fact C'], 'full_passages': ['full A', 'full B', 'full C'],
                  'coverage': {'complete': True}, 'review': {'status': 'approved'}}
        source.execute('INSERT INTO frozen VALUES (%s)', (psycopg.types.json.Jsonb(bundle),))
        yield source, source_dsn, target_dsn, item, bundle
    finally:
        if source is not None:
            source.close()
        for name in names:
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()


def collect(conn):
    return [row[0] for row in conn.execute('SELECT identity FROM objects').fetchall()]


def test_native_snapshot_dump_restore_retains_all_facts_frozen_evidence_and_rls(tmp_path, databases):
    from mira.database_recovery import backup_database, restore_database
    source, source_dsn, target_dsn, item, bundle = databases
    def concurrent_collect(conn):
        assert conn.execute('SHOW transaction_isolation').fetchone()[0] == 'repeatable read'
        assert conn.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
        objects = collect(conn)
        with psycopg.connect(source_dsn, autocommit=True) as other:
            other.execute("INSERT INTO facts VALUES (4,'concurrent fact D')")
            other.execute('INSERT INTO objects VALUES (%s,%s)',
                          (psycopg.types.json.Jsonb(item | {'workspace_id': str(uuid4())}), BODY))
        assert conn.execute('SELECT count(*) FROM facts').fetchone()[0] == 3
        return objects
    archive = tmp_path.resolve() / 'archive'
    manifest = backup_database(source, archive, collect_objects=concurrent_collect,
                               read_object=lambda _: BODY, tools=tools())
    assert len(manifest['objects']) == 1
    restored = []
    summary = restore_database(archive, target_dsn, trusted_backup=True,
                               write_object=lambda identity, body: restored.append((identity, body)), tools=tools())
    assert summary['database_restored'] is True and summary['object_count'] == 1
    assert restored == [(item, BODY)]
    with psycopg.connect(target_dsn, autocommit=True) as target:
        assert target.execute('SELECT body FROM facts ORDER BY id').fetchall() == [('fact A',), ('fact B',), ('fact C',)]
        assert target.execute('SELECT bundle FROM frozen').fetchone()[0] == bundle
        assert target.execute('SELECT count(*) FROM objects').fetchone()[0] == 1
        assert target.execute("SELECT relrowsecurity FROM pg_class WHERE oid='facts'::regclass").fetchone()[0]
        assert target.execute("SELECT has_table_privilege('authenticated','facts','SELECT')").fetchone()[0]
        assert target.execute("SELECT count(*) FROM pg_policy WHERE polrelid='facts'::regclass").fetchone()[0] == 1
    assert source.execute('SELECT count(*) FROM facts').fetchone()[0] == 4


@pytest.mark.parametrize('occupied', ['table', 'function', 'sequence', 'session'])
def test_nonempty_or_active_target_rejected_before_object_writes(tmp_path, databases, occupied):
    from mira.database_recovery import backup_database, restore_database, DatabaseRecoveryError
    source, _, target_dsn, _, _ = databases
    archive = tmp_path.resolve() / 'archive'
    backup_database(source, archive, collect_objects=collect, read_object=lambda _: BODY, tools=tools())
    target = psycopg.connect(target_dsn, autocommit=True)
    try:
        if occupied == 'table':
            target.execute('CREATE TABLE must_survive (value integer)')
        elif occupied == 'function':
            target.execute('CREATE FUNCTION must_survive() RETURNS integer LANGUAGE sql AS $$ SELECT 1 $$')
        elif occupied == 'sequence':
            target.execute('CREATE SEQUENCE must_survive')
        if occupied != 'session':
            target.close()
        writes = []
        with pytest.raises(DatabaseRecoveryError):
            restore_database(archive, target_dsn, trusted_backup=True, write_object=lambda *args: writes.append(args), tools=tools())
        assert writes == []
    finally:
        target.close()


@pytest.mark.parametrize('dsn', [
    'postgresql://user:secret@remote.example/mira_recovery_' + 'a' * 32,
    'postgresql://user:secret@127.0.0.1/postgres',
    'host=127.0.0.1 dbname=template1',
    'host=localhost hostaddr=10.0.0.1 dbname=mira_recovery_' + 'a' * 32,
    'host=127.0.0.1 dbname=workspacedb',
    'service=external dbname=mira_recovery_' + 'a' * 32,
])
def test_unsafe_target_dsn_rejected_without_network_or_object_writes(tmp_path, dsn):
    from mira.database_recovery import DatabaseRecoveryError, restore_database
    dump = tmp_path.resolve() / 'source'
    dump.write_bytes(b'fixture dump')
    archive = tmp_path.resolve() / 'archive'
    create_backup(archive, dump, [], lambda _: BODY)
    with pytest.raises(DatabaseRecoveryError) as failure:
        restore_database(archive, dsn, trusted_backup=True, write_object=lambda *args: pytest.fail('object write'), tools=tools())
    assert 'secret' not in str(failure.value)


def test_corruption_rejected_before_database_connection_or_object_write(tmp_path):
    from mira.database_recovery import restore_database
    dump = tmp_path.resolve() / 'source'
    dump.write_bytes(b'fixture dump')
    archive = tmp_path.resolve() / 'archive'
    create_backup(archive, dump, [], lambda _: BODY)
    (archive / 'database.dump').write_bytes(b'tampered')
    with pytest.raises(BackupValidationError):
        restore_database(archive, 'host=127.0.0.1 port=1 dbname=mira_recovery_' + uuid4().hex,
                         trusted_backup=True, write_object=lambda *args: pytest.fail('object write'), tools=tools())


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), True])
def test_tools_reject_invalid_timeouts(timeout):
    from mira.database_recovery import PgTools, DatabaseRecoveryError
    with pytest.raises(DatabaseRecoveryError):
        PgTools(timeout_seconds=timeout)


def test_dump_failure_and_timeout_leave_no_published_package(tmp_path, databases):
    from mira.database_recovery import PgTools, DatabaseRecoveryError, backup_database
    source, *_ = databases
    for suffix, body, timeout in [
        ('failure', 'import sys; sys.stderr.write("secret"); sys.exit(1)', 5),
        ('timeout', 'import time; time.sleep(10)', .2),
    ]:
        archive = tmp_path.resolve() / suffix
        marker = tmp_path.resolve() / (suffix + '.started')
        script = tmp_path.resolve() / (suffix + '.py')
        script.write_text('import os\nfrom pathlib import Path\nPath(' + repr(str(marker)) + ').write_text(str(os.getpid()))\n' + body + '\n')
        with pytest.raises(DatabaseRecoveryError) as failure:
            backup_database(source, archive, collect_objects=collect, read_object=lambda _: BODY,
                            tools=PgTools(dump_command=(sys.executable, str(script)), timeout_seconds=timeout))
        assert marker.exists(), 'the actual subprocess must run, rather than fail configuration validation'
        with pytest.raises(ChildProcessError):
            os.waitpid(int(marker.read_text()), os.WNOHANG)
        assert 'secret' not in str(failure.value)
        assert not archive.exists()
        assert source.execute('SELECT count(*) FROM facts').fetchone()[0] == 3


def test_source_name_is_rejected_even_if_source_was_emptied_and_closed(tmp_path, databases):
    from mira.database_recovery import backup_database, restore_database, DatabaseRecoveryError
    source, source_dsn, _, _, _ = databases
    archive = tmp_path.resolve() / 'archive'
    backup_database(source, archive, collect_objects=collect, read_object=lambda _: BODY, tools=tools())
    source.execute('DROP TABLE facts, objects, frozen')
    source.close()
    writes = []
    with pytest.raises(DatabaseRecoveryError):
        restore_database(archive, source_dsn, trusted_backup=True, write_object=lambda *args: writes.append(args), tools=tools())
    assert writes == []


def test_collect_callback_is_read_only_and_failed_export_rolls_back(tmp_path, databases):
    from mira.database_recovery import DatabaseRecoveryError, backup_database
    source, *_ = databases
    archive = tmp_path.resolve() / 'archive'
    def collect_with_write(conn):
        conn.execute("INSERT INTO facts VALUES (99,'must not persist')")
        return []
    with pytest.raises(DatabaseRecoveryError):
        backup_database(source, archive, collect_objects=collect_with_write, read_object=lambda _: BODY, tools=tools())
    assert not archive.exists()
    assert source.execute('SELECT count(*) FROM facts').fetchone()[0] == 3


def test_existing_transaction_is_not_committed_or_rolled_back(tmp_path, databases):
    from mira.database_recovery import DatabaseRecoveryError, backup_database
    source, *_ = databases
    with source.transaction():
        source.execute("INSERT INTO facts VALUES (99,'caller pending')")
        with pytest.raises(DatabaseRecoveryError):
            backup_database(source, tmp_path.resolve() / 'archive', collect_objects=collect,
                            read_object=lambda _: BODY, tools=tools())
        assert source.execute('SELECT count(*) FROM facts').fetchone()[0] == 4


def test_dump_credentials_use_environment_and_never_command_arguments(tmp_path, databases):
    from mira.database_recovery import PgTools, backup_database
    source, *_ = databases
    marker = tmp_path.resolve() / 'transport-safe'
    script = tmp_path.resolve() / 'transport.py'
    script.write_text(
        'import os, sys\nfrom pathlib import Path\n'
        'safe = bool(os.environ.get("PGPASSWORD")) and os.environ["PGPASSWORD"] not in " ".join(sys.argv)\n'
        'Path(' + repr(str(marker)) + ').write_text(str(safe))\n'
        'sys.stdout.buffer.write(b"synthetic-custom-archive")\n')
    backup_database(source, tmp_path.resolve() / 'archive', collect_objects=collect,
                    read_object=lambda _: BODY, tools=PgTools(dump_command=(sys.executable, str(script))))
    assert marker.read_text() == 'True'


def test_failed_object_writer_leaves_fresh_database_unpublished(tmp_path, databases):
    from mira.database_recovery import backup_database, restore_database
    from mira.recovery import BackupRestoreError
    source, _, target_dsn, _, _ = databases
    archive = tmp_path.resolve() / 'archive'
    backup_database(source, archive, collect_objects=collect, read_object=lambda _: BODY, tools=tools())
    def fail(*args):
        raise RuntimeError('private-object-credential')
    with pytest.raises(BackupRestoreError) as failure:
        restore_database(archive, target_dsn, trusted_backup=True, write_object=fail, tools=tools())
    assert 'credential' not in str(failure.value)
    with psycopg.connect(target_dsn, autocommit=True) as target:
        assert target.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0


@pytest.mark.parametrize('tool, arguments', [
    ('pg_dump', ('--exclude-table=public.document_passages',)),
    ('pg_dump', ('--exclude-table-data=public.document_passages',)),
    ('pg_dump', ('--exclude-table-data-and-children=public.document_passages',)),
    ('pg_dump', ('--filter=omit.txt',)),
    ('pg_dump', ('--filter', 'omit.txt')),
    ('pg_dump', ('-Tpublic.document_passages',)),
    ('pg_dump', ('-T', 'public.document_passages')),
    ('pg_dump', ('-Npublic',)),
    ('pg_dump', ('-tpublic.reports',)),
    ('pg_dump', ('--section=data',)),
    ('pg_dump', ('--exclude-t=public.facts',)),
    ('pg_dump', ('--', '--exclude-table=public.facts')),
    ('pg_restore', ('-Llist.txt',)),
    ('pg_restore', ('-L', 'list.txt')),
    ('pg_restore', ('--use-list=list.txt',)),
    ('pg_restore', ('--section', 'data')),
    ('pg_restore', ('-Cc',)),
    ('pg_restore', ('-cC',)),
    ('pg_restore', ('-Cfoo',)),
    ('pg_restore', ('-cfoo',)),
    ('pg_restore', ('--cre',)),
    ('pg_restore', ('--cle',)),
    ('pg_restore', ('--clean',)),
    ('pg_restore', ('--create',)),
    ('pg_restore', ('other-archive.dump',)),
    ('pg_restore', ('--', 'other-archive.dump')),
    ('pg_restore', ('--host', '--clean')),
])
def test_scope_and_destructive_options_are_rejected_before_execution(tool, arguments):
    from mira.database_recovery import DatabaseRecoveryError, PgTools
    field = 'dump_command' if tool == 'pg_dump' else 'restore_command'
    with pytest.raises(DatabaseRecoveryError):
        PgTools(**{field: (tool,) + arguments})


@pytest.mark.parametrize('arguments', [
    ('--host=127.0.0.1', '--port=5432', '--username=postgres'),
    ('--host', '/var/run/postgresql', '--port', '5432', '--username', 'postgres'),
    ('-h127.0.0.1', '-p5432', '-Upostgres'),
    ('-h', '127.0.0.1', '-p', '5432', '-U', 'postgres'),
])
def test_native_transport_only_options_are_accepted(arguments):
    from mira.database_recovery import PgTools
    configured = PgTools(dump_command=('pg_dump',) + arguments,
                         restore_command=('pg_restore',) + arguments)
    assert configured.dump_command == ('pg_dump',) + arguments


@pytest.mark.parametrize('acknowledgement', [None, False, 1, 'true'])
def test_restore_requires_explicit_trusted_archive_ack_before_tools_or_connections(tmp_path, acknowledgement):
    from mira.database_recovery import DatabaseRecoveryError, restore_database
    options = {} if acknowledgement is None else {'trusted_backup': acknowledgement}
    with pytest.raises(DatabaseRecoveryError):
        restore_database(tmp_path / 'does-not-even-exist',
                         'host=127.0.0.1 port=1 dbname=mira_recovery_' + uuid4().hex,
                         write_object=lambda *args: pytest.fail('object write'), **options)


@pytest.mark.parametrize('argument', ['--host=remote.example', '-h10.1.2.3', '--host=127.0.0.1,remote.example',
                                      '--host=/var/run/../elsewhere', '-p5432c', '--port=0', '--username=-c'])
def test_transport_flags_cannot_redirect_restore_to_remote_or_malformed_connection(argument):
    from mira.database_recovery import DatabaseRecoveryError, PgTools
    with pytest.raises(DatabaseRecoveryError):
        PgTools(restore_command=('pg_restore', argument))


@pytest.mark.parametrize('prefix', [
    ('docker', 'exec', '--env=PGOPTIONS=bad', 'container', 'pg_restore'),
    ('docker', 'exec', '-it', 'container', 'pg_restore'),
    ('docker', 'exec', '-i', 'container', 'pg_restore', '-Cc'),
    ('pg_restore', '--host=127.0.0.1', '--', '-Cc'),
    (sys.executable, '--', 'fixture.py'),
])
def test_wrapper_and_end_of_options_cannot_smuggle_native_flags(prefix):
    from mira.database_recovery import DatabaseRecoveryError, PgTools
    with pytest.raises(DatabaseRecoveryError):
        PgTools(restore_command=prefix)


def test_unsafe_source_dbname_is_rejected_before_native_dbname_argument(tmp_path):
    from types import SimpleNamespace
    from psycopg.pq import TransactionStatus
    from mira.database_recovery import DatabaseRecoveryError, backup_database
    connection = SimpleNamespace(info=SimpleNamespace(transaction_status=TransactionStatus.IDLE,
                                                       dbname='host=remote password=secret'))
    with pytest.raises(DatabaseRecoveryError) as failure:
        backup_database(connection, tmp_path / 'archive', collect_objects=lambda _: [],
                        read_object=lambda _: b'')
    assert 'secret' not in str(failure.value)
