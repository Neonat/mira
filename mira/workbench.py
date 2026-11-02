"""Local UI services: intake, background execution and document-library projection."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import uuid

from mira.batch import create_run, run_batch, load_bundle, SUCCESS
from mira.ingest import IngestionError, checked_url
from mira.storage import atomic_bytes, atomic_json

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mira-ingestion')
_JOBS = {}
_GUARD = threading.Lock()


def submit_run(directory, run_id, *, item_ids=None):
    """The worker never accesses Streamlit state. Checkpoints drive UI progress."""
    key = (str(Path(directory).resolve()), run_id)
    with _GUARD:
        prior = _JOBS.get(key)
        if prior is not None and not prior.done():
            return False
        _JOBS[key] = _POOL.submit(run_batch, directory, run_id,
                                 retry_failed=True, item_ids=item_ids)
        return True


def job_state(directory, run_id):
    key = (str(Path(directory).resolve()), run_id)
    with _GUARD:
        future = _JOBS.get(key)
    if future is None:
        return 'idle', None
    if not future.done():
        return ('running' if future.running() else 'queued'), None
    error = future.exception()
    return ('failed', str(error)) if error else ('finished', None)


def create_intake(directory, *, uploads=(), urls=(), fixture=False):
    """Validate all user inputs before persisting any uploaded bytes.

    uploads: dictionaries containing name, data (bytes) and original url.
    """
    directory = Path(directory)
    if not uploads and not urls:
        raise IngestionError('Choose a PDF or enter at least one source URL.')
    if len(uploads) + len(urls) > 20:
        raise IngestionError('Add up to 20 documents at a time.')
    rows, validated = [], []
    for upload in uploads:
        url = checked_url(upload['url'].strip())
        data = upload['data']
        if not data.startswith(b'%PDF-'):
            raise IngestionError(f"{upload['name']}: this file does not have a PDF signature.")
        if len(data) > 10_000_000:
            raise IngestionError(f"{upload['name']}: PDF exceeds the 10 MB limit.")
        digest = hashlib.sha256(data).hexdigest()
        # Never use user-provided filenames as filesystem paths.
        path = directory.resolve() / 'uploads' / f'{digest}.pdf'
        item_id = hashlib.sha256((url + digest).encode()).hexdigest()[:20]
        rows.append({'id': item_id, 'kind': 'pdf', 'path': str(path), 'url': url, 'fixture': fixture})
        validated.append((path, data))
    for url in urls:
        url = checked_url(url.strip())
        rows.append({'id': hashlib.sha256(url.encode()).hexdigest()[:20], 'kind': 'url', 'url': url})
    # Same source repeated within a submission creates one item.
    rows = list({row['id']: row for row in rows}.values())
    for path, data in validated:
        atomic_bytes(path, data, immutable=True)
    path = directory / 'intake' / f'{uuid.uuid4().hex}.json'
    atomic_json(path, {'schema_version': 1, 'items': rows})
    return create_run(path, directory)


def read_runs(directory):
    runs, errors = [], []
    for path in sorted((Path(directory) / 'runs').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            run = json.loads(path.read_text())
            if not isinstance(run.get('items'), list) or not run.get('run_id'):
                raise ValueError('Missing run fields')
            runs.append(run)
        except (ValueError, OSError) as error:
            errors.append(f'{path.name}: {error}')
    return runs, errors


def library_entries(directory, runs):
    """One entry per immutable bundle; latest source first, all versions retained."""
    entries, seen, errors = [], set(), []
    for run in runs:
        for item in run['items']:
            if item['status'] not in SUCCESS or item.get('bundle') in seen:
                continue
            try:
                bundle = load_bundle(directory, item)
            except (ValueError, OSError) as error:
                errors.append(f"{item['input']['id']}: {error}")
                continue
            seen.add(item['bundle'])
            entries.append({'key': item['bundle'], 'bundle': bundle, 'run_id': run['run_id'], 'item': item})
    return entries, errors


def original_bytes(directory, bundle):
    version = bundle['document_version']
    metadata = version['metadata']
    path = Path(metadata.get('local_snapshot_path', '')).resolve()
    raw_dir = (Path(directory) / 'raw').resolve()
    if not path.is_relative_to(raw_dir) or not path.is_file():
        raise IngestionError('Original snapshot is unavailable. Restore it from your local backup.')
    if path.stat().st_size > 10_000_000:
        raise IngestionError('Original snapshot exceeds its size limit.')
    data = path.read_bytes()
    expected = metadata.get('raw_pdf_sha256') or metadata.get('raw_html_sha256')
    if not expected or hashlib.sha256(data).hexdigest() != expected:
        raise IngestionError('Original snapshot failed its integrity check; preview is blocked.')
    return data


def import_package(directory, entry):
    """Portable original + CSV for the trusted importer; never a database payload."""
    import csv
    import io
    from datetime import datetime
    import zipfile

    # Reload the checkpoint-verified bundle instead of trusting UI-cached metadata.
    bundle = load_bundle(directory, entry['item'])
    version = bundle['document_version']
    if entry['item']['input'].get('origin') == 'fixture' or version['metadata'].get('origin') == 'fixture':
        raise IngestionError('Synthetic demo evidence cannot be exported for workspace import.')
    data = original_bytes(directory, bundle)
    suffix = 'pdf' if version['metadata'].get('raw_pdf_sha256') else 'html'
    filename = f"{hashlib.sha256(data).hexdigest()}.{suffix}"
    manifest = io.StringIO(newline='')
    writer = csv.writer(manifest)
    writer.writerow(['file', 'url', 'title', 'published'])
    published = version.get('published_at')
    writer.writerow([filename, checked_url(version['source_url']), version['title'],
                     datetime.fromisoformat(published).date().isoformat() if published else ''])
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, data)
        archive.writestr('manifest.csv', manifest.getvalue())
        archive.writestr('README.txt',
            'Mira local staging handoff\n\n'
            'Extract this archive into a local folder. From the repository, run:\n'
            'python -m mira import mas --manifest /absolute/path/to/manifest.csv\n\n'
            'Requires the worker database configuration and a curator/admin identity.\n'
            'The importer checks workspace permissions and source policy, re-extracts the original,\n'
            'and assigns database document/version/passage IDs. Local IDs are not database IDs.\n'
            'Only import sources approved for the destination workspace. This export does not sync data.\n')
    return output.getvalue()
