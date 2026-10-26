# Mira engineering guide

## What we are building

Mira is a focused audit-research tool. It collects approved news and regulator publications into a versioned evidence archive, groups source evidence into incidents, connects reviewed incidents to audit projects, and saves cited analysis and report versions for human review.

The archive is the product’s source of truth. Search indexes and embeddings are derived from saved passages and can be rebuilt. Mira searches the collection the team has ingested; it is not an internet-wide crawler or an Exa replacement. Fetching source pages uses the team’s own connectors and normal web/RSS access, subject to each publisher’s terms.

## Recommended first stack

Keep the first release small and in-house:

| Part | Starting choice | Purpose |
|---|---|---|
| Shared database and sign-in | Supabase Postgres 17, Supabase Auth, `pgvector` | Shared records, access rules, English full-text search and vector storage |
| App and ingestion | Python 3; one small Streamlit app for the first UI; `supabase-py` for authenticated database access | Source ingestion, curation screens and the first end-to-end workflow |
| Embeddings | Local `sentence-transformers/all-MiniLM-L6-v2` | Produces the 384-value vectors expected by the current schema; model name and revision must be saved with each row |
| Report output | HTML and JSON rendered from saved analysis revisions | Reproducible report exports; exporting must not rerun analysis |

These are implementation recommendations, not enforced by SQL. Keep model and library choices replaceable. Do not add an external web-search or embedding API for the first release. An optional local language model can help draft summaries, but every material claim still needs saved evidence and human review.

## How the data moves

```text
approved sources
  → ingestion run and run items
  → document → immutable document version → passages → search indexes/embeddings
  → incident revision + exact evidence links + curator review
  → project revision + reviewed incident links
  → regulation version + cited provisions
  → analysis run + selected evidence + findings + reviewer decisions
  → report snapshot
```

News/regulator documents and domain records are distinct. A document is not automatically an incident; an incident is not automatically relevant to a project; a suggested theme is not automatically a project; a generated finding is not an audit conclusion. Keep those decisions explicit and reviewable.

## Glossary and table map

All application records are in `public` and are workspace-scoped. `workspaces` is the boundary row itself; other domain records carry `workspace_id` directly or inherit it through a composite foreign key. The SQL migrations define the exact columns and constraints; use them rather than creating parallel tables.

| Term | Tables | Meaning |
|---|---|---|
| Workspace | `workspaces`, `workspace_members` | Mira data boundary and each user’s role in it. |
| Source and coverage | `sources`, `source_coverage`, `market_region_mappings` | Publisher/connector metadata, year-by-year completeness and configurable region-to-market mappings. |
| Ingestion | `ingestion_runs`, `ingestion_run_items` | User-requested incremental/backfill/import jobs, checkpoints, retries, idempotency and visible failures. |
| Source evidence | `documents`, `document_versions`, `document_passages`, `passage_embeddings` | Stable source identity, content-hashed snapshots, citation-sized passages and rebuildable search vectors. |
| Incident | `incidents`, `incident_revisions`, `incident_geographies`, `incident_evidence`, `incident_revision_reviews`, `incident_relationships` | A real-world event/case, dated factual revisions, market roles, supporting/contradicting/context sources, append-only review decisions, and same-event/development/related-case links. |
| Project | `projects`, `project_revisions`, `project_incidents`, `project_incident_evidence` | Audit scope snapshots and reviewed, reasoned links from that scope to exact incident revisions and evidence. |
| Suggested theme | `theme_suggestions`, `theme_suggestion_incidents`, `theme_suggestion_reviews` | Candidate grouping with its incident set and review/promotion history. Promotion must be explicit and idempotent. |
| Regulation | `regulations`, `regulation_versions`, `regulation_provisions` | Instrument identity, dated jurisdiction-specific versions, and provisions tied to the version’s source document/passages. |
| Analysis | `analysis_runs`, `analysis_evidence`, `analysis_revisions`, `analysis_findings`, `finding_evidence`, `finding_reviews` | A run pins a project revision, query mode/date and selected markets; findings distinguish external facts, requirements, applicability, risk implications and audit questions, with exact evidence and review history. |
| Report | `reports` | Versioned HTML/JSON snapshot of one saved analysis revision, including its evidence snapshot, template version and review state. |
| Audit trail | `audit_events` | Trigger-generated record IDs, action, revisions and changed field names. It deliberately does not copy row contents, source text or credentials. |

