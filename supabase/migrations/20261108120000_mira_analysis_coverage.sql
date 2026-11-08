-- Worker-authored passage coverage, independent of claim verification/corroboration.
begin;
create table public.analysis_coverage_policies (
 workspace_id uuid not null, analysis_run_id uuid not null,
 analysis_revision_id uuid primary key, policy_version integer not null default 1 check(policy_version=1),
 source_ids uuid[] not null, created_by uuid not null references auth.users(id),
 created_at timestamptz not null default clock_timestamp(),
 foreign key(analysis_revision_id,workspace_id,analysis_run_id) references public.analysis_revisions(id,workspace_id,analysis_run_id)
);
create table public.analysis_coverage_documents (
 workspace_id uuid not null, analysis_run_id uuid not null,
 analysis_revision_id uuid not null references public.analysis_coverage_policies(analysis_revision_id),
 document_version_id uuid not null, disposition text not null check(disposition in ('eligible','no_text','ineligible')),
 reason text, created_by uuid not null references auth.users(id), created_at timestamptz not null default clock_timestamp(),
 primary key(analysis_revision_id,document_version_id),
 foreign key(analysis_revision_id,workspace_id,analysis_run_id) references public.analysis_revisions(id,workspace_id,analysis_run_id),
 foreign key(document_version_id,workspace_id) references public.document_versions(id,workspace_id)
);
create table public.analysis_passage_events (
 id uuid primary key default gen_random_uuid(), sequence bigint generated always as identity unique,
 workspace_id uuid not null, analysis_run_id uuid not null, analysis_revision_id uuid not null,
 document_version_id uuid not null, passage_id uuid not null,
 status text not null check(status in ('candidate','attempted','analysed','failed','deferred')),
 batch_id text, agent_step_id uuid, reason text, event_key text not null check(btrim(event_key)<>''),
 created_by uuid not null references auth.users(id), created_at timestamptz not null default clock_timestamp(),
 unique(analysis_revision_id,event_key),
 foreign key(analysis_revision_id,workspace_id,analysis_run_id) references public.analysis_revisions(id,workspace_id,analysis_run_id),
 foreign key(analysis_revision_id,document_version_id) references public.analysis_coverage_documents(analysis_revision_id,document_version_id),
 foreign key(passage_id,document_version_id,workspace_id) references public.document_passages(id,document_version_id,workspace_id),
 foreign key(agent_step_id,workspace_id) references public.agent_steps(id,workspace_id),
 check(status not in ('failed','deferred') or nullif(btrim(reason),'') is not null)
);
create index analysis_passage_events_latest on public.analysis_passage_events(analysis_revision_id,passage_id,sequence desc);

create function private.analysis_coverage_document_reason(p_workspace uuid,p_run uuid,p_revision uuid,p_version uuid)
returns text language plpgsql stable security definer set search_path='' as $$
declare v record; r record; scope uuid[];
begin
 select dv.*,d.source_id,s.is_active,s.permitted_operations,s.jurisdiction_code into v
 from public.document_versions dv join public.documents d on d.id=dv.document_id and d.workspace_id=dv.workspace_id
 join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
 where dv.id=p_version and dv.workspace_id=p_workspace;
 if not found then raise exception 'coverage version scope mismatch' using errcode='check_violation'; end if;
 select a.* into r from public.analysis_runs a join public.analysis_revisions ar on ar.analysis_run_id=a.id and ar.workspace_id=a.workspace_id
 where a.id=p_run and a.workspace_id=p_workspace and ar.id=p_revision;
 if not found then raise exception 'coverage revision scope mismatch' using errcode='check_violation'; end if;
 select source_ids into scope from public.analysis_coverage_policies where analysis_revision_id=p_revision and workspace_id=p_workspace and analysis_run_id=p_run;
 if scope is null then raise exception 'coverage policy missing' using errcode='check_violation'; end if;
 if not(v.source_id=any(scope)) then return 'out_of_scope'; end if;
 if not v.is_active then return 'source_inactive'; end if;
 if not(v.permitted_operations @> array['store_text']::text[]) or
    (not(v.permitted_operations @> array['fetch']::text[]) and coalesce(v.metadata->>'import','')<>'manual') then return 'operation_denied'; end if;
 if v.jurisdiction_code is not null and btrim(v.jurisdiction_code) not in ('','INT') and not(v.jurisdiction_code=any(r.resolved_markets)) then return 'jurisdiction_mismatch'; end if;
 if v.published_at::date>r.as_of_date then return 'future_version'; end if;
 if exists(select 1 from public.document_versions later where later.workspace_id=p_workspace and later.document_id=v.document_id
   and later.version_number>v.version_number and (later.published_at is null or later.published_at::date<=r.as_of_date)) then return 'stale_version'; end if;
 if not exists(select 1 from public.document_passages p where p.document_version_id=p_version and p.workspace_id=p_workspace) then return 'no_text'; end if;
 return null;
