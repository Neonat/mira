# Mira approved sources (D4 draft)

The allow-list of websites Mira's agents may read for the MVP (AML/CFT, Singapore and Hong Kong), and the draft expected-source list the completeness checker uses. Companion to [PRD v2](mira_PRD_v2.md) §5.3 and §6.4.

Every URL below was requested on **26 October 2026** with an honest automated user agent (`MiraResearchPrototype/0.1`), and `robots.txt` was read for each host. The Singapore Statutes Online pages for TSFA and FSMA returned HTTP 200 at first; the CDSA page ID was confirmed by search after SSO started refusing requests. Terms of use were read for MAS, HKMA and SFC. Re-check before M0; sites move pages often (four of the first candidate URLs had moved).

## Selection rules

1. **Official first.** Regulators, legislation databases and international standard-setters. These are authoritative and are the sources the DBS brief asks about.
2. **Industry bodies, not news publishers.** Industry developments come from bodies such as the Wolfsberg Group and the banking associations. Commercial news (Reuters, Bloomberg, Straits Times, SCMP) is excluded for the MVP: paywalls, copyright (risk G7) and lower authority. Open web search stays off (§5.3).
3. **Respect each site.** Obey `robots.txt` and crawl delays. Do not disguise the user agent or work around bot blocking; a blocked source is imported by hand instead.
4. **Use feeds where they exist.** RSS feeds and APIs are more stable than scraping listing pages and give dates reliably.

## How this maps to the database

Each row becomes a `sources` row: `source_type`, `base_url` (the host `fetch_allowed` checks), `jurisdiction_code`, and `permitted_operations`, using the vocabulary defined in migration `20261026120000`:

| Operation | Meaning |
|---|---|
| `metadata` | Store title, date and URL only |
| `fetch` | `fetch_allowed` may download pages from this host |
| `store_text` | Extracted text may be saved as passages (needed for the verifier) |
| `quote` | Short quotes may appear in reports, with attribution |
| `embed` | Passages may be embedded for vector search |

## Access summary

| Status | Sources | What it means for M0 |
|---|---|---|
| Fetchable | MAS, HKMA, SFC (www and RSS), JFIU, FSTB, APG, Wolfsberg, Egmont, ABS, HKAB, Basel Institute | Scouts can fetch directly |
| Fetchable but JavaScript-rendered | SFC enforcement news listing (`apps.sfc.hk`); MAS listing pages may filter client-side | Use the SFC RSS feeds; for MAS, follow links from the server-rendered AML and enforcement pages |
| `robots.txt` disallows all | HK e-Legislation (`elegislation.gov.hk`) | Do not fetch. Import Cap. 615 by hand once (download, then `manual` source) |
| Blocks automated requests (HTTP 403) | FATF (`fatf-gafi.org`), BIS (`bis.org`) | Do not fetch. Import the few needed documents by hand |
| Crawl delay | MAS 2 s, SSO 6 s (and `/search` disallowed) | `fetch_allowed` must rate-limit per host |
| Starts refusing after a few requests | Singapore Statutes Online (`sso.agc.gov.sg`): HTTP 200, then 202, then 403 within a few minutes | Treat as manual import for M0: the Acts change rarely, so download each once and store it as a `manual` source |

## Copyright and terms (risk G7)

