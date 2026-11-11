"""Read-only country observations from an explicit portable evidence allowlist.

These engineering observations are independent of any signed-in workspace. They
neither enable sources nor supply research inputs; no source bodies are returned.
"""
from __future__ import annotations

import json
from pathlib import Path

_EVIDENCE = Path(__file__).resolve().parents[1] / "eval" / "evidence"
_PILOT = "2026-11-10-country-method-pilot"
_ARCHIVE = "2026-11-10-archive-hybrid-validation"
_RESEARCH = "2026-11-10-au-ae-uninterrupted-validation"
_HK = "2026-11-08-hk-authorized-followup-7be59cdf"
_NAMES = {"HK": "Hong Kong", "AU": "Australia", "AE": "UAE federal", "SG": "Singapore", "MY": "Malaysia", "DFSA": "DIFC / DFSA"}
_STORAGE = (
    "PostgreSQL holds complete permitted extracted evidence, native records, passages and provenance. "
    "pgvector is an optional experimental derivative ranking index, never a replacement for evidence "
    "or a proven storage-engine winner. Original-byte storage requires separate permission. "
    "Storage-size and cost comparisons were not tested."
)


def _load(name: str) -> dict:
    # Only module-selected constants reach this function; callers supply no paths.
    return json.loads((_EVIDENCE / f"{name}.json").read_text(encoding="utf-8"))


def _row(method: str, status: str, observation: str, **metrics) -> dict:
    return {"method": method, "status": status, "observation": observation, **metrics}


def _reference(name: str, label: str) -> dict:
    return {"label": label, "path": f"eval/evidence/{name}.json"}


