create table public.hybrid_passage_vectors (
    workspace_id uuid not null,
    passage_id uuid not null,
    model text not null,
    revision text not null,
    dimensions integer not null check (dimensions = 384),
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    embedding extensions.vector(384) not null,
    created_at timestamptz not null default now(),
    primary key (workspace_id, passage_id, model, revision, dimensions, content_sha256),
    foreign key (passage_id, workspace_id) references public.document_passages(id, workspace_id) on delete cascade
);
alter table public.hybrid_passage_vectors enable row level security;
create policy hybrid_passage_vectors_member_read on public.hybrid_passage_vectors for select to authenticated
    using (private.is_workspace_member(workspace_id));
grant select on public.hybrid_passage_vectors to authenticated;
grant select, insert on public.hybrid_passage_vectors to service_role;

-- The cache is worker-written only. Every insert checks both the request actor
-- and the actual saved passage content, and records metadata without vectors.
revoke all on public.hybrid_passage_vectors from public, anon, authenticated;
grant select on public.hybrid_passage_vectors to authenticated;
create function private.validate_hybrid_vector() returns trigger
language plpgsql security definer set search_path = '' as $$
declare actual_hash text; actor uuid := auth.uid();
begin
  if current_setting('role', true) in ('anon', 'authenticated') or actor is null
     or not private.has_workspace_role(new.workspace_id, array['admin','analyst']) then
    raise exception 'worker actor required' using errcode = '42501';
  end if;
  select encode(extensions.digest(convert_to(p.content, 'UTF8'), 'sha256'), 'hex')
    into actual_hash from public.document_passages p
    where p.id = new.passage_id and p.workspace_id = new.workspace_id;
  if actual_hash is null or actual_hash <> new.content_sha256 then
    raise exception 'passage content hash mismatch';
  end if;
  return new;
end $$;
create trigger hybrid_vector_validate before insert or update on public.hybrid_passage_vectors
for each row execute function private.validate_hybrid_vector();
create function private.audit_hybrid_vector() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.audit_events(workspace_id, entity_type, entity_id, action, details, actor_id)
  values (new.workspace_id, 'hybrid_passage_vectors', new.passage_id, 'insert',
          jsonb_build_object('model',new.model,'revision',new.revision,'content_sha256',new.content_sha256), auth.uid());
  return new;
end $$;
create trigger hybrid_vector_audit after insert on public.hybrid_passage_vectors
for each row execute function private.audit_hybrid_vector();