| Publisher | What the terms allow | Proposed operations | Open point |
|---|---|---|---|
| **MAS** | Restrictive: no reproduction, caching or redistribution without prior written permission. One personal, non-commercial copy is allowed. | `metadata`, `fetch`, `store_text`, `quote`, `embed` | **Decided 26 October 2026:** the prototype stores MAS text so the verifier can check claims against saved passages. Written permission from MAS is still to be requested (see the README's additional notes). |
| **HKMA** | Non-commercial display, download and reproduction allowed in original form, unmodified and attributed to HKMA. HKMA also offers APIs that may be used to build search and analysis tools. | `metadata`, `fetch`, `store_text`, `quote`, `embed` | Attribute every quote. Prefer the [HKMA API](https://apidocs.hkma.gov.hk/) or RSS where it covers the content. |
| **SFC** | Download for personal use or within your organisation; brief extracts may be shared with acknowledgement; wider reproduction needs consent. | `metadata`, `fetch`, `store_text`, `quote`, `embed` | Keep report quotes brief and acknowledged; do not redistribute full documents. |
| Others | Not reviewed yet | `metadata`, `fetch` until reviewed | Read each site's terms before granting `store_text`. |

## Singapore

| Source | Covers | Start URL | Type |
|---|---|---|---|
| MAS: Anti-money laundering | AML/CFT notices, guidelines, papers for each sector | https://www.mas.gov.sg/regulation/anti-money-laundering | regulator |
| MAS: Notice 626 | AML/CFT requirements for banks (core rule) | https://www.mas.gov.sg/regulation/notices/notice-626 | regulator |
| MAS: Notices and guidelines listings | All MAS notices / guidelines | https://www.mas.gov.sg/regulation/regulations-and-guidance?content_type=Notices and `?content_type=Guidelines` | regulator |
| MAS: Enforcement actions | Penalties, prohibition orders, AML breaches | https://www.mas.gov.sg/regulation/enforcement/enforcement-actions | regulator |
| MAS: Consultations | Consultation papers and responses | https://www.mas.gov.sg/publications?content_type=Consultations | regulator |
| MAS: Media releases | Announcements, incl. AML enforcement and policy | https://www.mas.gov.sg/news?content_type=Media+Releases | regulator |
| Singapore Statutes Online | CDSA (money-laundering offences) | https://sso.agc.gov.sg/Act/CDTOSCCBA1992 | regulator (legislation) |
| Singapore Statutes Online | Terrorism (Suppression of Financing) Act | https://sso.agc.gov.sg/Act/TSFA2002 | regulator (legislation) |
| Singapore Statutes Online | Financial Services and Markets Act 2022 | https://sso.agc.gov.sg/Act/FSMA2022 | regulator (legislation) |
| MAS: MAS Act page | MAS Act (incl. AML powers); links to the SSO text | https://www.mas.gov.sg/regulation/acts/mas-act | regulator (legislation) |
| Association of Banks in Singapore | Industry guidance and best practice | https://abs.org.sg/ | website (industry) |

## Hong Kong

| Source | Covers | Start URL | Type |
|---|---|---|---|
| HKMA: AML/CFT | Hub for banking AML/CFT | https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/ | regulator |
| HKMA: Ordinances and statutory guidelines | AMLO references and the HKMA AML/CFT Guideline | https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/ordinances-statutory-guidelines/ | regulator |
| HKMA: Circulars and guidance papers (AML) | AML circulars, guidance papers (about 100 PDFs) | https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/guidance-papers-circulars/ | regulator |
| HKMA: RSS feeds | Press releases (incl. disciplinary actions), circulars, guidelines, consultations | https://www.hkma.gov.hk/eng/other-information/rss/rss_press-release.xml, `rss_circulars.xml`, `rss_guidelines.xml`, `rss_consultations.xml` (same folder) | rss |
| SFC: AML/CFT | SFC AML guideline, circulars for licensed corporations | https://www.sfc.hk/en/Rules-and-standards/Anti-money-laundering-and-counter-financing-of-terrorism | regulator |
| SFC: RSS feeds | Press releases (incl. enforcement), circulars, consultations | https://www.sfc.hk/en/RSS-Feeds/Press-releases, `/Circulars`, `/Consultations-and-Conclusions` | rss |
| HK e-Legislation | AMLO, Cap. 615 | https://www.elegislation.gov.hk/hk/cap615 | **manual import only** (robots.txt) |
| JFIU | Suspicious transaction reporting, typologies | https://www.jfiu.gov.hk/en/ | regulator |
| FSTB: AML/CFT regime | Government policy, risk assessments | https://www.fstb.gov.hk/fsb/en/business/policy_highlights/anti-money-laundering-and-counter-financing-of-terrorism-regime.html | regulator |
| Hong Kong Association of Banks | Industry guidance (some document folders disallowed by robots.txt) | https://www.hkab.org.hk/en/home | website (industry) |

## International standard-setters and industry

Apply to both jurisdictions.

| Source | Covers | Start URL | Access |
|---|---|---|---|
| FATF | Standards, grey/black lists, mutual evaluations, typologies | https://www.fatf-gafi.org/en/publications.html | **manual import only** (403) |
| Asia/Pacific Group on Money Laundering (APG) | Regional body for SG and HK; mutual evaluations, typologies | https://apgml.org/ | fetch |
| Wolfsberg Group | Industry AML standards and guidance for banks | https://wolfsberg-group.org/resources | fetch |
| Egmont Group | FIU cooperation, case studies | https://egmontgroup.org/news-and-events/ | fetch |
| Basel Committee (BIS) | Banking supervision standards touching AML | https://www.bis.org/publications/bcbs-publications | **manual import only** (403) |
| Basel Institute on Governance | Basel AML Index, research | https://baselgovernance.org/resources/basel-aml-index/ | fetch |

## Draft expected-source list (v1)

The completeness checker (§6.4) checks each row for every run. Category values match `expected_sources.category`. Coverage is always reported "relative to expected-source list v1".

| Jurisdiction | Category | Expected item (`document_hint`) | Source |
|---|---|---|---|
| SG | rule | MAS Notice 626 and amendments | MAS |
| SG | guideline | Guidelines to MAS Notice 626 | MAS |
| SG | enforcement | MAS enforcement actions involving AML/CFT | MAS |
| SG | consultation | MAS consultation papers on AML/CFT | MAS |
| SG | circular | MAS media releases on AML/CFT policy | MAS |
| SG | legislation | CDSA amendments | SSO |
| SG | legislation | Terrorism (Suppression of Financing) Act amendments | SSO |
| SG | legislation | FSMA 2022 AML-related provisions | SSO |
| SG | industry | ABS industry AML/CFT guidance | ABS |
| HK | legislation | AMLO (Cap. 615) amendments | HK e-Legislation (manual) |
| HK | guideline | HKMA Guideline on AML/CFT (for authorized institutions) | HKMA |
| HK | circular | HKMA AML/CFT circulars and guidance papers | HKMA |
| HK | consultation | HKMA consultations on AML/CFT | HKMA |
| HK | enforcement | HKMA disciplinary actions for AML breaches | HKMA |
| HK | guideline | SFC AML/CFT Guideline for licensed corporations | SFC |
| HK | enforcement | SFC enforcement actions involving AML | SFC |
| HK | consultation | SFC consultations on AML/CFT | SFC |
| HK | circular | FSTB AML/CFT policy and risk assessment updates | FSTB |
| SG, HK | industry | FATF plenary outcomes and high-risk jurisdiction lists | FATF (manual) |
| SG, HK | industry | APG mutual evaluation and follow-up reports | APG |
| SG, HK | industry | Wolfsberg Group publications | Wolfsberg |

## Open points before M0

1. **MAS permission** (see the copyright table). The prototype stores MAS text from 26 October 2026; the written permission request is still open.
2. **Manual imports** for AMLO Cap. 615, the Singapore Acts on SSO, FATF and BIS: who downloads them, and when they are refreshed.
3. **Terms review** for the remaining sources before granting `store_text`.
4. **Seed data:** turn this list into seed SQL for `sources` and `expected_sources` once the points above are settled.
