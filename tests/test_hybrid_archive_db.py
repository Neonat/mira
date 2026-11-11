"""Archive-wide retrieval and bounded progressive indexing, no provider calls."""
from datetime import date
from types import SimpleNamespace as NS
from uuid import UUID,uuid4
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from mira.hybrid import EmbeddingIdentity,EmbeddingResult,HybridLimits
from mira.hybrid_runtime import HybridRetriever

pytestmark=pytest.mark.skipif(not os.getenv('MIRA_TEST_DATABASE_URL'),reason='local PostgreSQL required')

@pytest.fixture
def archive():
    with psycopg.connect(os.environ['MIRA_TEST_DATABASE_URL'],row_factory=dict_row) as conn:
        user=uuid4()
        conn.execute('insert into auth.users(id) values(%s)',(user,))
        ws=conn.execute("insert into public.workspaces(slug,name) values(%s,'Archive fixture') returning id",(str(uuid4()),)).fetchone()['id']
        conn.execute("insert into public.workspace_members(workspace_id,user_id,role) values(%s,%s,'analyst')",(ws,user))
        def source(key=None,active=True,ops=None):
            return conn.execute("insert into public.sources(workspace_id,source_key,name,source_type,jurisdiction_code,is_active,permitted_operations) values(%s,%s,'Fixture','website','HK',%s,%s) returning id",(ws,key or str(uuid4()),active,ops or ['store_text','embed'])).fetchone()['id']
        src=source()
        def passage(text,n=None,source_id=None,version=1,document=None,day='2026-01-01'):
            import hashlib
            doc=document or conn.execute("insert into public.documents(workspace_id,source_id,title) values(%s,%s,'Fixture') returning id",(ws,source_id or src)).fetchone()['id']
            v=conn.execute("insert into public.document_versions(workspace_id,document_id,version_number,content_sha256,source_url,title,published_at,extraction_status,metadata) values(%s,%s,%s,%s,%s,'Fixture',%s,'complete','{\"import\":\"manual\"}') returning id",(ws,doc,version,hashlib.sha256(text.encode()).hexdigest(),'https://fixture.invalid/'+str(doc),day)).fetchone()['id']
            pid=UUID(int=n) if n else uuid4()
            conn.execute('insert into public.document_passages(id,workspace_id,document_version_id,passage_number,content) values(%s,%s,%s,1,%s)',(pid,ws,v,text))
            return pid,doc
        class Embed:
            calls=[]
            def embed(self,texts,*,timeout_seconds):
                self.calls.append(list(texts))
                def vec(t):return ((1.,0.) if ('beneficial ownership' in t or 'ultimately owns' in t) else (0.,1.))+(0.,)*382
                return EmbeddingResult(tuple(vec(t) for t in texts),sum(len(t.split()) for t in texts))
        embed=Embed();embed.calls=[]
        ctx=NS(workspace_id=ws,user_id=user,brief=NS(jurisdictions=['HK'],as_of_date=date(2026,11,4)))
        task=NS(source_ids=[src],jurisdiction_code='HK',question='beneficial ownership')
        yield NS(conn=conn,ws=ws,user=user,source=source,src=src,passage=passage,embed=embed,ctx=ctx,task=task)
        conn.rollback()

def retriever(a,**kw):
    return HybridRetriever(a.embed,EmbeddingIdentity('fixture','archive',384),HybridLimits(**kw))

def count(a):
    return a.conn.execute('select count(*) n from public.hybrid_passage_vectors where workspace_id=%s',(a.ws,)).fetchone()['n']

def test_full_archive_over40_and_warm_query_only(archive):
    a=archive
    for i in range(1,122):a.passage('Office stationery and printers.',i)
    wanted,_=a.passage('Identify the natural person who ultimately owns the company.',9000)
    r=retriever(a,max_index_passages=10,max_index_batches=20,max_tokens=50000,result_limit=1)
    first=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=50000,remaining_seconds=15)
    assert [p.id for p in first.passages]==[wanted]
    assert first.fallback_reason is None
    assert (first.eligible_passages,first.indexed_passages,first.pending_passages)==(122,122,0)
    assert count(a)==122 and first.index_batches==13
    assert all(len(c)<=10 for c in a.embed.calls[1:])
    assert first.vectors==()  # the archive cache is ranked by SQL, never loaded whole
    before=len(a.embed.calls)
    warm=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=5000,remaining_seconds=10,index_missing=False)
    assert [p.id for p in warm.passages]==[wanted]
    assert len(a.embed.calls)==before+1 and a.embed.calls[-1]==['beneficial ownership']
    assert warm.index_batches==0 and warm.pending_passages==0

