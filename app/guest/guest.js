const link = location.hash.slice(1);
const elements = Object.fromEntries(
  ["title", "scope", "window", "status", "loading", "markets", "generate", "open", "download", "report", "reader", "close-reader", "reader-report"]
    .map(id => [id, document.getElementById(id)])
);
const markets = {HK: "Hong Kong", AU: "Australia", AE: "United Arab Emirates"};
let config;
let receipt;
let previewUrl;
let downloadUrl;
let stopped = false;
let submitting = false;
let statusTimer;
let expiryTimer;
let submissionVersion = 0;

async function rpc(name, input, token = link) {
  const headers = {"Content-Type": "application/json", apikey: config.key};
  if (config.key.startsWith("eyJ")) headers.Authorization = "Bearer " + config.key;
  const response = await fetch(new URL("/rest/v1/rpc/" + name, config.url), {
    method: "POST", headers, cache: "no-store",
    body: JSON.stringify(token === null ? input : {p_link: token, ...input})
  });
  if (!response.ok) {
    const error = new Error("Guest request could not be completed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function clearReport() {
  if (elements.reader.open) elements.reader.close();
  elements["reader-report"].removeAttribute("src");
  elements.report.hidden = true;
  elements.report.removeAttribute("src");
  elements.download.hidden = true;
  elements.download.removeAttribute("href");
  elements.open.hidden = true;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  previewUrl = undefined;
  downloadUrl = undefined;
}

function closed() {
  stopped = true;
  clearTimeout(statusTimer);
  clearTimeout(expiryTimer);
  clearReport();
  elements.loading.hidden = true;
  elements.generate.hidden = true;
  elements.window.hidden = true;
  elements.status.textContent = "This guest link is unavailable. Ask the host for a current link.";
}

function result(includeHtml) {
  return rpc("guest_demo_result", {p_receipt: receipt, p_include_html: includeHtml});
}

async function updateStatus() {
  if (stopped || submitting) return;
  const version = submissionVersion;
  const isCurrent = () => !stopped && !submitting && version === submissionVersion;
  try {
    const state = receipt ? await result(!previewUrl) : await rpc("guest_demo_info");
    if (!isCurrent()) return;
    if (!state) {
      const info = receipt && await rpc("guest_demo_info");
      if (!isCurrent()) return;
      if (info) {
        elements.generate.disabled = false;
        elements.generate.hidden = false;
        elements.status.textContent = "Generate a draft using the saved evidence.";
      } else {
        closed();
      }
    } else if (receipt) {
      if (state.status === "ready") {
        elements.status.textContent = "Your draft is ready.";
        if (state.html) showReport(state.html);
      } else if (["queued", "generating"].includes(state.status)) {
        elements.status.textContent = "Preparing your report…";
      } else {
        clearReport();
        elements.status.textContent = "This report is unavailable. Please ask the host.";
      }
    }
  } catch {
    if (!isCurrent()) return;
    clearReport();
    elements.status.textContent = "Connection interrupted. Reconnecting…";
  }
  scheduleStatus();
}

function scheduleStatus() {
  clearTimeout(statusTimer);
  if (!stopped && !submitting) statusTimer = setTimeout(updateStatus, 5000 + Math.random() * 600);
}

function showMarkets(scopes) {
  elements.markets.replaceChildren();
  for (const scope of scopes) {
    const item = document.createElement("li");
    const option = document.createElement("a");
    option.href = "#" + scope.link;
    option.textContent = scope.jurisdictions.map(code => markets[code] || code).join(", ") + " · " + scope.topic;
    item.append(option);
    elements.markets.append(item);
  }
  elements.title.textContent = "Choose a guest report";
  elements.status.textContent = "Choose a market to generate a draft from saved evidence.";
  elements.markets.hidden = false;
}

async function showPortal(key) {
  try {
    const scopes = await rpc("guest_demo_portal_info", {p_key: key}, null);
    if (scopes.length) {
      showMarkets(scopes);
    } else {
      elements.markets.hidden = true;
      elements.markets.replaceChildren();
      elements.title.textContent = "Guest access is closed";
      elements.status.textContent = "This QR code will work when the host opens the next session.";
    }
  } catch {
    elements.markets.hidden = true;
    elements.status.textContent = "Could not check guest access. Reconnecting…";
  }
  setTimeout(() => showPortal(key), 10000 + Math.random() * 1500);
}

async function start() {
  const portal = link.match(/^demo-([0-9a-f]{64})$/);
  const tokens = link.split(",");
  if (!portal && (tokens.length > 3 || !tokens.every(token => /^[0-9a-f]{64}$/.test(token)))) return closed();
  try {
    const response = await fetch("config.json", {cache: "no-store"});
    config = await response.json();
    if (portal) return await showPortal(portal[1]);
    if (tokens.length > 1) {
      const scopes = await Promise.all(tokens.map(async token => {
        const info = await rpc("guest_demo_info", {}, token);
        return info && {...info, link: token};
      }));
      if (!scopes.some(Boolean)) return closed();
      showMarkets(scopes.filter(Boolean));
      return;
    }
    const info = await rpc("guest_demo_info");
    if (!info) return closed();
    expiryTimer = setTimeout(closed, Math.max(0, new Date(info.expires_at) - Date.now()));
    const names = info.jurisdictions.map(code => markets[code] || code).join(", ");
    elements.title.textContent = names + " guest report";
    elements.scope.textContent = info.topic + " · " + info.period_start + " to " + info.period_end;
    elements.scope.hidden = false;
    elements.window.textContent = "Guest access ends at " + new Date(info.expires_at).toLocaleTimeString(
      [], {hour: "numeric", minute: "2-digit", timeZoneName: "short"}
    );
    elements.window.hidden = false;
    receipt = sessionStorage.getItem("mira-report:" + link);
    if (!receipt) {
      elements.status.textContent = "Generate a draft using the saved evidence.";
      elements.generate.hidden = false;
      scheduleStatus();
    } else {
      updateStatus();
    }
  } catch {
    elements.status.textContent = "The demo could not connect. Refresh the page or ask the host.";
  }
}

elements.generate.addEventListener("click", async () => {
  if (stopped || submitting) return;
  submitting = true;
  submissionVersion += 1;
  clearTimeout(statusTimer);
  elements.generate.disabled = true;
  elements.generate.hidden = true;
  elements.loading.hidden = false;
  elements.status.textContent = "Preparing your report…";
  if (!receipt) {
    receipt = Array.from(crypto.getRandomValues(new Uint8Array(32)), byte => byte.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem("mira-report:" + link, receipt);
  }
  try {
    const deadline = performance.now() + 12000;
    let response;
    do {
      try {
        response = await rpc("guest_demo_generate", {p_receipt: receipt});
      } catch (error) {
        if (!(error.status >= 500 || error.status === 429)) throw error;
        response = {status: "busy"};
      }
      if (stopped) return;
      if (response?.status !== "busy") break;
      elements.status.textContent = "Waiting for a report slot…";
      await new Promise(resolve => setTimeout(resolve, 500 + Math.random() * 350));
    } while (!stopped && performance.now() < deadline);
    if (stopped) return;
    if (!response) return closed();
    if (response.status === "capacity") {
      stopped = true;
      elements.status.textContent = "This demo has reached its report limit. Please ask the host.";
      return;
    }
    if (response.status === "ready" && response.html) {
      showReport(response.html);
    } else if (response.status === "busy") {
      elements.status.textContent = "The demo is busy. Tap Generate report to try again.";
      elements.generate.hidden = false;
    } else {
      elements.status.textContent = "Preparing your report…";
    }
  } catch {
    if (!stopped) {
      elements.generate.hidden = false;
      elements.status.textContent = "Submission interrupted. Try again.";
    }
  } finally {
    submitting = false;
    elements.generate.disabled = false;
    elements.loading.hidden = true;
    scheduleStatus();
  }
});

function showReport(html) {
  clearReport();
  const policy = "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">";
  const content = html.replace("<head>", "<head>" + policy);
  const type = "text/html;charset=utf-8";
  previewUrl = URL.createObjectURL(new Blob([content], {type}));
  downloadUrl = URL.createObjectURL(new Blob([html], {type}));
  elements.status.textContent = "Your draft is ready.";
  elements.download.href = downloadUrl;
  elements.download.hidden = false;
  elements.open.hidden = false;
  elements.report.src = previewUrl;
  elements.report.hidden = false;
}

elements.open.addEventListener("click", () => {
  if (!previewUrl || stopped) return;
  elements["reader-report"].src = previewUrl;
  elements.reader.showModal();
});
elements["close-reader"].addEventListener("click", () => elements.reader.close());
elements.reader.addEventListener("close", () => elements["reader-report"].removeAttribute("src"));
document.getElementById("guest-game")?.addEventListener("click", () => {
  try {
    sessionStorage.setItem("mira.guest-return", location.hash);
  } catch {
    // The game still links to the guest landing page when storage is blocked.
  }
});
window.addEventListener("hashchange", () => location.reload());

start();
