begin;

-- Keep only the per-fact evidence that must be compared again during a guest
-- request. Preparing it once avoids repeatedly unpacking the full snapshot.
create table private.guest_demo_support (
    window_id uuid not null references private.guest_demo_windows(id),
    snapshot_id uuid not null,
    finding_id uuid not null,
    analysis_run_id uuid not null,
    check_id uuid not null,
    method text not null,
    input_fingerprint text not null,
    input_snapshot jsonb not null,
    primary key (window_id, snapshot_id, finding_id)
);
alter table private.guest_demo_support enable row level security;
revoke all on private.guest_demo_support from public, anon, authenticated;

create or replace function public.open_guest_demo(p_report uuid, p_link text, p_minutes integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    ws uuid;
    started timestamptz;
    window_row private.guest_demo_windows%rowtype;
    digest bytea := private.guest_secret_hash(p_link);
    evidence_sources uuid[];
begin
    select workspace_id into ws from public.prepared_reports where id = p_report;
    if ws is null or not private.has_workspace_role(ws, array['admin']) then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    if digest is null or p_minutes is null or p_minutes not in (5, 60) then
        raise exception 'Choose five minutes or one hour and a valid guest link' using errcode = '22023';
    end if;
    perform 1 from public.workspaces where id = ws for no key update;
    if not private.guest_template_allowed(ws, p_report) then
        raise exception 'Guest access requires an available report with permitted, pinned evidence' using errcode = '22023';
    end if;
    -- Validate immutable evidence once. Publication rechecks mutable reviews,
    -- source grants and the exact current machine checks for the same facts.
    perform 1 from public.prepared_report_bindings b
    join public.prepared_facts f using (workspace_id, snapshot_id, finding_id)
    where b.report_id = p_report and b.workspace_id = ws
    order by f.snapshot_id, f.finding_id for share of f;
    if not found or not private.guest_template_allowed(ws, p_report) or exists (
        select 1 from public.prepared_report_bindings b
        where b.report_id = p_report and b.workspace_id = ws
          and not private.prepared_fact_supported(b.snapshot_id, b.finding_id)
    ) then
        raise exception 'Guest access requires current evidence support' using errcode = '22023';
    end if;
    select array_agg(distinct (source.value #>> '{}')::uuid) into evidence_sources
    from public.prepared_report_bindings b
    join public.prepared_snapshots s on s.id = b.snapshot_id and s.workspace_id = b.workspace_id
    cross join lateral jsonb_path_query(
        s.payload->'verifications'->b.finding_id::text->'input_snapshot', '$.**.source_id'
    ) as source(value)
    where b.report_id = p_report and b.workspace_id = ws;
    if coalesce(cardinality(evidence_sources), 0) = 0 then
        raise exception 'Guest access requires permitted source evidence' using errcode = '22023';
    end if;
    started := clock_timestamp();
    update private.guest_demo_windows set closed_at = started where workspace_id = ws and closed_at is null;
    insert into private.guest_demo_windows
        (workspace_id, template_report_id, opened_by, link_hash, opened_at, expires_at, evidence_source_ids)
    values (ws, p_report, auth.uid(), digest, started, started + make_interval(mins => p_minutes), evidence_sources)
    returning * into window_row;
    insert into private.guest_demo_slots(window_id, slot)
    select window_row.id, slot from generate_series(1, 100) as slot;
    insert into private.guest_demo_support
        (window_id, snapshot_id, finding_id, analysis_run_id, check_id, method, input_fingerprint, input_snapshot)
    select window_row.id, b.snapshot_id, b.finding_id,
        (s.payload->'evidence_input'->>'analysis_run_id')::uuid,
        (frozen.item->>'check_id')::uuid,
        case when (f.fact->>'is_inference')::boolean then 'inference_check' else 'llm' end,
        f.input_fingerprint, frozen.item->'input_snapshot'
    from public.prepared_report_bindings b
    join public.prepared_snapshots s on s.id = b.snapshot_id and s.workspace_id = b.workspace_id
    join public.prepared_facts f on f.workspace_id = b.workspace_id
        and f.snapshot_id = b.snapshot_id and f.finding_id = b.finding_id
    cross join lateral (select s.payload->'verifications'->b.finding_id::text as item) frozen
    where b.report_id = p_report and b.workspace_id = ws;
    started := clock_timestamp();
    update private.guest_demo_windows
        set opened_at = started, expires_at = started + make_interval(mins => p_minutes)
        where id = window_row.id returning * into window_row;
    return jsonb_build_object('id', window_row.id, 'expires_at', window_row.expires_at);
end
$$;

create or replace function private.guest_report_evidence_available(
    w private.guest_demo_windows, p_template uuid
) returns boolean language plpgsql volatile set search_path = '' as $$
begin
    -- Guest publications can share these locks. Evidence review takes an
    -- exclusive lock before adding alerts for affected reports.
    perform 1 from public.prepared_report_bindings b
    join public.prepared_facts f using (workspace_id, snapshot_id, finding_id)
    where b.report_id = p_template and b.workspace_id = w.workspace_id
    order by f.snapshot_id, f.finding_id for share of f;
    if not found or not private.guest_window_available(w) then return false; end if;

    -- Windows already open at migration time keep the full validation.
    if not exists (select 1 from private.guest_demo_support where window_id = w.id) then
        return not exists (
            select 1 from public.prepared_report_bindings b
            where b.report_id = p_template and b.workspace_id = w.workspace_id
              and not private.prepared_fact_supported(b.snapshot_id, b.finding_id)
        );
    end if;

    perform 1 from public.sources s
    where s.workspace_id = w.workspace_id and s.id = any(w.evidence_source_ids)
    order by s.id for share;
    if exists (
        select 1 from unnest(w.evidence_source_ids) as source(id)
        where not exists (
            select 1 from public.sources s
            where s.id = source.id and s.workspace_id = w.workspace_id and s.is_active
              and s.permitted_operations @> array['fetch','store_text','quote']::text[]
        )
    ) then return false; end if;

    return not exists (
        select 1 from private.guest_demo_support frozen
        left join lateral (
            select c.id, c.verdict, c.method, c.model, c.input_fingerprint, c.input_snapshot
            from public.claim_checks c
            where c.workspace_id = w.workspace_id and c.finding_id = frozen.finding_id
              and c.analysis_run_id = frozen.analysis_run_id
            order by c.checked_at desc, c.attempt desc, c.id desc
            limit 1 for share
        ) current_check on true
        where frozen.window_id = w.id
          and (current_check.id = frozen.check_id
            and current_check.verdict = 'supported'
            and current_check.model <> ''
            and current_check.method = frozen.method
            and current_check.input_fingerprint = frozen.input_fingerprint
            and current_check.input_snapshot = frozen.input_snapshot) is not true
    );
end
$$;

notify pgrst, 'reload schema';
commit;
