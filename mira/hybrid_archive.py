"""Exact archive SQL. Scope and current content are filtered before top-k."""

POOL = '''with eligible as materialized (
 select distinct on(v.document_id) v.id, ('embed'=any(s.permitted_operations)) can_embed
 from public.document_versions v
 join public.documents d on d.id=v.document_id and d.workspace_id=v.workspace_id
 join public.sources s on s.id=d.source_id and s.workspace_id=d.workspace_id
 where v.workspace_id=%(ws)s and d.source_id=any(%(sources)s) and s.is_active
 and s.source_key<>'mas' and 'store_text'=any(s.permitted_operations)
 and ('fetch'=any(s.permitted_operations) or v.metadata->>'import'='manual')
 and (((%(jurisdiction)s::text is null or %(jurisdiction)s::text='INT')
       and coalesce(trim(s.jurisdiction_code),'') in ('','INT'))
      or (%(jurisdiction)s::text is not null and %(jurisdiction)s::text<>'INT'
          and s.jurisdiction_code=%(jurisdiction)s and s.jurisdiction_code=any(%(jurisdictions)s)))
 and (v.published_at is null or v.published_at::date<=%(as_of)s)
 order by v.document_id,v.version_number desc
), pool as materialized (
 select p.id,p.content,p.search_vector,e.can_embed,
 encode(extensions.digest(convert_to(p.content,'UTF8'),'sha256'),'hex') content_sha256
 from public.document_passages p join eligible e on e.id=p.document_version_id
 where p.workspace_id=%(ws)s
) '''

CACHE = '''c.workspace_id=%(ws)s and c.passage_id=p.id and c.model=%(model)s
 and c.revision=%(revision)s and c.dimensions=%(dimensions)s
 and c.content_sha256=p.content_sha256'''

def parameters(ctx,task,identity):
    # Reuse the existing scout full-text query, not a weaker comparison arm.
    from mira.agents.scout import _terms
    words=sorted(_terms(task.question))[:12]
    return dict(ws=ctx.workspace_id,sources=list(task.source_ids),jurisdiction=task.jurisdiction_code,
                jurisdictions=list(ctx.brief.jurisdictions),as_of=ctx.brief.as_of_date,
                model=identity.model,revision=identity.revision,dimensions=identity.dimensions,
                query=' or '.join(['"money laundering"',*words]))

def counts(conn,params):
    return conn.execute(POOL+'''select count(*) eligible,
     count(*) filter(where exists(select 1 from public.hybrid_passage_vectors c where '''+CACHE+''')) indexed,
     count(*) filter(where (octet_length(p.content)>8192 or length(p.content)>%(characters)s or length(p.content)=0)
       and not exists(select 1 from public.hybrid_passage_vectors c where '''+CACHE+''')) blocked
     from pool p where p.can_embed''',params).fetchone()

def missing(conn,params):
    return conn.execute(POOL+'''select p.id,p.content,p.content_sha256 from pool p
      where p.can_embed and octet_length(p.content) between 1 and least(8192,%(capacity)s)
      and length(p.content)<=%(characters)s
      and not exists(select 1 from public.hybrid_passage_vectors c where '''+CACHE+''')
      order by p.id limit %(batch_size)s''',params).fetchall()

def search(conn,params,query_vector=None):
    lexical='''select p.id,row_number() over(order by ts_rank_cd(p.search_vector,
       websearch_to_tsquery('english'::regconfig,%(query)s)) desc,p.id) position
       from pool p where p.search_vector @@ websearch_to_tsquery('english'::regconfig,%(query)s)
       order by position limit %(candidates)s'''
    if query_vector is None:
        return conn.execute(POOL+'select id from ('+lexical+') ranked order by position limit %(limit)s',params).fetchall()
    params=dict(params,vector='['+','.join(map(str,query_vector))+']')
    return conn.execute(POOL+''', lexical as ('''+lexical+'''), semantic as (
       select p.id,row_number() over(order by c.embedding OPERATOR(extensions.<=>) %(vector)s::extensions.vector,p.id) position
       from pool p join public.hybrid_passage_vectors c on '''+CACHE+'''
       where p.can_embed order by position limit %(candidates)s
      ), combined as (
       select id,1.0/(60+position) score from lexical union all
       select id,1.0/(60+position) score from semantic
      ) select id from combined group by id order by sum(score) desc,id limit %(limit)s''',params).fetchall()
