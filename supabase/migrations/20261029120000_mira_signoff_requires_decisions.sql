-- PRD v2 §6.6: a report becomes reviewed only when every finding it cites has a reviewer decision.
-- The Streamlit app already checks this, but the database must enforce it too, because a client can
-- write to reports directly. Additive only: one function and one trigger.
--
-- A finding is "in the report" when a sentence in the report's evidence_snapshot cites it, the same
-- definition the app uses. The check fails closed: if any cited finding has no finding_reviews row,
-- the reviewed insert is refused.

begin;

create or replace function private.report_cited_finding_ids(p_snapshot jsonb)
returns setof uuid
language sql
immutable
set search_path = ''
as $$
  select distinct (finding_id_text)::uuid
  from jsonb_array_elements(coalesce(p_snapshot -> 'sections', '[]'::jsonb)) as section,
       jsonb_array_elements(coalesce(section -> 'sentences', '[]'::jsonb)) as sentence,
       jsonb_array_elements_text(coalesce(sentence -> 'finding_ids', '[]'::jsonb)) as finding_id_text
$$;

create or replace function private.require_decisions_before_signoff()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_undecided integer;
begin
  if new.review_status <> 'reviewed' then
    return new;
  end if;

  select count(*) into v_undecided
  from private.report_cited_finding_ids(new.evidence_snapshot) as cited(finding_id)
  where not exists (
    select 1
    from public.finding_reviews r
    where r.finding_id = cited.finding_id
      and r.workspace_id = new.workspace_id
  );

  if v_undecided > 0 then
    raise exception 'report cannot be signed off: % cited finding(s) have no reviewer decision', v_undecided
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists reports_require_decisions_before_signoff on public.reports;
create trigger reports_require_decisions_before_signoff
  before insert on public.reports
  for each row execute function private.require_decisions_before_signoff();

comment on function private.require_decisions_before_signoff() is
  'PRD v2 §6.6: refuses a reviewed report while any cited finding has no reviewer decision.';

commit;
