begin;

-- The slide holds a permanent routing key. Store only its digest. Each opening
-- uses a new nonce and routes to a new set of ordinary, expiring guest windows.
create table private.guest_demo_portals (
    key_hash bytea primary key check (octet_length(key_hash) = 32),
    report_ids uuid[] not null check (cardinality(report_ids) between 1 and 3),
    nonce uuid,
    window_ids uuid[] not null default '{}'
);
alter table private.guest_demo_portals enable row level security;
revoke all on private.guest_demo_portals from public, anon, authenticated;

create function private.guest_demo_portal_link(p_key text, nonce uuid, report_id uuid)
returns text language sql immutable strict set search_path = '' as $$
    select encode(sha256(decode(p_key, 'hex') || uuid_send(nonce) || uuid_send(report_id)), 'hex')
$$;

create function private.guest_demo_portal_admin(report_ids uuid[])
returns boolean language sql stable set search_path = '' as $$
    select count(*) = cardinality(report_ids)
        and count(distinct r.workspace_id) = cardinality(report_ids)
        and bool_and(private.has_workspace_role(r.workspace_id, array['admin']))
    from public.prepared_reports r where r.id = any(report_ids)
$$;

create function public.guest_demo_portal_info(p_key text) returns jsonb
language sql volatile security definer set search_path = '' as $$
    select coalesce(jsonb_agg(info.value || jsonb_build_object('link', target.link)
        order by item.position), '[]'::jsonb)
    from private.guest_demo_portals portal
    cross join lateral unnest(portal.report_ids) with ordinality as item(report_id, position)
    cross join lateral (select private.guest_demo_portal_link(p_key, portal.nonce, item.report_id) as link) target
    cross join lateral (select public.guest_demo_info(target.link) as value) info
    where portal.key_hash = private.guest_secret_hash(p_key) and portal.nonce is not null
      and info.value is not null
$$;

create function public.open_guest_demo_portal(p_key text, p_minutes integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
    portal private.guest_demo_portals%rowtype;
    next_nonce uuid := gen_random_uuid();
    target_report uuid;
    opened jsonb;
    windows uuid[] := '{}';
    started timestamptz;
    expires timestamptz;
begin
    select * into portal from private.guest_demo_portals
        where key_hash = private.guest_secret_hash(p_key) for update;
    if not found or private.guest_demo_portal_admin(portal.report_ids) is not true then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    -- Consistent workspace order also serializes concurrent operator actions.
    for target_report in
        select r.id from public.prepared_reports r where r.id = any(portal.report_ids)
        order by r.workspace_id
    loop
        opened := public.open_guest_demo(target_report,
            private.guest_demo_portal_link(p_key, next_nonce, target_report), p_minutes);
        windows := array_append(windows, (opened->>'id')::uuid);
    end loop;
    started := clock_timestamp();
    expires := started + make_interval(mins => p_minutes);
    update private.guest_demo_windows set opened_at = started, expires_at = expires
        where id = any(windows);
    update private.guest_demo_portals set nonce = next_nonce, window_ids = windows
        where key_hash = portal.key_hash;
    return jsonb_build_object('windows', cardinality(windows), 'expires_at', expires);
end
$$;

create function public.close_guest_demo_portal(p_key text) returns void
language plpgsql security definer set search_path = '' as $$
declare
    portal private.guest_demo_portals%rowtype;
begin
    select * into portal from private.guest_demo_portals
        where key_hash = private.guest_secret_hash(p_key) for update;
    if not found or private.guest_demo_portal_admin(portal.report_ids) is not true then
        raise exception 'Guest access requires a workspace admin' using errcode = '42501';
    end if;
    update private.guest_demo_windows set closed_at = clock_timestamp()
        where id = any(portal.window_ids) and closed_at is null;
    update private.guest_demo_portals set nonce = null, window_ids = '{}'
        where key_hash = portal.key_hash;
end
$$;

revoke all on function private.guest_demo_portal_link(text,uuid,uuid),
    private.guest_demo_portal_admin(uuid[]), public.guest_demo_portal_info(text),
    public.open_guest_demo_portal(text,integer), public.close_guest_demo_portal(text)
    from public, anon, authenticated;
grant execute on function public.guest_demo_portal_info(text) to anon, authenticated;
grant execute on function public.open_guest_demo_portal(text,integer),
    public.close_guest_demo_portal(text) to authenticated;

notify pgrst, 'reload schema';
commit;
