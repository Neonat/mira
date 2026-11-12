import { createReportApi } from './reports-api.mjs';

const $ = id => document.getElementById(id);
const form = $('sign-in');
const workspace = $('workspace');
const buttons = Array.from(document.querySelectorAll('[data-decision]'));
const date = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeZone: 'UTC' });
let api;
let session;
let generation = 0;
let remaining = [];
let active;
let report;

function status(text) {
  $('status').textContent = text;
}

function formatDate(value) {
  const time = value ? Date.parse(value) : NaN;
  return Number.isFinite(time) ? date.format(time) : '';
}

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function citationItem(citation) {
  const item = document.createElement('li');
  const title = element('strong', citation.title);
  if (citation.url) {
    const link = element('a', citation.title);
    link.href = citation.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    title.replaceChildren(link);
  }
  const meta = element('p', [
    citation.source, formatDate(citation.published_at), citation.page_number ? 'PDF page ' + citation.page_number : '',
  ].filter(Boolean).join(' · '));
  meta.className = 'muted';
  item.append(title, meta, element('blockquote', citation.quote));
  return item;
}

function clearCase() {
  active = undefined;
  $('case').hidden = true;
  $('case-title').textContent = '';
  $('finding').textContent = '';
  $('citations').replaceChildren();
}

function reset(message) {
  generation++;
  session = undefined;
  remaining = [];
  report = undefined;
  workspace.replaceChildren();
  workspace.disabled = false;
  clearCase();
  $('queue').hidden = true;
  form.hidden = false;
  status(message);
}

function showError(error, message) {
  if (error.status === 401) reset('Your session expired. Sign in again.');
  else status(message);
}

async function nextCase(version, message = '') {
  clearCase();
  status(message ? message + ' Loading next finding…' : 'Loading finding…');
  const token = session.token;
  const workspaceId = workspace.value;
  while (remaining.length && version === generation) {
    const item = remaining[0];
    const evidence = await api.getHongKongReviewEvidence(token, workspaceId, item);
    if (version !== generation) return;
    remaining.shift();
    if (!evidence.length || !item.fact?.content) continue;
    active = item;
    $('case-title').textContent = item.fact.title || 'Prepared finding';
    $('finding').textContent = item.fact.content;
    const reportDate = formatDate(report.created_at);
    $('case-date').textContent = reportDate ? 'Prepared report · ' + reportDate : '';
    $('citations').replaceChildren(...evidence.map(citationItem));
    $('case').hidden = false;
    $('case-title').focus();
    status(message);
    return;
  }
  if (version === generation) {
    status([message, 'No more published Hong Kong findings with available evidence are awaiting review.'].filter(Boolean).join(' '));
  }
}

async function openWorkspace() {
  const version = ++generation;
  clearCase();
  remaining = [];
  report = undefined;
  if (!workspace.value) {
    status('This account has no workspace access.');
    return;
  }
  status('Loading the Hong Kong review queue…');
  const { token, userId } = session;
  try {
    const [data, canReview] = await Promise.all([
      api.listHongKongReviewCases(token, workspace.value),
      api.canReview(token, workspace.value, userId),
    ]);
    if (version !== generation) return;
    report = data.report;
    remaining = data.cases;
    $('choices').hidden = !canReview;
    $('view-only').hidden = canReview;
    $('next').textContent = canReview ? 'Skip for now' : 'Next finding';
    if (!report) {
      status('This workspace has no published Hong Kong prepared report.');
      return;
    }
    if (!data.publishedCount) {
      status('The latest Hong Kong report has no findings in the published review queue.');
      return;
    }
    await nextCase(version);
  } catch (error) {
    if (version === generation) showError(error, 'The Hong Kong review queue could not be loaded. Select the workspace again or sign in again.');
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const submit = form.querySelector('button');
  submit.disabled = true;
  status('Signing in…');
  try {
    const result = await api.signIn(form.elements.email.value.trim(), form.elements.password.value);
    form.elements.password.value = '';
    if (!result.access_token || !result.user?.id) throw new Error('Invalid session');
    session = { token: result.access_token, userId: result.user.id };
    const workspaces = await api.listWorkspaces(session.token);
    for (const entry of workspaces) workspace.add(new Option(entry.name, entry.id));
    const hongKong = workspaces.find(entry => /hong kong|\bhk\b/i.test(entry.name));
    if (hongKong) workspace.value = hongKong.id;
    form.hidden = true;
    $('queue').hidden = false;
    await openWorkspace();
  } catch (error) {
    reset(error.status === 400 || error.status === 401 ? 'Sign-in failed. Check your email and password.' : 'Could not sign in to Mira. Try again.');
  } finally {
    submit.disabled = false;
  }
});

workspace.addEventListener('change', openWorkspace);
$('sign-out').addEventListener('click', () => {
  const token = session?.token;
  reset('Signed out.');
  if (token) void api.signOut(token).catch(() => {});
  form.elements.email.focus();
});
$('next').addEventListener('click', async () => {
  const version = generation;
  try {
    await nextCase(version);
  } catch (error) {
    if (version === generation) showError(error, 'The next finding could not be loaded. Sign in again to reload the queue.');
  }
});
for (const button of buttons) {
  button.addEventListener('click', async () => {
    if (!active || button.disabled) return;
    const version = generation;
    const item = active;
    const controls = [...buttons, workspace, $('next')];
    for (const control of controls) control.disabled = true;
    status('Saving evidence decision…');
    try {
      await api.saveEvidenceReview(session.token, item, button.dataset.decision);
    } catch (error) {
      if (version === generation) {
        for (const control of controls) control.disabled = false;
        showError(error, error.status === 403 ? 'Your account cannot save decisions in this workspace.' : 'Mira could not confirm the save. Reload the queue before retrying.');
        if (error.status !== 401 && error.status !== 403) clearCase();
      }
      return;
    }
    if (version !== generation) return;
    for (const control of controls) control.disabled = false;
    try {
      await nextCase(version, 'Evidence decision saved.');
    } catch (error) {
      if (version === generation) showError(error, 'Evidence decision saved. Sign in again to reload the queue.');
    }
  });
}

try {
  const response = await fetch('./config.json', { cache: 'no-store', redirect: 'error' });
  if (!response.ok) throw new Error('Mira configuration unavailable');
  api = createReportApi(await response.json());
  reset('Sign in with your Mira workspace account.');
} catch {
  status('Mira sign-in is unavailable. Refresh to try again.');
}
