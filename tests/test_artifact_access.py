from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from mira.artifact_access import read_report
from test_original_access import Client


def fixture():
    ws,user,rid,rev,run=[uuid4() for _ in range(5)]
    body=b'<p>original report ABC</p>';digest=sha256(body).hexdigest()
    identity=dict(workspace_id=str(ws),purpose='report',sha256=digest,size_bytes=len(body),media_type='text/html',
                  storage_kind='private_supabase',bucket='mira-evidence-private')
    tables={'workspace_members':[dict(workspace_id=str(ws),user_id=str(user),role='viewer')],
            'reports':[dict(id=str(rid),workspace_id=str(ws),analysis_revision_id=str(rev),report_version=1,
                            review_status='draft',artifact_storage_path=f'{run}/report-v1.html')],
            'analysis_revisions':[dict(id=str(rev),workspace_id=str(ws),analysis_run_id=str(run))],
            'report_artifacts':[dict(report_id=str(rid),workspace_id=str(ws),state='ready',content_sha256=digest,object_identity=identity)]}
    return ws,user,rid,tables,body


def test_private_report_read_survives_lost_local_directory(tmp_path):
    ws,user,rid,tables,body=fixture()
    reader=SimpleNamespace(read=lambda scope,identity:body)
    assert read_report(Client(tables,user),ws,rid,reports_dir=tmp_path/'missing',objects=reader)==body
    tables['workspace_members']=[]
    with pytest.raises(PermissionError):read_report(Client(tables,user),ws,rid,objects=reader)


def test_ready_missing_remote_does_not_substitute_local_or_foreign_html(tmp_path):
    ws,user,rid,tables,body=fixture()
    local=tmp_path/tables['reports'][0]['artifact_storage_path'];local.parent.mkdir();local.write_bytes(b'changed')
    def missing(*args):raise FileNotFoundError()
    with pytest.raises(PermissionError):read_report(Client(tables,user),ws,rid,reports_dir=tmp_path,objects=SimpleNamespace(read=missing))
    tables['report_artifacts']=[]
    assert read_report(Client(tables,user),ws,rid,reports_dir=tmp_path)==b'changed'
    tables['reports'][0]['artifact_storage_path']=f'{uuid4()}/report-v1.html'
    with pytest.raises(PermissionError):read_report(Client(tables,user),ws,rid,reports_dir=tmp_path)
