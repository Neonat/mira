import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { createReportApi, publisherUrl, verifyReportHtml } from '../app/guest/reports-api.mjs';

const config = { url: 'https://example.supabase.co', key: 'sb_publishable_fixture' };
const workspace = 'ec21099e-fc89-467a-a3ef-03409a6b762b';
const reportId = '85af748e-4b37-4d44-87df-b6991c7d4a77';

test('one session lists permitted workspaces and pages workspace-scoped report summaries', async () => {
  const calls = [];
  const api = createReportApi(config, async (url, options) => {
    calls.push({ url, options });
    if (url.pathname === '/auth/v1/token') return Response.json({ access_token: 'fixture-session' });
    if (url.pathname.endsWith('/workspaces')) return Response.json([{ id: workspace, name: 'Hong Kong' }]);
    return Response.json(Array.from({ length: 26 }, () => ({ id: reportId, workspace_id: workspace })));
  });

  const session = await api.signIn('viewer@example.test', 'fixture-password');
  assert.equal(session.access_token, 'fixture-session');
  assert.equal(calls[0].url.searchParams.get('grant_type'), 'password');
  assert.equal(calls[0].options.headers.apikey, config.key);
  assert.deepEqual(await api.listWorkspaces(session.access_token), [{ id: workspace, name: 'Hong Kong' }]);
  const result = await api.listReports(session.access_token, workspace, 1);
  assert.equal(result.reports.length, 25);
  assert.equal(result.hasMore, true);
  const summary = calls.at(-1);
  assert.equal(summary.options.headers.Authorization, 'Bearer fixture-session');
  assert.equal(summary.url.searchParams.get('workspace_id'), 'eq.' + workspace);
  assert.equal(summary.url.searchParams.get('offset'), '25');
  assert.doesNotMatch(summary.url.searchParams.get('select'), /(^|,)html(,|$)/);
});

test('artifact fetch binds both the report and workspace and checks the stored digest', async () => {
  const html = '<!doctype html><p>Hong Kong report</p>';
  const hash = createHash('sha256').update(html).digest('hex');
  const api = createReportApi(config, async (url, options) => {
    assert.equal(url.searchParams.get('workspace_id'), 'eq.' + workspace);
    assert.equal(url.searchParams.get('id'), 'eq.' + reportId);
    assert.equal(options.cache, 'no-store');
    return Response.json([{ id: reportId, workspace_id: workspace, html, content_sha256: hash }]);
  });
  const artifact = await api.getReport('fixture-session', workspace, reportId);
  assert.equal(await verifyReportHtml(artifact), html);
  await assert.rejects(verifyReportHtml({ ...artifact, html: '<p>different report</p>' }));
});

test('an absent artifact is unavailable and an expired session is distinguishable', async () => {
  const empty = createReportApi(config, async () => Response.json([]));
  await assert.rejects(empty.getReport('fixture-session', workspace, reportId));
  const expired = createReportApi(config, async () => new Response(null, { status: 401 }));
  await assert.rejects(expired.listReports('fixture-session', '', 0), { status: 401 });
  assert.throws(() => createReportApi({ ...config, url: 'https://example.test' }));
});

test('source browsing requests only permitted Hong Kong catalogue metadata', async () => {
  const api = createReportApi(config, async (url, options) => {
    assert.equal(url.pathname, '/rest/v1/documents');
    assert.equal(options.headers.Authorization, 'Bearer fixture-session');
    assert.equal(url.searchParams.get('workspace_id'), 'eq.' + workspace);
    assert.equal(url.searchParams.get('source.jurisdiction_code'), 'eq.HK');
    assert.equal(url.searchParams.get('source.source_key'), 'in.(hkma,sfc)');
    assert.equal(url.searchParams.get('source.is_active'), 'eq.true');
    assert.equal(url.searchParams.get('source.permitted_operations'), 'cs.{metadata}');
    assert.doesNotMatch(url.searchParams.get('select'), /extracted_text|connector_config|storage_path/);
    return Response.json([{ id: reportId, workspace_id: workspace, title: 'Hong Kong circular' }]);
  });
  const page = await api.listSources('fixture-session', workspace, 0);
  assert.equal(page.rows[0].title, 'Hong Kong circular');
  assert.equal(page.hasMore, false);
});

test('source links use public publisher pages and reject unapproved destinations', () => {
  const hkma = 'https://brdr.hkma.gov.hk/eng/doc-ldg/docId/20251106-2-EN';
  assert.equal(publisherUrl(hkma, 'hkma'), hkma);
  const sfc = 'https://apps.sfc.hk/edistributionWeb/api/circular/content?refNo=26EC69&lang=EN';
  assert.equal(publisherUrl(sfc, 'sfc'), 'https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/doc?refNo=26EC69');
  assert.equal(publisherUrl(sfc + '&other=1', 'sfc'), null);
  const circularIndex = 'https://apps.sfc.hk/edistributionWeb/api/circular/search?category=anti-money-laundering';
  assert.equal(publisherUrl(circularIndex, 'sfc'), 'https://apps.sfc.hk/edistributionWeb/gateway/EN/circular/aml/');
  assert.equal(publisherUrl('https://elsewhere.test/redirect', 'hkma'), null);
  assert.equal(publisherUrl('https://apps.sfc.hk/file.pdf', 'sfc'), null);
});

