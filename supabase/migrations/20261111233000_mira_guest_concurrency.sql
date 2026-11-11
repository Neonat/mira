begin;

alter table private.guest_demo_windows add column evidence_source_ids uuid[];

-- A slot stays claimed for the life of a window. SKIP LOCKED lets guests
-- reserve separate slots while retaining the exact 100-report limit.
create table private.guest_demo_slots (
    window_id uuid not null references private.guest_demo_windows(id),
    slot integer not null check (slot between 1 and 100),
    taken boolean not null default false,
    primary key (window_id, slot)
);
alter table private.guest_demo_slots enable row level security;
revoke all on private.guest_demo_slots from public, anon, authenticated;

insert into private.guest_demo_slots(window_id, slot, taken)
select w.id, slot, slot <= used.total
from private.guest_demo_windows w
cross join lateral (select count(*) as total from private.guest_demo_requests g where g.window_id = w.id) used
cross join generate_series(1, 100) as slot
where w.closed_at is null and w.expires_at > clock_timestamp();

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
    return jsonb_build_object('id', window_row.id, 'expires_at', window_row.expires_at);
end
$$;

create or replace function public.open_guest_demo(p_report uuid, p_link text) returns jsonb
language sql security definer set search_path = '' as $$
    select public.open_guest_demo(p_report, p_link, 5)
$$;

revoke all on function public.open_guest_demo(uuid,text,integer) from public, anon, authenticated;
grant execute on function public.open_guest_demo(uuid,text,integer) to authenticated;

create or replace function public.close_guest_demo(p_workspace uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if not private.has_workspace_role(p_workspace, array['admin']) then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    perform 1 from public.workspaces where id = p_workspace for no key update;
    update private.guest_demo_windows set closed_at = clock_timestamp()
        where workspace_id = p_workspace and closed_at is null;
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
    if w.evidence_source_ids is null then
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
        select 1 from public.prepared_report_bindings b
        join public.prepared_snapshots s on s.id = b.snapshot_id and s.workspace_id = b.workspace_id
        join public.prepared_facts f on f.workspace_id = b.workspace_id
            and f.snapshot_id = b.snapshot_id and f.finding_id = b.finding_id
        cross join lateral (select s.payload->'verifications'->b.finding_id::text as item) frozen
        left join lateral (
            select c.id, c.verdict, c.method, c.model, c.input_fingerprint, c.input_snapshot
            from public.claim_checks c
            where c.workspace_id = b.workspace_id and c.finding_id = b.finding_id
              and c.analysis_run_id = (s.payload->'evidence_input'->>'analysis_run_id')::uuid
            order by c.checked_at desc, c.attempt desc, c.id desc
            limit 1
        ) current_check on true
        where b.report_id = p_template and b.workspace_id = w.workspace_id
          and (current_check.id::text = frozen.item->>'check_id'
            and current_check.verdict = 'supported'
            and current_check.model <> ''
            and current_check.method = case when (f.fact->>'is_inference')::boolean then 'inference_check' else 'llm' end
            and current_check.input_fingerprint = f.input_fingerprint
            and current_check.input_snapshot = frozen.item->'input_snapshot') is not true
    );
end
$$;

create function private.guest_generate(p_link text, p_receipt text, include_html boolean) returns jsonb
language plpgsql set search_path = '' as $$
declare
    w private.guest_demo_windows%rowtype;
    q public.prepared_report_requests%rowtype;
    digest bytea := private.guest_secret_hash(p_receipt);
    rid uuid;
    submitted_at timestamptz;
    template public.prepared_reports%rowtype;
    existing jsonb;
    reserved integer;
    admitted boolean := false;
begin
    if digest is null then return null; end if;
    select * into w from private.guest_demo_windows
        where link_hash = private.guest_secret_hash(p_link) for share;
    if not found or not private.guest_window_available(w) then return null; end if;

    -- Duplicate receipts serialize independently, without blocking other guests.
    if not pg_try_advisory_xact_lock(hashtextextended(w.id::text || encode(digest, 'hex'), 20261111)) then
        return jsonb_build_object('status', 'busy');
    end if;
    existing := public.guest_demo_result(p_link, p_receipt, include_html);
    if existing is not null then return existing; end if;

    -- Bound concurrent publication across demo markets. Busy browsers wait
    -- outside Postgres and retry with the same receipt.
    for worker_slot in 1..6 loop
        if pg_try_advisory_xact_lock(20261111, worker_slot) then
            admitted := true;
            exit;
        end if;
    end loop;
    if not admitted then return jsonb_build_object('status', 'busy'); end if;

    select s.slot into reserved from private.guest_demo_slots s
    where s.window_id = w.id and not s.taken
    order by s.slot limit 1 for update skip locked;
    if not found then
        return jsonb_build_object('status', case when exists (
            select 1 from private.guest_demo_slots s where s.window_id = w.id and not s.taken
        ) then 'busy' else 'capacity' end);
    end if;

    select * into strict template from public.prepared_reports where id = w.template_report_id;
    select * into strict q from public.prepared_report_requests where id = template.request_id;
    if not private.guest_report_evidence_available(w, template.id) then return null; end if;
    rid := gen_random_uuid();
    submitted_at := clock_timestamp();
    insert into public.prepared_report_requests
        (id, workspace_id, actor_id, brief, source_ids, idempotency_key, status, created_at, generation_started_at)
    values (rid, w.workspace_id, w.opened_by, q.brief, q.source_ids,
        'guest-demo:' || rid, 'generating', submitted_at, submitted_at);
    insert into public.prepared_report_request_scopes (request_id, workspace_id, scope_id, snapshot_id)
        select rid, workspace_id, scope_id, snapshot_id
        from public.prepared_report_request_scopes where request_id = q.id;
    insert into private.guest_demo_requests (window_id, workspace_id, receipt_hash, request_id)
        values (w.id, w.workspace_id, digest, rid);
    perform private.publish_guest_prepared_report(rid, template, submitted_at);
    update private.guest_demo_slots set taken = true where window_id = w.id and slot = reserved;
    return public.guest_demo_result(p_link, p_receipt, include_html);
end
$$;

create function public.guest_demo_generate(p_link text, p_receipt text) returns jsonb
language sql volatile security definer set search_path = '' as $$
    select private.guest_generate(p_link, p_receipt, true)
$$;

create or replace function public.guest_demo_submit(p_link text, p_receipt text) returns text
language sql volatile security definer set search_path = '' as $$
    select private.guest_generate(p_link, p_receipt, false)->>'status'
$$;

revoke all on function private.guest_generate(text,text,boolean),
    public.guest_demo_generate(text,text) from public, anon, authenticated;
grant execute on function public.guest_demo_generate(text,text) to anon, authenticated;

notify pgrst, 'reload schema';
commit;
