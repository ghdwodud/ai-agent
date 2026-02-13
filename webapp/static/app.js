const els = {
  baseUrl: document.getElementById("baseUrl"),
  token: document.getElementById("token"),
  saveConn: document.getElementById("saveConn"),
  connMsg: document.getElementById("connMsg"),
  goal: document.getElementById("goal"),
  cwd: document.getElementById("cwd"),
  provider: document.getElementById("provider"),
  maxSteps: document.getElementById("maxSteps"),
  startRun: document.getElementById("startRun"),
  runMsg: document.getElementById("runMsg"),
  runId: document.getElementById("runId"),
  loadRun: document.getElementById("loadRun"),
  togglePoll: document.getElementById("togglePoll"),
  status: document.getElementById("status"),
  eventCount: document.getElementById("eventCount"),
  finalText: document.getElementById("finalText"),
  pendingBox: document.getElementById("pendingBox"),
  events: document.getElementById("events"),
};

let pollTimer = null;
let currentPending = null;

function getStored(key, fallback = "") {
  const v = localStorage.getItem(key);
  return v == null ? fallback : v;
}

function setStored(key, value) {
  localStorage.setItem(key, value);
}

function config() {
  return {
    baseUrl: (els.baseUrl.value || "").trim().replace(/\/+$/, ""),
    token: (els.token.value || "").trim(),
  };
}

async function api(path, options = {}) {
  const { baseUrl, token } = config();
  if (!baseUrl || !token) {
    throw new Error("Base URL and Bearer token are required.");
  }
  const headers = Object.assign(
    {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    options.headers || {}
  );
  const res = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

function setMsg(el, text, bad = false) {
  el.textContent = text;
  el.style.color = bad ? "#b24c2d" : "#1f7a5a";
}

async function startRun() {
  try {
    const payload = {
      goal: els.goal.value.trim(),
      cwd: els.cwd.value.trim() || ".",
      provider: els.provider.value,
      max_steps: Number(els.maxSteps.value || "6"),
    };
    const data = await api("/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    els.runId.value = data.run_id;
    setMsg(els.runMsg, `Run started: ${data.run_id}`);
    await loadRun();
    startPolling();
  } catch (err) {
    setMsg(els.runMsg, String(err.message || err), true);
  }
}

async function loadRun() {
  const runId = (els.runId.value || "").trim();
  if (!runId) {
    setMsg(els.runMsg, "run_id is required.", true);
    return;
  }
  try {
    const [snap, events] = await Promise.all([
      api(`/runs/${runId}`),
      api(`/runs/${runId}/events`),
    ]);
    renderSnapshot(snap);
    renderEvents(events.items || []);
  } catch (err) {
    setMsg(els.runMsg, String(err.message || err), true);
  }
}

function renderSnapshot(snap) {
  els.status.textContent = snap.status || "-";
  els.eventCount.textContent = String(snap.event_count ?? "-");
  els.finalText.textContent = snap.final_text || "No final output yet.";
  currentPending = snap.pending || null;
  if (currentPending) {
    els.pendingBox.textContent = JSON.stringify(currentPending, null, 2);
  } else {
    els.pendingBox.textContent = "No pending approval.";
  }
}

function renderEvents(items) {
  els.events.textContent = JSON.stringify(items, null, 2);
}

async function sendApproval(decision) {
  if (!currentPending) {
    setMsg(els.runMsg, "No pending approval.", true);
    return;
  }
  const runId = (els.runId.value || "").trim();
  try {
    await api(`/runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        request_id: currentPending.request_id,
        decision,
      }),
    });
    setMsg(els.runMsg, `Approval sent: ${decision}`);
    await loadRun();
  } catch (err) {
    setMsg(els.runMsg, String(err.message || err), true);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(loadRun, 1500);
  els.togglePoll.textContent = "Stop Poll";
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
  els.togglePoll.textContent = "Start Poll";
}

function togglePolling() {
  if (pollTimer) stopPolling();
  else startPolling();
}

function saveConnection() {
  const { baseUrl, token } = config();
  setStored("agent_base_url", baseUrl);
  setStored("agent_token", token);
  setMsg(els.connMsg, "Saved.");
}

function init() {
  els.baseUrl.value = getStored("agent_base_url", `${location.protocol}//${location.host}`);
  els.token.value = getStored("agent_token", "");
  els.saveConn.addEventListener("click", saveConnection);
  els.startRun.addEventListener("click", startRun);
  els.loadRun.addEventListener("click", loadRun);
  els.togglePoll.addEventListener("click", togglePolling);
  document.querySelectorAll(".approveBtn").forEach((btn) => {
    btn.addEventListener("click", () => sendApproval(btn.dataset.decision));
  });
}

init();

