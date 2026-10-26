-- PRD v2 §8: agent run trace, plans, expected-source checklist, verifier history,
-- coverage results, re-run links and the extra finding fields the verifier,
-- completeness checker, writer and re-run diff need. Additive only.
--
-- Write model: the orchestrator is a trusted server-side worker on a direct
-- Postgres connection. It sets request.jwt.claim(s) to the initiating user per
-- transaction so auth.uid() and the audit trigger record that user. Tables only
-- the worker writes get read access for app users and no insert grant.

begin;

-- Allowed values for sources.permitted_operations. The column default
-- (array['metadata']) stays valid.
--   metadata    store title, date, URL only
--   fetch       fetch_allowed may download pages from base_url
--   store_text  extracted text may be saved as passages
--   quote       short quotes may appear in reports
--   embed       passages may be embedded for vector search
alter table public.sources
  add constraint sources_permitted_operations_check
  check (permitted_operations <@ array['metadata', 'fetch', 'store_text', 'quote', 'embed']::text[]);

-- Run lifecycle: user cancellation and re-run linkage (§6.1, §6.5).
alter table public.analysis_runs drop constraint analysis_runs_status_check;
alter table public.analysis_runs
  add constraint analysis_runs_status_check
  check (status in ('queued', 'running', 'partial', 'failed', 'cancelled', 'draft', 'reviewed', 'superseded'));

alter table public.analysis_runs
  add column previous_run_id uuid,
  add constraint analysis_runs_previous_run_fk
    foreign key (previous_run_id, workspace_id) references public.analysis_runs (id, workspace_id),
  add constraint analysis_runs_previous_run_not_self check (previous_run_id is null or previous_run_id <> id);

-- Report sections (§9), facts versus inference (§6.3) and the re-run diff key (§6.5).
alter table public.analysis_findings drop constraint analysis_findings_finding_type_check;
alter table public.analysis_findings
  add constraint analysis_findings_finding_type_check
  check (finding_type in (
    'external_fact', 'regulatory_requirement', 'applicability_assessment', 'risk_implication', 'audit_question',
    'obligation_summary', 'deadline', 'jurisdiction_comparison', 'trend', 'industry_development', 'opportunity'
  ));

alter table public.analysis_findings
  add column jurisdiction_code char(2) check (jurisdiction_code is null or jurisdiction_code ~ '^[A-Z]{2}$'),
  add column change_type text check (change_type is null or change_type in ('new', 'amended', 'upcoming', 'unchanged')),
  add column industry_category text check (industry_category is null or industry_category in ('incident', 'case_study', 'best_practice', 'innovation')),
  add column is_inference boolean not null default false,
  add column evidence_confidence_reason text,
  add column key_date date,
  add column key_date_kind text check (key_date_kind is null or key_date_kind in ('published', 'effective', 'deadline', 'consultation_close', 'event')),
  add column regulation_id uuid,
  add column document_id uuid,
  add column diff_key text check (diff_key is null or length(diff_key) between 1 and 300),
  add constraint analysis_findings_key_date_pair check ((key_date is null) = (key_date_kind is null)),
  add constraint analysis_findings_industry_category_type check (industry_category is null or finding_type = 'industry_development'),
  add constraint analysis_findings_regulation_fk
    foreign key (regulation_id, workspace_id) references public.regulations (id, workspace_id),
  add constraint analysis_findings_document_fk
    foreign key (document_id, workspace_id) references public.documents (id, workspace_id);

-- quote_match input (§6.3 step 2). Required for supporting evidence; optional for context.
alter table public.finding_evidence
  add column supporting_quote text check (supporting_quote is null or length(btrim(supporting_quote)) > 0),
  add constraint finding_evidence_supports_has_quote check (support_type <> 'supports' or supporting_quote is not null);

