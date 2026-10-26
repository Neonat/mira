# Mira M0 ground truth: SG and HK AML/CFT developments

The go/no-go list for PRD v2 §11. Mira's single-agent prototype is scored by the share of these items it finds. **If recall is below 50%, the full build halts and the team reviews the approach.**

**Status: compiled by Claude from primary sources on 26 October 2026. It needs review by a human auditor before the gate is treated as final.** The same model family builds this list and runs Mira, so the two can share blind spots. The list was written before any Mira run produced findings, and is committed on its own so git history shows that.

Machine-readable copy: [`eval/m0_ground_truth.csv`](../eval/m0_ground_truth.csv).

## Rules (fixed before collection)

1. **Window.** Published or announced from 26 October 2025 to 26 October 2026 inclusive, as of 26 October 2026. This matches the evaluation window in §3.2 and does not move.
2. **One item** is one regulator publication or action:
   - A consultation paper and its later response are two items.
   - An amended notice or guideline is one item per issued revision.
   - Several penalties announced in one media release are one item.
   - A circular that only forwards another body's list (for example FATF statements) counts once, as the circular.
   - _Clarified during collection, on first meeting the same FATF statements forwarded by both MAS and the SFC:_ the statements from one FATF plenary are one item, wherever they are forwarded. It is dated by the first SG or HK regulator page, and any regulator's forwarding page matches it. A plenary held before the window is out even if it was forwarded inside the window.
3. **In scope:** the main subject is money laundering, terrorist financing or proliferation financing prevention, and it applies to banks (MAS, HKMA), to SFC-licensed corporations, or to the whole regime (legislation, national risk assessments, mutual evaluations).
4. **Out of scope:**
   - routine sanctions designation updates
   - investor alerts and lists of suspicious websites
   - enforcement that does not cite AML/CFT failures
   - speeches
   - industry news from commercial publishers
5. **Matching.** A Mira finding matches an item when it cites a document from the same publisher and identifies the same publication by reference number, title or canonical URL. For enforcement, it must name the same firm or individual and the same action.
6. **Evidence.** Every item's title and date come from its official page, fetched on the date shown. Anything that could not be confirmed is listed separately and does not count.

## Columns

