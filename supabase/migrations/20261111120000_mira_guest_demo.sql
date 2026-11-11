begin;

create table private.guest_demo_windows (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null,
    template_report_id uuid not null,
    opened_by uuid not null references auth.users(id),
    link_hash bytea not null unique,
    opened_at timestamptz not null,
    expires_at timestamptz not null check (expires_at = opened_at + interval '1 hour'),
    closed_at timestamptz,
    unique (id, workspace_id),
    foreign key (template_report_id, workspace_id) references public.prepared_reports(id, workspace_id)
);
create unique index guest_demo_one_open on private.guest_demo_windows(workspace_id) where closed_at is null;

create table private.guest_demo_requests (
    window_id uuid not null,
    workspace_id uuid not null,
    receipt_hash bytea not null,
    request_id uuid not null unique,
    primary key (window_id, receipt_hash),
    foreign key (window_id, workspace_id) references private.guest_demo_windows(id, workspace_id),
    foreign key (request_id, workspace_id) references public.prepared_report_requests(id, workspace_id)
);
alter table private.guest_demo_windows enable row level security;
alter table private.guest_demo_requests enable row level security;
revoke all on private.guest_demo_windows, private.guest_demo_requests from public, anon, authenticated;

create function private.guest_secret_hash(p_secret text) returns bytea
language sql immutable strict set search_path = '' as $$
    select case when length(p_secret) = 64 and p_secret ~ '^[0-9a-f]{64}$'
                then sha256(decode(p_secret, 'hex')) end
$$;

create function private.guest_template_allowed(p_workspace uuid, p_report uuid) returns boolean
language sql stable set search_path = '' as $$
    select exists (
        select 1 from public.prepared_reports r
        join public.prepared_report_requests q on q.id = r.request_id and q.workspace_id = r.workspace_id
        where r.id = p_report and r.workspace_id = p_workspace and q.status = 'ready'
        and private.prepared_sources_allowed(q.workspace_id, q.source_ids)
        and not exists (
            select 1 from public.sources s
            where s.workspace_id = q.workspace_id and s.id = any(q.source_ids)
              and not ('quote' = any(s.permitted_operations))
        )
        and not exists (select 1 from public.prepared_report_alerts a where a.report_id = r.id)
        and (select array_agg(s.scope_id order by s.scope_id)
             from public.prepared_report_request_scopes s
             join public.prepared_snapshots p on p.id = s.snapshot_id and p.workspace_id = s.workspace_id
             where s.request_id = q.id and s.scope_id = any(p.source_ids))
            = (select array_agg(id order by id) from unnest(q.source_ids) as source(id))
    )
$$;

