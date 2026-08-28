class ApiError extends Error {
  constructor({statusCode, statusText, title, message, details, hint, type}) {
    super(message || title || "Request failed");
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.statusText = statusText;
    this.title = title || "Request failed";
    this.details = details || [];
    this.hint = hint || "";
    this.type = type || "";
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  if (!response.ok) {
    throw await parseApiError(response);
  }
  return response.json();
}

async function parseApiError(response) {
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => ({}));
    return new ApiError({
      statusCode: payload.status_code || response.status,
      statusText: payload.status || response.statusText,
      title: payload.error || "Request failed",
      message: payload.message || response.statusText,
      details: payload.details || [],
      hint: payload.hint,
      type: payload.type,
    });
  }

  const text = await response.text();
  const message = extractHtmlError(text) || response.statusText || "The server returned a non-JSON error response.";
  return new ApiError({
    statusCode: response.status,
    statusText: response.statusText,
    title: "Server returned HTML error page",
    message,
    details: [],
    hint: "Check the Flask server log for the full traceback.",
  });
}

function extractHtmlError(text) {
  if (!text) {
    return "";
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, "text/html");
  const errorMessage = doc.querySelector(".errormsg")?.textContent?.trim();
  const title = doc.querySelector("title")?.textContent?.trim();
  return errorMessage || title || text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300);
}

function formPayload(form) {
  const data = new FormData(form);
  const payload = {};
  for (const [key, value] of data.entries()) {
    if (value !== "") {
      payload[key] = value;
    }
  }
  return payload;
}

