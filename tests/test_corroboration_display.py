from mira.corroboration_display import assessment_html


def test_auditor_sees_quotes_origin_dates_and_clickable_saved_sources():
    html=assessment_html({'assessment':{'status':'conflicting_evidence','checked_at':'2026-11-08T00:00:00Z',
        'reasons':['Different quantity'], 'candidates':[{'passage':{'id':'p','title':'Public report',
        'source_url':'https://example.org/report','published_at':'2026-01-02','document_version_id':'v',
        'source_name':'Publisher'}}], 'decisions':[{'passage_id':'p','quote':'<script>20 units</script>',
        'relation':'contradicts','origin_relation':'unknown','reason':'Quantity differs','origin_evidence':[]}],
        'stop_reasons':['document_limit'],'document_attempts':5,'queries_used':2}})
    assert 'Conflicting evidence' in html and '2026-01-02' in html
    assert 'href="https://example.org/report"' in html
    assert '&lt;script&gt;20 units&lt;/script&gt;' in html and '<script>' not in html
    assert 'Origin: unknown' in html and 'document attempts: 5' in html
