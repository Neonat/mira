-- Keep preparation pointers and guest manifests independent by topic.
begin;

alter table public.preparation_scopes
    drop constraint preparation_scopes_check,
    drop constraint preparation_scopes_workspace_id_source_id_key,
    add column topic text not null default 'AML/CFT' check(topic in ('AML/CFT','Cybersecurity')),
    add unique(workspace_id,source_id,topic);

create or replace function public.request_prepared_report(p_workspace uuid,p_brief jsonb,p_source_ids uuid[],p_idempotency_key text)
returns uuid language plpgsql security definer set search_path='' as $$
declare requested_topic text := p_brief->>'topic'; rid uuid; s record; observed_job uuid; waiting boolean:=false; failed boolean:=false;
begin
 if not private.has_workspace_role(p_workspace,array['admin','analyst']) then raise exception 'request requires analyst role' using errcode='42501'; end if;
 if not private.prepared_sources_allowed(p_workspace,p_source_ids) then raise exception 'source scope is not permitted'; end if;
 if jsonb_typeof(p_brief) is distinct from 'object' or requested_topic is null
    or requested_topic not in ('AML/CFT','Cybersecurity') then
  raise exception 'brief requires a supported topic';
 end if;
 if requested_topic = 'Cybersecurity' and (
  p_brief->'jurisdictions' is distinct from '["AE"]'::jsonb or exists(
   select 1 from public.sources where workspace_id=p_workspace and id=any(p_source_ids)
    and (source_key <> 'cbuae' or base_url is distinct from 'https://centralbank.ae')
  )
 ) then raise exception 'Cybersecurity requires approved UAE federal sources'; end if;
 insert into public.preparation_scopes(id,workspace_id,source_id,topic)
 select case when requested_topic='AML/CFT' then source_id else gen_random_uuid() end,
    p_workspace,source_id,requested_topic
 from (select distinct unnest(p_source_ids) source_id) sources order by source_id
 on conflict(workspace_id,source_id,topic) do nothing;
 perform 1 from public.preparation_scopes where workspace_id=p_workspace and topic=requested_topic and source_id=any(p_source_ids) order by id for update;
 select id into rid from public.prepared_report_requests where workspace_id=p_workspace and actor_id=auth.uid() and idempotency_key=p_idempotency_key;
 if rid is not null then return rid; end if;
 insert into public.prepared_report_requests(workspace_id,actor_id,brief,source_ids,idempotency_key,status)
 values(p_workspace,auth.uid(),p_brief,p_source_ids,p_idempotency_key,'queued') returning id into rid;
 for s in select * from public.preparation_scopes where workspace_id=p_workspace and topic=requested_topic and source_id=any(p_source_ids) order by id loop
  observed_job:=s.active_job_id;
  if observed_job is null then
   select j.id into observed_job from public.preparation_jobs j where j.workspace_id=p_workspace
    and j.status='queued' and coalesce(j.brief->>'topic','AML/CFT')=requested_topic and s.source_id=any(j.source_ids) order by j.created_at,j.id limit 1;
  end if;
  insert into public.prepared_report_request_scopes(request_id,workspace_id,scope_id,job_id,snapshot_id,previous_snapshot_id)
  values(rid,p_workspace,s.id,coalesce(observed_job,s.latest_failed_job_id),case when observed_job is null and s.latest_failed_job_id is null then s.latest_snapshot_id else null end,s.latest_snapshot_id);
  failed:=failed or (observed_job is null and s.latest_failed_job_id is not null);
  waiting:=waiting or observed_job is not null or s.latest_snapshot_id is null;
 end loop;
 if failed then update public.prepared_report_requests set status='evidence_failed',reason='A scheduled refresh failed; explicitly choose previous evidence or await a new request.' where id=rid;
 elsif waiting then update public.prepared_report_requests set status='waiting' where id=rid; end if;
 return rid;
end $$;

create or replace function private.guest_template_allowed(p_workspace uuid, p_report uuid) returns boolean
language sql stable set search_path = '' as $$
    select exists (
        select 1 from public.prepared_reports r
        join public.prepared_report_requests q on q.id = r.request_id and q.workspace_id = r.workspace_id
        where r.id = p_report and r.workspace_id = p_workspace and q.status = 'ready'
        and private.prepared_sources_allowed(q.workspace_id, q.source_ids)
        and not exists (
            select 1 from public.sources s
            where s.workspace_id = q.workspace_id and s.id = any(q.source_ids)
              and not ('quote' = any(s.permitted_operations))
        )
        and not exists (select 1 from public.prepared_report_alerts a where a.report_id = r.id)
        and (select array_agg(scope.source_id order by scope.source_id)
             from public.prepared_report_request_scopes s
             join public.preparation_scopes scope on scope.id = s.scope_id and scope.workspace_id = s.workspace_id
             join public.prepared_snapshots p on p.id = s.snapshot_id and p.workspace_id = s.workspace_id
             where s.request_id = q.id and scope.source_id = any(p.source_ids)
               and scope.topic = q.brief->>'topic')
            = (select array_agg(id order by id) from unnest(q.source_ids) as source(id))
    )
$$;

-- Amend only the topic check in the existing evidence freeze trigger.
do $migration$
declare
    definition text := pg_get_functiondef('private.freeze_reviewed_evidence()'::regprocedure);
    old_check text := $old$v_brief->>'topic' is distinct from 'AML/CFT'$old$;
    new_check text := $new$coalesce(v_brief->>'topic','') not in ('AML/CFT','Cybersecurity')$new$;
begin
    if strpos(definition,old_check)=0 then
        raise exception 'Unexpected reviewed evidence freeze definition';
    end if;
    execute replace(definition,old_check,new_check);
end
$migration$;

commit;
