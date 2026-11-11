# Country source-method pilot — 10 November 2026

The useful combination is **source-specific acquisition, complete permitted evidence in PostgreSQL, and optional vector ranking**. The pilot supports direct publication acquisition over indiscriminate browser use. It does **not** establish that hybrid ranking improves answer quality or that one database product is superior.

Audience: this is an internal engineering/evaluation record for the project team. Auditor-facing reports should show readable source links, publication/version dates, page/paragraph citations and corroboration status. Competition claims should use the measured scope below, not present these checks as multi-country production coverage.

## Scope and outcome

User-selected scope: Malaysia, Australia, and **DIFC/DFSA plus relevant UAE federal sources**, kept separate. Base `03eb05fc6926e98da671c2ccfb9e16e30d605b3a`. One bounded validation; no research agents, generated report, corroboration run, permanent source grant, country enablement, model-setting change or remote deployment. MAS was excluded from every pilot source list; the existing research workspace remains inactive for MAS with zero saved MAS versions.

| Source | Observed result | Recommended method and retention |
|---|---|---|
| Australia — Federal Register | API returned structured Act metadata. Direct HTML returned 552,388 characters; the same compilation PDF yielded 434 pages and 681,687 characters. Browser landing capture took 63.8s and returned 21,282 characters; 0/20 sampled HTML text prefixes appeared there, versus 20/20 in the PDF. | API for instrument identity/version discovery, direct publication HTML for search, PDF for page references and comparison. A dedicated API adapter remains to be built. Keep attributed licensed text and passages; check excluded material before retaining whole originals. |
| Australia — AUSTRAC | Robots request timed out after 12.418s; no automated publication acquisition or browser retry. | Defer automated acquisition until robots can be checked. Its public-site licence and AUSTRAC Online have different scopes. |
| UAE federal — CBUAE | Direct hub HTML yielded 11,228 characters and 30 links; a linked sanctions-review PDF yielded 8 pages and 15,577 characters. Browser acquisition stopped at an access challenge after 52.676s. | Direct hub → approved document links/PDF. Private organisational-use text with required attribution under the reviewed terms; no external embedding of this material in the pilot. Rulebook subdomain needs its own host/rights review. |
| Dubai/DIFC — DFSA | Robots allowed the representative public paths, but published terms require prior permission for public/private electronic retrieval-system storage. No application fulltext acquisition, retention or embedding. | Source references/human review pending permission. Manual import does not remove the retrieval-system restriction. |
| Malaysia — BNM / AML portal | Both live robots files explicitly disallow ExaBot. Reviewed terms restrict copying/reuse beyond the specified personal non-gain uses. No Exa call or application fulltext retention. | Permission-gated direct acquisition if approved later; avoid Exa for these hosts. Do not route through browser to avoid the restriction. |
| Malaysia — Securities Commission | Robots did not block the representative public paths; published terms require written permission for inclusion in an electronic retrieval system. No application fulltext retention. | Obtain a source grant before indexing. Accessible HTML/PDF is not a storage grant. |

These are source-level results, not country-wide access decisions or legal advice. Malaysian/DFSA publication formats were inspected through managed web during source discovery; that is distinct from this application's acquisition/storage tests.

## Discovery and ranking

Two actual Exa API searches completed, five URL/title results each, with no article content requested. Australian results exposed an October compilation while the controlled format comparison deliberately held the July compilation fixed. Version selection must verify availability/registration dates and resolve stable instrument IDs; `/latest` alone is insufficient for historical questions. All five UAE results were on `rulebook.centralbank.ae`, outside the pilot's exact acquisition host grant; none was followed. Domain discovery must not expand acquisition permission automatically.

Six questions were frozen before retrieval. The comparison selected 30 Australian HTML passages from 488 by a deterministic URL/passage-number hash, capped at 35,000 UTF-8 bytes, without query-score selection. Both arms used the same sample and top10. The lexical arm used PostgreSQL full text with Mira's existing Scout term expansion; the hybrid arm used the same lexical ranks plus `text-embedding-3-small`, 384 dimensions, and RRF60. PostgreSQL vector/fusion results matched the production pure ranking function on all six questions.

- Top1 was unchanged for **5/6** questions. Top10 overlaps were **3, 9, 1, 9, 10, 2**.
- Median lexical query time: **0.00129s**. Hybrid including query embedding: **0.88053s**, excluding cold indexing. Small temporary-table timings are descriptive, not a production benchmark.
- **8 embedding requests, 7,557 known tokens, 34,204 input bytes; zero failed/unknown-usage calls.** Two indexing calls and six query calls. No retries or replacement paid run.
- No human relevance labels or answer-quality judgements. Changed ranks and a plausible paraphrase are not evidence of improvement. The negative-control question still returns candidates under the broad Scout lexical expansion and semantic ranking; retrieval is not a claim-support decision.

Keep hybrid experimental. The pilot does not compare Malay/Arabic, full country archives, enterprise-scale latency or end-to-end report quality.

## Storage and information preservation

