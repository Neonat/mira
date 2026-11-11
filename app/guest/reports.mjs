import { createReportApi, publisherUrl, verifyReportHtml } from './reports-api.mjs';

const elements = Object.fromEntries(
  ['status', 'sign-in', 'library', 'workspace', 'reports', 'pages', 'previous', 'next', 'page-number',
    'preview', 'preview-heading', 'report-frame', 'download', 'close', 'sign-out',
    'show-reports', 'show-sources', 'source-note']
    .map(id => [id, document.getElementById(id)]),
);
const form = elements['sign-in'];
const markets = new Intl.DisplayNames(['en'], { type: 'region' });
const date = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeZone: 'UTC' });
let api;
let token;
let workspaces = new Map();
let page = 0;
let view = 'reports';
let listVersion = 0;
let previewVersion = 0;
let downloadUrl;
let previewButton;

function status(message) {
  elements.status.textContent = message;
}

function clearPreview() {
  previewVersion += 1;
  elements.preview.hidden = true;
  elements['report-frame'].removeAttribute('srcdoc');
  elements.download.removeAttribute('href');
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  downloadUrl = undefined;
  previewButton = undefined;
}

function reset(message) {
  token = undefined;
  listVersion += 1;
  workspaces.clear();
  elements.workspace.replaceChildren();
  elements.reports.replaceChildren();
  elements.pages.hidden = true;
  setView('reports');
  clearPreview();
  elements.library.hidden = true;
  form.hidden = false;
  status(message);
}

function handleFailure(error, message) {
  if (error.status === 401) reset('Your session expired. Sign in again.');
  else status(message);
}

function reportLabel(report) {
  const brief = report.request?.brief ?? {};
  const countries = (Array.isArray(brief.jurisdictions) ? brief.jurisdictions : [])
    .filter(code => typeof code === 'string' && /^[A-Z]{2}$/.test(code))
    .map(code => markets.of(code));
  return [countries.join(', '), brief.topic].filter(Boolean).join(' · ') || 'Prepared report';
}

async function openReport(report, label, button) {
  clearPreview();
  const version = previewVersion;
  const session = token;
  previewButton = button;
  status('Loading report…');
  try {
    const artifact = await api.getReport(session, report.workspace_id, report.id);
    const html = await verifyReportHtml(artifact);
    if (version !== previewVersion || session !== token) return;

    // The opaque frame cannot access the report library or execute report scripts.
    const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'";
    elements['report-frame'].srcdoc = '<!doctype html><meta http-equiv="Content-Security-Policy" content="'
      + policy + '"><meta name="referrer" content="no-referrer">' + html.replace(/^\s*<!doctype html>/i, '');
    downloadUrl = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    elements.download.href = downloadUrl;
    elements.download.download = 'mira-report-' + report.id + '.html';
    elements['preview-heading'].textContent = label;
    elements.preview.hidden = false;
    elements['preview-heading'].focus();
    status('');
  } catch (error) {
    if (version === previewVersion && session === token) {
      handleFailure(error, 'This report could not be opened.');
    }
  }
}

function reportRow(report) {
  const label = reportLabel(report);
  const item = document.createElement('li');
  const text = document.createElement('div');
  const title = document.createElement('strong');
  title.textContent = label;
  const detail = document.createElement('p');
  const review = report.review_state === 'human_checked' ? 'Evidence checked' : 'Human review pending';
  detail.textContent = [workspaces.get(report.workspace_id), date.format(new Date(report.created_at)), review].join(' · ');
  text.append(title, detail);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'secondary-action';
  button.textContent = 'Open report';
  button.setAttribute('aria-label', 'Open ' + label);
  button.addEventListener('click', () => openReport(report, label, button));
  item.append(text, button);
  return item;
}