test('the live review queue uses the latest Hong Kong report and excludes reviewed findings', async () => {
  const calls = [];
  const finding = 'a9d74f41-55eb-46a9-bc96-ad16f1e87383';
  const snapshot = 'b653120a-d3ca-40bb-85dc-d07d983b45f0';
  const api = createReportApi(config, async (url, options) => {
    assert.equal(options.headers.Authorization, 'Bearer reviewer');
    assert.equal(url.searchParams.get('workspace_id'), 'eq.' + workspace);
    calls.push(url);
    if (url.pathname.endsWith('/prepared_reports')) return Response.json([{ id: reportId }]);
    if (url.pathname.endsWith('/prepared_report_bindings')) {
      return Response.json([{ snapshot_id: snapshot, finding_id: finding }]);
    }
    return Response.json([{ snapshot_id: snapshot, finding_id: finding, fact: { content: 'Saved finding' } }]);
  });
  const result = await api.listHongKongReviewCases('reviewer', workspace);
  assert.equal(calls[0].searchParams.get('request.brief->jurisdictions'), 'eq.["HK"]');
  assert.equal(calls[0].searchParams.get('order'), 'created_at.desc,id.desc');
  assert.equal(calls[1].searchParams.get('report_id'), 'eq.' + reportId);
  assert.equal(calls[2].searchParams.get('prepared_fact_reviews'), 'is.null');
  assert.equal(calls[2].searchParams.get('snapshot_id'), 'eq.' + snapshot);
  assert.equal(calls[2].searchParams.get('finding_id'), 'in.(' + finding + ')');
  assert.equal(result.publishedCount, 1);
  assert.equal(result.cases[0].fact.content, 'Saved finding');
});

test('review evidence must match the pinned version and an active quotable Hong Kong source', async () => {
  const passage = '9e30a1f4-5724-4882-bec8-31ffb4fe2c30';
  const source = 'ae0ad7f2-5e70-4a38-a28c-082734bb51b6';
  const version = 'b3f605db-5ef3-4e4f-9d18-4979b6606d94';
  const item = { snapshot_id: reportId, fact: { evidence: [{
    passage_id: passage, document_version_id: version, supporting_quote: 'Saved quote',
  }] } };
  let allowQuote = true;
  let pinned = version;
  const api = createReportApi(config, async (url) => {
    assert.equal(url.searchParams.get('workspace_id'), 'eq.' + workspace);
    if (url.pathname.endsWith('/prepared_snapshots')) {
      assert.equal(url.searchParams.get('id'), 'eq.' + reportId);
      assert.match(url.searchParams.get('select'), new RegExp('->' + passage + '->>title'));
      return Response.json([{ p0_title: 'Hong Kong publication', p0_source_id: source,
        p0_document_version_id: pinned, p0_source_url: 'https://www.hkma.gov.hk/eng/example/' }]);
    }
    assert.equal(url.searchParams.get('jurisdiction_code'), 'eq.HK');
    assert.equal(url.searchParams.get('is_active'), 'eq.true');
    assert.equal(url.searchParams.get('permitted_operations'), 'cs.{metadata,quote}');
    return Response.json(allowQuote ? [{ id: source, name: 'HKMA', source_key: 'hkma' }] : []);
  });
  const [evidence] = await api.getHongKongReviewEvidence('reviewer', workspace, item);
  assert.equal(evidence.quote, 'Saved quote');
  assert.equal(evidence.url, 'https://www.hkma.gov.hk/eng/example/');
  allowQuote = false;
  assert.deepEqual(await api.getHongKongReviewEvidence('reviewer', workspace, item), []);
  allowQuote = true;
  pinned = reportId;
  assert.deepEqual(await api.getHongKongReviewEvidence('reviewer', workspace, item), []);
});

test('viewer and reviewer permissions stay distinct and decisions use the existing review RPC', async () => {
  let role = 'viewer';
  const calls = [];
  const api = createReportApi(config, async (url, options) => {
    calls.push({ url, options });
    if (url.pathname.endsWith('/workspace_members')) return Response.json([{ role }]);
    return Response.json('recorded-review');
  });
  assert.equal(await api.canReview('viewer', workspace, reportId), false);
  role = 'reviewer';
  assert.equal(await api.canReview('reviewer', workspace, reportId), true);
  const item = { snapshot_id: reportId, finding_id: workspace };
  assert.throws(() => api.saveEvidenceReview('reviewer', item, 'escalated'), /Invalid decision/);
  assert.equal(await api.saveEvidenceReview('reviewer', item, 'accepted'), 'recorded-review');
  const { url, options } = calls.at(-1);
  assert.equal(url.pathname, '/rest/v1/rpc/review_prepared_fact');
  assert.equal(options.method, 'POST');
  assert.equal(options.headers.Authorization, 'Bearer reviewer');
  assert.deepEqual(JSON.parse(options.body), {
    p_snapshot: reportId, p_finding: workspace, p_decision: 'accepted', p_comment: null,
  });
});