def test_partial_indexing_is_visible_and_resumes(archive):
    a=archive
    for i in range(1,22):a.passage('Office stationery.',i)
    r=retriever(a,max_index_passages=10,max_index_batches=1,max_tokens=10000)
    first=r.index(a.conn,a.ctx,a.task,remaining_tokens=10000,remaining_seconds=10)
    assert (first.indexed_passages,first.pending_passages)==(10,11)
    assert first.indexing_stop_reason=='batch_limit'
    second=r.index(a.conn,a.ctx,a.task,remaining_tokens=10000,remaining_seconds=10)
    assert (second.indexed_passages,second.pending_passages)==(20,1)
    third=r.index(a.conn,a.ctx,a.task,remaining_tokens=10000,remaining_seconds=10)
    assert third.indexed_passages==21 and third.pending_passages==0
    assert count(a)==21 and sum(len(c) for c in a.embed.calls)==21

def test_exact_term_keyword_arm_and_source_version_gates(archive):
    a=archive
    old,doc=a.passage('beneficial ownership old version.')
    current,_=a.passage('beneficial ownership current version.',document=doc,version=2)
    future,_=a.passage('beneficial ownership future version.',document=doc,version=3,day='2030-01-01')
    mas=a.source('mas',True);a.task.source_ids.append(mas)
    mas_pid,_=a.passage('beneficial ownership MAS forbidden.',source_id=mas)
    denied=a.source(ops=['store_text']);a.task.source_ids.append(denied)
    denied_pid,_=a.passage('beneficial ownership unembeddable.',source_id=denied)
    r=retriever(a)
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert (result.eligible_passages,result.indexed_passages)==(1,1)
    cached={r['passage_id'] for r in a.conn.execute('select passage_id from public.hybrid_passage_vectors where workspace_id=%s',(a.ws,)).fetchall()}
    assert cached=={current}
    keyword=r.keyword(a.conn,a.ctx,a.task,limit=20)
    assert {p.id for p in keyword}=={current,denied_pid}
    assert not {old,future,mas_pid}.intersection(p.id for p in result.passages)

def test_oversized_inputs_do_not_starve_later_passages_or_discard_text(archive):
    a=archive
    for i in range(1,43):a.passage('irrelevant '*900,i)
    wanted,_=a.passage('The natural person who ultimately owns a company.',9000)
    r=retriever(a,max_index_passages=10,max_index_batches=2,result_limit=1)
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert [p.id for p in result.passages]==[wanted]
    assert (result.eligible_passages,result.indexed_passages,result.pending_passages,result.blocked_passages)==(43,1,42,42)
    assert result.indexing_stop_reason=='input_limit'
    assert count(a)==1
    assert a.conn.execute('select count(*) n from public.document_passages where workspace_id=%s',(a.ws,)).fetchone()['n']==43

def test_known_usage_survives_cache_failure(archive,monkeypatch):
    a=archive;a.passage('The natural person who ultimately owns a company.')
    r=retriever(a)
    def fail(*args,**kwargs):raise RuntimeError('fixture cache failure')
    monkeypatch.setattr(r,'_save',fail)
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert result.tokens==sum(len(t.split()) for c in a.embed.calls for t in c)>0
    assert result.cache_error=='RuntimeError'
    assert count(a)==0 and result.pending_passages==1

def test_deadline_after_embedding_preserves_usage_and_prior_batches(archive,monkeypatch):
    a=archive;a.passage('The natural person who ultimately owns a company.')
    r=retriever(a)
    def timeout(*args,**kwargs):raise TimeoutError('fixture database deadline')
    monkeypatch.setattr(r,'_search',timeout)
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert result.fallback_reason=='time_limit'
    assert result.tokens==sum(len(t.split()) for c in a.embed.calls for t in c)>0
    assert count(a)==1

