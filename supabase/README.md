# Supabase schema

The ordered SQL migrations in `migrations/` define Mira’s Postgres schema. They are the database contract shared by ingestion, project/regulation analysis, search and report code.

- `20261012220000_mira_initial_schema.sql` creates the 35 workspace-scoped tables, constraints, RLS policies, audit/timestamp triggers and full-text/vector search functions. It also creates the `mira` workspace row.
- `20261012230000_mira_harden_table_privileges.sql` removes broad API-role grants and keeps only the intended authenticated operations.
- `config.toml` targets the local Supabase stack and Postgres 17. It contains no remote project reference or credentials.

For local development, run `supabase start`; use `supabase db reset` only to rebuild the local database. See the [archived Mira engineering guide](../docs/archive/mira-engineering-guide.md) for table meanings, access rules, bootstrap steps and implementation contracts.