function sourceRow(source) {
  const item = document.createElement('li');
  const text = document.createElement('div');
  const title = document.createElement('strong');
  title.textContent = source.title;
  const detail = document.createElement('p');
  const key = source.source?.source_key;
  const publisher = key === 'hkma' ? 'Hong Kong Monetary Authority' : 'Securities and Futures Commission';
  const published = source.versions?.[0]?.published_at;
  detail.textContent = [publisher, published && date.format(new Date(published))].filter(Boolean).join(' · ');
  text.append(title, detail);
  const destination = publisherUrl(source.canonical_url, key);
  if (destination) {
    const link = document.createElement('a');
    link.className = 'publisher-link';
    link.href = destination;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = key === 'sfc' && destination.endsWith('/') ? 'Open publisher index' : 'Open publisher';
    link.setAttribute('aria-label', link.textContent + ': ' + source.title);
    text.append(link);
    if (key === 'sfc') {
      const notice = document.createElement('p');
      const disclaimer = document.createElement('a');
      disclaimer.href = 'https://www.sfc.hk/en/Quick-links/Others/Disclaimer';
      disclaimer.target = '_blank';
      disclaimer.rel = 'noopener noreferrer';
      disclaimer.textContent = 'Disclaimer';
      notice.append('You should pay careful attention to the ', disclaimer, ' on the SFC’s website when referring to information using this link.');
      text.append(notice);
    }
  }
  item.append(text);
  return item;
}

function setView(next) {
  view = next;
  elements['show-reports'].setAttribute('aria-pressed', String(view === 'reports'));
  elements['show-sources'].setAttribute('aria-pressed', String(view === 'sources'));
  elements['source-note'].hidden = view !== 'sources';
  elements.reports.setAttribute('aria-label', view === 'sources' ? 'Sources' : 'Reports');
}

async function loadLibrary(nextPage) {
  clearPreview();
  const version = ++listVersion;
  const session = token;
  const workspace = elements.workspace.value;
  const sources = view === 'sources';
  page = nextPage;
  elements.reports.replaceChildren();
  elements.pages.hidden = true;
  status(sources ? 'Loading sources…' : 'Loading reports…');
  try {
    const data = await (sources ? api.listSources(session, workspace, page) : api.listReports(session, workspace, page));
    if (version !== listVersion || session !== token) return;
    const rows = sources ? data.rows : data.reports;
    const visible = rows.filter(row => workspaces.has(row.workspace_id) && (!workspace || row.workspace_id === workspace));
    elements.reports.replaceChildren(...visible.map(sources ? sourceRow : reportRow));
    elements.previous.disabled = page === 0;
    elements.next.disabled = !data.hasMore;
    elements['page-number'].textContent = 'Page ' + (page + 1);
    elements.pages.hidden = page === 0 && !data.hasMore;
    const emptyMessage = sources ? 'No published sources for this workspace.' : 'No saved reports in this workspace.';
    status(visible.length ? '' : emptyMessage);
  } catch (error) {
    if (version === listVersion && session === token) {
      handleFailure(error, sources ? 'Sources could not be loaded.' : 'Reports could not be loaded.');
    }
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const submit = form.querySelector('button');
  const { email, password } = form.elements;
  submit.disabled = true;
  status('Signing in…');
  try {
    const pending = api.signIn(email.value, password.value);
    password.value = '';
    const session = await pending;
    const available = await api.listWorkspaces(session.access_token);
    token = session.access_token;
    workspaces = new Map(available.map(row => [row.id, row.name]));
    elements.workspace.replaceChildren(new Option('All my workspaces', ''), ...available.map(row => new Option(row.name, row.id)));
    elements.workspace.disabled = available.length === 0;
    elements['show-reports'].disabled = available.length === 0;
    elements['show-sources'].disabled = available.length === 0;
    form.hidden = true;
    elements.library.hidden = false;
    if (available.length) await loadLibrary(0);
    else status('This account has no Mira workspace memberships.');
  } catch {
    reset('Sign-in could not be completed. Check your credentials and try again.');
  } finally {
    password.value = '';
    submit.disabled = false;
  }
});

for (const name of ['reports', 'sources']) {
  elements['show-' + name].addEventListener('click', () => {
    setView(name);
    loadLibrary(0);
  });
}
elements.workspace.addEventListener('change', () => loadLibrary(0));
elements.previous.addEventListener('click', () => loadLibrary(page - 1));
elements.next.addEventListener('click', () => loadLibrary(page + 1));
elements.close.addEventListener('click', () => {
  const opener = previewButton;
  clearPreview();
  opener?.focus();
});
elements['sign-out'].addEventListener('click', () => {
  const session = token;
  reset('Signed out.');
  if (session) api.signOut(session).catch(() => {});
});

try {
  const response = await fetch('./config.json', { cache: 'no-store', redirect: 'error' });
  if (!response.ok) throw new Error('Report configuration unavailable');
  api = createReportApi(await response.json());
  reset('Sign in with your Mira account.');
} catch {
  status('Mira is temporarily unavailable.');
}
