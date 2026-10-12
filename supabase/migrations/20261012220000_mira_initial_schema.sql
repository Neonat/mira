-- Mira initial schema. Apply to the existing Supabase Postgres database.
-- Source versions, domain revisions, analyses, reviews, and reports are evidence
-- records. Application code should add revisions instead of rewriting history.

begin;

create extension if not exists vector with schema extensions;
create schema if not exists private;
revoke all on schema private from public, anon;

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,47}$'),
  name text not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);

create table public.workspace_members (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null check (role in ('admin', 'analyst', 'curator', 'reviewer', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

-- SECURITY DEFINER avoids recursive membership checks inside RLS policies.
-- The private schema is not exposed through the Supabase Data API.
create or replace function private.workspace_role(p_workspace_id uuid)
returns text
language sql
stable
security definer
set search_path = ''
as $function$
  select wm.role
  from public.workspace_members as wm
  where wm.workspace_id = p_workspace_id
    and wm.user_id = (select auth.uid())
;
$function$;

create or replace function private.is_workspace_member(p_workspace_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select private.workspace_role(p_workspace_id) is not null
;
$function$;

create or replace function private.has_workspace_role(
  p_workspace_id uuid,
  p_roles text[]
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select coalesce(private.workspace_role(p_workspace_id) = any (p_roles), false)
;
$function$;

revoke all on function private.workspace_role(uuid) from public, anon;
revoke all on function private.is_workspace_member(uuid) from public, anon;
revoke all on function private.has_workspace_role(uuid, text[]) from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.workspace_role(uuid) to authenticated;
grant execute on function private.is_workspace_member(uuid) to authenticated;
grant execute on function private.has_workspace_role(uuid, text[]) to authenticated;

create table public.market_region_mappings (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  region_code text not null check (region_code ~ '^[A-Z0-9_-]{2,16}$'),
  region_name text not null,
  market_code char(2) not null check (market_code ~ '^[A-Z]{2}$'),
  mapping_version integer not null check (mapping_version > 0),
  valid_from date,
  valid_to date,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (workspace_id, region_code, market_code, mapping_version),
  check (valid_to is null or valid_from is null or valid_to > valid_from),
  unique (id, workspace_id)
);

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  source_key text not null,
  name text not null,
  publisher text,
  source_type text not null check (source_type in ('website', 'rss', 'regulator', 'upload', 'archive', 'manual')),
  base_url text,
  jurisdiction_code char(2) check (jurisdiction_code is null or jurisdiction_code ~ '^[A-Z]{2}$'),
  languages text[] not null default array['en']::text[],
  permitted_operations text[] not null default array['metadata']::text[],
  access_conditions text,
  expected_coverage jsonb not null default '{}'::jsonb,
  connector_config jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, source_key),
  unique (id, workspace_id)
);

create table public.source_coverage (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  source_id uuid not null,
  coverage_year smallint not null check (coverage_year between 1800 and 2200),
  status text not null check (status in ('unknown', 'available', 'ingested', 'partial', 'unavailable', 'failed')),
  verified_at timestamptz,
  item_count integer check (item_count is null or item_count >= 0),
  gap_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (source_id, workspace_id) references public.sources (id, workspace_id) on delete cascade,
  unique (source_id, coverage_year),
  unique (id, workspace_id)
);

create table public.ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  source_id uuid not null,
  status text not null default 'queued' check (status in ('queued', 'running', 'completed', 'completed_with_errors', 'failed', 'cancelled')),
  mode text not null default 'incremental' check (mode in ('incremental', 'backfill', 'manual_upload')),
  date_basis text not null default 'publication' check (date_basis in ('publication', 'event', 'retrieval')),
  requested_from date,
  requested_to date,
  idempotency_key text not null,
  checkpoint jsonb not null default '{}'::jsonb,
  counts jsonb not null default '{"new":0,"updated":0,"unchanged":0,"skipped":0,"failed":0}'::jsonb,
  error_summary text,
  started_at timestamptz,
  finished_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (source_id, workspace_id) references public.sources (id, workspace_id),
  unique (workspace_id, idempotency_key),
  unique (id, workspace_id),
  check (requested_to is null or requested_from is null or requested_to >= requested_from)
);

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  source_id uuid not null,
  document_type text not null default 'news' check (document_type in ('news', 'regulation', 'guidance', 'case_study', 'other')),
  canonical_url text,
  external_id text,
  title text not null,
  first_seen_at timestamptz not null default now(),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (source_id, workspace_id) references public.sources (id, workspace_id),
  unique (id, workspace_id),
  unique (source_id, canonical_url),
  unique (source_id, external_id)
);

create table public.ingestion_run_items (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  run_id uuid not null,
  source_item_key text not null,
  item_url text,
  status text not null default 'pending' check (status in ('pending', 'processing', 'saved', 'unchanged', 'skipped', 'failed')),
  document_id uuid,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  error_message text,
  checkpoint jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  foreign key (run_id, workspace_id) references public.ingestion_runs (id, workspace_id) on delete cascade,
  foreign key (document_id, workspace_id) references public.documents (id, workspace_id),
  unique (run_id, source_item_key),
  unique (id, workspace_id)
);

create table public.document_versions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  document_id uuid not null,
  version_number integer not null check (version_number > 0),
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  source_url text not null,
  title text not null,
  language_code text,
  published_at timestamptz,
  retrieved_at timestamptz not null default now(),
  extraction_status text not null check (extraction_status in ('pending', 'complete', 'partial', 'failed', 'unsupported')),
  extracted_text text,
  storage_path text,
  extraction_version text,
  metadata jsonb not null default '{}'::jsonb,
  supersedes_version_id uuid,
  created_at timestamptz not null default now(),
  foreign key (document_id, workspace_id) references public.documents (id, workspace_id) on delete cascade,
  foreign key (supersedes_version_id, workspace_id) references public.document_versions (id, workspace_id),
  unique (document_id, version_number),
  unique (document_id, content_sha256),
  unique (id, workspace_id)
);

