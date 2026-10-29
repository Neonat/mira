"""HTML report rendered from saved records, without new generation (PRD v2 §9; v1 DB07).

Every sentence links to the passages behind the claims it cites; an inference
links to the passages behind the facts it rests on. Draft reports carry a
watermark and the statements in §7.2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import urlsplit
from uuid import UUID

from mira.contracts import Brief, ReportSnapshot, RunStatus
from mira.store import ExpectedSourceRecord, PassageRecord, StoredClaim

TEMPLATE_VERSION = "report/1"

SECTION_TITLES: dict[str, str] = {
    "executive_summary": "Executive summary",
    "regulatory_developments": "Regulatory developments",
    "deadlines_timeline": "Deadlines and consultation timeline",
    "jurisdiction_comparison": "Jurisdiction comparison",
    "supervisory_trends": "Supervisory trends and focus areas",
    "industry_developments": "Industry developments",
    "impact_assessment": "Impact assessment",
    "what_changed": "What changed since the previous run",
    "coverage_limitations": "Coverage and limitations",
}

STATEMENTS = (
    "Draft for auditor review. Mira summarises public sources only; it does not conclude whether the bank complies with any rule.",
    "Priority means how soon to look at an item, not that a breach exists. An enforcement case against another firm is not a finding about the bank.",
    "Coverage is relative to the named expected-source list, never to every possible source.",
)

STYLE = """
body { font-family: system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1a1a1a; }
.watermark { position: fixed; top: 40%; left: 0; right: 0; text-align: center; font-size: 8rem; opacity: 0.06; transform: rotate(-20deg); pointer-events: none; }
.meta td { padding: 0 1rem 0 0; } .statements { border-left: 3px solid #b45309; padding-left: 1rem; color: #444; }
.tag { font-size: 0.75rem; border: 1px solid #888; border-radius: 3px; padding: 0 0.3rem; margin-left: 0.3rem; }
sup a { text-decoration: none; } .empty { color: #666; font-style: italic; }
table { border-collapse: collapse; } th, td { text-align: left; padding: 0.2rem 0.6rem; border-bottom: 1px solid #ddd; vertical-align: top; }
"""


@dataclass(frozen=True)
class ReportContext:
    brief: Brief
    run_status: RunStatus
    claims: Mapping[UUID, StoredClaim]
    passages: Mapping[UUID, PassageRecord]
    unresolved: Mapping[UUID, str]
    generated_at: datetime
    expected: Mapping[UUID, ExpectedSourceRecord] = field(default_factory=dict)
    # Sign-off record for a reviewed report (PRD v2 §6.6). Required when run_status is "reviewed".
    reviewer: str | None = None
    decided_at: datetime | None = None


def _link(url: str) -> str:
    if urlsplit(url).scheme in ("http", "https"):
        return f'<a href="{escape(url)}" rel="noopener noreferrer">{escape(url)}</a>'
    return escape(url)


def render_html(snapshot: ReportSnapshot, context: ReportContext) -> str:
    numbers: dict[UUID, int] = {}

    def passages_for(finding_id: UUID, seen: set[UUID]) -> list[UUID]:
        if finding_id in seen or finding_id not in context.claims:
            return []
        seen.add(finding_id)
        claim = context.claims[finding_id]
        ids = [item.passage_id for item in claim.evidence]
        for dependency in claim.depends_on:
            ids.extend(passages_for(dependency, seen))
        return ids

    def sentence_html(text: str, finding_ids: list[UUID]) -> str:
        refs: list[int] = []
        for finding_id in finding_ids:
            for passage_id in passages_for(finding_id, set()):
                number = numbers.setdefault(passage_id, len(numbers) + 1)
                if number not in refs:
                    refs.append(number)
        marks = "".join(f'<sup><a href="#e{n}">[{n}]</a></sup>' for n in refs)
        kinds = {context.claims[f].draft.is_inference for f in finding_ids if f in context.claims}
        tag = {frozenset({True}): "inference", frozenset({True, False}): "includes inference"}.get(frozenset(kinds))
        tag = f'<span class="tag">{tag}</span>' if tag else ""
        return f"<p>{escape(text)}{marks}{tag}</p>"

    brief = context.brief
    if context.run_status == "reviewed" and (context.reviewer is None or context.decided_at is None):
        # A reviewed label without a named reviewer and decision date would be a claim nobody made.
        raise ValueError("a reviewed report must name the reviewer and the decision date")
    label = {"partial": "Draft (partial run), not reviewed", "reviewed": "Reviewed"}.get(
        context.run_status, "Draft, not reviewed"
    )
    signoff = (
        f"<tr><td>Reviewed by</td><td>{escape(context.reviewer)}</td></tr>"
        f"<tr><td>Decision date</td><td>{context.decided_at.date().isoformat()}</td></tr>"
        if context.run_status == "reviewed" else ""
    )
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{escape(brief.topic)} report: {escape(', '.join(brief.jurisdictions))}</title>",
        f"<style>{STYLE}</style></head><body>",
    ]
    if context.run_status != "reviewed":
        parts.append('<div class="watermark">DRAFT</div>')
    parts += [
        f"<h1>{escape(brief.topic)} developments: {escape(', '.join(brief.jurisdictions))}</h1>",
        '<table class="meta">',
        f"<tr><td>Status</td><td>{label}</td></tr>",
        signoff,
        f"<tr><td>Period</td><td>{brief.period_start.isoformat()} to {brief.period_end.isoformat()}</td></tr>",
        f"<tr><td>As of</td><td>{brief.as_of_date.isoformat()}</td></tr>",
        f"<tr><td>Run</td><td>{snapshot.analysis_run_id}</td></tr>",
        f"<tr><td>Generated</td><td>{context.generated_at.isoformat(timespec='seconds')}</td></tr>",
        "</table>",
        '<div class="statements">' + "".join(f"<p>{escape(text)}</p>" for text in STATEMENTS) + "</div>",
    ]

    sections = {section.section: section for section in snapshot.sections}
    for key, title in SECTION_TITLES.items():
        section = sections.get(key)
        if section is None:
            continue
        parts.append(f"<h2>{escape(title)}</h2>")
        if section.no_verified_items and not section.sentences:
            parts.append('<p class="empty">No verified items.</p>')
        parts += [sentence_html(sentence.text, sentence.finding_ids) for sentence in section.sentences]
        if key == "coverage_limitations" and snapshot.coverage:
            parts.append("<h3>Expected sources</h3><table><tr><th>Jurisdiction</th><th>Expected item</th>"
                         "<th>Status</th><th>Note</th></tr>")
            for row in snapshot.coverage:
                item = context.expected.get(row.expected_source_id)
                parts.append(
                    f"<tr><td>{escape(item.jurisdiction_code if item else '')}</td>"
                    f"<td>{escape(item.document_hint if item else str(row.expected_source_id))}</td>"
                    f"<td>{escape(row.status.replace('_', ' '))}</td><td>{escape(row.note or '')}</td></tr>"
                )
            parts.append("</table>")
        if key == "coverage_limitations" and context.unresolved:
            parts.append("<h3>Unresolved items (not in the report body)</h3><ul>")
            for finding_id, reason in context.unresolved.items():
                claim = context.claims.get(finding_id)
                title = claim.draft.title if claim else str(finding_id)
                parts.append(f"<li>{escape(title)}: {escape(reason)}</li>")
            parts.append("</ul>")

    parts.append("<h2>Evidence appendix</h2><ol>")
    for passage_id, number in sorted(numbers.items(), key=lambda item: item[1]):
        passage = context.passages.get(passage_id)
        if passage is None:
            parts.append(f'<li id="e{number}">Passage {passage_id} (not loaded)</li>')
            continue
        published = passage.published_at.isoformat() if passage.published_at else "date unknown"
        parts.append(
            f'<li id="e{number}" value="{number}">{escape(passage.source_name)}, '
            f"<em>{escape(passage.title)}</em> ({published}). {_link(passage.source_url)}. "
            f"Passage {passage.passage_number}, document version {passage.document_version_id}."
            f"{' Imported by hand from a downloaded copy.' if passage.imported else ''}</li>"
        )
    parts.append("</ol></body></html>")
    return "\n".join(part for part in parts if part)
