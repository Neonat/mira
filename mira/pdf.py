"""PDF text extraction with physical-page citations; no OCR or date inference."""
import hashlib
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader, __version__ as PYPDF_VERSION
from pypdf.errors import PyPdfError

from mira.ingest import IngestionError, checked_url, clean, passages

MAX_PDF_BYTES = 10_000_000
MAX_PAGES = 200
MAX_TEXT = 2_000_000
VERSION = f'pdf-v1-pypdf-{PYPDF_VERSION}'


def extract_pdf(data, url, *, origin='local', title=None, size=1000):
    url = checked_url(url)
    if not data.startswith(b'%PDF-'):
        raise IngestionError('Not a PDF file: missing PDF signature.')
    if len(data) > MAX_PDF_BYTES:
        raise IngestionError('PDF exceeds the 10 MB limit.')
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise IngestionError('Encrypted PDF: supply an authorised, unencrypted copy.')
        if not 0 < len(reader.pages) <= MAX_PAGES:
            raise IngestionError(f'PDF must contain 1–{MAX_PAGES} pages.')
        texts, page_info, cited = [], [], []
        offset = 0
        for number, page in enumerate(reader.pages, 1):
            text = clean([page.extract_text() or ''])
            if offset + len(text) > MAX_TEXT:
                raise IngestionError('Extracted PDF text exceeds the 2 million character limit.')
            # Short/empty pages may be scans, blank dividers or unsupported encodings.
            # Do not label them definitively scanned without an image-level check.
            needs_review = len(''.join(text.split())) < 40
            page_info.append({'page_number': number, 'char_start': offset,
                              'char_end': offset + len(text),
                              'status': 'needs_review' if needs_review else 'text_extracted',
                              'reason': 'Little or no text; may need OCR or visual review.' if needs_review else None})
            for passage in passages(text, size):
                passage.update(page_number=number, passage_number=len(cited) + 1,
                               char_start=offset + passage['char_start'],
                               char_end=offset + passage['char_end'], extraction_version=VERSION)
                cited.append(passage)
            texts.append(text)
            offset += len(text) + 2
        text = '\n\n'.join(texts)
        if not text.strip():
            raise IngestionError('No extractable PDF text. OCR or visual review is required; no evidence saved.')
        title = title or str((reader.metadata or {}).get('/Title') or Path(url).stem)
    except IngestionError:
        raise
    except (PyPdfError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise IngestionError('PDF could not be parsed; check that the file is intact.') from error
    gaps = [p['page_number'] for p in page_info if p['status'] == 'needs_review']
    return {
        'schema_version': 1, 'source_key': 'mas',
        'document': {'canonical_url': url, 'title': title, 'document_type': 'regulation'},
        'document_version': {
            'content_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'source_url': url, 'title': title, 'published_at': None,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'extraction_status': 'partial' if gaps else 'complete',
            'extracted_text': text, 'extraction_version': VERSION,
            'metadata': {
                'origin': origin, 'media_type': 'application/pdf',
                'raw_pdf_sha256': hashlib.sha256(data).hexdigest(),
                'page_count': len(page_info), 'pages_needing_review': gaps,
                'date_warning': 'Publication date unknown; PDF creation dates are not publication dates.',
                'extraction_warning': ('Pages with little or no text need OCR or visual review.' if gaps
                                       else 'Text extracted on every page; reading order, tables and accuracy still need review.'),
            },
        },
        'pages': page_info, 'passages': cited,
    }