Six JSON records — **five text representations plus one structured API record**, not six independent publications — round-tripped exactly through temporary local PostgreSQL JSONB tables. All **1,282,162 extracted characters and 1,671 passages** were preserved; every passage matched its recorded text offsets. Passage spans covered every extracted non-whitespace character. A private, attributed derived JSON snapshot also round-tripped with its SHA256 unchanged. Full text was retained independently of any claim summary.

This checks preservation **after extraction**. It does not prove that OCR, tables, footnotes or every fact in a publisher original were extracted correctly. HTML/PDF sizes differ; a larger extraction is not automatically more accurate. The browser landing page is a different representation and must not be treated as a complete replacement for the Act.

Recommended storage roles:

1. **PostgreSQL:** complete permitted extracted text, structured native records, source/instrument/version IDs, publication/availability/effective dates, hashes, passage/page offsets, permissions, coverage events and claim provenance. Claims are derived records, never the sole retained evidence.
2. **Private object storage where rights allow:** immutable publisher originals and separately labelled derived snapshots; database references plus hashes. The pilot tested a local derived snapshot, not whole-original retention or hosted storage durability.
3. **pgvector:** rebuildable, permission-scoped derivative cache alongside keyword search. Model/revision/content hashes identify cache entries; vectors do not replace evidence.

Map HTML, PDF and browser captures to the **same publication version** where justified, retaining representation-specific page mappings. Counting their copies as separate sources inflates storage and apparent corroboration. This generic cross-format identity mapping is a follow-up design need, not a capability established by this pilot.

No comparison of cloud providers, database engines, encryption, backup/restore or storage cost was performed. Keep the existing PostgreSQL architecture; this evidence does not justify migrating databases.

## Verification and audit exception

The live comparison harness completed six exact JSONB round trips, passage-offset checks, eight API calls and six SQL-versus-production fusion assertions. Its **final audit exited 1** because it incorrectly asserted that MAS was inactive across every unrelated persisted test workspace in the shared local database. The raw result and traceback are preserved; this is not represented as a wholly passing harness.

A separate read-only audit confirmed unchanged global MAS counts, inactive MAS/zero versions in the relevant saved research workspace, no persisted pilot tables after exception rollback, and no persistent source grants. No API or acquisition was repeated to correct the audit. The pilot only used temporary tables; no public evidence rows were written. A future harness should scope this assertion to its authorized workspace/source manifest from the start.

Independent read-only evidence review found no blockers: recorded metrics, checked hashes, sample membership, offsets and comparisons agreed with the artifacts. It did not independently query live services or the database. The separate pilot stages did not share one enforced global deadline; actual live activity finished within the stated 20-minute allowance. A reusable runner should enforce one shared deadline rather than rely on stage limits and coordinator supervision.

The caps were 12 publication targets, four Exa searches, two browser captures, ten embedding requests, 40,000 embedding tokens, 300,000 embedding input bytes and 20 minutes. Seven acquisition entries were recorded, including the added UAE PDF; there were two Exa calls, two browser captures and eight embedding calls. Preliminary endpoint discovery also requested the API schema and the same title-metadata endpoint subsequently checked through Mira's transport; those two successful requests are recorded separately. Nine initial robots probes and subsequent transport/browser policy/resource requests are outside the publication-target count. Live checks and the final audit ran from 18:52:24 to 18:59:23 UTC on 9 November, corresponding to 10 November in Singapore. Permission discovery preceded this timed application validation. No runtime code changed, so the previously recorded full suite was not repeated for this evidence-only pilot.

Portable metadata: [machine-readable result](2026-11-10-country-method-pilot.json). Private fulltext, harnesses, logs, attribution and snapshot are under `reports/country-method-pilot-20261110/`; their hashes are in the portable result. These files are ignored by git. No publisher article bodies or vectors are included in the portable evidence.

## Primary source policies

- [Federal Register terms](https://www.legislation.gov.au/terms-of-use) and [programmatic access/API policy](https://www.legislation.gov.au/help-and-resources/using-the-legislation-register/data-share-and-reuse). CC BY adaptation rights support this pilot's derived prose/vector use as an interpretation of the licence, not a source-specific embedding endorsement; excluded logos/third-party material are not granted by that inference.
- [AUSTRAC public copyright](https://www.austrac.gov.au/austrac-copyright-attribution-and-third-party-guidelines) and [separate AUSTRAC Online terms](https://www.austrac.gov.au/austrac-online-copyright).
- [CBUAE terms, particularly §2.3](https://centralbank.ae/en/footer/terms-and-conditions/) and [open-data policy](https://centralbank.ae/en/open-data-landing/open-data-policy/). The open-data licence was not applied indiscriminately to regulatory guidance.
- [DFSA legal disclaimer](https://www.dfsa.ae/Legal-Disclaimer) and [DIFC AML regulatory scope](https://www.dfsa.ae/what-we-do/aml-ctf-sanctions-compliance/regulatory-framework).
- [BNM terms](https://www.bnm.gov.my/terms-of-use), [AML portal terms](https://amlcft.bnm.gov.my/web/amlcft/terms-of-use), [BNM robots](https://www.bnm.gov.my/robots.txt), [AML portal robots](https://amlcft.bnm.gov.my/robots.txt), and [SC Malaysia disclaimer](https://www.sc.com.my/about/disclaimer).
