const pageSize = 25;
const workspacePageSize = 100;
const sfcRoutes = {
  '/edistributionWeb/api/circular/content': ['EC', '/edistributionWeb/gateway/EN/circular/doc'],
  '/edistributionWeb/api/news/content': ['PR', '/edistributionWeb/gateway/EN/news-and-announcements/news/doc'],
};
const sfcIndexes = {
  '/edistributionWeb/api/circular/search': '/edistributionWeb/gateway/EN/circular/aml/',
  '/edistributionWeb/api/news/search': '/edistributionWeb/gateway/EN/news-and-announcements/news/',
  '/edistributionWeb/api/consultation/search': '/edistributionWeb/gateway/EN/consultation/',
  '/edistributionWeb/api/consultation/conclusion': '/edistributionWeb/gateway/EN/consultation/',
};

export function publisherUrl(value, source) {
  let url;
  try { url = new URL(value); }
  catch { return null; }
  if (url.protocol !== 'https:' || url.username || url.password || url.port) return null;
  if (source === 'hkma' && ['www.hkma.gov.hk', 'brdr.hkma.gov.hk'].includes(url.hostname)) return url.href;
  if (source !== 'sfc' || /\.pdf$/i.test(url.pathname)) return null;
  if (url.hostname === 'www.sfc.hk' && !url.pathname.includes('/api/')) return url.href;
  if (url.hostname !== 'apps.sfc.hk') return null;
  if (url.pathname.startsWith('/edistributionWeb/gateway/')) return url.href;
  const index = sfcIndexes[url.pathname];
  if (index) return new URL(index, url.origin).href;
  const route = sfcRoutes[url.pathname];
  if (!route || [...url.searchParams.keys()].length !== 2 || url.searchParams.get('lang') !== 'EN') return null;
  const [prefix, path] = route;
  const reference = url.searchParams.get('refNo');
  if (!new RegExp('^[0-9]{2}' + prefix + '[0-9]+$').test(reference ?? '')) return null;
  const reader = new URL(path, url.origin);
  reader.searchParams.set('refNo', reference);
  return reader.href;
}

export function createReportApi(config, request = fetch) {
  const project = new URL(config.url);
  const hosted = project.protocol === 'https:' && project.hostname.endsWith('.supabase.co');
  const local = project.origin === globalThis.location?.origin && project.hostname === '127.0.0.1';
  if ((!hosted && !local) || !config.key?.startsWith('sb_publishable_')) {
    throw new Error('Invalid report configuration');
  }

  async function send(path, { token, method = 'GET', query, body } = {}) {
    const url = new URL(path, project.origin);
    if (query) url.search = new URLSearchParams(query);
    const headers = { apikey: config.key };
    if (token) headers.Authorization = 'Bearer ' + token;
    if (body) headers['Content-Type'] = 'application/json';
    const response = await request(url, {
      method, headers, cache: 'no-store', redirect: 'error', credentials: 'omit',
      body: body && JSON.stringify(body),
    });
    if (!response.ok) {
      const error = new Error('Report service request failed');
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }

  return {
    signIn(email, password) {
      return send('/auth/v1/token', {
        method: 'POST', query: { grant_type: 'password' }, body: { email, password },
      });
    },
    signOut(token) {
      return send('/auth/v1/logout', { token, method: 'POST', query: { scope: 'local' } });
    },
    async listWorkspaces(token) {
      const workspaces = [];
      while (true) {
        const batch = await send('/rest/v1/workspaces', {
          token, query: { select: 'id,name', order: 'name.asc,id.asc', limit: workspacePageSize, offset: workspaces.length },
        });
        workspaces.push(...batch);
        if (batch.length < workspacePageSize) return workspaces;
      }
    },
    async listReports(token, workspace, page) {
      const query = {
        select: 'id,workspace_id,created_at,review_state,request:prepared_report_requests!inner(brief)',
        order: 'created_at.desc,id.desc',
        limit: pageSize + 1,
        offset: page * pageSize,
      };
      if (workspace) query.workspace_id = 'eq.' + workspace;
      const rows = await send('/rest/v1/prepared_reports', { token, query });
      return { reports: rows.slice(0, pageSize), hasMore: rows.length > pageSize };
    },
    async listSources(token, workspace, page) {
      const query = {
        select: 'id,workspace_id,title,canonical_url,source:sources!inner(source_key),versions:document_versions(published_at)',
        'source.jurisdiction_code': 'eq.HK',
        'source.source_key': 'in.(hkma,sfc)',
        'source.is_active': 'eq.true',
        'source.permitted_operations': 'cs.{metadata}',
        'versions.order': 'published_at.desc.nullslast',
        'versions.limit': 1,
        canonical_url: 'not.is.null',
        order: 'title.asc,id.asc',
        limit: pageSize + 1,
        offset: page * pageSize,
      };
      if (workspace) query.workspace_id = 'eq.' + workspace;
      const rows = await send('/rest/v1/documents', { token, query });
      return { rows: rows.slice(0, pageSize), hasMore: rows.length > pageSize };
    },
    async getReport(token, workspace, reportId) {
      const rows = await send('/rest/v1/prepared_reports', {
        token,
        query: {
          select: 'id,workspace_id,html,content_sha256',
          workspace_id: 'eq.' + workspace,
          id: 'eq.' + reportId,
          limit: 1,
        },
      });
      if (rows.length !== 1 || rows[0].id !== reportId || rows[0].workspace_id !== workspace) {
        throw new Error('Report unavailable');
      }
      return rows[0];
    },
  };
}

export async function verifyReportHtml(artifact) {
  if (typeof artifact.html !== 'string' || !artifact.html) throw new Error('Report unavailable');
  const bytes = new TextEncoder().encode(artifact.html);
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hex = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
  if (hex !== artifact.content_sha256) throw new Error('Report integrity check failed');
  return artifact.html;
}
