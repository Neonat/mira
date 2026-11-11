-- Additive scheduled preparation and prepared reports. Legacy reports are unchanged.
begin;
create table public.preparation_jobs (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id),
 actor_id uuid not null references auth.users(id), source_ids uuid[] not null,
 brief jsonb not null, budget jsonb not null, models jsonb not null, settings jsonb not null,
 idempotency_key text not null, status text not null default 'queued' check(status in ('queued','preparing','succeeded','failed','cancelled')),
 phase text not null default 'queued', owner uuid, generation bigint not null default 0, lease_until timestamptz,
 analysis_run_id uuid references public.analysis_runs(id), reason text,
 created_at timestamptz not null default clock_timestamp(), finished_at timestamptz,
 unique(workspace_id,idempotency_key), unique(id,workspace_id)
);
create table public.preparation_scopes (
 id uuid primary key, workspace_id uuid not null, source_id uuid not null,
 active_job_id uuid, latest_snapshot_id uuid, latest_failed_job_id uuid, unique(id,workspace_id), unique(workspace_id,source_id),
 foreign key(source_id,workspace_id) references public.sources(id,workspace_id),
 foreign key(active_job_id,workspace_id) references public.preparation_jobs(id,workspace_id),
 foreign key(latest_failed_job_id,workspace_id) references public.preparation_jobs(id,workspace_id), check(id=source_id)
);
create table public.prepared_snapshots (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null,
 job_id uuid not null unique, generation bigint not null, source_ids uuid[] not null,
 payload jsonb not null, input_fingerprint text not null, known_version_ids uuid[] not null default '{}'::uuid[],
 published_at timestamptz not null default clock_timestamp(), unique(id,workspace_id),
 foreign key(job_id,workspace_id) references public.preparation_jobs(id,workspace_id)
);
alter table public.preparation_scopes add foreign key(latest_snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id);
create table public.prepared_snapshot_parents (
 snapshot_id uuid not null, parent_snapshot_id uuid not null, workspace_id uuid not null,
 source_ids uuid[] not null check(cardinality(source_ids)>0),
 primary key(snapshot_id,parent_snapshot_id), check(snapshot_id<>parent_snapshot_id),
 foreign key(snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id),
 foreign key(parent_snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id)
);
create table public.prepared_facts (
 workspace_id uuid not null, snapshot_id uuid not null, finding_id uuid not null,
 fact jsonb not null, input_fingerprint text not null,
 primary key(snapshot_id,finding_id), unique(snapshot_id,finding_id,workspace_id),
 foreign key(snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id)
);
create table public.prepared_fact_reviews (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null,
 snapshot_id uuid not null, finding_id uuid not null, sequence bigint not null,
 input_fingerprint text not null, decision text not null check(decision in ('accepted','rejected','correction_requested')),
 comment text, actor_id uuid not null references auth.users(id), created_at timestamptz not null default clock_timestamp(),
 unique(snapshot_id,finding_id,sequence),
 foreign key(snapshot_id,finding_id,workspace_id) references public.prepared_facts(snapshot_id,finding_id,workspace_id)
);
create table public.prepared_report_requests (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id),
 actor_id uuid not null references auth.users(id), brief jsonb not null, source_ids uuid[] not null,
 idempotency_key text not null, status text not null check(status in ('queued','waiting','evidence_failed','generating','ready','failed','cancelled')),
 owner uuid, generation bigint not null default 0, lease_until timestamptz, reason text,
 created_at timestamptz not null default clock_timestamp(), generation_started_at timestamptz, finished_at timestamptz,
 unique(workspace_id,actor_id,idempotency_key), unique(id,workspace_id)
);
create table public.prepared_report_request_scopes (
 request_id uuid not null, workspace_id uuid not null, scope_id uuid not null,
 job_id uuid, snapshot_id uuid, previous_snapshot_id uuid, choice_by uuid references auth.users(id), choice_at timestamptz,
 primary key(request_id,scope_id),
 foreign key(request_id,workspace_id) references public.prepared_report_requests(id,workspace_id),
 foreign key(scope_id,workspace_id) references public.preparation_scopes(id,workspace_id),
 foreign key(job_id,workspace_id) references public.preparation_jobs(id,workspace_id),
 foreign key(snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id),
 foreign key(previous_snapshot_id,workspace_id) references public.prepared_snapshots(id,workspace_id)
);
create table public.prepared_reports (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null, request_id uuid not null unique,
 capture jsonb not null, html text not null, content_sha256 text not null,
 review_state text not null check(review_state in ('human_checked','human_review_pending')),
 created_at timestamptz not null default clock_timestamp(), unique(id,workspace_id),
 foreign key(request_id,workspace_id) references public.prepared_report_requests(id,workspace_id)
);
create table public.prepared_report_bindings (
 report_id uuid not null, workspace_id uuid not null, snapshot_id uuid not null, finding_id uuid not null,
 review_id uuid references public.prepared_fact_reviews(id), review_sequence bigint, decision text,
 primary key(report_id,snapshot_id,finding_id),
 foreign key(report_id,workspace_id) references public.prepared_reports(id,workspace_id),
 foreign key(snapshot_id,finding_id,workspace_id) references public.prepared_facts(snapshot_id,finding_id,workspace_id)
);
create table public.prepared_report_alerts (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null, report_id uuid not null,
 snapshot_id uuid not null, finding_id uuid not null, review_id uuid not null references public.prepared_fact_reviews(id),
 decision text not null, created_at timestamptz not null default clock_timestamp(), unique(report_id,review_id),
 foreign key(report_id,workspace_id) references public.prepared_reports(id,workspace_id)
);
create table public.prepared_report_approvals (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null, report_id uuid not null unique,
 actor_id uuid not null references auth.users(id), comment text, capture jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 foreign key(report_id,workspace_id) references public.prepared_reports(id,workspace_id)
);
create table public.preparation_schedules (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.workspaces(id),
 actor_id uuid not null references auth.users(id), source_ids uuid[] not null, brief jsonb not null,
 budget jsonb not null, models jsonb not null, settings jsonb not null,
 frequency_seconds integer not null check(frequency_seconds>0), next_due timestamptz not null, enabled boolean not null default false, error text
);
create table public.preparation_frontier (
 workspace_id uuid not null, source_id uuid not null, url text not null, entry jsonb not null,
 status text not null default 'pending' check(status in ('pending','acquired','failed','deferred')),
 attempts integer not null default 0, error text, job_id uuid not null, generation bigint not null,
 discovered_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp(),
 primary key(workspace_id,source_id,url), foreign key(source_id,workspace_id) references public.sources(id,workspace_id),
 foreign key(job_id,workspace_id) references public.preparation_jobs(id,workspace_id)
);
create function private.prepared_immutable() returns trigger language plpgsql set search_path='' as $$
begin raise exception 'prepared evidence/report history is immutable'; end $$;
do $$ declare t text; begin
 foreach t in array array['preparation_jobs','preparation_scopes','prepared_snapshots','prepared_snapshot_parents','prepared_facts','prepared_fact_reviews','prepared_report_requests','prepared_report_request_scopes','prepared_reports','prepared_report_bindings','prepared_report_alerts','prepared_report_approvals','preparation_schedules','preparation_frontier'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant select on public.%I to authenticated',t);
  execute format('create policy member_read on public.%I for select to authenticated using(private.is_workspace_member(workspace_id))',t);
 end loop;
 foreach t in array array['prepared_snapshots','prepared_snapshot_parents','prepared_facts','prepared_fact_reviews','prepared_reports','prepared_report_bindings','prepared_report_alerts','prepared_report_approvals'] loop
  execute format('create trigger immutable before update or delete on public.%I for each row execute function private.prepared_immutable()',t);
 end loop;
end $$;
create function private.prepared_sources_allowed(p_workspace uuid,p_sources uuid[]) returns boolean language sql stable security definer set search_path='' as $$
 select cardinality(p_sources)>0 and not exists(select 1 from unnest(p_sources) x(id) where not exists(
 select 1 from public.sources s where s.id=x.id and s.workspace_id=p_workspace and s.is_active
 and s.permitted_operations @> array['fetch','store_text']::text[] and coalesce(s.jurisdiction_code,'')<>'MY'
 and upper(s.source_key) not like '%MAS%' and upper(s.source_key) not like '%DFSA%'))
$$;
create function public.request_prepared_report(p_workspace uuid,p_brief jsonb,p_source_ids uuid[],p_idempotency_key text)
returns uuid language plpgsql security definer set search_path='' as $$
declare rid uuid; s record; observed_job uuid; waiting boolean:=false; failed boolean:=false;
begin
 if not private.has_workspace_role(p_workspace,array['admin','analyst']) then raise exception 'request requires analyst role' using errcode='42501'; end if;
 if not private.prepared_sources_allowed(p_workspace,p_source_ids) then raise exception 'source scope is not permitted'; end if;
 if jsonb_typeof(p_brief)<>'object' then raise exception 'brief must be an object'; end if;
 insert into public.preparation_scopes(id,workspace_id,source_id) select distinct x,p_workspace,x from unnest(p_source_ids) x on conflict do nothing;
 perform 1 from public.preparation_scopes where workspace_id=p_workspace and id=any(p_source_ids) order by id for update;
 select id into rid from public.prepared_report_requests where workspace_id=p_workspace and actor_id=auth.uid() and idempotency_key=p_idempotency_key;
 if rid is not null then return rid; end if;
 insert into public.prepared_report_requests(workspace_id,actor_id,brief,source_ids,idempotency_key,status)
 values(p_workspace,auth.uid(),p_brief,p_source_ids,p_idempotency_key,'queued') returning id into rid;
 for s in select * from public.preparation_scopes where workspace_id=p_workspace and id=any(p_source_ids) order by id loop
  observed_job:=s.active_job_id;
  if observed_job is null then
   select j.id into observed_job from public.preparation_jobs j where j.workspace_id=p_workspace
    and j.status='queued' and s.source_id=any(j.source_ids) order by j.created_at,j.id limit 1;
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
create function public.cancel_prepared_report_request(p_request uuid) returns void language plpgsql security definer set search_path='' as $$
begin
 update public.prepared_report_requests set status='cancelled',finished_at=clock_timestamp()
 where id=p_request and actor_id=auth.uid() and private.is_workspace_member(workspace_id) and status not in ('ready','failed','cancelled');
 if not found then raise exception 'request unavailable or terminal'; end if;
end $$;
create function public.choose_prepared_previous(p_request uuid,p_scope uuid) returns void language plpgsql security definer set search_path='' as $$
declare r public.prepared_report_requests%rowtype; e public.prepared_report_request_scopes%rowtype;
begin
 select * into r from public.prepared_report_requests where id=p_request for update;
 if r.actor_id is distinct from auth.uid() or not private.has_workspace_role(r.workspace_id,array['admin','analyst']) then raise exception 'request actor required' using errcode='42501'; end if;
 if r.status not in ('waiting','evidence_failed') then raise exception 'request cannot choose older evidence'; end if;
 select * into e from public.prepared_report_request_scopes where request_id=p_request and scope_id=p_scope;
 if e.previous_snapshot_id is null or not exists(select 1 from public.preparation_jobs where id=e.job_id and status in ('failed','cancelled')) then raise exception 'failed refresh with previous snapshot required'; end if;
 update public.prepared_report_request_scopes set snapshot_id=previous_snapshot_id,choice_by=auth.uid(),choice_at=clock_timestamp() where request_id=p_request and scope_id=p_scope;
 update public.prepared_report_requests set status='waiting',reason=null where id=p_request;
end $$;
create function public.review_prepared_fact(p_snapshot uuid,p_finding uuid,p_decision text,p_comment text) returns uuid language plpgsql security definer set search_path='' as $$
declare f public.prepared_facts%rowtype; rid uuid; seq bigint;
begin
 select * into f from public.prepared_facts where snapshot_id=p_snapshot and finding_id=p_finding for update;
 if not found or not private.has_workspace_role(f.workspace_id,array['admin','reviewer']) then raise exception 'reviewer role required' using errcode='42501'; end if;
 select coalesce(max(sequence),0)+1 into seq from public.prepared_fact_reviews where snapshot_id=p_snapshot and finding_id=p_finding;
 insert into public.prepared_fact_reviews(workspace_id,snapshot_id,finding_id,sequence,input_fingerprint,decision,comment,actor_id)
 values(f.workspace_id,p_snapshot,p_finding,seq,f.input_fingerprint,p_decision,p_comment,auth.uid()) returning id into rid;
 if p_decision in ('rejected','correction_requested') then
 insert into public.prepared_report_alerts(workspace_id,report_id,snapshot_id,finding_id,review_id,decision)
 select f.workspace_id,b.report_id,p_snapshot,p_finding,rid,p_decision from public.prepared_report_bindings b where b.snapshot_id=p_snapshot and b.finding_id=p_finding;
 end if;
 return rid;
end $$;
-- Inspect the exact per-fact verification closure, including nested corroboration
-- candidates and dependency passages. Shared source locks prevent grant revocation
-- between the decision and publication/approval commit. Ingestion is unaffected.
create function private.prepared_input_quote_allowed(p_workspace uuid,p_input jsonb)
returns boolean language plpgsql volatile security definer set search_path='' as $$
declare ids uuid[];
begin
 select array_agg(distinct (x.value#>>'{}')::uuid) into ids
 from jsonb_path_query(p_input,'$.**.source_id') x(value);
 if coalesce(cardinality(ids),0)=0 then return false; end if;
 perform 1 from public.sources where workspace_id=p_workspace and id=any(ids) order by id for share;
 return not exists(select 1 from unnest(ids) i(id) where not exists(
  select 1 from public.sources s where s.workspace_id=p_workspace and s.id=i.id and s.is_active
  and s.permitted_operations @> array['fetch','store_text','quote']::text[]));
end $$;
revoke all on function private.prepared_input_quote_allowed(uuid,jsonb) from public,anon,authenticated;
create function private.prepared_fact_supported(p_snapshot uuid,p_finding uuid) returns boolean language sql volatile security definer set search_path='' as $$
 select coalesce((select c.verdict='supported' and c.model is not null and c.model<>''
 and c.method=case when (f.fact->>'is_inference')::boolean then 'inference_check' else 'llm' end
 and c.id::text=s.payload->'verifications'->p_finding::text->>'check_id'
 and c.input_fingerprint=f.input_fingerprint
 and c.input_fingerprint=private.evidence_input_fingerprint(c.input_snapshot)
 and c.input_snapshot=private.evidence_input_subset(s.payload->'evidence_input',array[p_finding])
 and private.prepared_input_quote_allowed(f.workspace_id,c.input_snapshot)
 from public.prepared_facts f join public.prepared_snapshots s on s.id=f.snapshot_id
 join lateral(select * from public.claim_checks cc where cc.workspace_id=f.workspace_id and cc.finding_id=p_finding
 and cc.analysis_run_id=(s.payload->'evidence_input'->>'analysis_run_id')::uuid order by checked_at desc,attempt desc,id desc limit 1)c on true
 where f.snapshot_id=p_snapshot and f.finding_id=p_finding),false)
$$;
revoke all on function private.prepared_fact_supported(uuid,uuid) from public,anon,authenticated;
create function public.approve_prepared_report(p_report uuid,p_comment text) returns uuid language plpgsql security definer set search_path='' as $$
declare r public.prepared_reports%rowtype; b record; decision text; aid uuid; captures jsonb:='[]'::jsonb;
begin
 select * into r from public.prepared_reports where id=p_report;
 if not found or not private.has_workspace_role(r.workspace_id,array['admin','reviewer']) then raise exception 'reviewer role required' using errcode='42501'; end if;
 if r.review_state<>'human_checked' then raise exception 'pending historical report requires a new checked revision'; end if;
 perform 1 from public.prepared_facts f join public.prepared_report_bindings pb on pb.snapshot_id=f.snapshot_id and pb.finding_id=f.finding_id where pb.report_id=p_report order by f.snapshot_id,f.finding_id for update of f;
 if not exists(select 1 from public.prepared_report_bindings where report_id=p_report) then raise exception 'report has no supported bindings'; end if;
 for b in select * from public.prepared_report_bindings where report_id=p_report loop
  select v.decision into decision from public.prepared_fact_reviews v where v.snapshot_id=b.snapshot_id and v.finding_id=b.finding_id order by sequence desc limit 1;
  if decision is distinct from 'accepted' then raise exception 'all included evidence must currently be accepted'; end if;
  if not private.prepared_fact_supported(b.snapshot_id,b.finding_id) then raise exception 'included evidence lacks current machine support'; end if;
  if not private.prepared_sources_allowed(r.workspace_id,(select source_ids from public.prepared_snapshots where id=b.snapshot_id)) then raise exception 'source permission revoked'; end if;
  captures:=captures||jsonb_build_array(to_jsonb(b)||jsonb_build_object('current_review',(select to_jsonb(v) from public.prepared_fact_reviews v where v.snapshot_id=b.snapshot_id and v.finding_id=b.finding_id order by sequence desc limit 1)));
 end loop;
 insert into public.prepared_report_approvals(workspace_id,report_id,actor_id,comment,capture) values(r.workspace_id,p_report,auth.uid(),p_comment,jsonb_build_object('report_sha256',r.content_sha256,'bindings',captures)) returning id into aid;
 return aid;
end $$;
revoke all on function private.prepared_sources_allowed(uuid,uuid[]) from public,anon,authenticated;
revoke all on function private.prepared_immutable() from public,anon,authenticated;
revoke all on function public.request_prepared_report(uuid,jsonb,uuid[],text),public.cancel_prepared_report_request(uuid),public.choose_prepared_previous(uuid,uuid),public.review_prepared_fact(uuid,uuid,text,text),public.approve_prepared_report(uuid,text) from public,anon;
grant execute on function public.request_prepared_report(uuid,jsonb,uuid[],text),public.cancel_prepared_report_request(uuid),public.choose_prepared_previous(uuid,uuid),public.review_prepared_fact(uuid,uuid,text,text),public.approve_prepared_report(uuid,text) to authenticated;
commit;
