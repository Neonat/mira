# Scheduled evidence and prepared reports — 11 November 2026

Audience: Mira maintainers, demo operators and technical reviewers. The product
workflow serves internal-audit analysts and senior reviewers.

[PR13](https://github.com/Neonat/mira/pull/13) adds background evidence
preparation and an independent worker for prepared archive reports. The
additive migration is `20261110180000_mira_prepared_evidence.sql`. See the
[operator runbook](../research-console.md) and [workflow
contract](../superpowers/specs/2026-11-10-scheduled-evidence-reporting-design.md).

- **Preparation.** Approved acquisition, retained full text, bounded analysis,
  machine verification and corroboration run before snapshot publication.
  Schedules advance their date cutoff, preserve the configured cadence after
  missed cycles and persist discovered links and acquisition dispositions.
  Completed analysis for an identical brief and model profile can be reused;
  deferred, failed and correction-requested passages can be processed again.
- **Concurrency.** The database serializes overlapping source scopes. Requests
  atomically pin the completed snapshots and any registered refreshes for
  their sources. Lease generations fence stale workers. A failed refresh does
  not silently substitute older evidence; the analyst can explicitly choose
  previous evidence. Cancelling a report does not cancel shared preparation.
- **Review.** Cumulative snapshots retain eligible older facts and their
  original checks. New drafts filter by date, source access, support and
  dependencies. The report records pending or checked status per fact and
  shows a draft warning in both HTML and the console. Later adverse decisions
  add alerts without changing original HTML. Final approval is separate;
  this prototype retains the original draft artifact alongside approval.
- **Reporting.** The worker assembles the draft from selected frozen claims,
  citations, corroboration and coverage. It needs no provider keys and can
  serve ready sources while preparation is busy. New research and BYOK are
  available in Full research.

The [local benchmark](../../eval/evidence/2026-11-10-prepared-report-benchmark.md)
used four synthetic documents in real PostgreSQL. Ready requests produced
final HTML in 0.093 seconds with review pending and 0.090 seconds after
scripted acceptance, preserving 20/20 expected facts in both cases. The timer
excludes preparation and daemon poll delay. Provider calls: zero. Neither the
benchmark nor the local browser check measures real-country coverage or human
precision.

Validation: the integrated suite on the final runtime passed 1,437 tests and
8 subtests, with one failure caused by the new scheduler fixture selecting
a source without text-storage permission. After the fixture was constrained
to eligible sources, all 44 preparation storage, runtime and report database
checks passed. No runtime code changed after the integrated run. Local Auth
and Chromium also verified queue submission, waiting without a completed
source snapshot, worker completion, and a historical pending warning in the
console and rendered HTML at desktop and mobile sizes.

The five-minute target applies after evidence is ready. A request waiting for
a refresh may take longer. Large snapshot histories, fresh country coverage
and unattended operation have not been measured at production scale. Discovery
catch-up does not automatically revisit every acquired URL for silent changes.
There is no separate prepared PDF renderer; the HTML can be printed.

MAS, Malaysia and DIFC/DFSA remain disabled; hybrid stays experimental.
Ewen's PR6 changes, provider models and source grants remain intact. The
migration was applied locally. No production schedule or paid worker was
activated, no new provider calls were made, and no remote migration, merge or
deployment was performed.
