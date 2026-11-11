-- Private artifact references are separate from immutable signed report snapshots.
begin;
create table public.report_artifacts (
 report_id uuid primary key references public.reports(id),
 workspace_id uuid not null references public.workspaces(id),
 state text not null check(state in ('pending','failed','ready')),
 content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
 object_identity jsonb,
 error_code text check(error_code is null or error_code ~ '^[A-Za-z_]{1,64}$'),
 attempts integer not null default 0 check(attempts>=0),
 created_by uuid not null references auth.users(id),
 updated_at timestamptz not null default clock_timestamp(),
 check((state='ready')=(object_identity is not null))
);
alter table public.report_artifacts enable row level security;
revoke all on public.report_artifacts from public,anon,authenticated;
grant select on public.report_artifacts to authenticated;
grant select,insert,update on public.report_artifacts to service_role;
create policy report_artifacts_member_read on public.report_artifacts for select to authenticated
 using(private.is_workspace_member(workspace_id));
create function private.validate_report_artifact() returns trigger
language plpgsql security definer set search_path='' as $$
declare v jsonb;
begin
 if tg_op='DELETE' then raise exception 'artifact references are immutable' using errcode='check_violation'; end if;
 if current_setting('role',true) in ('authenticated','anon') or auth.uid() is null or
    not private.has_workspace_role(new.workspace_id,array['admin','analyst','reviewer']) then
   raise exception 'artifact worker actor required' using errcode='42501'; end if;
 if tg_op='INSERT' and new.created_by is distinct from auth.uid() then
   raise exception 'artifact actor mismatch' using errcode='check_violation'; end if;
 if not exists(select 1 from public.reports r where r.id=new.report_id and r.workspace_id=new.workspace_id) then
   raise exception 'artifact report scope mismatch' using errcode='check_violation'; end if;
 if tg_op='UPDATE' and ((new.report_id,new.workspace_id,new.created_by,new.content_sha256) is distinct from (old.report_id,old.workspace_id,old.created_by,old.content_sha256)
     or old.state='ready' and (new.state<>'ready' or new.object_identity is distinct from old.object_identity)) then
   raise exception 'published artifact identity is immutable' using errcode='check_violation'; end if;
 if new.state='ready' then
   v:=new.object_identity;
   if jsonb_typeof(v)<>'object' or not coalesce(v->>'workspace_id'=new.workspace_id::text,false)
     or not coalesce(v->>'purpose'='report',false) or not coalesce(v->>'storage_kind'='private_supabase',false)
     or not coalesce(v->>'bucket'='mira-evidence-private',false)
     or not coalesce(v->>'sha256'=new.content_sha256,false)
     or jsonb_typeof(v->'size_bytes') is distinct from 'number'
     or not coalesce((v->>'size_bytes')::numeric between 0 and 20000000,false)
     or (v->>'size_bytes')::numeric<>trunc((v->>'size_bytes')::numeric)
     or not coalesce(v->>'media_type' in ('text/html','text/html; charset=utf-8'),false) then
     raise exception 'invalid report artifact identity' using errcode='check_violation'; end if;
 end if;
 new.updated_at:=clock_timestamp();
 return new;
end $$;
create trigger report_artifact_validate before insert or update or delete on public.report_artifacts
 for each row execute function private.validate_report_artifact();
create function private.audit_report_artifact() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 insert into public.audit_events(workspace_id,entity_type,entity_id,action,actor_id,details)
 values(new.workspace_id,'report_artifacts',new.report_id,lower(tg_op),auth.uid(),
   jsonb_build_object('state',new.state,'attempts',new.attempts));
 return new;
end $$;
create trigger report_artifact_audit after insert or update on public.report_artifacts
 for each row execute function private.audit_report_artifact();

