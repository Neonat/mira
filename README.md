# Mira

Mira helps internal auditors research incidents and regulatory developments from a traceable, searchable evidence collection. The team stores source snapshots, incidents, project scope, regulation versions, analysis and report snapshots in Supabase Postgres. Search runs against this saved collection; Mira does not depend on Exa or a hosted search API.

## Start here

- [Engineering guide](docs/mira-engineering-guide.md): architecture, glossary, database contracts, roles, local setup and the three work areas.
- [`supabase/migrations/`](supabase/migrations/): canonical, ordered schema history.
- [`supabase/config.toml`](supabase/config.toml): local Supabase development configuration.

This repository currently contains the database foundation and build guide. It does not yet contain the application, source connectors, embedding worker, analysis workflow or report UI.

## Run the schema locally

Install the [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) and Docker, then from this repository run:

```sh
supabase start
supabase status
```

The local stack applies the checked-in migrations. To recreate the **local** database from those migrations:

```sh
supabase db reset
```

`db reset` deletes and rebuilds its target database. Use it only with the local stack here. Do not add `--linked`; that targets a remote project. The team’s shared project already has these two migration versions applied. Do not push migrations to a remote project without first confirming the selected account/project and reviewing `supabase db push --dry-run --linked` with the database owner.

Never commit database passwords, access tokens, service-role keys, or real environment files. The service-role key bypasses row-level security and must stay on trusted server processes.
