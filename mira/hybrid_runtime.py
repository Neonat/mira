"""Worker-only bridge between eligible saved passages and hybrid fusion."""
from dataclasses import dataclass, replace
import hashlib
import time

import psycopg

from mira.hybrid import HybridResult, PassageVector, retrieve
from mira.pg_store import PostgresStore
from mira.db import acting_as


@dataclass(frozen=True)
class HybridRuntimeResult(HybridResult):
    cache_error: str | None = None


class HybridRetriever:
    def __init__(self, embedder, identity, limits):
        if identity.dimensions != 384:
            raise ValueError('saved embeddings require 384 dimensions')
        self.embedder, self.identity, self.limits = embedder, identity, limits

    def retrieve(self, conn, ctx, task, *, remaining_tokens, remaining_seconds):
        if remaining_tokens is not None and remaining_tokens <= 0:
            return HybridResult([], (), fallback_reason='token_limit')
        if remaining_seconds is not None and remaining_seconds <= 0:
            return HybridResult([], (), fallback_reason='time_limit')
        limits = replace(self.limits,
                         max_tokens=min(self.limits.max_tokens, remaining_tokens) if remaining_tokens is not None else self.limits.max_tokens,
                         timeout_seconds=min(self.limits.timeout_seconds, remaining_seconds) if remaining_seconds is not None else self.limits.timeout_seconds)
        deadline = time.monotonic() + limits.timeout_seconds
        result = None
        try:
            with conn.transaction():
                old = conn.execute("select current_setting('statement_timeout') as statement, current_setting('lock_timeout') as lock").fetchone()
                result = self._retrieve(conn, ctx, task, limits, deadline)
                conn.execute("select set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)", (old['statement'], old['lock']))
                return result
        except (TimeoutError, psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable):
            if result is not None:
                return HybridRuntimeResult(result.passages, result.vectors, result.tokens,
                                           result.reserved_tokens, result.fallback_reason,
                                           cache_error='deadline')
            return HybridResult([], (), fallback_reason='time_limit')

    @staticmethod
    def _timeout(conn, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('hybrid deadline reached')
        milliseconds = str(max(1, int(remaining * 1000)))
        conn.execute("select set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)", (milliseconds, milliseconds))

    def _retrieve(self, conn, ctx, task, limits, deadline):
        self._timeout(conn, deadline)
        rows = conn.execute('''with eligible as (
            select distinct on (v.document_id) v.id
            from public.document_versions v
            join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
            join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
            where v.workspace_id=%s and d.source_id=any(%s) and s.is_active
              and s.permitted_operations @> array['store_text','embed']::text[]
              and ('fetch' = any(s.permitted_operations) or v.metadata->>'import' = 'manual')
              and ((%s::text is null or %s::text='INT') and coalesce(trim(s.jurisdiction_code), '') in ('','INT')
                   or %s::text is not null and %s::text <> 'INT' and s.jurisdiction_code=%s and s.jurisdiction_code=any(%s))
              and (v.published_at is null or v.published_at::date <= %s)
            order by v.document_id, v.version_number desc
        ) select p.id from public.document_passages p join eligible v on v.id=p.document_version_id
          where p.workspace_id=%s order by p.id limit %s''',
          (ctx.workspace_id, list(task.source_ids), task.jurisdiction_code, task.jurisdiction_code, task.jurisdiction_code,
           task.jurisdiction_code, task.jurisdiction_code, list(ctx.brief.jurisdictions),
           ctx.brief.as_of_date, ctx.workspace_id, limits.max_index_passages + 1)).fetchall()
        if len(rows) > limits.max_index_passages:
            return HybridResult([], (), fallback_reason='passage_limit')
        if not rows:
            return HybridResult([], (), fallback_reason='no_eligible_passages')
        ids = [r['id'] for r in rows]
        self._timeout(conn, deadline)
        passages = PostgresStore(conn).get_passages(ctx.workspace_id, ids)
        hashes = {p.id: hashlib.sha256(p.content.encode('utf-8')).hexdigest() for p in passages}
        self._timeout(conn, deadline)
        cached = conn.execute('''select passage_id, content_sha256, embedding::text as embedding
          from public.hybrid_passage_vectors where workspace_id=%s and passage_id=any(%s)
          and model=%s and revision=%s and dimensions=%s''',
          (ctx.workspace_id, ids, self.identity.model, self.identity.revision, self.identity.dimensions)).fetchall()
        vectors = []
        for row in cached:
            if hashes.get(row['passage_id']) == row['content_sha256']:
                values = tuple(float(x) for x in row['embedding'].strip('[]').split(','))
                vectors.append(PassageVector(row['passage_id'], self.identity, values))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return HybridResult([], (), fallback_reason='time_limit')
        limits = replace(limits, timeout_seconds=remaining)
        result = retrieve(passages, task.question, self.embedder, self.identity, limits, vectors)
        if result.fallback_reason is None:
            # A cache write failure must not erase already incurred provider usage.
            try:
                with acting_as(conn, ctx.user_id):
                    for vector in result.vectors:
                        self._timeout(conn, deadline)
                        conn.execute('''insert into public.hybrid_passage_vectors
                          (workspace_id,passage_id,model,revision,dimensions,content_sha256,embedding)
                          values (%s,%s,%s,%s,%s,%s,%s::extensions.vector) on conflict do nothing''',
                          (ctx.workspace_id, vector.passage_id, self.identity.model, self.identity.revision,
                           self.identity.dimensions, hashes[vector.passage_id], '[' + ','.join(map(str, vector.values)) + ']'))
            except Exception as exc:
                return HybridRuntimeResult(result.passages, result.vectors, result.tokens,
                                           result.reserved_tokens, result.fallback_reason,
                                           cache_error=type(exc).__name__)
        return result
