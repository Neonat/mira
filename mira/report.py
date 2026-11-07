"""HTML report rendered from saved records, without new generation (PRD v2 §9; v1 DB07).

Every sentence links to the passages behind the claims it cites; an inference
links to the passages behind the facts it rests on. The header shows the
review status and scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from html import escape
from urllib.parse import urlsplit
from uuid import UUID

from mira.contracts import Brief, ReportSentence, ReportSnapshot, RunStatus
from mira.coverage_display import CHECKLIST_DESCRIPTION, coverage_label
from mira.store import ExpectedSourceRecord, PassageRecord, StoredClaim

TEMPLATE_VERSION = "report/3"

MARKET_NAMES = {"SG": "Singapore", "HK": "Hong Kong"}
DATE_LABELS = {
    "published": "Published", "effective": "Effective", "deadline": "Deadline",
    "consultation_close": "Consultation closes", "event": "Event date",
}

SECTION_TITLES: dict[str, str] = {
    "executive_summary": "Executive summary",
    "regulatory_developments": "Regulatory developments",
    "deadlines_timeline": "Deadlines and consultation timeline",
    "jurisdiction_comparison": "Jurisdiction comparison",
    "supervisory_trends": "Supervisory trends and focus areas",
    "industry_developments": "Industry developments",
    "impact_assessment": "Risk and applicability insights",
    "what_changed": "What changed since the previous run",
    "coverage_limitations": "Coverage and limitations",
}

SCOPE = (
    "Mira reports public developments and evidence-based insights. "
    "The auditor determines DBS compliance, the implications for DBS, and any action to take."
)

STYLE = """
body { font-family: system-ui, sans-serif; max-width: 54rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.55; color: #202830; overflow-wrap: anywhere; }
h1, h2, h3, h4 { line-height: 1.2; color: #153448; }
h1 { font-size: clamp(1.7rem, 5vw, 2.45rem); margin: .5rem 0 1rem; }
h2 { margin: 2rem 0 .75rem; padding-top: .85rem; border-top: 2px solid #cad9e2; }
h3 { margin: 1.3rem 0 .65rem; }
.watermark { display: inline-block; color: #713d10; background: #fff2d9; font-size: .78rem; font-weight: 700; letter-spacing: .08em; padding: .2rem .55rem; }
.meta td:first-child { font-weight: 650; white-space: nowrap; }
.statements { border-left: 3px solid #648295; padding-left: .8rem; color: #394b57; }
.finding { padding: .9rem 0; border-bottom: 1px solid #dbe4ea; }
.finding h3, .finding h4, .finding p { margin: .4rem 0; }
.finding h3, .finding h4 { font-size: 1.08rem; }
.number { color: #466071; }
.tag { display: inline-block; background: #e9f0f5; color: #18394e; font-size: .78rem; font-weight: 650; border-radius: 3px; padding: .08rem .4rem; }
.date { margin-left: .55rem; font-size: .85rem; color: #394b57; }
.evidence { font-size: .87rem; }
.prose, .summary { max-width: 74ch; }
.summary { padding-left: 1.35rem; }
.summary li { margin-bottom: .6rem; }
sup { margin-left: .18rem; }
a { color: #135782; text-underline-offset: .15em; }
.empty { color: #52616b; font-style: italic; }
table { border-collapse: collapse; } th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #dbe4ea; vertical-align: top; }
th { background: #edf3f7; }
.coverage th:first-child { white-space: nowrap; }
@media screen and (max-width: 36rem) {
  .coverage, .coverage tbody { display: block; }
  .coverage thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .coverage tbody tr { display: grid; grid-template-columns: 3rem 1fr; padding: .65rem 0; border-bottom: 1px solid #dbe4ea; }
  .coverage td { border: 0; padding: .12rem 0; }
  .coverage td:nth-child(2) { font-weight: 650; }
  .coverage td:nth-child(n+3) { grid-column: 2; font-size: .9rem; }
  .coverage td:nth-child(3) { color: #395568; font-weight: 650; }
}
@media print {
  body { margin: 0; padding: 0; font-size: 10pt; }
  h2 { margin-top: 1.2rem; }
  .prose { text-align: justify; hyphens: auto; }
  h2, h3, h4, thead { break-after: avoid; }
  tr { break-inside: avoid; }
}
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


def _link(url: str, label: str) -> str:
    if urlsplit(url).scheme in ("http", "https"):
        return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'
    return escape(label)


def _date_html(kind: str | None, day: date) -> str:
    label = DATE_LABELS.get(kind or "", "Key date")
    return f'<span class="date">{label} <time datetime="{day.isoformat()}">{day.day} {day:%b %Y}</time></span>'


def render_html(snapshot: ReportSnapshot, context: ReportContext) -> str:
    numbers: dict[UUID, int] = {}
    anchored_findings: set[UUID] = set()
    main_finding_ids = {
        sentence.finding_ids[0]
        for section in snapshot.sections
        if section.section not in ("executive_summary", "deadlines_timeline", "what_changed", "coverage_limitations")
        for sentence in section.sentences
        if len(sentence.finding_ids) == 1
    }

    def passages_for(finding_id: UUID, seen: set[UUID]) -> list[UUID]:
        if finding_id in seen or finding_id not in context.claims:
            return []
        seen.add(finding_id)
        claim = context.claims[finding_id]
        ids = [item.passage_id for item in claim.evidence]
        for dependency in claim.depends_on:
            ids.extend(passages_for(dependency, seen))
        return ids

    def sentence_html(
        text: str, finding_ids: list[UUID], index: int | None = None, *, grouped: bool = False, main: bool = False
    ) -> str:
        refs: list[int] = []
        documents: dict[UUID, PassageRecord] = {}
        for finding_id in finding_ids:
            for passage_id in passages_for(finding_id, set()):
                number = numbers.setdefault(passage_id, len(numbers) + 1)
                if number not in refs:
                    refs.append(number)
                passage = context.passages.get(passage_id)
                if passage is not None:
                    documents.setdefault(passage.document_id, passage)
        marks = "".join(f'<sup><a href="#e{n}">[{n}]</a></sup>' for n in refs)
        drafts = [context.claims[f].draft for f in finding_ids if f in context.claims]
        kinds = frozenset(draft.is_inference for draft in drafts)
        tag = {
            frozenset({False}): "Fact", frozenset({True}): "Inference",
            frozenset({True, False}): "Facts and inferences",
        }.get(kinds)
        tag = f'<span class="tag">{tag}</span>' if tag else ""
        if any(snapshot.review_outcomes.get(f) and snapshot.review_outcomes[f].decision == "amended"
               for f in finding_ids):
            tag += '<span class="tag">Reviewer amendment</span>'
        if index is None:
            return f"{tag} {escape(text)}{marks}".lstrip()
        title = drafts[0].title if len(drafts) == 1 else "Related findings"
        dates = dict.fromkeys((draft.key_date_kind, draft.key_date) for draft in drafts if draft.key_date)
        date_html = "".join(_date_html(kind, day) for kind, day in dates)
        links = " · ".join(_link(p.source_url, f"{p.source_name} — {p.title}") for p in documents.values())
        evidence = f'<p class="evidence"><strong>Sources</strong> {links}{marks}</p>' if links or marks else ""
        heading = "h4" if grouped else "h3"
        anchor = ""
        if main and len(finding_ids) == 1 and finding_ids[0] not in anchored_findings:
            anchored_findings.add(finding_ids[0])
            anchor = f' id="finding-{finding_ids[0]}"'
        return (
            f'<article class="finding"{anchor}>{tag}{date_html}'
            f'<{heading}><span class="number">{index}.</span> {escape(title)}</{heading}>'
            f'<p class="prose">{escape(text)}</p>{evidence}</article>'
        )

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
    markets = ", ".join(MARKET_NAMES.get(code, code) for code in brief.jurisdictions)
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(brief.topic)} report: {escape(markets)}</title>",
        f"<style>{STYLE}</style></head><body>",
    ]
    if context.run_status != "reviewed":
        parts.append('<div class="watermark">DRAFT</div>')
    parts += [
        f"<h1>{escape(brief.topic)} developments in {escape(markets)}</h1>",
        '<table class="meta">',
        f"<tr><td>Status</td><td>{label}</td></tr>",
        signoff,
        f"<tr><td>Period</td><td>{brief.period_start.isoformat()} to {brief.period_end.isoformat()}</td></tr>",
        f"<tr><td>As of</td><td>{brief.as_of_date.isoformat()}</td></tr>",
        f"<tr><td>Run</td><td>{snapshot.analysis_run_id}</td></tr>",
        f"<tr><td>Generated</td><td>{context.generated_at.isoformat(timespec='seconds')}</td></tr>",
        "</table>",
        f'<p class="statements">{escape(SCOPE)}</p>',
    ]

    sections = {section.section: section for section in snapshot.sections}
    index = 0
    for key, title in SECTION_TITLES.items():
        section = sections.get(key)
        if section is None:
            continue
        parts.append(f"<h2>{escape(title)}</h2>")
        if section.no_verified_items and not section.sentences:
            parts.append('<p class="empty">No verified items.</p>')
        if key == "executive_summary" and any(sentence.finding_ids for sentence in section.sentences):
            parts.append('<ul class="summary">')
            parts += [f"<li>{sentence_html(sentence.text, sentence.finding_ids)}</li>" for sentence in section.sentences]
            parts.append("</ul>")
        else:
            group_by_market = len(brief.jurisdictions) > 1 and key not in (
                "jurisdiction_comparison", "deadlines_timeline", "what_changed", "coverage_limitations",
            )
            groups: dict[str | None, list[ReportSentence]] = {None: section.sentences}
            if group_by_market:
                groups = {}
                for sentence in section.sentences:
                    jurisdictions = {
                        context.claims[f].draft.jurisdiction_code for f in sentence.finding_ids if f in context.claims
                    }
                    market = next(iter(jurisdictions)) if len(jurisdictions) == 1 else None
                    groups.setdefault(market, []).append(sentence)
            for market, sentences in groups.items():
                if group_by_market:
                    parts.append(f"<h3>{escape(MARKET_NAMES.get(market, market) if market else 'Shared or regional')}</h3>")
                for sentence in sentences:
                    if key == "deadlines_timeline" and len(sentence.finding_ids) == 1:
                        finding_id = sentence.finding_ids[0]
                        claim = context.claims.get(finding_id)
                        if (finding_id in main_finding_ids and claim and claim.draft.key_date
                                and sentence.text == claim.draft.content):
                            draft = claim.draft
                            parts.append(
                                f'<p>{_date_html(draft.key_date_kind, draft.key_date)} '
                                f'<a href="#finding-{finding_id}">{escape(draft.title)}</a></p>'
                            )
                            continue
                    if sentence.finding_ids and key != "what_changed":
                        index += 1
                        parts.append(sentence_html(
                            sentence.text, sentence.finding_ids, index, grouped=group_by_market,
                            main=key != "deadlines_timeline",
                        ))
                    else:
                        parts.append(f"<p>{sentence_html(sentence.text, sentence.finding_ids)}</p>")
        if key == "coverage_limitations" and snapshot.coverage:
            parts.append(f"<h3>Source coverage checklist</h3><p>{CHECKLIST_DESCRIPTION}</p>"
                         '<table class="coverage" role="table"><thead><tr><th scope="col">Market</th>'
                         '<th scope="col">Checklist item</th><th scope="col">Outcome</th>'
                         '<th scope="col">Detail</th></tr></thead><tbody role="rowgroup">')
            for row in snapshot.coverage:
                item = context.expected.get(row.expected_source_id)
                parts.append(
                    f'<tr role="row"><td role="cell">{escape(item.jurisdiction_code if item else "")}</td>'
                    f'<td role="cell">{escape(item.document_hint if item else str(row.expected_source_id))}</td>'
                    f'<td role="cell">{escape(coverage_label(row.status, row.note))}</td>'
                    f'<td role="cell">{escape(row.note or "")}</td></tr>'
                )
            parts.append("</tbody></table>")
        if key == "coverage_limitations" and context.unresolved:
            parts.append("<h3>Unresolved items (not in the report body)</h3><ul>")
            for finding_id, reason in context.unresolved.items():
                claim = context.claims.get(finding_id)
                title = claim.draft.title if claim else str(finding_id)
                if claim and claim.draft.finding_type == "audit_question":
                    title = "Audit action excluded"
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
            f"<em>{escape(passage.title)}</em> ({published}). {_link(passage.source_url, passage.source_url)}. "
            f"Passage {passage.passage_number}, document version {passage.document_version_id}."
            f"{' Imported by hand from a downloaded copy.' if passage.imported else ''}</li>"
        )
    parts.append("</ol></body></html>")
    return "\n".join(part for part in parts if part)
