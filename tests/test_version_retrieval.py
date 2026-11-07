"""Regression checks against an isolated, rolled-back local Postgres workspace."""
import os
from concurrent.futures import Future
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from mira.agents.scout import WebScout, _ScoutRun, _Visit
from mira.db import connect

DSN = os.environ.get('MIRA_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='MIRA_TEST_DATABASE_URL not set')

@pytest.fixture
def setup_run():
    with connect(DSN) as conn, conn.transaction(force_rollback=True):
        workspace = conn.execute("insert into public.workspaces (slug,name) values (%s,'version test') returning id", (str(uuid4()),)).fetchone()['id']
        source = conn.execute("insert into public.sources (workspace_id,source_key,name,source_type,permitted_operations) values (%s,%s,'test','website',array['metadata','fetch','store_text']) returning id", (workspace,str(uuid4()))).fetchone()['id']
        brief = SimpleNamespace(topic='AML', period_start=date(2025,1,1), period_end=date(2026,12,31), as_of_date=date(2026,12,31))
        ctx = SimpleNamespace(workspace_id=workspace, user_id=uuid4(), analysis_run_id=uuid4(), brief=brief)
        task = SimpleNamespace(source_ids=(source,), question='money laundering', max_documents=1)
        run = _ScoutRun(WebScout('', None, None), conn, ctx, uuid4(), task)
        def document():
            return conn.execute("insert into public.documents (workspace_id,source_id,title,canonical_url) values (%s,%s,'test',%s) returning id", (workspace,source,'https://example.org/'+str(uuid4()))).fetchone()['id']
        def version(doc, number, published, content):
            v = conn.execute("insert into public.document_versions (workspace_id,document_id,version_number,content_sha256,source_url,title,published_at,extraction_status,extracted_text) values (%s,%s,%s,%s,%s,'test',%s,'complete',%s) returning id", (workspace,doc,number,uuid4().hex + uuid4().hex,'https://example.org/'+str(doc),published,content)).fetchone()['id']
            p = conn.execute("insert into public.document_passages (workspace_id,document_version_id,passage_number,content) values (%s,%s,1,%s) returning id", (workspace,v,content)).fetchone()['id']
            return v,p
        yield run, document, version

def test_only_latest_eligible_version_including_visits_and_shared_cache(setup_run):
    run, document, version = setup_run
    doc = document()
    old, oldp = version(doc,1,date(2026,1,1),'money laundering obsolete')
    new, newp = version(doc,2,date(2026,1,1),'money laundering current')
    run.visits.append(_Visit('https://example.org/old',old,[oldp]))
    future = Future(); future.set_result((None,_Visit('https://example.org/old',old,[oldp])))
    run.scout._pages[(run.ctx.workspace_id,run.ctx.analysis_run_id,'old')] = future
    assert {p.id for p in run._passages()} == {newp}

def test_future_latest_falls_back_to_older_eligible(setup_run):
    run, document, version = setup_run
    doc = document()
    _, oldp = version(doc,1,date(2026,1,1),'older publication')
    version(doc,2,date(2027,1,1),'future publication')
    assert {p.id for p in run._passages()} == {oldp}


def test_obsolete_search_hits_do_not_consume_search_limit(setup_run):
    run, document, version = setup_run
    doc = document()
    for number in range(1, 17):
        version(doc, number, date(2024, 1, 1), 'money laundering money laundering')
    version(doc, 17, date(2024, 1, 1), 'replacement without keywords')
    target = document()
    _, passage = version(target, 1, date(2024, 1, 1), 'money laundering target')
    assert passage in {p.id for p in run._passages()}


def test_manual_import_and_source_workspace_isolation(setup_run):
    run, document, version = setup_run
    doc = document()
    v, passage = version(doc, 1, None, 'manual content')
    run.conn.execute("update public.document_versions set metadata = '{\"import\":\"manual\"}' where id = %s", (v,))
    other = run.conn.execute("insert into public.sources (workspace_id,source_key,name,source_type,permitted_operations) values (%s,%s,'other','website',array['metadata','fetch','store_text']) returning id", (run.ctx.workspace_id,str(uuid4()))).fetchone()['id']
    outsider = document()
    run.conn.execute('update public.documents set source_id = %s where id = %s', (other, outsider))
    _, forbidden = version(outsider, 1, date(2026,1,1), 'money laundering forbidden')
    run.visits.append(_Visit('https://example.org/forbidden', None, [forbidden]))
    assert {p.id for p in run._passages()} == {passage}


def test_foreign_workspace_visit_is_excluded(setup_run):
    run, _, _ = setup_run
    conn = run.conn
    ws = conn.execute("insert into public.workspaces (slug,name) values (%s,'other') returning id", (str(uuid4()),)).fetchone()['id']
    source = conn.execute("insert into public.sources (workspace_id,source_key,name,source_type,permitted_operations) values (%s,%s,'other','website',array['metadata','fetch','store_text']) returning id", (ws,str(uuid4()))).fetchone()['id']
    doc = conn.execute("insert into public.documents (workspace_id,source_id,title) values (%s,%s,'foreign') returning id", (ws,source)).fetchone()['id']
    v = conn.execute("insert into public.document_versions (workspace_id,document_id,version_number,content_sha256,source_url,title,extraction_status) values (%s,%s,1,%s,'https://example.org/foreign','foreign','complete') returning id", (ws,doc,uuid4().hex + uuid4().hex)).fetchone()['id']
    p = conn.execute("insert into public.document_passages (workspace_id,document_version_id,passage_number,content) values (%s,%s,1,'money laundering') returning id", (ws,v)).fetchone()['id']
    run.visits.append(_Visit('https://example.org/foreign',v,[p]))
    assert run._passages() == []
