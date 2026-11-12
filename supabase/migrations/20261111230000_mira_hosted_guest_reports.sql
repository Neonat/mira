-- Keep historical one-hour windows valid. New demo windows last five minutes.
begin;

alter table private.guest_demo_windows drop constraint guest_demo_windows_check;
alter table private.guest_demo_windows add constraint guest_demo_window_duration
    check (expires_at - opened_at in (interval '5 minutes', interval '1 hour'));

create or replace function public.open_guest_demo(p_report uuid, p_link text) returns jsonb
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
    values (ws, p_report, auth.uid(), digest, started, started + interval '5 minutes')
    returning * into window_row;
    return jsonb_build_object('id', window_row.id, 'expires_at', window_row.expires_at);
end
$$;

-- Recheck the frozen bindings before publishing. Fact locks serialize with the
-- reviewer so a correction either blocks publication or alerts the new report.
create function private.guest_report_evidence_available(
    w private.guest_demo_windows, p_template uuid
) returns boolean language plpgsql volatile set search_path = '' as $$
begin
    perform 1
    from public.prepared_report_bindings b
    join public.prepared_facts f using (workspace_id, snapshot_id, finding_id)
    where b.report_id = p_template and b.workspace_id = w.workspace_id
    order by f.snapshot_id, f.finding_id for update of f;
    if not found or not private.guest_window_available(w) then return false; end if;
    return not exists (
        select 1 from public.prepared_report_bindings b
        where b.report_id = p_template and b.workspace_id = w.workspace_id
          and not private.prepared_fact_supported(b.snapshot_id, b.finding_id)
    );
end
$$;

-- The approved template already contains the deterministic rendering for these
-- exact pins. Publish that rendering with a new request, timestamp and digest.
create function private.publish_guest_prepared_report(
    p_request uuid, template public.prepared_reports, p_started timestamptz
) returns void language plpgsql set search_path = '' as $$
declare
    rendered text;
    capture jsonb;
    rid uuid;
    generated_at text := to_char(p_started at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00';
begin
    rendered := regexp_replace(template.html,
        '<tr><td>Generated</td><td>[^<]*</td></tr>',
        '<tr><td>Generated</td><td>' || generated_at || '</td></tr>');
    capture := template.capture || jsonb_build_object(
        'request_id', p_request, 'generated_at', p_started,
        'guest_template_report_id', template.id,
        'generation_method', 'publish a fresh copy of the pinned saved-evidence draft',
        'manifest', template.capture->'manifest' || jsonb_build_object(
            'queued_at', p_started, 'generation_started_at', p_started),
        'report_snapshot', template.capture->'report_snapshot' || jsonb_build_object(
            'analysis_run_id', p_request, 'analysis_revision_id', p_request)
    );
    insert into public.prepared_reports(workspace_id,request_id,capture,html,content_sha256,review_state)
    values(template.workspace_id,p_request,capture,rendered,
        encode(sha256(convert_to(rendered,'UTF8')),'hex'),template.review_state)
    returning id into rid;
    insert into public.prepared_report_bindings(report_id,workspace_id,snapshot_id,finding_id,review_id,review_sequence,decision)
    select rid,workspace_id,snapshot_id,finding_id,review_id,review_sequence,decision
    from public.prepared_report_bindings where report_id = template.id;
    update public.prepared_report_requests set status = 'ready', finished_at = clock_timestamp()
    where id = p_request and workspace_id = template.workspace_id;
end
$$;

revoke all on function private.guest_report_evidence_available(private.guest_demo_windows,uuid),
    private.publish_guest_prepared_report(uuid,public.prepared_reports,timestamptz) from public,anon,authenticated;

create or replace function public.guest_demo_submit(p_link text, p_receipt text) returns text
language plpgsql security definer set search_path = '' as $$
declare
    w private.guest_demo_windows%rowtype;
    q public.prepared_report_requests%rowtype;
    digest bytea := private.guest_secret_hash(p_receipt);
    rid uuid;
    submitted_at timestamptz;
    template public.prepared_reports%rowtype;
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
    select * into strict template from public.prepared_reports where id = w.template_report_id;
    if not private.guest_report_evidence_available(w, template.id) then return null; end if;
    rid := gen_random_uuid();
    submitted_at := clock_timestamp();
    insert into public.prepared_report_requests (id, workspace_id, actor_id, brief, source_ids, idempotency_key, status, created_at, generation_started_at)
        values (rid, w.workspace_id, w.opened_by, q.brief, q.source_ids, 'guest-demo:' || rid, 'generating', submitted_at, submitted_at);
    insert into public.prepared_report_request_scopes (request_id, workspace_id, scope_id, snapshot_id)
        select rid, workspace_id, scope_id, snapshot_id
        from public.prepared_report_request_scopes where request_id = q.id;
    insert into private.guest_demo_requests (window_id, workspace_id, receipt_hash, request_id)
        values (w.id, w.workspace_id, digest, rid);
    perform private.publish_guest_prepared_report(rid, template, submitted_at);
    return 'ready';
end
$$;

notify pgrst, 'reload schema';
commit;
