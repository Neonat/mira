# Configured hybrid retrieval: controlled live integration validation

The user requested configuring an embedding model, enabling hybrid vector retrieval, testing it and updating PR13 while keeping MAS disabled. The existing hybrid implementation at source `39a5fae` was used without changing retrieval algorithms, source grants or agent role models. [Portable metadata](2026-11-10-hybrid-embedding-validation.json) records request counts, usage, fixture controls and evidence hashes.

The two existing local development environment files now enable `text-embedding-3-small`, 384 dimensions and cache revision `mira-te3-small-384-v1`. The revision is our cache generation label, **not an immutable provider model snapshot**. The existing OpenAI credential was reused securely; local files remain ignored/0600 and unrelated settings were preserved. The template supplies the recommended model/revision but keeps its enable flag off for other installations. No worker was automatically launched and no remote deployment occurred.

The coordinator authorized **one controlled live embedding validation**, capped at two provider requests, 8,000 actual-plus-unknown-reserved tokens, 6,000 UTF-8 input bytes and 90 seconds. It used synthetic text and disposable PostgreSQL rows, the configured factory, actual isolated OpenAI SDK requests, the pgvector cache and normal scout retrieval/accounting. No research run, generative agent, Exa, publisher fetch or browser call was executed.

| Check | Measured result |
|---|---|
| Synonym-only retrieval | “beneficial ownership” retrieved the expected passage about the natural person who ultimately owns/controls a legal entity; zero lexical matches in the eligible pool |
| Cold provider request | Query plus four eligible passages; five 384-dimensional vectors; 42 tokens |
| Cached passage vectors | Four, with the configured model/revision/dimensions |
| Warm provider request through scout | Query only; one vector; three tokens |
| Repeated scout selection | No third provider request or duplicate embedding charge |
| Scope controls | Inactive MAS, foreign workspace, future/superseded versions and missing `embed` permission excluded from semantic inputs/results |
| MAS-only probe | No eligible passages and no additional provider call |
| Total provider usage | **45 measured tokens**, zero unknown reservations, 269 UTF-8 input bytes |
| Total validation time | **3.719 seconds** |
| Database fixtures | All rows/cache entries rolled back after warm-cache checks |

Default worker limits remain **40 eligible passages, 60,000 input characters, 20,000 embedding tokens, 20 seconds and 20 results**. The controlled fixture tightened them to four passages/4,000 characters/4,000 tokens/20 seconds/one result per retrieval. An above-cap eligible corpus falls back to keywords; this update does not silently sample or backfill a large corpus. Warm-cache behavior was checked within the validation transaction; it is not a hosted deployment or restart/recovery acceptance test.

Before the live execution, **14 hybrid/factory/deadline tests** and **two local PostgreSQL runtime tests** passed. The private harness was first exercised with fake embeddings and real PostgreSQL to check SQL, scout integration, the two-request cap and unknown-usage reservation. That offline fixture is separate from the measured actual-API result above. Final regression evidence is recorded in the [current hybrid handoff](../../docs/agent-handoffs/hybrid-retrieval.md).

Local reproduction evidence is retained under `reports/hybrid-validation-20261110/`: the exact harness, raw result and single-execution marker, with SHA256 values in the portable metadata. No credentials or provider vectors are exported. Re-executing the original harness is refused by its marker; this authorization is consumed, with no automatic retry/resume/replacement.

This validates the provider/cache/scout integration on a controlled corpus. It does not establish Hong Kong publication recall, human precision or archive-scale retrieval gains. The interrupted Hong Kong run remains an unchanged historical observation. MAS acquisition and private Supabase Storage uploads remain disabled; the separate Storage upload key is not needed for pgvector cache access through the database worker connection.
