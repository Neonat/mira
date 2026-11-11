# Offline synthetic prepared-report benchmark — 10 November 2026

**All fixture data, verifier responses and review decisions are synthetic. These results are not human precision or country coverage.**

Base `bfd45eb`; observed HEAD `bfd45ebef3aee99cecf98ee4fa28231771a66558`. Real local PostgreSQL; one source, four documents, 20 distinct critical facts; 20 exact-quote checks and 20 scripted support checks saved with canonical frozen evidence. Real job lease, immutable snapshot publication and normal report request queue. MAS inactive; keyword retrieval configured; hybrid experimental and unused.

| Case | Submit to final HTML | Facts preserved | Captured state | Provider calls |
|---|---:|---:|---|---:|
| review_pending | 0.092727s | 20/20 | human_review_pending | 0 |
| scripted_review_accepted | 0.090420s | 20/20 | human_checked | 0 |

Both submissions were below 300 seconds. Exact factual text, Article A/B/C, dates, exceptions, quoted passages, finding IDs, source IDs, citation URLs and HTML hashes were asserted. First report retained its pending warning and immutable content after later scripted acceptances. `human_checked` describes captured database review state; no person labelled these facts and final approval was not performed.

Reproduce from repository root (loads only DB environment keys and refuses remote/non-55432 connections):

```sh
PYTHONPATH=.:tests /Users/natsim/Documents/dbsearch/.venv/bin/python eval/prepared_report_benchmark.py
```

Each invocation creates a new isolated workspace and exactly two reports; it overwrites these dated output summaries. Private HTML, source fixtures and full captures: `reports/scheduled-evidence-20261110/benchmark/`. Portable JSON includes all 20 expected facts and database identities. No historical data or truth labels changed.

Limitations:

- All documents, claims, model responses and review decisions are synthetic; no human precision or country coverage claim.
- Single cold first submission plus one second submission; no statistical latency distribution, equal-budget comparison or capacity test.
- Timer starts after completed preparation, excludes import/check/publication, and includes normal request submission, DB worker and final HTML retrieval.
- No fresh ingestion latency, discovery recall, report recall against real publications, live provider reliability or final report approval measured.
- Fixture selects 20 known facts directly; no analysis coverage events were written, so analysis_coverage is null and exhaustive analysis is unmeasured.
- Only local PostgreSQL network access permitted; scripted verifier calls are not provider calls. Benchmark workspace remains isolated for inspection.

Next bounded step: coordinator may visually inspect the two saved HTML artifacts, then integrate the benchmark with focused runtime checks. A real prepared corpus and human labels require a separate explicit assignment.