-- An inferred finding cites the verified facts it rests on and falls if they fall (§6.3).
create table public.finding_dependencies (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  finding_id uuid not null,
  depends_on_finding_id uuid not null,
  created_at timestamptz not null default now(),
  foreign key (finding_id, workspace_id, analysis_run_id) references public.analysis_findings (id, workspace_id, analysis_run_id) on delete cascade,
  foreign key (depends_on_finding_id, workspace_id, analysis_run_id) references public.analysis_findings (id, workspace_id, analysis_run_id) on delete cascade,
  unique (finding_id, depends_on_finding_id),
  check (finding_id <> depends_on_finding_id)
);

-- One row per orchestrator step: the live run view and the audit trace (§7.3).
create table public.agent_steps (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  step_no integer not null check (step_no > 0),
  role text not null check (role in (
    'orchestrator', 'planner', 'regulatory_scout', 'industry_scout', 'analyst',
    'verifier', 'completeness_checker', 'writer'
  )),
  jurisdiction_code char(2) check (jurisdiction_code is null or jurisdiction_code ~ '^[A-Z]{2}$'),
  gap_round smallint not null default 0 check (gap_round >= 0),
  status text not null default 'queued' check (status in ('queued', 'running', 'succeeded', 'failed', 'skipped', 'cancelled')),
  contract_version text,
  model text,
  prompt_version text,
  temperature numeric(3, 2) check (temperature is null or temperature between 0 and 2),
  input_refs jsonb not null default '{}'::jsonb check (jsonb_typeof(input_refs) = 'object'),
  output_refs jsonb not null default '{}'::jsonb check (jsonb_typeof(output_refs) = 'object'),
  tokens_in integer check (tokens_in is null or tokens_in >= 0),
  tokens_out integer check (tokens_out is null or tokens_out >= 0),
  started_at timestamptz,
  finished_at timestamptz,
  error text,
  created_at timestamptz not null default now(),
  foreign key (analysis_run_id, workspace_id) references public.analysis_runs (id, workspace_id) on delete cascade,
  unique (analysis_run_id, step_no),
  unique (id, workspace_id),
  check (finished_at is null or started_at is null or finished_at >= started_at),
  check (status <> 'failed' or error is not null)
);

