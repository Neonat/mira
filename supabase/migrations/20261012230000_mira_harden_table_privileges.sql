-- Supabase can grant broad default table privileges to API roles. RLS does not
-- protect TRUNCATE or trigger creation, so remove those grants and re-add only
-- the operations allowed by Mira's row policies.

begin;

do $revoke_api_roles$
declare
  table_name text;
begin
  foreach table_name in array array[
    'workspaces', 'workspace_members', 'market_region_mappings', 'sources',
    'source_coverage', 'ingestion_runs', 'documents', 'ingestion_run_items',
    'document_versions', 'document_passages', 'passage_embeddings', 'incidents',
    'incident_revisions', 'incident_geographies', 'incident_evidence',
    'incident_revision_reviews', 'incident_relationships', 'projects',
    'project_revisions', 'project_incidents', 'project_incident_evidence',
    'regulations', 'regulation_versions', 'regulation_provisions',
    'theme_suggestions', 'theme_suggestion_incidents', 'theme_suggestion_reviews',
    'analysis_runs', 'analysis_evidence', 'analysis_revisions', 'analysis_findings',
    'finding_evidence', 'finding_reviews', 'reports', 'audit_events'
  ] loop
    execute format('revoke all privileges on public.%I from public, anon, authenticated', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
  end loop;
end
$revoke_api_roles$;

revoke all privileges on all sequences in schema public from public, anon, authenticated;
revoke execute on all functions in schema public from public, anon, authenticated;

grant select, update on public.workspaces to authenticated;
grant select, insert, update, delete on public.workspace_members to authenticated;

do $restore_insert_grants$
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
  end loop;

  execute 'grant insert on public.market_region_mappings to authenticated';

  foreach table_name in array array[
    'projects', 'project_revisions', 'project_incidents', 'project_incident_evidence',
    'regulations', 'regulation_versions', 'regulation_provisions', 'theme_suggestions',
    'theme_suggestion_incidents', 'analysis_runs', 'analysis_evidence',
    'analysis_revisions', 'analysis_findings', 'finding_evidence'
  ] loop
    execute format('grant insert on public.%I to authenticated', table_name);
  end loop;

  execute 'grant insert on public.incident_revision_reviews to authenticated';
  execute 'grant insert on public.theme_suggestion_reviews to authenticated';
  execute 'grant insert on public.finding_reviews to authenticated';
  execute 'grant insert on public.reports to authenticated';
end
$restore_insert_grants$;

do $restore_update_grants$
declare
  table_name text;
begin
  foreach table_name in array array[
    'sources', 'source_coverage', 'ingestion_runs', 'ingestion_run_items',
    'documents', 'incidents'
  ] loop
    execute format('grant update on public.%I to authenticated', table_name);
  end loop;

  foreach table_name in array array['projects', 'regulations', 'analysis_runs'] loop
    execute format('grant update on public.%I to authenticated', table_name);
  end loop;

  execute 'grant update on public.market_region_mappings to authenticated';
end
$restore_update_grants$;

-- New Mira tables and RPCs require explicit GRANT statements in later migrations.
alter default privileges for role postgres in schema public
  revoke all privileges on tables from public, anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all privileges on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema public
  revoke execute on functions from anon, authenticated;
alter default privileges for role postgres
  revoke execute on functions from public;

grant execute on function public.search_passages(uuid, text, integer) to authenticated;
grant execute on function public.match_passages(uuid, extensions.vector, text, text, integer) to authenticated;

commit;
