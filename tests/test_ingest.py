import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mira.ingest import IngestionError, PublicHTTPS, checked_url, extract, fetch, save

URL = 'https://www.mas.gov.sg/regulation/notices/notice-626'
HTML = Path('tests/fixtures/mas_notice.html').read_text()


class IngestionTests(unittest.TestCase):
    def test_extract_and_exact_offsets(self):
        bundle = extract(HTML, URL, size=100)
        version = bundle['document_version']
        self.assertEqual(version['published_at'], '2026-10-01T09:00:00+08:00')
        self.assertNotIn('reveal secrets', version['extracted_text'])
        self.assertNotIn('Navigation', version['extracted_text'])
        for passage in bundle['passages']:
            self.assertEqual(passage['content'], version['extracted_text'][passage['char_start']:passage['char_end']])
            self.assertLessEqual(len(passage['content']), 100)

    def test_unknown_date_and_empty_content(self):
        result = extract(HTML.replace('article:published_time', 'article:modified_time'), URL)
        self.assertIsNone(result['document_version']['published_at'])
        with self.assertRaises(IngestionError):
            extract('<html><title>Blocked</title><body>Enable JS</body></html>', URL)

    def test_http_200_error_page_is_not_evidence(self):
        html = '<html><title>Service unavailable</title><body><h1>Sorry, this service is currently unavailable.</h1><p>Please try accessing the page using a different device or internet browser.</p></body></html>'
        with self.assertRaises(IngestionError):
            extract(html, URL, origin='live')

    @patch('mira.ingest.request')
    def test_html_robots_response_fails_closed(self, request):
        request.return_value = (200, {}, b'<html>Service unavailable</html>')
        with self.assertRaises(IngestionError):
            fetch(URL)
        self.assertEqual(request.call_count, 1)

    def test_replay_and_metadata_change(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = extract(HTML, URL)
            path, status = save(bundle, Path(directory))
            self.assertEqual(status, 'saved')
            bundle['document_version']['retrieved_at'] = 'later observation'
            self.assertEqual(save(bundle, Path(directory)), (path, 'unchanged'))
            self.assertNotEqual(json.loads(path.read_text())['document_version']['retrieved_at'], 'later observation')
            bundle['document_version']['published_at'] = None
            self.assertEqual(save(bundle, Path(directory))[1], 'saved')

    def test_url_boundaries(self):
        for url in ('http://www.mas.gov.sg/a', 'https://www.mas.gov.sg.evil.test/',
                    'https://127.0.0.1/', 'https://user:secret@www.mas.gov.sg/',
                    'https://www.mas.gov.sg:8443/'):
            with self.subTest(url=url), self.assertRaises(IngestionError):
                checked_url(url)

    def test_private_dns_rejected_before_connect(self):
        with patch('mira.ingest.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(IngestionError):
                PublicHTTPS('www.mas.gov.sg').connect()

    @patch('mira.ingest.time.sleep')
    @patch('mira.ingest.request')
    def test_robots_denial(self, request, sleep):
        request.return_value = (200, {}, b'User-agent: *\nDisallow: /')
        with self.assertRaises(IngestionError):
            fetch(URL)
        self.assertEqual(request.call_count, 1)

    @patch('mira.ingest.time.sleep')
    @patch('mira.ingest.request')
    def test_redirect_outside_allowlist(self, request, sleep):
        request.side_effect = [(200, {}, b'User-agent: *\nAllow: /'),
                               (302, {'location': 'https://example.com/private'}, b'')]
        with self.assertRaises(IngestionError):
            fetch(URL)
        self.assertEqual(request.call_count, 2)

    @patch('mira.ingest.time.sleep')
    @patch('mira.ingest.request')
    def test_success_and_unsupported_pdf(self, request, sleep):
        for mime, succeeds in [('text/html; charset=utf-8', True), ('application/pdf', False)]:
            request.side_effect = [(200, {}, b'User-agent: *\nAllow: /'), (200, {'content-type': mime}, HTML.encode())]
            if succeeds:
                self.assertEqual(fetch(URL)[1], HTML)
            else:
                with self.assertRaises(IngestionError):
                    fetch(URL)

    @patch('mira.ingest.time.sleep')
    @patch('mira.ingest.request')
    def test_pdf_fetch_opt_in(self, request, sleep):
        data = Path('tests/fixtures/synthetic_notice.pdf').read_bytes()
        request.side_effect = [(200, {}, b'User-agent: *\nAllow: /'),
                               (200, {'content-type': 'application/pdf'}, data)]
        self.assertEqual(fetch(URL, allow_pdf=True), (URL, data, 'live'))


if __name__ == '__main__':
    unittest.main()