| Column | Meaning |
|---|---|
| `expected_source` | The row of the [expected-source list v1](mira_approved_sources.md#draft-expected-source-list-v1) the item falls under (codes below) |
| `reach` | `fetchable`: on an allow-listed host Mira may fetch. `manual`: the source refuses automated access, so Mira finds it only after a manual import. `outside`: not on the allow-list |
| `kind` | `regulatory` (SG and HK authorities) or `international` (FATF, APG, Wolfsberg) |

Recall is reported three ways: all items, `fetchable` items only (manual imports are deferred; see the README's additional notes), and `regulatory` items only.

Expected-source codes:

| Code | Expected item | Code | Expected item |
|---|---|---|---|
| SG-1 | MAS Notice 626 and amendments | HK-1 | AMLO (Cap. 615) amendments |
| SG-2 | Guidelines to MAS Notice 626 | HK-2 | HKMA Guideline on AML/CFT |
| SG-3 | MAS enforcement actions involving AML/CFT | HK-3 | HKMA AML/CFT circulars and guidance papers |
| SG-4 | MAS consultation papers on AML/CFT | HK-4 | HKMA consultations on AML/CFT |
| SG-5 | MAS media releases on AML/CFT policy | HK-5 | HKMA disciplinary actions for AML breaches |
| SG-6 | CDSA amendments | HK-6 | SFC AML/CFT Guideline for licensed corporations |
| SG-7 | Terrorism (Suppression of Financing) Act amendments | HK-7 | SFC enforcement actions involving AML |
| SG-8 | FSMA 2022 AML-related provisions | HK-8 | SFC consultations on AML/CFT |
| SG-9 | ABS industry AML/CFT guidance | HK-9 | FSTB AML/CFT policy and risk assessment updates |
| INT-1 | FATF plenary outcomes and high-risk jurisdiction lists | INT-2 | APG mutual evaluation and follow-up reports |
| INT-3 | Wolfsberg Group publications | | |

## Items

**23 items:** 19 regulatory (6 SG, 13 HK) and 4 international; 22 `fetchable`, 1 `manual`.

PRD v2 §11 expected 20 to 40 items. The count is what the listings support; nothing was added to reach a number.

| ID | Published | Jurisdiction | Publisher | Item | Expected source | Reach | Kind |
|---|---|---|---|---|---|---|---|
| GT01 | 2025-11-04 | SG | MHA / SPF | [Criminal Law (Miscellaneous Amendments) Act 2025](https://www.police.gov.sg/Knowledge-Hub/Legislation/Caning-for-Scams-and-Scams-related-Offences). Passed 4 Nov 2025; adds discretionary caning for scam mules convicted of laundering scam proceeds under the CDSA; in force 30 Dec 2025. | SG-6 | manual | regulatory |
| GT02 | 2025-11-07 | HK | HKMA | [Gazettal of Guideline on AI-to-AI Information Sharing for the Detection or Prevention of Crime](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251106-2-EN) (20251106-2-EN). New statutory guideline on sharing information between authorized institutions to detect or prevent crime, listed with HKMA's AML/CFT statutory guidelines. | HK-2 | fetchable | regulatory |
| GT03 | 2025-11-17 | HK | SFC | [Detection and prevention of potential layering activities in money laundering](https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/). AML/CFT circular to licensed corporations and VASPs on detecting and preventing layering in money laundering. | HK-6 | fetchable | regulatory |
| GT04 | 2025-11-19 | HK | HKMA | [Supporting Artificial Intelligence Adoption in AML/CFT](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251118-3-EN) (20251118-3-EN). HKMA AML/CFT circular supporting banks' use of AI in AML/CFT. | HK-3 | fetchable | regulatory |
| GT05 | 2025-11-21 | HK | HKMA | [Guidance on risk-based AML/CFT controls for politically exposed persons](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251118-4-EN) (20251118-4-EN). HKMA guidance on risk-based controls for politically exposed persons, with 'Smart tips on the treatment of politically exposed persons'. | HK-3 | fetchable | regulatory |
| GT06 | 2025-12-12 | HK | HKMA | [Guidance on combating high-end money laundering](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251210-1-EN) (20251210-1-EN). HKMA guidance to banks on combating high-end money laundering. | HK-3 | fetchable | regulatory |
| GT07 | 2025-12-24 | HK | FSTB / SFC | [FSTB and SFC conclude consultations on virtual asset dealer and custodian regimes, further consult on two new regimes](https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=25PR210&lang=EN) (25PR210). Consultation conclusions: new VA dealing and custodian licensing regimes to be legislated under the AMLO (Cap. 615), bill planned for 2026. | HK-9 | fetchable | regulatory |
| GT08 | 2026-02-09 | HK | SFC | [SFC reprimands and fines Kylin International (HK) Co., Limited $9 million for fund management failures](https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=26PR19&lang=EN) (26PR19). HK$9m fine; findings include failure to keep records showing compliance with AML/CTF requirements. | HK-7 | fetchable | regulatory |
| GT09 | 2026-02-24 | SG,HK | MAS (FATF) | [February 2026 FATF Statement](https://www.mas.gov.sg/publications/fatf-statement/2026/february-2026). FATF plenary of 11-13 Feb 2026: high-risk and increased-monitoring lists; also forwarded by SFC circular of 13 Mar 2026. | INT-1 | fetchable | international |
| GT10 | 2026-03-09 | SG | MAS | [Licensed Fund Management Company And Its Officers Investigated For Suspected Money Laundering And Suspected Failure To Comply With Obligations As A Licensed Capital Markets Services Licence Holder](https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/capital-asia-investments). Capital Asia Investments and its officers investigated for suspected money laundering under CDSA s54; over S$160m of assets seized. | SG-3 | fetchable | regulatory |
| GT11 | 2026-03-16 | HK | HKMA | [Thematic Review of Sanctions Screening Systems](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260316-1-EN) (20260316-1-EN). HKMA findings from a thematic review of banks' sanctions screening systems. | HK-3 | fetchable | regulatory |
| GT12 | 2026-03-17 | SG | MAS | [MAS Issues Prohibition Orders against former Relationship Managers Wang Qiming and Liu Kai](https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/mas-issues-prohibition-orders-against-former-relationship-managers-wang-qiming-and-liu-kai). 16- and 7-year prohibition orders on two former relationship managers convicted in connection with the August 2023 money laundering case. | SG-3 | fetchable | regulatory |
| GT13 | 2026-05-06 | SG | MAS | [Singapore has a robust framework for combatting financial crime according to international body](https://www.mas.gov.sg/news/media-releases/2026/singapore-has-a-robust-framework-for-combatting-financial-crime-according-to-international-body). FATF 5th-round mutual evaluation of Singapore published; Singapore placed on regular follow-up. | SG-5 | fetchable | regulatory |
| GT14 | 2026-05-25 | SG | MAS | [Circular on Risk-Proportionate Source of Wealth Establishment](https://www.mas.gov.sg/regulation/circulars/circular-on-risk-proportionate-source-of-wealth-establishment) (AMLD 05/2026). Guidance to banks and other FIs on risk-proportionate, efficient source-of-wealth establishment. | SG-5 | fetchable | regulatory |
| GT15 | 2026-05-25 | SG | MAS | [MAS Imposes $300,000 Composition Penalty on Padang Trust Singapore Pte. Ltd. for AML/CFT Breaches](https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/mas-imposes-$300000-composition-penalty-on-padang-trust-singapore-pte-ltd-for-aml-cft-breaches). S$300,000 composition penalty on a licensed trust company for breaches of MAS AML/CFT requirements. | SG-3 | fetchable | regulatory |
| GT16 | 2026-06-22 | HK | HKMA | [Supporting Adoption of Artificial Intelligence in Fighting Financial Crime](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260622-1-EN) (20260622-1-EN). HKMA AML/CFT circular on adopting AI to fight financial crime. | HK-3 | fetchable | regulatory |
| GT17 | 2026-06-23 | SG,HK | Wolfsberg Group | [The Wolfsberg Group publishes updated Guidance on the Risk-Based Approach](https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach). Updated industry guidance for banks on the risk-based approach to financial crime risk. | INT-3 | fetchable | international |
| GT18 | 2026-06-25 | SG,HK | MAS (FATF) | [June 2026 FATF Statement](https://www.mas.gov.sg/publications/fatf-statement/2026/june-2026). FATF plenary of 17-19 Jun 2026: high-risk and increased-monitoring lists; also forwarded by SFC circular of 14 Jul 2026. | INT-1 | fetchable | international |
| GT19 | 2026-07-15 | SG,HK | Wolfsberg Group | [The Wolfsberg Group publishes Guidance on the provision of banking services to non-bank payment service providers (PSPs)](https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services). Industry guidance for banks serving non-bank payment service providers. | INT-3 | fetchable | international |
| GT20 | 2026-08-27 | HK | HKMA | [Guidance on risk-based AML/CFT controls for politically exposed persons (Smart Tips version 2.0)](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260827-4-EN) (20260827-4-EN). Revised PEP guidance with 'Smart Tips on the Treatment of Politically Exposed Persons_Version 2.0'. | HK-3 | fetchable | regulatory |
| GT21 | 2026-09-03 | HK | HKMA | [Remote on-boarding of individual customers](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260902-1-EN) (20260902-1-EN). HKMA AML/CFT circular on remote on-boarding of individual customers. | HK-3 | fetchable | regulatory |
| GT22 | 2026-09-29 | HK | SFC | [SFC reprimands and fines Zheng Da International Financial Holding Limited $7 million and suspends its responsible officer for regulatory breaches](https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR158) (26PR158). HK$7m fine and RO suspension for failing to comply with the AMLO and AML Guideline: no due diligence on customer-supplied trading systems, ineffective monitoring of suspicious trading. | HK-7 | fetchable | regulatory |
| GT23 | 2026-10-22 | HK | HKMA | [Anti-bribery & corruption controls for account opening](https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20261022-1-EN) (20261022-1-EN). HKMA circular, filed with its AML/CFT circulars, on anti-bribery and corruption controls at account opening. | HK-3 | fetchable | regulatory |

Notes on reach:

- `fetchable` assumes the scouts' allow-list covers the hosts the documents live on, not only the start URLs:
  - HKMA circulars are served from `brdr.hkma.gov.hk`, not `www.hkma.gov.hk`.
  - SFC circulars and news are served from `apps.sfc.hk`. Those pages are rendered with JavaScript, so the scout should use the SFC RSS feeds.
- GT01 is `manual` because the Act's text is on Singapore Statutes Online. MHA and SPF, which announced it, are not on the allow-list.
- HKMA listing dates sometimes differ by a day or two from the date in the document ID (GT05, GT06, GT21). The listing date is used.

## Listings scanned

All scanned on 26 October 2026.

| Publisher | Listing | Window coverage |
|---|---|---|
| HKMA | [AML/CFT circulars and guidance papers](https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/guidance-papers-circulars/) | Full |
| HKMA | [AML/CFT ordinances and statutory guidelines](https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/ordinances-statutory-guidelines/) | Full. The AML/CFT Guideline for authorized institutions is still the May 2023 revision |
| HKMA | [AML disciplinary actions](https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism/disciplinary-actions/) and [enforcement press releases](https://www.hkma.gov.hk/eng/news-and-media/press-releases/enforcement/) | Full. No AML disciplinary action after 22 Jul 2025 |
| SFC | [AML/CFT circulars](https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/), 2025 and 2026, all categories | Full |
| SFC | [Consultations](https://apps.sfc.hk/edistributionWeb/gateway/EN/consultation/) | Full |
| SFC | [Enforcement news](https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/enforcement-news/), 26 Sep 2025 to 22 Oct 2026 | Titles screened; AML content checked for firm fines with unclear titles |
| FSTB | [AML/CFT regime site](https://www.fstb.gov.hk/fsb/aml/en/overview.htm) | Last revised 7 Aug 2025; nothing in window |
| MAS | [Notice 626](https://www.mas.gov.sg/regulation/notices/notice-626) | Last revised 30 Jun 2025, before the window |
| MAS | [Anti-money laundering page](https://www.mas.gov.sg/regulation/anti-money-laundering) | Full |
| MAS | [Enforcement actions](https://www.mas.gov.sg/regulation/enforcement/enforcement-actions), pages 1-3 | Full. Every action in the window was opened and checked for AML content |
| MAS | [Consultations](https://www.mas.gov.sg/publications/consultations), pages 1-2 | Full. No AML/CFT consultation in the window |
| MAS | Quarterly enforcement summaries for [Q1](https://www.mas.gov.sg/news/media-releases/2026/key-enforcement-actions-taken-by-mas-in-q1-2026) and [Q2 2026](https://www.mas.gov.sg/news/media-releases/2026/key-enforcement-actions-taken-by-mas-in-q2-2026) | Cross-check |
| MHA / SPF | AML and CDSA legislation releases | Search-based |
| APG | [Home page news](https://apgml.org/) | No SG or HK item in the window |
| Wolfsberg Group | [Home page news and resources](https://wolfsberg-group.org/) | Full |
| ABS | [Industry guidelines](https://abs.org.sg/industry-guidelines) | No dated items; nothing countable |

## Considered and excluded

| Candidate | Why excluded |
|---|---|
| FATF plenary of 22-24 Oct 2025 (forwarded by SFC on 12 Nov 2025 and MAS on 13 Nov 2025) | Plenary held before the window |
| FATF plenary of 28-30 Oct 2026 | After the window |
| SFC UN sanctions circulars; "Early Alert on United Nations Sanctions" | Routine sanctions designation updates |
| SFC AML webinar circulars (27 Nov 2025, 13 Oct 2026) | Events, not regulatory publications |
| SFC fine on EFG Bank AG, 11 Dec 2025 | Product due diligence, not AML |
| HKMA circular on VA activities for licensed stablecoins, 27 May 2026 | Not AML/CFT |
| Banking Legislation (Miscellaneous Amendments) Bill 2026 | Not AML/CFT |
| MAS enforcement actions in the window other than GT10, GT12 and GT15 | Each opened; none cites AML/CFT |
| Wolfsberg note on human trafficking disruption during the World Cup | Concerns the US 314(b) information-sharing mechanism, not SG or HK banks |
| Wolfsberg stablecoin issuer guidance (8 Sep 2025) and earlier 2025 statements | Before the window |

## Unconfirmed candidates (not counted)

| Candidate | What is missing |
|---|---|
| SFC fines on XHK Limited (1 Jun 2026), Victory Securities (24 Jul 2026) and China Industrial Securities International Asset Management (27 Jul 2026) | Titles say only "regulatory breaches" or "red flags". The full releases were not reached, so AML relevance is unconfirmed |
| MAS circulars AMLD 01/2026 to 04/2026 | AMLD 05/2026 implies earlier 2026 AML circulars, but none appears in MAS's public listings |
| MAS consultation numbers P008-2026, P010-2026 and P018-2025 | Missing from the public consultations listing; topics unknown |

A human reviewer should resolve these before the gate is final, and add anything the listings above could not show.
