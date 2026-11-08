-- Independent corroboration is append-only. No historical rows are invented.
begin;
create table public.corroboration_assessments (
  id uuid primary key default gen_random_uuid(),
  sequence bigint generated always as identity unique,
  workspace_id uuid not null references public.workspaces(id),
  analysis_run_id uuid not null,
  analysis_revision_id uuid not null references public.analysis_revisions(id),
  finding_id uuid not null,
  base_input jsonb not null,
  result jsonb not null,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default clock_timestamp(),
  foreign key (finding_id, workspace_id, analysis_run_id)
    references public.analysis_findings(id,workspace_id,analysis_run_id),
  check (jsonb_typeof(result) = 'object')
);
create index corroboration_latest on public.corroboration_assessments(workspace_id,analysis_run_id,finding_id,sequence desc);
alter table public.corroboration_assessments enable row level security;
revoke all on public.corroboration_assessments from public, anon, authenticated;
grant select on public.corroboration_assessments to authenticated;
create policy corroboration_member_read on public.corroboration_assessments for select to authenticated
  using (private.is_workspace_member(workspace_id));
create trigger corroboration_audit after insert on public.corroboration_assessments
  for each row execute function private.log_audit_event();

-- Separate the acyclic base input from verification/reviewer input containing assessments.
alter function private.capture_evidence_input(uuid,uuid,uuid,uuid[]) rename to capture_base_evidence_input;
alter function private.evidence_input_subset(jsonb,uuid[]) rename to base_evidence_input_subset;

