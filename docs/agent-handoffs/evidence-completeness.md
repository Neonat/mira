# Evidence completeness implementation

Objective: user-approved passage coverage and bounded batch analysis first, then permitted-original retention/page navigation and optional hybrid retrieval; test and open a PR. Base `e4ad439` (documentation PR10), merged runtime baseline `95bd1f8`. Branch `codex/passage-coverage-retrieval`; [PR11](https://github.com/Neonat/mira/pull/11) is open on PR10. Tested implementation commit `6fc63b1`. Ewen's PR6 remains an ancestor; no role model or source grant changes.

Coordinator owns integration, shared Python contracts/stores/orchestration, provenance projection, report/review UI, documentation and push. Bounded worker ownership and scoped results are recorded in [batch planner](analysis-batch-planner.md), [coverage database](analysis-coverage-db.md), [original storage](private-originals.md) and [hybrid retrieval](hybrid-retrieval.md). These historical handoff stages are superseded by the integrated behavior below.

## Delivered behavior

- Normal worker expands all scoped acquired/reused/selected saved versions, including checklist inspection references, to complete eligible passage sets. Whole-passage batches have explicit count/character/call/output/deadline limits and a follow-up reserve. Claim labels and inference dependencies are mapped across batches. Valid empty responses count as processed; later failures preserve earlier findings.
- Append-only worker ledger, actor/step/workspace/version checks, strict terminal transitions, idempotency and serialization with review. Claim persistence and analysed dispositions commit atomically. Contract1.6 freezes canonical per-document counts and failure/defer reasons; legacy1.4/1.5 records remain unchanged. Passage analysis is distinct from checklist/publication recall and does not certify every fact was extracted.
- Private originals require global opt-in plus explicit current source approval/reference. Content-addressed immutable bytes have workspace/digest/size/permission checks; browser DOM is excluded. Storage/config failures preserve extracted text. Signed-in downloads enforce current membership/source approval and compare the signed expected identity against the identity actually read. Optional identities freeze in new provenance. Known PDF pages link directly without rewriting saved URLs.
- Optional hybrid retrieval is off by default. Eligible sources/versions are filtered before limits; manual imports retain existing nonfetchable-source behavior. Vectors bind passage content/model/revision/384 dimensions, with worker-only audited cache writes and member-read RLS. Bounded one-attempt requests use a killed/reaped subprocess, deduct DB elapsed time and preserve measured usage separately from unknown reservations and role-model billing. All fallbacks are recorded.

## Validation and reviews

No paid/live model, embedding, Exa or research acquisition was performed. Local tests use scripted providers, synthetic pages, throwaway PostgreSQL workspaces and real Chromium. The new end-to-end fixture runs scout/extraction/database/bounded analysis/verification/HTML with MAS inactive and zero MAS versions.

Independent focused reviews found and resolved: terminal state rewrites; missing frozen reason counts; malformed retention config aborting text persistence; phase timeouts instead of hard embedding deadlines; discarded known usage; and a signed-original identity race. Each received a regression. A final focused read found no remaining blocker.

Focused integrated scope: 131 passed before final race/inspection/layout additions; signed-access/UI follow-up20 passed; saved-inspection12 passed; older version/balancing fixture corrections6 passed. The first complete suite found six outdated task stubs lacking the real jurisdiction/brief fields (684passed,6failed,+8subtests); fixtures were corrected without weakening production scope checks. Complete final-candidate suite: **691 passed,8 subtests passed,no skips in92.39s**. Command: `PYTHONPATH=/private/tmp/mira-browser-deps:. MIRA_BROWSER_EXECUTABLE=<local Chromium> MIRA_TEST_DATABASE_URL=<local test PostgreSQL> PYTHONDONTWRITEBYTECODE=1 /Users/natsim/Documents/dbsearch/.venv/bin/python -m pytest tests eval -q -p no:cacheprovider --basetemp=/private/tmp/mira-completeness-final-candidate --tb=short`. No runtime/test files changed after this passing candidate; subsequent edits record documentation and PR status.

Chromium screenshots at1280px and390px verified coverage reason visibility, no page overflow and a document column wider than300px. The first mobile inspection caught an inherited narrow market-column layout; the dedicated passage table now uses full-width mobile cards. Temporary local QA files are under `/private/tmp/mira-evidence-completeness-review/`, outside Git.

New migrations20261108120000,20261108123000,20261108124000 were applied to local test PostgreSQL only. The coverage migration's two functions and manual-import helper were updated in place during local development; do not blindly reapply its non-idempotent table DDL to that already-updated local instance. Fresh environments apply the committed migrations normally. No remote migrations or historical snapshot rewrites occurred.

## Private team follow-up

- Passage processing is measured; complete fact extraction is not guaranteed. New default bounds can defer large corpora, visibly.
- Hybrid synonym fixtures demonstrate ranking mechanics only. Live recall/precision/latency gains and the earlier Hong Kong release targets remain unmeasured for this change. Above-cap eligible pools explicitly retain lexical retrieval; optional defaults do not promise semantic indexing of the entire archive.
- Private originals use local filesystem storage. Deployment needs shared durable storage, backup/restore and retention operations; existing report artifact durability remains separate work. Source approvals are not supplied by this implementation.
- No MAS automation was enabled. Its prior disabled/manual path and existing source grants are unchanged. Synthetic older MAS-labelled fixtures do not access the MAS site.
- No merge/deploy/live-validation authorization is implied. PR10 remains open; this feature PR is stacked on its documentation branch unless that is merged first.

Status: implementation complete; PR11 open, unmerged.

Exact next step: review the new PR and apply new migrations in the intended environment only under separate deployment authorization. A future paid quality comparison needs a new bounded run authorization; prior Hong Kong run allowances remain consumed.
