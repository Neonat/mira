# Private object adapter handoff

Objective: implement the bounded, immutable private Supabase object adapter without integrating shared orchestration, database policy, or local originals.

Base SHA: `6e30570`; assigned branch `codex/durable-evidence-recovery`.

Owned files: `mira/private_objects.py`, `tests/test_private_objects.py`, this handoff. Read-only: `AGENTS.md`, `docs/agent-handoffs/README.md`, `docs/superpowers/specs/2026-11-08-durable-evidence-design.md`, installed SDK source. No shared file edits, credentials, real provider calls, database access, commits or pushes.

Sources/commands:

- Coordinator supplied official Supabase access-control, Python upload and download references. No external network used in this task.
- Inspected the installed `storage3` download implementation, bucket proxy, request implementation, bucket lookup and `StorageApiError` implementation. `download()` eagerly returns `response.content`, so it cannot satisfy the bounded-read requirement.
- `/Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_private_objects.py -q`

Changes:

- Frozen `ObjectIdentity` validates canonical UUIDs, purpose, lowercase SHA-256, nonnegative integer size, MIME type and the reserved backend/bucket. `to_dict()` emits JSON-compatible UUID strings and exactly seven identity fields. `object_key` is a derived property `<workspace>/<purpose>/<sha256>.bin`; no path or URL enters the identity.
- `PrivateObjectStore(client, bucket='mira-evidence-private', max_bytes=20_000_000)` uses the supplied SDK client. `put(ws, purpose, body, media_type)` checks private bucket metadata once per instance, uploads with `upsert='false'`, and always performs a complete digest/size verification before returning an identity. Duplicate conflicts (409, or 400 with SDK Duplicate/ResourceAlreadyExists code) are accepted only after the same verification. Other errors fail closed.
- `read(ws, identity)` validates every identity field, workspace binding and declared size before transport, without requiring bucket-admin metadata. It streams the authenticated SDK object endpoint, disables redirects and compression, validates Content-Length when supplied, rejects excess bytes before retaining them, and verifies exact size/SHA-256. Public/signed URLs, update/delete and identity fallback are absent.
- The streaming boundary uses storage3 bucket proxy `_base_url`, `_headers`, `_client`. Tests exercise actual `storage3==2.33.0`, `supabase==2.33.0`, `httpx==0.28.1` with `httpx.MockTransport`, including SDK multipart upload, `SyncBucket` metadata and a full `supabase.create_client` with fabricated credentials. SDK shape changes fail closed and require rerunning these tests.
- HTTP phases have a 10-second timeout; the 30-second elapsed deadline is checked at every native transport chunk and completion. A final blocking HTTP phase may extend wall time by up to its phase timeout; this is not a hard process-level cancellation deadline. The accumulator never exceeds the declared size, itself bounded by `max_bytes`; one native HTTP transport chunk may arrive before overflow is rejected. HTTPX's ordinary network transport uses bounded receive chunks. No SDK eager download is used.
- Exceptions contain fixed messages and are raised outside provider exception handlers, without retained provider exception chains, bodies, headers or client reprs.

Scoped checks and results: initial test-first collection failed because the adapter module was absent; implementation then exposed fixture differences in actual SDK multipart uploads and bucket schema, which were corrected in the fixture. Deadline and duplicate-400 regressions were observed failing before their fixes. Final focused result: **36 passed in 0.22s**, no warnings or skips. The full suite is reserved for the coordinator's single integrated run.

Open risks:

- Workspace binding is not authorization. Callers must enforce current source grants; independent storage/database RLS must also enforce workspace membership and current source grants. This adapter does not create those policies.
- Upload credentials are worker-only. App readers must receive the normal signed-in Supabase client with its current user token. The adapter never provisions or switches credentials. Put fails closed when private bucket metadata cannot be confirmed; ordinary reads do not need that lookup.
- Private bucket metadata caching is instance-local; operators must prohibit changing the reserved bucket to public. SDK internals are version-coupled as described above.
- No actual remote Supabase validation, permission/RLS proof, recovery integration or durability claim follows from these offline adapter tests.

Exact next step: coordinator integrates the adapter with backend selection and immutable original/report references, implements storage RLS and source-grant enforcement, adds integration coverage, then runs the integrated suite once. No remote migration or paid validation is authorized here.

