# Evidence integrity integration

Objective: Freeze checked/reviewed evidence, block incomplete reviewed rendering, and exclude superseded retrieval versions. Ingestion expansion and corroboration remain deferred.

Base SHA: `ad79028f650cc4e8632fc94344c72e0ed332a47a`. Separate layout commit `53b88fb` was preserved during integration.

Owned files: `mira/contracts.py`, `mira/store.py`, `mira/evidence_snapshot.py`, `mira/orchestrator.py`, `mira/pg_store.py`, `mira/render.py`, `mira/render_job.py`, `mira/agents/scout.py`, `mira/review_display.py`, `app/streamlit_app.py`; new migration `20261107180000`; corresponding evidence/render/retrieval/pipeline/worker/UI tests and coordinator documentation. Specialist assignments are recorded in frozen-render-fix.md, version-retrieval-fix.md and review-display-fix.md. The coordinator integrated shared contracts/orchestration/migration/PRD and owns publication.

Read-only: Existing historical run/report records and rendered files; separate report-layout sources; source permissions and Mira API model settings.

Changes:

- Contract 1.4 contains the complete retained recursive finding closure, exact quotations, passage text/IDs, document-version and citation/provenance metadata, brief/checklist labels, reviewer identity/time and semantic-check provenance.
- The worker stores actual pre-call verification input. The server overwrites caller-supplied reviewer inputs and sign-off bundles. Sign-off compares each retained finding's exact input against its eligible supported semantic check and reviewer input; stale/unbound/missing inputs block. Retained supporting findings also need decisions. Future-dated checks cannot enter a sign-off.
- Reviewed snapshots are immutable except artifact-path completion. Reviewed rendering and signed UI project only the frozen bundle and validate identity, dependency closure, passages/versions, support and review/check records before writing any artifact. Late live evidence and metadata changes cannot enter a signed report.
- Legacy reviewed snapshots refuse regeneration; existing rendered files remain. No guessed backfill or historical rewrite. Missing/corrupt jobs remain pending while unrelated jobs continue.
- Retrieval selects the latest saved version eligible by publication/as-of before FTS ranking/limits, consistently across visits, shared reuse, manual/stored and search results. A future latest version does not hide eligible older evidence. This is not historical archive retrieval.
- Distinct quotes from one passage persist; identical links deduplicate using a fixed-size SHA-256 quote index. Full long quotations remain unchanged in text storage.

Sources/commands and results:

- Focused red/green checks and independent source review are recorded in specialist handoffs. A 12,000-character quote reproduced the previous B-tree index-size failure; the digest-index regression passed after correction.
- Full isolated integration: `PYTHONDONTWRITEBYTECODE=1 MIRA_TEST_DATABASE_URL=<local PostgreSQL DSN> <repo>/.venv/bin/python -m pytest tests eval -q -p no:cacheprovider --basetemp=/tmp/mira-evidence-final-integration-2 --tb=short` from `/tmp/mira-evidence-integrity-validation`: **350 passed, 8 subtests passed, none skipped, 10.95s**. Initial full run exposed two fixture problems; unique synthetic email and the version-query stub were corrected, with both focused cases passing before this final suite.
- Separate layout integration on the shared branch: `pytest tests/test_report_navigation.py tests/test_render.py tests/test_evidence_integrity_db.py::test_frozen_rerender_survives_live_citation_source_label_changes_and_unavailable_retrieval ...`: **26 passed**.
- PostgreSQL at `127.0.0.1:55432`; migration `20261107180000` applied locally. Scripted providers/fake web only. No paid/live research/model calls, remote migrations or deployment. No source-permission changes.

Open risks: Original HTML/PDF capture retention and durable artifact storage/restore are still unfinished. Historical unbound checks/reviews require fresh checking/review for new sign-off; do not substitute live evidence for missing historical bundles. Human amendments remain reviewer attestations under existing D8 policy. Unknown publication dates remain unknown; latest saved content is not proof of historical webpage state. The prior video/browser rehearsal predates contract 1.4; this pass validates its review projection automatically. Live recall and human-labelled precision were not measured.

Publication: implementation `27c28fac8631c9afdb8cdef60ab6b48b526ef5a7` is pushed to https://github.com/Neonat/mira/pull/4. PR3 was already merged, so a follow-up PR was opened; the merged PR description was restored to its prior state.

Exact next step: Review PR4. Subsequent work requires a newly bounded assignment; preserve the explicit ingestion/corroboration deferral and do not repeat paid research or historical backfills.

Status: complete (implementation, independent review and local database/integration validation).
