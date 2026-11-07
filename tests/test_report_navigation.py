"""Auditors can navigate and reference the rendered report without changing its evidence."""
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from uuid import uuid4

from mira.contracts import ReportSection, ReportSentence
from mira.report import ReportContext, render_html
from mira.store import StoredClaim
from test_render import AT, BRIEF, fixture


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.targets = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.targets.append(attrs['href'][1:])


def report():
    snapshot, saved, passage = fixture()
    claim = StoredClaim(saved.finding_id, saved.draft.model_copy(update={
        'key_date': date(2026, 3, 1), 'key_date_kind': 'published',
    }), saved.evidence, saved.depends_on)
    later = replace(claim, finding_id=uuid4(), draft=claim.draft.model_copy(update={
        'title': 'Later development', 'key_date': date(2026, 6, 1), 'content': 'Later supported text.',
    }))
    sentences = [ReportSentence(text=c.draft.content, finding_ids=[c.finding_id], structural=False)
                 for c in (later, claim)]
    snapshot = snapshot.model_copy(update={'sections': [
        ReportSection(section='executive_summary', sentences=sentences[:1], no_verified_items=False),
        ReportSection(section='regulatory_developments', sentences=sentences, no_verified_items=False),
        ReportSection(section='deadlines_timeline', sentences=sentences, no_verified_items=False),
        ReportSection(section='coverage_limitations', sentences=[], no_verified_items=True),
    ]})
    context = ReportContext(BRIEF, 'draft', {c.finding_id: c for c in (claim, later)},
                            {passage.id: passage}, {}, AT)
    return snapshot, context


def test_contents_and_paragraph_links_have_unique_rendered_destinations():
    snapshot, context = report()
    html = render_html(snapshot, context)
    assert '<nav class="contents"' in html
    assert html.index('Table of contents') < html.index('id="section-executive_summary"')
    assert 'href="#section-evidence"' in html
    assert 'href="#section-impact_assessment"' not in html
    assert 'id="paragraph-2-1"' in html and '>2.1</a>' in html
    assert 'id="paragraph-2-2"' in html and '>2.2</a>' in html
    assert 'Back to contents' in html
    links = Links(html)
    assert len(links.ids) == len(set(links.ids))
    assert set(links.targets) <= set(links.ids)


def test_overview_counts_unique_report_findings_instead_of_repeated_mentions():
    snapshot, context = report()
    html = render_html(snapshot, context)
    assert '<dt>Facts</dt><dd>2</dd>' in html
    assert '<dt>Inferences</dt><dd>0</dd>' in html
    assert '<dt>Cited sources</dt><dd>1</dd>' in html
    assert '<dt>Unresolved</dt><dd>0</dd>' in html


def test_timeline_orders_saved_dates_and_preserves_source_links_and_undated_text():
    snapshot, context = report()
    timeline = snapshot.sections[2]
    timeline = timeline.model_copy(update={'sentences': [*timeline.sentences,
        ReportSentence(text='No deadline has been confirmed.', finding_ids=[], structural=True)]})
    snapshot = snapshot.model_copy(update={'sections': [*snapshot.sections[:2], timeline, *snapshot.sections[3:]]})
    html = render_html(snapshot, context)
    table = html.split('<table class="timeline"', 1)[1].split('</table>', 1)[0]
    assert table.index('2026-03-01') < table.index('2026-06-01')
    assert 'Screening' in table and 'Later development' in table
    assert 'href="#finding-' in table
    assert 'No deadline has been confirmed.' in html


def test_timeline_sorts_dated_standalone_and_reworded_entries_without_losing_prose():
    snapshot, context = report()
    original = snapshot.sections[2]
    for standalone in (False, True):
        timeline = original.model_copy(update={'sentences': [
            original.sentences[0].model_copy(update={'text': 'Keep the full later wording and its conditions.'}),
            original.sentences[1],
        ]})
        sections = [timeline] if standalone else [snapshot.sections[1], timeline]
        html = render_html(snapshot.model_copy(update={'sections': sections}), context)
        table = html.split('<table class="timeline"', 1)[1].split('</table>', 1)[0]
        assert table.index('2026-03-01') < table.index('2026-06-01')
        assert '<p class="prose">Keep the full later wording and its conditions.</p>' in table
        assert '<span class="number">' in table
        assert 'href="#e1"' in html
        assert set(Links(html).targets) <= set(Links(html).ids)