function numericFields(payload, fields) {
  for (const field of fields) {
    if (payload[field] !== undefined) {
      payload[field] = Number(payload[field]);
    }
  }
  return payload;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function formatBool(value) {
  return value ? "Yes" : "No";
}

function formatNumber(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatTuple(value) {
  if (!Array.isArray(value)) {
    return "--";
  }
  return value.join(" x ");
}

function badgeTone(value) {
  const state = String(value || "unknown").toLowerCase();
  if (["ready", "idle", "ok", "connected", "mock"].includes(state)) {
    return "ready";
  }
  if (["busy", "moving", "slewing", "tracking", "acquiring", "focusing", "exposing", "calibrating"].includes(state)) {
    return "busy";
  }
  if (["error", "alert", "fault", "failed"].includes(state)) {
    return "error";
  }
  if (["offline", "disconnected"].includes(state)) {
    return "offline";
  }
  return "unknown";
}

function stateBadge(value) {
  const state = String(value || "unknown").toLowerCase();
  return `<span class="badge badge-${badgeTone(state)}">${escapeHtml(state.toUpperCase())}</span>`;
}

function deviceStateBadge(device) {
  if (!device || !device.connected) {
    return stateBadge("offline");
  }
  return stateBadge(device.state || (device.ready ? "ready" : "busy"));
}

function setBadge(id, html) {
  const element = document.getElementById(id);
  if (element) {
    element.outerHTML = html.replace("<span", `<span id="${id}"`);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function hideError() {
  const panel = document.getElementById("action-error");
  if (panel) {
    panel.classList.add("hidden");
  }
}

function normalizeErrorDetail(detail) {
  if (typeof detail === "string") {
    return ["Detail", detail];
  }
  if (detail && typeof detail === "object") {
    const location = Array.isArray(detail.loc) ? detail.loc.join(".") : detail.loc;
    const label = location || detail.type || "Detail";
    const message = detail.msg || JSON.stringify(detail);
    return [label, message];
  }
  return ["Detail", String(detail)];
}

function showError(error) {
  const panel = document.getElementById("action-error");
  if (!panel) {
    alert(error.message || String(error));
    return;
  }

  const status = [error.statusCode, error.statusText].filter(Boolean).join(" ");
  const details = [];
  if (error.type) {
    details.push(["Error type", error.type]);
  }
  if (error.hint) {
    details.push(["Suggested check", error.hint]);
  }
  for (const detail of error.details || []) {
    details.push(normalizeErrorDetail(detail));
  }

  document.getElementById("action-error-status").textContent = status || "Request failed";
  document.getElementById("action-error-title").textContent = error.title || "Instrument command failed";
  document.getElementById("action-error-message").textContent = error.message || String(error);
  document.getElementById("action-error-details").innerHTML = details.map(([key, value]) => `
    <div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>
  `).join("");
  panel.classList.remove("hidden");
  panel.scrollIntoView({behavior: "smooth", block: "nearest"});
}

function renderKeyGrid(targetId, rows) {
  const target = document.getElementById(targetId);
  target.innerHTML = rows.map(([label, value]) => `
    <div class="key-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderAxisTable(axes) {
  document.getElementById("axis-status").innerHTML = `
    <table>
      <thead>
        <tr><th>Axis</th><th>Position</th><th>Units</th><th>Homed</th><th>Limits</th><th>Fault</th></tr>
      </thead>
      <tbody>
        ${axes.map((axis) => `
          <tr>
            <td>${escapeHtml(axis.name)}</td>
            <td>${formatNumber(axis.position, 0)}</td>
            <td>${escapeHtml(axis.units)}</td>
            <td>${formatBool(axis.homed)}</td>
            <td>${formatNumber(axis.min_limit, 0)} to ${formatNumber(axis.max_limit, 0)}</td>
            <td>${escapeHtml(axis.fault || "--")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
  updateMotionAxisOptions(axes);
}

function updateMotionAxisOptions(axes) {
  const select = document.querySelector('#motion-form select[name="axis"]');
  if (!select || !axes.length) {
    return;
  }
  const current = select.value;
  select.innerHTML = axes.map((axis) => `<option value="${escapeHtml(axis.name)}">${escapeHtml(axis.name)}</option>`).join("");
  if (axes.some((axis) => axis.name === current)) {
    select.value = current;
  }
}

function populateDeviceSelect(selectId, names, selected) {
  const select = document.getElementById(selectId);
  if (!select) {
    return;
  }

  const uniqueNames = [...new Set([selected, ...names].filter(Boolean))];
  select.replaceChildren();
  for (const name of uniqueNames) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  }
  if (selected) {
    select.value = selected;
  }
}

function updateIndiDeviceSelectors(payload) {
  const devices = payload.devices || [];
  const allNames = devices.map((device) => device.name);
  let cameraNames = devices.filter((device) => device.camera).map((device) => device.name);
  let focuserNames = devices.filter((device) => device.focuser).map((device) => device.name);

  if (!cameraNames.length) {
    cameraNames = allNames;
  }
  if (!focuserNames.length) {
    focuserNames = allNames;
  }

  populateDeviceSelect(
    "indi-science-camera",
    cameraNames,
    payload.selected?.science_camera,
  );
  populateDeviceSelect(
    "indi-lens",
    focuserNames,
    payload.selected?.lens,
  );
}

async function refreshIndiDevices() {
  const payload = await api("/api/indi/devices");
  updateIndiDeviceSelectors(payload);
  const count = payload.devices?.length || 0;
  setText(
    "indi-device-message",
    count === 1 ? "Discovered 1 INDI device." : `Discovered ${count} INDI devices.`,
  );
}

function renderLog(log) {
  const target = document.getElementById("log-output");
  if (!log.length) {
    target.className = "table-wrap empty-state";
    target.textContent = "No log entries yet.";
    return;
  }
  target.className = "table-wrap";
  target.innerHTML = `
    <table>
      <thead>
        <tr><th>UTC time</th><th>Object</th><th>Type</th><th>Exposure</th><th>File</th><th>Status</th></tr>
      </thead>
      <tbody>
        ${log.slice().reverse().map((entry) => {
          const request = entry.request || {};
          const result = entry.result || {};
          return `
            <tr>
              <td>${escapeHtml(entry.timestamp || "--")}</td>
              <td>${escapeHtml(request.object_name || "--")}</td>
              <td>${escapeHtml(result.image_type || request.image_type || "--")}</td>
              <td>${formatNumber(result.exposure_s || request.exposure_s, 1, " s")}</td>
              <td><code>${escapeHtml(result.path || "--")}</code></td>
              <td>${result.success ? '<span class="badge badge-ready">OK</span>' : '<span class="badge badge-error">FAIL</span>'}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderResult(targetId, title, rows) {
  const target = document.getElementById(targetId);
  target.className = "result-box";
  target.innerHTML = `
    <strong>${escapeHtml(title)}</strong>
    <dl>
      ${Object.entries(rows).map(([key, value]) => `
        <div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>
      `).join("")}
    </dl>
  `;
}

const SCIENCE_JS9_DISPLAY_ID = "scienceJS9";
const sciencePreviewState = {
  ready: false,
  loadError: false,
  latestExposure: null,
  loadedExposureId: null,
  loadingExposureId: null,
  image: null,
  loadTimer: null,
  loadSequence: 0,
  displayWidth: null,
  displayHeight: null,
  resizeObserver: null,
  resizeFrame: null,
};

function setSciencePreviewStatus(message, tone = "muted") {
  const target = document.getElementById("science-preview-status");
  if (!target) {
    return;
  }
  target.textContent = message;
  target.dataset.tone = tone;
}

function scienceJs9DisplayExists() {
  if (!window.JS9) {
    return false;
  }
  try {
    return Boolean(window.JS9.LookupDisplay(SCIENCE_JS9_DISPLAY_ID, false));
  } catch (error) {
    return false;
  }
}

function scienceJs9PluginHeight(elementId) {
  const element = document.getElementById(elementId);
  return element ? Math.ceil(element.getBoundingClientRect().height) : 0;
}

function getScienceJs9TargetDimensions() {
  const shell = document.querySelector(".science-js9-shell");
  if (!shell) {
    return null;
  }

  const style = window.getComputedStyle(shell);
  const horizontalPadding =
    Number.parseFloat(style.paddingLeft || "0") +
    Number.parseFloat(style.paddingRight || "0");
  const verticalPadding =
    Number.parseFloat(style.paddingTop || "0") +
    Number.parseFloat(style.paddingBottom || "0");

  const width = Math.floor(shell.clientWidth - horizontalPadding);
  const pluginHeight =
    scienceJs9PluginHeight(`${SCIENCE_JS9_DISPLAY_ID}Menubar`) +
    scienceJs9PluginHeight(`${SCIENCE_JS9_DISPLAY_ID}Colorbar`) +
    scienceJs9PluginHeight(`${SCIENCE_JS9_DISPLAY_ID}Statusbar`);
  const height = Math.floor(shell.clientHeight - verticalPadding - pluginHeight);

  return {
    width: Math.max(320, width),
    height: Math.max(280, height),
  };
}

function fitScienceJs9Image() {
  if (!sciencePreviewState.image || !window.JS9) {
    return;
  }
  try {
    window.JS9.SetZoom("toFit", {display: sciencePreviewState.image});
  } catch (error) {
    console.error("Could not fit the JS9 science image", error);
  }
}

function resizeScienceJs9({force = false} = {}) {
  if (!sciencePreviewState.ready || !window.JS9) {
    return;
  }

  const target = getScienceJs9TargetDimensions();
  if (!target) {
    return;
  }

  const widthChanged = Math.abs(target.width - (sciencePreviewState.displayWidth || 0)) >= 2;
  const heightChanged = Math.abs(target.height - (sciencePreviewState.displayHeight || 0)) >= 2;
  if (!force && !widthChanged && !heightChanged) {
    return;
  }

  try {
    window.JS9.ResizeDisplay(
      SCIENCE_JS9_DISPLAY_ID,
      target.width,
      target.height,
      {
        resizeMenubar: true,
        resizeColorbar: true,
        resizeStatusbar: true,
      },
    );
    sciencePreviewState.displayWidth = target.width;
    sciencePreviewState.displayHeight = target.height;

    window.requestAnimationFrame(() => {
      fitScienceJs9Image();
      // Menubar wrapping can change its height after a width update. A second
      // pass converges on the remaining image height without creating a loop.
      scheduleScienceJs9Resize();
    });
  } catch (error) {
    console.error("Could not resize the JS9 science display", error);
  }
}

function scheduleScienceJs9Resize() {
  if (sciencePreviewState.resizeFrame !== null) {
    window.cancelAnimationFrame(sciencePreviewState.resizeFrame);
  }
  sciencePreviewState.resizeFrame = window.requestAnimationFrame(() => {
    sciencePreviewState.resizeFrame = null;
    resizeScienceJs9();
  });
}

function observeScienceJs9Size() {
  const shell = document.querySelector(".science-js9-shell");
  if (!shell) {
    return;
  }

  if (window.ResizeObserver) {
    sciencePreviewState.resizeObserver = new ResizeObserver(scheduleScienceJs9Resize);
    sciencePreviewState.resizeObserver.observe(shell);
  } else {
    window.addEventListener("resize", scheduleScienceJs9Resize);
  }
}

function markScienceJs9Ready() {
  if (sciencePreviewState.ready || !scienceJs9DisplayExists()) {
    return;
  }
  sciencePreviewState.ready = true;
  resizeScienceJs9({force: true});
  setSciencePreviewStatus("JS9 ready; no science exposure loaded.");
  loadLatestSciencePreview();
}

function initializeScienceJs9() {
  if (window.__js9LoadError || !window.JS9 || !window.jQuery) {
    sciencePreviewState.loadError = true;
    setSciencePreviewStatus(
      "JS9 could not be loaded. Check network access or ICS_JS9_ASSET_BASE.",
      "error",
    );
    return;
  }

  window.jQuery(document).on("JS9:ready", markScienceJs9Ready);
  observeScienceJs9Size();
  markScienceJs9Ready();

  // JS9 normally becomes ready at DOM-ready time. This also covers pages where
  // its ready event fired before this application handler was registered.
  let attempts = 0;
  const readyPoll = window.setInterval(() => {
    attempts += 1;
    markScienceJs9Ready();
    if (sciencePreviewState.ready || attempts >= 40) {
      window.clearInterval(readyPoll);
      if (!sciencePreviewState.ready) {
        sciencePreviewState.loadError = true;
        setSciencePreviewStatus("JS9 did not initialize its science display.", "error");
      }
    }
  }, 250);
}

function syncSciencePreview(exposure) {
  sciencePreviewState.latestExposure = exposure || null;
  if (sciencePreviewState.loadError) {
    return;
  }
  if (!exposure) {
    if (!sciencePreviewState.loadedExposureId && !sciencePreviewState.loadingExposureId) {
      setSciencePreviewStatus(
        sciencePreviewState.ready
          ? "No completed science exposure is available."
          : "Waiting for JS9 and a completed science exposure.",
      );
    }
    return;
  }

  if (
    exposure.exposure_id === sciencePreviewState.loadedExposureId ||
    exposure.exposure_id === sciencePreviewState.loadingExposureId
  ) {
    return;
  }
  loadLatestSciencePreview();
}

function loadLatestSciencePreview({force = false} = {}) {
  const exposure = sciencePreviewState.latestExposure;
  if (!exposure) {
    setSciencePreviewStatus("No completed science exposure is available.");
    return;
  }
  if (!sciencePreviewState.ready) {
    if (!sciencePreviewState.loadError) {
      setSciencePreviewStatus(`Waiting for JS9 to display ${exposure.exposure_id}.`);
    }
    return;
  }
  if (!force && exposure.exposure_id === sciencePreviewState.loadedExposureId) {
    return;
  }

  const exposureId = exposure.exposure_id;
  const loadSequence = ++sciencePreviewState.loadSequence;
  const imageId = `${exposureId}.fits`;
  const refreshImage = sciencePreviewState.image;
  const requestUrl = new URL("/api/science-camera/latest.fits", window.location.origin);
  requestUrl.searchParams.set("exposure_id", exposureId);
  requestUrl.searchParams.set("revision", `${exposureId}-${loadSequence}-${Date.now()}`);

  sciencePreviewState.loadingExposureId = exposureId;
  setSciencePreviewStatus(`Loading ${exposureId}...`);

  if (sciencePreviewState.loadTimer) {
    window.clearTimeout(sciencePreviewState.loadTimer);
  }
  sciencePreviewState.loadTimer = window.setTimeout(() => {
    if (sciencePreviewState.loadSequence === loadSequence) {
      sciencePreviewState.loadingExposureId = null;
      setSciencePreviewStatus(`JS9 timed out while loading ${exposureId}.`, "error");
    }
  }, 60000);

  try {
    window.JS9.Load(
      requestUrl.toString(),
      {
        id: imageId,
        file: imageId,
        scale: "linear",
        colormap: "grey",
        refresh: refreshImage || false,
        onload: (image) => {
          if (sciencePreviewState.loadSequence !== loadSequence) {
            if (image && image !== sciencePreviewState.image) {
              window.JS9.CloseImage({display: image});
            }
            return;
          }
          if (sciencePreviewState.loadTimer) {
            window.clearTimeout(sciencePreviewState.loadTimer);
            sciencePreviewState.loadTimer = null;
          }

          const previousImage = sciencePreviewState.image;
          sciencePreviewState.image = image;
          sciencePreviewState.loadedExposureId = exposureId;
          sciencePreviewState.loadingExposureId = null;

          window.JS9.SetColormap("grey", {display: image});
          window.JS9.SetScale("zscale", {display: image});
          resizeScienceJs9({force: true});
          fitScienceJs9Image();
          setSciencePreviewStatus(`Displaying ${exposureId}.`, "ready");

          if (previousImage && previousImage !== image) {
            window.JS9.CloseImage({display: previousImage});
          }
        },
      },
      {display: SCIENCE_JS9_DISPLAY_ID},
    );
  } catch (error) {
    if (sciencePreviewState.loadTimer) {
      window.clearTimeout(sciencePreviewState.loadTimer);
      sciencePreviewState.loadTimer = null;
    }
    sciencePreviewState.loadingExposureId = null;
    setSciencePreviewStatus(`Could not load FITS preview: ${error.message || error}`, "error");
    console.error("JS9 FITS preview load failed", error);
  }
}

function updateStatus(status) {
  setBadge("system-state-badge", stateBadge(status.state));
  setText("system-message", status.message || "--");

  const science = status.science_camera;
  const scienceName = science.name || "Science camera";
  setText("science-camera-label", scienceName);
  setText("science-camera-title", `Science Camera / ${scienceName}`);
  setBadge("science-state-badge", deviceStateBadge(science));
  setText("science-summary", `${formatNumber(science.temperature_c, 1, " C")} / ${formatNumber(science.setpoint_c, 1, " C")}`);
  setText("science-note", `Cooler ${formatNumber(science.cooler_power_pct, 0, "%")}; ${science.exposing ? "exposing" : "not exposing"}`);
  setText("science-message", science.message || (science.connected ? "Connected" : "Offline"));

  const tcs = status.tcs;
  setBadge("tcs-state-badge", deviceStateBadge(tcs));
  setText("tcs-summary", tcs.target_name || "No target");
  setText("tcs-note", `${tcs.tracking ? "Tracking" : "Not tracking"}; ${tcs.guiding ? "guiding" : "not guiding"}`);
  setText("tcs-message", tcs.message || (tcs.connected ? "Connected" : "Offline"));

  const acquisition = status.acquisition_camera;
  setBadge("acquisition-state-badge", deviceStateBadge(acquisition));
  setText("acquisition-summary", acquisition.exposing ? "Exposure in progress" : (acquisition.ready ? "Ready" : "Unavailable"));
  setText("acquisition-note", `${formatNumber(acquisition.temperature_c, 1, " C")}; ${acquisition.gain_mode || "readout mode unavailable"}`);
  setText("acquisition-message", acquisition.message || (acquisition.connected ? "Connected" : "Offline"));

  const lens = status.lens;
  setText("lens-control-title", `Camera Lens Focus / ${lens.name || "Lens"}`);
  setBadge("lens-state-badge", deviceStateBadge(lens));
  setText("lens-summary", `Position ${lens.position ?? "--"}`);
  setText("lens-note", lens.moving ? "Moving" : "Stationary");
  setText("lens-message", lens.message || (lens.connected ? "Connected" : "Offline"));

  if (status.last_exposure) {
    setText("last-exposure-summary", `${status.last_exposure.image_type} ${formatNumber(status.last_exposure.exposure_s, 1, " s")}`);
    setText("last-exposure-note", status.last_exposure.exposure_id);
  } else {
    setText("last-exposure-summary", "None");
    setText("last-exposure-note", "No science exposure recorded.");
  }

  syncSciencePreview(status.last_exposure);

  renderKeyGrid("tcs-status", [
    ["Connection", tcs.connected ? "Connected" : "Offline"],
    ["Target", tcs.target_name || "--"],
    ["RA / Dec", `${tcs.ra || "--"} / ${tcs.dec || "--"}`],
    ["Alt / Az", `${formatNumber(tcs.altitude_deg, 1, " deg")} / ${formatNumber(tcs.azimuth_deg, 1, " deg")}`],
    ["Airmass", formatNumber(tcs.airmass, 2)],
    ["Tracking / Guiding", `${formatBool(tcs.tracking)} / ${formatBool(tcs.guiding)}`],
  ]);
  renderKeyGrid("science-camera-status", [
    ["Camera", scienceName],
    ["Connection", science.connected ? "Connected" : "Offline"],
    ["Temperature", formatNumber(science.temperature_c, 2, " C")],
    ["Setpoint", formatNumber(science.setpoint_c, 2, " C")],
    ["Cooler power", formatNumber(science.cooler_power_pct, 0, "%")],
    ["Exposing", formatBool(science.exposing)],
    ["Binning", formatTuple(science.binning)],
    ["ROI", formatTuple(science.roi)],
    ["Gain mode", science.gain_mode || "--"],
  ]);
  renderKeyGrid("acquisition-camera-status", [
    ["Connection", status.acquisition_camera.connected ? "Connected" : "Offline"],
    ["Ready", formatBool(status.acquisition_camera.ready)],
    ["Exposing", formatBool(status.acquisition_camera.exposing)],
    ["Binning", formatTuple(status.acquisition_camera.binning)],
    ["ROI", formatTuple(status.acquisition_camera.roi)],
    ["Readout mode", status.acquisition_camera.gain_mode || "--"],
  ]);
  renderAxisTable(status.axes || []);
  renderKeyGrid("lens-status", [
    ["Connection", status.lens.connected ? "Connected" : "Offline"],
    ["Ready", formatBool(status.lens.ready)],
    ["Position", status.lens.position ?? "--"],
    ["Moving", formatBool(status.lens.moving)],
  ]);
}

async function refreshStatus() {
  const status = await api("/api/status");
  updateStatus(status);
}

async function refreshLog() {
  const log = await api("/api/log");
  renderLog(log);
}

async function runAndRefresh(task) {
  try {
    await task();
    await refreshStatus();
    await refreshLog();
  } catch (error) {
    showError(error);
  }
}

function bindSubmit(formId, handler) {
  const form = document.getElementById(formId);
  if (!form) {
    console.warn(`Skipping submit handler for missing form #${formId}`);
    return;
  }
  form.addEventListener("submit", handler);
}

async function initializePage() {
  try {
    await Promise.all([refreshStatus(), refreshLog()]);
  } catch (error) {
    setBadge("system-state-badge", stateBadge("error"));
    setText("system-message", error.message || "Initial status request failed");
    showError(error);
  }
}

function poll(task) {
  task().catch((error) => {
    console.error("Periodic refresh failed", error);
  });
}

document.addEventListener("click", (event) => {
  const action = event.target.dataset.action;
  if (!action) {
    return;
  }

  if (action === "dismiss-error") {
    hideError();
  }
  if (action === "connect") {
    hideError();
    runAndRefresh(() => api("/api/connect", {method: "POST"}));
  }
  if (action === "disconnect") {
    runAndRefresh(() => api("/api/disconnect", {method: "POST"}));
  }
  if (action === "abort-exposure") {
    runAndRefresh(() => api("/api/science-camera/abort", {method: "POST"}));
  }
  if (action === "refresh-indi-devices") {
    hideError();
    refreshIndiDevices().catch(showError);
  }
  if (action === "reload-science-preview") {
    loadLatestSciencePreview({force: true});
  }
  if (action === "home-axis") {
    const form = document.getElementById("motion-form");
    const payload = formPayload(form);
    runAndRefresh(() => api("/api/motion/home", {method: "POST", body: JSON.stringify({axis: payload.axis})}));
  }
  if (action === "calibrate-lens") {
    runAndRefresh(async () => {
      await api("/api/lens/calibrate", {method: "POST"});
      renderResult("lens-output", "Lens calibration started", {
        "INDI property": "CALIBRATE.CALIBRATE",
      });
    });
  }
});

bindSubmit("indi-devices-form", (event) => {
  event.preventDefault();
  const payload = formPayload(event.target);
  runAndRefresh(async () => {
    const result = await api("/api/indi/devices", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setText(
      "indi-device-message",
      `Using ${result.selected.science_camera} and ${result.selected.lens} for this ICS session.`,
    );
  });
});

bindSubmit("temperature-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["setpoint_c"]);
  runAndRefresh(() => api("/api/science-camera/temperature", {method: "POST", body: JSON.stringify(payload)}));
});

bindSubmit("exposure-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["exposure_s"]);
  runAndRefresh(async () => {
    const result = await api("/api/science-camera/expose", {method: "POST", body: JSON.stringify(payload)});
    renderResult("science-camera-output", "Exposure complete", {
      "Exposure ID": result.exposure_id,
      "Image type": result.image_type,
      "Exposure": `${result.exposure_s} s`,
      "File": result.path,
    });
    syncSciencePreview(result);
  });
});

bindSubmit("acq-preview-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["exposure_s"]);
  runAndRefresh(async () => {
    const result = await api("/api/acquisition/preview", {method: "POST", body: JSON.stringify(payload)});
    renderResult("acq-output", "Guide camera preview captured", {"ACE result": result.path});
  });
});

bindSubmit("motion-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["position", "delta"]);
  runAndRefresh(() => api("/api/motion/move", {method: "POST", body: JSON.stringify(payload)}));
});

bindSubmit("lens-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["position"]);
  runAndRefresh(async () => {
    const result = await api("/api/lens/move", {method: "POST", body: JSON.stringify(payload)});
    renderResult("lens-output", "Lens focus move requested", {
      "Target position": payload.position,
      "Reported position": result.lens?.position ?? "--",
      "State": result.lens?.state || "--",
    });
  });
});

bindSubmit("lens-aperture-absolute-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["f_stop"]);
  runAndRefresh(async () => {
    await api("/api/lens/aperture/absolute", {method: "POST", body: JSON.stringify(payload)});
    renderResult("lens-output", "Lens aperture set", {
      "Aperture": `f/${formatNumber(payload.f_stop, 2)}`,
      "INDI property": "ABS_APERTURE.APERTURE_ABSOLUTE",
    });
  });
});

bindSubmit("lens-aperture-relative-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["delta"]);
  runAndRefresh(async () => {
    await api("/api/lens/aperture/relative", {method: "POST", body: JSON.stringify(payload)});
    renderResult("lens-output", "Lens aperture adjusted", {
      "Relative change": `${payload.delta >= 0 ? "+" : ""}${formatNumber(payload.delta, 2)}`,
      "INDI property": "REL_APERTURE.APERTURE_RELATIVE",
    });
  });
});

bindSubmit("tcs-goto-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["ra_deg", "dec_deg"]);
  runAndRefresh(async () => {
    const result = await api("/api/tcs/goto-j2000", {method: "POST", body: JSON.stringify(payload)});
    renderResult("acq-output", "TCS J2000 slew requested", {
      "RA": `${formatNumber(result.ra_deg, 6)} deg`,
      "Dec": `${formatNumber(result.dec_deg, 6)} deg`,
      "Message": result.message || "--",
    });
  });
});

bindSubmit("tcs-offset-form", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["east_arcsec", "north_arcsec"]);
  runAndRefresh(async () => {
    const result = await api("/api/tcs/offset", {method: "POST", body: JSON.stringify(payload)});
    renderResult("acq-output", "TCS offset requested", {
      "East offset": `${formatNumber(result.east_offset_arcsec, 2)} arcsec`,
      "North offset": `${formatNumber(result.north_offset_arcsec, 2)} arcsec`,
      "Commanded RA": `${formatNumber(result.commanded_ra_deg, 6)} deg`,
      "Commanded Dec": `${formatNumber(result.commanded_dec_deg, 6)} deg`,
      "Method": result.method || "--",
    });
  });
});

initializeScienceJs9();
initializePage();
setInterval(() => poll(refreshStatus), 2000);
setInterval(() => poll(refreshLog), 10000);
