import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from mira.batch import create_run, run_batch

ROOT = Path(__file__).resolve().parents[1]

class InspectorTests(unittest.TestCase):
    def test_library_pdf_filter_and_intake_validation(self):
        import mira.inspector
        with tempfile.TemporaryDirectory() as directory, patch.object(mira.inspector, 'DATA', Path(directory)):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('library is empty' in i.value for i in app.info))
            run = create_run(ROOT / 'tests/fixtures/batch.json', directory)
            run_batch(directory, run['run_id'])
            app.run()
            self.assertEqual([m.value for m in app.metric], ['2', '1', '1'])
            next(r for r in app.radio if r.label == 'Document type').set_value('PDF').run()
            next(b for b in app.button if b.label == 'Open').click().run()
            self.assertFalse(app.exception)
            next(s for s in app.selectbox if s.label == 'Page').select(2).run()
            self.assertFalse(any('PAGE 1' in c.value for c in app.caption))
            self.assertTrue(any('PAGE 2' in c.value for c in app.caption))
            next(t for t in app.text_input if t.label == 'Find in passages').input('no-such-word').run()
            self.assertTrue(any('No passages match' in i.value for i in app.info))
            next(r for r in app.radio if r.label == 'Workspace').set_value('Add sources').run()
            next(b for b in app.button if b.label == 'Start extraction').click().run()
            self.assertTrue(any('Confirm source permissions' in e.value for e in app.error))
            next(r for r in app.radio if r.label == 'Source input').set_value('Paste URLs').run()
            app.text_area[0].input('https://example.com/not-approved')
            app.checkbox[0].check()
            next(b for b in app.button if b.label == 'Start extraction').click().run()
            self.assertTrue(app.error)
            self.assertFalse(app.exception)
            next(r for r in app.radio if r.label == 'Workspace').set_value('Ingestion queue').run()
            self.assertTrue(any('OCR' in e.value for e in app.error))
            self.assertFalse(app.exception)
