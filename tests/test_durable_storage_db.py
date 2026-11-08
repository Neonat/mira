"""Local SQL checks for immutable report publication and direct bucket access."""
import os
from datetime import date
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from mira.budget import RunBudget
from mira.contracts import Brief,ReportSnapshot
from mira.db import acting_as
from mira.pg_store import PostgresStore,create_run
from test_pipeline_db import conn,workspace

pytestmark=pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'),reason='local test PostgreSQL required')

@pytest.fixture
def artifact(conn,workspace,tmp_path):
    ws,user=workspace
    ctx=create_run(conn,ws,user,Brief(topic='AML/CFT',jurisdictions=['HK'],period_start=date(2025,11,4),
        period_end=date(2026,11,4),as_of_date=date(2026,11,4),plan_requires_approval=False),RunBudget(),{})
    snap=ReportSnapshot(contract_version='1.4',analysis_run_id=ctx.analysis_run_id,analysis_revision_id=ctx.analysis_revision_id,
        sections=[],coverage=[],unresolved_finding_ids=[])
    report=PostgresStore(conn,reports_dir=tmp_path).save_report(ctx,snap,'<p>fixture</p>')
    identity=dict(workspace_id=str(ws),purpose='report',sha256='a'*64,size_bytes=14,media_type='text/html',
        storage_kind='private_supabase',bucket='mira-evidence-private')
    return ws,user,report,identity


def register(conn,artifact,state='ready'):
    ws,user,report,identity=artifact
    with acting_as(conn,user):
        conn.execute('insert into public.report_artifacts(workspace_id,report_id,state,content_sha256,object_identity,attempts,created_by) values(%s,%s,%s,%s,%s,1,%s)',
            (ws,report,state,identity['sha256'],Jsonb(identity) if state=='ready' else None,user))


def test_report_identity_cannot_be_rebound_or_written_by_app(conn,artifact):
    ws,user,report,identity=artifact;register(conn,artifact)
    with acting_as(conn,user):
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute("update public.report_artifacts set object_identity=jsonb_set(object_identity,'{sha256}',%s) where report_id=%s",(Jsonb('b'*64),report))
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) n from public.report_artifacts where report_id=%s',(report,)).fetchone()['n']==1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction():conn.execute('delete from public.report_artifacts where report_id=%s',(report,))


def test_private_bucket_read_requires_published_reference_and_membership(conn,artifact):
    ws,user,report,identity=artifact
    key=f'{ws}/report/'+identity['sha256']+'.bin'
    conn.execute('insert into storage.objects(bucket_id,name) values(%s,%s)',('mira-evidence-private',key))
    with acting_as(conn,user):
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) n from storage.objects where bucket_id=%s and name=%s',('mira-evidence-private',key)).fetchone()['n']==0
    register(conn,artifact)
    with acting_as(conn,user):
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) n from storage.objects where bucket_id=%s and name=%s',('mira-evidence-private',key)).fetchone()['n']==1
    other=uuid4()
    with acting_as(conn,other):
        conn.execute('set local role authenticated')
        assert conn.execute('select count(*) n from storage.objects where bucket_id=%s and name=%s',('mira-evidence-private',key)).fetchone()['n']==0


def test_app_cannot_make_reserved_bucket_public_even_with_broad_policy(conn,artifact):
    ws,user,_,_=artifact
    with conn.transaction(force_rollback=True):
        conn.execute('grant update,delete on storage.buckets to authenticated')
        conn.execute('create policy fixture_broad_bucket_select on storage.buckets for select to authenticated using(true)')
        conn.execute('create policy fixture_broad_bucket_update on storage.buckets for update to authenticated using(true) with check(true)')
        conn.execute('create policy fixture_broad_bucket_delete on storage.buckets for delete to authenticated using(true)')
        with acting_as(conn,user):
            conn.execute('set local role authenticated')
            assert conn.execute("update storage.buckets set public=true where id='mira-evidence-private'").rowcount==0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("delete from storage.buckets where id='mira-evidence-private'")
        assert conn.execute("select public from storage.buckets where id='mira-evidence-private'").fetchone()['public'] is False


@pytest.mark.parametrize('change', ['revoked','reference','inactive','store_permission'])
def test_direct_original_reads_recheck_current_grant_despite_broad_object_policy(conn,workspace,change):
    ws,user=workspace
    source=conn.execute("select id from public.sources where workspace_id=%s and source_key='hkma'",(ws,)).fetchone()['id']
    grant={'original_retention':{'approved':True,'reference':'fixture-original-approval'}}
    conn.execute('update public.sources set connector_config=connector_config||%s where id=%s',(Jsonb(grant),source))
    doc=conn.execute("insert into public.documents(workspace_id,source_id,title) values(%s,%s,'fixture original') returning id",(ws,source)).fetchone()['id']
    identity=dict(workspace_id=str(ws),purpose='original',sha256='c'*64,size_bytes=3,media_type='application/pdf',
                  storage_kind='private_supabase',bucket='mira-evidence-private',approval_reference='fixture-original-approval')
    conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status,metadata) values(%s,%s,1,%s,'https://example.org/f.pdf','Fixture','complete',%s)",
        (ws,doc,'d'*64,Jsonb(dict(original_retained=True,retained_original=identity))))
    key=f'{ws}/original/'+identity['sha256']+'.bin'
    conn.execute('insert into storage.objects(bucket_id,name) values(%s,%s)',('mira-evidence-private',key))
    with conn.transaction(force_rollback=True):
        conn.execute('create policy fixture_broad_object_read on storage.objects for select to authenticated using(true)')
        with acting_as(conn,user):
            conn.execute('set local role authenticated')
            assert conn.execute('select count(*) n from storage.objects where bucket_id=%s and name=%s',('mira-evidence-private',key)).fetchone()['n']==1
        if change=='inactive':conn.execute('update public.sources set is_active=false where id=%s',(source,))
        elif change=='store_permission':conn.execute("update public.sources set permitted_operations=array['metadata','fetch'] where id=%s",(source,))
        else:
            if change=='revoked':grant['original_retention']['approved']=False
            else:grant['original_retention']['reference']='changed'
            conn.execute('update public.sources set connector_config=connector_config||%s where id=%s',(Jsonb(grant),source))
        with acting_as(conn,user):
            conn.execute('set local role authenticated')
            assert conn.execute('select count(*) n from storage.objects where bucket_id=%s and name=%s',('mira-evidence-private',key)).fetchone()['n']==0
