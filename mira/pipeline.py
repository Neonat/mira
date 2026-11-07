"""Input adapters shared by the single-file CLI, batch worker and inspector."""
import hashlib
from pathlib import Path

from mira.ingest import IngestionError, MAX_BYTES, checked_url, extract, fetch
from mira.storage import raw_snapshot


def process_item(item, directory):
    url = checked_url(item['url'])
    size = item.get('passage_size', 1000)
    origin = item.get('origin', 'local')
    if item['kind'] == 'url':
        url, payload, origin = fetch(url, allow_pdf=True)
        if isinstance(payload, bytes):
            from mira.pdf import extract_pdf
            data, suffix = payload, 'pdf'
            bundle = extract_pdf(data, url, origin=origin, size=size)
        else:
            data, suffix = payload.encode('utf-8'), 'html'
            bundle = extract(payload, url, origin, size)

    else:
        path = Path(item['path'])
        limit = 10_000_000 if item['kind'] == 'pdf' else MAX_BYTES
        with path.open('rb') as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise IngestionError(f'Input exceeds the {limit // 1_000_000} MB limit.')
        if item.get('input_sha256') and hashlib.sha256(data).hexdigest() != item['input_sha256']:
            raise IngestionError('Input changed since the run was created. Start a new batch to preserve history.')
        suffix = item['kind']
        if suffix == 'pdf':
            from mira.pdf import extract_pdf
            bundle = extract_pdf(data, url, origin=origin, size=size)
        elif suffix == 'html':
            bundle = extract(data.decode('utf-8'), url, origin, size)
        else:
            raise IngestionError('Supported input kinds are html, pdf and url.')
    bundle['document_version']['metadata']['local_snapshot_path'] = raw_snapshot(data, directory, suffix)
    return bundle
