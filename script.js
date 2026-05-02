/**
 * TaxShield Dashboard – script.js
 * Professional frontend logic with:
 *   - Clean API service layer
 *   - Toast notifications (replaces all alert() calls)
 *   - Loading states on every async action
 *   - Proper error handling throughout
 *   - Chart.js dashboard visualisation
 *   - Section-based SPA navigation
 */

"use strict";

// ── Config ────────────────────────────────────────────────────────────────────
const CONFIG = {
  API_BASE: "http://127.0.0.1:8000",
  USER_ID:  parseInt(sessionStorage.getItem("ts_user_id") || "1"),
  DATE:     new Date().toISOString().split("T")[0],   // today's date as YYYY-MM-DD
};

// ── Session helpers ───────────────────────────────────────────────────────────

/** Return stored JWT token */
function getToken() {
  return sessionStorage.getItem("ts_token") || "";
}

/** Clear session and redirect to login */
function logout() {
  sessionStorage.clear();
  window.location.href = "login.html";
}

/** Return the logged-in merchant's display name */
function getMerchantName() {
  return sessionStorage.getItem("ts_name") || "Merchant";
}

/** Return shop name */
function getShopName() {
  return sessionStorage.getItem("ts_shop") || "";
}

/** Return income type (Business / Salary / etc.) */
function getIncomeType() {
  return sessionStorage.getItem("ts_income") || "Business";
}

// ── API Service ───────────────────────────────────────────────────────────────
const api = {
  /**
   * Send a JSON POST request.
   * @param {string} endpoint
   * @param {object} body
   * @returns {Promise<object>}
   */
  /** Build auth headers including JWT token */
  _headers() {
    const token = getToken();
    return {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    };
  },

  async post(endpoint, body) {
    const res = await fetch(`${CONFIG.API_BASE}${endpoint}`, {
      method:  "POST",
      headers: this._headers(),
      body:    JSON.stringify(body),
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  },

  async upload(endpoint, formData) {
    const token = getToken();
    const res = await fetch(`${CONFIG.API_BASE}${endpoint}`, {
      method:  "POST",
      headers: token ? { "Authorization": `Bearer ${token}` } : {},
      body:    formData,
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed: ${res.status}`);
    }
    return res.json();
  },

  async get(endpoint) {
    const res = await fetch(`${CONFIG.API_BASE}${endpoint}`, {
      headers: this._headers(),
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  },
};

// ── Toast Notifications ───────────────────────────────────────────────────────
const toast = {
  /**
   * Show a toast message.
   * @param {string} message
   * @param {'success'|'error'|'warning'|'info'} type
   * @param {number} duration  ms before auto-dismiss
   */
  show(message, type = "info", duration = 3500) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const icons = {
      success: "✓",
      error:   "✕",
      warning: "⚠",
      info:    "ℹ",
    };

    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${icons[type] || "ℹ"}</span><span>${message}</span>`;
    container.appendChild(el);

    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(8px)";
      el.style.transition = "0.3s ease";
      setTimeout(() => el.remove(), 320);
    }, duration);
  },

  success: (msg) => toast.show(msg, "success"),
  error:   (msg) => toast.show(msg, "error", 5000),
  warning: (msg) => toast.show(msg, "warning"),
  info:    (msg) => toast.show(msg, "info"),
};

// ── Loading State ─────────────────────────────────────────────────────────────
function setLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> Loading…`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    btn.disabled = false;
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = {
  currency: (n) => `₹ ${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
  percent:  (n) => `${Number(n || 0).toFixed(1)}%`,
  date:     (d) => d ? new Date(d).toLocaleDateString("en-IN") : "—",
};

function getVal(id)       { return document.getElementById(id)?.value || ""; }
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

// ── Navigation ────────────────────────────────────────────────────────────────
function navigate(sectionId) {
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  const section = document.getElementById(`section-${sectionId}`);
  if (section) section.classList.add("active");

  const navItem = document.querySelector(`[data-nav="${sectionId}"]`);
  if (navItem) navItem.classList.add("active");

  // Auto-load data for relevant sections
  if (sectionId === "dashboard") loadDashboard();
  if (sectionId === "analyze")   loadAnalysis();
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
let dashChart = null;

async function loadDashboard() {
  try {
    const data = await api.get(`/dashboard?user_id=${CONFIG.USER_ID}`);

    setHTML("dash-income",  fmt.currency(data.total_income));
    setHTML("dash-expense", fmt.currency(data.total_expense));

    const profitEl = document.getElementById("dash-profit");
    if (profitEl) {
      profitEl.textContent = fmt.currency(data.profit);
      profitEl.className = `card-value ${data.profit >= 0 ? "positive" : "negative"}`;
    }

    setHTML("dash-tax", fmt.currency(data.tax));

    _drawDashboardChart(data);
  } catch (err) {
    toast.error("Could not load dashboard: " + err.message);
  }
}

function _drawDashboardChart(data) {
  const ctx = document.getElementById("dashboard-chart")?.getContext("2d");
  if (!ctx) return;

  if (dashChart) dashChart.destroy();

  dashChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Income", "Expense", "Profit", "Est. Tax"],
      datasets: [{
        label: "Amount (₹)",
        data: [data.total_income, data.total_expense, data.profit, data.tax],
        backgroundColor: [
          "rgba(34,197,94,0.7)",
          "rgba(239,68,68,0.7)",
          data.profit >= 0 ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
          "rgba(232,160,32,0.7)",
        ],
        borderColor: [
          "rgba(34,197,94,1)",
          "rgba(239,68,68,1)",
          data.profit >= 0 ? "rgba(34,197,94,1)" : "rgba(239,68,68,1)",
          "rgba(232,160,32,1)",
        ],
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ₹ ${ctx.parsed.y.toLocaleString("en-IN")}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#8b98b8" },
        },
        y: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: {
            color: "#8b98b8",
            callback: (v) => `₹${(v / 1000).toFixed(0)}k`,
          },
        },
      },
    },
  });
}

