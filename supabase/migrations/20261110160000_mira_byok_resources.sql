-- Handles are opaque, temporary broker references. Provider credentials never enter PostgreSQL.
create or replace function public.bind_run_credentials(p_run_id uuid,p_handle text)
returns void language plpgsql security invoker set search_path = '' as $$
begin
 if p_handle is null or p_handle !~ '^[A-Za-z0-9_-]{32,128}$' then
   raise exception 'invalid credential handle' using errcode='22023';
 end if;
 update public.analysis_runs r set retrieval_settings=jsonb_set(r.retrieval_settings,
   '{research,credential_handle}',to_jsonb(p_handle))
 where r.id=p_run_id and r.created_by=auth.uid() and r.status='queued'
   and r.retrieval_settings->'research'->>'credential_mode'='byok'
   and private.has_workspace_role(r.workspace_id,array['admin','analyst']);
 if not found then
   raise exception 'run cannot accept credentials' using errcode='42501';
 end if;
end $$;
revoke all on function public.bind_run_credentials(uuid,text) from public,anon;
grant execute on function public.bind_run_credentials(uuid,text) to authenticated;

-- The worker journals admission before dispatch. API clients may cancel/approve or bind
-- fresh leases but cannot forge/refund consumption or enlarge a started allowance.
create or replace function private.guard_run_resources()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
 if current_setting('role',true) in ('authenticated','anon') then
   if tg_op='INSERT' then
     if new.retrieval_settings ?| array['monetary_usage','worker_invocation'] then
       raise exception 'usage is worker owned' using errcode='42501';
     end if;
     if new.status in ('queued','running') and (coalesce(new.retrieval_settings->'research'->>'credential_mode','') <> 'byok' or coalesce(new.source_limits->>'max_cost_usd','') !~ '^[0-9]+([.][0-9]+)?$' or (new.source_limits->>'max_cost_usd')::numeric <= 0) then
       raise exception 'runnable client runs require BYOK and a positive allowance' using errcode='42501';
     end if;
   else
     if new.retrieval_settings->'worker_invocation' is distinct from old.retrieval_settings->'worker_invocation' then
       raise exception 'invocation is worker owned' using errcode='42501';
     end if;
     if old.retrieval_settings->'research'->>'credential_mode' = 'byok' and new.retrieval_settings->'research'->>'credential_mode' is distinct from 'byok' then
       raise exception 'credential mode is fixed' using errcode='42501';
     end if;
     if new.status is distinct from old.status and new.status in ('queued','running') then
       raise exception 'execution transitions are worker owned' using errcode='42501';
     end if;
     if new.retrieval_settings->'monetary_usage' is distinct from old.retrieval_settings->'monetary_usage' then
       raise exception 'usage is worker owned' using errcode='42501';
     end if;
     if old.retrieval_settings ? 'monetary_usage' and
       (new.source_limits is distinct from old.source_limits or new.model_settings is distinct from old.model_settings
        or (new.retrieval_settings->'research')-'credential_handle' is distinct from (old.retrieval_settings->'research')-'credential_handle') then
       raise exception 'started resource limits are fixed' using errcode='42501';
     end if;
   end if;
 end if;
 return new;
end $$;
create trigger guard_run_resources before insert or update on public.analysis_runs
for each row execute function private.guard_run_resources();
