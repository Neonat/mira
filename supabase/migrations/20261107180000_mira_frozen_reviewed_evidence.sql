-- Preserve the actual checked/reviewed evidence. Historical rows are not backfilled.
begin;

create extension if not exists pgcrypto with schema extensions;

alter table public.claim_checks add column input_snapshot jsonb;
alter table public.claim_checks add column input_fingerprint text;
alter table public.finding_reviews add column input_snapshot jsonb;
alter table public.finding_reviews add column input_fingerprint text;

-- A finding may use distinct quotations from the same passage. Preserve them
-- both, while still collapsing identical links (including nullable context).
alter table public.finding_evidence
  drop constraint finding_evidence_finding_id_analysis_evidence_id_support_ty_key;
-- Fixed-size identity avoids PostgreSQL's B-tree entry limit for long quotes;
-- the complete original quotation remains in supporting_quote.
create unique index finding_evidence_quote_unique on public.finding_evidence
  (finding_id, analysis_evidence_id, support_type,
   (extensions.digest(supporting_quote, 'sha256'))) nulls not distinct;

create function private.evidence_input_fingerprint(p_input jsonb)
returns text language sql immutable strict set search_path = '' as $$
  select pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_input::text, 'UTF8')), 'hex')
$$;

-- One statement snapshot for the full recursive finding/evidence input. This
-- deliberately includes all link types: unseen context cannot become certified.
create function private.capture_evidence_input(p_workspace uuid, p_run uuid, p_revision uuid, p_roots uuid[])
returns jsonb language sql stable security definer set search_path = '' as $$
  with recursive needed(id) as (
    select unnest(p_roots)
    union
    select d.depends_on_finding_id from public.finding_dependencies d
    join needed n on n.id = d.finding_id
    where d.workspace_id = p_workspace and d.analysis_run_id = p_run
  ), findings as (
    select f.* from public.analysis_findings f join needed n on n.id = f.id
    where f.workspace_id = p_workspace and f.analysis_run_id = p_run
      and f.analysis_revision_id = p_revision
  ), links as (
    select e.finding_id, ae.passage_id, ae.document_version_id, e.support_type, e.supporting_quote
    from public.finding_evidence e
    join findings f on f.id = e.finding_id
    join public.analysis_evidence ae on ae.id = e.analysis_evidence_id
      and ae.workspace_id = p_workspace and ae.analysis_run_id = p_run
    where e.workspace_id = p_workspace and e.analysis_run_id = p_run
  ), passage_rows as (
    select distinct p.id, p.document_version_id, v.document_id, d.source_id, s.name as source_name,
      nullif(btrim(s.jurisdiction_code), '') as jurisdiction_code, v.title, v.source_url,
      v.published_at::date as published_at, p.passage_number, p.content,
      coalesce(v.metadata->>'import', '') = 'manual' as imported,
      v.content_sha256, coalesce(p.extraction_version, v.extraction_version) as extraction_version,
      p.page_number, p.char_start, p.char_end
    from links l
    join public.document_passages p on p.id = l.passage_id and p.workspace_id = p_workspace
    join public.document_versions v on v.id = p.document_version_id and v.workspace_id = p_workspace
    join public.documents d on d.id = v.document_id and d.workspace_id = p_workspace
    join public.sources s on s.id = d.source_id and s.workspace_id = p_workspace
  )
  select jsonb_build_object(
    'schema_version', 1, 'workspace_id', p_workspace, 'analysis_run_id', p_run,
    'analysis_revision_id', p_revision,
    'findings', coalesce((select jsonb_object_agg(f.id::text, jsonb_build_object(
      'finding_id', f.id, 'finding_type', f.finding_type, 'title', f.title, 'content', f.content,
      'priority', f.priority, 'evidence_confidence', f.evidence_confidence,
      'priority_reason', f.priority_reason, 'jurisdiction_code', nullif(btrim(f.jurisdiction_code), ''),
      'change_type', f.change_type, 'industry_category', f.industry_category,
      'is_inference', f.is_inference, 'evidence_confidence_reason', f.evidence_confidence_reason,
      'key_date', f.key_date, 'key_date_kind', f.key_date_kind,
      'depends_on', coalesce((select jsonb_agg(d.depends_on_finding_id order by d.depends_on_finding_id)
        from public.finding_dependencies d where d.finding_id = f.id
          and d.workspace_id = p_workspace and d.analysis_run_id = p_run), '[]'::jsonb),
      'evidence', coalesce((select jsonb_agg(jsonb_build_object(
        'passage_id', l.passage_id, 'document_version_id', l.document_version_id,
        'supporting_quote', l.supporting_quote, 'support_type', l.support_type
      ) order by l.passage_id, l.supporting_quote, l.support_type) from links l where l.finding_id = f.id), '[]'::jsonb)
    )) from findings f), '{}'::jsonb),
    'passages', coalesce((select jsonb_object_agg(p.id::text, to_jsonb(p)) from passage_rows p), '{}'::jsonb)
  )