-- Versioned research plan, visible before scouting (§4, AG02).
create table public.research_plans (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  version integer not null check (version > 0),
  contract_version text not null,
  plan jsonb not null check (jsonb_typeof(plan) = 'object'),
  agent_step_id uuid,
  approved_by uuid references auth.users (id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  foreign key (analysis_run_id, workspace_id) references public.analysis_runs (id, workspace_id) on delete cascade,
  foreign key (agent_step_id, workspace_id) references public.agent_steps (id, workspace_id),
  unique (analysis_run_id, version),
  unique (id, workspace_id),
  check ((approved_by is null) = (approved_at is null))
);

-- Completeness checklist per topic × jurisdiction (§6.4).
create table public.expected_sources (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  list_version integer not null check (list_version > 0),
  topic text not null check (length(btrim(topic)) > 0),
  jurisdiction_code char(2) not null check (jurisdiction_code ~ '^[A-Z]{2}$'),
  category text not null check (category in (
    'legislation', 'rule', 'guideline', 'circular', 'consultation', 'enforcement', 'industry'
  )),
  source_id uuid not null,
  document_hint text not null check (length(btrim(document_hint)) > 0),
  url_hint text,
  is_active boolean not null default true,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (source_id, workspace_id) references public.sources (id, workspace_id),
  unique (workspace_id, topic, jurisdiction_code, list_version, document_hint),
  unique (id, workspace_id)
);

-- Verifier verdict history (§6.3). method 'inference_check' is the
-- "introduces no new fact" test for inferred findings.
create table public.claim_checks (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  finding_id uuid not null,
  attempt smallint not null check (attempt > 0),
  method text not null check (method in ('quote_match', 'llm', 'inference_check')),
  verdict text not null check (verdict in ('supported', 'partially_supported', 'unsupported', 'contradicted')),
  reason text not null,
  model text,
  prompt_version text,
  agent_step_id uuid,
  checked_at timestamptz not null default now(),
  foreign key (finding_id, workspace_id, analysis_run_id) references public.analysis_findings (id, workspace_id, analysis_run_id) on delete cascade,
  foreign key (agent_step_id, workspace_id) references public.agent_steps (id, workspace_id),
  unique (finding_id, attempt, method),
  check (method = 'quote_match' or model is not null)
);

-- Completeness table printed in the report (§6.4, §9 section 10).
create table public.coverage_results (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  expected_source_id uuid not null,
  gap_round smallint not null default 0 check (gap_round >= 0),
  status text not null check (status in ('found', 'no_change', 'missing', 'fetch_failed', 'out_of_budget')),
  document_version_id uuid,
  note text,
  created_at timestamptz not null default now(),
  foreign key (analysis_run_id, workspace_id) references public.analysis_runs (id, workspace_id) on delete cascade,
  foreign key (expected_source_id, workspace_id) references public.expected_sources (id, workspace_id),
  foreign key (document_version_id, workspace_id) references public.document_versions (id, workspace_id),
  unique (analysis_run_id, expected_source_id, gap_round)
);

create index analysis_runs_previous_run_idx on public.analysis_runs (workspace_id, previous_run_id);
create index analysis_findings_diff_key_idx on public.analysis_findings (workspace_id, diff_key);
create index finding_dependencies_depends_on_idx on public.finding_dependencies (workspace_id, depends_on_finding_id);
create index agent_steps_run_idx on public.agent_steps (workspace_id, analysis_run_id, step_no);
create index research_plans_run_idx on public.research_plans (workspace_id, analysis_run_id, version desc);
create index expected_sources_lookup_idx on public.expected_sources (workspace_id, topic, jurisdiction_code, list_version, is_active);
create index claim_checks_finding_idx on public.claim_checks (workspace_id, finding_id, attempt);
create index coverage_results_run_idx on public.coverage_results (workspace_id, analysis_run_id, status);

do $agentic_tables$
declare
  table_name text;
begin
  foreach table_name in array array[
    'finding_dependencies', 'agent_steps', 'research_plans', 'expected_sources',
    'claim_checks', 'coverage_results'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all privileges on public.%I from public, anon, authenticated', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for select to authenticated using (private.is_workspace_member(workspace_id))',
      table_name || '_member_read', table_name
    );
    execute format(
      'create trigger %I after insert or update or delete on public.%I for each row execute function private.log_audit_event()',
      table_name || '_audit_log', table_name
    );
  end loop;
end
$agentic_tables$;

create trigger expected_sources_touch_updated_at
  before update on public.expected_sources
  for each row execute function private.touch_updated_at();

-- Curators maintain the expected-source list, like the source catalogue.
grant insert, update on public.expected_sources to authenticated;
create policy expected_sources_curator_insert on public.expected_sources
  for insert to authenticated
  with check (private.has_workspace_role(workspace_id, array['admin', 'curator']::text[]));
create policy expected_sources_curator_update on public.expected_sources
  for update to authenticated
  using (private.has_workspace_role(workspace_id, array['admin', 'curator']::text[]))
  with check (private.has_workspace_role(workspace_id, array['admin', 'curator']::text[]));

-- Analysts link inferred findings to their facts, like finding_evidence.
grant insert on public.finding_dependencies to authenticated;
create policy finding_dependencies_analyst_insert on public.finding_dependencies
  for insert to authenticated
  with check (private.has_workspace_role(workspace_id, array['admin', 'analyst']::text[]));

-- The worker writes plans; an auditor may approve an unapproved plan once, as themselves.
grant update (approved_by, approved_at) on public.research_plans to authenticated;
create policy research_plans_analyst_approve on public.research_plans
  for update to authenticated
  using (approved_at is null and private.has_workspace_role(workspace_id, array['admin', 'analyst']::text[]))
  with check (approved_by = (select auth.uid()) and private.has_workspace_role(workspace_id, array['admin', 'analyst']::text[]));

-- agent_steps, claim_checks and coverage_results stay read-only for app users:
-- only the trusted worker writes them.

commit;
