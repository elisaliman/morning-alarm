// --- DOM refs ---

const status = document.getElementById("status");
const scriptBox = document.getElementById("script-box");
const scriptText = document.getElementById("script-text");
const player = document.getElementById("player");
const orb = document.getElementById("btn-orb");
const orbLabel = document.getElementById("orb-label");
const pulseRing = document.getElementById("pulse-ring");
const alarmPicker = document.getElementById("alarm-picker");
const alarmCountdown = document.getElementById("alarm-countdown");
const btnPlayNow = document.getElementById("btn-play-now");
const btnCancelPicker = document.getElementById("btn-cancel-picker");

// --- State ---

let alarmTimeout = null;
let countdownInterval = null;
let alarmTargetMs = null;
let isGenerating = false;
let pickerOpen = false;
let pregenPromise = null;
let pregenResult = null;

// ============================================================
// Clock
// ============================================================

function updateClock() {
  const now = new Date();
  const h = now.getHours();
  const m = String(now.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  document.getElementById("clock").textContent = `${h12}:${m} ${ampm}`;

  let greeting = "Good evening";
  if (h < 12) greeting = "Good morning";
  else if (h < 17) greeting = "Good afternoon";
  document.getElementById("greeting").textContent = greeting;
}

updateClock();
setInterval(updateClock, 10000);

// ============================================================
// Scroll-drum time picker
// ============================================================

const ITEM_H = 36;
const PAD_ITEMS = 2;
const REPEAT_COUNT = 80;

function _addDrumItem(container, text) {
  const el = document.createElement("div");
  el.className = "drum-item";
  el.style.height = ITEM_H + "px";
  if (text !== undefined) el.textContent = text;
  container.appendChild(el);
}

function _attachSnap(container) {
  let userScrolling = false;
  let debounce = null;

  container.addEventListener("pointerdown", () => { userScrolling = true; }, { passive: true });
  container.addEventListener("pointerup", () => { userScrolling = false; }, { passive: true });
  container.addEventListener("pointercancel", () => { userScrolling = false; }, { passive: true });

  container.addEventListener("scroll", () => {
    clearTimeout(debounce);
    if (container._snapping) return;
    debounce = setTimeout(() => {
      if (userScrolling) return;
      snapDrum(container);
    }, 120);
  }, { passive: true });
}

function buildDrum(container, values, startIndex, infinite) {
  container.innerHTML = "";
  const total = values.length;

  for (let i = 0; i < PAD_ITEMS; i++) _addDrumItem(container);

  if (infinite) {
    for (let rep = 0; rep < REPEAT_COUNT; rep++) {
      for (let j = 0; j < total; j++) _addDrumItem(container, values[j]);
    }
  } else {
    for (let j = 0; j < total; j++) _addDrumItem(container, values[j]);
  }

  for (let i = 0; i < PAD_ITEMS; i++) _addDrumItem(container);

  const offset = infinite ? Math.floor(REPEAT_COUNT / 2) * total + startIndex : startIndex;
  container.scrollTop = offset * ITEM_H;

  container._totalPerRep = total;
  container._infinite = !!infinite;
  container._snapping = false;
  _attachSnap(container);
}

function snapDrum(container) {
  const idx = Math.round(container.scrollTop / ITEM_H);
  const target = idx * ITEM_H;

  if (Math.abs(container.scrollTop - target) < 1) {
    recenterDrum(container);
    return;
  }

  container._snapping = true;
  container.scrollTo({ top: target, behavior: "smooth" });

  setTimeout(() => {
    container._snapping = false;
    recenterDrum(container);
  }, 300);
}

function recenterDrum(container) {
  if (!container._infinite) return;
  const total = container._totalPerRep;
  const rawIdx = Math.round(container.scrollTop / ITEM_H);

  if (rawIdx < total * 10 || rawIdx >= total * (REPEAT_COUNT - 10)) {
    const posInCycle = ((rawIdx % total) + total) % total;
    const midStart = Math.floor(REPEAT_COUNT / 2) * total;
    container.scrollTop = (midStart + posInCycle) * ITEM_H;
  }
}

function getDrumValue(container) {
  const rawIdx = Math.round(container.scrollTop / ITEM_H);
  const total = container._totalPerRep;
  return ((rawIdx % total) + total) % total;
}

const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1));
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, "0"));
const AMPMS = ["AM", "PM"];

function initDrums() {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const h12 = h % 12 || 12;

  buildDrum(document.getElementById("drum-hour"), HOURS, h12 - 1, true);
  buildDrum(document.getElementById("drum-min"), MINUTES, m, true);
  buildDrum(document.getElementById("drum-ampm"), AMPMS, h >= 12 ? 1 : 0, false);
}

function getPickerTime() {
  const hIdx = getDrumValue(document.getElementById("drum-hour"));
  const mIdx = getDrumValue(document.getElementById("drum-min"));
  const apIdx = getDrumValue(document.getElementById("drum-ampm"));

  let h = (hIdx % 12) + 1;
  const m = mIdx % 60;
  const isPM = (apIdx % 2) === 1;

  if (isPM && h !== 12) h += 12;
  if (!isPM && h === 12) h = 0;

  return { h, m };
}

