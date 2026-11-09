"""Worker-only, bounded indexing and exact retrieval over the eligible archive."""
from contextlib import contextmanager
from dataclasses import dataclass,replace
import time

import psycopg

from mira import hybrid_archive as archive
from mira.hybrid import HybridResult,EmbeddingError,_valid
from mira.pg_store import PostgresStore
from mira.db import acting_as,require_role


@dataclass(frozen=True)
class HybridRuntimeResult(HybridResult):
    cache_error: str | None = None
    eligible_passages: int = 0
    indexed_passages: int = 0
    pending_passages: int = 0
    blocked_passages: int = 0
    index_batches: int = 0
    indexing_stop_reason: str | None = None
    coverage_known: bool = False
    input_characters: int = 0
    input_bytes: int = 0
    embedding_requests: int = 0


class HybridRetriever:
    def __init__(self,embedder,identity,limits):
        if identity.dimensions!=384:
            raise ValueError('saved embeddings require 384 dimensions')
        if not (1<=limits.max_index_passages<=2048 and 0<=limits.max_index_batches<=1000
                and limits.max_characters>0 and limits.max_tokens>0 and limits.timeout_seconds>0
                and 0<=limits.result_limit<=1000):
            raise ValueError('invalid archive hybrid limits')
        self.embedder,self.identity,self.limits=embedder,identity,limits

    @staticmethod
    def _timeout(conn,deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('hybrid deadline reached')
        ms=str(max(1,int(remaining*1000)))
        conn.execute("select set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",(ms,ms))

    @contextmanager
    def _db(self,conn,deadline):
        if time.monotonic()>=deadline:raise TimeoutError('hybrid deadline reached')
        with conn.transaction():
            old=conn.execute("select current_setting('statement_timeout') statement,current_setting('lock_timeout') lock").fetchone()
            self._timeout(conn,deadline)
            yield
            conn.execute("select set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",(old['statement'],old['lock']))

    def _authorize(self,conn,ctx,deadline):
        with self._db(conn,deadline),acting_as(conn,ctx.user_id):require_role(conn,ctx.workspace_id)

    def keyword(self,conn,ctx,task,*,limit=None,timeout_seconds=None):
        limit=self.limits.result_limit if limit is None else limit
        if not 0<=limit<=1000:raise ValueError('invalid result limit')
        deadline=time.monotonic()+(timeout_seconds or self.limits.timeout_seconds)
        self._authorize(conn,ctx,deadline)
        params=archive.parameters(ctx,task,self.identity)|dict(limit=limit,candidates=max(20,limit*4))
        return self._search(conn,ctx,params,None,deadline)

    def _search(self,conn,ctx,params,query,deadline):
        self._authorize(conn,ctx,deadline)
        with self._db(conn,deadline):
            rows=archive.search(conn,params,query)
            self._timeout(conn,deadline)
            passages={p.id:p for p in PostgresStore(conn).get_passages(ctx.workspace_id,[r['id'] for r in rows])}
            return [passages[r['id']] for r in rows if r['id'] in passages]

    def _save(self,conn,ctx,rows,vectors,deadline):
        with self._db(conn,deadline),acting_as(conn,ctx.user_id):
            for row,vector in zip(rows,vectors):
                self._timeout(conn,deadline)
                conn.execute('''insert into public.hybrid_passage_vectors
                 (workspace_id,passage_id,model,revision,dimensions,content_sha256,embedding)
                 values(%s,%s,%s,%s,%s,%s,%s::extensions.vector) on conflict do nothing''',
                 (ctx.workspace_id,row['id'],self.identity.model,self.identity.revision,self.identity.dimensions,
                  row['content_sha256'],'['+','.join(map(str,vector))+']'))

    def retrieve(self,conn,ctx,task,*,remaining_tokens,remaining_seconds,index_missing=True):
        return self._run(conn,ctx,task,remaining_tokens,remaining_seconds,query=True,index_missing=index_missing)

    def index(self,conn,ctx,task,*,remaining_tokens,remaining_seconds):
        return self._run(conn,ctx,task,remaining_tokens,remaining_seconds,query=False,index_missing=True)

    def _run(self,conn,ctx,task,tokens,seconds,*,query,index_missing):
        limits=replace(self.limits,max_tokens=min(self.limits.max_tokens,tokens) if tokens is not None else self.limits.max_tokens,
                       timeout_seconds=min(self.limits.timeout_seconds,seconds) if seconds is not None else self.limits.timeout_seconds)
        used=reserved=batches=characters_sent=bytes_sent=requests=0
        state=dict(eligible_passages=0,indexed_passages=0,pending_passages=0,blocked_passages=0,coverage_known=False)
        stop=cache_error=None
        deadline=time.monotonic()+max(0,limits.timeout_seconds)
        params=archive.parameters(ctx,task,self.identity)|dict(characters=limits.max_characters,batch_size=limits.max_index_passages,
                 limit=limits.result_limit,candidates=max(20,limits.result_limit*4))
        def output(passages=(),fallback=None):
            return HybridRuntimeResult(list(passages),(),used,reserved,fallback,cache_error=cache_error,
                                       index_batches=batches,indexing_stop_reason=stop,
                                       input_characters=characters_sent,input_bytes=bytes_sent,embedding_requests=requests,**state)
        def status():
            with self._db(conn,deadline):counts=archive.counts(conn,params)
            state.update(eligible_passages=counts['eligible'],indexed_passages=counts['indexed'],
                         pending_passages=counts['eligible']-counts['indexed'],blocked_passages=counts['blocked'],coverage_known=True)
        def embed(texts):
            nonlocal used,reserved,characters_sent,bytes_sent,requests
            chars=sum(len(t) for t in texts)
            size=sum(len(t.encode('utf-8')) for t in texts)
            amount=size+1024
            if characters_sent+chars>limits.max_characters:raise EmbeddingError('input_limit',0,tokens=0)
            if amount>limits.max_tokens-used-reserved:raise EmbeddingError('token_limit',0,tokens=0)
            if time.monotonic()>=deadline:raise TimeoutError('hybrid deadline reached')
            self._authorize(conn,ctx,deadline)
            characters_sent+=chars;bytes_sent+=size;requests+=1
            try:
                result=self.embedder.embed(texts,timeout_seconds=max(0,deadline-time.monotonic()))
            except EmbeddingError as exc:
                if type(exc.tokens) is int and exc.tokens>=0:used+=exc.tokens
                else:reserved+=amount
                raise
            except Exception:
                reserved+=amount
                raise EmbeddingError('embedding_failed',amount) from None
            if type(getattr(result,'tokens',None)) is not int or result.tokens<0:
                reserved+=amount
                raise EmbeddingError('embedding_failed',amount)
            used+=result.tokens
            if result.tokens>amount or used+reserved>limits.max_tokens:
                raise EmbeddingError('token_limit_exceeded',0,tokens=0)
            try:
                if len(result.vectors)!=len(texts):raise ValueError('vector count mismatch')
                return tuple(_valid(v,self.identity) for v in result.vectors)
            except (ValueError,TypeError,AttributeError,OverflowError):raise EmbeddingError('embedding_failed',0,tokens=0) from None
        if limits.max_tokens<=0:return output(fallback='token_limit')
        if limits.timeout_seconds<=0:return output(fallback='time_limit')
        # Initial actor refusal stays fail-closed and cannot send any text.
        self._authorize(conn,ctx,deadline)
        try:
            status()
            if not state['eligible_passages']:
                return output(self._search(conn,ctx,params,None,deadline) if query else (),fallback='no_eligible_passages')
            if query and not index_missing and not state['indexed_passages']:
                return output(self._search(conn,ctx,params,None,deadline),fallback='no_indexed_passages')
            q=None
            if query:
                if not task.question.strip() or len(task.question.encode())>8192 or len(task.question)>limits.max_characters:
                    return output(self._search(conn,ctx,params,None,deadline),fallback='input_limit')
                try:q=embed([task.question])[0]
                except EmbeddingError as exc:
                    return output(self._search(conn,ctx,params,None,deadline),fallback=str(exc) if str(exc)=='token_limit' else 'embedding_failed')
            if index_missing:
                while state['pending_passages']>state['blocked_passages'] and batches<limits.max_index_batches:
                    # Conservative byte bound also respects the provider's
                    # 300,000-token aggregate input ceiling per request.
                    capacity=min(300000,limits.max_tokens-used-reserved-1024)
                    if capacity<=0:stop='token_limit';break
                    characters_left=limits.max_characters-characters_sent
                    if characters_left<=0:stop='input_limit';break
                    with self._db(conn,deadline):rows=archive.missing(conn,params|dict(capacity=capacity,characters=characters_left))
                    if not rows:
                        with self._db(conn,deadline):
                            fits_characters=archive.missing(conn,params|dict(capacity=8192,characters=characters_left,batch_size=1))
                        stop='token_limit' if fits_characters else 'input_limit'
                        break
                    packed=[];size=chars=0
                    for row in rows:
                        length=len(row['content']);byte_size=len(row['content'].encode())
                        if size+byte_size<=capacity and chars+length<=characters_left:
                            packed.append(row);size+=byte_size;chars+=length
                    if not packed:stop='input_limit';break
                    try:vectors=embed([row['content'] for row in packed])
                    except EmbeddingError as exc:stop=str(exc) if str(exc) in ('input_limit','token_limit','token_limit_exceeded') else 'embedding_failed';break
                    batches+=1
                    try:self._save(conn,ctx,packed,vectors,deadline)
                    except (TimeoutError,psycopg.errors.QueryCanceled,psycopg.errors.LockNotAvailable):raise
                    except Exception as exc:cache_error=type(exc).__name__;stop='cache_write_failed';break
                    status()
                if state['pending_passages'] and stop is None:
                    stop='input_limit' if state['pending_passages']==state['blocked_passages'] else 'batch_limit'
            status()
            if not query:return output()
            if not state['indexed_passages']:return output(self._search(conn,ctx,params,None,deadline),fallback='no_indexed_passages')
            return output(self._search(conn,ctx,params,q,deadline))
        except (TimeoutError,psycopg.errors.QueryCanceled,psycopg.errors.LockNotAvailable):
            state['coverage_known']=False
            return output(fallback='time_limit')
        except Exception as exc:
            # No post-provider database/materialization error may erase usage.
            state['coverage_known']=False
            cache_error=type(exc).__name__
            return output(fallback='retrieval_failed')