## Database contracts to preserve

- **Workspace isolation:** include `workspace_id` in every query and write. RLS is the enforcement boundary; client filters alone are not authorization.
- **Exact citations:** an evidence link must identify a document version and, when available, a passage from that same version. Regulation provisions also point to the exact regulation version and source document. Do not cite only a mutable URL.
- **Keep dates distinct:** preserve incident event dates, source publication dates, retrieval timestamps, and regulation effective dates separately. Unknown dates need an explicit reason; retrieval date is not a substitute for event/publication date.
- **Add revisions:** source versions, incident facts, project scope, regulation versions, analysis revisions, review events and reports are historical evidence. Correct them by creating a new version/revision/review event, not by silently replacing history.
- **Idempotency and recovery:** use the schema’s idempotency keys, unique source identities, content hashes and ingestion checkpoints. A retry should not duplicate a document, job, theme promotion or report version.
- **Facts versus inference:** keep source-backed external facts separate from applicability assessments and risk implications. Record uncertainty, contradictory evidence, missing internal evidence and reviewer decisions. Public external evidence cannot establish the bank’s internal control effectiveness or compliance status.
- **Coverage is data:** update `source_coverage` by source/year and surface unknown, partial, unavailable and failed ranges. Ingesting some records does not prove the historical archive is complete.
- **Rights before storage:** check publisher terms before retaining extracted text or exporting it. `document_versions.storage_path` can reference permitted archived objects; this repository does not create a storage bucket.

## Search contract

The schema provides two authenticated, invoker-rights functions. Use the parameter names exactly as written when calling them through Supabase RPC:

- `search_passages(p_workspace_id, p_query, p_limit)` — English Postgres full-text search; returns `passage_id`, `document_version_id`, `content` and `rank_score`.
- `match_passages(p_workspace_id, p_query_embedding, p_model_name, p_model_revision, p_limit)` — cosine similarity over 384-dimensional local embeddings; returns the same IDs/content plus `similarity`.

Both default to 20 rows, are capped at 100, and inherit workspace RLS. The app should call both with the same workspace, date, market and source filters, then merge/rerank the results (for example, reciprocal rank fusion). Scores from these two functions are different kinds of values; do not compare them as if they were calibrated to the same scale. Group results into incidents/regulations only after preserving the passage citation and source version. Embeddings and indexes are derived data and must be reproducible from saved text/passages.

## Roles and access

Supabase Auth identifies users; `workspace_members` grants a role: `admin`, `analyst`, `curator`, `reviewer` or `viewer`. Authenticated users can read rows in their workspace subject to RLS. The `anon` role has no access to Mira tables or search functions. Content hard-delete is not granted to app users; membership removal is admin-controlled.

| Role | Intended writes |
|---|---|
| `admin` | Workspace and membership administration; all role-gated write areas. |
| `curator` | Sources, ingestion, documents, incident facts/evidence, and theme review. |
| `analyst` | Projects, project links, regulations, themes, analysis and findings. |
| `reviewer` | Append review decisions and create/review reports where the RLS policy permits. |
| `viewer` | Read-only. |

This is enforced by both SQL grants and RLS policies. Do not use a service-role key to make client writes work: it bypasses RLS. If a trusted worker needs elevated credentials, keep them server-side, validate the actor/workspace/role before each operation, and record the initiating user and request ID.

The migration seeds one `mira` workspace, but it does not create Auth accounts or workspace memberships. For local development, create a test Auth user in local Supabase Studio and have the local database owner add that Auth user’s UUID to the seeded workspace as `admin`. After that, the admin can add teammates with the appropriate least-privilege role. The initial admin membership is an owner/bootstrap operation because a user cannot authorize their own membership under RLS.

For local bootstrap, look up the test user ID in Studio’s SQL Editor, then run the insert with the returned UUIDs:

```sql
select id, email from auth.users order by created_at;
select id as workspace_id from public.workspaces where slug = 'mira';

insert into public.workspace_members (workspace_id, user_id, role)
values ('WORKSPACE_UUID', 'AUTH_USER_UUID', 'admin')
on conflict (workspace_id, user_id) do update set role = excluded.role;
```

Replace both placeholders with the UUIDs returned by the first two queries. Run this only against the local database when following the local setup.

## Work split for three developers

| Owner | Build next | Shared contract to use |
|---|---|---|
| Nathaniel — ingestion/incidents | Curated RSS/web/PDF connectors; user-triggered runs; resumable backfills; extraction, deduplication and incident candidates; coverage and failure screens; curator correction/review. | `sources` → `ingestion_runs`/`ingestion_run_items` → `documents`/`document_versions`/`document_passages` → `incidents`/`incident_revisions`/`incident_evidence`. Preserve source dates and exact evidence. |
| Ewen — projects/regulations/analysis | Direct project creation and reviewed theme promotion; regulation ingestion/versioning; effective-date and jurisdiction filtering; evidence-backed findings, review questions and reviewer workflow. | `project_revisions`/`project_incidents`; `regulation_versions`/`regulation_provisions`; `analysis_runs`/`analysis_evidence`/`analysis_findings`/`finding_reviews`. |
| Saai — database/search/report delivery | Own migrations, shared query/transaction helpers, Auth/RLS integration, hybrid retrieval, citation serialization and immutable report snapshots. | These migrations, the two search functions, workspace policies, `reports`, and the report evidence snapshot. Coordinate any schema change with Nathaniel and Ewen before merging it. |

Agree JSON/request shapes for shared operations before each module starts writing production code. For operations that create several related rows, use a database transaction/RPC or trusted transaction-capable backend; a series of independent REST calls can leave partial records if one step fails. Start with one source and one end-to-end workflow before broad historical backfills.

## Local development and migrations

1. Clone this repo, install the Supabase CLI and Docker, and run `supabase start`.
2. Use `supabase status` for local URLs and local development keys. Keep them in an ignored `.env` file; never commit real values.
3. Create a local Auth test user and bootstrap it into the seeded workspace as described above.
4. Make schema changes in a new ordered SQL migration: `supabase migration new short_change_name`. Do not edit already-applied migrations to change shared state.
5. Recreate and inspect the local database with `supabase db reset`. If a future TypeScript client is added, generate its types from the local schema rather than maintaining duplicate table definitions by hand.
6. Commit the migration with the code that needs it. Only the designated database owner should apply migrations to the shared remote; inspect the linked project and dry-run output first.

The checked-in migrations are already recorded as applied on the team’s shared Supabase project as of 12 October 2026. Other developers should work against local Supabase or follow the database owner’s access/setup instructions; do not relink this repository to a guessed project.

## Current boundaries

- Current full-text search is English-only; vectors are 384-dimensional. Any model/dimension change needs a migration and re-embedding plan.
- There is no combined hybrid-search RPC, source connector, extraction pipeline, embedding worker, analysis model, frontend, file bucket, or report renderer in this repo yet.
- The initial project setup has no app users or memberships and no imported news/regulation data.
- A first demo topic is not fixed by the schema. AML/CFT customer due diligence with Singapore and Hong Kong sources was proposed as a starting point; keep the final topic and markets configurable until the team agrees them.
- A populated database and citations do not by themselves make an assessment correct. Bank identity, hosting, licensing, internal-control evidence, recovery, access review and model validation need separate approval before bank production use.
- Do not claim complete 20–30 year coverage unless source/year coverage and missing archives have been measured and reported.

## References

- [Supabase Python client](https://github.com/supabase/supabase-py)
- [Streamlit](https://github.com/streamlit/streamlit)
- [Sentence Transformers](https://github.com/huggingface/sentence-transformers)
- [Supabase local development workflow](https://supabase.com/docs/guides/local-development/cli-workflows)
- [Supabase CLI configuration](https://supabase.com/docs/guides/local-development/cli/config)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase vector columns and pgvector](https://supabase.com/docs/guides/ai/vector-columns)
