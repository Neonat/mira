# Private storage and recovery

Audience: developers and trusted operators. These commands handle complete database/evidence copies; they are separate from research and never call a model or Exa. MAS remains inactive and source grants/role models are unchanged.

## Private artifact storage

Apply migration `20261108130000_mira_private_artifacts.sql` to the intended environment through the team's migration process. Local tests apply it only to the isolated local stack. It creates a reserved **private** `mira-evidence-private` bucket, worker-written report references and restrictive Storage policies, following [Supabase access controls](https://supabase.com/docs/guides/storage/security/access-control). App-role policies cannot make the reserved bucket public. Object reads require workspace membership; original-file reads additionally require the current active source's retention grant and reference.

Set `MIRA_ARTIFACT_STORAGE=supabase` on the worker and configure `SUPABASE_URL` plus `MIRA_STORAGE_SERVICE_ROLE_KEY` securely. An anon/publishable key is for the signed-in app and cannot replace the worker credential. Never give the service key to Streamlit, browser code, reports or Git. Keep `local` until worker credentials and the target bucket are ready. Retaining originals still independently requires `MIRA_RETAIN_ORIGINALS=1` and an explicit source approval; this integration supplies no grants. Rendered browser DOM remains a capture rather than a publisher original.

New uploads use immutable workspace/purpose/SHA-256 keys. Byte count and digest are checked on readback before publication is marked ready. A failed upload keeps the full saved snapshot and local HTML; worker polls retry a bounded batch. A content mismatch cannot replace a pinned report. Missing old local files advance retry scheduling so they cannot starve later valid reports. App readers prefer verified private report copies and can read them after local-file loss; a missing/corrupt published copy fails closed.

The optional backend does not backfill or rewrite historical reviewed snapshots. Legacy local identities and HTML remain readable. Backups preserve exact old report paths and bytes. A report with no rendered artifact remains represented by its complete snapshot and pending render state in the database.

## Create and verify a complete backup

Use PostgreSQL17-compatible `pg_dump` and `pg_restore`, configured through the trusted operator's PATH. Commands run from the repository root with ignored `.env` loaded. The source worker connection must be able to export a snapshot and dump the full database. Roles/extensions must already exist on a recovery cluster.

```sh
.venv/bin/python -m mira backup create backups/mira-2026-11-08
.venv/bin/python -m mira backup verify backups/mira-2026-11-08
```

Creation exports one repeatable-read, read-only database snapshot and inventories external bytes from that same snapshot. The archive contains the complete native database dump, an identity manifest, referenced originals/report bytes, and a manifest-integrity marker. Facts, full passages, versions, verification bindings, coverage, review decisions, permissions and audit records remain in the database dump. It does not include `.env` or provider credentials. The database itself can contain authentication records and other sensitive application data; package directories/files are0700/0600 and should stay in controlled backup storage.

Every referenced saved file must be available and match its binding. Missing/corrupt files or incomplete packages prevent a successful complete backup; they are not silently omitted. Checksum verification detects corruption but does not authenticate who created an archive. Keep the package exclusively owned throughout verification and restore. Copy the verified package to the team's independently managed backup storage and apply its retention/encryption policy; the CLI is on demand and does not claim a configured backup schedule, remote deployment or recovery-time guarantee.

For the existing local test database container, the explicit transport option uses its installed native tools without putting database credentials in command arguments:

```sh
.venv/bin/python -m mira backup create backups/local-drill --postgres-container supabase_db_mira-dbsearch
```

That wrapper must address the same local cluster as `MIRA_WORKER_DATABASE_URL`. It does not reset the database or start a research worker.

## Restore only into a fresh local recovery database

Create a separate, empty local database named `mira_recovery_<32 lowercase hexadecimal characters>` using the local database administrator. The tool does not create, drop, clean, overwrite or migrate a shared/source database. The target must have no user objects, extensions beyond `plpgsql`, or other sessions. Source-name equality and non-loopback targets are refused.

```sh
.venv/bin/python -m mira backup restore backups/mira-2026-11-08 \
  --database mira_recovery_0123456789abcdef0123456789abcdef \
  --trusted-backup \
  --originals-dir /private/tmp/mira-recovered-originals \
  --reports-dir /private/tmp/mira-recovered-reports
```

Use `--trusted-backup` **only for a trusted operator-created archive**: native restore executes the archive's SQL with the target database role's privileges, as described in the [PostgreSQL restore documentation](https://www.postgresql.org/docs/17/app-pgrestore.html). Do not use it for untrusted downloaded packages. All package members are verified before restore writes. Objects are restored immutably before the database transaction is published. Exact existing bytes are accepted; differing existing objects are never overwritten. Failed object restoration leaves the database unpublished, though completed immutable object copies can remain. External object storage and PostgreSQL are not one transaction.

After recovery, verify the restored full passages, object digests, HTML, frozen review identities, access policies and application reads before directing an app/worker to the recovered environment. Promotion to a deployed environment is a separate operator action. Tests use disposable synthetic databases and verify A/B/C retention, concurrent snapshot exclusion, exact HTML/original restoration, access controls and refusal of corrupt or unsafe targets. They establish the exercised recovery mechanism, not a hosted-provider restore drill or a measured RPO/RTO.