def country_method_results(country: str) -> dict:
    """Return fresh, curated observations for one exact supported country code.

    Unknown codes raise ValueError before file access. Missing/malformed approved
    evidence raises normally rather than substituting fabricated measurements.
    """
    if not isinstance(country, str) or country not in _NAMES:
        raise ValueError("Unsupported country code")
    result = {
        "country_code": country, "country_name": _NAMES[country],
        "recommendation": "", "storage": _STORAGE,
        "acquisition": [], "archive": [],
        "research": {"kind": "not_tested", "scope": "No research measurement in these approved artifacts."},
        "quality_winner": None, "cost_comparison": None, "storage_size_comparison": None,
        "references": [],
    }
    if country == "HK":
        archive = _load(_ARCHIVE)
        saved = archive["live_result"]["saved"]
        latency = archive["latency_summary"]
        current = _load(_HK)["current"]
        result["recommendation"] = "Use approved source-specific direct acquisition and keyword search; hybrid remains optional and experimental. No quality winner established."
        result["acquisition"] = [
            _row("official_api", "not_tested", "No controlled official-API comparison in these HK artifacts."),
            _row("direct_publication", "measured", "Historical live acquisition benchmark; acquisition recall is distinct from report citation recall.", acquired_benchmark=current["acquired"]["recall"]["all"]),
            _row("exa", "measured", "URL discovery completed; no Exa-versus-no-Exa quality ablation."),
            _row("browser", "not_tested", "Enabled but never attempted in the historical live run; no browser quality comparison."),
        ]
        shared = {"eligible_passages": saved["eligible"], "indexed_passages": saved["indexed"], "questions": latency["sample_queries"]}
        result["archive"] = [
            _row("keyword", "measured", "Same saved HK corpus and six unlabelled questions, equal top10 output budget; warm median latency. No relevance winner.", latency_seconds=latency["saved_lexical_median_seconds"], **shared),
            _row("hybrid", "measured", "Experimental ranking on the same saved corpus and six unlabelled questions. Median includes query embedding HTTP; cold indexing is additional. Equal output budgets, not equal compute; no quality winner.", latency_seconds=latency["saved_hybrid_median_seconds"], **shared),
        ]
        brief = current["brief"]
        result["research"] = {
            "kind": "historical_partial_live_report", "run_id": current["run_id"],
            "scope": f"HK AML/CFT {brief['period_start']} through {brief['period_end']}, as of {brief['as_of_date']}. Partial verified-claim fallback after writer timeout; separate from the one-fact synthetic demo. Model verification is not human precision labelling; not a controlled method comparison.",
            "verified_facts": current["report_facts"],
            "acquired_benchmark": current["acquired"]["recall"]["all"],
            "cited_benchmark": current["cited"]["recall"]["all"],
        }
        result["references"] = [_reference(_ARCHIVE, "Saved HK archive comparison — 10 Nov 2026"), _reference(_HK, "Historical HK partial live run — 8 Nov 2026")]
    elif country in {"AU", "AE"}:
        pilot = _load(_PILOT)
        research = _load(_RESEARCH)
        acquisitions = {a["id"]: a for a in pilot["acquisitions"]}
        summary = pilot["descriptive_summary"]
        result["references"] = [_reference(_PILOT, "Bounded source-method pilot — 10 Nov 2026"), _reference(_RESEARCH, "AU/UAE partial live validation — 10 Nov 2026")]
        verified = sum(c["n"] for c in research["verified_counts"] if c["jurisdiction_code"] == country and not c["is_inference"])
        result["research"] = {
            "kind": "partial_live_fallback_report", "run_id": research["run_id"],
            "scope": "AU and UAE federal AML/CFT, 10 Nov 2025 through 10 Nov 2026, as of 10 Nov 2026. Eight-representation capacity cap; corpora differ from prior run. Partial fallback, failed/deferred analysis, inconclusive corroboration; no independent support or human precision labels. No national publication-recall denominator.",
            "verified_facts": verified,
        }
        if country == "AU":
            result["recommendation"] = "Prefer Federal Register API identity/version discovery and complete direct publication HTML/PDF. AUSTRAC remains subject to live access checks. Hybrid is experimental; no quality winner established."
            result["acquisition"] = [
                _row("official_api", "measured", "Structured Federal Register title metadata acquired; identity/version discovery is separate from publication acquisition."),
                _row("direct_publication", "measured", "July 2026 compilation HTML/PDF representation comparison: sampled HTML prefixes found in full PDF; not a national coverage or universal accuracy score.", sample_prefix_hits=summary["anchor_pdf_hits"], sample_prefix_total=20, pages=acquisitions["au-act-pdf"]["pages"]),
                _row("exa", "measured", "URL/title discovery exposed another compilation; availability and version dates still require validation."),
                _row("browser", "measured", "Landing DOM representation contained none of the sampled HTML prefixes; this is a representation comparison, not universal browser accuracy.", sample_prefix_hits=summary["anchor_browser_hits"], sample_prefix_total=20),
                _row("austrac", "recommended", "Check current source access before acquisition; the pilot robots request timed out and acquired no AUSTRAC publication."),
            ]
            shared = {"sample_passages": pilot["comparison"]["sample"]["selected_passages"], "questions": summary["frozen_questions"]}
            result["archive"] = [
                _row("keyword", "measured", "Same deterministic 30-passage Australian sample and top10; six unlabelled questions. Temporary-table median, not production latency.", latency_seconds=summary["lexical_median_seconds"], **shared),
                _row("hybrid", "measured", "Experimental same-sample ranking; six unlabelled questions, no quality winner. Median includes embedding API and excludes cold indexing.", latency_seconds=summary["hybrid_median_seconds_including_api"], **shared),
            ]
        else:
            result["recommendation"] = "Prefer the tested approved CBUAE federal hub and direct PDF route. External embedding is not granted; DIFC/DFSA is a separate disabled scope."
            result["acquisition"] = [
                _row("official_api", "not_tested", "No federal API acquisition comparison in this pilot."),
                _row("direct_publication", "measured", "Approved CBUAE federal hub linked to an acquired complete sanctions-review PDF; this source sample does not establish country coverage.", pages=acquisitions["ae-sanctions-pdf"]["pages"]),
                _row("exa", "measured", "Discovery returned rulebook subdomain URLs outside the exact pilot acquisition grant; none followed."),
                _row("browser", "measured", "Tested hub browser capture encountered an access challenge; do not bypass it."),
            ]
            result["archive"] = [
                _row("keyword", "recommended", "Search permitted retained federal text; no controlled UAE ranking-quality measurement."),
                _row("hybrid", "blocked", "External embedding not granted for CBUAE material; zero UAE vectors in the live validation."),
            ]
    else:
        result["references"] = [_reference(_PILOT, "Source-level permissions and MAS exclusion — 10 Nov 2026")]
        if country == "SG":
            result["recommendation"] = "MAS automation remains disabled. Assess other Singapore sources individually under existing grants; this is not a country-wide block."
            result["acquisition"] = [_row("mas", "blocked", "MAS automation excluded; controls and BYOK cannot enable it."), _row("other_sources", "not_tested", "Other Singapore sources require individual permission and method checks.")]
            result["archive"] = [_row("keyword", "not_tested", "No Singapore archive comparison in these artifacts."), _row("hybrid", "not_tested", "Experimental only where separately permitted; no Singapore quality comparison.")]
        else:
            result["recommendation"] = "Disabled pending source permission; no UI control or BYOK changes the restriction."
            reason = ("Malaysia: BNM hosts disallow ExaBot and reuse is restricted; Securities Commission retrieval-system storage needs written permission." if country == "MY" else "DIFC/DFSA electronic retrieval-system storage requires prior permission; manual import does not remove the restriction.")
            result["acquisition"] = [_row(method, "blocked", reason) for method in ("official_api", "direct_publication", "exa", "browser")]
            result["archive"] = [_row(method, "blocked", reason) for method in ("keyword", "hybrid")]
    return result
