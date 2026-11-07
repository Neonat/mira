# Auditor report navigation and layout

**Objective:** Implement approved linked contents, numbered paragraphs, fully justified narrative, overview counts, chronological timeline, and labelled coverage.

**Base:** `ad79028f650cc4e8632fc94344c72e0ed332a47a`, shared branch `codex/nat-ingestion`.

**Owned:** `mira/report.py`, new `tests/test_report_navigation.py`, `docs/superpowers/plans/2026-11-07-report-navigation.md`, this handoff. Ignored updated report artifact only. All ingestion/evidence-integrity/runtime shared files and existing modified tests are read-only; no branch switch, commit, push, migrations, or API calls.

**Changes:** Template `report/4`: linked contents and section anchors; section.paragraph links alongside existing finding/evidence anchors; fully justified narrative for screen/print at every viewport, no alignment toggle; unique report finding/source counts; chronological saved key-date timeline with links to original finding text and publishers; labelled coverage badges. Original finding numbering retained independently of paragraph references. Dated standalone/reworded timeline entries are sorted and retain full prose; undated entries remain verbatim.

**Artifact:** `reports/30704efb-5ebe-42b4-a48e-e396d54bc959/report-v1-layout.html`; original `report-v1.html` remains unchanged. Rendered from saved draft snapshot and database evidence; original unresolved reasons copied verbatim. Checked preservation of all 13 finding paragraphs and 11 original external source URLs. 89 unique anchors / 125 resolved internal links. Local regeneration script `/tmp/mira-render-layout.py`; no model calls or report-row mutations.

**Checks:** Four navigation/overview/timeline regressions failed for absent features before implementation. Focused report checks: **29 passed**. Full offline suite once: **282 passed, 66 skipped, 8 subtests passed, 1 failed**. Failure: `tests/test_research_coverage.py::test_passage_selection_covers_distinct_publications_before_more_pages`, in concurrent ingestion work, unrelated to report rendering. Database tests skipped because `MIRA_TEST_DATABASE_URL` was not set. Do not claim a green integrated suite. Diff whitespace check clean.

**Visual limitation:** CUA policy denied opening local `file://` reports. No workaround attempted; desktop/mobile/print appearance has not been visually verified. HTML structure and links checked automatically.

**Review:** Read-only reviewer identified timeline ordering for standalone/reworded dated entries; corrected with a failing-then-passing regression. Follow-up found missing finding numbers/justification for those rows; both corrected using the existing numbered article renderer and explicit regression assertions. Final focused checks 29 passed. Ingestion owner should address its coverage test failure before the coordinator's next integrated database suite.

**Status:** Complete. Deliver layout artifact; visual QA remains unverified as disclosed.

**Push validation:** Validated an isolated archive of base HEAD plus only the four report-owned files: **253 passed, 44 skipped, 8 subtests passed** (5.21 s). No ingestion changes included; database tests intentionally offline. This separates the report commit from concurrent working-tree failures.
