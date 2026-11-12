-- One-time operator revision of the 139-finding Hong Kong guest template.
-- The two new citations add only original paraphrases, review metadata,
-- and publisher links.
begin;
set local statement_timeout = '55s';

do $revise$
declare
    base_id constant uuid := '4b3b1acf-f44e-4fa9-a5b0-41d56f8de1b3';
    revision_id constant uuid := '291353ea-179f-4e7c-89e4-5cd58de83419';
    new_request_id constant uuid := '58be66a0-b4be-4400-8c4d-a1b26da91448';
    other_templates constant uuid[] := array['012cb985-ec1a-4482-acfc-7f0d25532bc5',
        'f5af7946-53e9-4b1f-85e7-8213675a44d0']::uuid[];
    links constant jsonb := $links$[
        {
            "publisher": "Wolfsberg Group",
            "label": "Risk-based approach guidance",
            "published_on": "2026-06-23",
            "source_url": "https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach",
            "paraphrase": "Wolfsberg advises banks to direct resources toward their most significant financial-crime risks and scale back controls that contribute little.",
            "source_locator": "Opening discussion of how to allocate resources and assess effectiveness"
        },
        {
            "publisher": "Wolfsberg Group",
            "label": "Banking services for non-bank payment providers",
            "published_on": "2026-07-15",
            "source_url": "https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services",
            "paraphrase": "Wolfsberg advises banks to adjust due diligence and monitoring to the risks of the payment services each provider actually offers.",
            "source_locator": "Bullet on applying the risk-based approach to payment provider relationships"
        }
    ]$links$::jsonb;
    review constant jsonb := '{"decision":"accepted","reviewed_on":"2026-11-12","method":"publisher-page comparison","checked_by":"Codex","authorization":"Operator approved inclusion of the displayed paraphrases"}'::jsonb;
    portal private.guest_demo_portals%rowtype;
    base public.prepared_reports%rowtype;
    prior_request public.prepared_report_requests%rowtype;
    wolfsberg_source_id uuid;
    reviewed_links jsonb;
    rendered_items text;
    rendered text;
    captured jsonb;
