# Scheduled evidence preparation and asynchronous reporting

Status: implemented and validated locally as of 11 November 2026. Audience:
product owner, demo team and implementers. The product serves internal-audit
analysts and senior reviewers. See the [implementation
handoff](../../agent-handoffs/scheduled-evidence-reporting.md) for validation and
deployment boundaries.

## User-selected workflow

- Collect and prepare evidence on a schedule, ahead of report requests.
- A person normally checks the prepared evidence before report generation.
- If a request arrives while ingestion is running, wait for that ingestion to
  finish. Do not read partially ingested data. The user accepts a longer wait in
  this edge case.
- If human checking has not finished when the evidence becomes available, the
  report may be generated, but must clearly identify that its evidence has not
  received the human check. It must not be presented as checked or signed off.
- Assume enterprise credentials are provisioned for scheduled Exa/AI work. A
  requesting user may use BYOK or an enterprise-provided credential, according
  to the deployment's policy. Credential provisioning is outside the demo flow.
- The normal ready-evidence demonstration targets five minutes maximum. Actual
  research jobs may run substantially longer within their configured budgets.

## Architecture

Separate the existing request pipeline into background evidence preparation and
request-time reporting. Retain source collection, full-text/passages, analysis,
verification and corroboration; move their reusable work ahead of requests.

1. A scheduled preparation job acquires approved publications incrementally,
   retains full permitted text and versions, and records discovery/extraction
   failures. It analyses eligible passages and performs machine verification and
   corroboration, recording unanalysed or unresolved evidence.
2. Publish a completed immutable evidence snapshot. This is the boundary after
   acquisition and its scheduled machine processing have completed. Evidence can
   be incomplete, but its dispositions and preparation status must be explicit.
   A snapshot initially has human review pending; a reviewer can subsequently
   record the check against that exact snapshot.
3. A report request is queued immediately. Once its requested evidence is ready,
   retrieve relevant evidence for the topic, source set, period and as-of date,
   then generate a new report bound to that exact completed snapshot.

The archive stores full documents, passages and derived facts separately. Saved
facts do not replace the underlying text. Passage dispositions preserve the
distinction between retained, analysed, machine-supported and human-checked
information. Scheduled jobs need durable discovery progress and catch-up so they
do not repeatedly process only the same first page of publications.

## Concurrency and snapshot boundary

Coordinator proposal: scope the ingestion mutex to a workspace and the evidence
being refreshed, rather than locking the entire database or every country.
Overlapping preparation jobs in the same scope serialize; unrelated scopes may
proceed independently. Use a job/lease boundary and short atomic publication,
not a database transaction held open across network or model calls.

The request's wait-versus-snapshot decision must be atomic with publication and
job registration. This prevents a race where a request starts reading while a
new ingestion job is publishing. A request that observes active preparation waits
for that job. Coordinator contract: register an atomic request manifest covering
every requested scope. It records the active logical preparation job IDs and the
completed snapshot IDs for scopes that are not refreshing. Wait for all the
registered active jobs, then bind their published snapshot IDs in that manifest.
Show each scope's freshness time rather than claiming a single synchronized
refresh. The request may then proceed even if human review is pending. A later
ingestion cycle cannot silently change that manifest or force indefinite waiting.

Coordinator recovery contract: each job attempt has a monotonically increasing
fencing generation and owner. Lease recovery invalidates the previous owner.
Job-owned state transitions, progress cursors and snapshot publication must check
the current generation/owner. Publication and the terminal transition are atomic
and idempotent. A returning expired worker cannot publish or satisfy a waiting
request; the request remains tied to the logical job and its valid publication.

Define the handoff boundary after all scheduled machine processing, rather than
after downloads alone: verification still running means the evidence is still
being prepared. Display the current phase to explain the wait.

Coordinator failure default: failed preparation must not expose partial writes
as a completed latest snapshot. Show the failure and identify any previous
completed snapshot separately; using that older snapshot requires an explicit
user choice. Cancellation of one report request does not cancel shared scheduled
preparation. Requests pin permissions-eligible, as-of-compatible versions.

## Review and report states

Preparation: queued → preparing → ready for human check → human checked.
Failure is a separate state. Completeness is a separate measurement: "checked"
does not mean every publication was found or every passage analysed.

