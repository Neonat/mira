"""Retention integration uses only local throwaway database sources and bytes."""
import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from psycopg.errors import ForeignKeyViolation
from psycopg.types.json import Jsonb

from mira.evidence import EvidenceWriter
from mira.extract import Extracted
from mira.fetch import FetchedPage
from mira.originals import PrivateOriginalStore, RetentionPolicy
from mira.store import SourceRecord
from test_pipeline_db import conn, workspace

pytestmark = pytest.mark.skipif(not os.environ.get('MIRA_TEST_DATABASE_URL'), reason='local DB required')


@pytest.fixture
def setup_original(conn, workspace, tmp_path):
    ws, user = workspace
    source_id = uuid4()
    grant = {'original_retention': {'approved': True, 'reference': 'throwaway-fixture-only'}}
    conn.execute('''insert into public.sources
        (id, workspace_id, source_key, name, source_type, base_url, permitted_operations, connector_config)
        values (%s,%s,%s,'Original fixture','website','https://original.test',%s,%s)''',
        (source_id, ws, str(source_id), ['fetch', 'store_text'], Jsonb(grant)))
    source = SourceRecord(source_id, 'Original fixture', 'website', 'https://original.test', None,
                          ('fetch', 'store_text'), grant)
    page = FetchedPage('https://original.test/a.pdf', 'https://original.test/a.pdf', source,
                       'pdf', 'application/pdf', b'%PDF fixture original bytes', datetime.now(UTC))
    extracted = Extracted('Fixture PDF', 'complete', ['First complete paragraph.', 'Second complete paragraph.'])
    store = PrivateOriginalStore(tmp_path.resolve() / 'originals', RetentionPolicy(enabled=True))
    return ws, user, page, extracted, store


def version(conn, saved):
    return conn.execute('select * from public.document_versions where id=%s',
                        (saved.document_version_id,)).fetchone()


@pytest.mark.parametrize('provenance', [None, {'import': 'manual'}])
def test_http_and_manual_bytes_are_retained_with_text(conn, setup_original, provenance):
    ws, user, page, extracted, store = setup_original
    saved = EvidenceWriter(conn, ws, user, originals=store).save(page, extracted, provenance)
    row = version(conn, saved)
    assert row['extracted_text'] == extracted.text
    assert saved.passage_ids
    assert row['metadata']['original_retained'] is True
    assert row['metadata']['original_retention_status'] == 'retained'
    identity = row['metadata']['retained_original']
    assert identity['sha256'] == hashlib.sha256(page.body).hexdigest()
    assert identity['sha256'] == row['metadata']['capture_sha256']
    assert store.read(ws, identity) == page.body


@pytest.mark.parametrize('method', ['live_browser', 'offline_browser', 'unknown'])
def test_browser_and_unknown_capture_never_retained(conn, setup_original, method):
    ws, user, page, extracted, store = setup_original
    saved = EvidenceWriter(conn, ws, user, originals=store).save(
        page, extracted, {'acquisition_method': method, 'import': 'manual'} if method != 'unknown'
        else {'acquisition_method': method})
    metadata = version(conn, saved)['metadata']
    assert metadata['original_retained'] is False
    assert metadata['original_retention_status'] == 'not_permitted'
    assert not metadata.get('retained_original')
    assert not store.root.exists()


@pytest.mark.parametrize('change', ['inactive', 'revoked', 'permission', 'foreign'])
def test_database_source_overrides_stale_or_forged_page_grants(conn, setup_original, change):
    ws, user, page, extracted, store = setup_original
    if change == 'inactive':
        conn.execute('update public.sources set is_active=false where id=%s', (page.source.id,))
    elif change == 'revoked':
        conn.execute("update public.sources set connector_config='{}' where id=%s", (page.source.id,))
    elif change == 'permission':
        conn.execute("update public.sources set permitted_operations=array['metadata'] where id=%s", (page.source.id,))
    else:
        # Source exists, but not in the writer's requested workspace. Foreign-key
        # rejection may stop the save; importantly it must never write its bytes.
        page = replace(page, source=replace(page.source, id=uuid4()))
    if change == 'foreign':
        with pytest.raises(ForeignKeyViolation):
            EvidenceWriter(conn, ws, user, originals=store).save(page, extracted)
    else:
        saved = EvidenceWriter(conn, ws, user, originals=store).save(page, extracted)
        assert version(conn, saved)['metadata']['original_retention_status'] == 'not_permitted'
    assert not store.root.exists()


def test_io_failure_preserves_text_and_passages_without_error_path(conn, setup_original):
    ws, user, page, extracted, store = setup_original
    store.root.write_text('not a directory')
    saved = EvidenceWriter(conn, ws, user, originals=store).save(page, extracted)
    row = version(conn, saved)
    assert row['extracted_text'] == extracted.text
    assert saved.passage_ids
    assert row['metadata']['original_retention_status'] == 'failed'
    assert row['metadata']['original_retained'] is False
    assert not row['metadata'].get('retained_original')
    assert str(store.root) not in str(row['metadata'])


def test_repeated_real_capture_can_add_retention_to_existing_version(conn, setup_original):
    ws, user, page, extracted, store = setup_original
    off = PrivateOriginalStore(store.root, RetentionPolicy())
    first = EvidenceWriter(conn, ws, user, originals=off).save(page, extracted)
    assert version(conn, first)['metadata']['original_retention_status'] == 'not_enabled'
    second = EvidenceWriter(conn, ws, user, originals=store).save(page, extracted)
    assert second.unchanged
    assert first.document_version_id == second.document_version_id
    assert version(conn, second)['metadata']['original_retained'] is True
    assert store.read(ws, version(conn, second)['metadata']['retained_original']) == page.body


def test_default_writer_uses_environment_opt_in_and_private_root(conn, setup_original, monkeypatch):
    ws, user, page, extracted, store = setup_original
    monkeypatch.setenv('MIRA_RETAIN_ORIGINALS', 'true')
    monkeypatch.setenv('MIRA_ORIGINALS_DIR', str(store.root))
    saved = EvidenceWriter(conn, ws, user).save(page, extracted)
    assert version(conn, saved)['metadata']['original_retained'] is True


def test_malformed_retention_configuration_cannot_discard_text(conn, setup_original):
    ws, user, page, extracted, store = setup_original
    conn.execute('update public.sources set connector_config=%s where id=%s', (Jsonb([1]), page.source.id))
    saved = EvidenceWriter(conn, ws, user, originals=store).save(page, extracted)
    row = version(conn, saved)
    assert row['extracted_text'] == extracted.text
    assert saved.passage_ids
    assert row['metadata']['original_retained'] is False
    assert row['metadata']['original_retention_status'] in {'not_permitted', 'failed'}
