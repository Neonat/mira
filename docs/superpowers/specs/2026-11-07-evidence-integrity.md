# Evidence integrity: approved implementation scope

User approved implementation of frozen evidence snapshots, fail-closed reviewed rendering and version-aware retrieval. Base `ad79028`. No ingestion expansion, corroboration, raw-capture storage, durable report storage or paid/live research is included.

## Chosen approach

Use a self-contained typed JSON bundle rather than only a list of live IDs. Existing review-outcome freezing remains. New worker-written claim checks carry their actual in-memory verification input, and server-written review rows capture their current input. Sign-off compares those identities to a single server capture, then freezes that capture. Caller-provided evidence bundles are never trusted.

Legacy reviewed files remain unchanged. Legacy reviewed snapshots without a bundle refuse regeneration; they are not backfilled from current links. Old verification/review inputs without bindings require fresh checking/review before new sign-off.

## Shared JSON contract

`ReportSnapshot.evidence_bundle: FrozenEvidenceBundle | None = None`; contract version advances to1.4. Absence permits reading old drafts but never reviewed regeneration.

`EvidenceInput` contains `schema_version:1`, `workspace_id`, `analysis_run_id`, `analysis_revision_id`, `findings: dict[UUID,FrozenFinding]`, `passages: dict[UUID,FrozenPassage]`.

`FrozenFinding` fields: `finding_id`, `finding_type`, `title`, `content`, `priority`, `evidence_confidence`, `priority_reason`, `jurisdiction_code`, `change_type`, `industry_category`, `is_inference`, `evidence_confidence_reason`, `key_date`, `key_date_kind`, `depends_on:list[UUID]`, `evidence:list[FrozenCitation]`. Nullable metadata matches ClaimDraft. No temporary claim/passage labels are stored.

`FrozenCitation`: `passage_id`, `document_version_id`, `supporting_quote`, `support_type` (supports/contradicts/context). Actual current verifier input includes supporting links only; unseen additional link types must mismatch rather than be silently certified.

`FrozenPassage`: all PassageRecord fields (`id`, `document_version_id`, `document_id`, `source_id`, `source_name`, `jurisdiction_code`, `title`, `source_url`, `published_at`, `passage_number`, `content`, `imported`) plus `content_sha256` (original capture hash), `extraction_version`, `page_number`, `char_start`, `char_end`. New PassageRecord provenance fields default null for compatibility; PostgreSQL retrieval populates actual values. Unknown provenance stays explicit, without invented hashes or extraction versions.

`FrozenEvidenceBundle` extends EvidenceInput with `brief:Brief`, `expected_sources:dict[UUID,FrozenExpectedSource]`, `reviewer_display_name:str`, `reviewed_at:datetime`, and required `verifications:dict[UUID,FrozenVerification]`. FrozenVerification retains check ID, method, verdict, reason, model, prompt version, checked-at time, input fingerprint, attempt and agent-step ID. FrozenExpectedSource mirrors ExpectedSourceRecord. Coverage and reviewer outcomes stay in ReportSnapshot.

Canonical identity is JSONB equality, with SHA-256 of JSONB text available as a diagnostic fingerprint. Finding/dependency/evidence arrays sort by UUID, passage ID, quote/type to make order irrelevant. Include the full recursive dependency closure and all required passage metadata. Missing closure entries are errors, never filtered silently.

Distinct quotes from one passage are preserved; identical passage/quote pairs deduplicate. Database link uniqueness uses the fixed-size `extensions.digest(supporting_quote, 'sha256')`, with the full quotation retained as text, avoiding B-tree limits on long quotes.

## Trusted capture and sign-off

- `build_verification_input(ctx, claim, claims, passages) -> EvidenceInput` builds the exact actual in-memory claim/dependency/passage input before calling the verifier. `RunStore.save_checks(..., input_snapshot:dict|None=None)` stores that same payload on every check from the call. The existing worker-only claim_checks table is the trusted authority; app users cannot forge it.
- New `claim_checks.input_snapshot jsonb` and `finding_reviews.input_snapshot jsonb` are nullable for historical rows. Review BEFORE INSERT always replaces caller input with the server's capture for that finding. No backfill.
- A SQL STABLE capture function scopes all data by workspace, run and revision and builds recursive findings/passages in one statement snapshot. At sign-off, use one captured body throughout: per-finding dependency subsets derived from it are compared to the latest supported LLM/inference check and latest reviewer input, with review ordering rules preserved. Missing/bad/outdated inputs block.
- Sign-off runs existing outcome/amendment/exclusion checks first, then freezes retained roots and their full closure from the server capture, not supplied JSON. Validate snapshot identity against the report row. Freeze brief, coverage labels and reviewer display name too.
- Eligible semantic checks must predate or equal sign-off time. Every retained recursive supporting finding needs an accepted/amended bound review. Excluded findings do not require unnecessary ancestor reviews; directly cited roots still require a decision under the existing gate.
- New reviewed rows cannot later replace snapshot/identity/reviewer/template fields. Artifact-path completion remains supported. Privileged database administrators remain outside the app security boundary.

## Reviewed render

Consume only evidence_bundle and stored report metadata. Do not reload current finding evidence, dependencies, sources, expected labels, brief or reviewer email. Validate recursive closure, passage presence/version relationships, fact support, quote consistency, review outcomes and coverage labels before any artifact write. A valid frozen bundle remains renderable if live evidence links later change or become unavailable. Corrupt/incomplete bundles fail closed and leave pending report paths null.

## Retrieval

Select latest eligible saved version per document before FTS ranking/limit. Eligible publication date is unknown or at/before as_of; a future latest version must not hide an eligible older version. Apply the same choice to visits/shared reuse/manual/stored/search passages. Capture time is not a historical-page guarantee; the policy is current saved evidence about a dated publication scope.

## Acceptance

Tests cover late evidence/dependency additions, changes between verification/review/sign-off, caller bundle forgery, cross-workspace/run JSON, missing passage/dependency/version, quote mismatch, frozen citation/label independence after sign-off, legacy refusal, future latest fallback, same-date old/new versions, and limits applied after eligibility. Use isolated local fixtures, no historical rewrites/reset. Apply only the new local migration, run narrow tests during implementation and one complete tests+eval suite after integration. No paid calls or remote deployment.
