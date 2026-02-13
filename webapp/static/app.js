const els = {
  baseUrl: document.getElementById("baseUrl"),
  goal: document.getElementById("goal"),
  provider: document.getElementById("provider"),
  startRun: document.getElementById("startRun"),
  runMsg: document.getElementById("runMsg"),
  runIdText: document.getElementById("runIdText"),
  togglePoll: document.getElementById("togglePoll"),
  status: document.getElementById("status"),
  eventCount: document.getElementById("eventCount"),
  finalText: document.getElementById("finalText"),
  pendingBox: document.getElementById("pendingBox"),
  events: document.getElementById("events"),
};

let pollTimer = null;
let currentPending = null;
let currentRunId = "";

function getStored(key, fallback = "") {
  const v = localStorage.getItem(key);
  return v == null ? fallback : v;
}

function setStored(key, value) {
  localStorage.setItem(key, value);
}

function cfg() {
  return {
    baseUrl: (els.baseUrl.value || "").trim().replace(/\/+$/, ""),
  };
}

async function api(path, options = {}) {
  const { baseUrl } = cfg();
  if (!baseUrl) {
    throw new Error("API 주소를 입력하세요.");
  }
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const res = await fetch(`${baseUrl}${path}`, { ...options, headers, credentials: "include" });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

function setMsg(text, isError = false) {
  els.runMsg.textContent = text;
  els.runMsg.style.color = isError ? "#b24c2d" : "#1f7a5a";
}

function saveConn() {
  const { baseUrl } = cfg();
  setStored("agent_base_url", baseUrl);
}

async function startRun() {
  try {
    saveConn();
    const payload = {
      goal: els.goal.value.trim(),
      cwd: ".",
      provider: els.provider.value,
      max_steps: 8,
    };
    const data = await api("/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    currentRunId = data.run_id;
    setStored("last_run_id", currentRunId);
    setMsg(`요청 시작됨: ${currentRunId}`);
    await loadRun();
    startPolling();
  } catch (err) {
    setMsg(String(err.message || err), true);
  }
}

async function loadRun() {
  const runId = currentRunId || getStored("last_run_id", "");
  if (!runId) return;
  currentRunId = runId;
  try {
    const [snap, events] = await Promise.all([
      api(`/runs/${runId}`),
      api(`/runs/${runId}/events`),
    ]);
    els.status.textContent = snap.status || "-";
    els.runIdText.textContent = runId;
    els.eventCount.textContent = String(snap.event_count ?? "-");
    els.finalText.textContent = snap.final_text || "아직 최종 결과가 없습니다.";
    currentPending = snap.pending || null;
    els.pendingBox.textContent = currentPending
      ? JSON.stringify(currentPending, null, 2)
      : "현재 승인 대기 요청이 없습니다.";
    els.events.textContent = JSON.stringify(events.items || [], null, 2);
  } catch (err) {
    setMsg(String(err.message || err), true);
  }
}

async function sendApproval(decision) {
  if (!currentPending) {
    setMsg("승인 대기 요청이 없습니다.", true);
    return;
  }
  try {
    await api(`/runs/${currentRunId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        request_id: currentPending.request_id,
        decision,
      }),
    });
    setMsg(`승인 응답 전송: ${decision}`);
    await loadRun();
  } catch (err) {
    setMsg(String(err.message || err), true);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(loadRun, 1500);
  els.togglePoll.textContent = "자동 새로고침 중지";
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
  els.togglePoll.textContent = "자동 새로고침 시작";
}

function togglePolling() {
  if (pollTimer) stopPolling();
  else startPolling();
}

function init() {
  els.baseUrl.value = getStored("agent_base_url", `${location.protocol}//${location.host}`);
  currentRunId = getStored("last_run_id", "");

  els.baseUrl.addEventListener("change", saveConn);
  els.startRun.addEventListener("click", startRun);
  els.togglePoll.addEventListener("click", togglePolling);
  document.querySelectorAll(".approveBtn").forEach((btn) => {
    btn.addEventListener("click", () => sendApproval(btn.dataset.decision));
  });

  if (currentRunId) {
    loadRun();
  }
}

init();
