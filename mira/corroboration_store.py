"""Worker-only, workspace-scoped saved evidence and append-only corroboration ledger."""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID
from psycopg.types.json import Jsonb
from mira.contracts import FrozenPassage
from mira.db import acting_as, require_role
from mira.pg_store import PostgresStore


class CorroborationStore:
    def __init__(self, conn):
        self.conn = conn
        self.evidence = PostgresStore(conn)

    def latest(self, ctx, finding_ids):
        rows = self.conn.execute('''select distinct on (finding_id) id,sequence,finding_id,result
            from public.corroboration_assessments where workspace_id=%s and analysis_run_id=%s
            and analysis_revision_id=%s and finding_id=any(%s) order by finding_id,sequence desc''',
            (ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,list(finding_ids))).fetchall()
        return {r['finding_id']: {'assessment_id':str(r['id']),'sequence':r['sequence'],'assessment':r['result']} for r in rows}

    def save(self, ctx, claim, base_input, result):
        from mira.corroboration import CorroborationAssessment, validate_frozen_assessment
        assessment = CorroborationAssessment.model_validate(result)
        validate_frozen_assessment(assessment)
        if (assessment.workspace_id != ctx.workspace_id or assessment.finding_id != claim.finding_id
            or assessment.analysis_run_id != ctx.analysis_run_id or assessment.analysis_revision_id != ctx.analysis_revision_id
            or assessment.base_evidence_input != base_input):
            raise ValueError('corroboration identity or base input mismatch')
        sources = {s.id:s for s in self.evidence.list_sources(ctx.workspace_id)}
        for candidate in assessment.candidates:
            passage = candidate.passage
            loaded = self.evidence.get_passages(ctx.workspace_id,[passage.id])
            if not loaded or FrozenPassage(**asdict(loaded[0])) != passage:
                raise ValueError('corroboration passage changed or belongs to another workspace')
            source = sources.get(passage.source_id)
            if source is None or not {'fetch','store_text'} <= set(source.permitted_operations):
                raise ValueError('corroboration source is not permitted')
            current = self.conn.execute('''select id from public.document_versions
                where workspace_id=%s and document_id=%s and (published_at is null or published_at::date<=%s)
                order by version_number desc limit 1''',
                (ctx.workspace_id,passage.document_id,ctx.brief.as_of_date)).fetchone()
            if not current or current['id'] != passage.document_version_id:
                raise ValueError('corroboration candidate version is stale')
        with acting_as(self.conn,ctx.user_id):
            require_role(self.conn,ctx.workspace_id)
            row = self.conn.execute('''insert into public.corroboration_assessments
                (workspace_id,analysis_run_id,analysis_revision_id,finding_id,base_input,result,created_by)
                values (%s,%s,%s,%s,%s,%s,%s) returning id,sequence''',
                (ctx.workspace_id,ctx.analysis_run_id,ctx.analysis_revision_id,claim.finding_id,
                 Jsonb(base_input),Jsonb(result),ctx.user_id)).fetchone()
        return {'assessment_id':str(row['id']),'sequence':row['sequence'],'assessment':result}

    def candidates(self, ctx, claim, *, max_documents=5, max_passages=20):
        """Choose latest eligible versions before FTS, document or passage caps."""
        from mira.corroboration import CandidateEvidence
        from mira.agents.scout import document_key
        from mira.agents.scout import _terms
        words = sorted(w for w in _terms(claim.draft.title + " " + claim.draft.content) if not w.isdigit())[:16]
        if not words:
            return []
        query = ' OR '.join('"' + word + '"' for word in words)
        primary_ids = [e.passage_id for e in claim.evidence]
        selected=list(ctx.research_settings.source_ids) if ctx.research_settings and ctx.research_settings.source_ids else None
        rows = self.conn.execute('''with eligible as (
            select distinct on (v.document_id) v.id,v.document_id from public.document_versions v
            join public.documents d on d.id=v.document_id and d.workspace_id=%s
            join public.sources s on s.id=d.source_id and s.workspace_id=%s
            where v.workspace_id=%s and s.is_active and s.permitted_operations @> array['fetch','store_text']::text[]
              and (%s::uuid[] is null or s.id=any(%s::uuid[]))
              and (s.jurisdiction_code is null or btrim(s.jurisdiction_code)=any(%s))
              and (v.published_at is null or v.published_at::date<=%s)
              and d.id not in (select v2.document_id from public.document_passages p2
                  join public.document_versions v2 on v2.id=p2.document_version_id
                  where p2.workspace_id=%s and p2.id=any(%s))
            order by v.document_id,v.version_number desc
        ), hits as (
            select p.id,e.document_id,ts_rank_cd(p.search_vector,websearch_to_tsquery('english',%s)) as rank
            from public.document_passages p join eligible e on e.id=p.document_version_id
            where p.workspace_id=%s and p.search_vector @@ websearch_to_tsquery('english',%s)
        ), docs as (select document_id,max(rank) as rank from hits group by document_id
            order by rank desc,document_id limit %s)
        select h.id from hits h join docs d on d.document_id=h.document_id
        order by h.rank desc,h.id limit %s''',
        (ctx.workspace_id,ctx.workspace_id,ctx.workspace_id,selected,selected,list(ctx.brief.jurisdictions),ctx.brief.as_of_date,
         ctx.workspace_id,primary_ids,query,ctx.workspace_id,query,
         max_documents,max_passages)).fetchall()
        records = self.evidence.get_passages(ctx.workspace_id,[r['id'] for r in rows])
        return [CandidateEvidence(passage=FrozenPassage(**asdict(p)),workspace_id=ctx.workspace_id,
            publication_id=document_key(p.source_url),organization_id=str(p.source_id)) for p in records]