create table public.document_passages (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  document_version_id uuid not null,
  passage_number integer not null check (passage_number > 0),
  content text not null,
  page_number integer check (page_number is null or page_number > 0),
  section_label text,
  char_start integer check (char_start is null or char_start >= 0),
  char_end integer check (char_end is null or char_end >= 0),
  extraction_version text,
  search_vector tsvector generated always as (to_tsvector('english'::regconfig, coalesce(content, ''))) stored,
  created_at timestamptz not null default now(),
  foreign key (document_version_id, workspace_id) references public.document_versions (id, workspace_id) on delete cascade,
  unique (document_version_id, passage_number),
  unique (id, workspace_id),
  unique (id, document_version_id, workspace_id),
  check (char_end is null or char_start is null or char_end >= char_start)
);

-- Local semantic embeddings use a 384-dimensional model for the first release.
-- Model name and revision are stored per row for repeatable rebuilds.
create table public.passage_embeddings (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  passage_id uuid not null,
  model_name text not null,
  model_revision text not null,
  embedding extensions.vector(384) not null,
  created_at timestamptz not null default now(),
  foreign key (passage_id, workspace_id) references public.document_passages (id, workspace_id) on delete cascade,
  unique (passage_id, model_name, model_revision),
  unique (id, workspace_id)
);

create table public.incidents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  lifecycle_status text not null default 'active' check (lifecycle_status in ('active', 'archived', 'merged')),
  merged_into_incident_id uuid,
  first_seen_at timestamptz not null default now(),
  last_material_update_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (merged_into_incident_id, workspace_id) references public.incidents (id, workspace_id),
  unique (id, workspace_id),
  check (merged_into_incident_id is null or merged_into_incident_id <> id)
);

create table public.incident_revisions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  incident_id uuid not null,
  revision_number integer not null check (revision_number > 0),
  title text not null,
  summary text not null,
  factual_status text not null check (factual_status in ('reported', 'alleged', 'confirmed', 'disputed', 'unresolved')),
  event_date_start date,
  event_date_end date,
  unknown_date_reason text,
  entities jsonb not null default '[]'::jsonb check (jsonb_typeof(entities) = 'array'),
  risk_topics text[] not null default '{}'::text[],
  change_reason text not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (incident_id, workspace_id) references public.incidents (id, workspace_id) on delete cascade,
  unique (incident_id, revision_number),
  unique (id, workspace_id),
  check (event_date_end is null or event_date_start is null or event_date_end >= event_date_start),
  check (event_date_start is not null or unknown_date_reason is not null)
);

create table public.incident_geographies (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  incident_revision_id uuid not null,
  geography_role text not null check (geography_role in ('event_location', 'affected_market', 'entity_domicile', 'regulatory_jurisdiction')),
  market_code char(2) check (market_code is null or market_code ~ '^[A-Z]{2}$'),
  region_code text,
  created_at timestamptz not null default now(),
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id) on delete cascade,
  check (market_code is not null or region_code is not null),
  unique (incident_revision_id, geography_role, market_code, region_code)
);