begin
    select * into strict portal from private.guest_demo_portals
    where cardinality(report_ids) = 3 and report_ids @> other_templates
      and (base_id = any(report_ids) or revision_id = any(report_ids))
    for update;
    select * into strict base from public.prepared_reports where id = base_id;
    perform 1 from public.workspaces where id = base.workspace_id for no key update;
    if exists (select 1 from private.guest_demo_windows w
        where (w.id = any(portal.window_ids) or w.workspace_id = base.workspace_id)
          and w.closed_at is null and w.expires_at > clock_timestamp()) then
        raise exception 'A guest window remains open';
    end if;

    select * into strict prior_request from public.prepared_report_requests q where q.id = base.request_id;
    if base.content_sha256 is distinct from 'd2d6bb4ef4680b872f62fbd67f54a57411bf0fb1e15b43340bbaf00316cbc1d3'
        or encode(sha256(convert_to(base.html, 'UTF8')), 'hex') is distinct from base.content_sha256
        or base.review_state <> 'human_review_pending'
        or base.capture ? 'reviewed_link_citations'
        or not private.guest_template_allowed(base.workspace_id, base_id)
        or (select count(*) from public.prepared_report_bindings b where b.report_id = base_id) <> 139
        or (length(base.html) - length(replace(base.html, '</body>', ''))) <> length('</body>') then
        raise exception 'The previous Hong Kong template does not match the expected draft';
    end if;

    select s.id into strict wolfsberg_source_id from public.sources s
    where s.workspace_id = base.workspace_id and s.source_key = 'wolfsberg' and s.is_active
      and s.permitted_operations @> array['metadata', 'fetch']::text[]
      and s.permitted_operations <@ array['metadata', 'fetch']::text[]
    for share;
    if exists (select 1 from public.documents d join public.document_versions v on v.document_id = d.id
        where d.workspace_id = base.workspace_id and d.source_id = wolfsberg_source_id) then
        raise exception 'The workspace already has Wolfsberg source versions';
    end if;

    -- The approved records below contain plain text and fixed publisher URLs.
    -- Reject unsafe markup if an operator edits the input later.
    if exists (select 1 from jsonb_array_elements(links) l(value)
        where value->>'source_url' !~ '^https://wolfsberg-group\.org/news/[a-z-]+$'
           or concat(value->>'label', value->>'paraphrase', value->>'published_on') ~ '[<>&"]') then
        raise exception 'Unexpected citation text or URL';
    end if;
    select jsonb_agg(value || jsonb_build_object('review', review) order by position),
        string_agg(format('<li><p>%s</p><a href="%s" rel="noopener noreferrer">%s</a> · %s</li>',
            value->>'paraphrase', value->>'source_url', value->>'label', value->>'published_on'), '' order by position)
    into reviewed_links, rendered_items
    from jsonb_array_elements(links) with ordinality l(value, position);

    rendered := replace(base.html, '</body>',
        '<section id="reviewed-link-citations"><h2>Wolfsberg industry guidance</h2>' ||
        '<p>Paraphrases checked against the publisher releases on 12 November 2026. Follow each link to read the source.</p>' ||
        '<ul>' || rendered_items || '</ul></section></body>');
    captured := base.capture || jsonb_build_object(
        'request_id', new_request_id, 'parent_report_id', base_id, 'reviewed_link_citations', reviewed_links,
        'report_snapshot', base.capture->'report_snapshot' || jsonb_build_object(
            'analysis_run_id', new_request_id, 'analysis_revision_id', new_request_id));

    if not exists (select 1 from public.prepared_reports where id = revision_id) then
        insert into public.prepared_report_requests
            (id, workspace_id, actor_id, brief, source_ids, idempotency_key, status, finished_at)
        values (new_request_id, base.workspace_id, prior_request.actor_id, prior_request.brief,
            prior_request.source_ids, 'guest-template-revision:' || revision_id, 'ready', clock_timestamp());
        insert into public.prepared_report_request_scopes
            (request_id, workspace_id, scope_id, job_id, snapshot_id, previous_snapshot_id, choice_by, choice_at)
        select new_request_id, s.workspace_id, s.scope_id, s.job_id, s.snapshot_id, s.previous_snapshot_id, s.choice_by, s.choice_at
        from public.prepared_report_request_scopes s where s.request_id = prior_request.id;
        insert into public.prepared_reports (id, workspace_id, request_id, capture, html, content_sha256, review_state)
        values (revision_id, base.workspace_id, new_request_id, captured, rendered,
            encode(sha256(convert_to(rendered, 'UTF8')), 'hex'), base.review_state);
        insert into public.prepared_report_bindings
            (report_id, workspace_id, snapshot_id, finding_id, review_id, review_sequence, decision)
        select revision_id, workspace_id, snapshot_id, finding_id, review_id, review_sequence, decision
        from public.prepared_report_bindings where report_id = base_id;
    end if;

    if not exists (select 1 from public.prepared_reports r where r.id = revision_id
        and r.html = rendered and r.capture = captured and r.review_state = base.review_state
        and r.content_sha256 = encode(sha256(convert_to(rendered, 'UTF8')), 'hex'))
        or not private.guest_template_allowed(base.workspace_id, revision_id)
        or (select count(*) from public.prepared_report_bindings where report_id = revision_id) <> 139
        or exists ((select snapshot_id, finding_id, review_id, review_sequence, decision
            from public.prepared_report_bindings where report_id = base_id)
            except (select snapshot_id, finding_id, review_id, review_sequence, decision
            from public.prepared_report_bindings where report_id = revision_id)) then
        raise exception 'The revision does not preserve the previous report and exact findings';
    end if;

    update private.guest_demo_portals set report_ids = array_replace(report_ids, base_id, revision_id)
    where key_hash = portal.key_hash;
end $revise$;

-- Verify the real anonymous generate and download RPCs. The savepoint removes
-- the temporary window, request, and guest copy before activating the revision.
savepoint verify_download;
do $open$
declare
    actor uuid;
    opened jsonb;
    link text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
    receipt text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
begin
    select q.actor_id into strict actor from public.prepared_report_requests q
    where q.id = '58be66a0-b4be-4400-8c4d-a1b26da91448';
    perform set_config('request.jwt.claim.sub', actor::text, true);
    perform set_config('request.jwt.claims', jsonb_build_object('sub', actor, 'role', 'authenticated')::text, true);
    perform set_config('mira.test_link', link, true);
    perform set_config('mira.test_receipt', receipt, true);
    opened := public.open_guest_demo('291353ea-179f-4e7c-89e4-5cd58de83419', link, 5);
    perform set_config('mira.test_window', opened->>'id', true);
