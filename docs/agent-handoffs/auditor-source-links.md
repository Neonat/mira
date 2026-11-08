# Readable publication links for auditors

Objective: merge PR7 with current main first, preserving PR6/PR8, then fix report links that open raw SFC JSON.

Base SHA: `33b6be6c6f39586a957d6982f657d87c1a4c7785` (PR7 merge, 8 November 2026 at 17:39:22 SGT). Follow-up branch: `codex/auditor-source-links`.

Owned: `mira/source_links.py`, `mira/report.py`, `mira/corroboration_display.py`, `tests/test_report_source_links.py`, this handoff and coordinator README/checkpoint. Read-only: acquisition/runtime, database schema/rows, source grants, model settings, saved/frozen evidence, historical signed reports and slide binaries. No paid research or remote migration.

## Merge completed first

PR7 incorporated main `ff3a70f` after documentation-only conflicts in the handoff README, checkpoint JSON and PRD. Preserved PR8 historical precision/provenance caveats and original slide blobs, PR6 guardrails and the newer implemented phases/run evidence. Included requested table-spacing fix `42f08a4`. The merged tree passed **538 tests + 8 subtests, none skipped, 53.81s**. PR7's tested head `28af483` was merged using an expected-head guard; GitHub confirms merge commit `33b6be6`. The connected GitHub integration lacked mutation permission (403), so the existing authenticated CLI performed the authorized operation.

## Source-link behavior

The screenshot was an SFC `/edistributionWeb/api/.../content` response. Its `html` field was being shown as JSON because report links used the acquisition destination. The new display-only helper maps verified English circular/news content endpoints to the same reference's official reader page:

- [Circular 26EC69](https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC69)
- [Circular 26EC2](https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC2)
- [Circular 26EC39](https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC39)
- [News 26PR19](https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR19)

All four rendered the expected readable publication in the browser, with their corresponding titles and dates. Web text extraction alone returned JavaScript placeholders or an unavailable response; actual browser state supplied the verification. These were bounded read-only page checks, not a new research/model run or storage-permission expansion.

Mapping requires the exact HTTPS authority, a recognized content endpoint, one `refNo`, one `lang=EN` and a matching reference prefix. Unknown languages/endpoints, duplicate or additional parameters, spoofed authorities, PDF links and search indexes stay unchanged. No arbitrary `publicUrl` from a source response is trusted. Fragment identifiers are retained, links remain escaped, and their bare-URL labels match the new destination.

The projection is used in draft/reviewed reports, inline citations, the evidence appendix, corroboration candidates and origin evidence. Review-screen corroboration already uses the same renderer. Original acquisition URLs, hashes, quotes, facts, assessment envelopes, frozen bundles and verification fingerprints are unchanged. Template version is `report/6`; historical report files are not rewritten.

The user's current **draft** `reports/7be59cdf-8dc7-4c5f-ae22-1c3db4c10b82/report-v1.html` was explicitly updated: **24 anchors across four publications**, zero remaining API-content anchors. Reversing just those destinations/bare-URL labels exactly recovers the original HTML; all other content is unchanged. An ignored backup is beside it at `report-v1-before-source-links.html`. No report-row mutation or new report/research generation. Local-file browser preview remains blocked by Browser Use URL policy; no workaround was attempted.

## Tests and review

Nine regressions failed first at the expected missing reader destinations, while thirteen preservation/boundary cases already passed. Draft and frozen reviewed render tests prove the saved URLs/snapshots remain unchanged; corroboration/origin tests preserve the assessment and quotes. Focused report suite: **52 passed**. Independent read-only reviewer found no actionable issues.

Final command: `PYTHONPATH=/private/tmp/mira-browser-deps:. MIRA_BROWSER_EXECUTABLE=<existing Chromium> MIRA_TEST_DATABASE_URL=<local PostgreSQL> PYTHONDONTWRITEBYTECODE=1 /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests eval -q -p no:cacheprovider --basetemp=/private/tmp/mira-auditor-source-links-final --tb=short` → **560 passed + 8 subtests, none skipped, 54.55 seconds**. JSON, whitespace, credential and change-scope checks accompany publication.

Open risks: external publisher availability can change; unverified endpoint/language mappings are intentionally not invented. This does not provide an archived original, change independent-source judgements, recover missed facts or resolve the earlier bounded-run acceptance limits. MAS remains disabled.

Exact next step at this checkpoint: publish this separately reviewed link fix and share its PR and the updated local draft. PR7 is merged; do not automatically merge the new follow-up or deploy remotely. Status: implementation, review and verification complete.