Coordinator review contract: store append-only decisions against each exact
prepared fact/evidence version: accepted, rejected or correction requested;
absence of a decision means pending. Rejected or correction-requested items are
excluded from new reports, including pending-review drafts. Corrections create
new versions and require machine checks and a new human decision. The snapshot
shows pending/accepted/rejected/correction counts. A report's "checked evidence"
label requires current acceptance for every included item; mixed/pending items
require the pending-review label. Snapshot human review can finish with rejected
items excluded; finishing the check does not certify completeness.

Report: queued → waiting for evidence, when necessary → generating → draft ready.
Show the human review state of the pinned evidence snapshot alongside the report
state. New inference or factual wording created for a specific request still
requires machine grounding; reusing checked evidence does not approve new claims.

Human evidence checking and final report approval are distinct. In particular:

- Human review pending does not mean machine checks were skipped. Only claims
  that meet the existing machine-support policy may be included.
- Mixed review states must not collapse into a blanket "checked" badge. Expose
  the pending portions and their supporting citations.
- A pending-review report remains labelled with its actual captured review state.
  A later check does not silently rewrite an already generated report; a new
  revision can incorporate the later review or corrections.
- Later rejection/correction of an included item creates a separate visible alert
  against affected reports. Preserve historical bytes and captured review state,
  expose the later invalidation in the app, and offer a corrected report revision.
- Existing report review/sign-off remains the final approval mechanism. No
  unchecked report automatically becomes an approved audit conclusion.

## User-facing behavior

Normal request: "Generating from checked evidence. Sources prepared through
[time]." Show the actual covered source/date scope and coverage limitations.

Request during preparation: "Waiting for the scheduled evidence refresh to
finish." Queue without blocking the interface; show preparation progress.

Completion before human review: "Draft — human evidence review pending. This
report uses the completed refresh from [time]." Put the label on the report page
and exported report, not just a temporary notification. Identify the latest
completed human check separately if one exists.

Record and display both end-to-end elapsed time and its preparation-wait/report
generation components. The edge case may exceed five minutes; do not hide that
wait or count it as meeting the normal demo target. The report itself is newly
generated; any previously prepared evidence is identified honestly.

## Alternatives considered

- Existing request-time discovery → analysis → verification → writing: retained
  as a full research workflow, but it has not met the demonstration's latency or
  coverage needs.
- Scheduled evidence preparation with fresh reports on request: the approach
  selected in this discussion. It moves reusable work out of the user wait while
  supporting new queries and explicit evidence freshness/review states.
- Pre-generated fixed reports: could make opening a report fast, but does not
  provide fresh query-specific generation. It is not the selected design.

## Acceptance and implementation boundaries

- Prove that report requests do not trigger a full acquisition run when a suitable
  completed snapshot is available.
- Test simultaneous refresh/request arrival, two refreshes, atomic publication,
  failed refresh, lease recovery, stale-worker publication refusal, idempotent
  completion, cancellation, and independent scopes. Test multi-scope manifests
  where only some scopes refresh and another cycle starts during the wait.
- Test pending, mixed and completed human checks; preserve review labels and exact
  snapshot/citation provenance in HTML/PDF and later report revisions.
- Test rejection and correction requests before/after report generation; excluded
  facts must not leak into fresh drafts and later alerts must not rewrite history.
- Retain date, source-permission, workspace-access and unsupported-inference
  guards. Human-check status must not bypass them.
- Benchmark the ready-evidence path against substantive reference material and
  critical-fact coverage, as well as the five-minute ceiling. A fast two-fact
  report is not sufficient acceptance.
- Preparation uses the existing research pipeline through machine checks and
  stops before the writer. A separate report worker assembles HTML from frozen
  findings and their original check records. It can serve ready scopes while
  preparation is busy elsewhere. The console downloads HTML for browser print;
  there is no separate prepared-report PDF renderer.
- MAS/Malaysia/DFSA remain disabled and hybrid experimental. This document does
  not create a scheduled task, enable a worker, authorize paid validation, change
  credential persistence, or deploy a migration.

Schedule frequency, source scope and background-job budgets are deployment
settings to choose before activating unattended jobs. The design assumes the
required enterprise credentials are already available; it does not make their
setup a prerequisite for demonstrating the workflow.
