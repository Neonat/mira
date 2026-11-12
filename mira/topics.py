"""Controlled topic scope and search vocabulary."""

CYBERSECURITY = "Cybersecurity"
CYBER_SOURCE_KEY = "cbuae"
CYBER_SOURCE_HOST = "centralbank.ae"
CYBER_SOURCE_ROUTES = {
    "guideline": ("https://centralbank.ae/en/our-operations/financial-stability/",),
    "industry": ("https://centralbank.ae/en/news-and-publications/publications/",),
}
CYBER_TERMS = "phishing impersonation ransomware malware DDoS disruption third-party supply chain"
AML_TERMS = "money laundering terrorism financing AML CFT"
CYBER_FOCUS = (
    "Cover publicly documented threats affecting UAE financial institutions. Focus on phishing and "
    "impersonation, ransomware and malware, denial of service or cyber-related disruption, and "
    "third-party or supply-chain compromise. Keep warnings, exercises, aggregate observations and "
    "actual incidents distinct. Attribute sector-wide observations to the source. Separate the "
    "observation year from publication. A later report may support a retrospective observation "
    "only when the quoted evidence explicitly ties it to the period. If the source supplies only "
    "a year, state that year in the finding and leave the exact date empty. Describe recurring threats as observations unless the source establishes a change."
)