// ── Add Income ────────────────────────────────────────────────────────────────
async function addIncome(btn) {
  const amount   = parseFloat(getVal("income-amount"));
  const source   = getVal("income-source");
  const date     = getVal("income-date")     || CONFIG.DATE;
  const category = getVal("income-category") || null;
  const gst      = parseFloat(getVal("income-gst")) || 0;

  if (!amount || amount <= 0) return toast.warning("Please enter a valid amount.");
  if (!source.trim())        return toast.warning("Please enter an income source.");

  setLoading(btn, true);
  try {
    await api.post("/income", {
      user_id: CONFIG.USER_ID,
      amount, source, date, gst,
      category: category || "General",
    });
    toast.success("Income recorded successfully.");
    document.getElementById("income-form")?.reset();
    await loadIncomeList();
  } catch (err) {
    toast.error("Failed to add income: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

async function loadIncomeList() {
  try {
    const list = await api.get(`/income?user_id=${CONFIG.USER_ID}`);
    const tbody = document.getElementById("income-table-body");
    if (!tbody) return;

    tbody.innerHTML = list.length === 0
      ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:2rem">No income records yet.</td></tr>`
      : list.map(r => `
          <tr>
            <td>${fmt.date(r.date)}</td>
            <td>${r.source}</td>
            <td><span class="badge badge-blue">${r.category || "—"}</span></td>
            <td class="amount-positive">${fmt.currency(r.amount)}</td>
            <td><span class="badge badge-warning">GST ${fmt.currency(r.gst)}</span></td>
          </tr>`).join("");
  } catch (err) {
    toast.error("Could not load income list.");
  }
}

// ── Add Expense ───────────────────────────────────────────────────────────────
async function addExpense(btn) {
  const item     = getVal("expense-item");
  const amount   = parseFloat(getVal("expense-amount"));
  const date     = getVal("expense-date")     || CONFIG.DATE;
  const category = getVal("expense-category") || null;
  const gst      = parseFloat(getVal("expense-gst")) || 0;

  if (!item.trim())          return toast.warning("Please enter an item name.");
  if (!amount || amount <= 0) return toast.warning("Please enter a valid amount.");

  setLoading(btn, true);
  try {
    await api.post("/expense", {
      user_id: CONFIG.USER_ID,
      item, amount, date, gst,
      category: category || "Others",
    });
    toast.success("Expense recorded successfully.");
    document.getElementById("expense-form")?.reset();
    await loadExpenseList();
  } catch (err) {
    toast.error("Failed to add expense: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

async function loadExpenseList() {
  try {
    const list = await api.get(`/expense?user_id=${CONFIG.USER_ID}`);
    const tbody = document.getElementById("expense-table-body");
    if (!tbody) return;

    tbody.innerHTML = list.length === 0
      ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:2rem">No expense records yet.</td></tr>`
      : list.map(r => `
          <tr>
            <td>${fmt.date(r.date)}</td>
            <td>${r.item}</td>
            <td><span class="badge badge-warning">${r.category || "Others"}</span></td>
            <td class="amount-negative">${fmt.currency(r.amount)}</td>
            <td><span class="badge badge-blue">GST ${fmt.currency(r.gst)}</span></td>
          </tr>`).join("");
  } catch (err) {
    toast.error("Could not load expense list.");
  }
}

// ── GST Calculator ────────────────────────────────────────────────────────────
async function loadGSTSummary(btn) {
  setLoading(btn, true);
  try {
    const data = await api.get(`/gst-summary?user_id=${CONFIG.USER_ID}`);
    setHTML("gst-output",  fmt.currency(data.output_gst));
    setHTML("gst-input",   fmt.currency(data.input_gst));
    const payEl = document.getElementById("gst-payable");
    if (payEl) {
      payEl.textContent = fmt.currency(data.gst_payable);
      payEl.className = `card-value ${data.gst_payable > 0 ? "negative" : "positive"}`;
    }
  } catch (err) {
    toast.error("Could not load GST summary: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

// ── Tab Switcher ──────────────────────────────────────────────────────────────
function switchTab(section, tab) {
  // Deactivate all tabs and panels in this section
  const sectionEl = document.getElementById(`section-${section}`);
  sectionEl.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  sectionEl.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));

  // Activate selected
  const targetPanel = document.getElementById(`${section}-tab-${tab}`);
  if (targetPanel) targetPanel.classList.add("active");

  // Activate correct tab button (match by text content heuristic)
  sectionEl.querySelectorAll(".tab-btn").forEach(b => {
    if (b.getAttribute("onclick")?.includes(`'${tab}'`)) b.classList.add("active");
  });

  // Stop camera if leaving camera tab
  if (section === "scan" && tab !== "camera") stopCamera();
}

// ══════════════════════════════════════════════════════════════════════════════
// SCAN BILL — FILE UPLOAD
// ══════════════════════════════════════════════════════════════════════════════
async function scanBillFromFile(btn) {
  const fileInput = document.getElementById("bill-file");
  const file = fileInput?.files[0];
  if (!file) return toast.warning("Please select a bill image first.");
  await _processBillFile(file, btn);
}

// ══════════════════════════════════════════════════════════════════════════════
// SCAN BILL — LIVE CAMERA
// ══════════════════════════════════════════════════════════════════════════════
let _cameraStream = null;

async function startCamera() {
  try {
    _cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
    });

    const video = document.getElementById("camera-video");
    video.srcObject = _cameraStream;
    video.style.display = "block";

    document.getElementById("camera-placeholder").style.display = "none";
    document.getElementById("btn-start-camera").style.display  = "none";
    document.getElementById("btn-capture").style.display       = "inline-flex";
    document.getElementById("btn-stop-camera").style.display   = "inline-flex";
    document.getElementById("camera-snapshot").style.display   = "none";
    document.getElementById("btn-scan-live").style.display     = "none";
    document.getElementById("btn-retake").style.display        = "none";

    toast.info("Camera ready. Point at the bill and capture.");
  } catch (err) {
    toast.error("Camera access denied: " + err.message);
  }
}

function stopCamera() {
  if (_cameraStream) {
    _cameraStream.getTracks().forEach(t => t.stop());
    _cameraStream = null;
  }

  const video = document.getElementById("camera-video");
  if (video) { video.srcObject = null; video.style.display = "none"; }

  document.getElementById("camera-placeholder").style.display = "flex";
  document.getElementById("btn-start-camera").style.display  = "inline-flex";
  document.getElementById("btn-capture").style.display       = "none";
  document.getElementById("btn-stop-camera").style.display   = "none";
  document.getElementById("btn-retake").style.display        = "none";
  document.getElementById("btn-scan-live").style.display     = "none";
}

function capturePhoto() {
  const video    = document.getElementById("camera-video");
  const canvas   = document.getElementById("camera-canvas");
  const snapshot = document.getElementById("camera-snapshot");

  canvas.width  = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);

  const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
  snapshot.src          = dataUrl;
  snapshot.style.display = "block";

  // Pause live stream (keep stream alive for retake)
  video.style.display = "none";

  document.getElementById("btn-capture").style.display   = "none";
  document.getElementById("btn-retake").style.display    = "inline-flex";
  document.getElementById("btn-scan-live").style.display = "inline-flex";

  toast.success("Photo captured! Review and click 'Scan This Photo'.");
}

function retakePhoto() {
  document.getElementById("camera-snapshot").style.display = "none";
  document.getElementById("camera-video").style.display    = "block";
  document.getElementById("btn-capture").style.display     = "inline-flex";
  document.getElementById("btn-retake").style.display      = "none";
  document.getElementById("btn-scan-live").style.display   = "none";
  setHTML("ocr-result", "");
}

async function scanBillFromCamera(btn) {
  const canvas = document.getElementById("camera-canvas");
  if (!canvas.width) return toast.warning("Please capture a photo first.");

  // Convert canvas to Blob → File
  canvas.toBlob(async (blob) => {
    const file = new File([blob], "live_capture.jpg", { type: "image/jpeg" });
    await _processBillFile(file, btn);
  }, "image/jpeg", 0.92);
}

/** Shared OCR upload + display logic */
async function _processBillFile(file, btn) {
  const fd = new FormData();
  fd.append("file", file);

  setLoading(btn, true);
  setHTML("ocr-result", "");

  try {
    const data = await api.upload(`/scan-bill?user_id=${CONFIG.USER_ID}`, fd);
    const accuracy = data.accuracy_score || 0;

    setHTML("ocr-result", `
      <div class="result-card">
        <div class="result-row">
          <span class="result-key">Vendor</span>
          <span class="result-value">${data.vendor || "Unknown"}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Amount</span>
          <span class="result-value amount-positive">${fmt.currency(data.amount)}</span>
        </div>
        <div class="result-row">
          <span class="result-key">GST</span>
          <span class="result-value">${fmt.currency(data.gst)}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Date</span>
          <span class="result-value">${data.date || "Not detected"}</span>
        </div>
        <div class="result-row">
          <span class="result-key">OCR Confidence</span>
          <span class="result-value">${fmt.percent(data.ocr_confidence)}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Accuracy Score</span>
          <span class="result-value ${accuracy < 60 ? "risk-HIGH" : "risk-LOW"}">${fmt.percent(accuracy)}</span>
        </div>
      </div>
      ${accuracy < 60
        ? `<div class="alert-box" style="margin-top:0.75rem">⚠ Low OCR accuracy. Try better lighting or a clearer image.</div>`
        : `<div class="alert-box success" style="margin-top:0.75rem">✓ Bill scanned and saved as expense.</div>`}
    `);

    toast.success(`Bill scanned — ${fmt.currency(data.amount)} detected.`);
  } catch (err) {
    toast.error("Bill scan failed: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// VOICE — FILE UPLOAD
// ══════════════════════════════════════════════════════════════════════════════
async function uploadVoiceFile(btn) {
  const fileInput = document.getElementById("voice-file");
  const file = fileInput?.files[0];
  if (!file) return toast.warning("Please select an audio file first.");
  await _processVoiceBlob(file, btn);
}

// ══════════════════════════════════════════════════════════════════════════════
// VOICE — LIVE RECORDER
// ══════════════════════════════════════════════════════════════════════════════
let _mediaRecorder  = null;
let _audioChunks    = [];
let _recordingBlob  = null;
let _timerInterval  = null;
let _secondsElapsed = 0;
let _analyserAF     = null;

// Init visualiser bars
(function initBars() {
  document.addEventListener("DOMContentLoaded", () => {
    const vis = document.getElementById("recorder-visualiser");
    if (!vis) return;
    for (let i = 0; i < 16; i++) {
      const bar = document.createElement("div");
      bar.className = "recorder-bar";
      bar.style.height = "6px";
      vis.appendChild(bar);
    }
  });
})();

async function toggleRecording() {
  if (_mediaRecorder && _mediaRecorder.state === "recording") {
    stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    _audioChunks   = [];
    _secondsElapsed = 0;
    _recordingBlob  = null;

    // Hide previous playback + send buttons
    document.getElementById("recording-playback").style.display = "none";
    document.getElementById("btn-send-recording").style.display = "none";
    document.getElementById("btn-discard").style.display        = "none";
    setHTML("voice-result", "");

    // Choose best supported format
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : "audio/webm";

    _mediaRecorder = new MediaRecorder(stream, { mimeType });
    _mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) _audioChunks.push(e.data); };
    _mediaRecorder.onstop = _onRecordingStop;
    _mediaRecorder.start(100);

    // UI
    const micBtn = document.getElementById("btn-mic");
    micBtn.classList.add("recording");
    micBtn.title = "Click to stop recording";
    micBtn.textContent = "⏹";

    document.getElementById("recorder-status").innerHTML =
      `<span class="dot"></span> Recording…`;

    // Timer
    _timerInterval = setInterval(() => {
      _secondsElapsed++;
      const m = String(Math.floor(_secondsElapsed / 60)).padStart(2, "0");
      const s = String(_secondsElapsed % 60).padStart(2, "0");
      document.getElementById("recorder-timer").textContent = `${m}:${s}`;
      // Auto-stop at 2 minutes
      if (_secondsElapsed >= 120) stopRecording();
    }, 1000);

    // Visualiser via Web Audio API
    _startVisualiser(stream);

    toast.info("Recording started. Speak your expense clearly.");
  } catch (err) {
    toast.error("Microphone access denied: " + err.message);
  }
}

function stopRecording() {
  if (_mediaRecorder && _mediaRecorder.state !== "inactive") {
    _mediaRecorder.stop();
    _mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  clearInterval(_timerInterval);
  cancelAnimationFrame(_analyserAF);

  const micBtn = document.getElementById("btn-mic");
  micBtn.classList.remove("recording");
  micBtn.title    = "Start recording";
  micBtn.textContent = "🎙️";

  document.getElementById("recorder-status").textContent = "Recording stopped. Review below.";

  // Reset bars
  document.querySelectorAll(".recorder-bar").forEach(b => {
    b.style.height = "6px";
    b.classList.remove("active");
  });
}

function _onRecordingStop() {
  _recordingBlob = new Blob(_audioChunks, { type: _mediaRecorder.mimeType });

  const url      = URL.createObjectURL(_recordingBlob);
  const playback = document.getElementById("recording-playback");
  playback.src           = url;
  playback.style.display = "block";

  document.getElementById("btn-send-recording").style.display = "inline-flex";
  document.getElementById("btn-discard").style.display        = "inline-flex";

  toast.success("Recording ready. Listen back then send to AI.");
}

function discardRecording() {
  _recordingBlob = null;
  _audioChunks   = [];
  const playback = document.getElementById("recording-playback");
  playback.src           = "";
  playback.style.display = "none";
  document.getElementById("btn-send-recording").style.display = "none";
  document.getElementById("btn-discard").style.display        = "none";
  document.getElementById("recorder-timer").textContent       = "00:00";
  document.getElementById("recorder-status").textContent      = "Press the mic button to start recording";
  setHTML("voice-result", "");
  toast.info("Recording discarded.");
}

async function sendRecording(btn) {
  if (!_recordingBlob) return toast.warning("No recording found. Please record first.");

  // Give file a name with the right extension
  const ext  = _mediaRecorder.mimeType.includes("ogg") ? "ogg" : "webm";
  const file = new File([_recordingBlob], `live_recording.${ext}`, { type: _mediaRecorder.mimeType });

  await _processVoiceBlob(file, btn);
}

/** Shared voice upload + display logic */
async function _processVoiceBlob(file, btn) {
  const fd = new FormData();
  fd.append("file", file);

  setLoading(btn, true);
  setHTML("voice-result", "");

  try {
    const data = await api.upload(`/voice-expense?user_id=${CONFIG.USER_ID}`, fd);
    const r    = data.voice_result || data;

    setHTML("voice-result", `
      <div class="result-card">
        <div class="result-row">
          <span class="result-key">Transcript</span>
          <span class="result-value">${r.transcript || "—"}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Item Detected</span>
          <span class="result-value">${r.item || "—"}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Amount</span>
          <span class="result-value amount-positive">${fmt.currency(r.amount)}</span>
        </div>
      </div>
      <div class="alert-box success" style="margin-top:0.75rem">
        ✓ Expense saved: <strong>${r.item}</strong> — ${fmt.currency(r.amount)}
      </div>
    `);

    toast.success(`Voice expense saved: ${r.item} — ${fmt.currency(r.amount)}`);
  } catch (err) {
    toast.error("Voice processing failed: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

/** Animate visualiser bars using Web Audio analyser */
function _startVisualiser(stream) {
  try {
    const ctx      = new (window.AudioContext || window.webkitAudioContext)();
    const source   = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 64;
    source.connect(analyser);

    const data = new Uint8Array(analyser.frequencyBinCount);
    const bars = document.querySelectorAll(".recorder-bar");

    function draw() {
      _analyserAF = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(data);
      bars.forEach((bar, i) => {
        const val = data[i] || 0;
        bar.style.height = `${6 + (val / 255) * 42}px`;
        bar.classList.toggle("active", val > 20);
      });
    }
    draw();
  } catch (_) {
    // Web Audio not critical — visualiser is cosmetic
  }
}

// ── Bank Statement ────────────────────────────────────────────────────────────
async function uploadBankStatement(btn) {
  const fileInput = document.getElementById("bank-file");
  const file = fileInput?.files[0];
  if (!file) return toast.warning("Please select a PDF bank statement.");

  const fd = new FormData();
  fd.append("file", file);

  setLoading(btn, true);
  setHTML("bank-result", "");

  try {
    const data = await api.upload(`/upload-bank-statement?user_id=${CONFIG.USER_ID}`, fd);
    const detected = data.income_detected || [];

    setHTML("bank-result", `
      <div class="alert-box success">
        ✓ Imported <strong>${detected.length}</strong> credit transaction${detected.length !== 1 ? "s" : ""}.
        Total: ${fmt.currency(detected.reduce((a, b) => a + b, 0))}
      </div>
      ${detected.length > 0 ? `
        <div class="result-card">
          ${detected.map((amt, i) => `
            <div class="result-row">
              <span class="result-key">Transaction ${i + 1}</span>
              <span class="result-value amount-positive">${fmt.currency(amt)}</span>
            </div>`).join("")}
        </div>` : ""}
    `);

    toast.success(`Imported ${detected.length} transactions from statement.`);
  } catch (err) {
    toast.error("Bank statement upload failed: " + err.message);
  } finally {
    setLoading(btn, false);
  }
}

// ── Financial Analysis ────────────────────────────────────────────────────────
async function loadAnalysis() {
  try {
    const data = await api.get(`/ai-insights?user_id=${CONFIG.USER_ID}`);
    const fin  = data.financial_analysis || {};
    const pat  = data.spending_pattern   || {};

    // Financial summary
    setHTML("analysis-income",  fmt.currency(fin.income));
    setHTML("analysis-expense", fmt.currency(fin.expense));
    setHTML("analysis-profit",  fmt.currency(fin.profit));
    setHTML("analysis-gst",     fmt.currency(fin.gst_payable));

    const riskEl = document.getElementById("analysis-risk");
    if (riskEl) {
      riskEl.textContent = fin.risk_level || "—";
      riskEl.className   = `card-value risk-${fin.risk_level}`;
    }

    // Alerts
    const alertsEl = document.getElementById("analysis-alerts");
    if (alertsEl) {
      alertsEl.innerHTML = (fin.alerts || []).length === 0
        ? `<div class="alert-box success">✓ No financial alerts. Everything looks healthy.</div>`
        : fin.alerts.map(a => `<div class="alert-box">${a}</div>`).join("");
    }

    // Suggestions
    const sugEl = document.getElementById("analysis-suggestions");
    if (sugEl) {
      sugEl.innerHTML = (fin.suggestions || []).map(s =>
        `<div class="alert-box info">💡 ${s}</div>`
      ).join("") || "";
    }

    // Spending pattern
    const topEl = document.getElementById("spending-top");
    if (topEl) topEl.textContent = pat.top_category || "—";

    _drawCategoryChart(pat.category_distribution || {});

  } catch (err) {
    toast.error("Could not load analysis: " + err.message);
  }
}

let categoryChart = null;

function _drawCategoryChart(distribution) {
  const ctx = document.getElementById("category-chart")?.getContext("2d");
  if (!ctx) return;

  if (categoryChart) categoryChart.destroy();

  const labels = Object.keys(distribution);
  const values = Object.values(distribution);
  const palette = [
    "#e8a020","#3b82f6","#22c55e","#ef4444","#a855f7",
    "#14b8a6","#f97316","#ec4899","#64748b","#eab308",
  ];

  categoryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: palette.slice(0, labels.length),
        borderColor: "var(--bg-card)",
        borderWidth: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "right",
          labels: { color: "#8b98b8", font: { size: 11 }, padding: 12 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed.toFixed(1)}%`,
          },
        },
      },
    },
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// REPORTS & ITR FORMS
// ══════════════════════════════════════════════════════════════════════════════

// ── Financial Summary Report ──────────────────────────────────────────────────
async function generateReport(btn) {
  setLoading(btn, true);
  setHTML("report-status", "");
  try {
    const data = await api.get(`/generate-report?user_id=${CONFIG.USER_ID}`);
    toast.success("Financial report generated successfully.");
    setHTML("report-status", `
      <div class="alert-box success">
        ✓ Report ready — click <strong>Download PDF</strong> to save it.
      </div>`);
  } catch (err) {
    toast.error("Report generation failed: " + err.message);
    setHTML("report-status", `<div class="alert-box">✕ ${err.message}</div>`);
  } finally {
    setLoading(btn, false);
  }
}

function downloadReport() {
  window.open(`${CONFIG.API_BASE}/download-report?user_id=${CONFIG.USER_ID}`);
}

// ── ITR-4 SUGAM ───────────────────────────────────────────────────────────────
async function generateITR4(btn) {
  setLoading(btn, true);
  setHTML("itr4-status", "");
  try {
    const data = await api.get(`/generate-itr4?user_id=${CONFIG.USER_ID}`);
    toast.success("ITR-4 Sugam draft generated!");
    setHTML("itr4-status", `
      <div class="alert-box success" style="margin-bottom:0.6rem">
        ✓ ITR-4 Sugam pre-filled draft is ready.
        Click <strong>Download ITR-4 PDF</strong> to save.
      </div>
      <div class="result-card">
        <div class="result-row">
          <span class="result-key">Assessment Year</span>
          <span class="result-value">${data.assessment_year}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Financial Year</span>
          <span class="result-value">${data.financial_year}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Gross Turnover</span>
          <span class="result-value amount-positive">${fmt.currency(data.gross_turnover)}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Net Profit Declared</span>
          <span class="result-value ${data.net_profit >= 0 ? 'amount-positive' : 'amount-negative'}">
            ${fmt.currency(data.net_profit)}
          </span>
        </div>
        <div class="result-row">
          <span class="result-key">Presumptive Profit (8%)</span>
          <span class="result-value">${fmt.currency(data.gross_turnover * 0.08)}</span>
        </div>
      </div>
      <div class="alert-box" style="margin-top:0.6rem">
        ⚠ ${data.note}
      </div>`);
  } catch (err) {
    toast.error("ITR-4 generation failed: " + err.message);
    setHTML("itr4-status", `<div class="alert-box">✕ ${err.message}</div>`);
  } finally {
    setLoading(btn, false);
  }
}

function downloadITR4() {
  window.open(`${CONFIG.API_BASE}/download-itr4?user_id=${CONFIG.USER_ID}`);
}

// ── ITR-3 ─────────────────────────────────────────────────────────────────────
async function generateITR3(btn) {
  setLoading(btn, true);
  setHTML("itr3-status", "");
  try {
    const data = await api.get(`/generate-itr3?user_id=${CONFIG.USER_ID}`);
    toast.success("ITR-3 draft generated!");
    setHTML("itr3-status", `
      <div class="alert-box success" style="margin-bottom:0.6rem">
        ✓ ITR-3 pre-filled draft is ready.
        Click <strong>Download ITR-3 PDF</strong> to save.
      </div>
      <div class="result-card">
        <div class="result-row">
          <span class="result-key">Assessment Year</span>
          <span class="result-value">${data.assessment_year}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Gross Turnover</span>
          <span class="result-value amount-positive">${fmt.currency(data.gross_turnover)}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Net Profit (P&L)</span>
          <span class="result-value ${data.net_profit >= 0 ? 'amount-positive' : 'amount-negative'}">
            ${fmt.currency(data.net_profit)}
          </span>
        </div>
      </div>
      <div class="alert-box" style="margin-top:0.6rem">
        ⚠ ${data.note}
      </div>`);
  } catch (err) {
    toast.error("ITR-3 generation failed: " + err.message);
    setHTML("itr3-status", `<div class="alert-box">✕ ${err.message}</div>`);
  } finally {
    setLoading(btn, false);
  }
}

function downloadITR3() {
  window.open(`${CONFIG.API_BASE}/download-itr3?user_id=${CONFIG.USER_ID}`);
}

// ══════════════════════════════════════════════════════════════════════════════
// EMAIL REPORT
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Quick-fill the recipient fields with preset values.
 * 'myself' → logged-in user's email
 * 'ca'     → prompt for CA email
 * 'govt'   → Income Tax Department official address
 */
function quickFill(type) {
  const nameEl  = document.getElementById("email-to-name");
  const emailEl = document.getElementById("email-to");

  if (type === "myself") {
    // Fill with logged-in user's own email from session
    const myEmail = sessionStorage.getItem("ts_email") || "";
    const myName  = getMerchantName();
    nameEl.value  = myName;
    emailEl.value = myEmail;
    if (!myEmail) {
      toast.warning("Your email is not saved in your profile. Please type it manually.");
    } else {
      toast.info("Filled with your own email.");
    }

  } else if (type === "ca") {
    nameEl.value  = "My Chartered Accountant";
    emailEl.value = "";
    emailEl.focus();
    toast.info("Enter your CA's email address.");

  } else if (type === "govt") {
    nameEl.value  = "Income Tax Department";
    emailEl.value = "efiling@incometax.gov.in";
    toast.warning(
      "Government portals require official e-filing at incometax.gov.in — " +
      "this email is for reference / draft sharing only."
    );
  }
}

/**
 * Send the selected report PDF via email.
 */
async function sendReportEmail(btn) {
  const toEmail    = document.getElementById("email-to").value.trim();
  const toName     = document.getElementById("email-to-name").value.trim();
  const reportType = document.getElementById("email-report-type").value;
  const ccEmail    = document.getElementById("email-cc").value.trim() || null;

  // ── Validation ────────────────────────────────────────────────────────
  if (!toEmail) return toast.warning("Please enter a recipient email address.");
  if (!toName)  return toast.warning("Please enter the recipient name.");
  if (!_isValidEmail(toEmail)) return toast.warning("Please enter a valid email address.");

  setLoading(btn, true);
  setHTML("email-status", "");

  try {
    const data = await api.post(
      `/email/send-report?user_id=${CONFIG.USER_ID}`,
      { to_email: toEmail, to_name: toName, report_type: reportType, cc_email: ccEmail }
    );

    const reportLabels = {
      financial: "Financial Summary Report",
      itr4:      "ITR-4 Sugam Draft",
      itr3:      "ITR-3 Draft",
    };

    setHTML("email-status", `
      <div class="alert-box success">
        ✓ <strong>${reportLabels[reportType]}</strong> sent successfully to
        <strong>${toEmail}</strong>${ccEmail ? ` (CC: ${ccEmail})` : ""}.
      </div>
      <div class="result-card" style="margin-top:0.6rem">
        <div class="result-row">
          <span class="result-key">Sent To</span>
          <span class="result-value">${toName} &lt;${toEmail}&gt;</span>
        </div>
        <div class="result-row">
          <span class="result-key">Report</span>
          <span class="result-value">${reportLabels[reportType]}</span>
        </div>
        <div class="result-row">
          <span class="result-key">Attachment</span>
          <span class="result-value">${data.attachment || "PDF attached"}</span>
        </div>
      </div>
    `);

    toast.success(`Email sent to ${toEmail}!`);

    // Clear fields after success
    document.getElementById("email-to").value      = "";
    document.getElementById("email-to-name").value = "";
    document.getElementById("email-cc").value      = "";

  } catch (err) {
    // Show helpful error messages
    let errMsg = err.message;
    if (errMsg.includes("App Password")) {
      errMsg = "Gmail App Password not configured. Add EMAIL_USERNAME and EMAIL_PASSWORD to your .env file.";
    } else if (errMsg.includes("Report PDF not found")) {
      errMsg = "Report PDF not found. Please click Generate first, then email.";
    }

    setHTML("email-status", `
      <div class="alert-box">✕ ${errMsg}</div>
      ${errMsg.includes("App Password") || errMsg.includes("not configured") ? `
      <div class="alert-box info" style="margin-top:0.5rem">
        💡 <strong>Setup Guide:</strong><br/>
        1. Go to <a href="https://myaccount.google.com/apppasswords" target="_blank"
           style="color:var(--accent-blue)">Google App Passwords</a><br/>
        2. Generate a 16-character App Password<br/>
        3. Add to your .env file:<br/>
        <code style="font-size:0.75rem;background:var(--bg-input);padding:4px 8px;border-radius:4px;display:block;margin-top:6px">
EMAIL_USERNAME=your_gmail@gmail.com<br/>
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
        </code>
        4. Restart the server
      </div>` : ""}
    `);

    toast.error("Email failed: " + errMsg);
  } finally {
    setLoading(btn, false);
  }
}

/** Basic email format validation */
function _isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ── Upload zone drag-and-drop enhancement ─────────────────────────────────────
function initUploadZones() {
  document.querySelectorAll(".upload-zone").forEach(zone => {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const input = zone.querySelector("input[type=file]");
      if (input && e.dataTransfer.files[0]) {
        const dt = new DataTransfer();
        dt.items.add(e.dataTransfer.files[0]);
        input.files = dt.files;
        const label = zone.querySelector(".upload-text");
        if (label) label.textContent = e.dataTransfer.files[0].name;
      }
    });
    // Update label when file selected via click
    const input = zone.querySelector("input[type=file]");
    if (input) {
      input.addEventListener("change", () => {
        const label = zone.querySelector(".upload-text");
        if (label && input.files[0]) label.textContent = input.files[0].name;
      });
    }
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // ── Session guard — redirect if not logged in ──────────────────────────────
  if (!sessionStorage.getItem("ts_token")) {
    window.location.href = "login.html";
    return;
  }

  // ── Populate topbar with merchant info ─────────────────────────────────────
  const nameEl = document.getElementById("topbar-name");
  if (nameEl) nameEl.textContent = getMerchantName();

  const shopEl = document.getElementById("topbar-shop");
  if (shopEl) {
    const shop = getShopName();
    shopEl.textContent  = shop || getIncomeType();
    shopEl.style.display = "inline";
  }

  // ── Set today's date in topbar ─────────────────────────────────────────────
  const dateEl = document.getElementById("current-date");
  if (dateEl) {
    dateEl.textContent = new Date().toLocaleDateString("en-IN", {
      weekday: "short", day: "numeric", month: "short", year: "numeric",
    });
  }

  navigate("dashboard");
  initUploadZones();
});
