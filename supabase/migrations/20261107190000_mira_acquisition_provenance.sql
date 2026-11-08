-- Freeze acquisition context in new verification/review inputs; no historic backfill.
begin;
create or replace function private.capture_evidence_input(p_workspace uuid, p_run uuid, p_revision uuid, p_roots uuid[])
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
      jsonb_build_object('acquisition_method', v.metadata->'acquisition_method', 'requested_url', v.metadata->'requested_url', 'original_capture_sha256', v.metadata->'original_capture_sha256', 'capture_sha256', v.metadata->'capture_sha256', 'extraction_sha256', v.metadata->'extraction_sha256', 'original_retained', v.metadata->'original_retained', 'acquired_at', v.retrieved_at) as acquisition_provenance
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
      ) order by l.passage_id, l.supporting_quote, l.support_type) from links l where l.finding_id = f.id), '[]'::jsonb)
    )) from findings f), '{}'::jsonb),
    'passages', coalesce((select jsonb_object_agg(p.id::text, to_jsonb(p)) from passage_rows p), '{}'::jsonb)
  )
$$;
commit;