$$;

-- Subsets are derived from the captured JSON, never by re-reading live edges.
create function private.evidence_input_subset(p_input jsonb, p_roots uuid[])
returns jsonb language sql immutable set search_path = '' as $$
  with recursive needed(id) as (
    select id::text from unnest(p_roots) as roots(id)
    union
    select dep.value from needed n
    cross join lateral jsonb_array_elements_text(p_input -> 'findings' -> n.id -> 'depends_on') dep
  ), chosen as (
    select f.key, f.value from jsonb_each(p_input -> 'findings') f join needed n on n.id = f.key
  ), passages as (
    select distinct e.value ->> 'passage_id' as id from chosen f
    cross join lateral jsonb_array_elements(f.value -> 'evidence') e
  )
  select jsonb_build_object(
    'schema_version', p_input -> 'schema_version', 'workspace_id', p_input -> 'workspace_id',
    'analysis_run_id', p_input -> 'analysis_run_id', 'analysis_revision_id', p_input -> 'analysis_revision_id',
    'findings', coalesce((select jsonb_object_agg(key, value) from chosen), '{}'::jsonb),
    'passages', coalesce((select jsonb_object_agg(p.key, p.value)
      from jsonb_each(p_input -> 'passages') p join passages x on x.id = p.key), '{}'::jsonb)
  )
$$;

create function private.capture_finding_review_input()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_finding public.analysis_findings%rowtype;
begin
  if not exists (select 1 from public.workspace_members m where m.workspace_id = new.workspace_id
                and m.user_id = new.reviewed_by and m.role in ('admin','reviewer'))
     or (current_setting('role', true) = 'authenticated' and new.reviewed_by is distinct from auth.uid()) then
    raise exception 'review requires the acting workspace reviewer' using errcode = 'insufficient_privilege';
  end if;
  select * into v_finding from public.analysis_findings
  where id = new.finding_id and workspace_id = new.workspace_id;
  if not found then
    raise exception 'review finding is not available in this workspace' using errcode = 'check_violation';
  end if;
  new.input_snapshot := private.capture_evidence_input(
    new.workspace_id, v_finding.analysis_run_id, v_finding.analysis_revision_id, array[new.finding_id]
  );
  new.input_fingerprint := private.evidence_input_fingerprint(new.input_snapshot);
  return new;
end
$$;
create trigger finding_reviews_capture_input before insert on public.finding_reviews
  for each row execute function private.capture_finding_review_input();

create function private.freeze_reviewed_evidence()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  v_run uuid; v_roots uuid[]; v_input jsonb; v_brief jsonb; v_expected jsonb;
  v_reviewer text; v_verifications jsonb := '{}'::jsonb; v_subset jsonb;
  v_id uuid; v_check public.claim_checks%rowtype; v_review public.finding_reviews%rowtype;
  v_outcome jsonb; v_bundle jsonb;