-- Current source approval also governs direct Storage requests; UI checks alone
-- cannot protect objects whose grant was revoked after a report was signed.
create function private.can_read_evidence_object(p_bucket text,p_name text) returns boolean
language plpgsql stable security definer set search_path='' as $$
declare ws uuid; purpose text; digest text;
begin
 if p_bucket<>'mira-evidence-private' or p_name !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(original|report)/[0-9a-f]{64}\.bin$' then return false; end if;
 ws:=split_part(p_name,'/',1)::uuid;
 if not private.is_workspace_member(ws) then return false; end if;
 purpose:=split_part(p_name,'/',2); digest:=split_part(split_part(p_name,'/',3),'.',1);
 if purpose='report' then
   return exists(select 1 from public.report_artifacts a where a.workspace_id=ws and a.state='ready'
     and a.object_identity->>'sha256'=digest and a.object_identity->>'bucket'=p_bucket
     and a.object_identity->>'storage_kind'='private_supabase' and a.object_identity->>'purpose'='report');
 end if;
 return exists(select 1 from public.document_versions v
   join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
   join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
   where v.workspace_id=ws and s.is_active and 'store_text'=any(s.permitted_operations)
     and v.metadata->'original_retained'='true'::jsonb
     and v.metadata->'retained_original'->>'workspace_id'=ws::text
     and v.metadata->'retained_original'->>'purpose'='original'
     and v.metadata->'retained_original'->>'storage_kind'='private_supabase'
     and v.metadata->'retained_original'->>'bucket'=p_bucket
     and v.metadata->'retained_original'->>'sha256'=digest
     and s.connector_config->'original_retention'->'approved'='true'::jsonb
     and coalesce(btrim(s.connector_config->'original_retention'->>'reference'),'')<>''
     and s.connector_config->'original_retention'->>'reference'=v.metadata->'retained_original'->>'approval_reference');
end $$;
revoke all on function private.can_read_evidence_object(text,text) from public;
grant execute on function private.can_read_evidence_object(text,text) to anon,authenticated;
-- Supabase owns storage schema. Vanilla test environments may omit it; no public
-- bucket or storage schema is invented as a substitute.
do $$ begin
 if to_regclass('storage.objects') is not null then
   if exists(select 1 from storage.buckets where id='mira-evidence-private' and public) then
     raise exception 'reserved evidence bucket must be private'; end if;
   insert into storage.buckets(id,name,public,file_size_limit)
   values('mira-evidence-private','mira-evidence-private',false,20000000) on conflict(id) do nothing;
   execute 'create policy mira_evidence_bucket_insert_boundary on storage.buckets as restrictive for insert to anon,authenticated with check(id<>''mira-evidence-private'')';
   execute 'create policy mira_evidence_bucket_update_boundary on storage.buckets as restrictive for update to anon,authenticated using(id<>''mira-evidence-private'') with check(id<>''mira-evidence-private'')';
   execute 'create policy mira_evidence_bucket_delete_boundary on storage.buckets as restrictive for delete to anon,authenticated using(id<>''mira-evidence-private'')';
   execute 'create policy mira_evidence_read on storage.objects for select to authenticated using(bucket_id=''mira-evidence-private'' and private.can_read_evidence_object(bucket_id,name))';
   execute 'create policy mira_evidence_read_boundary on storage.objects as restrictive for select to public using(bucket_id<>''mira-evidence-private'' or private.can_read_evidence_object(bucket_id,name))';
   execute 'create policy mira_evidence_insert_boundary on storage.objects as restrictive for insert to anon,authenticated with check(bucket_id<>''mira-evidence-private'')';
   execute 'create policy mira_evidence_update_boundary on storage.objects as restrictive for update to anon,authenticated using(bucket_id<>''mira-evidence-private'') with check(bucket_id<>''mira-evidence-private'')';
   execute 'create policy mira_evidence_delete_boundary on storage.objects as restrictive for delete to anon,authenticated using(bucket_id<>''mira-evidence-private'')';
 end if;
end $$;
revoke all on function private.validate_report_artifact() from public,anon,authenticated;
revoke all on function private.audit_report_artifact() from public,anon,authenticated;
commit;
