"""Expanded URL discovery passes through real save/check/review, with no live calls."""
from functools import partial
import pytest

from mira.agents.scout import WebScout
from mira.discovery import ExaDiscovery
from mira.contracts import ReportSnapshot
from mira.render import render_signed_off
from test_pipeline_db import DSN, conn, workspace, analyst, run_hk, review_all_findings
from test_evidence_integrity_db import sign_off

pytestmark = pytest.mark.skipif(not DSN, reason='MIRA_TEST_DATABASE_URL not set')


def test_discovery_only_publication_is_saved_verified_and_frozen(conn, workspace, tmp_path, monkeypatch):
    import test_pipeline_db as fixtures
    from mira.fetch import RawResponse
    target = 'https://brdr.hkma.gov.hk/eng/doc-ldg/current/TEST-1'
    # None of the permitted seed pages exposes the publication in this scenario.
    for url in list(fixtures.PAGES):
        if url != target and not url.endswith('.pdf'):
            monkeypatch.setitem(fixtures.PAGES, url, RawResponse(200, fixtures.HTML,
                b'<main><h1>Publications index</h1><p>No links in the static index.</p></main>'))
    discovery = ExaDiscovery(search=lambda query, count, timeout: [
        {'url': target, 'title': 'AML controls publication', 'publishedDate': '2025-12-12'},
        {'url': 'https://private.invalid/secret', 'title': 'Forbidden result'},
    ])
    monkeypatch.setattr(fixtures, 'WebScout', partial(WebScout, max_rounds=1, discovery=discovery))
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == 'draft', outcome.reasons
    rows = conn.execute('select source_url, metadata from public.document_versions where workspace_id=%s',
                        (ctx.workspace_id,)).fetchall()
    assert any(row['source_url'] == target for row in rows)
    assert all('private.invalid' not in row['source_url'] for row in rows)
    assert conn.execute('select count(*) as n from public.claim_checks where analysis_run_id=%s and verdict=%s',
                        (ctx.analysis_run_id, 'supported')).fetchone()['n'] >= 2
    review_all_findings(conn, ctx, ctx.user_id)
    signed = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(signed['evidence_snapshot'])
    assert any(p.source_url == target for p in snapshot.evidence_bundle.passages.values())
    html = render_signed_off(snapshot, generated_at=signed['generated_at'])
    assert target in html and 'enhanced due diligence' in html
    assert any(fixtures.CIRCULAR_TEXT in p.content for p in snapshot.evidence_bundle.passages.values())


def test_same_capture_changed_extraction_creates_immutable_version(conn, workspace):
    from datetime import UTC, datetime
    from mira.evidence import EvidenceWriter
    from mira.extract import Extracted
    from mira.fetch import FetchedPage
    from mira.pg_store import PostgresStore
    ws, user = workspace
    source = next(s for s in PostgresStore(conn).list_sources(ws) if s.name == 'HKMA')
    page = FetchedPage('https://www.hkma.gov.hk/extraction-fixture',
                       'https://www.hkma.gov.hk/extraction-fixture', source, 'html', 'text/html',
                       b'<main>same captured bytes</main>', datetime.now(UTC))
    writer = EvidenceWriter(conn, ws, user)
    first = writer.save(page, Extracted('Original', 'complete', ['Original passage on AML controls.']))
    second = writer.save(page, Extracted('Improved', 'complete', ['Improved passage on AML controls.']))
    assert first.document_id == second.document_id
    assert first.document_version_id != second.document_version_id
    rows = conn.execute('select extracted_text, metadata from public.document_versions where document_id=%s order by version_number',
                        (first.document_id,)).fetchall()
    assert 'Original passage' in rows[0]['extracted_text']
    assert 'Improved passage' in rows[1]['extracted_text']
    assert rows[0]['metadata']['capture_sha256'] == rows[1]['metadata']['capture_sha256']
    assert rows[0]['metadata']['extraction_sha256'] != rows[1]['metadata']['extraction_sha256']
    again = writer.save(page, Extracted('Improved', 'complete', ['Improved passage on AML controls.']))
    assert again.unchanged and again.document_version_id == second.document_version_id


def test_review_freezes_capture_context_without_live_metadata(conn, workspace, tmp_path):
    ctx, outcome = run_hk(conn, workspace, tmp_path, analyst)
    assert outcome.status == 'draft', outcome.reasons
    review_all_findings(conn, ctx, ctx.user_id)
    signed = sign_off(conn, ctx)
    snapshot = ReportSnapshot.model_validate(signed['evidence_snapshot'])
    passages = list(snapshot.evidence_bundle.passages.values())
    assert passages and all(p.acquisition_provenance['capture_sha256'] for p in passages)
    assert all(p.acquisition_provenance['original_retained'] is False for p in passages)
    original = render_signed_off(snapshot, generated_at=signed['generated_at'])
    conn.execute("update public.document_versions set metadata='{}'::jsonb where workspace_id=%s", (ctx.workspace_id,))
    assert render_signed_off(snapshot, generated_at=signed['generated_at']) == original
