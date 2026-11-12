"""Source of truth for the M0 ground-truth list (docs/mira_m0_ground_truth.md).

Writes eval/m0_ground_truth.csv and prints the markdown items table, so the two never drift:

    .venv/bin/python eval/build_ground_truth.py eval/m0_ground_truth.csv > /tmp/table.md

Never import this from mira/: the list must stay out of prompts, fixtures and seed data.
"""

import csv
import sys
from pathlib import Path

VERIFIED = "2026-10-26"
FIELDS = ["id", "jurisdiction", "kind", "publisher", "category", "title", "reference", "published",
          "effective", "url", "expected_source", "reach", "summary", "verified", "hk_url"]

# These two shared FATF items have an official Hong Kong copy. Keep the
# benchmark identity and date so the market-specific URL does not add an item.
HK_FATF_COPIES = {
    "https://www.mas.gov.sg/publications/fatf-statement/2026/february-2026":
        "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/doc?refNo=26EC13",
    "https://www.mas.gov.sg/publications/fatf-statement/2026/june-2026":
        "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/doc?refNo=26EC39",
}

ITEMS = [
    ("SG", "regulatory", "MHA / SPF", "legislation", "Criminal Law (Miscellaneous Amendments) Act 2025", "", "2025-11-04", "2025-12-30",
     "https://www.police.gov.sg/Knowledge-Hub/Legislation/Caning-for-Scams-and-Scams-related-Offences", "SG-6", "manual",
     "Passed 4 Nov 2025; adds discretionary caning for scam mules convicted of laundering scam proceeds under the CDSA; in force 30 Dec 2025."),
    ("HK", "regulatory", "HKMA", "guideline", "Gazettal of Guideline on AI-to-AI Information Sharing for the Detection or Prevention of Crime", "20251106-2-EN", "2025-11-07", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251106-2-EN", "HK-2", "fetchable",
     "New statutory guideline on sharing information between authorized institutions to detect or prevent crime, listed with HKMA's AML/CFT statutory guidelines."),
    ("HK", "regulatory", "SFC", "circular", "Detection and prevention of potential layering activities in money laundering", "25EC62", "2025-11-17", "",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/doc?refNo=25EC62", "HK-6", "fetchable",
     "AML/CFT circular to licensed corporations and VASPs on detecting and preventing layering in money laundering."),
    ("HK", "regulatory", "HKMA", "circular", "Supporting Artificial Intelligence Adoption in AML/CFT", "20251118-3-EN", "2025-11-19", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251118-3-EN", "HK-3", "fetchable",
     "HKMA AML/CFT circular supporting banks' use of AI in AML/CFT."),
    ("HK", "regulatory", "HKMA", "circular", "Guidance on risk-based AML/CFT controls for politically exposed persons", "20251118-4-EN", "2025-11-21", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251118-4-EN", "HK-3", "fetchable",
     "HKMA guidance on risk-based controls for politically exposed persons, with 'Smart tips on the treatment of politically exposed persons'."),
    ("HK", "regulatory", "HKMA", "circular", "Guidance on combating high-end money laundering", "20251210-1-EN", "2025-12-12", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251210-1-EN", "HK-3", "fetchable",
     "HKMA guidance to banks on combating high-end money laundering."),
    ("HK", "regulatory", "FSTB / SFC", "consultation", "FSTB and SFC conclude consultations on virtual asset dealer and custodian regimes, further consult on two new regimes", "25PR210", "2025-12-24", "",
     "https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=25PR210&lang=EN", "HK-9", "fetchable",
     "Consultation conclusions: new VA dealing and custodian licensing regimes to be legislated under the AMLO (Cap. 615), bill planned for 2026."),
    ("HK", "regulatory", "SFC", "enforcement", "SFC reprimands and fines Kylin International (HK) Co., Limited $9 million for fund management failures", "26PR19", "2026-02-09", "",
     "https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=26PR19&lang=EN", "HK-7", "fetchable",
     "HK$9m fine; findings include failure to keep records showing compliance with AML/CTF requirements."),
    ("SG", "international", "MAS (FATF)", "circular", "February 2026 FATF Statement", "", "2026-02-24", "",
     "https://www.mas.gov.sg/publications/fatf-statement/2026/february-2026", "INT-1", "fetchable",
     "FATF plenary of 11-13 Feb 2026: high-risk and increased-monitoring lists; also forwarded by SFC circular of 13 Mar 2026."),
    ("SG", "regulatory", "MAS", "enforcement", "Licensed Fund Management Company And Its Officers Investigated For Suspected Money Laundering And Suspected Failure To Comply With Obligations As A Licensed Capital Markets Services Licence Holder", "", "2026-03-09", "",
     "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/capital-asia-investments", "SG-3", "blocked",
     "Capital Asia Investments and its officers investigated for suspected money laundering under CDSA s54; over S$160m of assets seized."),
    ("HK", "regulatory", "HKMA", "circular", "Thematic Review of Sanctions Screening Systems", "20260316-1-EN", "2026-03-16", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260316-1-EN", "HK-3", "fetchable",
     "HKMA findings from a thematic review of banks' sanctions screening systems."),
    ("SG", "regulatory", "MAS", "enforcement", "MAS Issues Prohibition Orders against former Relationship Managers Wang Qiming and Liu Kai", "", "2026-03-17", "",
     "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/mas-issues-prohibition-orders-against-former-relationship-managers-wang-qiming-and-liu-kai", "SG-3", "blocked",
     "16- and 7-year prohibition orders on two former relationship managers convicted in connection with the August 2023 money laundering case."),
    ("SG", "regulatory", "MAS", "media_release", "Singapore has a robust framework for combatting financial crime according to international body", "", "2026-05-06", "",
     "https://www.mas.gov.sg/news/media-releases/2026/singapore-has-a-robust-framework-for-combatting-financial-crime-according-to-international-body", "SG-5", "blocked",
     "FATF 5th-round mutual evaluation of Singapore published; Singapore placed on regular follow-up."),
    ("SG", "regulatory", "MAS", "enforcement", "MAS Imposes $300,000 Composition Penalty on Padang Trust Singapore Pte. Ltd. for AML/CFT Breaches", "", "2026-05-25", "",
     "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions/2026/mas-imposes-$300000-composition-penalty-on-padang-trust-singapore-pte-ltd-for-aml-cft-breaches", "SG-3", "blocked",
     "S$300,000 composition penalty on a licensed trust company for breaches of MAS AML/CFT requirements."),
    ("SG", "regulatory", "MAS", "circular", "Circular on Risk-Proportionate Source of Wealth Establishment", "AMLD 05/2026", "2026-05-25", "",
     "https://www.mas.gov.sg/regulation/circulars/circular-on-risk-proportionate-source-of-wealth-establishment", "SG-5", "blocked",
     "Guidance to banks and other FIs on risk-proportionate, efficient source-of-wealth establishment."),
    ("HK", "regulatory", "HKMA", "circular", "Supporting Adoption of Artificial Intelligence in Fighting Financial Crime", "20260622-1-EN", "2026-06-22", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260622-1-EN", "HK-3", "fetchable",
     "HKMA AML/CFT circular on adopting AI to fight financial crime."),
    ("SG", "international", "MAS (FATF)", "circular", "June 2026 FATF Statement", "", "2026-06-25", "",
     "https://www.mas.gov.sg/publications/fatf-statement/2026/june-2026", "INT-1", "fetchable",
     "FATF plenary of 17-19 Jun 2026: high-risk and increased-monitoring lists; also forwarded by SFC circular of 14 Jul 2026."),
    ("SG", "international", "Wolfsberg Group", "industry", "The Wolfsberg Group publishes updated Guidance on the Risk-Based Approach", "", "2026-06-23", "",
     "https://wolfsberg-group.org/news/guidance-on-the-risk-based-approach", "INT-3", "fetchable",
     "Updated industry guidance for banks on the risk-based approach to financial crime risk."),
    ("SG", "international", "Wolfsberg Group", "industry", "The Wolfsberg Group publishes Guidance on the provision of banking services to non-bank payment service providers (PSPs)", "", "2026-07-15", "",
     "https://wolfsberg-group.org/news/guidance-on-the-provision-of-banking-services", "INT-3", "fetchable",
     "Industry guidance for banks serving non-bank payment service providers."),
    ("HK", "regulatory", "SFC", "enforcement", "SFC reprimands and fines Victory Securities Company Limited $1.7 million and suspends its responsible officer for regulatory breaches", "26PR113", "2026-07-24", "",
     "https://apps.sfc.hk/edistributionWeb/api/news/list-content?refNo=26PR113&lang=EN", "HK-7", "fetchable",
     "HK$1.7m fine and RO suspension; the SFC found the firm fell short of the AMLO and AML Guideline by not enquiring into red flags before executing a client's orders."),
    ("HK", "regulatory", "HKMA", "circular", "Guidance on risk-based AML/CFT controls for politically exposed persons (Smart Tips version 2.0)", "20260827-4-EN", "2026-08-27", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260827-4-EN", "HK-3", "fetchable",
     "Revised PEP guidance with 'Smart Tips on the Treatment of Politically Exposed Persons_Version 2.0'."),
    ("HK", "regulatory", "HKMA", "circular", "Remote on-boarding of individual customers", "20260902-1-EN", "2026-09-03", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20260902-1-EN", "HK-3", "fetchable",
     "HKMA AML/CFT circular on remote on-boarding of individual customers."),
    ("HK", "regulatory", "SFC", "enforcement", "SFC reprimands and fines Zheng Da International Financial Holding Limited $7 million and suspends its responsible officer for regulatory breaches", "26PR158", "2026-09-29", "",
     "https://apps.sfc.hk/edistributionWeb/gateway/EN/news-and-announcements/news/doc?refNo=26PR158", "HK-7", "fetchable",
     "HK$7m fine and RO suspension for failing to comply with the AMLO and AML Guideline: no due diligence on customer-supplied trading systems, ineffective monitoring of suspicious trading."),
    ("HK", "regulatory", "HKMA", "circular", "Anti-bribery & corruption controls for account opening", "20261022-1-EN", "2026-10-22", "",
     "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20261022-1-EN", "HK-3", "fetchable",
     "HKMA circular, filed with its AML/CFT circulars, on anti-bribery and corruption controls at account opening."),
]

