-- Include source reuse notices in new evidence captures; omit absent notices for legacy compatibility.
-- Existing reviewed snapshots and stored historical document metadata are not changed.
begin;
create or replace function private.capture_base_evidence_input(p_workspace uuid, p_run uuid, p_revision uuid, p_roots uuid[])
returns jsonb language sql stable security definer set search_path = '' as $$
  with recursive needed(id) as (
    select unnest(p_roots)
    union
    select d.depends_on_finding_id from public.finding_dependencies d
    join needed n on n.id = d.finding_id
    where d.workspace_id = p_workspace and d.analysis_run_id = p_run
  ), findings as (
    select f.* from public.analysis_findings f join needed n on n.id = f.id
    where f.workspace_id = p_workspace and f.analysis_run_id = p_run
      and f.analysis_revision_id = p_revision
  ), links as (
    select e.finding_id, ae.passage_id, ae.document_version_id, e.support_type, e.supporting_quote
    from public.finding_evidence e
    join findings f on f.id = e.finding_id
    join public.analysis_evidence ae on ae.id = e.analysis_evidence_id
      and ae.workspace_id = p_workspace and ae.analysis_run_id = p_run
    where e.workspace_id = p_workspace and e.analysis_run_id = p_run
  ), passage_rows as (
    select distinct p.id, p.document_version_id, v.document_id, d.source_id, s.name as source_name,
      nullif(btrim(s.jurisdiction_code), '') as jurisdiction_code, v.title, v.source_url,
      v.published_at::date as published_at, p.passage_number, p.content,
      coalesce(v.metadata->>'import', '') = 'manual' as imported,
      v.content_sha256, coalesce(p.extraction_version, v.extraction_version) as extraction_version,
      p.page_number, p.char_start, p.char_end,
      jsonb_build_object('acquisition_method', v.metadata->'acquisition_method', 'requested_url', v.metadata->'requested_url', 'original_capture_sha256', v.metadata->'original_capture_sha256', 'capture_sha256', v.metadata->'capture_sha256', 'extraction_sha256', v.metadata->'extraction_sha256', 'original_retained', v.metadata->'original_retained', 'acquired_at', v.retrieved_at, 'browser_context', v.metadata->'browser_context') || case when jsonb_typeof(v.metadata->'source_reuse')='object' and v.metadata->'source_reuse'<>'{}'::jsonb then jsonb_build_object('source_reuse',v.metadata->'source_reuse') else '{}'::jsonb end || case when v.metadata->'retained_original' is not null and v.metadata->'retained_original'<>'null'::jsonb then jsonb_build_object('retained_original',v.metadata->'retained_original') else '{}'::jsonb end as acquisition_provenance
    from links l
    join public.document_passages p on p.id = l.passage_id and p.workspace_id = p_workspace
    join public.document_versions v on v.id = p.document_version_id and v.workspace_id = p_workspace
    join public.documents d on d.id = v.document_id and d.workspace_id = p_workspace
    join public.sources s on s.id = d.source_id and s.workspace_id = p_workspace
  )
  select jsonb_build_object(
    'schema_version', 1, 'workspace_id', p_workspace, 'analysis_run_id', p_run,
    'analysis_revision_id', p_revision,
    'findings', coalesce((select jsonb_object_agg(f.id::text, jsonb_build_object(
      'finding_id', f.id, 'finding_type', f.finding_type, 'title', f.title, 'content', f.content,
      'priority', f.priority, 'evidence_confidence', f.evidence_confidence,
      'priority_reason', f.priority_reason, 'jurisdiction_code', nullif(btrim(f.jurisdiction_code), ''),
      'change_type', f.change_type, 'industry_category', f.industry_category,
      'is_inference', f.is_inference, 'evidence_confidence_reason', f.evidence_confidence_reason,
      'key_date', f.key_date, 'key_date_kind', f.key_date_kind,
      'depends_on', coalesce((select jsonb_agg(d.depends_on_finding_id order by d.depends_on_finding_id)
        from public.finding_dependencies d where d.finding_id = f.id
          and d.workspace_id = p_workspace and d.analysis_run_id = p_run), '[]'::jsonb),
      'evidence', coalesce((select jsonb_agg(jsonb_build_object(
        'passage_id', l.passage_id, 'document_version_id', l.document_version_id,
        'supporting_quote', l.supporting_quote, 'support_type', l.support_type
      ) order by l.passage_id, l.supporting_quote collate "C", l.support_type) from links l where l.finding_id = f.id), '[]'::jsonb)
    )) from findings f), '{}'::jsonb),
    'passages', coalesce((select jsonb_object_agg(p.id::text, to_jsonb(p)) from passage_rows p), '{}'::jsonb)
  )
$$;
create or replace function private.corroboration_candidate_current(p_workspace uuid,p_asof date,p_candidate jsonb)
returns boolean language sql stable security definer set search_path='' as $$
  with saved as (select p.id, p.document_version_id, v.document_id, d.source_id, s.name as source_name,
      nullif(btrim(s.jurisdiction_code), '') as jurisdiction_code, v.title, v.source_url,
      v.published_at::date as published_at, p.passage_number, p.content,
      coalesce(v.metadata->>'import', '') = 'manual' as imported,
      v.content_sha256, coalesce(p.extraction_version, v.extraction_version) as extraction_version,
      p.page_number, p.char_start, p.char_end,
      jsonb_build_object('acquisition_method', v.metadata->'acquisition_method', 'requested_url', v.metadata->'requested_url', 'original_capture_sha256', v.metadata->'original_capture_sha256', 'capture_sha256', v.metadata->'capture_sha256', 'extraction_sha256', v.metadata->'extraction_sha256', 'original_retained', v.metadata->'original_retained', 'acquired_at', v.retrieved_at, 'browser_context', v.metadata->'browser_context') || case when jsonb_typeof(v.metadata->'source_reuse')='object' and v.metadata->'source_reuse'<>'{}'::jsonb then jsonb_build_object('source_reuse',v.metadata->'source_reuse') else '{}'::jsonb end || case when v.metadata->'retained_original' is not null and v.metadata->'retained_original'<>'null'::jsonb then jsonb_build_object('retained_original',v.metadata->'retained_original') else '{}'::jsonb end as acquisition_provenance
    from public.document_passages p
    join public.document_versions v on v.id=p.document_version_id and v.workspace_id=p_workspace
    join public.documents d on d.id=v.document_id and d.workspace_id=p_workspace
    join public.sources s on s.id=d.source_id and s.workspace_id=p_workspace
    where p.id=(p_candidate->'passage'->>'id')::uuid and p.workspace_id=p_workspace
      and s.is_active and s.permitted_operations @> array['fetch','store_text']::text[]
      and (v.published_at is null or v.published_at::date<=p_asof)
      and not exists(select 1 from public.document_versions later where later.document_id=v.document_id
        and later.workspace_id=p_workspace and later.version_number>v.version_number
        and (later.published_at is null or later.published_at::date<=p_asof)))
  select coalesce((select to_jsonb(saved)=p_candidate->'passage' from saved),false)
    and coalesce(p_candidate->>'workspace_id'=p_workspace::text,false)
$$;
commit;