create table public.incident_evidence (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  incident_revision_id uuid not null,
  document_version_id uuid not null,
  passage_id uuid,
  relation text not null check (relation in ('supports', 'contradicts', 'context')),
  curator_note text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id) on delete cascade,
  foreign key (document_version_id, workspace_id) references public.document_versions (id, workspace_id),
  foreign key (passage_id, document_version_id, workspace_id) references public.document_passages (id, document_version_id, workspace_id),
  unique (incident_revision_id, document_version_id, passage_id, relation),
  unique (id, workspace_id, incident_revision_id)
);

-- Reviews are append-only and can target an incident revision as a whole or
-- one of its source-evidence links. No review erases the source.
create table public.incident_revision_reviews (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  incident_revision_id uuid not null,
  incident_evidence_id uuid,
  decision text not null check (decision in ('reviewed', 'disputed', 'excluded')),
  reason text not null,
  idempotency_key text,
  reviewed_by uuid not null references auth.users (id),
  reviewed_at timestamptz not null default now(),
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id) on delete cascade,
  foreign key (incident_evidence_id, workspace_id, incident_revision_id) references public.incident_evidence (id, workspace_id, incident_revision_id),
  unique (workspace_id, idempotency_key),
  unique (id, workspace_id)
);

create table public.incident_relationships (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  from_incident_id uuid not null,
  to_incident_id uuid not null,
  relation text not null check (relation in ('same_event', 'development_of', 'related_case')),
  reason text not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (from_incident_id, workspace_id) references public.incidents (id, workspace_id) on delete cascade,
  foreign key (to_incident_id, workspace_id) references public.incidents (id, workspace_id) on delete cascade,
  check (from_incident_id <> to_incident_id),
  unique (from_incident_id, to_incident_id, relation)
);

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  lifecycle_status text not null default 'active' check (lifecycle_status in ('active', 'archived')),
  owner_id uuid references auth.users (id) on delete set null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id)
);

create table public.project_revisions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  project_id uuid not null,
  revision_number integer not null check (revision_number > 0),
  title text not null,
  objective text not null,
  audit_questions text[] not null default '{}'::text[],
  entity_scope text[] not null default '{}'::text[],
  activities text[] not null default '{}'::text[],
  risk_topics text[] not null default '{}'::text[],
  markets char(2)[] not null default '{}'::char(2)[],
  regions text[] not null default '{}'::text[],
  region_mapping_version integer,
  reporting_period_start date,
  reporting_period_end date,
  change_reason text not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (project_id, workspace_id) references public.projects (id, workspace_id) on delete cascade,
  unique (project_id, revision_number),
  unique (id, workspace_id),
  check (reporting_period_end is null or reporting_period_start is null or reporting_period_end >= reporting_period_start)
);

create table public.project_incidents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  project_revision_id uuid not null,
  incident_revision_id uuid not null,
  relevance_reason text not null,
  link_origin text not null check (link_origin in ('manual', 'suggested_theme', 'system_suggested')),
  review_status text not null check (review_status in ('suggested', 'accepted', 'rejected')),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (project_revision_id, workspace_id) references public.project_revisions (id, workspace_id) on delete cascade,
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id),
  unique (project_revision_id, incident_revision_id),
  unique (id, workspace_id, incident_revision_id)
);

create table public.project_incident_evidence (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  project_incident_id uuid not null,
  incident_revision_id uuid not null,
  incident_evidence_id uuid not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (project_incident_id, workspace_id, incident_revision_id) references public.project_incidents (id, workspace_id, incident_revision_id) on delete cascade,
  foreign key (incident_evidence_id, workspace_id, incident_revision_id) references public.incident_evidence (id, workspace_id, incident_revision_id),
  unique (project_incident_id, incident_evidence_id),
  unique (id, workspace_id)
);

create table public.regulations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  authority text not null,
  instrument_code text,
  canonical_url text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, workspace_id),
  unique (workspace_id, authority, instrument_code)
);

create table public.regulation_versions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  regulation_id uuid not null,
  version_label text not null,
  title text not null,
  instrument_type text not null check (instrument_type in ('act', 'regulation', 'notice', 'guideline', 'consultation', 'enforcement', 'other')),
  jurisdiction_code char(2) not null check (jurisdiction_code ~ '^[A-Z]{2}$'),
  status text not null check (status in ('draft', 'proposed', 'in_force', 'amended', 'repealed', 'withdrawn', 'superseded', 'unknown')),
  published_at date,
  effective_from date,
  effective_to date,
  unknown_dates_reason text,
  institution_types text[] not null default '{}'::text[],
  activities text[] not null default '{}'::text[],
  source_document_version_id uuid not null,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (regulation_id, workspace_id) references public.regulations (id, workspace_id) on delete cascade,
  foreign key (source_document_version_id, workspace_id) references public.document_versions (id, workspace_id),
  unique (regulation_id, version_label),
  unique (id, workspace_id),
  unique (id, workspace_id, source_document_version_id),
  check (effective_to is null or effective_from is null or effective_to > effective_from),
  check (effective_from is not null or unknown_dates_reason is not null)
);

