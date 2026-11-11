"""Allow-listed sources and expected-source list v2 (docs/mira_approved_sources.md).

``seed(conn, workspace_id)`` upserts both, so it is safe to run again after the
list changes. Start URLs are hub, listing and feed pages only; individual
documents are found by the scouts.

``permitted_operations`` follows the approved-sources terms review: MAS (decided
26 Oct 2026), Singapore Statutes Online and HK e-Legislation (decided 6 Nov 2026),
HKMA and SFC may store text; other sites are ``metadata`` and ``fetch`` until
their terms are reviewed; other sources that refuse automated access are
``manual`` with ``metadata`` only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from mira.topics import CYBERSECURITY, CYBER_SOURCE_ROUTES

ALL_OPERATIONS = ("metadata", "fetch", "store_text", "quote", "embed")
FETCH_ONLY = ("metadata", "fetch")
MANUAL = ("metadata",)
EXPECTED_LIST_VERSION = 3


@dataclass(frozen=True)
class SourceSeed:
    key: str
    name: str
    publisher: str
    source_type: str
    base_url: str
    jurisdiction: str | None
    operations: tuple[str, ...]
    start_urls: tuple[str, ...] = ()
    feeds: tuple[str, ...] = ()
    extra_hosts: tuple[str, ...] = ()
    crawl_delay_seconds: float = 1.0
    block_markers: tuple[str, ...] = ()
    notes: str = ""
    category_urls: dict[str, tuple[str, ...]] = field(default_factory=dict)
    is_active: bool = True
    profile: dict[str, object] = field(default_factory=dict)

    def connector_config(self) -> dict[str, object]:
        return {
            "start_urls": list(self.start_urls),
            "feeds": list(self.feeds),
            "extra_hosts": list(self.extra_hosts),
            "crawl_delay_seconds": self.crawl_delay_seconds,
            "block_markers": list(self.block_markers),
            "category_urls": {key: list(urls) for key, urls in self.category_urls.items()},
            **self.profile,
        }


MAS_AML = "https://www.mas.gov.sg/regulation/anti-money-laundering"
HKMA_AML = "https://www.hkma.gov.hk/eng/key-functions/banking/anti-money-laundering-and-counter-financing-of-terrorism"
HKMA_RSS = "https://www.hkma.gov.hk/eng/other-information/rss"

SOURCES: tuple[SourceSeed, ...] = (
    SourceSeed(
        "mas", "MAS", "Monetary Authority of Singapore", "regulator", "https://www.mas.gov.sg", "SG", ALL_OPERATIONS,
        start_urls=(
            MAS_AML,
            "https://www.mas.gov.sg/regulation/notices/notice-626",
            "https://www.mas.gov.sg/regulation/guidelines/guidelines-to-notice-626-on-prevention-of-money-laundering-and-cft-for-banks",
            "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions",
            "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions?page=2",
        ),
        crawl_delay_seconds=2.0,
        block_markers=("Sorry, this service is currently unavailable",),
        is_active=False,
        notes=("robots.txt crawl delay 2 s. From 26 Oct 2026 the site serves a block page to automated "
               "requests (pages, sitemap and PDFs); import MAS documents by hand until access is agreed"),
    ),
    SourceSeed("sso", "Singapore Statutes Online", "Attorney-General's Chambers", "manual", "https://sso.agc.gov.sg", "SG", ALL_OPERATIONS,
               notes=("Refuses automated requests; import Acts by hand. From 6 Nov 2026 the text of imported "
                      "Acts is stored and quoted")),
    SourceSeed("abs", "Association of Banks in Singapore", "ABS", "website", "https://abs.org.sg", "SG", FETCH_ONLY,
               start_urls=("https://abs.org.sg/industry-guidelines",)),
    SourceSeed(
        "hkma", "HKMA", "Hong Kong Monetary Authority", "regulator", "https://www.hkma.gov.hk", "HK", ALL_OPERATIONS,
        start_urls=(
            f"{HKMA_AML}/guidance-papers-circulars/",
            f"{HKMA_AML}/ordinances-statutory-guidelines/",
            f"{HKMA_AML}/disciplinary-actions/",
        ),
        feeds=(f"{HKMA_RSS}/rss_circulars.xml", f"{HKMA_RSS}/rss_guidelines.xml",
               f"{HKMA_RSS}/rss_consultations.xml", f"{HKMA_RSS}/rss_press-release.xml"),
        extra_hosts=("brdr.hkma.gov.hk",),
        notes="Circulars and guidelines are served from brdr.hkma.gov.hk",
        category_urls={
            "circular": (f"{HKMA_AML}/guidance-papers-circulars/",),
            "guideline": (f"{HKMA_AML}/ordinances-statutory-guidelines/",),
            "enforcement": (f"{HKMA_AML}/disciplinary-actions/",),
            "consultation": (f"{HKMA_RSS}/rss_consultations.xml",),
        },
    ),
    SourceSeed(
        "sfc", "SFC", "Securities and Futures Commission", "regulator", "https://www.sfc.hk", "HK", ALL_OPERATIONS,
        start_urls=("https://www.sfc.hk/en/Rules-and-standards/Anti-money-laundering-and-counter-financing-of-terrorism",),
        feeds=("https://www.sfc.hk/en/RSS-Feeds/Press-releases", "https://www.sfc.hk/en/RSS-Feeds/Circulars",
               "https://www.sfc.hk/en/RSS-Feeds/Consultations-and-Conclusions"),
        extra_hosts=("apps.sfc.hk",),
        notes="Use the public publication-search and content services behind the SFC's JavaScript pages; RSS covers only recent items",
        category_urls={
            "circular": ("https://apps.sfc.hk/edistributionWeb/api/circular/search?category=anti-money-laundering&year={year}&pageSize=100",),
            "guideline": ("https://www.sfc.hk/en/Rules-and-standards/Anti-money-laundering-and-counter-financing-of-terrorism/Legal-and-regulatory-requirements",),
            "enforcement": ("https://apps.sfc.hk/edistributionWeb/api/news/search?category=enforcement&year={year}&pageSize=100",),
            "consultation": ("https://apps.sfc.hk/edistributionWeb/api/consultation/search?category=all&year={year}&pageSize=100",),
        },
    ),
    SourceSeed("hk-elegislation", "HK e-Legislation", "Department of Justice", "manual", "https://www.elegislation.gov.hk", "HK", ALL_OPERATIONS,
               notes=("robots.txt disallows all; import Cap. 615 by hand. From 6 Nov 2026 the text of imported "
                      "ordinances is stored and quoted")),
    SourceSeed("jfiu", "JFIU", "Joint Financial Intelligence Unit", "regulator", "https://www.jfiu.gov.hk", "HK", FETCH_ONLY,
               start_urls=("https://www.jfiu.gov.hk/en/",)),
    SourceSeed("fstb", "FSTB", "Financial Services and the Treasury Bureau", "regulator", "https://www.fstb.gov.hk", "HK", FETCH_ONLY,
               start_urls=("https://www.fstb.gov.hk/fsb/aml/en/overview.htm",)),
    SourceSeed("hkab", "Hong Kong Association of Banks", "HKAB", "website", "https://www.hkab.org.hk", "HK", FETCH_ONLY,
               start_urls=("https://www.hkab.org.hk/en/home",)),
    SourceSeed("fatf", "FATF", "Financial Action Task Force", "manual", "https://www.fatf-gafi.org", None, MANUAL,
               notes="HTTP 403 to automated requests; import by hand"),
    SourceSeed("apg", "Asia/Pacific Group on Money Laundering", "APG", "website", "https://apgml.org", None, FETCH_ONLY,
               start_urls=("https://apgml.org/",)),
    SourceSeed("wolfsberg", "Wolfsberg Group", "Wolfsberg Group", "website", "https://wolfsberg-group.org", None, FETCH_ONLY,
               start_urls=("https://wolfsberg-group.org/resources",)),
    SourceSeed("egmont", "Egmont Group", "Egmont Group", "website", "https://egmontgroup.org", None, FETCH_ONLY,
               start_urls=("https://egmontgroup.org/news-and-events/",)),
    SourceSeed("bis", "Basel Committee (BIS)", "Bank for International Settlements", "manual", "https://www.bis.org", None, MANUAL,
               notes="HTTP 403 to automated requests; import by hand"),
    SourceSeed("basel-institute", "Basel Institute on Governance", "Basel Institute on Governance", "website",
               "https://baselgovernance.org", None, FETCH_ONLY,
               start_urls=("https://baselgovernance.org/resources/basel-aml-index/",)),
    SourceSeed(
        "au-register", "Federal Register of Legislation", "Office of Parliamentary Counsel", "regulator",
        "https://www.legislation.gov.au", "AU", ALL_OPERATIONS,
        start_urls=("https://api.prod.legislation.gov.au/v1/Versions?$filter=titleId%20eq%20'C2006A00169'&$orderby=registeredAt%20desc&$top=12",),
        extra_hosts=("api.prod.legislation.gov.au",), crawl_delay_seconds=10,
        notes="CC BY 4.0 licensed prose with attribution, excluding marked/third-party material. API discovery and fixed dated files; no blanket grant for originals. https://www.legislation.gov.au/terms-of-use",
        profile={"acquisition_profile":"register_api_files", "allow_live_browser":False,
                 "allow_browser":False,"discovery_hosts":["www.legislation.gov.au"],
                 "source_reuse":{"notice":"Based on content from the Federal Register of Legislation, downloaded {retrieved_date}. CC BY 4.0. Changes: text extracted; formatting changed. No endorsement.",
                                 "reference":"https://www.legislation.gov.au/terms-of-use",
                                 "licence":"https://creativecommons.org/licenses/by/4.0/"}},
    ),
    SourceSeed(
        "austrac", "AUSTRAC", "Australian Transaction Reports and Analysis Centre", "regulator",
        "https://www.austrac.gov.au", "AU", ALL_OPERATIONS,
        start_urls=("https://www.austrac.gov.au/industry-and-business/obligations-and-guidance/your-amlctf-program/develop-your-amlctf-programs/step-3-manage-and-mitigate-your-risks-amlctf-policies",),
        notes="Public guidance only; live robots must permit each request. AUSTRAC Online and excluded logos/third-party material are outside this grant. https://www.austrac.gov.au/austrac-copyright-attribution-and-third-party-guidelines",
        profile={"acquisition_profile":"public_guidance_files","allow_live_browser":False,"allow_browser":False,
                 "source_reuse":{"notice":"© Commonwealth of Australia (AUSTRAC). CC BY 4.0 for licensed material. Downloaded {retrieved_date}; text extracted and formatting changed. No endorsement.",
                                 "reference":"https://www.austrac.gov.au/austrac-copyright-attribution-and-third-party-guidelines",
                                 "licence":"https://creativecommons.org/licenses/by/4.0/"}},
    ),
    SourceSeed(
        "cbuae", "CBUAE (federal)", "Central Bank of the UAE", "regulator", "https://centralbank.ae", "AE",
        ("metadata","fetch","store_text","quote"),
        start_urls=("https://centralbank.ae/en/our-operations/anti-money-laundering-aml/offsite-supervision/",),
        category_urls={"guideline":("https://centralbank.ae/en/our-operations/anti-money-laundering-aml/offsite-supervision/",)},
        notes="Federal public pages and same-host PDFs; internal organisational use under §2.3 with copyright notice. No external embedding or browser-block fallback; no rulebook subdomain, DIFC/DFSA or VARA approval. https://centralbank.ae/en/footer/terms-and-conditions/",
        profile={"acquisition_profile":"federal_hub_pdf","allow_live_browser":False,"allow_browser":False,
                 "source_reuse":{"notice":"© Central Bank of the UAE. Private organisational-use extract, downloaded {retrieved_date}. Formatting changed. No endorsement.",
                                 "reference":"https://centralbank.ae/en/footer/terms-and-conditions/"}},
    ),
)


@dataclass(frozen=True)
class ExpectedSeed:
    jurisdiction: str
    category: str
    hint: str
    source_key: str
    url_hint: str | None = None


EXPECTED: tuple[ExpectedSeed, ...] = (
    ExpectedSeed("SG", "rule", "MAS Notice 626 and amendments", "mas", "https://www.mas.gov.sg/regulation/notices/notice-626"),
    ExpectedSeed("SG", "guideline", "Guidelines to MAS Notice 626", "mas"),
    ExpectedSeed("SG", "enforcement", "MAS enforcement actions involving AML/CFT", "mas", "https://www.mas.gov.sg/regulation/enforcement/enforcement-actions"),
    ExpectedSeed("SG", "consultation", "MAS consultation papers on AML/CFT", "mas"),
    ExpectedSeed("SG", "circular", "MAS media releases on AML/CFT policy", "mas"),
    ExpectedSeed("SG", "legislation", "CDSA amendments", "sso"),
    ExpectedSeed("SG", "legislation", "Terrorism (Suppression of Financing) Act amendments", "sso"),
    ExpectedSeed("SG", "legislation", "FSMA 2022 AML-related provisions", "sso"),
    ExpectedSeed("SG", "industry", "ABS industry AML/CFT guidance", "abs"),
    ExpectedSeed("HK", "legislation", "AMLO (Cap. 615) amendments", "hk-elegislation"),
    ExpectedSeed("HK", "guideline", "HKMA Guideline on AML/CFT (for authorized institutions)", "hkma"),
    ExpectedSeed("HK", "circular", "HKMA AML/CFT circulars and guidance papers", "hkma", f"{HKMA_AML}/guidance-papers-circulars/"),
    ExpectedSeed("HK", "consultation", "HKMA consultations on AML/CFT", "hkma"),
    ExpectedSeed("HK", "enforcement", "HKMA disciplinary actions for AML breaches", "hkma", f"{HKMA_AML}/disciplinary-actions/"),
    ExpectedSeed("HK", "guideline", "SFC AML/CFT Guideline for licensed corporations", "sfc"),
    ExpectedSeed("HK", "circular", "SFC AML/CFT circulars", "sfc"),
    ExpectedSeed("HK", "enforcement", "SFC enforcement actions involving AML", "sfc"),
    ExpectedSeed("HK", "consultation", "SFC consultations on AML/CFT", "sfc"),
    ExpectedSeed("HK", "circular", "FSTB AML/CFT policy and risk assessment updates", "fstb"),
    ExpectedSeed("AU", "legislation", "Federal AML/CTF Act registered compilations", "au-register"),
    ExpectedSeed("AU", "guideline", "AUSTRAC public AML/CTF program policies guidance", "austrac"),
    ExpectedSeed("AE", "guideline", "CBUAE federal AML/CFT thematic reviews and guidance publications", "cbuae"),
    *(ExpectedSeed(code, "industry", hint, key) for code in ("SG", "HK") for hint, key in (
        ("FATF plenary outcomes and high-risk jurisdiction lists", "fatf"),
        ("APG mutual evaluation and follow-up reports", "apg"),
        ("Wolfsberg Group publications", "wolfsberg"),
    )),
)


CYBER_EXPECTED = (
    ExpectedSeed("AE", "guideline", "CBUAE Financial Stability Reports on UAE financial-sector cyber risk",
                 "cbuae", CYBER_SOURCE_ROUTES["guideline"][0]),
    ExpectedSeed("AE", "industry", "CBUAE annual reports on cyber threats and financial-sector resilience",
                 "cbuae", CYBER_SOURCE_ROUTES["industry"][0]),
)


@dataclass
class SeedResult:
    sources: int = 0
    expected_sources: int = 0
    source_ids: dict[str, UUID] = field(default_factory=dict)


def seed(conn: psycopg.Connection, workspace_id: UUID, topic: str = "AML/CFT") -> SeedResult:
    """Upsert the allow-list and the expected-source list into ``workspace_id``."""
    result = SeedResult()
    with conn.transaction():
        for source in SOURCES:
            row = conn.execute(
                """insert into public.sources
                     (workspace_id, source_key, name, publisher, source_type, base_url, jurisdiction_code,
                      permitted_operations, access_conditions, connector_config, is_active)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (workspace_id, source_key) do update set
                     name = excluded.name, publisher = excluded.publisher, source_type = excluded.source_type,
                     base_url = excluded.base_url, jurisdiction_code = excluded.jurisdiction_code,
                     permitted_operations = case when excluded.source_key in ('au-register','austrac','cbuae')
                       then public.sources.permitted_operations else excluded.permitted_operations end,
                     access_conditions = excluded.access_conditions, connector_config = excluded.connector_config,
                     is_active = case when excluded.source_key = 'mas' then false else public.sources.is_active end
                   returning id""",
                (workspace_id, source.key, source.name, source.publisher, source.source_type, source.base_url,
                 source.jurisdiction, list(source.operations), source.notes or None, Jsonb(source.connector_config()), source.is_active),
            ).fetchone()
            result.source_ids[source.key] = row["id"]
            result.sources += 1
        for item in (CYBER_EXPECTED if topic == CYBERSECURITY else EXPECTED):
            conn.execute(
                """insert into public.expected_sources
                     (workspace_id, list_version, topic, jurisdiction_code, category, source_id, document_hint, url_hint)
                   values (%s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (workspace_id, topic, jurisdiction_code, list_version, document_hint) do update set
                     category = excluded.category, source_id = excluded.source_id, url_hint = excluded.url_hint,
                     is_active = true""",
                (workspace_id, EXPECTED_LIST_VERSION, topic, item.jurisdiction, item.category,
                 result.source_ids[item.source_key], item.hint, item.url_hint),
            )
            result.expected_sources += 1
    return result
