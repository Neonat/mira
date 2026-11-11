"""Report durability survives upload failure and local-file loss, without rebinding."""
import os
from hashlib import sha256

import pytest
from psycopg.types.json import Jsonb

from mira.db import acting_as
from test_durable_storage_db import conn,workspace,artifact

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local DB required')

class Objects:
    fail=False
    def __init__(self):
        self.blobs={}
    def put(self,ws,purpose,body,media_type):
        if self.fail:raise ValueError('fixture unavailable')
        identity=dict(workspace_id=str(ws),purpose=purpose,sha256=sha256(body).hexdigest(),size_bytes=len(body),
                      media_type=media_type,storage_kind='private_supabase',bucket='mira-evidence-private')
        self.blobs[identity['sha256']]=body
        return identity
    def read(self,ws,identity):
        return self.blobs[identity['sha256']]


def test_failed_publication_retries_same_content_and_refuses_rebinding(conn,artifact):
    from mira.artifact_jobs import publish_report
    ws,user,rid,_=artifact
    objects=Objects();objects.fail=True
    assert publish_report(conn,ws,rid,user,b'<p>ABC</p>',objects) is False
    row=conn.execute('select * from public.report_artifacts where report_id=%s',(rid,)).fetchone()
    assert row['state']=='failed' and row['object_identity'] is None and row['attempts']==1
    objects.fail=False
    assert publish_report(conn,ws,rid,user,b'<p>ABC</p>',objects) is True
    row=conn.execute('select * from public.report_artifacts where report_id=%s',(rid,)).fetchone()
    assert row['state']=='ready' and row['attempts']==2
    assert publish_report(conn,ws,rid,user,b'<p>changed</p>',objects) is False
    assert len(objects.blobs)==1
    assert conn.execute('select object_identity from public.report_artifacts where report_id=%s',(rid,)).fetchone()['object_identity']==row['object_identity']


def test_supabase_originals_keep_explicit_grants_and_local_legacy_read(tmp_path):
    from mira.artifact_storage import OriginalStorage
    from mira.originals import PrivateOriginalStore,RetentionPolicy
    from test_orchestrator import MAS
    from dataclasses import replace
    from uuid import uuid4
    objects=Objects(); ws=uuid4()
    local=PrivateOriginalStore(tmp_path.resolve()/'originals',RetentionPolicy(enabled=True))
    storage=OriginalStorage(local,objects,backend='supabase')
    assert storage.retain(ws,MAS,b'ABC',acquisition_method='http_fetch',content_type='text/html') is None
    source=replace(MAS,connector_config={'original_retention':{'approved':True,'reference':'fixture'}})
    assert storage.retain(ws,source,b'ABC',acquisition_method='live_browser',content_type='text/html') is None
    identity=storage.retain(ws,source,b'ABC',acquisition_method='http_fetch',content_type='text/html')
    assert identity['storage_kind']=='private_supabase' and storage.read(ws,identity)==b'ABC'
    old=local.retain(ws,source,b'legacy',acquisition_method='manual_import',content_type='text/html')
    assert storage.read(ws,old)==b'legacy'


def test_remote_original_obeys_same_configured_byte_cap_as_local(tmp_path):
    from mira.artifact_storage import OriginalStorage
    from mira.originals import PrivateOriginalStore,RetentionPolicy
    from test_orchestrator import MAS
    from dataclasses import replace
    from uuid import uuid4
    ws=uuid4();objects=Objects();objects.blobs={}
    local=PrivateOriginalStore(tmp_path.resolve()/'originals',RetentionPolicy(enabled=True,max_bytes=2))
    storage=OriginalStorage(local,objects,backend='supabase')
    source=replace(MAS,connector_config={'original_retention':{'approved':True,'reference':'fixture'}})
    with pytest.raises(ValueError):storage.retain(ws,source,b'ABC',acquisition_method='http_fetch',content_type='text/html')
    assert not objects.blobs
    identity=objects.put(ws,'original',b'ABC','text/html')
    with pytest.raises(ValueError):storage.read(ws,identity)


def test_unavailable_oldest_reports_do_not_starve_newer_publication(conn,artifact,tmp_path):
    from mira.artifact_jobs import retry_publications
    ws,user,rid,_=artifact; objects=Objects();objects.blobs={}
    reports=tmp_path/'reports';reports.mkdir()
    original=conn.execute('select * from public.reports where id=%s',(rid,)).fetchone()
    run_id = conn.execute(
        'select analysis_run_id from public.analysis_revisions where id=%s and workspace_id=%s',
        (original['analysis_revision_id'], ws),
    ).fetchone()['analysis_run_id']
    ids=[]
    with acting_as(conn,user):
        for n in range(2,23):
            path=f"{run_id}/report-v{n}.html"
            row=conn.execute('''insert into public.reports(workspace_id,analysis_revision_id,report_version,format,review_status,template_version,evidence_snapshot,artifact_storage_path,generated_by)
                values(%s,%s,%s,'html','draft',%s,%s,%s,%s) returning id''',
                (ws,original['analysis_revision_id'],n,original['template_version'],Jsonb(original['evidence_snapshot']),path,user)).fetchone()
            ids.append(row['id'])
            conn.execute("insert into public.report_artifacts(workspace_id,report_id,state,content_sha256,created_by) values(%s,%s,'pending',%s,%s)",
                (ws,row['id'],sha256(b'ABC').hexdigest(),user))
            if n==22:
                file=reports/path;file.parent.mkdir();file.write_bytes(b'ABC')
    retry_publications(conn,ws,reports_dir=reports,objects=objects)
    retry_publications(conn,ws,reports_dir=reports,objects=objects)
    assert conn.execute('select state from public.report_artifacts where report_id=%s',(ids[-1],)).fetchone()['state']=='ready'


def test_real_store_publishes_generated_html_and_reviewed_render(conn,artifact,tmp_path,monkeypatch):
    from mira.artifact_jobs import publish_report
    from mira.pg_store import PostgresStore
    from mira.store import RunContext
    from mira.pg_store import load_run
    from mira.contracts import ReportSnapshot
    from mira.render_job import pending_signoffs,render_one
    from test_pipeline_db import insert_reviewed
    ws,user,rid,_=artifact;objects=Objects();objects.blobs={}
    row=conn.execute('select * from public.reports where id=%s',(rid,)).fetchone()
    runid=conn.execute('select analysis_run_id from public.analysis_revisions where id=%s',(row['analysis_revision_id'],)).fetchone()['analysis_run_id']
    ctx=load_run(conn,runid)
    published=PostgresStore(conn,reports_dir=tmp_path/'reports',artifact_store=objects).save_report(ctx,
        ReportSnapshot.model_validate(row['evidence_snapshot']),'<p>full report ABC</p>')
    ref=conn.execute('select state,object_identity from public.report_artifacts where report_id=%s',(published,)).fetchone()
    assert ref['state']=='ready' and objects.read(ws,ref['object_identity'])==b'<p>full report ABC</p>'
    current=conn.execute('select * from public.reports where id=%s',(published,)).fetchone()
    insert_reviewed(conn,current,user,current['report_version']+1)
    monkeypatch.setenv('MIRA_ARTIFACT_STORAGE','supabase')
    monkeypatch.setattr('mira.artifact_jobs.worker_object_store',lambda:objects)
    pending=pending_signoffs(conn,ws)[0]
    rendered=render_one(conn,ws,pending,tmp_path/'reviewed')
    frozen=conn.execute('select object_identity from public.report_artifacts where report_id=%s',(rendered,)).fetchone()['object_identity']
    assert b'Reviewed' in objects.read(ws,frozen)