create table public.regulation_provisions (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  regulation_version_id uuid not null,
  source_document_version_id uuid not null,
  provision_ref text not null,
  heading text,
  provision_text text not null,
  passage_id uuid,
  page_number integer check (page_number is null or page_number > 0),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (regulation_version_id, workspace_id, source_document_version_id) references public.regulation_versions (id, workspace_id, source_document_version_id) on delete cascade,
  foreign key (passage_id, source_document_version_id, workspace_id) references public.document_passages (id, document_version_id, workspace_id),
  unique (regulation_version_id, provision_ref),
  unique (id, workspace_id),
  unique (id, regulation_version_id, workspace_id)
);

create table public.theme_suggestions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  generation_key text not null,
  title text not null,
  description text not null,
  markets char(2)[] not null default '{}'::char(2)[],
  period_start date,
  period_end date,
  coverage_summary jsonb not null default '{}'::jsonb,
  generation_settings jsonb not null default '{}'::jsonb,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (workspace_id, generation_key),
  unique (id, workspace_id),
  check (period_end is null or period_start is null or period_end >= period_start)
);

create table public.theme_suggestion_incidents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  theme_suggestion_id uuid not null,
  incident_revision_id uuid not null,
  membership_reason text not null,
  rank integer check (rank is null or rank > 0),
  created_at timestamptz not null default now(),
  foreign key (theme_suggestion_id, workspace_id) references public.theme_suggestions (id, workspace_id) on delete cascade,
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id),
  unique (theme_suggestion_id, incident_revision_id)
);

create table public.theme_suggestion_reviews (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  theme_suggestion_id uuid not null,
  decision text not null check (decision in ('dismissed', 'promoted', 'needs_changes')),
  idempotency_key text not null,
  decision_reason text,
  resulting_project_id uuid,
  reviewed_by uuid references auth.users (id) on delete set null,
  reviewed_at timestamptz not null default now(),
  foreign key (theme_suggestion_id, workspace_id) references public.theme_suggestions (id, workspace_id) on delete cascade,
  foreign key (resulting_project_id, workspace_id) references public.projects (id, workspace_id),
  unique (workspace_id, idempotency_key),
  check ((decision = 'promoted') = (resulting_project_id is not null))
);

create table public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  project_revision_id uuid not null,
  status text not null default 'queued' check (status in ('queued', 'running', 'partial', 'failed', 'draft', 'reviewed', 'superseded')),
  idempotency_key text not null,
  query_mode text not null check (query_mode in ('current', 'historical')),
  as_of_date date not null,
  resolved_markets char(2)[] not null default '{}'::char(2)[],
  region_mapping_version integer,
  retrieval_settings jsonb not null default '{}'::jsonb,
  model_settings jsonb not null default '{}'::jsonb,
  source_limits jsonb not null default '{}'::jsonb,
  failure_summary text,
  started_at timestamptz,
  finished_at timestamptz,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (project_revision_id, workspace_id) references public.project_revisions (id, workspace_id),
  unique (id, workspace_id),
  unique (workspace_id, idempotency_key)
);

create table public.analysis_evidence (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  document_version_id uuid,
  passage_id uuid,
  incident_revision_id uuid,
  regulation_version_id uuid,
  provision_id uuid,
  selection_reason text,
  selected_at timestamptz not null default now(),
  foreign key (analysis_run_id, workspace_id) references public.analysis_runs (id, workspace_id) on delete cascade,
  foreign key (document_version_id, workspace_id) references public.document_versions (id, workspace_id),
  foreign key (passage_id, document_version_id, workspace_id) references public.document_passages (id, document_version_id, workspace_id),
  foreign key (incident_revision_id, workspace_id) references public.incident_revisions (id, workspace_id),
  foreign key (regulation_version_id, workspace_id) references public.regulation_versions (id, workspace_id),
  foreign key (provision_id, regulation_version_id, workspace_id) references public.regulation_provisions (id, regulation_version_id, workspace_id),
  unique (id, workspace_id, analysis_run_id),
  unique nulls not distinct (analysis_run_id, document_version_id, passage_id, incident_revision_id, regulation_version_id, provision_id),
  check (num_nonnulls(document_version_id, passage_id, incident_revision_id, regulation_version_id, provision_id) > 0),
  check (passage_id is null or document_version_id is not null),
  check (provision_id is null or regulation_version_id is not null)
);

