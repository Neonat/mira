"""Consistent full PostgreSQL exports and guarded local recovery.

Command prefixes are trusted operator configuration (including Docker wrappers),
never shell input. Roles and server extensions must already exist in the local
cluster. The caller creates the empty recovery DB; this module never creates,
cleans, drops, migrates or replaces a database.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import ipaddress
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import tempfile
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from .recovery import (BackupError, MAX_DATABASE_BYTES, create_backup,
                       restore_backup, verify_backup)


class DatabaseRecoveryError(BackupError):
    """Safe failure without DSNs, credentials, subprocess output or SQL details."""


def _fail():
    raise DatabaseRecoveryError('Database recovery operation refused or failed')


def _loopback(value):
    if value == 'localhost':
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class PgTools:
    dump_command: tuple[str, ...] = ('pg_dump',)
    restore_command: tuple[str, ...] = ('pg_restore',)
    timeout_seconds: float = 120

    def __post_init__(self):
        if (isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            _fail()
        for field in ('dump_command', 'restore_command'):
            value = getattr(self, field)
            if (not isinstance(value, (tuple, list)) or not value
                    or any(not isinstance(arg, str) or not arg or '\x00' in arg for arg in value)):
                _fail()
            utility = 'pg_dump' if field == 'dump_command' else 'pg_restore'
            _validate_command(tuple(value), utility)
            object.__setattr__(self, field, tuple(value))


def _validate_command(command, utility):
    """Accept explicit transport syntax, never PostgreSQL option abbreviations."""
    if any('password=' in arg.lower() or 'postgres://' in arg.lower()
           or 'postgresql://' in arg.lower() for arg in command):
        _fail()
    executable = Path(command[0]).name
    if executable == 'docker':
        if len(command) < 4 or command[1] != 'exec':
            _fail()
        position = 2
        while position < len(command) and command[position] in ('-i', '--interactive'):
            position += 1
        # Exactly one literal container name followed by the native utility.
        if (position + 1 >= len(command) or command[position].startswith('-')
                or Path(command[position + 1]).name != utility):
            _fail()
        position += 2
    elif executable == utility:
        position = 1
    elif (re.fullmatch(r'(python|pypy)([0-9]+(\.[0-9]+)*)?', executable)
          and len(command) == 2 and not command[1].startswith('-')
          and command[1].endswith('.py')):
        # Isolated tests inject a runtime plus one literal fixture script.
        # The script is trusted executable configuration, never shell content.
        return
    else:
        _fail()
    long_options = {'--host': 'host', '--port': 'port', '--username': 'username'}
    short_options = {'-h': 'host', '-p': 'port', '-U': 'username'}
    while position < len(command):
        arg = command[position]
        position += 1
        if arg in long_options or arg in short_options:
            kind = (long_options | short_options)[arg]
            if position >= len(command):
                _fail()
            value = command[position]
            position += 1
        elif '=' in arg and arg.split('=', 1)[0] in long_options:
            option, value = arg.split('=', 1)
            kind = long_options[option]
        elif len(arg) > 2 and arg[:2] in short_options:
            kind, value = short_options[arg[:2]], arg[2:]
        else:
            _fail()
        if not value or value.startswith('-'):
            _fail()
        if kind == 'host':
            local_socket = value.startswith('/') and '..' not in Path(value).parts and ',' not in value
            if not local_socket and not _loopback(value):
                _fail()
        elif kind == 'port':
            if not value.isdecimal() or not 1 <= int(value) <= 65535:
                _fail()
        elif re.fullmatch(r'[A-Za-z_][A-Za-z_0-9$-]{0,62}', value) is None:
            _fail()



def _one(conn, query, params=None):
    with conn.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()[0]


def _environment(conn):
    # libpq parameters are passed through the environment, never in argv. Drop
    # ambient libpq settings so they cannot redirect the chosen connection.
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    parameters = conn.info.get_parameters()
    mapping = {'host': 'PGHOST', 'hostaddr': 'PGHOSTADDR', 'port': 'PGPORT', 'user': 'PGUSER',
               'dbname': 'PGDATABASE', 'sslmode': 'PGSSLMODE', 'sslrootcert': 'PGSSLROOTCERT',
               'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY', 'sslcrl': 'PGSSLCRL'}
    for key, variable in mapping.items():
        if parameters.get(key):
            env[variable] = parameters[key]
    env['PGPASSWORD'] = conn.info.password or ''
    env['PGCONNECT_TIMEOUT'] = '10'
    env['PGPASSFILE'] = os.devnull
    return env


def _capture(command, output, *, env, timeout, limit, input_path=None):
    """Bound binary stdout by bytes and wall time, and always reap the child."""
    deadline = time.monotonic() + timeout
    input_stream = open(input_path, 'rb') if input_path else None
    process = None
    try:
        process = subprocess.Popen(command, stdin=input_stream or subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            size = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail()
                for key, _ in selector.select(remaining):
                    body = os.read(key.fd, min(1024**2, limit - size + 1))
                    if not body:
                        selector.unregister(key.fd)
                        continue
                    size += len(body)
                    if size > limit:
                        _fail()
                    output.write(body)
            remaining = deadline - time.monotonic()
            if remaining <= 0 or process.wait(timeout=remaining) != 0:
                _fail()
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
        if input_stream is not None:
            input_stream.close()


def backup_database(conn: psycopg.Connection, destination: Path, *,
                    collect_objects: Callable[[psycopg.Connection], Sequence[dict]],
                    read_object: Callable[[dict], bytes], tools: PgTools = PgTools()) -> dict:
    """Export one read-only snapshot, its complete DB, and its object references."""
    try:
        if (conn.info.transaction_status != TransactionStatus.IDLE
                or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9$-]{0,62}', conn.info.dbname) is None):
            _fail()
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            snapshot = _one(conn, 'SELECT pg_catalog.pg_export_snapshot()')
            objects = collect_objects(conn)
            if conn.info.transaction_status != TransactionStatus.INTRANS:
                _fail()
            with tempfile.TemporaryDirectory(prefix='mira-database-backup-') as directory:
                dump = Path(directory).resolve() / 'database.dump'
                fd = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as output:
                    os.fchmod(output.fileno(), 0o600)
                    _capture((*tools.dump_command, '--format=custom', '--snapshot=' + snapshot,
                              '--dbname=' + conn.info.dbname), output,
                             env=_environment(conn), timeout=tools.timeout_seconds, limit=MAX_DATABASE_BYTES)
                    output.flush()
                    os.fsync(output.fileno())
                return create_backup(destination, dump, objects, read_object)
    except BackupError:
        raise
    except Exception:
        raise DatabaseRecoveryError('Database backup failed') from None




def _target_parameters(dsn):
    params = conninfo_to_dict(dsn)
    allowed = {'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode',
               'sslrootcert', 'sslcert', 'sslkey', 'connect_timeout', 'application_name'}
    if (params.keys() - allowed or not _loopback(params.get('host', ''))
            or ('hostaddr' in params and not _loopback(params['hostaddr']))
            or re.fullmatch(r'mira_recovery_(?:test_)?[0-9a-f]{32}', params.get('dbname', '')) is None):
        _fail()
    port = params.get('port', '5432')
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        _fail()
    # Pin hostaddr as well: ambient PGHOSTADDR must not redirect localhost.
    params.setdefault('hostaddr', '127.0.0.1' if params['host'] == 'localhost' else params['host'])
    params['port'] = port
    params['connect_timeout'] = '10'
    params['application_name'] = 'mira-recovery-guard'
    return params


def _assert_empty_target(conn, name):
    if (_one(conn, 'SELECT pg_catalog.current_database()') != name
            or _one(conn, 'SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE datname=%s AND pid<>pg_catalog.pg_backend_pid()', (name,))
            or _one(conn, "SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname !~ '^pg_'")
            or _one(conn, "SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'")
            or _one(conn, "SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')")
            or _one(conn, "SELECT count(*) FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast'")
            or _one(conn, "SELECT count(*) FROM pg_catalog.pg_extension WHERE extname<>'plpgsql'")
            or _one(conn, 'SELECT count(*) FROM pg_catalog.pg_foreign_server')
            or _one(conn, 'SELECT count(*) FROM pg_catalog.pg_largeobject_metadata')
            or _one(conn, 'SELECT datistemplate OR NOT datallowconn FROM pg_catalog.pg_database WHERE datname=%s', (name,))):
        _fail()


def _source_name(archive, tools):
    # Native list header records the source DB name. Capture it privately;
    # do not trust an operator's target name to imply it differs from source.
    with tempfile.TemporaryFile(mode='w+b') as output:
        _capture((*tools.restore_command, '--list'), output, env={key: value for key, value in os.environ.items() if not key.startswith('PG')},
                 timeout=tools.timeout_seconds, limit=8 * 1024**2,
                 input_path=Path(archive) / 'database.dump')
        output.seek(0)
        header = output.read(64 * 1024).decode('utf-8', errors='strict')
    match = re.search(r'^;\s+dbname: (.+)$', header, re.MULTILINE)
    if not match:
        _fail()
    return match.group(1)


def restore_database(archive: Path, target_dsn: str, *,
                     write_object: Callable[[dict, bytes], None], tools: PgTools = PgTools(),
                     trusted_backup: bool = False) -> dict:
    """Restore an operator-created trusted archive into an empty local DB.

    Native pg_restore executes archive SQL with the target role's permissions.
    Checksums detect corruption, not authorship; an operator must explicitly
    acknowledge a trusted archive with trusted_backup=True before any tools,
    database connection or object writes are permitted.
    """
    if trusted_backup is not True:
        _fail()
    manifest = verify_backup(archive)
    try:
        params = _target_parameters(target_dsn)
        if _source_name(archive, tools) == params['dbname']:
            _fail()
        with psycopg.connect(**params, autocommit=True) as target:
            # Serialize cooperating recovery workers without changing target data.
            if not _one(target, 'SELECT pg_catalog.pg_try_advisory_lock(pg_catalog.hashtext(%s))', (params['dbname'],)):
                _fail()
            _assert_empty_target(target, params['dbname'])
            def publish_database(dump):
                _assert_empty_target(target, params['dbname'])
                with open(dump, 'rb') as input_stream:
                    subprocess.run((*tools.restore_command, '--exit-on-error', '--single-transaction',
                                    '--dbname=' + params['dbname']), stdin=input_stream,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=_environment(target), timeout=tools.timeout_seconds, check=True)
            restore_backup(archive, write_object=write_object, restore_database=publish_database)
        return {'schema_version': 1, 'database_restored': True, 'object_count': len(manifest['objects'])}
    except BackupError:
        raise
    except Exception:
        raise DatabaseRecoveryError('Database restore failed') from None