begin
  if new.review_status <> 'reviewed' then return new; end if;
  if not exists (select 1 from public.workspace_members m where m.workspace_id = new.workspace_id
                and m.user_id = new.reviewed_by and m.role in ('admin','reviewer'))
     or (current_setting('role', true) = 'authenticated' and new.reviewed_by is distinct from auth.uid()) then
    raise exception 'sign-off requires the acting workspace reviewer' using errcode = 'insufficient_privilege';
  end if;
  select analysis_run_id into v_run from public.analysis_revisions
  where id = new.analysis_revision_id and workspace_id = new.workspace_id;
  if v_run is null or new.evidence_snapshot ->> 'analysis_run_id' is distinct from v_run::text
     or new.evidence_snapshot ->> 'analysis_revision_id' is distinct from new.analysis_revision_id::text then
    raise exception 'report snapshot identity does not match its run/revision; generate a fresh verified draft'
      using errcode = 'check_violation';
  end if;
  select coalesce(array_agg(id), '{}'::uuid[]) into v_roots
  from private.report_cited_finding_ids(new.evidence_snapshot) as roots(id);

  -- Input, scope, checklist labels and displayed reviewer identity share a
  -- statement snapshot. Later comparisons use only subsets of this capture.
  select private.capture_evidence_input(new.workspace_id, v_run, new.analysis_revision_id, v_roots),
    jsonb_build_object('topic', pr.risk_topics[1], 'jurisdictions', pr.markets,
      'period_start', pr.reporting_period_start, 'period_end', pr.reporting_period_end,
      'as_of_date', r.as_of_date,
      'plan_requires_approval', coalesce((r.retrieval_settings->>'plan_requires_approval')::boolean, false)),
    coalesce((select jsonb_object_agg(e.id::text, jsonb_build_object(
      'id', e.id, 'list_version', e.list_version, 'jurisdiction_code', btrim(e.jurisdiction_code),
      'category', e.category, 'source_id', e.source_id, 'document_hint', e.document_hint))
      from public.expected_sources e where e.workspace_id = new.workspace_id and e.id in (
        select (x.value ->> 'expected_source_id')::uuid
        from jsonb_array_elements(coalesce(new.evidence_snapshot->'coverage','[]'::jsonb)) x
      )), '{}'::jsonb),
    coalesce((select u.email from auth.users u where u.id = new.reviewed_by), 'reviewer (name not on record)')
  into v_input, v_brief, v_expected, v_reviewer
  from public.analysis_runs r join public.project_revisions pr
    on pr.id = r.project_revision_id and pr.workspace_id = new.workspace_id
  where r.id = v_run and r.workspace_id = new.workspace_id;
  if v_input is null or v_brief->>'topic' is distinct from 'AML/CFT'
     or coalesce(jsonb_array_length(v_brief->'jurisdictions'), 0) = 0
     or v_brief->>'period_start' is null or v_brief->>'period_end' is null
     or (v_brief->>'period_start')::date > (v_brief->>'period_end')::date
     or (v_brief->>'period_end')::date > (v_brief->>'as_of_date')::date then
    raise exception 'reviewed report requires a complete research brief' using errcode = 'check_violation';
  end if;
  if exists (select 1 from unnest(v_roots) x(id) where not (v_input->'findings' ? x.id::text)) then
    raise exception 'reviewed report is missing a required finding' using errcode = 'check_violation';
  end if;
  if exists (select 1 from jsonb_array_elements(coalesce(new.evidence_snapshot->'coverage','[]'::jsonb)) x
    where not (v_expected ? (x.value->>'expected_source_id'))) then
    raise exception 'reviewed report is missing a required checklist label' using errcode = 'check_violation';
  end if;

  for v_id in select key::uuid from jsonb_each(v_input->'findings') order by key loop
    v_subset := private.evidence_input_subset(v_input, array[v_id]);
    select * into v_check from public.claim_checks c
    where c.workspace_id = new.workspace_id and c.analysis_run_id = v_run and c.finding_id = v_id
      and c.checked_at <= new.reviewed_at
    order by c.checked_at desc, c.attempt desc, c.id desc limit 1;
    if not found or v_check.verdict <> 'supported' or coalesce(btrim(v_check.model), '') = ''
       or v_check.method <> (case when (v_input->'findings'->v_id::text->>'is_inference')::boolean
                                 then 'inference_check' else 'llm' end)
       or v_check.input_snapshot is null or v_check.input_snapshot <> v_subset
       or v_check.input_fingerprint is distinct from private.evidence_input_fingerprint(v_subset) then
      raise exception 'evidence changed or verification is unbound; run fresh verification before sign-off'
        using errcode = 'check_violation';
    end if;
    v_outcome := new.evidence_snapshot->'review_outcomes'->v_id::text;
    if v_outcome is null or v_outcome->>'decision' is null
       or v_outcome->>'decision' not in ('accepted','amended') then
      raise exception 'supporting finding needs a reviewer decision before sign-off' using errcode = 'check_violation';
    end if;
    select * into v_review from public.finding_reviews r
    where r.id = (v_outcome->>'review_id')::uuid and r.workspace_id = new.workspace_id and r.finding_id = v_id;
    if not found or v_review.input_snapshot is null or v_review.input_snapshot <> v_subset
       or v_review.input_fingerprint is distinct from private.evidence_input_fingerprint(v_subset) then
      raise exception 'evidence changed since review; review the finding and its dependencies again'
        using errcode = 'check_violation';
    end if;
    v_verifications := v_verifications || jsonb_build_object(v_id::text, jsonb_build_object(
      'check_id', v_check.id, 'method', v_check.method, 'verdict', v_check.verdict,
      'reason', v_check.reason, 'model', v_check.model, 'prompt_version', v_check.prompt_version,
      'checked_at', v_check.checked_at, 'input_fingerprint', v_check.input_fingerprint,
      'attempt', v_check.attempt, 'agent_step_id', v_check.agent_step_id));
  end loop;
  v_bundle := v_input || jsonb_build_object('brief', v_brief, 'expected_sources', v_expected,
    'reviewer_display_name', v_reviewer, 'reviewed_at', new.reviewed_at, 'verifications', v_verifications);
  new.evidence_snapshot := jsonb_set(new.evidence_snapshot, '{evidence_bundle}', v_bundle);
  new.evidence_snapshot := jsonb_set(new.evidence_snapshot, '{contract_version}', '"1.4"'::jsonb);
  return new;
end
$$;
-- Alphabetical ordering runs this after the existing decision/amendment gate.
create trigger zz_reports_freeze_evidence before insert on public.reports
  for each row execute function private.freeze_reviewed_evidence();

create function private.protect_reviewed_snapshot()
returns trigger language plpgsql set search_path = '' as $$
begin
  if old.review_status = 'reviewed' and
     (to_jsonb(new) - 'artifact_storage_path') is distinct from (to_jsonb(old) - 'artifact_storage_path') then
    raise exception 'reviewed report snapshot is immutable; create a new report version'
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;
create trigger reports_protect_reviewed_snapshot before update on public.reports
  for each row execute function private.protect_reviewed_snapshot();

revoke all on function private.evidence_input_fingerprint(jsonb) from public, anon, authenticated;
revoke all on function private.capture_evidence_input(uuid,uuid,uuid,uuid[]) from public, anon, authenticated;
revoke all on function private.evidence_input_subset(jsonb,uuid[]) from public, anon, authenticated;
revoke all on function private.capture_finding_review_input() from public, anon, authenticated;
revoke all on function private.freeze_reviewed_evidence() from public, anon, authenticated;
revoke all on function private.protect_reviewed_snapshot() from public, anon, authenticated;

commit;
