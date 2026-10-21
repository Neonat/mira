import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter

from mira.ingest import IngestionError, extract
from mira.pdf import extract_pdf
from mira.pipeline import process_item
from mira.batch import create_run, run_batch, run_path, run_lock, load_bundle
from mira.storage import atomic_json

FIXTURES = Path(__file__).parent / 'fixtures'
URL = 'https://www.mas.gov.sg/fixtures/synthetic.pdf'


class PDFTests(unittest.TestCase):
    def test_pages_have_exact_offsets_and_unknown_publication(self):
        result = extract_pdf((FIXTURES / 'synthetic_notice.pdf').read_bytes(), URL, origin='fixture', size=150)
        self.assertEqual(result['document_version']['extraction_status'], 'complete')
        self.assertIsNone(result['document_version']['published_at'])
        self.assertEqual({p['page_number'] for p in result['passages']}, {1, 2})
        text = result['document_version']['extracted_text']
        for p in result['passages']:
            self.assertEqual(p['content'], text[p['char_start']:p['char_end']])
            page = result['pages'][p['page_number'] - 1]
            self.assertGreaterEqual(p['char_start'], page['char_start'])
            self.assertLessEqual(p['char_end'], page['char_end'])

    def test_scan_and_malformed_pdf_never_succeed_empty(self):
        for data in ((FIXTURES / 'synthetic_scan.pdf').read_bytes(), b'not a pdf', b'%PDF-1.7 invalid'):
            with self.subTest(data=data[:10]), self.assertRaises(IngestionError):
                extract_pdf(data, URL)

    def test_mixed_pdf_preserves_missing_page(self):
        writer = PdfWriter()
        reader = PdfReader(FIXTURES / 'synthetic_notice.pdf')
        writer.add_page(reader.pages[0])
        writer.add_blank_page(width=600, height=800)
        writer.add_page(reader.pages[1])
        output = io.BytesIO()
        writer.write(output)
        bundle = extract_pdf(output.getvalue(), URL)
        self.assertEqual(bundle['document_version']['extraction_status'], 'partial')
        self.assertEqual(bundle['document_version']['metadata']['pages_needing_review'], [2])
        self.assertEqual({p['page_number'] for p in bundle['passages']}, {1, 3})

    def test_encrypted_pdf_has_actionable_failure(self):
        writer = PdfWriter()
        writer.add_blank_page(width=600, height=800)
        writer.encrypt('secret')
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(IngestionError, 'Encrypted'):
            extract_pdf(output.getvalue(), URL)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'out'
        self.html = self.root / 'source.html'
        self.html.write_bytes((FIXTURES / 'mas_notice.html').read_bytes())
        self.manifest = self.root / 'batch.json'
        self.write_manifest([{'id': 'one', 'kind': 'html', 'path': 'source.html', 'url': URL, 'fixture': True},
                             {'id': 'two', 'kind': 'pdf', 'path': str((FIXTURES / 'synthetic_notice.pdf').resolve()), 'url': URL + '?two', 'fixture': True}])

    def write_manifest(self, items):
        self.manifest.write_text(json.dumps({'schema_version': 1, 'items': items}))

    def test_pause_resume_replay_skips_success(self):
        run = create_run(self.manifest, self.out)
        paused = run_batch(self.out, run['run_id'], max_items=1, processor=process_item)
        self.assertEqual(paused['status'], 'paused')
        self.assertEqual(len(paused['items'][0]['attempts']), 1)
        finished = run_batch(self.out, run['run_id'], processor=process_item)
        self.assertEqual(finished['status'], 'completed')
        self.assertEqual(len(finished['items'][0]['attempts']), 1)
        with patch('mira.batch.extract_isolated', side_effect=AssertionError('Must not rerun')):
            replay = run_batch(self.out, run['run_id'], processor=lambda *_: self.fail('Unexpected extraction'))
        self.assertEqual(replay['status'], 'completed')
        self.assertEqual(create_run(self.manifest, self.out)['run_id'], run['run_id'])
        self.assertEqual(len(list(self.out.glob('*.json'))), 2)
        self.assertEqual(len(list((self.out / 'raw').glob('*'))), 2)

    def test_failed_items_retry_without_repeating_saved(self):
        run = create_run(self.manifest, self.out)
        def fail_first(item, directory):
            if item['id'] == 'one':
                raise IngestionError('Temporary failure')
            return process_item(item, directory)
        failed = run_batch(self.out, run['run_id'], processor=fail_first)
        self.assertEqual(failed['status'], 'completed_with_errors')
        run_batch(self.out, run['run_id'], processor=lambda *_: self.fail('Failed item needs explicit retry'))
        recovered = run_batch(self.out, run['run_id'], retry_failed=True, processor=process_item)
        self.assertEqual(recovered['status'], 'completed')
        self.assertEqual([len(i['attempts']) for i in recovered['items']], [2, 1])
        self.assertEqual(recovered['items'][0]['attempts'][0]['error'], 'Temporary failure')

    def test_changed_input_requires_new_run(self):
        run = create_run(self.manifest, self.out)
        self.html.write_text(self.html.read_text().replace('invented paragraph', 'changed paragraph'))
        result = run_batch(self.out, run['run_id'], processor=process_item)
        self.assertEqual(result['items'][0]['status'], 'failed')
        self.assertIn('Input changed', result['items'][0]['error'])
        self.assertNotEqual(create_run(self.manifest, self.out)['run_id'], run['run_id'])

    def test_interrupted_attempt_is_recovered(self):
        run = create_run(self.manifest, self.out)
        with self.assertRaises(KeyboardInterrupt):
            run_batch(self.out, run['run_id'], processor=lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        recovered = run_batch(self.out, run['run_id'], processor=process_item)
        self.assertEqual(recovered['status'], 'completed')
        self.assertEqual(recovered['items'][0]['attempts'][0]['status'], 'interrupted')

    def test_lock_rejects_concurrent_run(self):
        run = create_run(self.manifest, self.out)
        with run_lock(run_path(self.out, run['run_id'])):
            with self.assertRaisesRegex(IngestionError, 'already being processed'):
                run_batch(self.out, run['run_id'])

    def test_corrupted_bundle_is_not_displayed_or_silently_overwritten(self):
        run = create_run(self.manifest, self.out)
        done = run_batch(self.out, run['run_id'], processor=process_item)
        item = done['items'][0]
        path = self.out / item['bundle']
        bundle = json.loads(path.read_text())
        bundle['document_version']['extracted_text'] = 'tampered'
        atomic_json(path, bundle)
        with self.assertRaisesRegex(IngestionError, 'changed'):
            load_bundle(self.out, item)
        result = run_batch(self.out, run['run_id'], retry_failed=True, processor=process_item)
        self.assertEqual(result['items'][0]['status'], 'failed')

    def test_real_subprocess_worker_and_scan_failure(self):
        run = create_run(FIXTURES / 'batch.json', self.out)
        result = run_batch(self.out, run['run_id'])
        self.assertEqual(result['counts'], {'saved': 2, 'failed': 1})
        self.assertIn('OCR', result['items'][2]['error'])

    def test_duplicate_ids_rejected(self):
        item = {'id': 'one', 'kind': 'url', 'url': URL}
        self.write_manifest([item, item])
        with self.assertRaises(IngestionError):
            create_run(self.manifest, self.out)


if __name__ == '__main__':
    unittest.main()