create table public.analysis_revisions (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  revision_number integer not null check (revision_number > 0),
  review_status text not null default 'draft' check (review_status in ('draft', 'reviewed', 'superseded')),
  executive_summary text,
  unresolved_questions jsonb not null default '[]'::jsonb check (jsonb_typeof(unresolved_questions) = 'array'),
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (analysis_run_id, workspace_id) references public.analysis_runs (id, workspace_id) on delete cascade,
  unique (analysis_run_id, revision_number),
  unique (id, workspace_id),
  unique (id, workspace_id, analysis_run_id)
);

create table public.analysis_findings (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  analysis_revision_id uuid not null,
  finding_type text not null check (finding_type in ('external_fact', 'regulatory_requirement', 'applicability_assessment', 'risk_implication', 'audit_question')),
  title text not null,
  content text not null,
  applicability_status text check (applicability_status is null or applicability_status in ('applicable', 'not_applicable', 'uncertain', 'not_assessed')),
  priority text not null default 'unrated' check (priority in ('high', 'medium', 'low', 'unrated')),
  evidence_confidence text not null default 'unrated' check (evidence_confidence in ('high', 'medium', 'low', 'unrated')),
  priority_reason text,
  missing_internal_evidence text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  foreign key (analysis_revision_id, workspace_id, analysis_run_id) references public.analysis_revisions (id, workspace_id, analysis_run_id) on delete cascade,
  unique (id, workspace_id),
  unique (id, workspace_id, analysis_run_id)
);

create table public.finding_evidence (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  analysis_run_id uuid not null,
  finding_id uuid not null,
  analysis_evidence_id uuid not null,
  support_type text not null check (support_type in ('supports', 'contradicts', 'context')),
  explanation text,
  created_at timestamptz not null default now(),
  foreign key (finding_id, workspace_id, analysis_run_id) references public.analysis_findings (id, workspace_id, analysis_run_id) on delete cascade,
  foreign key (analysis_evidence_id, workspace_id, analysis_run_id) references public.analysis_evidence (id, workspace_id, analysis_run_id) on delete cascade,
  unique (finding_id, analysis_evidence_id, support_type)
);

create table public.finding_reviews (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null,
  finding_id uuid not null,
  decision text not null check (decision in ('accepted', 'amended', 'rejected', 'needs_evidence')),
  reviewer_note text,
  amended_content text,
  reviewed_by uuid references auth.users (id) on delete set null,
  reviewed_at timestamptz not null default now(),
  foreign key (finding_id, workspace_id) references public.analysis_findings (id, workspace_id) on delete cascade,
  check ((decision = 'amended') = (amended_content is not null))
);

create table public.reports (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version > 0),
  workspace_id uuid not null,
  analysis_revision_id uuid not null,
  report_version integer not null check (report_version > 0),
  format text not null check (format in ('html', 'json')),
  review_status text not null default 'draft' check (review_status in ('draft', 'reviewed')),
  template_version text not null,
  evidence_snapshot jsonb not null,
  artifact_storage_path text,
  generated_by uuid references auth.users (id) on delete set null,
  generated_at timestamptz not null default now(),
  reviewed_by uuid references auth.users (id) on delete set null,
  reviewed_at timestamptz,
  foreign key (analysis_revision_id, workspace_id) references public.analysis_revisions (id, workspace_id),
  unique (analysis_revision_id, report_version),
  unique (id, workspace_id),
  check (
    (review_status = 'draft' and reviewed_at is null and reviewed_by is null)
    or (review_status = 'reviewed' and reviewed_at is not null and reviewed_by is not null)
  )
);

create table public.audit_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  entity_type text not null,
  entity_id uuid not null,
  action text not null,
  previous_revision integer,
  resulting_revision integer,
  request_id text,
  idempotency_key text,
  details jsonb not null default '{}'::jsonb,
  actor_id uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now()
);

-- Log record IDs and changed field names, never row contents. This preserves an
-- audit trail without copying article text, report text, or credentials into logs.
create or replace function private.log_audit_event()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  old_row jsonb := '{}'::jsonb;
  new_row jsonb := '{}'::jsonb;
  row_data jsonb;
  row_workspace_id uuid;
  row_id uuid;
  changed_fields text[];