end $open$;

set local role anon;
do $download$
declare
    made jsonb := public.guest_demo_generate(current_setting('mira.test_link'), current_setting('mira.test_receipt'));
    downloaded jsonb := public.guest_demo_result(current_setting('mira.test_link'), current_setting('mira.test_receipt'), true);
begin
    if made->>'status' is distinct from 'ready' or downloaded->>'html' is null
        or made->>'html' is distinct from downloaded->>'html' then
        raise exception 'Guest download did not return the generated HTML';
    end if;
    perform set_config('mira.download_hash', encode(sha256(convert_to(downloaded->>'html', 'UTF8')), 'hex'), true);
end $download$;
reset role;

do $verify$
declare
    template public.prepared_reports%rowtype;
    guest public.prepared_reports%rowtype;
begin
    select * into strict template from public.prepared_reports where id = '291353ea-179f-4e7c-89e4-5cd58de83419';
    select r.* into strict guest from public.prepared_reports r
    join private.guest_demo_requests g on g.request_id = r.request_id
    where g.window_id = current_setting('mira.test_window')::uuid;
    if guest.capture->>'guest_template_report_id' is distinct from template.id::text
        or guest.capture->'reviewed_link_citations' is distinct from template.capture->'reviewed_link_citations'
        or guest.content_sha256 is distinct from current_setting('mira.download_hash')
        or guest.review_state is distinct from template.review_state
        or exists (select 1 from jsonb_array_elements(guest.capture->'reviewed_link_citations') l(value)
            where strpos(guest.html, 'href="' || (value->>'source_url') || '"') = 0
               or strpos(guest.html, '<p>' || (value->>'paraphrase') || '</p>') = 0)
        or (select count(*) from public.prepared_report_bindings where report_id = guest.id) <> 139
        or exists ((select snapshot_id, finding_id, review_id, review_sequence, decision
            from public.prepared_report_bindings where report_id = template.id)
            except (select snapshot_id, finding_id, review_id, review_sequence, decision
            from public.prepared_report_bindings where report_id = guest.id)) then
        raise exception 'Guest download lost citations or saved finding and review bindings';
    end if;
end $verify$;
rollback to savepoint verify_download;
commit;

-- Audit the persisted revision, including citation URLs taken from its actual
-- saved finding bindings and reviewed link records.
with revision as (
    select r.* from public.prepared_reports r join private.guest_demo_portals p on r.id = any(p.report_ids)
    where r.id = '291353ea-179f-4e7c-89e4-5cd58de83419'
), citation_urls as (
    select p.value->>'source_url' as url from revision r
    join public.prepared_report_bindings b on b.report_id = r.id
    cross join lateral jsonb_array_elements(r.capture->'selected_findings'->b.finding_id::text->'evidence') e(value)
    cross join lateral (select r.capture->'snapshots'->b.snapshot_id::text->'verifications'->b.finding_id::text
        ->'input_snapshot'->'passages'->(e.value->>'passage_id') as value) p
    union all
    select l.value->>'source_url' from revision r
    cross join lateral jsonb_array_elements(r.capture->'reviewed_link_citations') l(value)
    where l.value->'review'->>'decision' = 'accepted'
)
select r.id as hosted_template, r.content_sha256,
    (select count(*) from public.prepared_report_bindings where report_id = r.id) as historical_bindings,
    jsonb_array_length(r.capture->'reviewed_link_citations') as reviewed_link_citations,
    (select count(url) from citation_urls) as citation_rows,
    (select encode(sha256(convert_to(string_agg(url, E'\n' order by url collate "C"), 'UTF8')), 'hex')
        from citation_urls) as citation_url_digest,
    (select count(*) from public.sources s join public.documents d on d.source_id = s.id
        join public.document_versions v on v.document_id = d.id
        where s.workspace_id = r.workspace_id and s.source_key = 'wolfsberg') as wolfsberg_versions,
    (select count(*) from private.guest_demo_portals p join private.guest_demo_windows w on w.id = any(p.window_ids)
        where r.id = any(p.report_ids) and w.closed_at is null and w.expires_at > clock_timestamp()) as open_portal_windows
from revision r;
