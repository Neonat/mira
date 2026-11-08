from types import SimpleNamespace
import os

import pytest

from mira.hybrid import EmbeddingIdentity, HybridLimits
from mira.hybrid_runtime import HybridRetriever


def test_runtime_rejects_incompatible_dimension():
    with pytest.raises(ValueError):
        HybridRetriever(None, EmbeddingIdentity('m', 'r', 2), HybridLimits())


def test_database_filters_before_limit_and_reuses_content_bound_cache(monkeypatch):
    import uuid
    import psycopg
    from psycopg.rows import dict_row
    from datetime import date
    from mira.hybrid import EmbeddingResult

    class Embed:
        calls = []
        timeouts = []
        def embed(self, texts, *, timeout_seconds):
            self.calls.append(list(texts))
            self.timeouts.append(timeout_seconds)
            return EmbeddingResult(tuple((1.,) + (0.,) * 383 for _ in texts), len(texts))

    dsn = os.getenv('MIRA_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('MIRA_TEST_DATABASE_URL not set')
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        ws = conn.execute("insert into public.workspaces (slug,name) values (%s,'fixture') returning id", (str(uuid.uuid4()),)).fetchone()['id']
        other = conn.execute("insert into public.workspaces (slug,name) values (%s,'fixture') returning id", (str(uuid.uuid4()),)).fetchone()['id']
        user_id = uuid.uuid4()
        conn.execute("insert into auth.users (id) values (%s)", (user_id,))
        conn.execute("insert into public.workspace_members (workspace_id,user_id,role) values (%s,%s,'analyst')", (ws,user_id))
        source_ids = []
        def source(workspace, ops, active=True, jurisdiction='HK'):
            row = conn.execute("insert into public.sources (workspace_id,source_key,name,source_type,jurisdiction_code,permitted_operations,is_active) values (%s,%s,'fixture','website',%s,%s,%s) returning id", (workspace,str(uuid.uuid4()),jurisdiction,ops,active)).fetchone()
            source_ids.append(row['id'])
            return row['id']
        def document(workspace, src, versions, manual=False):
            doc = conn.execute("insert into public.documents (workspace_id,source_id,title) values (%s,%s,'fixture') returning id", (workspace,src)).fetchone()['id']
            for number, day, content in versions:
                version = conn.execute("insert into public.document_versions (workspace_id,document_id,version_number,content_sha256,source_url,title,published_at,extraction_status,metadata) values (%s,%s,%s,%s,'https://example.com','fixture',%s,'complete',%s::jsonb) returning id", (workspace,doc,number,format(number, '064x'),day, '{"import":"manual"}' if manual else '{}')).fetchone()['id']
                conn.execute("insert into public.document_passages (workspace_id,document_version_id,passage_number,content) values (%s,%s,1,%s)", (workspace,version,content))
        ops=['fetch','store_text','embed']
        valid = source(ws,ops)
        document(ws,valid,[(1,'2020-01-01','stale'),(2,'2021-01-01','eligible'),(3,'2030-01-01','future')])
        for src in (source(ws,ops,False),source(ws,['fetch','store_text']),source(ws,ops,True,'SG')):
            document(ws,src,[(1,'2020-01-01','excluded')])
        manual = source(ws,['store_text','embed'])
        document(ws,manual,[(1,'2020-01-01','manual eligible')],manual=True)
        foreign = source(other,ops)
        document(other,foreign,[(1,'2020-01-01','foreign')])
        ctx = SimpleNamespace(workspace_id=ws, user_id=user_id, brief=SimpleNamespace(jurisdictions=['HK'], as_of_date=date(2025,1,1)))
        task = SimpleNamespace(source_ids=source_ids, jurisdiction_code='HK', question='eligible')
        embedder = Embed()
        retriever = HybridRetriever(embedder, EmbeddingIdentity('fixture','1'), HybridLimits(max_index_passages=2))
        first = retriever.retrieve(conn,ctx,task,remaining_tokens=20000,remaining_seconds=10)
        assert {p.content for p in first.passages} == {'eligible', 'manual eligible'}
        second = retriever.retrieve(conn,ctx,task,remaining_tokens=20000,remaining_seconds=10)
        assert set(embedder.calls[0]) == {'eligible', 'manual eligible'}
        assert embedder.calls[1] == ['eligible']
        assert second.tokens == 1
        from mira.db import acting_as
        with pytest.raises(psycopg.Error), acting_as(conn,user_id):
            conn.execute("update public.hybrid_passage_vectors set content_sha256=%s where workspace_id=%s", ('b'*64, ws))
        revised = HybridRetriever(embedder, EmbeddingIdentity('fixture','2'), HybridLimits(max_index_passages=2))
        revised.retrieve(conn,ctx,task,remaining_tokens=20000,remaining_seconds=10)
        assert len(embedder.calls[-1]) == 3
        assert conn.execute("select count(*) as n from public.audit_events where workspace_id=%s and entity_type='hybrid_passage_vectors' and actor_id=%s",(ws,user_id)).fetchone()['n'] == 4
        international = source(ws,ops,True,None)
        document(ws,international,[(1,'2020-01-01','international eligible')])
        intl_task = SimpleNamespace(source_ids=source_ids, jurisdiction_code=None, question='international')
        international_result = retriever.retrieve(conn,ctx,intl_task,remaining_tokens=20000,remaining_seconds=10)
        assert [p.content for p in international_result.passages] == ['international eligible']
        import time
        from mira.pg_store import PostgresStore
        original_get = PostgresStore.get_passages
        def slow_get(self, *args):
            time.sleep(0.1)
            return original_get(self, *args)
        with monkeypatch.context() as patch:
            patch.setattr(PostgresStore, 'get_passages', slow_get)
            retriever.retrieve(conn,ctx,intl_task,remaining_tokens=20000,remaining_seconds=0.5)
        assert 0 < embedder.timeouts[-1] < 0.45
        with pytest.raises(psycopg.errors.QueryCanceled), conn.transaction():
            HybridRetriever._timeout(conn, time.monotonic() + 0.05)
            conn.execute('select pg_sleep(1)')
        # Authenticated members can read only their workspace and cannot insert.
        other_user = uuid.uuid4()
        conn.execute("insert into auth.users (id) values (%s)", (other_user,))
        conn.execute("insert into public.workspace_members (workspace_id,user_id,role) values (%s,%s,'analyst')", (other,other_user))
        with acting_as(conn,user_id):
            conn.execute('set local role authenticated')
            assert conn.execute('select count(*) as n from public.hybrid_passage_vectors where workspace_id=%s',(ws,)).fetchone()['n'] == 5
            with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
                conn.execute("insert into public.hybrid_passage_vectors select * from public.hybrid_passage_vectors limit 1")
            conn.execute('reset role')
        with acting_as(conn,other_user):
            conn.execute('set local role authenticated')
            assert conn.execute('select count(*) as n from public.hybrid_passage_vectors where workspace_id=%s',(ws,)).fetchone()['n'] == 0
            conn.execute('reset role')
        # A worker without an actor cannot insert, even with SQL write privileges.
        with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
            conn.execute("insert into public.hybrid_passage_vectors select workspace_id,passage_id,model,'noactor',dimensions,content_sha256,embedding,created_at from public.hybrid_passage_vectors where workspace_id=%s limit 1",(ws,))
        # Lexical scout retrieval shares the same permission and jurisdiction gate,
        # while permitting store_text sources that do not grant embeddings.
        from mira.agents.scout import _ScoutRun
        from mira.pg_store import PostgresStore
        import threading
        from datetime import datetime, UTC
        from types import SimpleNamespace as NS
        ctx.brief.topic = 'test'
        ctx.brief.period_start = date(2019, 1, 1)
        ctx.brief.period_end = date(2025, 1, 1)
        ctx.analysis_run_id = uuid.uuid4()
        task.max_llm_tokens = 5000
        task.max_minutes = None
        run = _ScoutRun.__new__(_ScoutRun)
        run.scout = NS(_fetch_lock=threading.Lock(), _pages={}, hybrid=None)
        run.conn, run.ctx, run.task = conn, ctx, task
        run.store = PostgresStore(conn)
        run.visits, run.hybrid_diagnostics = [], None
        run.tokens_in = run.tokens_out = run.hybrid_tokens = run.hybrid_reserved_tokens = 0
        run._started = 0
        contents = {p.content for p in run._passages()}
        assert contents == {'eligible', 'excluded', 'manual eligible'}
        from mira.hybrid import HybridResult
        class Failure:
            calls = 0
            def retrieve(self, *args, **kwargs):
                self.calls += 1
                return HybridResult([], (), reserved_tokens=50, fallback_reason='embedding_failed')
        failure = Failure()
        run.scout.hybrid = failure
        assert {p.content for p in run._passages()} == contents
        run._passages()
        assert failure.calls == 1
        assert run.hybrid_diagnostics['reserved_tokens'] == 50
        assert run._remaining_tokens() == 4950
        class Success:
            identity = EmbeddingIdentity('fixture', '1')
            calls = 0
            def retrieve(self, *args, **kwargs):
                self.calls += 1
                return HybridResult(first.passages, (), tokens=30)
        success = Success()
        run.hybrid_diagnostics = None
        run.scout.hybrid = success
        run._passages()
        run._passages()
        assert success.calls == 1
        assert run.tokens_in == 0 and run.hybrid_tokens == 30
        assert run._remaining_tokens() == 4920
        assert run.hybrid_diagnostics['model'] == 'fixture'
        run.scout.hybrid = None
        run.task = intl_task
        assert {p.content for p in run._passages()} == {'international eligible'}
        conn.rollback()