begin
  if tg_op <> 'INSERT' then
    old_row := to_jsonb(old);
  end if;
  if tg_op <> 'DELETE' then
    new_row := to_jsonb(new);
  end if;
  row_data := case when tg_op = 'DELETE' then old_row else new_row end;
  row_workspace_id := (row_data ->> 'workspace_id')::uuid;
  row_id := (row_data ->> 'id')::uuid;

  select coalesce(array_agg(field_name order by field_name), array[]::text[])
    into changed_fields
  from (
    select key as field_name from jsonb_each(old_row)
    union
    select key as field_name from jsonb_each(new_row)
  ) as fields
  where old_row -> field_name is distinct from new_row -> field_name;

  insert into public.audit_events (
    workspace_id, entity_type, entity_id, action, previous_revision,
    resulting_revision, request_id, idempotency_key, details, actor_id
  ) values (
    row_workspace_id,
    tg_table_name,
    row_id,
    lower(tg_op),
    nullif(old_row ->> 'revision_number', '')::integer,
    nullif(new_row ->> 'revision_number', '')::integer,
    nullif(row_data ->> 'request_id', ''),
    nullif(row_data ->> 'idempotency_key', ''),
    jsonb_build_object('changed_fields', to_jsonb(changed_fields)),
    (select auth.uid())
  );
  return null;
end
$function$;

create or replace function private.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $function$
begin
  new.updated_at := now();
  return new;
end
$function$;

revoke all on function private.log_audit_event() from public, anon;
revoke all on function private.touch_updated_at() from public, anon;
grant execute on function private.log_audit_event() to authenticated;
grant execute on function private.touch_updated_at() to authenticated;

do $audit_triggers$
declare
  table_name text;
begin
  foreach table_name in array array[
    'market_region_mappings', 'sources', 'source_coverage', 'ingestion_runs',
    'documents', 'ingestion_run_items', 'document_versions', 'document_passages',
    'passage_embeddings', 'incidents', 'incident_revisions', 'incident_geographies',
    'incident_evidence', 'incident_revision_reviews', 'incident_relationships',
    'projects', 'project_revisions', 'project_incidents', 'project_incident_evidence',
    'regulations', 'regulation_versions', 'regulation_provisions',
    'theme_suggestions', 'theme_suggestion_incidents', 'theme_suggestion_reviews',
    'analysis_runs', 'analysis_evidence', 'analysis_revisions', 'analysis_findings',
    'finding_evidence', 'finding_reviews', 'reports'
  ] loop
    execute format(
      'create trigger %I after insert or update or delete on public.%I for each row execute function private.log_audit_event()',
      table_name || '_audit_log', table_name
    );
  end loop;
end
$audit_triggers$;

do $updated_at_triggers$
declare
  table_name text;
begin
  foreach table_name in array array[
    'sources', 'source_coverage', 'ingestion_runs', 'ingestion_run_items',
    'incidents', 'projects', 'regulations', 'analysis_runs'
  ] loop
    execute format(
      'create trigger %I before update on public.%I for each row execute function private.touch_updated_at()',
      table_name || '_touch_updated_at', table_name
    );
  end loop;
end
$updated_at_triggers$;

-- Join, queue, date, and local retrieval indexes.
create index market_region_mappings_lookup_idx on public.market_region_mappings (workspace_id, region_code, mapping_version);
create index sources_active_idx on public.sources (workspace_id, is_active, source_type);
create index source_coverage_status_idx on public.source_coverage (workspace_id, status, coverage_year);
create index ingestion_runs_queue_idx on public.ingestion_runs (workspace_id, status, created_at);
create index ingestion_run_items_retry_idx on public.ingestion_run_items (run_id, status);
create index documents_source_idx on public.documents (workspace_id, source_id, first_seen_at desc);
create index document_versions_published_idx on public.document_versions (workspace_id, published_at desc);
create index document_passages_search_idx on public.document_passages using gin (search_vector);
create index passage_embeddings_hnsw_idx on public.passage_embeddings using hnsw (embedding extensions.vector_cosine_ops);
create index incident_revisions_dates_idx on public.incident_revisions (workspace_id, event_date_start, event_date_end);
create index incident_geographies_market_idx on public.incident_geographies (workspace_id, geography_role, market_code);
create index project_incidents_project_idx on public.project_incidents (workspace_id, project_revision_id, review_status);
create index regulation_versions_applicability_idx on public.regulation_versions (workspace_id, jurisdiction_code, effective_from, effective_to);
create index analysis_runs_project_idx on public.analysis_runs (workspace_id, project_revision_id, created_at desc);
create index analysis_evidence_run_idx on public.analysis_evidence (workspace_id, analysis_run_id);
create index analysis_findings_revision_idx on public.analysis_findings (workspace_id, analysis_revision_id, finding_type);
create index reports_revision_idx on public.reports (workspace_id, analysis_revision_id, report_version desc);
create index audit_events_entity_idx on public.audit_events (workspace_id, entity_type, entity_id, created_at desc);

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;

