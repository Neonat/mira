"""Worker publication retry. Snapshots remain usable when remote storage fails."""
from hashlib import sha256

from psycopg.types.json import Jsonb

from mira.artifact_storage import worker_object_store
from mira.config import REPORTS_DIR,report_file
from mira.db import acting_as


def publish_report(conn,ws,report_id,actor,body,objects=None):
    digest=sha256(body).hexdigest()
    with acting_as(conn,actor):
        conn.execute('''insert into public.report_artifacts
            (workspace_id,report_id,state,content_sha256,attempts,created_by)
            values(%s,%s,'pending',%s,0,%s) on conflict(report_id) do nothing''',(ws,report_id,digest,actor))
        row=conn.execute('select * from public.report_artifacts where workspace_id=%s and report_id=%s for update',(ws,report_id)).fetchone()
        if not row:
            return False
        if row['content_sha256']!=digest:
            conn.execute("update public.report_artifacts set error_code='ContentMismatch',attempts=attempts+1 where workspace_id=%s and report_id=%s",(ws,report_id))
            return False
    try:
        objects=objects or worker_object_store()
        if objects is None:
            raise ValueError('Private storage disabled')
        identity=objects.put(ws,'report',body,'text/html; charset=utf-8')
        if identity.get('sha256')!=digest or identity.get('workspace_id')!=str(ws) or identity.get('size_bytes')!=len(body):
            raise ValueError('Publication identity mismatch')
        with acting_as(conn,actor):
            conn.execute("update public.report_artifacts set state='ready',object_identity=%s,error_code=null,attempts=attempts+1 where workspace_id=%s and report_id=%s",
                (Jsonb(identity),ws,report_id))
        return True
    except Exception as exc:
        code=type(exc).__name__
        if not code.isidentifier() or len(code)>64:code='StorageError'
        with acting_as(conn,actor):
            conn.execute("update public.report_artifacts set state=case when state='ready' then state else 'failed' end,error_code=%s,attempts=attempts+1 where workspace_id=%s and report_id=%s",(code,ws,report_id))
        return False


def publish_configured_report(conn,ws,report_id,actor,body):
    import os
    if os.environ.get('MIRA_ARTIFACT_STORAGE','local')!='local':
        return publish_report(conn,ws,report_id,actor,body)
    return None


def retry_publications(conn,ws,*,reports_dir=REPORTS_DIR,objects=None):
    rows=conn.execute('''select a.report_id,a.created_by,r.artifact_storage_path
        from public.report_artifacts a join public.reports r on r.id=a.report_id and r.workspace_id=a.workspace_id
        where a.workspace_id=%s and a.state in ('pending','failed')
        and exists(select 1 from public.workspace_members m where m.workspace_id=a.workspace_id and m.user_id=a.created_by and m.role in ('admin','analyst','reviewer'))
        order by a.updated_at limit 20''',(ws,)).fetchall()
    ready=[]
    for row in rows:
        path=report_file(row['artifact_storage_path'],reports_dir)
        try:
            if path is None:
                with acting_as(conn,row['created_by']):
                    conn.execute("update public.report_artifacts set state='failed',error_code='LocalFileUnavailable',attempts=attempts+1 where workspace_id=%s and report_id=%s",(ws,row['report_id']))
            elif publish_report(conn,ws,row['report_id'],row['created_by'],path.read_bytes(),objects):
                ready.append(row['report_id'])
        except Exception:
            # A concurrent membership change or unavailable file must not block
            # the other reports in this bounded retry batch.
            continue
    return ready