create function public.open_guest_demo(p_report uuid, p_link text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    ws uuid;
    started timestamptz;
    window_row private.guest_demo_windows%rowtype;
    digest bytea := private.guest_secret_hash(p_link);
begin
    select workspace_id into ws from public.prepared_reports where id = p_report;
    if ws is null or not private.has_workspace_role(ws, array['admin']) then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    if digest is null then raise exception 'Invalid guest link' using errcode = '22023'; end if;
    perform 1 from public.workspaces where id = ws for update;
    if not private.guest_template_allowed(ws, p_report) then
        raise exception 'Guest access requires an available report with permitted, pinned evidence' using errcode = '22023';
    end if;
    started := clock_timestamp();
    update private.guest_demo_windows set closed_at = started where workspace_id = ws and closed_at is null;
    insert into private.guest_demo_windows
        (workspace_id, template_report_id, opened_by, link_hash, opened_at, expires_at)
    values (ws, p_report, auth.uid(), digest, started, started + interval '1 hour')
    returning * into window_row;
    return jsonb_build_object('id', window_row.id, 'expires_at', window_row.expires_at);
end
$$;

create function public.close_guest_demo(p_workspace uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if not private.has_workspace_role(p_workspace, array['admin']) then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    perform 1 from public.workspaces where id = p_workspace for update;
    update private.guest_demo_windows set closed_at = clock_timestamp()
        where workspace_id = p_workspace and closed_at is null;
end
$$;

create function public.guest_demo_admin_status(p_workspace uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
    if not private.has_workspace_role(p_workspace, array['admin']) then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    return (select jsonb_build_object('id', w.id, 'expires_at', w.expires_at, 'report_id', w.template_report_id)
        from private.guest_demo_windows w
        where w.workspace_id = p_workspace and w.closed_at is null and w.expires_at > clock_timestamp());
end
$$;

create function private.guest_window_available(w private.guest_demo_windows) returns boolean
language sql volatile set search_path = '' as $$
    select w.closed_at is null and w.expires_at > clock_timestamp()
        and exists (select 1 from public.workspace_members m
            where m.workspace_id = w.workspace_id and m.user_id = w.opened_by and m.role = 'admin')
        and private.guest_template_allowed(w.workspace_id, w.template_report_id)
$$;

create function public.guest_demo_info(p_link text) returns jsonb
language sql volatile security definer set search_path = '' as $$
    select jsonb_build_object('topic', q.brief->'topic', 'jurisdictions', q.brief->'jurisdictions',
        'period_start', q.brief->'period_start', 'period_end', q.brief->'period_end',
        'expires_at', w.expires_at)
    from private.guest_demo_windows w
    join public.prepared_reports r on r.id = w.template_report_id
    join public.prepared_report_requests q on q.id = r.request_id
    where w.link_hash = private.guest_secret_hash(p_link) and private.guest_window_available(w)
$$;

create function public.guest_demo_submit(p_link text, p_receipt text) returns text
language plpgsql security definer set search_path = '' as $$
declare
    w private.guest_demo_windows%rowtype;
    q public.prepared_report_requests%rowtype;
    digest bytea := private.guest_secret_hash(p_receipt);
    rid uuid;
    existing_status text;
begin
    if digest is null then return null; end if;
    select * into w from private.guest_demo_windows
        where link_hash = private.guest_secret_hash(p_link) for update;
    if not found or not private.guest_window_available(w) then return null; end if;

    select r.status into existing_status from private.guest_demo_requests g
        join public.prepared_report_requests r on r.id = g.request_id
        where g.window_id = w.id and g.receipt_hash = digest;
    if found then return existing_status; end if;
    if (select count(*) from private.guest_demo_requests where window_id = w.id) >= 100 then
        return 'capacity';
    end if;

    select r.* into strict q from public.prepared_report_requests r
        join public.prepared_reports t on t.request_id = r.id and t.workspace_id = r.workspace_id
        where t.id = w.template_report_id;
    rid := gen_random_uuid();
    insert into public.prepared_report_requests (id, workspace_id, actor_id, brief, source_ids, idempotency_key, status)
        values (rid, w.workspace_id, w.opened_by, q.brief, q.source_ids, 'guest-demo:' || rid, 'queued');
    insert into public.prepared_report_request_scopes (request_id, workspace_id, scope_id, snapshot_id)
        select rid, workspace_id, scope_id, snapshot_id
        from public.prepared_report_request_scopes where request_id = q.id;
    insert into private.guest_demo_requests (window_id, workspace_id, receipt_hash, request_id)
        values (w.id, w.workspace_id, digest, rid);
    return 'queued';
end
$$;

create function public.guest_demo_result(p_link text, p_receipt text, p_include_html boolean) returns jsonb
language sql volatile security definer set search_path = '' as $$
    select case
        when exists (select 1 from public.prepared_report_alerts a where a.report_id = r.id)
            then jsonb_build_object('status', 'unavailable')
        when p_include_html and q.status = 'ready'
            then jsonb_build_object('status', q.status, 'html', r.html)
        else jsonb_build_object('status', q.status)
        end
    from private.guest_demo_windows w
    join private.guest_demo_requests g on g.window_id = w.id
    join public.prepared_report_requests q on q.id = g.request_id
    left join public.prepared_reports r on r.request_id = q.id
    where w.link_hash = private.guest_secret_hash(p_link) and g.receipt_hash = private.guest_secret_hash(p_receipt)
      and private.guest_window_available(w)
$$;

revoke all on function private.guest_secret_hash(text), private.guest_template_allowed(uuid,uuid),
    private.guest_window_available(private.guest_demo_windows) from public, anon, authenticated;
revoke all on function public.open_guest_demo(uuid,text), public.close_guest_demo(uuid),
    public.guest_demo_admin_status(uuid), public.guest_demo_info(text), public.guest_demo_submit(text,text),
    public.guest_demo_result(text,text,boolean) from public, anon, authenticated;
grant execute on function public.open_guest_demo(uuid,text), public.close_guest_demo(uuid),
    public.guest_demo_admin_status(uuid) to authenticated;
grant execute on function public.guest_demo_info(text), public.guest_demo_submit(text,text),
    public.guest_demo_result(text,text,boolean) to anon, authenticated;

notify pgrst, 'reload schema';
commit;
