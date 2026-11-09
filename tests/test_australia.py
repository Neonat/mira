import json
from datetime import date

from mira.australia import extract_register_json, is_register_api_url

TITLE = 'https://api.prod.legislation.gov.au/v1/Titles/C2004A01224'
VERSIONS = "https://api.prod.legislation.gov.au/v1/Versions?$filter=titleId%20eq%20%27C2004A01224%27"


def extract(data, url=VERSIONS):
    return extract_register_json(json.dumps(data).encode(), url)


def version(**extra):
    return {'titleId': 'C2004A01224', 'name': 'Example Act', 'start': '2024-07-01T00:00:00',
            'registeredAt': '2024-07-10T12:00:00', 'registerId': 'C2024C00001',
            'compilationNumber': '3', **extra}


def test_url_scope():
    assert is_register_api_url(TITLE)
    assert is_register_api_url(VERSIONS)
    for url in ['http://api.prod.legislation.gov.au/v1/Titles/C2004A01224',
                'https://api.prod.legislation.gov.au.evil.test/v1/Titles/C2004A01224',
                'https://evil@api.prod.legislation.gov.au/v1/Titles/C2004A01224',
                'https://api.prod.legislation.gov.au:444/v1/Titles/C2004A01224',
                'https://api.prod.legislation.gov.au/v1/Versions',
                'https://api.prod.legislation.gov.au/v1/Titles/../Versions',
                'https://api.prod.legislation.gov.au/v1/Other']:
        assert not is_register_api_url(url)


def test_title_metadata_only():
    data = {'id': 'C2004A01224', 'name': 'Example Act', 'collection': 'Act'}
    result = extract(data, TITLE)
    assert result.status == 'complete'
    assert result.metadata['native_record'] == data
    assert 'discovery metadata' in result.text.lower()
    assert 'not legal text' in result.text.lower()
    assert not result.links


def test_expanded_and_collection_preserve_registration_date():
    v = version()
    for data, url in [({'id': 'C2004A01224', 'name': 'Example Act', 'versions': [v]}, TITLE),
                      ({'value': [v], '@odata.nextLink': 'https://evil.test'}, VERSIONS)]:
        result = extract(data, url)
        assert result.status == 'complete'
        assert result.metadata['native_record'] == data
        assert result.links
        for link in result.links:
            assert link.published == date(2024, 7, 10)
            assert 'registeredAt' in link.date_source
            assert '2024-07-01' in link.context
            assert link.url.startswith('https://api.prod.legislation.gov.au/v1/Documents?')
            assert 'latest' not in link.url.lower()


def test_missing_registration_does_not_use_effective_date():
    result = extract({'value': [version(registeredAt=None)]})
    assert result.status == 'complete'
    assert all(link.published is None and link.date_source is None for link in result.links)


def test_bad_input_fails_safely():
    for data in [{'value': 'bad'}, {'value': [version(titleId='../evil')]},
                 {'value': [version(registeredAt='2024-99-99')]},
                 {'value': [version(documents='bad')]}, {'value': [3]}]:
        result = extract(data)
        assert result.status in ('failed', 'unsupported')
        assert not result.links
    assert extract_register_json(b'{', VERSIONS).status == 'failed'
    assert extract({'value': []}, 'https://evil.test/v1/Versions?$filter=x').status == 'unsupported'


def test_pdf_representation_uses_retrospective_date_and_never_upstream_url():
    v = version(retrospectiveStart='2024-06-01T00:00:00', documents=[
        {'type': 'Primary', 'format': 'Pdf', 'titleId': 'C2004A01224',
         'registerId': 'C2024C00001', 'fileName': 'act.pdf', 'url': 'https://evil.test/a.pdf'}])
    result = extract({'value': [v]})
    assert [link.url for link in result.links] == [
        'https://www.legislation.gov.au/C2004A01224/2024-07-01/2024-06-01/text/original/pdf']
    assert all(link.published == date(2024, 7, 10) for link in result.links)


def test_document_malformed_without_start_is_rejected():
    result = extract({'value': [version(start=None, documents=[{'type': 3}])]})
    assert result.status == 'failed'
    assert not result.links


