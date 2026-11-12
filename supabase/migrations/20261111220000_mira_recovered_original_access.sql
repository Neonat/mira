-- Recovered bytes use the same private access boundary without changing the
-- original-retention state recorded in historical verification inputs.
create or replace function private.can_read_evidence_object(p_bucket text,p_name text) returns boolean
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
   cross join lateral (select case
     when v.metadata->'original_retained'='true'::jsonb then v.metadata->'retained_original'
     when v.metadata#>>'{recovered_original,identity,sha256}'=v.metadata->>'capture_sha256'
       then v.metadata#>'{recovered_original,identity}'
   end as original) i
   where v.workspace_id=ws and s.is_active and 'store_text'=any(s.permitted_operations)
     and i.original->>'workspace_id'=ws::text
     and i.original->>'purpose'='original'
     and i.original->>'storage_kind'='private_supabase'
     and i.original->>'bucket'=p_bucket
     and i.original->>'sha256'=digest
     and s.connector_config->'original_retention'->'approved'='true'::jsonb
     and coalesce(btrim(s.connector_config->'original_retention'->>'reference'),'')<>''
     and s.connector_config->'original_retention'->>'reference'=i.original->>'approval_reference');
end $$;
