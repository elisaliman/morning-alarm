const btn = document.getElementById("btn-wake");
const status = document.getElementById("status");
const scriptBox = document.getElementById("script-box");
const scriptText = document.getElementById("script-text");
const player = document.getElementById("player");

// --- Wake ---

async function handleWake() {
  btn.disabled = true;
  btn.textContent = "Brewing\u2026";
  status.textContent = "Fetching weather, calendar, and crafting your morning\u2026";
  scriptBox.classList.add("hidden");

  try {
    const res = await fetch("/generate-morning");
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const data = await res.json();

    scriptText.textContent = data.script
      .replace(/\[sfx:[^\]]*\]/gi, "")
      .replace(/\n{2,}/g, "\n\n")
      .trim();
    scriptBox.classList.remove("hidden");

    player.src = data.audio_url;
    player.play();

    status.textContent = "Playing your morning\u2026";

    player.addEventListener(
      "ended",
      () => { status.textContent = "Have a wonderful day."; },
      { once: true }
    );
  } catch (err) {
    status.textContent = `Something went wrong: ${err.message}`;
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Wake Me Up";
  }
}

// --- Settings modal ---

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
    document.getElementById("loc-name").value = loc.name || "";
    document.getElementById("loc-lat").value = loc.lat || "";
    document.getElementById("loc-lon").value = loc.lon || "";

    renderGoogleStatus(data.google || {});
  } catch (err) {
    console.error("Failed to load settings", err);
  }
}

function renderGoogleStatus(google) {
  const statusEl = document.getElementById("google-status");
  const connectBtn = document.getElementById("btn-google-connect");
  const disconnectBtn = document.getElementById("btn-google-disconnect");

  if (google.connected) {
    statusEl.innerHTML = `Connected as <span class="text-indigo-300">${google.email}</span>`;
    connectBtn.textContent = "Switch Account";
    connectBtn.classList.remove("hidden");
    disconnectBtn.classList.remove("hidden");
  } else {
    statusEl.textContent = "No Google account connected";
    connectBtn.textContent = "Connect Account";
    connectBtn.classList.remove("hidden");
    disconnectBtn.classList.add("hidden");
  }
}

// --- Location ---

async function saveLocation() {
  const lat = document.getElementById("loc-lat").value.trim();
  const lon = document.getElementById("loc-lon").value.trim();
  const name = document.getElementById("loc-name").value.trim();
  const locStatus = document.getElementById("loc-status");

  if (!lat || !lon) {
    locStatus.textContent = "Latitude and longitude are required.";
    return;
  }

  try {
    const res = await fetch("/api/settings/location", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, name }),
    });
    if (!res.ok) throw new Error("Save failed");
    locStatus.textContent = "Location saved.";
    setTimeout(() => { locStatus.textContent = ""; }, 3000);
  } catch (err) {
    locStatus.textContent = `Error: ${err.message}`;
  }
}

// --- Google Calendar ---

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