# Shared international items apply to both markets and count once.
rows = []
for number, item in enumerate(sorted(ITEMS, key=lambda i: (i[6], i[0], i[4])), 1):
    jurisdiction, kind, publisher, category, title, reference, published, effective, url, expected, reach, summary = item
    if kind == "international":
        jurisdiction = "SG,HK"
    rows.append(dict(zip(FIELDS, [f"GT{number:02d}", jurisdiction, kind, publisher, category, title, reference, published,
                                   effective, url, expected, reach, summary, VERIFIED, HK_FATF_COPIES.get(url, "")])))

out = Path(sys.argv[1])
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)

print("| ID | Published | Jurisdiction | Publisher | Item | Expected source | Reach | Kind |")
print("|---|---|---|---|---|---|---|---|")
for row in rows:
    ref = f" ({row['reference']})" if row["reference"] else ""
    title = row["title"].replace("|", "/")
    publisher = "SFC (HK) / MAS (SG)" if row["hk_url"] else row["publisher"]
    link = f"[{title}]({row['hk_url']}) ([SG copy]({row['url']}))" if row["hk_url"] else f"[{title}]({row['url']})"
    print(f"| {row['id']} | {row['published']} | {row['jurisdiction']} | {publisher} | {link}{ref}. {row['summary']} | {row['expected_source']} | {row['reach']} | {row['kind']} |")

counts = {
    "all": len(rows),
    "fetchable": sum(r["reach"] == "fetchable" for r in rows),
    "blocked": sum(r["reach"] == "blocked" for r in rows),
    "regulatory": sum(r["kind"] == "regulatory" for r in rows),
    "SG regulatory": sum(r["kind"] == "regulatory" and r["jurisdiction"] == "SG" for r in rows),
    "HK regulatory": sum(r["kind"] == "regulatory" and r["jurisdiction"] == "HK" for r in rows),
}
print("\n", counts, file=sys.stderr)