def test_variant_documents_do_not_fabricate_primary_pdf_route():
    v = version(documents=[{'type': 'Primary', 'format': 'Pdf', 'volumeNumber': 2},
                           {'type': 'Primary', 'format': 'Pdf', 'rectificationVersionNumber': 1},
                           {'type': 'Primary', 'format': 'Pdf', 'versionType': 'Replacement'}])
    result = extract({'value': [v]})
    assert result.status == 'complete'
    assert len(result.links) == 1


def test_primary_epub_exposes_verified_html_instead_of_incomplete_viewer():
    v=version(documents=[{'type':'Primary','format':'Epub','volumeNumber':0},
                         {'type':'Primary','format':'Pdf','volumeNumber':0}])
    result=extract({'value':[v]})
    assert result.status=='complete'
    assert any('/epub/OEBPS/document_1/document_1.html' in l.url for l in result.links)
    assert not any(l.url.endswith('/text') for l in result.links)


def test_versions_discover_scoped_documents_with_registration_date():
    v = version()
    result = extract({'value': [v]})
    assert len(result.links) == 1
    link = result.links[0]
    assert link.url == ('https://api.prod.legislation.gov.au/v1/Documents?'
                        '$filter=titleId%20eq%20%27C2004A01224%27%20and%20registerId%20eq%20%27C2024C00001%27')
    assert link.published == date(2024, 7, 10)
    assert 'registeredAt' in link.date_source


def test_documents_scoped_filter_and_representations():
    url = ('https://api.prod.legislation.gov.au/v1/Documents?'
           '$filter=titleId%20eq%20%27C2004A01224%27%20and%20registerId%20eq%20%27C2024C00001%27')
    document = {'titleId': 'C2004A01224', 'registerId': 'C2024C00001',
                'start': '2024-07-01T00:00:00', 'retrospectiveStart': '2024-07-01T00:00:00',
                'type': 'Primary', 'format': 'Pdf', 'volumeNumber': 0,
                'rectificationVersionNumber': 0, 'uniqueTypeNumber': 0, 'extra': {'preserved': True}}
    data = {'value': [document, {**document, 'format': 'Epub'}], '@odata.nextLink': 'https://evil.test'}
    assert is_register_api_url(url)
    result = extract(data, url)
    assert result.metadata['native_record'] == data
    assert result.metadata['role'] == 'discovery_metadata'
    assert len(result.links) == 2
    assert result.links[0].url.endswith('/2024-07-01/2024-07-01/text/original/pdf')
    assert result.links[1].url.endswith('/2024-07-01/2024-07-01/text/original/epub/OEBPS/document_1/document_1.html')
    assert all(link.published is None and link.date_source is None for link in result.links)
    assert extract({'value': [{**document, 'registerId': 'C2024C00002'}]}, url).status == 'failed'
    for suffix in ['titleId%20eq%20%27C2004A01224%27',
                   'titleId%20eq%20%27C2004A01224%27%20or%20registerId%20eq%20%27C2024C00001%27',
                   'titleId%20eq%20%27C2004A01224%27%20and%20registerId%20eq%20%27C2024C00001%27%20or%20true']:
        assert not is_register_api_url('https://api.prod.legislation.gov.au/v1/Documents?$filter=' + suffix)


def test_captured_zero_rectification_is_an_original_representation():
    url = ('https://api.prod.legislation.gov.au/v1/Documents?'
           '$filter=titleId%20eq%20%27C2006A00169%27%20and%20registerId%20eq%20%27C2026C00447%27')
    doc = {'titleId': 'C2006A00169', 'registerId': 'C2026C00447',
           'start': '2026-10-01T00:00:00', 'retrospectiveStart': '2026-10-01T00:00:00',
           'rectificationVersionNumber': 0, 'versionType': 'Rectification', 'type': 'Primary',
           'uniqueTypeNumber': 0, 'volumeNumber': 0, 'format': 'Pdf', 'compilationNumber': '63',
           'rectified': '2026-10-10T13:35:17.8667995', 'extension': '.pdf'}
    result = extract({'value': [doc]}, url)
    assert len(result.links) == 1
    assert result.links[0].url.endswith('/2026-10-01/2026-10-01/text/original/pdf')
    assert result.links[0].published is None
