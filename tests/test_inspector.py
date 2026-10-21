import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class InspectorTests(unittest.TestCase):
    def test_empty_demo_pdf_filter_and_failure(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'MIRA_DATA_DIR': directory}):
            # The app imports this module once; update its data root explicitly
            # for repeatable tests in the same interpreter.
            import mira.inspector
            with patch.object(mira.inspector, 'DATA', Path(directory)):
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=45).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('No ingestion runs' in info.value for info in app.info))
                next(b for b in app.button if b.label == 'Load synthetic demo').click().run()
                self.assertFalse(app.exception)
                self.assertEqual([m.value for m in app.metric][:4], ['3', '2', '1', '0'])
                source = next(s for s in app.selectbox if s.label == 'Source')
                source.select_index(1).run()
                self.assertFalse(app.exception)
                self.assertTrue(any('PAGE 1' in c.value for c in app.caption))
                page = next(s for s in app.selectbox if s.label == 'Page')
                page.select(2).run()
                self.assertFalse(any('PAGE 1' in c.value for c in app.caption))
                self.assertTrue(any('PAGE 2' in c.value for c in app.caption))
                app.text_input[0].input('no-such-passage').run()
                self.assertTrue(any('No passages match' in i.value for i in app.info))
                app.radio[0].set_value('Needs attention').run()
                source = next(s for s in app.selectbox if s.label == 'Source')
                source.select_index(1).run()
                self.assertTrue(any('OCR' in e.value for e in app.error))
                self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
