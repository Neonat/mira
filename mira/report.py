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

TEMPLATE_VERSION = "report/4"

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
p, .summary li, .unresolved li { text-align: justify; text-justify: inter-word; hyphens: auto; }
.evidence, .back, .empty { text-align: left; }
.contents { margin: 1.5rem 0; padding: 1rem 1.2rem; background: #f2f6f8; border: 1px solid #cad9e2; border-radius: .35rem; }
.contents h2 { border: 0; padding: 0; margin: 0 0 .7rem; font-size: 1.15rem; }
.contents ol { list-style: none; padding: 0; margin: 0; columns: 2; column-gap: 2rem; }
.contents li { break-inside: avoid; margin: .4rem 0; }
.contents a { display: block; padding: .15rem 0; }
.overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: .75rem; margin: 1.4rem 0; }
.overview div { border-top: 3px solid #648295; padding: .65rem .8rem; background: #f2f6f8; }
.overview dt { font-size: .82rem; color: #466071; }
.overview dd { font-size: 1.65rem; font-weight: 650; margin: .1rem 0 0; }
.paragraph-number { display: inline-block; margin-right: .55rem; font-size: .85rem; font-weight: 650; font-variant-numeric: tabular-nums; text-decoration: none; }
[id] { scroll-margin-top: 1.2rem; }
:target { outline: 2px solid #648295; outline-offset: .35rem; }
a:focus-visible { outline: 2px solid #135782; outline-offset: 3px; }
.back { font-size: .8rem; margin: 1rem 0; }
.table-scroll { overflow-x: auto; }
.timeline { width: 100%; font-size: .92rem; }
.timeline .date { margin: 0; }
.timeline th:first-child, .timeline td:first-child { min-width: 8rem; }
.timeline th:last-child, .timeline td:last-child { white-space: nowrap; }
.timeline td:nth-child(2) { min-width: 11rem; }
.outcome { display: inline-block; font-weight: 650; padding: .1rem .4rem; border-radius: .2rem; background: #edf3f7; }
.outcome-found { background: #e7f2ed; color: #24543e; }
.outcome-missing, .outcome-fetch_failed, .outcome-out_of_budget { background: #fff2d9; color: #713d10; }
.summary { padding-left: 1.35rem; }
.summary li { margin-bottom: .6rem; }
sup { margin-left: .18rem; }
a { color: #135782; text-underline-offset: .15em; }
.empty { color: #52616b; font-style: italic; }
table { border-collapse: collapse; } th, td { text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #dbe4ea; vertical-align: top; }
th { background: #edf3f7; }
.coverage th:first-child { white-space: nowrap; }
@media screen and (max-width: 36rem) {
  .contents ol { columns: 1; }
  .overview { grid-template-columns: repeat(2, 1fr); }
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
  .contents, .overview, .finding { break-inside: avoid; }
  .table-scroll { overflow: visible; }
  .back { display: none; }
  .timeline th:first-child, .timeline td:first-child, .timeline td:nth-child(2) { min-width: 0; }
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
        text: str, finding_ids: list[UUID], index: int | None = None, *, grouped: bool = False, main: bool = False,
        paragraph: str = ""
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
            f'<p class="prose"{paragraph_anchor(paragraph)}>{paragraph_link(paragraph)}{escape(text)}</p>{evidence}</article>'
        )

    def paragraph_anchor(reference: str) -> str:
        return f' id="paragraph-{reference.replace(".", "-")}"' if reference else ""

    def paragraph_link(reference: str) -> str:
        return (f'<a class="paragraph-number" href="#paragraph-{reference.replace(".", "-")}" '
                f'aria-label="Paragraph {reference}">{reference}</a>') if reference else ""

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
    section_numbers = {key: number for number, key in enumerate(
        (key for key in SECTION_TITLES if key in sections), start=1)}
    appendix_number = len(section_numbers) + 1
    cited_ids = {fid for section in snapshot.sections for sentence in section.sentences
                 for fid in sentence.finding_ids if fid in context.claims}
    cited_passages = {pid for fid in cited_ids for pid in passages_for(fid, set())}
    source_urls = {context.passages[pid].source_url for pid in cited_passages if pid in context.passages}
    overview = {
        "Facts": sum(not context.claims[fid].draft.is_inference for fid in cited_ids),
        "Inferences": sum(context.claims[fid].draft.is_inference for fid in cited_ids),
        "Unresolved": len(snapshot.unresolved_finding_ids),
        "Cited sources": len(source_urls),
    }
    parts.append('<dl class="overview" aria-label="Report overview">' + "".join(
        f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in overview.items()) + '</dl>')
    parts.append('<nav class="contents" id="contents" aria-label="Table of contents">'
                 '<h2>Table of contents</h2><ol>')
    for key, number in section_numbers.items():
        parts.append(f'<li><a href="#section-{key}">{number}. {escape(SECTION_TITLES[key])}</a></li>')
        if key == "coverage_limitations":
            if snapshot.coverage:
                parts.append('<li><a href="#source-coverage">Source coverage checklist</a></li>')
            if context.unresolved:
                parts.append('<li><a href="#unresolved-items">Unresolved items</a></li>')
    parts.append(f'<li><a href="#section-evidence">{appendix_number}. Evidence appendix</a></li></ol></nav>')
    index = 0
    for key, title in SECTION_TITLES.items():
        section = sections.get(key)
        if section is None:
            continue
        section_number = section_numbers[key]
        paragraph_index = 0

        def next_paragraph() -> str:
            nonlocal paragraph_index
            paragraph_index += 1
            return f"{section_number}.{paragraph_index}"

        parts.append(f'<section aria-labelledby="section-{key}">'
                     f'<h2 id="section-{key}">{section_number}. {escape(title)}</h2>')
        if section.no_verified_items and not section.sentences:
            parts.append('<p class="empty">No verified items.</p>')
        if key == "executive_summary" and any(sentence.finding_ids for sentence in section.sentences):
            parts.append('<ul class="summary">')
            for sentence in section.sentences:
                reference = next_paragraph()
                parts.append(f'<li{paragraph_anchor(reference)}>{paragraph_link(reference)}'
                             f'{sentence_html(sentence.text, sentence.finding_ids)}</li>')
            parts.append("</ul>")
        else:
            sentences_to_render = section.sentences
            if key == "deadlines_timeline":
                dated = []
                remaining = []
                for sentence in section.sentences:
                    finding_id = sentence.finding_ids[0] if len(sentence.finding_ids) == 1 else None
                    claim = context.claims.get(finding_id)
                    if claim and claim.draft.key_date:
                        dated.append((claim.draft.key_date, sentence, claim))
                    else:
                        remaining.append(sentence)
                if dated:
                    parts.append('<div class="table-scroll" tabindex="0" role="region" '
                                 'aria-label="Dated developments"><table class="timeline">'
                                 '<thead><tr><th scope="col">Date</th><th scope="col">Development</th>'
                                 '<th scope="col">Publisher</th><th scope="col">Reference</th>'
                                 '</tr></thead><tbody>')
                    for _, sentence, claim in sorted(dated, key=lambda row: row[0]):
                        reference = next_paragraph()
                        publishers = sorted({context.passages[pid].source_name
                                             for pid in passages_for(claim.finding_id, set())
                                             if pid in context.passages})
                        if claim.finding_id in main_finding_ids and sentence.text == claim.draft.content:
                            development = f'<a href="#finding-{claim.finding_id}">{escape(claim.draft.title)}</a>'
                        else:
                            index += 1
                            development = sentence_html(sentence.text, sentence.finding_ids, index)
                        parts.append(f'<tr{paragraph_anchor(reference)}><td>'
                                     f'{_date_html(claim.draft.key_date_kind, claim.draft.key_date)}</td>'
                                     f'<td>{development}</td>'
                                     f'<td>{escape(", ".join(publishers))}</td>'
                                     f'<td>{paragraph_link(reference)}</td></tr>')
                    parts.append('</tbody></table></div>')
                sentences_to_render = remaining
            group_by_market = len(brief.jurisdictions) > 1 and key not in (
                "jurisdiction_comparison", "deadlines_timeline", "what_changed", "coverage_limitations",
            )
            groups: dict[str | None, list[ReportSentence]] = {None: sentences_to_render}
            if group_by_market:
                groups = {}
                for sentence in sentences_to_render:
                    jurisdictions = {
                        context.claims[f].draft.jurisdiction_code for f in sentence.finding_ids if f in context.claims
                    }
                    market = next(iter(jurisdictions)) if len(jurisdictions) == 1 else None
                    groups.setdefault(market, []).append(sentence)
            for market, sentences in groups.items():
                if group_by_market:
                    parts.append(f"<h3>{escape(MARKET_NAMES.get(market, market) if market else 'Shared or regional')}</h3>")
                for sentence in sentences:
                    reference = next_paragraph()
                    if sentence.finding_ids and key != "what_changed":
                        index += 1
                        parts.append(sentence_html(
                            sentence.text, sentence.finding_ids, index, grouped=group_by_market,
                            main=key != "deadlines_timeline", paragraph=reference,
                        ))
                    else:
                        parts.append(f'<p{paragraph_anchor(reference)}>{paragraph_link(reference)}'
                                     f'{sentence_html(sentence.text, sentence.finding_ids)}</p>')
        if key == "coverage_limitations" and snapshot.coverage:
            parts.append(f'<h3 id="source-coverage">Source coverage checklist</h3><p>{CHECKLIST_DESCRIPTION}</p>'
                         '<table class="coverage" role="table"><thead><tr><th scope="col">Market</th>'
                         '<th scope="col">Checklist item</th><th scope="col">Outcome</th>'
                         '<th scope="col">Detail</th></tr></thead><tbody role="rowgroup">')
            for row in snapshot.coverage:
                item = context.expected.get(row.expected_source_id)
                parts.append(
                    f'<tr role="row"><td role="cell">{escape(item.jurisdiction_code if item else "")}</td>'
                    f'<td role="cell">{escape(item.document_hint if item else str(row.expected_source_id))}</td>'
                    f'<td role="cell"><span class="outcome outcome-{row.status}">{escape(coverage_label(row.status, row.note))}</span></td>'
                    f'<td role="cell">{escape(row.note or "")}</td></tr>'
                )
            parts.append("</tbody></table>")
        if key == "coverage_limitations" and context.unresolved:
            parts.append('<h3 id="unresolved-items">Unresolved items (not in the report body)</h3><ul class="unresolved">')
            for finding_id, reason in context.unresolved.items():
                claim = context.claims.get(finding_id)
                title = claim.draft.title if claim else str(finding_id)
                if claim and claim.draft.finding_type == "audit_question":
                    title = "Audit action excluded"
                reference = next_paragraph()
                parts.append(f'<li{paragraph_anchor(reference)}>{paragraph_link(reference)}{escape(title)}: {escape(reason)}</li>')
            parts.append("</ul>")

        parts.append('<p class="back"><a href="#contents">Back to contents</a></p></section>')

    parts.append(f'<section aria-labelledby="section-evidence"><h2 id="section-evidence">'
                 f'{appendix_number}. Evidence appendix</h2><ol>')
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
    parts.append('</ol><p class="back"><a href="#contents">Back to contents</a></p></section></body></html>')
    return "\n".join(part for part in parts if part)