def test_source_revocation_during_embedding_cannot_publish_vectors(archive):
    a=archive;a.passage('The natural person who ultimately owns a company.')
    original=a.embed.embed
    def revoke(texts,**kw):
        result=original(texts,**kw)
        a.conn.execute('update public.sources set permitted_operations=%s where id=%s',(['store_text'],a.src))
        return result
    a.embed.embed=revoke
    r=retriever(a)
    result=r.index(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert result.tokens>0 and result.cache_error=='InsufficientPrivilege'
    assert count(a)==0

def test_unauthorised_actor_cannot_send_archive_text_to_provider(archive):
    from mira.db import NotAuthorisedError
    a=archive;a.passage('Private evidence.')
    a.ctx.user_id=uuid4()
    with pytest.raises(NotAuthorisedError):
        retriever(a).retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert not a.embed.calls

def test_unknown_reservations_respect_smaller_remaining_budget(archive):
    from mira.hybrid import EmbeddingError
    a=archive;a.passage('beneficial ownership facts.')
    def unknown(*args,**kw):raise EmbeddingError('unknown',20000)
    a.embed.embed=unknown
    result=retriever(a).retrieve(a.conn,a.ctx,a.task,remaining_tokens=2000,remaining_seconds=10)
    assert 0<result.reserved_tokens<=2000
    assert result.fallback_reason=='embedding_failed' and result.tokens==0

def test_non_timeout_database_failure_retains_paid_usage(archive,monkeypatch):
    a=archive;a.passage('The natural person who ultimately owns a company.')
    r=retriever(a)
    def disconnect(*args,**kw):raise psycopg.OperationalError('fixture lost connection')
    monkeypatch.setattr(r,'_search',disconnect)
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert result.fallback_reason=='retrieval_failed'
    assert result.tokens==sum(len(t.split()) for c in a.embed.calls for t in c)>0
    assert result.cache_error=='OperationalError' and result.coverage_known is False

def test_character_budget_is_cumulative_across_batches(archive):
    a=archive
    for i in range(1,4):a.passage('ten chars!',i)
    r=retriever(a,max_characters=10,max_index_passages=1,max_index_batches=3)
    result=r.index(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    assert sum(len(t) for c in a.embed.calls for t in c)<=10
    assert result.indexed_passages==1 and result.pending_passages==2
    assert result.indexing_stop_reason=='input_limit'

def test_embedding_batch_respects_provider_input_ceiling(archive):
    a=archive
    for i in range(1,42):a.passage('x'*8000,i)
    result=retriever(a,max_index_batches=2,max_characters=500000,max_tokens=500000).index(
        a.conn,a.ctx,a.task,remaining_tokens=500000,remaining_seconds=15)
    assert all(sum(len(t.encode()) for t in c)<=300000 for c in a.embed.calls)
    assert result.indexed_passages==41 and result.pending_passages==0

def test_small_token_remainder_is_not_misreported_as_character_limit(archive):
    a=archive;a.passage('x'*500)
    result=retriever(a).retrieve(a.conn,a.ctx,a.task,remaining_tokens=1200,remaining_seconds=10)
    assert result.indexing_stop_reason=='token_limit'
    assert result.indexed_passages==0 and result.pending_passages==1

def test_stale_content_cache_is_ignored_and_frozen_empty_index_costs_nothing(archive):
    a=archive;pid,_=a.passage('The natural person who ultimately owns a company.')
    r=retriever(a)
    r.index(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10)
    a.conn.execute('update public.document_passages set content=%s where id=%s',('Office stationery.',pid))
    a.embed.calls=[]
    result=r.retrieve(a.conn,a.ctx,a.task,remaining_tokens=20000,remaining_seconds=10,index_missing=False)
    assert result.indexed_passages==0 and result.pending_passages==1
    assert result.fallback_reason=='no_indexed_passages'
    assert not a.embed.calls and result.tokens==0
