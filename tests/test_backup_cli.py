"""Recovery CLI never connects for verification or unacknowledged SQL restore."""
import os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_backup_help_and_restore_requires_trusted_archive_acknowledgement(tmp_path):
    help_run=subprocess.run([sys.executable,'-m','mira','backup','--help'],cwd=ROOT,capture_output=True,text=True)
    assert help_run.returncode==0 and 'restore' in help_run.stdout
    env={**os.environ,'MIRA_WORKER_DATABASE_URL':'postgresql://invalid.invalid/unused'}
    result=subprocess.run([sys.executable,'-m','mira','backup','restore',str(tmp_path/'missing'),
        '--database','mira_recovery_'+'a'*32],cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==2
    assert '--trusted-backup' in result.stderr
    assert 'invalid.invalid' not in result.stderr


def test_verify_has_no_database_connection_requirement(tmp_path):
    from mira.recovery import create_backup
    dump=tmp_path.resolve()/'fixture.dump';dump.write_bytes(b'opaque native dump fixture')
    package=tmp_path.resolve()/'backup'
    create_backup(package,dump,[],lambda _:b'')
    env={**os.environ,'MIRA_WORKER_DATABASE_URL':'postgresql://invalid.invalid/unused'}
    result=subprocess.run([sys.executable,'-m','mira','backup','verify',str(package)],cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0 and '"verified": true' in result.stdout
    assert 'invalid.invalid' not in result.stdout+result.stderr