// ============================================================
// UI helpers
// ============================================================

function formatTime12(h, m) {
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
}

function hidePickerUI() {
  alarmPicker.classList.add("hidden");
  btnCancelPicker.classList.add("hidden");
  btnPlayNow.classList.add("hidden");
  pickerOpen = false;
}

function resetOrb() {
  orb.disabled = false;
  orb.classList.remove("orb-confirm");
  orbLabel.textContent = "Set Alarm";
  pulseRing.classList.remove("pulse-ring-active");
}

function cleanScript(raw) {
  return raw
    .replace(/\[sfx:[^\]]*\]/gi, "")
    .replace(/<break[^>]*\/?\s*>/gi, "")
    .replace(/\n{2,}/g, "\n\n")
    .trim();
}

// ============================================================
// Orb — single button for all states
// ============================================================

function handleOrbClick() {
  if (isGenerating) return;

  if (alarmTargetMs) {
    clearScheduledAlarm();
    return;
  }

  if (pickerOpen) {
    confirmAlarm();
    return;
  }

  showAlarmPicker();
}

function showAlarmPicker() {
  initDrums();
  alarmPicker.classList.remove("hidden");
  btnCancelPicker.classList.remove("hidden");
  btnPlayNow.classList.remove("hidden");
  pickerOpen = true;
  orbLabel.textContent = "Confirm";
  orb.classList.add("orb-confirm");
}

function cancelAlarmPicker() {
  hidePickerUI();
  resetOrb();
}

function confirmAlarm() {
  const { h, m } = getPickerTime();

  const now = new Date();
  const target = new Date();
  target.setHours(h, m, 0, 0);
  if (target <= now) target.setDate(target.getDate() + 1);

  alarmTargetMs = target.getTime();
  alarmTimeout = setTimeout(() => fireAlarm(), alarmTargetMs - Date.now());

  hidePickerUI();
  orb.classList.remove("orb-confirm");

  orbLabel.innerHTML = `<span class="text-sm opacity-70">${formatTime12(h, m)}</span><br><span class="text-xs opacity-50">tap to cancel</span>`;
  pulseRing.classList.add("pulse-ring-active");
  alarmCountdown.classList.remove("hidden");
  updateCountdown();
  countdownInterval = setInterval(updateCountdown, 1000);

  pregenerate();
}

function updateCountdown() {
  if (!alarmTargetMs) return;
  const diff = alarmTargetMs - Date.now();
  if (diff <= 0) {
    alarmCountdown.textContent = "";
    return;
  }
  const hrs = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  const secs = Math.floor((diff % 60000) / 1000);

  let parts = [];
  if (hrs > 0) parts.push(`${hrs}h`);
  parts.push(`${mins}m`);
  parts.push(`${secs}s`);
  alarmCountdown.textContent = parts.join(" ");
}

function clearScheduledAlarm() {
  if (alarmTimeout) clearTimeout(alarmTimeout);
  if (countdownInterval) clearInterval(countdownInterval);
  alarmTimeout = null;
  countdownInterval = null;
  alarmTargetMs = null;
  pregenPromise = null;
  pregenResult = null;
  isGenerating = false;

  hidePickerUI();
  resetOrb();
  alarmCountdown.classList.add("hidden");
  alarmCountdown.textContent = "";
  status.textContent = "";
}

// ============================================================
// Generate & play
// ============================================================