create policy workspaces_member_read on public.workspaces
  for select to authenticated
  using (private.is_workspace_member(id));
create policy workspaces_admin_update on public.workspaces
  for update to authenticated
  using (private.has_workspace_role(id, array['admin']::text[]))
  with check (private.has_workspace_role(id, array['admin']::text[]));
create policy workspace_members_member_read on public.workspace_members
  for select to authenticated
  using (user_id = (select auth.uid()) or private.has_workspace_role(workspace_id, array['admin']::text[]));
create policy workspace_members_admin_insert on public.workspace_members
  for insert to authenticated
  with check (private.has_workspace_role(workspace_id, array['admin']::text[]));
create policy workspace_members_admin_update on public.workspace_members
  for update to authenticated
  using (private.has_workspace_role(workspace_id, array['admin']::text[]))
  with check (private.has_workspace_role(workspace_id, array['admin']::text[]));
create policy workspace_members_admin_delete on public.workspace_members
  for delete to authenticated
  using (private.has_workspace_role(workspace_id, array['admin']::text[]));

grant select, update on public.workspaces to authenticated;
grant select, insert, update, delete on public.workspace_members to authenticated;
revoke all on public.workspaces, public.workspace_members from anon;

-- Enable membership-scoped reads on every workspace-owned table.
do $policies$
declare
  table_name text;
  table_names text[] := array[
    'market_region_mappings', 'sources', 'source_coverage', 'ingestion_runs',
    'documents', 'ingestion_run_items', 'document_versions', 'document_passages',
    'passage_embeddings', 'incidents', 'incident_revisions', 'incident_geographies',
    'incident_evidence', 'incident_revision_reviews', 'incident_relationships',
    'projects', 'project_revisions', 'project_incidents', 'project_incident_evidence',
    'regulations', 'regulation_versions', 'regulation_provisions',
    'theme_suggestions', 'theme_suggestion_incidents', 'theme_suggestion_reviews',
    'analysis_runs', 'analysis_evidence', 'analysis_revisions', 'analysis_findings',
    'finding_evidence', 'finding_reviews', 'reports', 'audit_events'
  ];
begin
  foreach table_name in array table_names loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('revoke all on public.%I from anon', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for select to authenticated using (private.is_workspace_member(workspace_id))',
      table_name || '_member_read', table_name
    );
  end loop;
end
$policies$;

-- Collection maintenance belongs to curators; analysis and project work belongs
-- to analysts; reviewers can append review decisions. App users cannot hard-delete.
do $writes$
declare
  table_name text;
begin
  foreach table_name in array array[
    'sources', 'source_coverage', 'ingestion_runs', 'ingestion_run_items',
    'documents', 'document_versions', 'document_passages', 'passage_embeddings',
    'incidents', 'incident_revisions', 'incident_geographies', 'incident_evidence',
    'incident_relationships'
  ] loop
    execute format('grant insert on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''curator'']::text[]))',
      table_name || '_curator_insert', table_name
    );
  end loop;

  foreach table_name in array array[
    'market_region_mappings'
  ] loop
    execute format('grant insert on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'']::text[]))',
      table_name || '_admin_insert', table_name
    );
  end loop;

  foreach table_name in array array[
    'projects', 'project_revisions', 'project_incidents', 'project_incident_evidence', 'regulations',
    'regulation_versions', 'regulation_provisions', 'theme_suggestions',
    'theme_suggestion_incidents', 'analysis_runs',
    'analysis_evidence', 'analysis_revisions', 'analysis_findings', 'finding_evidence'
  ] loop
    execute format('grant insert on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''analyst'']::text[]))',
      table_name || '_analyst_insert', table_name
    );
  end loop;

  execute 'grant insert on public.incident_revision_reviews to authenticated';
  execute 'create policy incident_revision_reviews_reviewer_insert on public.incident_revision_reviews for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''reviewer'']::text[]) and reviewed_by = (select auth.uid()))';

  execute 'grant insert on public.theme_suggestion_reviews to authenticated';
  execute 'create policy theme_suggestion_reviews_reviewer_insert on public.theme_suggestion_reviews for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''analyst'',''curator'',''reviewer'']::text[]) and reviewed_by = (select auth.uid()))';

  execute 'grant insert on public.finding_reviews to authenticated';
  execute 'create policy finding_reviews_reviewer_insert on public.finding_reviews for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''reviewer'']::text[]) and reviewed_by = (select auth.uid()))';

  execute 'grant insert on public.reports to authenticated';
  execute 'create policy reports_author_insert on public.reports for insert to authenticated with check (private.has_workspace_role(workspace_id, array[''admin'',''analyst'',''reviewer'']::text[]) and generated_by = (select auth.uid()) and (review_status = ''draft'' or (private.has_workspace_role(workspace_id, array[''admin'',''reviewer'']::text[]) and reviewed_by = (select auth.uid()))))';

  foreach table_name in array array[
    'sources', 'source_coverage', 'ingestion_runs', 'ingestion_run_items',
    'documents', 'incidents'
  ] loop
    execute format('grant update on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for update to authenticated using (private.has_workspace_role(workspace_id, array[''admin'',''curator'']::text[])) with check (private.has_workspace_role(workspace_id, array[''admin'',''curator'']::text[]))',
      table_name || '_curator_update', table_name
    );
  end loop;

  foreach table_name in array array[
    'projects', 'regulations', 'analysis_runs'
  ] loop
    execute format('grant update on public.%I to authenticated', table_name);
    execute format(
      'create policy %I on public.%I for update to authenticated using (private.has_workspace_role(workspace_id, array[''admin'',''analyst'']::text[])) with check (private.has_workspace_role(workspace_id, array[''admin'',''analyst'']::text[]))',
      table_name || '_analyst_update', table_name
    );
  end loop;

  execute 'grant update on public.market_region_mappings to authenticated';
  execute 'create policy market_region_mappings_admin_update on public.market_region_mappings for update to authenticated using (private.has_workspace_role(workspace_id, array[''admin'']::text[])) with check (private.has_workspace_role(workspace_id, array[''admin'']::text[]))';