create function private.corroboration_candidate_current(p_workspace uuid,p_asof date,p_candidate jsonb)
returns boolean language sql stable security definer set search_path='' as $$
  with saved as (select p.id, p.document_version_id, v.document_id, d.source_id, s.name as source_name,
      nullif(btrim(s.jurisdiction_code), '') as jurisdiction_code, v.title, v.source_url,
      v.published_at::date as published_at, p.passage_number, p.content,
      coalesce(v.metadata->>'import', '') = 'manual' as imported,
      v.content_sha256, coalesce(p.extraction_version, v.extraction_version) as extraction_version,
      p.page_number, p.char_start, p.char_end,
      jsonb_build_object('acquisition_method', v.metadata->'acquisition_method', 'requested_url', v.metadata->'requested_url', 'original_capture_sha256', v.metadata->'original_capture_sha256', 'capture_sha256', v.metadata->'capture_sha256', 'extraction_sha256', v.metadata->'extraction_sha256', 'original_retained', v.metadata->'original_retained', 'acquired_at', v.retrieved_at) as acquisition_provenance
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

create function private.validate_corroboration()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_candidate jsonb; v_asof date;
begin
  if tg_op <> 'INSERT' then
    raise exception 'corroboration assessment is immutable; append a fresh assessment' using errcode='check_violation';
  end if;
  if not exists(select 1 from public.analysis_findings f where f.id=new.finding_id
    and f.workspace_id=new.workspace_id and f.analysis_run_id=new.analysis_run_id
    and f.analysis_revision_id=new.analysis_revision_id) then
    raise exception 'corroboration scope mismatch' using errcode='check_violation';
  end if;
  if new.base_input is distinct from private.capture_base_evidence_input(
      new.workspace_id,new.analysis_run_id,new.analysis_revision_id,array[new.finding_id]) then
    raise exception 'corroboration base evidence changed' using errcode='check_violation';
  end if;
  if new.result->>'finding_id' is distinct from new.finding_id::text
     or new.result->>'workspace_id' is distinct from new.workspace_id::text
     or new.result->>'analysis_run_id' is distinct from new.analysis_run_id::text
     or new.result->>'analysis_revision_id' is distinct from new.analysis_revision_id::text then
    raise exception 'corroboration result identity mismatch' using errcode='check_violation';
  end if;
  if new.result->>'checked_at' is null or (new.result->>'checked_at')::timestamptz>clock_timestamp() then
    raise exception 'corroboration check time is missing or in the future' using errcode='check_violation';
  end if;
  new.created_at := clock_timestamp();
  select as_of_date into v_asof from public.analysis_runs where id=new.analysis_run_id and workspace_id=new.workspace_id;
  for v_candidate in select value from jsonb_array_elements(coalesce(new.result->'candidates','[]'::jsonb)) loop
    if private.corroboration_candidate_current(new.workspace_id,v_asof,v_candidate) is not true then
      raise exception 'corroboration candidate is stale or outside the workspace' using errcode='check_violation';
    end if;
  end loop;
  return new;
end
$$;
create trigger corroboration_validate before insert or update or delete on public.corroboration_assessments
  for each row execute function private.validate_corroboration();

create function private.capture_evidence_input(p_workspace uuid,p_run uuid,p_revision uuid,p_roots uuid[])
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare v_base jsonb; v_corrob jsonb;
begin
  v_base := private.capture_base_evidence_input(p_workspace,p_run,p_revision,p_roots);
  with latest as (
    select distinct on (a.finding_id) a.* from public.corroboration_assessments a
    where a.workspace_id=p_workspace and a.analysis_run_id=p_run and a.analysis_revision_id=p_revision
      and v_base->'findings' ? a.finding_id::text
    order by a.finding_id,a.sequence desc
  )
  select jsonb_object_agg(a.finding_id::text,jsonb_build_object(
    'assessment_id',a.id,'sequence',a.sequence,'assessment',a.result)) into v_corrob from latest a;
  if v_corrob is not null then
    return v_base || jsonb_build_object('corroboration',v_corrob);
  end if;
  return v_base;
end
$$;
create function private.evidence_input_subset(p_input jsonb,p_roots uuid[])
returns jsonb language sql immutable set search_path = '' as $$
  with base as (select private.base_evidence_input_subset(p_input,p_roots) as value),
  assessments as (select jsonb_object_agg(c.key,c.value) as value from jsonb_each(
    coalesce(p_input->'corroboration','{}'::jsonb)) c cross join base b where b.value->'findings' ? c.key)
  select b.value || case when a.value is not null then jsonb_build_object('corroboration',a.value)
    else '{}'::jsonb end from base b cross join assessments a
$$;

-- A later assessment or changed candidate invalidates new sign-off, never an old bundle.
create function private.check_corroboration_signoff()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_id uuid; v_entry jsonb; v_assessment public.corroboration_assessments%rowtype; v_candidate jsonb; v_asof date;
begin
 if new.review_status <> 'reviewed' then return new; end if;
 for v_id,v_entry in select key::uuid,value from jsonb_each(coalesce(
   new.evidence_snapshot->'evidence_bundle'->'corroboration','{}'::jsonb)) loop
   select * into v_assessment from public.corroboration_assessments where id=(v_entry->>'assessment_id')::uuid
     and workspace_id=new.workspace_id;
   if not found or (v_assessment.result->>'checked_at')::timestamptz>new.reviewed_at
      or v_assessment.base_input is distinct from private.capture_base_evidence_input(
       new.workspace_id,v_assessment.analysis_run_id,new.analysis_revision_id,array[v_id]) then
     raise exception 'corroboration evidence changed; run fresh assessment and verification' using errcode='check_violation';
   end if;
   select as_of_date into v_asof from public.analysis_runs where id=v_assessment.analysis_run_id and workspace_id=new.workspace_id;
   for v_candidate in select value from jsonb_array_elements(coalesce(v_assessment.result->'candidates','[]'::jsonb)) loop
     if private.corroboration_candidate_current(new.workspace_id,v_asof,v_candidate) is not true then
       raise exception 'corroboration candidate changed; run fresh assessment and verification' using errcode='check_violation';
     end if;
   end loop;
 end loop;
 if new.evidence_snapshot->'evidence_bundle' ? 'corroboration' then
   new.evidence_snapshot := jsonb_set(new.evidence_snapshot,'{contract_version}','"1.5"'::jsonb);
 end if;
 return new;
end
$$;
-- Existing zz trigger freezes/checks full enriched input first.
create trigger zzz_reports_check_corroboration before insert on public.reports
  for each row execute function private.check_corroboration_signoff();

revoke all on function private.corroboration_candidate_current(uuid,date,jsonb) from public,anon,authenticated;
revoke all on function private.validate_corroboration() from public,anon,authenticated;
revoke all on function private.capture_evidence_input(uuid,uuid,uuid,uuid[]) from public,anon,authenticated;
revoke all on function private.evidence_input_subset(jsonb,uuid[]) from public,anon,authenticated;
revoke all on function private.check_corroboration_signoff() from public,anon,authenticated;
commit;
