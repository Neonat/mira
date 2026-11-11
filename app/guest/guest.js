const link = location.hash.slice(1);
const elements = Object.fromEntries(
  ["title", "scope", "window", "status", "generate", "open", "download", "report"]
    .map(id => [id, document.getElementById(id)])
);
const markets = {HK: "Hong Kong", AU: "Australia", AE: "United Arab Emirates"};
let config;
let receipt;
let previewUrl;
let downloadUrl;
let stopped = false;

async function rpc(name, input) {
  const headers = {"Content-Type": "application/json", apikey: config.key};
  if (config.key.startsWith("eyJ")) headers.Authorization = "Bearer " + config.key;
  const response = await fetch(new URL("/rest/v1/rpc/" + name, config.url), {
    method: "POST", headers, cache: "no-store",
    body: JSON.stringify({p_link: link, ...input})
  });
  if (!response.ok) throw new Error("Guest request could not be completed");
  return response.json();
}

function clearReport() {
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
  clearReport();
  elements.generate.hidden = true;
  elements.window.hidden = true;
  elements.status.textContent = "This guest link is unavailable. Ask the host for a current link.";
}

function result(includeHtml) {
  return rpc("guest_demo_result", {p_receipt: receipt, p_include_html: includeHtml});
}

async function updateStatus() {
  if (stopped) return;
  try {
    const state = receipt ? await result(false) : await rpc("guest_demo_info");
    if (!state) {
      if (receipt && await rpc("guest_demo_info")) {
        elements.generate.disabled = false;
        elements.generate.hidden = false;
        elements.status.textContent = "Generate a draft using the saved evidence.";
      } else {
        closed();
      }
    } else if (receipt) {
      if (state.status === "ready") {
        elements.status.textContent = "Your draft is ready.";
        elements.open.hidden = false;
      } else if (["queued", "generating"].includes(state.status)) {
        elements.status.textContent = "Preparing your report…";
      } else {
        clearReport();
        elements.status.textContent = "This report is unavailable. Please ask the host.";
      }
    }
  } catch {
    clearReport();
    elements.status.textContent = "Connection interrupted. Reconnecting…";
  }
  if (!stopped) setTimeout(updateStatus, receipt && elements.open.hidden ? 900 : 5000);
}

async function start() {
  if (!/^[0-9a-f]{64}$/.test(link)) return closed();
  try {
    const response = await fetch("config.json", {cache: "no-store"});
    config = await response.json();
    const info = await rpc("guest_demo_info");
    if (!info) return closed();
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
    }
    updateStatus();
  } catch {
    elements.status.textContent = "The demo could not connect. Refresh the page or ask the host.";
  }
}

elements.generate.addEventListener("click", async () => {
  elements.generate.disabled = true;
  elements.status.textContent = "Submitting…";
  if (!receipt) {
    receipt = Array.from(crypto.getRandomValues(new Uint8Array(32)), byte => byte.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem("mira-report:" + link, receipt);
  }
  try {
    const status = await rpc("guest_demo_submit", {p_receipt: receipt});
    if (!status) return closed();
    if (status === "capacity") {
      stopped = true;
      elements.generate.hidden = true;
      elements.status.textContent = "This demo has reached its report limit. Please ask the host.";
      return;
    }
    elements.generate.hidden = true;
    elements.status.textContent = "Preparing your report…";
  } catch {
    elements.generate.disabled = false;
    elements.status.textContent = "Submission interrupted. Try again.";
  }
});

elements.open.addEventListener("click", async () => {
  elements.open.disabled = true;
  try {
    const response = await result(true);
    if (stopped) return;
    if (!response) return closed();
    if (!response.html) return clearReport();
    clearReport();
    const policy = "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">";
    const content = response.html.replace("<head>", "<head>" + policy);
    const type = "text/html;charset=utf-8";
    previewUrl = URL.createObjectURL(new Blob([content], {type}));
    downloadUrl = URL.createObjectURL(new Blob([response.html], {type}));
    elements.download.href = downloadUrl;
    elements.download.hidden = false;
    elements.report.src = previewUrl;
    elements.report.hidden = false;
    elements.report.scrollIntoView({block: "start"});
  } catch {
    elements.status.textContent = "Could not open the report. Try again.";
  } finally {
    elements.open.disabled = false;
  }
});

start();