end $$;

create function private.validate_analysis_coverage()
returns trigger language plpgsql security definer set search_path='' as $$
declare previous jsonb; actual text; expected text; latest_status text;
begin
 if tg_op<>'INSERT' then raise exception 'analysis coverage is immutable' using errcode='check_violation'; end if;
 if current_setting('role',true) in ('authenticated','anon') or new.created_by is distinct from auth.uid() then
   raise exception 'coverage actor mismatch or untrusted connection' using errcode='check_violation'; end if;
 perform 1 from public.analysis_revisions where id=new.analysis_revision_id and workspace_id=new.workspace_id and analysis_run_id=new.analysis_run_id for update;
 if not found then raise exception 'coverage revision scope mismatch' using errcode='check_violation'; end if;
 if tg_table_name='analysis_coverage_policies' then
   if exists(select 1 from unnest(new.source_ids) sid where sid is null or not exists(select 1 from public.sources s where s.id=sid and s.workspace_id=new.workspace_id)) then
     raise exception 'coverage source scope mismatch' using errcode='check_violation'; end if;
   select to_jsonb(p)-'created_at' into previous from public.analysis_coverage_policies p where p.analysis_revision_id=new.analysis_revision_id;
 elsif tg_table_name='analysis_coverage_documents' then
   select to_jsonb(d)-'created_at' into previous from public.analysis_coverage_documents d where d.analysis_revision_id=new.analysis_revision_id and d.document_version_id=new.document_version_id;
 else
   select to_jsonb(e)-array['id','sequence','created_at'] into previous from public.analysis_passage_events e where e.analysis_revision_id=new.analysis_revision_id and e.event_key=new.event_key;
 end if;
 if previous is not null then
   if previous is distinct from (to_jsonb(new)-case when tg_table_name='analysis_passage_events' then array['id','sequence','created_at'] else array['created_at'] end) then
     raise exception 'coverage idempotency payload mismatch' using errcode='check_violation'; end if;
   return null;
 end if;
 if exists(select 1 from public.reports where analysis_revision_id=new.analysis_revision_id and review_status='reviewed') then
   raise exception 'coverage revision already reviewed' using errcode='check_violation'; end if;
 if tg_table_name='analysis_coverage_documents' then
   actual:=private.analysis_coverage_document_reason(new.workspace_id,new.analysis_run_id,new.analysis_revision_id,new.document_version_id);
   expected:=case when actual is null then 'eligible' when actual='no_text' then 'no_text' else 'ineligible' end;
   if new.disposition<>expected or new.reason is distinct from actual then raise exception 'coverage document eligibility mismatch' using errcode='check_violation'; end if;
 elsif tg_table_name='analysis_passage_events' then
   select status into latest_status from public.analysis_passage_events where analysis_revision_id=new.analysis_revision_id and passage_id=new.passage_id order by sequence desc limit 1;
   if not ((latest_status is null and new.status='candidate') or
           (latest_status='candidate' and new.status in ('attempted','deferred')) or
           (latest_status='attempted' and new.status in ('analysed','failed','deferred'))) then
     raise exception 'invalid coverage phase transition' using errcode='check_violation'; end if;
   if not exists(select 1 from public.analysis_coverage_documents d where d.analysis_revision_id=new.analysis_revision_id and d.document_version_id=new.document_version_id and d.disposition='eligible') then
     raise exception 'coverage passage requires eligible registration' using errcode='check_violation'; end if;
   if new.status<>'candidate' and not exists(select 1 from public.analysis_passage_events e where e.analysis_revision_id=new.analysis_revision_id and e.passage_id=new.passage_id and e.status='candidate') then
     raise exception 'coverage candidate required' using errcode='check_violation'; end if;
   if new.status in ('attempted','analysed','failed') and not exists(select 1 from public.agent_steps a where a.id=new.agent_step_id and a.workspace_id=new.workspace_id and a.analysis_run_id=new.analysis_run_id and a.role='analyst') then
     raise exception 'coverage requires analyst step in same run' using errcode='check_violation'; end if;
   if new.status in ('analysed','failed') and not exists(select 1 from public.analysis_passage_events e where e.analysis_revision_id=new.analysis_revision_id and e.passage_id=new.passage_id and e.status='attempted' and e.batch_id is not distinct from new.batch_id and e.agent_step_id=new.agent_step_id) then
     raise exception 'coverage matching attempt required' using errcode='check_violation'; end if;
 end if;
 -- Identity defaults run before a contended row lock. Allocate the ordering
 -- watermark again after the lock so sequence reflects serialized appends.
 if tg_table_name='analysis_passage_events' then
   new.sequence:=nextval('public.analysis_passage_events_sequence_seq'::regclass);
 end if;
 new.created_at:=clock_timestamp();
 return new;