Status: complete for assigned pure adapter; shared integration remains coordinator-owned.

## Recovery byte bridge follow-up

Objective: bridge the complete native database backup to every retained original and saved report byte object, preserving existing identities and legacy HTML exactly. Same assignment base/branch; no commits or pushes.

Owned follow-up files: new `mira/recovery_storage.py`, new `tests/test_recovery_storage.py`, this appended handoff only. Read-only sources: `mira/originals.py`, `mira/private_objects.py`, `mira/recovery.py`, report publication/access modules, schema/migrations, existing local SQL fixtures. No orchestration, schema, RLS, acquisition grants, report snapshots or database paths changed.

Changes:

- `ArchiveObjects(local_originals, reports_dir, objects=None)` exposes `collect(conn)`, `read(identity)` and `write(identity, body)` as the operator recovery package callbacks.
- `collect` issues two SELECTs covering all workspaces inside the coordinator-owned consistent read-only snapshot. It normalizes missing purpose only for legacy local originals and verifies workspace/purpose/backend/size/type/digest bindings. It deduplicates originals by workspace/purpose/digest; approval-reference differences do not duplicate the blob because the complete original metadata remains in the native database dump. Conflicting immutable fields abort.
- Ready report references select the exact private remote identity and never fall back to local bytes. Pending/failed/local reports require the exact run UUID, report version and review suffix path, preserve original HTML bytes, and verify any pending publication digest. Null paths without ready references remain unrendered snapshots in the full dump. Missing, malformed or corrupt named artifacts fail closed.
- Local report identities carry only the additional `relative_path` needed to restore every original saved HTML location. Deduplication includes that path, so one package blob can restore identical HTML under several report paths. No report is regenerated and no database snapshot/path is rewritten.
- Local reads use dirfds and `O_NOFOLLOW` for every ancestor and leaf, reject nonregular/oversized files and verify digest/size. Legacy report permissions (ordinary 0644/0755) are readable for compatibility; restored files/directories use 0600/0700. Original reads retain the existing stricter original-store permission checks.
- Restoration validates all identity/body fields before creating directories. Local originals and reports use the existing private directory walker, private exclusive temporary files and atomic no-overwrite hard-link publication. Existing bytes must match exactly; corrupt files and symlinks are never replaced. This is an operator recovery path, not new acquisition: it does not synthesize source records, references or grants, and works with retention acquisition disabled.
- Private Supabase reads strip only an optional original approval reference after strict identity validation. Restore uploads must return the exact same immutable backend identity and pass readback; remote storage never silently becomes local.

Commands/results:

- Initial test-first collection failed because `mira.recovery_storage` did not exist. After implementation, a fixture incorrectly recreated the same report directory without `exist_ok`; corrected that fixture.
- `MIRA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests/test_recovery_storage.py -q`: **36 passed in 0.31s**, no skips/warnings. Includes two actual SQL fixture checks (legacy local report restoration; retained original normalization and ready remote report inventory), immutable original ABC restoration, malformed/missing/corrupt byte cases, foreign paths, root/ancestor/leaf symlinks, pending digest mismatch and a complete package callback round trip with shared HTML blobs and object-before-database publication.
- SQL fixture SELECTs wrap the unchanged production queries in a fixture-workspace filter because the shared local test database contains historical evidence. They do not rewrite, delete or scan files belonging to those historical workspaces. All fixture database work is transaction-scoped. Pure tests do not require the database; only the two explicit SQL cases require the environment DSN.
- No external network/provider call was used. The full suite remains reserved for the coordinator's integrated run.

Open risks/limits: the bridge is exclusively for full-database operator backup/recovery, with no public UI route. Coordinator must hold a consistent native PostgreSQL snapshot/dump, exclusively own the package during restoration, verify the full package before callbacks, and restrict database publication to a fresh empty local recovery target. RLS/source grants remain enforced by the integrated application/storage policies; this bridge neither proves nor changes them. Missing remote objects fail closed. Backend SDK coupling remains as documented above.

Exact next step: coordinator passes `ArchiveObjects.collect(snapshot_conn)` and `.read` to package creation, and `.write` to object restoration before the guarded native database restore. Run the integrated suite once after wiring. No remote migration or paid validation is authorized.

Status: complete for assigned recovery byte bridge; integration remains coordinator-owned.