async function fetchMorning() {
  const res = await fetch("/generate-morning");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error ${res.status}`);
  }
  return res.json();
}

async function pregenerate() {
  pregenResult = null;
  status.textContent = "Preparing your morning in the background\u2026";
  isGenerating = true;

  pregenPromise = fetchMorning();

  try {
    pregenResult = await pregenPromise;
    status.textContent = "Ready \u2014 waiting for alarm\u2026";
  } catch (err) {
    status.textContent = `Pre-generation failed: ${err.message}. Will retry when alarm fires.`;
    console.error(err);
    pregenResult = null;
  } finally {
    isGenerating = false;
    pregenPromise = null;
  }
}

function playResult(data) {
  scriptText.textContent = cleanScript(data.script);
  scriptBox.classList.remove("hidden");

  player.src = data.audio_url;
  player.play();

  status.textContent = "Playing\u2026";
  resetOrb();

  player.addEventListener(
    "ended",
    () => { status.textContent = ""; },
    { once: true }
  );
}

async function fireAlarm() {
  if (countdownInterval) clearInterval(countdownInterval);
  countdownInterval = null;
  alarmTimeout = null;
  alarmTargetMs = null;
  alarmCountdown.classList.add("hidden");
  pulseRing.classList.remove("pulse-ring-active");

  orb.disabled = true;
  orbLabel.textContent = "Brewing\u2026";
  scriptBox.classList.add("hidden");

  try {
    let data = pregenResult;

    if (!data && pregenPromise) {
      status.textContent = "Almost ready\u2026";
      data = await pregenPromise;
    }

    if (!data) {
      status.textContent = "Generating your morning\u2026";
      data = await fetchMorning();
    }

    playResult(data);
  } catch (err) {
    status.textContent = `Something went wrong: ${err.message}`;
    console.error(err);
    resetOrb();
  } finally {
    pregenResult = null;
    pregenPromise = null;
    isGenerating = false;
  }
}

async function handleWake() {
  if (isGenerating) return;
  isGenerating = true;
  orb.disabled = true;
  orbLabel.textContent = "Brewing\u2026";

  hidePickerUI();
  pulseRing.classList.remove("pulse-ring-active");
  status.textContent = "Fetching weather, calendar, and crafting your morning\u2026";
  scriptBox.classList.add("hidden");

  try {
    playResult(await fetchMorning());
  } catch (err) {
    status.textContent = `Something went wrong: ${err.message}`;
    console.error(err);
  } finally {
    isGenerating = false;
    resetOrb();
  }
}

// ============================================================
// Settings modal
// ============================================================

function openSettings() {
  document.getElementById("settings-modal").classList.remove("hidden");
  loadSettings();
}

function closeSettings() {
  document.getElementById("settings-modal").classList.add("hidden");
}

document.getElementById("settings-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeSettings();
});

async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();

    const loc = data.location || {};
    document.getElementById("loc-current").textContent = loc.name
      ? `Current: ${loc.name}`
      : "Current: New York (default)";
    document.getElementById("city-search").value = "";

    renderGoogleStatus(data.google || {});
  } catch (err) {
    console.error("Failed to load settings", err);
  }
}

function renderGoogleStatus(google) {
  const statusEl = document.getElementById("google-status");
  const connectBtn = document.getElementById("btn-google-connect");
  const disconnectBtn = document.getElementById("btn-google-disconnect");

  connectBtn.classList.remove("hidden");

  if (google.connected) {
    statusEl.innerHTML = `Connected as <span class="text-indigo-300">${google.email}</span>`;
    connectBtn.textContent = "Switch Account";
    disconnectBtn.classList.remove("hidden");
  } else {
    statusEl.textContent = "No Google account connected";
    connectBtn.textContent = "Connect Account";
    disconnectBtn.classList.add("hidden");
  }
}

// ============================================================
// Location (city search)
// ============================================================

let citySearchTimer = null;

function handleCitySearch() {
  clearTimeout(citySearchTimer);
  const q = document.getElementById("city-search").value.trim();
  const resultsEl = document.getElementById("city-results");

  if (q.length < 2) {
    resultsEl.classList.add("hidden");
    return;
  }

  citySearchTimer = setTimeout(() => searchCities(q), 300);
}

async function searchCities(q) {
  const resultsEl = document.getElementById("city-results");
  try {
    const res = await fetch(`/api/cities?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    const cities = data.results || [];

    if (cities.length === 0) {
      resultsEl.innerHTML = `<div class="px-4 py-3 text-white/30 text-sm">No cities found</div>`;
    } else {
      resultsEl.innerHTML = cities.map((c, i) =>
        `<button onclick='selectCity(${i})' class="w-full text-left px-4 py-2.5 text-white/70 text-sm hover:bg-white/10 transition-colors cursor-pointer">${c.label}</button>`
      ).join("");
      window._cityResults = cities;
    }

    resultsEl.classList.remove("hidden");
  } catch (err) {
    console.error("City search failed", err);
  }
}

async function selectCity(index) {
  const city = window._cityResults[index];
  if (!city) return;

  document.getElementById("city-results").classList.add("hidden");
  document.getElementById("city-search").value = "";
  const locStatus = document.getElementById("loc-status");

  try {
    const res = await fetch("/api/settings/location", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat: city.lat, lon: city.lon, name: city.label }),
    });
    if (!res.ok) throw new Error("Save failed");
    document.getElementById("loc-current").textContent = `Current: ${city.label}`;
    locStatus.textContent = "Location updated.";
    setTimeout(() => { locStatus.textContent = ""; }, 3000);
  } catch (err) {
    locStatus.textContent = `Error: ${err.message}`;
  }
}

// ============================================================
// Google Calendar
// ============================================================

async function googleConnect() {
  const statusEl = document.getElementById("google-status");
  statusEl.textContent = "Opening Google sign-in\u2026 check your browser.";

  try {
    const res = await fetch("/api/google/connect", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Connection failed");
    renderGoogleStatus({ connected: true, email: data.email });
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

async function googleDisconnect() {
  try {
    await fetch("/api/google/disconnect", { method: "POST" });
    renderGoogleStatus({ connected: false });
  } catch (err) {
    console.error("Disconnect failed", err);
  }
}

// ============================================================
// Cache
// ============================================================

async function clearCache() {
  const cacheStatus = document.getElementById("cache-status");
  try {
    await fetch("/api/cache/clear", { method: "POST" });
    cacheStatus.textContent = "Cache cleared. Next alarm will generate fresh.";
    setTimeout(() => { cacheStatus.textContent = ""; }, 3000);
  } catch (err) {
    cacheStatus.textContent = `Error: ${err.message}`;
  }
}
