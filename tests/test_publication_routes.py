from mira.publication_routes import (
    is_publication_pdf, register_document_key, register_publication,
)

BASE = 'https://www.legislation.gov.au/C2006A00169/2026-07-01/2026-07-01/text/original/'
PDF = BASE + 'pdf'
HTML = BASE + 'epub/OEBPS/document_1/document_1.html'


def test_fixed_representations_share_document_key():
    assert register_publication(PDF + '#page=4') == {
        'title_id': 'C2006A00169', 'start': '2026-07-01',
        'retrospective_start': '2026-07-01', 'representation': 'pdf',
    }
    assert register_publication(HTML)['representation'] == 'html'
    assert register_document_key(PDF) == register_document_key(HTML)
    assert register_document_key(PDF) is not None
    assert is_publication_pdf(PDF + '#page=4')
    assert not is_publication_pdf(HTML)


def test_dates_are_part_of_identity():
    assert register_document_key(PDF) != register_document_key(PDF.replace('2026-07-01', '2026-10-01'))
    assert register_document_key(PDF) != register_document_key(PDF.replace('/2026-07-01/text', '/2026-06-01/text'))


def test_other_routes_and_malicious_urls_are_rejected():
    bad = [
        BASE + 'html', BASE + 'pdf?x=1', BASE + 'pdf/extra',
        BASE + 'epub/OEBPS/document_2/document_2.html',
        'https://www.legislation.gov.au/C2006A00169/2026-07-01/text',
        'https://www.legislation.gov.au/C2006A00169/latest/text',
        PDF.replace('www.legislation.gov.au', 'api.prod.legislation.gov.au'),
        PDF.replace('www.legislation.gov.au', 'www.legislation.gov.au.evil.test'),
        PDF.replace('www.legislation.gov.au', 'evil@www.legislation.gov.au'),
        PDF.replace('www.legislation.gov.au', 'www.legislation.gov.au:444'),
        PDF.replace('https:', 'http:'), PDF.replace('C2006A00169', '..'),
        PDF.replace('2026-07-01', '2026-02-30'),
    ]
    for url in bad:
        assert register_publication(url) is None
        assert register_document_key(url) is None
        assert not is_publication_pdf(url)


def test_control_characters_cannot_be_normalized_into_a_valid_route():
    assert register_publication(PDF.replace('legislation', 'legis\nlation')) is None
    assert register_publication('\t' + PDF) is None
