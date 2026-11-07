# Auditor Report Navigation Implementation Plan

> Execute inline; user approved implementation and fully justified text.

**Goal:** Make saved reports easy to navigate, reference, and scan.
**Architecture:** Presentation-only changes in `mira/report.py`; consume existing snapshots and context without changing evidence or ingestion. Keep existing finding/evidence anchors and add section/paragraph anchors.
**Tech stack:** Python HTML renderer, CSS, pytest; no dependencies or API calls.
**Spec:** User-approved proposal in this chat: linked contents, numbered paragraphs, fully justified narrative, overview counts, chronological timeline, labelled coverage.

## Constraints and ownership
- Own only `mira/report.py`, new `tests/test_report_navigation.py`, this plan, and a report-layout handoff.
- Shared checkout allowed by AGENTS; preserve the ingestion agent's uncommitted work, including existing tests/test_render.py edits. No branch switch or shared-file edits.
- Preserve original saved report; produce separate `report-v1-layout.html` from saved evidence.
- Fully justify narrative at every viewport; no alignment toggle.
- Counts describe report contents, not measured accuracy. No invented dates or priority claims.

## Review focus
- Absent/empty sections: contents links only to rendered destinations.
- Repeated findings: unique paragraph anchors and unique overview counts.
- Timeline: dated items sorted by actual saved key dates; retain date kinds and references, and undated text.
- Citations: existing finding and evidence anchors remain valid.
- Desktop, narrow screen, print: readable text, no table overflow.

## Task 1: Report layout
- [x] Add behavior tests for navigation, numbering, counts and chronological timeline.
- [x] Run scoped tests and confirm missing-feature failures.
- [x] Implement renderer changes and fully justified narrative CSS.
- [x] Run report-focused checks; review diff for evidence preservation.

## Task 2: Deliver and verify
- [x] Render a separate layout copy of the completed HK run using saved records only.
- [ ] Visual desktop/mobile preview blocked by CUA file:// policy; all 125 section/paragraph/evidence links verified automatically.
- [x] Run full offline suite once after integration; report skips/failures.
- [x] Record handoff and deliver report link.

Verification ledger: focused checks 29 passed. Full offline suite: 282 passed, 66 skipped, 8 subtests passed, one concurrent ingestion failure (see handoff). Original draft and evidence preserved; no research rerun. Focused review findings addressed with regression checks; see report-layout handoff.
