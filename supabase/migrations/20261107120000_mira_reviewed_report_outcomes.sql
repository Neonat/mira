-- Freeze the latest reviewer outcomes into each new reviewed report.
-- Existing report versions and their rendered artifacts remain historical records.
begin;

-- A transaction can record several reviews with the same timestamp. Preserve
-- their insertion order instead of using random UUIDs to decide which is latest.
alter table public.finding_reviews add column if not exists review_sequence bigint generated always as identity;

create or replace function private.require_decisions_before_signoff()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_run_id uuid;
  v_cited uuid[];
  v_needed uuid[];
  v_excluded uuid[];
  v_outcomes jsonb;
  v_sections jsonb := '[]'::jsonb;
  v_sentences jsonb;
  v_section jsonb;
  v_sentence jsonb;
  v_ids uuid[];
  v_remaining uuid[];
  v_text text;
  v_id uuid;
begin
  if new.review_status <> 'reviewed' then
    return new;
  end if;

  -- Use server time and read all latest outcomes in one statement. Subsequent
  -- review events cannot change the decisions saved in this report version.
  new.reviewed_at := clock_timestamp();
  select analysis_run_id into v_run_id from public.analysis_revisions
  where id = new.analysis_revision_id and workspace_id = new.workspace_id;
  select coalesce(array_agg(id), '{}'::uuid[]) into v_cited
  from private.report_cited_finding_ids(new.evidence_snapshot) as cited(id);

  with recursive needed(id) as (
    select unnest(v_cited)
    union
    select d.depends_on_finding_id from public.finding_dependencies d
    join needed n on n.id = d.finding_id
    where d.workspace_id = new.workspace_id
  )
  select coalesce(array_agg(id), '{}'::uuid[]) into v_needed from needed;

  if exists (
    select 1 from unnest(v_needed) as n(id)
    where not exists (
      select 1 from public.analysis_findings f
      where f.id = n.id and f.workspace_id = new.workspace_id and f.analysis_run_id = v_run_id
    )
  ) then
    raise exception 'report cites findings outside its analysis run' using errcode = 'check_violation';
  end if;

  select coalesce(jsonb_object_agg(f.id::text, jsonb_build_object(
    'review_id', r.id, 'decision', r.decision, 'reviewed_at', r.reviewed_at,
    'reviewed_by', r.reviewed_by, 'review_sequence', r.review_sequence,
    'amended_content', r.amended_content, 'exclusion_reason', null
  )), '{}'::jsonb) into v_outcomes
  from public.analysis_findings f
  left join lateral (
    select id, decision, reviewed_at, reviewed_by, review_sequence, amended_content from public.finding_reviews
    where finding_id = f.id and workspace_id = new.workspace_id and reviewed_at <= new.reviewed_at
    order by reviewed_at desc, review_sequence desc limit 1
  ) r on true
  where f.id = any(v_needed) and f.workspace_id = new.workspace_id;

  if exists (select 1 from unnest(v_cited) as c(id)
             where v_outcomes -> c.id::text ->> 'decision' is null) then
    raise exception 'report cannot be signed off: cited finding has no reviewer decision'
      using errcode = 'check_violation';
  end if;

  with recursive excluded(id) as (
    select id from unnest(v_needed) as n(id) where v_outcomes -> id::text ->> 'decision' = 'rejected'
    union
    select d.finding_id from public.finding_dependencies d
    join excluded e on e.id = d.depends_on_finding_id
    where d.workspace_id = new.workspace_id and d.finding_id = any(v_needed)
  )
  select coalesce(array_agg(id), '{}'::uuid[]) into v_excluded from excluded;

  foreach v_id in array v_excluded loop
    v_outcomes := jsonb_set(v_outcomes, array[v_id::text, 'exclusion_reason'], to_jsonb(
      case when v_outcomes -> v_id::text ->> 'decision' = 'rejected' then 'Rejected by reviewer'
           else 'Supporting finding rejected by reviewer' end
    ));
  end loop;

  if exists (select 1 from unnest(v_needed) as n(id)
             where not (id = any(v_excluded)) and v_outcomes -> id::text ->> 'decision' = 'needs_evidence') then
    raise exception 'report cannot be signed off: finding needs evidence' using errcode = 'check_violation';
  end if;

  -- An inference must be reviewed again after an amendment to any ancestor.
  if exists (
    with recursive ancestry(child, parent) as (
      select finding_id, depends_on_finding_id from public.finding_dependencies
      where workspace_id = new.workspace_id and finding_id = any(v_needed)
      union
      select a.child, d.depends_on_finding_id from ancestry a
      join public.finding_dependencies d on d.finding_id = a.parent
      where d.workspace_id = new.workspace_id
    )
    select 1 from ancestry a
    where not (a.child = any(v_excluded))
      and v_outcomes -> a.parent::text ->> 'decision' = 'amended'
      and (coalesce((v_outcomes -> a.child::text ->> 'reviewed_at')::timestamptz, '-infinity'::timestamptz),
           coalesce((v_outcomes -> a.child::text ->> 'review_sequence')::bigint, 0))
          < ((v_outcomes -> a.parent::text ->> 'reviewed_at')::timestamptz,
             (v_outcomes -> a.parent::text ->> 'review_sequence')::bigint)
  ) then
    raise exception 'review the dependent inference again after amending its supporting finding'
      using errcode = 'check_violation';
  end if;

  for v_section in select value from jsonb_array_elements(new.evidence_snapshot -> 'sections') loop
    v_sentences := '[]'::jsonb;
    for v_sentence in select value from jsonb_array_elements(v_section -> 'sentences') loop
      select coalesce(array_agg(value::uuid order by ord), '{}'::uuid[]) into v_ids
      from jsonb_array_elements_text(v_sentence -> 'finding_ids') with ordinality as ids(value, ord);
      if cardinality(v_ids) = 0 then
        v_sentences := v_sentences || jsonb_build_array(v_sentence);
        continue;
      end if;
      select coalesce(array_agg(id order by ord), '{}'::uuid[]) into v_remaining
      from unnest(v_ids) with ordinality as ids(id, ord) where not (id = any(v_excluded));
      if cardinality(v_remaining) = 0 then
        continue;
      end if;
      if v_remaining <> v_ids or exists (
        select 1 from unnest(v_remaining) as ids(id) where v_outcomes -> id::text ->> 'decision' = 'amended'
      ) then
        select string_agg(coalesce(v_outcomes -> f.id::text ->> 'amended_content', f.content), ' ' order by ids.ord)
        into v_text from unnest(v_remaining) with ordinality as ids(id, ord)
        join public.analysis_findings f on f.id = ids.id and f.workspace_id = new.workspace_id;
        v_sentence := jsonb_set(v_sentence, '{text}', to_jsonb(v_text));
        v_sentence := jsonb_set(v_sentence, '{finding_ids}', to_jsonb(v_remaining));
      end if;
      v_sentences := v_sentences || jsonb_build_array(v_sentence);
    end loop;
    v_section := jsonb_set(v_section, '{sentences}', v_sentences);
    v_section := jsonb_set(v_section, '{no_verified_items}', to_jsonb(jsonb_array_length(v_sentences) = 0));
    v_sections := v_sections || jsonb_build_array(v_section);
  end loop;
  new.evidence_snapshot := jsonb_set(new.evidence_snapshot, '{sections}', v_sections);
  new.evidence_snapshot := jsonb_set(new.evidence_snapshot, '{review_outcomes}', v_outcomes);
  new.evidence_snapshot := jsonb_set(new.evidence_snapshot, '{contract_version}', '"1.3"'::jsonb);
  return new;
end;
$$;

comment on function private.require_decisions_before_signoff() is
  'Freezes latest reviewer outcomes, applies amendments and exclusions, blocks evidence requests and stale dependent reviews.';

commit;
