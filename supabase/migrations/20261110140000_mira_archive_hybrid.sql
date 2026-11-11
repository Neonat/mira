-- Existing immutable cache identity/actor checks remain; recheck current source
-- grants when publishing each batch, including revocation during a provider call.
create function private.validate_hybrid_source() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
 if not exists (
   select 1 from public.document_passages p
   join public.document_versions v on v.id=p.document_version_id and v.workspace_id=p.workspace_id
   join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
   join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
   where p.id=new.passage_id and p.workspace_id=new.workspace_id
   and s.is_active and s.source_key<>'mas'
   and s.permitted_operations @> array['store_text','embed']::text[]
   and ('fetch'=any(s.permitted_operations) or v.metadata->>'import'='manual')
 ) then
   raise exception 'current source embedding approval required' using errcode='42501';
 end if;
 return new;
end $$;
create trigger hybrid_vector_source_validate before insert or update on public.hybrid_passage_vectors
for each row execute function private.validate_hybrid_source();