end
$writes$;

-- Search remains inside Mira's Postgres database. Both RPCs are invoker-rights,
-- so the same workspace RLS policies apply to direct queries and search results.
create or replace function public.search_passages(
  p_workspace_id uuid,
  p_query text,
  p_limit integer default 20
)
returns table (
  passage_id uuid,
  document_version_id uuid,
  content text,
  rank_score real
)
language sql
stable
security invoker
set search_path = ''
as $function$
  select
    p.id,
    p.document_version_id,
    p.content,
    ts_rank_cd(p.search_vector, websearch_to_tsquery('english'::regconfig, p_query)) as rank_score
  from public.document_passages as p
  where p.workspace_id = p_workspace_id
    and p.search_vector @@ websearch_to_tsquery('english'::regconfig, p_query)
  order by rank_score desc, p.id
  limit least(greatest(coalesce(p_limit, 20), 1), 100)
$function$;

create or replace function public.match_passages(
  p_workspace_id uuid,
  p_query_embedding extensions.vector(384),
  p_model_name text,
  p_model_revision text,
  p_limit integer default 20
)
returns table (
  passage_id uuid,
  document_version_id uuid,
  content text,
  similarity real
)
language sql
stable
security invoker
set search_path = public, extensions, pg_temp
as $function$
  select
    p.id,
    p.document_version_id,
    p.content,
    (1 - (e.embedding <=> p_query_embedding))::real as similarity
  from public.passage_embeddings as e
  join public.document_passages as p
    on p.id = e.passage_id and p.workspace_id = e.workspace_id
  where e.workspace_id = p_workspace_id
    and e.model_name = p_model_name
    and e.model_revision = p_model_revision
  order by e.embedding <=> p_query_embedding, e.passage_id
  limit least(greatest(coalesce(p_limit, 20), 1), 100)
$function$;

revoke all on function public.search_passages(uuid, text, integer) from public, anon;
revoke all on function public.match_passages(uuid, extensions.vector, text, text, integer) from public, anon;
grant execute on function public.search_passages(uuid, text, integer) to authenticated;
grant execute on function public.match_passages(uuid, extensions.vector, text, text, integer) to authenticated;

-- Seed configuration only. Add Auth users to workspace_members after sign-in;
-- the seed does not grant access to any Supabase dashboard account automatically.
insert into public.workspaces (slug, name)
values ('mira', 'Mira')
on conflict (slug) do nothing;

comment on table public.document_versions is 'Immutable fetched or imported source snapshots. Store text only when source terms permit it.';
comment on table public.document_passages is 'Exact searchable evidence segments tied to one immutable document version.';
comment on table public.incident_revisions is 'Immutable incident facts; use a new revision for corrections.';
comment on table public.project_revisions is 'Immutable project scope snapshots used by analysis runs.';
comment on table public.regulation_versions is 'Immutable instrument versions with jurisdiction and effective dates.';
comment on table public.analysis_evidence is 'Evidence selected for one saved analysis run; findings cite these exact rows.';
comment on table public.reports is 'Immutable report snapshots; exports must render this saved snapshot without new analysis.';
comment on table public.audit_events is 'Append-only application change events. Do not store credentials or full source text here.';

commit;
