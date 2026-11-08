"""Operator-only recovery commands. They never run research or change source grants."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


def add_backup_commands(commands):
    backup=commands.add_parser('backup',help='create/verify a complete private backup or recover a fresh local database')
    actions=backup.add_subparsers(dest='backup_action',required=True)
    for action in ('create','verify','restore'):
        parser=actions.add_parser(action)
        parser.add_argument('path',type=Path)
        if action!='verify':
            parser.add_argument('--postgres-container',help='explicit local test PostgreSQL container; otherwise native tools are used')
            parser.add_argument('--originals-dir',type=Path)
            parser.add_argument('--reports-dir',type=Path)
        if action=='restore':
            parser.add_argument('--database',required=True,help='operator-created empty local mira_recovery_<32hex> database')
            parser.add_argument('--trusted-backup',action='store_true',help='acknowledge this operator-created backup is trusted: native archive restore executes SQL')
    return backup


def execute_backup(args):
    from mira.database_recovery import PgTools,backup_database,restore_database
    from mira.recovery import BackupError,verify_backup
    if args.backup_action=='restore' and not args.trusted_backup:
        print('Restore requires --trusted-backup for an operator-created archive; native restore executes SQL.',file=__import__('sys').stderr)
        return 2
    try:
        if args.backup_action=='verify':
            manifest=verify_backup(args.path)
            print(json.dumps({'verified':True,'object_count':len(manifest['objects'])}))
            return 0
        from psycopg.conninfo import conninfo_to_dict,make_conninfo
        from mira.db import connect
        from mira.artifact_storage import worker_object_store
        from mira.originals import PrivateOriginalStore,RetentionPolicy
        from mira.recovery_storage import ArchiveObjects
        from mira.config import REPO_ROOT,REPORTS_DIR
        dsn=os.environ['MIRA_WORKER_DATABASE_URL']
        tools=PgTools()
        if args.postgres_container:
            if not re.fullmatch(r'supabase_db_[A-Za-z0-9_-]+',args.postgres_container) or urlsplit(dsn).hostname not in ('127.0.0.1','localhost','::1'):
                raise ValueError('Only an explicit local PostgreSQL test container is allowed')
            prefix=('docker','exec','-i',args.postgres_container)
            options=('--host=/var/run/postgresql','--port=5432','--username=postgres')
            tools=PgTools(dump_command=prefix+('pg_dump',)+options,restore_command=prefix+('pg_restore',)+options)
        originals=args.originals_dir or Path(os.environ.get('MIRA_ORIGINALS_DIR') or REPO_ROOT/'private-originals')
        reports=args.reports_dir or REPORTS_DIR
        objects=ArchiveObjects(PrivateOriginalStore(originals,RetentionPolicy.from_env()),reports,worker_object_store())
        if args.backup_action=='create':
            with connect(dsn) as conn:
                result=backup_database(conn,args.path,collect_objects=objects.collect,read_object=objects.read,tools=tools)
            summary={'backup_created':True,'object_count':len(result['objects'])}
        else:
            params=conninfo_to_dict(dsn);params['dbname']=args.database
            summary=restore_database(args.path,make_conninfo(**params),write_object=objects.write,tools=tools,trusted_backup=True)
        print(json.dumps(summary))
        return 0
    except (BackupError,ValueError,OSError,KeyError):
        print('Backup/recovery refused or failed; check private storage, tools, package integrity and the empty local target.',file=__import__('sys').stderr)
        return 2
