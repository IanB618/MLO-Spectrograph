async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }
  return response.json();
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

function stateBadge(value) {
  const state = value || "unknown";
  return `<span class="badge badge-${escapeHtml(state)}">${escapeHtml(state.toUpperCase())}</span>`;
}

function connectionBadge(device) {
  if (!device || !device.connected) {
    return '<span class="badge badge-offline">OFFLINE</span>';
  }
  if (device.ready) {
    return '<span class="badge badge-ready">READY</span>';
  }
  return '<span class="badge badge-busy">BUSY</span>';
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function renderDeviceTable(status) {
  const devices = [
    ["Science camera", status.science_camera],
    ["Acquisition camera", status.acquisition_camera],
    ["Lens controller", status.lens],
    ["ACE TCS", status.tcs],
  ];
  document.getElementById("device-table").innerHTML = `
    <table>
      <thead>
        <tr><th>Subsystem</th><th>Status</th><th>Backend state</th><th>Message</th></tr>
      </thead>
      <tbody>
        ${devices.map(([label, device]) => `
          <tr>
            <td>${escapeHtml(label)}</td>
            <td>${connectionBadge(device)}</td>
            <td>${escapeHtml(device.state || "--")}</td>
            <td>${escapeHtml(device.message || "--")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
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

function updateStatus(status) {
  document.getElementById("system-state-badge").outerHTML = stateBadge(status.state).replace("<span", '<span id="system-state-badge"');
  setText("system-message", status.message || "--");

  const science = status.science_camera;
  setText("science-summary", `${formatNumber(science.temperature_c, 1, " C")} / ${formatNumber(science.setpoint_c, 1, " C")}`);
  setText("science-note", `${science.connected ? "Connected" : "Offline"}; cooler ${formatNumber(science.cooler_power_pct, 0, "%")}`);

  const tcs = status.tcs;
  setText("tcs-summary", tcs.target_name || "No target");
  setText("tcs-note", `${tcs.tracking ? "Tracking" : "Not tracking"}; ${tcs.guiding ? "guiding" : "not guiding"}`);

  if (status.last_exposure) {
    setText("last-exposure-summary", `${status.last_exposure.image_type} ${formatNumber(status.last_exposure.exposure_s, 1, " s")}`);
    setText("last-exposure-note", status.last_exposure.exposure_id);
  } else {
    setText("last-exposure-summary", "None");
    setText("last-exposure-note", "No science exposure recorded.");
  }

  renderDeviceTable(status);
  renderKeyGrid("tcs-status", [
    ["Connection", tcs.connected ? "Connected" : "Offline"],
    ["Target", tcs.target_name || "--"],
    ["RA / Dec", `${tcs.ra || "--"} / ${tcs.dec || "--"}`],
    ["Alt / Az", `${formatNumber(tcs.altitude_deg, 1, " deg")} / ${formatNumber(tcs.azimuth_deg, 1, " deg")}`],
    ["Airmass", formatNumber(tcs.airmass, 2)],
    ["Tracking / Guiding", `${formatBool(tcs.tracking)} / ${formatBool(tcs.guiding)}`],
  ]);
  renderKeyGrid("science-camera-status", [
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
    alert(error.message);
  }
}

document.addEventListener("click", (event) => {
  const action = event.target.dataset.action;
  if (!action) {
    return;
  }

  if (action === "connect") {
    runAndRefresh(() => api("/api/connect", {method: "POST"}));
  }
  if (action === "disconnect") {
    runAndRefresh(() => api("/api/disconnect", {method: "POST"}));
  }
  if (action === "safe") {
    runAndRefresh(() => api("/api/safe", {method: "POST", body: JSON.stringify({message: "Manual safe mode from UI"})}));
  }
  if (action === "clear-safe") {
    runAndRefresh(() => api("/api/safe/clear", {method: "POST"}));
  }
  if (action === "abort-exposure") {
    runAndRefresh(() => api("/api/science-camera/abort", {method: "POST"}));
  }
  if (action === "home-axis") {
    const form = document.getElementById("motion-form");
    const payload = formPayload(form);
    runAndRefresh(() => api("/api/motion/home", {method: "POST", body: JSON.stringify({axis: payload.axis})}));
  }
  if (action === "focus-sweep") {
    runAndRefresh(async () => {
      const result = await api("/api/lens/focus-sweep", {method: "POST"});
      renderResult("calibration-output", "Focus sweep result", {"Best position": result.best_position});
    });
  }
  if (action === "center-target") {
    runAndRefresh(async () => {
      const result = await api("/api/acquisition/center", {method: "POST"});
      renderResult("acq-output", "Centering result", {"Delta east": `${result.dx_arcsec} arcsec`, "Delta north": `${result.dy_arcsec} arcsec`});
    });
  }
  if (action === "run-calibration") {
    runAndRefresh(async () => {
      const result = await api("/api/calibration/run", {method: "POST"});
      renderResult("calibration-output", "Calibration result", {"Frames produced": result.frames.length});
    });
  }
});

document.getElementById("temperature-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["setpoint_c"]);
  runAndRefresh(() => api("/api/science-camera/temperature", {method: "POST", body: JSON.stringify(payload)}));
});

document.getElementById("exposure-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["exposure_s"]);
  runAndRefresh(async () => {
    const result = await api("/api/science-camera/expose", {method: "POST", body: JSON.stringify(payload)});
    renderResult("calibration-output", "Exposure complete", {
      "Exposure ID": result.exposure_id,
      "Image type": result.image_type,
      "Exposure": `${result.exposure_s} s`,
      "File": result.path,
    });
  });
});

document.getElementById("acq-preview-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["exposure_s"]);
  runAndRefresh(async () => {
    const result = await api("/api/acquisition/preview", {method: "POST", body: JSON.stringify(payload)});
    renderResult("acq-output", "Preview captured", {"Preview file": result.path});
  });
});

document.getElementById("motion-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["position", "delta"]);
  runAndRefresh(() => api("/api/motion/move", {method: "POST", body: JSON.stringify(payload)}));
});

document.getElementById("lens-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["position", "delta"]);
  runAndRefresh(() => api("/api/lens/move", {method: "POST", body: JSON.stringify(payload)}));
});

document.getElementById("tcs-offset-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const payload = numericFields(formPayload(event.target), ["east_arcsec", "north_arcsec"]);
  runAndRefresh(async () => {
    const result = await api("/api/tcs/offset", {method: "POST", body: JSON.stringify(payload)});
    renderResult("acq-output", "TCS offset requested", {
      "Total east offset": `${result.east_offset_arcsec} arcsec`,
      "Total north offset": `${result.north_offset_arcsec} arcsec`,
    });
  });
});

refreshStatus();
refreshLog();
setInterval(refreshStatus, 2000);
setInterval(refreshLog, 10000);
