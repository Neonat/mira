"""Authenticated report reads, with verified private copies preferred over local files."""
from hashlib import sha256
from uuid import UUID

from mira.config import REPORTS_DIR,report_file
from mira.original_access import _row,_ROLES
from mira.private_objects import PrivateObjectStore


def read_report(client,workspace_id,report_id,*,reports_dir=REPORTS_DIR,objects=None):
    try:
        if not isinstance(workspace_id,UUID) or not isinstance(report_id,UUID):raise ValueError('identity')
        user=client.auth.get_user().user
        if not user:raise ValueError('auth')
        member=_row(client,'workspace_members','role',workspace_id=workspace_id,user_id=user.id)
        if member.get('role') not in _ROLES:raise ValueError('role')
        report=_row(client,'reports','artifact_storage_path,analysis_revision_id,report_version,review_status',
                    id=report_id,workspace_id=workspace_id)
        refs=client.table('report_artifacts').select('state,object_identity,content_sha256').eq('workspace_id',str(workspace_id)).eq('report_id',str(report_id)).execute().data
        if not isinstance(refs,list) or len(refs)>1:raise ValueError('reference')
        ref=refs[0] if refs else None
        if ref and ref['state']=='ready':
            identity=ref['object_identity']
            if identity.get('purpose')!='report' or identity.get('sha256')!=ref['content_sha256']:raise ValueError('binding')
            return (objects or PrivateObjectStore(client)).read(workspace_id,identity)
        revision=_row(client,'analysis_revisions','analysis_run_id',id=report['analysis_revision_id'],workspace_id=workspace_id)
        run=str(UUID(revision['analysis_run_id']))
        suffix='-reviewed' if report['review_status']=='reviewed' else ''
        expected=f"{run}/report-v{int(report['report_version'])}{suffix}.html"
        if report['artifact_storage_path']!=expected:raise ValueError('path binding')
        path=report_file(expected,reports_dir)
        if path is None or path.stat().st_size>20_000_000:raise ValueError('file')
        body=path.read_bytes()
        if ref and sha256(body).hexdigest()!=ref['content_sha256']:raise ValueError('digest')
        return body
    except Exception:
        raise PermissionError('Report file is unavailable') from None
