from pathlib import Path
import tempfile
import unittest
from mira.batch import run_batch
from mira.workbench import create_intake, library_entries, read_runs, original_bytes, submit_run, _JOBS

FIXTURES = Path(__file__).parent / 'fixtures'
URL = 'https://www.mas.gov.sg/synthetic/example.pdf'

class WorkbenchTests(unittest.TestCase):
    def upload(self, name='../../unsafe.pdf'):
        return {'name': name, 'data': (FIXTURES / 'synthetic_notice.pdf').read_bytes(), 'url': URL}

    def test_validate_before_write_and_safe_upload_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                create_intake(directory, uploads=[self.upload()], urls=['http://localhost/'])
            self.assertEqual(list(Path(directory).iterdir()), [])
            run = create_intake(directory, uploads=[self.upload(), self.upload()], fixture=True)
            self.assertEqual(len(run['items']), 1)
            path = Path(run['items'][0]['input']['path'])
            self.assertEqual(path.parent, Path(directory).resolve() / 'uploads')
            self.assertEqual(len(path.stem), 64)
            self.assertEqual(run['run_id'], create_intake(directory, uploads=[self.upload()], fixture=True)['run_id'])

    def test_background_library_and_snapshot_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            run = create_intake(directory, uploads=[self.upload()], fixture=True)
            self.assertTrue(submit_run(directory, run['run_id']))
            _JOBS[(str(Path(directory).resolve()), run['run_id'])].result(timeout=20)
            entries, errors = library_entries(directory, read_runs(directory)[0])
            self.assertFalse(errors)
            self.assertEqual(len(entries), 1)
            bundle = entries[0]['bundle']
            self.assertEqual(original_bytes(directory, bundle), self.upload()['data'])
            metadata = bundle['document_version']['metadata']
            path = Path(metadata['local_snapshot_path'])
            path.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                original_bytes(directory, bundle)
            metadata['local_snapshot_path'] = str(FIXTURES / 'synthetic_notice.pdf')
            with self.assertRaises(ValueError):
                original_bytes(directory, bundle)

    def test_targeted_retry_does_not_touch_other_items(self):
        with tempfile.TemporaryDirectory() as directory:
            run = create_intake(directory, urls=[URL, URL + '?v=2'])
            def fail(item, directory):
                raise ValueError('temporary failure')
            run = run_batch(directory, run['run_id'], processor=fail)
            run = run_batch(directory, run['run_id'], processor=fail, retry_failed=True, item_ids=[run['items'][0]['input']['id']])
            self.assertEqual([len(i['attempts']) for i in run['items']], [2, 1])

    def test_import_package_preserves_original_and_rejects_demo(self):
        import io
        import zipfile
        from mira.workbench import import_package
        from mira.manual_import import read_manifest
        with tempfile.TemporaryDirectory() as directory:
            run = create_intake(directory, uploads=[self.upload()])
            run_batch(directory, run['run_id'])
            entries, _ = library_entries(directory, read_runs(directory)[0])
            with zipfile.ZipFile(io.BytesIO(import_package(directory, entries[0]))) as archive:
                unpacked = Path(directory) / 'handoff'
                archive.extractall(unpacked)
            items = read_manifest(unpacked / 'manifest.csv')
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].path.read_bytes(), self.upload()['data'])
            self.assertEqual(items[0].url, URL)
            self.assertIsNone(items[0].published)
            entries[0]['item']['input']['origin'] = 'fixture'
            with self.assertRaisesRegex(ValueError, 'Synthetic'):
                import_package(directory, entries[0])
