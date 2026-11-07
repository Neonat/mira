"""Checkpointed local ingestion runs. Usage: python -m mira.batch --help."""
import argparse
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from mira.ingest import IngestionError, checked_url, save
from mira.storage import atomic_json

SUCCESS = {'saved', 'unchanged'}
ROOT = Path(__file__).resolve().parent.parent
PIPELINE_VERSION = 'local-ingestion-v2'


def now():
    return datetime.now(timezone.utc).isoformat()


def run_path(directory, run_id):
    if not re.fullmatch(r'[0-9a-f]{24}', run_id):
        raise IngestionError('Invalid run ID.')
    return Path(directory) / 'runs' / f'{run_id}.json'


@contextmanager
def run_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise IngestionError('This run is already being processed. Refresh after it finishes.') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def prepare_items(manifest, base):
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise IngestionError('Manifest must have schema_version: 1.')
    rows = manifest.get('items')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise IngestionError('Manifest must contain 1–100 items.')
    prepared, identifiers = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise IngestionError('Each manifest item must be an object.')
        key = row.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', key) or key in identifiers:
            raise IngestionError('Each item needs a unique id containing letters, numbers, dashes or underscores.')
        identifiers.add(key)
        kind = row.get('kind')
        if kind not in ('html', 'pdf', 'url'):
            raise IngestionError('Item kind must be html, pdf or url.')
        url = row.get('url')
        if not isinstance(url, str):
            raise IngestionError('Each item needs its original source URL.')
        checked_url(url)
        size = row.get('passage_size', 1000)
        if type(size) is not int or not 50 <= size <= 4000:
            raise IngestionError('passage_size must be an integer from 50 to 4000.')
        fixture = row.get('fixture', False)
        if type(fixture) is not bool:
            raise IngestionError('fixture must be true or false.')
        item = {'id': key, 'kind': kind, 'url': url, 'passage_size': size,
                'origin': 'live' if kind == 'url' else 'fixture' if fixture else 'local'}
        if kind != 'url':
            if not isinstance(row.get('path'), str) or not row['path']:
                raise IngestionError('Local inputs need a path relative to the manifest.')
            path = (Path(base) / row['path']).resolve()
            item['path'] = str(path)
            # Missing files are item failures, not an excuse to abandon the batch.
            if path.is_file():
                limit = 10_000_000 if kind == 'pdf' else 2_000_000
                if path.stat().st_size > limit:
                    raise IngestionError(f'Input {key} exceeds its size limit.')
                item['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        prepared.append(item)
    return prepared


def create_run(manifest_path, directory, *, refresh=False):
    manifest_path = Path(manifest_path).resolve()
    if manifest_path.stat().st_size > 1_000_000:
        raise IngestionError('Manifest exceeds 1 MB.')
    manifest = json.loads(manifest_path.read_text())
    items = prepare_items(manifest, manifest_path.parent)
    identity = {'pipeline_version': PIPELINE_VERSION, 'items': items}
    if refresh:
        identity['refresh_at'] = now()
    run_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    path = run_path(directory, run_id)
    with run_lock(path):
        if path.exists():
            return json.loads(path.read_text())
        run = {'schema_version': 1, 'run_id': run_id, 'pipeline_version': PIPELINE_VERSION,
               'created_at': now(), 'updated_at': now(), 'status': 'queued',
               'manifest': str(manifest_path), 'items': [
                   {'input': item, 'status': 'pending', 'attempts': [], 'bundle': None,
                    'error': None} for item in items]}
        atomic_json(path, run)
        return run


def extract_isolated(item, directory):
    # A malformed PDF cannot block the entire queue indefinitely. A separate
    # interpreter also releases parser memory after every document.
    try:
        result = subprocess.run([sys.executable, '-m', 'mira.worker'],
                                input=json.dumps({'item': item, 'directory': str(Path(directory).resolve())}),
                                text=True, capture_output=True, cwd=ROOT, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise IngestionError('Extraction exceeded 60 seconds; retry or inspect the source.') from error
    try:
        response = json.loads(result.stdout)
    except ValueError as error:
        raise IngestionError('Extraction worker exited unexpectedly; inspect the input file.') from error
    if result.returncode or 'error' in response:
        raise IngestionError(response.get('error', 'Extraction worker failed.'))
    return response['bundle']


def load_bundle(directory, item):
    filename = item.get('bundle')
    if not filename or not re.fullmatch(r'[0-9a-f]{64}\.json', filename):
        raise IngestionError('Saved bundle reference is invalid.')
    path = Path(directory) / filename
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item.get('bundle_sha256'):
        raise IngestionError('Saved bundle changed; restore the original snapshot before proceeding.')
    return json.loads(data)


def run_batch(directory, run_id, *, retry_failed=False, max_items=None, processor=extract_isolated, item_ids=None):
    path = run_path(directory, run_id)
    if max_items is not None and max_items < 1:
        raise IngestionError('max_items must be positive.')
    with run_lock(path):
        run = json.loads(path.read_text())
        if item_ids is not None and not set(item_ids).issubset({i['input']['id'] for i in run['items']}):
            raise IngestionError('Requested item is not in this run.')
        run['status'] = 'running'
        processed = 0
        atomic_json(path, run)
        try:
            for item in run['items']:
                if item_ids is not None and item['input']['id'] not in item_ids:
                    continue
                if item['status'] in SUCCESS:
                    try:
                        load_bundle(directory, item)
                    except (OSError, ValueError) as error:
                        item['status'], item['error'] = 'failed', str(error)
                        atomic_json(path, run)
                    else:
                        continue
                if item['status'] == 'failed' and not retry_failed:
                    continue
                if max_items is not None and processed >= max_items:
                    break
                if item['status'] == 'processing' and item['attempts']:
                    item['attempts'][-1].update(status='interrupted', finished_at=now())
                item['status'], item['error'] = 'processing', None
                attempt = {'started_at': now(), 'status': 'processing'}
                item['attempts'].append(attempt)
                atomic_json(path, run)
                try:
                    bundle = processor(item['input'], directory)
                    saved_path, status = save(bundle, Path(directory))
                    item.update(status=status, bundle=saved_path.name,
                                bundle_sha256=hashlib.sha256(saved_path.read_bytes()).hexdigest(),
                                extraction_status=bundle['document_version']['extraction_status'])
                except Exception as error:
                    # The queue must record a failure and continue to other sources.
                    item.update(status='failed', error=str(error)[:500])
                attempt.update(status=item['status'], error=item['error'], finished_at=now())
                processed += 1
                run['updated_at'] = now()
                atomic_json(path, run)
        except KeyboardInterrupt:
            run['status'] = 'cancelled'
            raise
        finally:
            counts = Counter(item['status'] for item in run['items'])
            run['counts'] = dict(counts)
            if run['status'] != 'cancelled':
                if counts['pending'] or counts['processing']:
                    run['status'] = 'paused'
                elif counts['failed']:
                    run['status'] = 'completed_with_errors'
                else:
                    run['status'] = 'completed'
            run['updated_at'] = now()
            atomic_json(path, run)
        return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data/ingestion'))
    commands = parser.add_subparsers(dest='action', required=True)
    start = commands.add_parser('start')
    start.add_argument('manifest', type=Path)
    start.add_argument('--refresh', action='store_true', help='Create a new observation run, even for the same manifest')
    resume = commands.add_parser('resume')
    resume.add_argument('run_id')
    resume.add_argument('--retry-failed', action='store_true')
    for command in (start, resume):
        command.add_argument('--max-items', type=int, help='Pause after this many attempts')
    args = parser.parse_args()
    try:
        run_id = (create_run(args.manifest, args.output_dir, refresh=args.refresh)['run_id']
                  if args.action == 'start' else args.run_id)
        print(json.dumps({'run_id': run_id, 'status': 'accepted'}), flush=True)
        run = run_batch(args.output_dir, run_id, retry_failed=getattr(args, 'retry_failed', False),
                        max_items=args.max_items)
        print(json.dumps({'run_id': run_id, 'status': run['status'], 'counts': run['counts']}))
        return 1 if run['status'] == 'completed_with_errors' else 0
    except KeyboardInterrupt:
        print('Paused by user. Resume using the same run ID.', file=sys.stderr)
        return 130
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
