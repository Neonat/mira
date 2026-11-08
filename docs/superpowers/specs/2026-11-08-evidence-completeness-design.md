# Passage coverage, retained originals and hybrid retrieval

User-authorised implementation: passage coverage tracking and bounded batch analysis first; then permitted original retention/direct page navigation and a measurable hybrid-retrieval path. Open a PR when tested. MAS stays disabled. Existing role model/effort configuration stays unchanged.

## 1. Passage coverage and analysis

Keep complete permitted extracted text/passages independently of derived facts. Expand analysis candidates from the full eligible versions selected or acquired by scoped scout tasks, not just the passage labels shown to the scout. Preserve workspace/source permissions, latest publication/as-of eligibility and publication identity. Record which saved passages are candidates, attempted, successfully analysed, failed or deferred, with reasons, batch/step identity and version binding. Successful analysis means a validated response and durable claim save, including a valid empty result; it is not exhaustive fact extraction.

Partition whole passages deterministically; never silently truncate an oversized passage. Default normal-worker bounds: 12 passages/18,000 content characters per batch, at most 8 batches, 16,384 output tokens and 120 seconds per request. Run allowances always take precedence; keep 32,000 tokens and 120 seconds for verification/report work where possible. Deferred passages remain stored and visible. Exact batch/deadline/usage and unknown-usage reservations are recorded separately. Failures preserve earlier successful batches; cancellation remains respected. Labels are unique across batches, with intra-batch inference dependencies preserved. Existing single-agent comparison and direct legacy orchestration remain compatible; the normal worker explicitly enables the new analysis policy.

Persist the ledger under workspace isolation and worker-only writes. New reports capture a typed coverage summary (with document/passage counts and disposition reasons); reviewed rendering uses that frozen record, not live counters. Preserve legacy report serialization/rendering and do not invent old coverage events. Tests cover multi-fact documents, passages omitted by scout context, failure, no claims, size/call/token/time limits, independent batch labels/dependencies, cancellation and frozen sign-off.

## 2. Retained originals and readable source navigation

Add bounded private original-file retention, separate from extracted text. Require explicit global opt-in AND a source-specific retention grant/reference; existing store_text alone does not grant retention. No existing grants are expanded. Store immutable content-addressed bytes under workspace scope, verify digest/size on retrieval and prevent path traversal/symlink escape. Persist MIME/size/hash/retention provenance only after successful storage. Do not describe rendered browser DOM as a publisher's original download. Failure must not falsely mark an original retained or discard already saved text.

Provide direct PDF page references where page identity is known; maintain readable publisher destinations. Original retrieval must pass authenticated workspace/role checks, with no public bucket or worker credentials in the client/report. Existing signed artifacts and saved acquisition URLs remain unchanged. Offline fixtures exercise permission denial/revocation, corruption, cross-workspace reads and page references.

## 3. Hybrid retrieval

Keep current full-text retrieval and add an opt-in semantic branch against compatible indexed saved passages. Keyword and vector candidates are filtered by workspace, active permitted source, selected eligible version and as-of date before ranking/limits, then fused/deduplicated with deterministic provenance. Reuse Postgres/pgvector rather than changing app stack. Store explicit embedding model/revision/dimensions; do not mix incompatible vectors. New embedding configuration is separate from existing role models and off by default. Provider work is bounded, usage/reservations recorded and charged to its allowance. Errors fall back explicitly to lexical retrieval without claiming a semantic hit.

Measure the retrieval mechanism with controlled synonym/exact-term/irrelevant/conflicting-scope cases under equal candidate limits. Reuse saved evidence for any offline corpus diagnostics without injecting M0 targets into runtime. No paid/live research run is authorised by this implementation plan; any such validation needs its own bounded approval. Do not claim a live recall or precision gain from fixtures.

## Delivery and preservation

This branch starts at reviewed documentation checkpoint e4ad439 on top of main95bd1f8; PR10 remains open. Preserve those changes and publish the implementation separately (stacked against the documentation branch if still necessary). Coordinator owns shared contracts, orchestration, database migrations/integration, docs and pushes. Workers receive bounded disjoint file assignments and never recursively delegate. Use scoped red/green checks, reviews and one final complete local PostgreSQL/Chromium tests/eval suite after integration. No merge, remote migration or deployment is included.