end $$;

-- Policy/document tables have composite identities; audit without copying text.
create function private.audit_analysis_coverage()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.audit_events(workspace_id,entity_type,entity_id,action,actor_id,details)
 values(new.workspace_id,tg_table_name,coalesce((to_jsonb(new)->>'id')::uuid,new.analysis_revision_id),'insert',new.created_by,
 jsonb_build_object('analysis_revision_id',new.analysis_revision_id));
 return new;
end $$;
do $$ declare t text; begin
 foreach t in array array['analysis_coverage_policies','analysis_coverage_documents','analysis_passage_events'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('revoke all on public.%I from public,anon,authenticated',t);
 execute format('grant select on public.%I to authenticated',t);
 execute format('create policy coverage_member_read on public.%I for select to authenticated using(private.is_workspace_member(workspace_id))',t);
 execute format('create trigger coverage_validate before insert or update or delete on public.%I for each row execute function private.validate_analysis_coverage()',t);
 execute format('create trigger coverage_audit after insert on public.%I for each row execute function private.audit_analysis_coverage()',t);
 end loop;
end $$;
revoke all on sequence public.analysis_passage_events_sequence_seq from public,anon,authenticated;

create function private.capture_analysis_coverage(p_workspace uuid,p_run uuid,p_revision uuid)
returns jsonb language sql stable security definer set search_path='' as $$
 with events as (
 select * from public.analysis_passage_events where workspace_id=p_workspace and analysis_run_id=p_run and analysis_revision_id=p_revision
 ), latest as (
 select distinct on(passage_id) passage_id,document_version_id,status,reason from events order by passage_id,sequence desc
 ), counts as (
 select l.document_version_id,count(*) candidate_passages,
 count(*) filter(where exists(select 1 from events e where e.passage_id=l.passage_id and e.status='attempted')) attempted_passages,
 count(*) filter(where status='analysed') analysed_passages,count(*) filter(where status='failed') failed_passages,
 count(*) filter(where status='deferred') deferred_passages,count(*) filter(where status in ('candidate','attempted')) pending_passages
 from latest l group by l.document_version_id
 ), docs as (
 select cd.document_version_id,d.source_id,s.name source_name,v.title,v.source_url,cd.disposition,cd.reason,
 coalesce(c.candidate_passages,0) candidate_passages,coalesce(c.attempted_passages,0) attempted_passages,
 coalesce(c.analysed_passages,0) analysed_passages,coalesce(c.failed_passages,0) failed_passages,
 coalesce(c.deferred_passages,0) deferred_passages,coalesce(c.pending_passages,0) pending_passages,
 coalesce((select jsonb_object_agg(r.reason,r.n) from (select l.reason,count(*) n from latest l where l.document_version_id=cd.document_version_id and l.reason is not null group by l.reason) r),'{}'::jsonb) reason_counts
 from public.analysis_coverage_documents cd join public.document_versions v on v.id=cd.document_version_id and v.workspace_id=cd.workspace_id
 join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
 join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
 left join counts c on c.document_version_id=cd.document_version_id
 where cd.workspace_id=p_workspace and cd.analysis_run_id=p_run and cd.analysis_revision_id=p_revision
 )
 select jsonb_build_object('policy_version',1,'workspace_id',p_workspace,'analysis_run_id',p_run,'analysis_revision_id',p_revision,
 'event_sequence',coalesce((select max(sequence) from events),0),
 'candidate_passages',coalesce(sum(candidate_passages),0),'attempted_passages',coalesce(sum(attempted_passages),0),
 'analysed_passages',coalesce(sum(analysed_passages),0),'failed_passages',coalesce(sum(failed_passages),0),
 'deferred_passages',coalesce(sum(deferred_passages),0),'pending_passages',coalesce(sum(pending_passages),0),
 'documents',coalesce(jsonb_agg(to_jsonb(docs) order by document_version_id::text),'[]'::jsonb))
 from docs having exists(select 1 from public.analysis_coverage_policies where workspace_id=p_workspace and analysis_run_id=p_run and analysis_revision_id=p_revision)
$$;

-- Preserve the originally supplied legacy version before old wrappers rewrite it.
create function private.guard_analysis_coverage_report()
returns trigger language plpgsql security definer set search_path='' as $$
begin
 perform 1 from public.analysis_revisions where id=new.analysis_revision_id and workspace_id=new.workspace_id for update;
 if not exists(select 1 from public.analysis_coverage_policies where analysis_revision_id=new.analysis_revision_id and workspace_id=new.workspace_id)
 and (new.evidence_snapshot ? 'analysis_coverage' or new.evidence_snapshot->>'contract_version'='1.6') then
 raise exception 'uninstrumented revision cannot claim analysis coverage' using errcode='check_violation'; end if;
 return new;
end $$;
create trigger aa_reports_guard_analysis_coverage before insert on public.reports for each row execute function private.guard_analysis_coverage_report();
create function private.freeze_analysis_coverage()
returns trigger language plpgsql security definer set search_path='' as $$
declare run uuid; summary jsonb; draft_summary jsonb;
begin
 select analysis_run_id into run from public.analysis_revisions where id=new.analysis_revision_id and workspace_id=new.workspace_id for update;
 summary:=private.capture_analysis_coverage(new.workspace_id,run,new.analysis_revision_id);
 if summary is null then return new; end if;
 if new.evidence_snapshot->'analysis_coverage' is distinct from summary then
 raise exception 'analysis coverage missing, stale or forged' using errcode='check_violation'; end if;
 if new.review_status='reviewed' then
 select evidence_snapshot->'analysis_coverage' into draft_summary from public.reports
 where analysis_revision_id=new.analysis_revision_id and workspace_id=new.workspace_id and review_status='draft'
 order by report_version desc limit 1;
 if draft_summary is distinct from summary then raise exception 'review requires latest draft analysis coverage' using errcode='check_violation'; end if;
 end if;
 new.evidence_snapshot:=jsonb_set(new.evidence_snapshot,'{contract_version}','"1.6"'::jsonb);
 return new;
end $$;
create trigger zzzz_reports_freeze_analysis_coverage before insert on public.reports for each row execute function private.freeze_analysis_coverage();
revoke all on function private.analysis_coverage_document_reason(uuid,uuid,uuid,uuid) from public,anon,authenticated;
revoke all on function private.validate_analysis_coverage() from public,anon,authenticated;
revoke all on function private.audit_analysis_coverage() from public,anon,authenticated;
revoke all on function private.capture_analysis_coverage(uuid,uuid,uuid) from public,anon,authenticated;
revoke all on function private.guard_analysis_coverage_report() from public,anon,authenticated;
revoke all on function private.freeze_analysis_coverage() from public,anon,authenticated;
commit;
