# Presentation feature status — 8 November 2026

**Audience:** the project team and presenters preparing the competition narrative. Judges, DBS stakeholders and pilot auditors should start with the [README](../../README.md); the product owner and technical reviewers use [PRD v3](../mira_PRD_v3_draft.md).

## Current story

Mira takes an auditor's brief through approved-source research, saved evidence, claim verification, source-independence assessment, a readable report and finding-level review/sign-off. The auditor retains ownership of DBS actions and business decisions. Lead with this implemented journey and show the evidence navigation and review decisions.

Merged delivery includes PR6 guardrails, PR7 ingestion/corroboration/browser acquisition, PR8 slides and historical evidence, and PR9 reader-facing SFC source links. Current implementation reference: `95bd1f8`.

| Capability to show | Evidence available |
|---|---|
| Scoped Exa discovery | Actual API-key transport completed 5/5 requested searches in the latest authorised Hong Kong run; metadata enters reports only after permitted saving |
| Browser acquisition | Actual Chromium navigation/JavaScript/read-only actions; the separate permitted HKMA acquisition captured 20,084 characters and 128 links in 24.91 seconds, labelled partial because optional resources were denied |
| Verification and corroboration | Primary quote/support checks plus visible source-independence outcomes, quotations, dates and origin rationale; fixture-based independent support flows into a frozen signed report |
| Auditor-readable output | Navigable report, improved table spacing, evidence appendix and browser-verified readable SFC publication destinations |
| Review and repeatability | Finding-level decisions, dependency-aware review, frozen evidence and rerun changes |

The latest research report shows primary-source-only and inconclusive corroboration outcomes. Its report wording must retain those outcomes rather than describe the findings as independently corroborated. The [dated research record](../../eval/evidence/2026-11-08-hk-authorized-followup-7be59cdf.md) distinguishes acquired publications, report citations, completed assessor calls and semantic outcomes.

## Demonstration and measurement references

The latest merged implementation passed **560 tests + 8 subtests, none skipped**, including local PostgreSQL and actual Chromium fixtures. This is engineering verification, separate from research-quality or auditor-productivity measurement. Exact checks and the four live SFC page observations are in the [source-link handoff](../agent-handoffs/auditor-source-links.md).

The delivered 7 November deck/video and PR8 slides keep their dated demonstration/evidence cut. Do not relabel an earlier recording as a fresh run of the merged prototype. No presentation binaries were modified by this documentation refresh. Use the [storytelling handoff](storytelling-production-handoff.md) and [recording handoff](../demo/launch-production-handoff.md) for those assets, and PRD v3 §7 for technical questions on measured results.

For team preparation, PRD v3 §§8–9 retains the operating/acceptance decisions. MAS stays inactive in the current validation/demo configuration. No new paid run, source permission, model setting or remote deployment is authorised by these notes.
