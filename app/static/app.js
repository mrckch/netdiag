// ===================================================================
// netdiag v3 Frontend — Schnelltest-Workflow, 4 Tabs
// ===================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// HTML-Escape für alle Werte aus dem Netz (nmap-Hostnamen, LLDP-Switch-Namen
// usw.) und Nutzereingaben, bevor sie per innerHTML gerendert werden.
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}
const postJson = (path, body) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const patchJson = (path, body) => api(path, {
  method: "PATCH", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function fmtTs(unix) {
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------- State

let TREE = { floors: [] };
let DEVICE_TYPES = [];
let PENDING = null;          // { kind, result } — ungespeichertes Ergebnis
let LAST_SWITCH = null;      // { host, portName } aus letztem Autotest (für Port-Aktionen)
let PA_IFINDEX = null;       // aufgelöster ifIndex im Port-Aktionen-Tab
let VLAN_CURRENT = null;     // zuletzt gelesener VLAN-Zustand
let CURRENT_OUTLET = null;   // im Kataster-Detail geöffnete Dose

async function loadTree() { TREE = await api("/api/tree"); }
async function loadDeviceTypes() { DEVICE_TYPES = (await api("/api/device_types")).device_types; }

// ---------------------------------------------------------------- Tabs

$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "kataster") loadKataster();
    if (btn.dataset.tab === "portaktionen") renderPortAktionen();
    if (btn.dataset.tab === "verwaltung") loadVerwaltung();
  });
});

// ------------------------------------------------- Messen: Interfaces

async function loadIfaces() {
  const data = await api("/api/interfaces");
  const sel = $("#iface");
  sel.innerHTML = "";
  data.interfaces.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = opt.textContent = name;
    sel.appendChild(opt);
  });
}

// ------------------------------------------------- Ergebnis-UI-Helfer

function setLed(cardId, state) {
  const led = document.querySelector(`#${cardId} [data-led]`);
  if (!led) return;
  led.classList.remove("ok", "warn", "bad");
  if (state) led.classList.add(state);
}
function setBody(cardId, rows) {
  const dds = document.querySelectorAll(`#${cardId} [data-body] dd`);
  rows.forEach((val, i) => { if (dds[i]) dds[i].textContent = val ?? "—"; });
}
function markUnsaved(on) {
  $("#resultGrid").classList.toggle("unsaved", on);
  $("#saveBar").style.display = on ? "block" : "none";
  if (on) $("#saveStatus").textContent = "";
}

// ------------------------------------------------- Autotest (ohne Auto-Save)

async function runAutotest() {
  const iface = $("#iface").value;
  const btn = $("#runAutotest");
  btn.disabled = true;
  $("#runStatus").textContent = `teste ${iface} … (~10s)`;

  try {
    const data = await api(`/api/autotest?interface=${encodeURIComponent(iface)}`);
    PENDING = { kind: "autotest", result: data };

    const link = data.link;
    setBody("card-link", [
      link.error ? `Fehler: ${link.error}` : (link.link_detected ? "verbunden" : "kein Link"),
      link.speed, link.duplex,
    ]);
    setLed("card-link", link.error ? "bad" : (link.link_detected ? "ok" : "warn"));

    const neighbor = data.lldp.neighbors?.[0];
    const cdp = data.sniff?.cdp;
    const swName = neighbor?.switch_name || cdp?.device_id;
    const swPort = neighbor?.port_id || cdp?.port_id;
    const swIp = neighbor?.switch_mgmt_ip || cdp?.mgmt_ip;
    setBody("card-lldp", [
      swName || (data.lldp.error ? `Fehler: ${data.lldp.error}` : "kein Nachbar erkannt"),
      swPort || "—", swIp || "—",
    ]);
    setLed("card-lldp", swName ? "ok" : "warn");
    LAST_SWITCH = (swIp && swPort) ? { host: swIp, portName: swPort, name: swName } : null;
    PA_IFINDEX = null;
    VLAN_CURRENT = null;

    const sniff = data.sniff;
    setBody("card-vlan", [
      sniff.error ? `Fehler: ${sniff.error}` : (sniff.vlan_ids_seen.length ? sniff.vlan_ids_seen.join(", ") : "keine tagged VLANs"),
      sniff.eapol_seen ? "ja — 802.1X aktiv" : "nein",
      sniff.stp_seen ? "aktiv (BPDU)" : "keine BPDU",
    ]);
    setLed("card-vlan", sniff.error ? "bad" : "ok");

    const dhcp = data.dhcp;
    setBody("card-dhcp", [
      dhcp.offered_ip || (dhcp.error ? `Fehler: ${dhcp.error}` : "keine Antwort"),
      dhcp.router, dhcp.dns_servers, dhcp.subnet_mask,
    ]);
    setLed("card-dhcp", dhcp.server_found ? "ok" : "bad");

    const ping = data.ping_gateway;
    if (ping) {
      setBody("card-ping", [ping.reachable ? "ja" : "nein", ping.avg_ms ? `${ping.avg_ms} ms` : "—"]);
      setLed("card-ping", ping.reachable ? "ok" : "bad");
    } else {
      setBody("card-ping", ["kein Gateway bekannt", "—"]);
      setLed("card-ping", "warn");
    }

    setBody("card-iperf", ["—", "—", "—"]);
    setLed("card-iperf", null);

    markUnsaved(true);
    $("#runStatus").textContent = `fertig ${new Date().toLocaleTimeString()} — nicht gespeichert`;
  } catch (e) {
    $("#runStatus").textContent = `Fehler: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}
$("#runAutotest").addEventListener("click", runAutotest);

async function runIperf() {
  const btn = $("#runIperf");
  btn.disabled = true;
  $("#runStatus").textContent = "iperf läuft … (~25s beide Richtungen)";
  try {
    const data = await api("/api/iperf");
    if (data.error) {
      setBody("card-iperf", [`Fehler: ${data.error}`, "—", "—"]);
      setLed("card-iperf", "bad");
      $("#runStatus").textContent = "iperf-Fehler";
    } else {
      setBody("card-iperf", [
        data.mbps_down != null ? `${data.mbps_down} Mbit/s` : "—",
        data.mbps_up != null ? `${data.mbps_up} Mbit/s` : "—",
        data.retransmits ?? "—",
      ]);
      setLed("card-iperf", "ok");
      PENDING = { kind: "iperf", result: data };
      markUnsaved(true);
      $("#runStatus").textContent = `iperf fertig ${new Date().toLocaleTimeString()} — nicht gespeichert`;
    }
  } catch (e) {
    $("#runStatus").textContent = `Fehler: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}
$("#runIperf").addEventListener("click", runIperf);

// ------------------------------------------------- Zuordnen-Leiste (sticky)

const pickFloor = $("#pickFloor");
const pickRoom = $("#pickRoom");
const pickOutlet = $("#pickOutlet");

function fillPicker() {
  const prevFloor = pickFloor.value;
  pickFloor.innerHTML = '<option value="">Etage…</option>';
  TREE.floors.forEach((f) => {
    const o = document.createElement("option");
    o.value = f.id; o.textContent = f.name;
    pickFloor.appendChild(o);
  });
  if (prevFloor && [...pickFloor.options].some((o) => o.value === prevFloor)) pickFloor.value = prevFloor;
  fillRooms();
}
function fillRooms() {
  const floor = TREE.floors.find((f) => f.id == pickFloor.value);
  const prevRoom = pickRoom.value;
  pickRoom.innerHTML = '<option value="">Raum…</option>';
  pickRoom.disabled = !floor;
  (floor?.rooms || []).forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id; o.textContent = r.name;
    pickRoom.appendChild(o);
  });
  if (prevRoom && [...pickRoom.options].some((o) => o.value === prevRoom)) pickRoom.value = prevRoom;
  fillOutlets();
}
function fillOutlets() {
  const floor = TREE.floors.find((f) => f.id == pickFloor.value);
  const room = floor?.rooms.find((r) => r.id == pickRoom.value);
  const prevOutlet = pickOutlet.value;
  pickOutlet.innerHTML = '<option value="">Dose…</option>';
  pickOutlet.disabled = !room;
  $("#quickAddOutlet").disabled = !room;
  (room?.outlets || []).forEach((o) => {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = `${o.label}${o.device_icon ? " " + o.device_icon : ""}`;
    pickOutlet.appendChild(opt);
  });
  if (prevOutlet && [...pickOutlet.options].some((o) => o.value === prevOutlet)) pickOutlet.value = prevOutlet;
}
pickFloor.addEventListener("change", fillRooms);
pickRoom.addEventListener("change", fillOutlets);

$("#quickAddOutlet").addEventListener("click", async () => {
  const label = prompt("Bezeichnung der neuen Dose (z.B. D03):");
  if (!label) return;
  try {
    const created = await postJson("/api/outlets", { room_id: Number(pickRoom.value), label });
    await loadTree();
    fillPicker();
    pickOutlet.value = created.id;
  } catch (e) { alert(e.message); }
});

// Ein-Klick-Speichern: sticky Auswahl wird direkt übernommen
$("#saveMeasurement").addEventListener("click", async () => {
  if (!PENDING) return;
  const outletId = pickOutlet.value ? Number(pickOutlet.value) : null;
  try {
    await postJson("/api/measurements", {
      result: PENDING.result,
      kind: PENDING.kind,
      outlet_id: outletId,
    });
    PENDING = null;
    markUnsaved(false);
    $("#runStatus").textContent = outletId
      ? "✓ gespeichert & zugeordnet"
      : "✓ gespeichert (ohne Zuordnung — im Kataster nachholbar)";
    loadTree().then(fillPicker);
  } catch (e) {
    $("#saveStatus").textContent = `Fehler: ${e.message}`;
  }
});

// Netz-Scan (nie gespeichert)
$("#runScan").addEventListener("click", async () => {
  const subnet = $("#subnetInput").value.trim();
  const box = $("#scanResults");
  if (!subnet) return;
  box.textContent = "scanne …";
  try {
    const data = await api(`/api/scan?subnet=${encodeURIComponent(subnet)}`);
    if (data.error) { box.textContent = `Fehler: ${data.error}`; return; }
    box.innerHTML = "";
    data.hosts.forEach((h) => {
      const row = document.createElement("div");
      row.className = "scan-row";
      row.innerHTML = `<span>${esc(h.ip ?? "—")}</span><span>${esc(h.hostname ?? h.vendor ?? "")}</span><span>${esc(h.mac ?? "—")}</span>`;
      box.appendChild(row);
    });
    if (!data.hosts.length) box.textContent = "keine Geräte gefunden";
  } catch (e) { box.textContent = `Fehler: ${e.message}`; }
});

// ------------------------------------------------- Kataster

async function loadKataster() {
  await loadTree();
  await loadDeviceTypes();
  const tree = $("#tree");
  tree.innerHTML = "";
  $("#outletDetail").style.display = "none";

  const un = await api("/api/measurements?unassigned=true");
  const box = $("#unassignedBox");
  const list = $("#unassignedList");
  if (un.measurements.length) {
    box.style.display = "block";
    list.innerHTML = "";
    un.measurements.forEach((m) => {
      const row = document.createElement("div");
      row.className = "meas-row";
      row.innerHTML =
        `<span>${fmtTs(m.started_at)}</span>` +
        `<span>${esc(m.kind)} · ${esc(m.speed ?? "")} ${esc(m.switch_name ?? "")} ${esc(m.switch_port ?? "")}</span>`;
      const btn = document.createElement("button");
      btn.className = "btn-inline";
      btn.textContent = "zuordnen…";
      btn.addEventListener("click", () => assignDialog(m.id));
      row.appendChild(btn);
      list.appendChild(row);
    });
  } else {
    box.style.display = "none";
  }

  TREE.floors.forEach((f) => {
    const fl = document.createElement("details");
    fl.className = "tree-floor";
    fl.open = true;
    fl.innerHTML = `<summary>${esc(f.name)}</summary>`;
    f.rooms.forEach((r) => {
      const rm = document.createElement("details");
      rm.className = "tree-room";
      rm.innerHTML = `<summary>${esc(r.name)}</summary>`;
      r.outlets.forEach((o) => {
        const row = document.createElement("div");
        row.className = "tree-outlet";
        const patch = o.patch_panel_name ? ` · ${o.patch_panel_name}/${o.patch_panel_port ?? "?"}` : "";
        row.innerHTML =
          `<span class="outlet-icon">${esc(o.device_icon ?? "·")}</span>` +
          `<span class="outlet-label">${esc(o.label)}<span class="outlet-patch">${esc(patch)}</span></span>` +
          `<span class="outlet-meta">${o.n_measurements} Messung(en)</span>`;
        row.addEventListener("click", () => showOutletDetail(o, r, f));
        rm.appendChild(row);
      });
      if (!r.outlets.length) rm.insertAdjacentHTML("beforeend", '<div class="tree-empty">keine Dosen</div>');
      fl.appendChild(rm);
    });
    tree.appendChild(fl);
  });
  if (!TREE.floors.length) {
    tree.innerHTML = '<div class="tree-empty">Noch keine Etagen angelegt — siehe Verwaltung.</div>';
  }
}

async function showOutletDetail(outlet, room, floor) {
  CURRENT_OUTLET = { outlet, room, floor };
  const panel = $("#outletDetail");
  panel.style.display = "block";
  $("#outletDetailTitle").textContent =
    `DOSE — ${floor.name} / ${room.name} / ${outlet.label}`;
  $("#detailPatchName").value = outlet.patch_panel_name || "";
  $("#detailPatchPort").value = outlet.patch_panel_port || "";
  $("#detailNotes").value = outlet.notes || "";
  $("#detailStatus").textContent = "";

  // Geräte-Icons
  const box = $("#detailDeviceIcons");
  box.innerHTML = "";
  let selectedDevice = outlet.device_type_id;
  DEVICE_TYPES.forEach((dt) => {
    const btn = document.createElement("button");
    btn.className = "device-icon" + (selectedDevice === dt.id ? " active" : "");
    btn.textContent = dt.icon;
    btn.title = dt.name;
    btn.addEventListener("click", () => {
      selectedDevice = selectedDevice === dt.id ? null : dt.id;
      box.querySelectorAll(".device-icon").forEach((b) => b.classList.remove("active"));
      if (selectedDevice === dt.id) btn.classList.add("active");
      panel.dataset.deviceTypeId = selectedDevice ?? "";
    });
    box.appendChild(btn);
  });
  panel.dataset.deviceTypeId = selectedDevice ?? "";

  $("#detailSave").onclick = async () => {
    try {
      await patchJson(`/api/outlets/${outlet.id}`, {
        patch_panel_name: $("#detailPatchName").value.trim() || null,
        patch_panel_port: $("#detailPatchPort").value.trim() || null,
        notes: $("#detailNotes").value.trim() || null,
        device_type_id: panel.dataset.deviceTypeId ? Number(panel.dataset.deviceTypeId) : null,
      });
      $("#detailStatus").textContent = "✓ gespeichert";
      loadTree();
    } catch (e) { $("#detailStatus").textContent = `Fehler: ${e.message}`; }
  };
  $("#detailDelete").onclick = async () => {
    if (!confirm(`Dose "${outlet.label}" löschen?`)) return;
    try {
      await api(`/api/outlets/${outlet.id}`, { method: "DELETE" });
    } catch (e) {
      if (confirm(`${e.message}\n\nWirklich inkl. aller Messungen löschen?`)) {
        await api(`/api/outlets/${outlet.id}?confirm=true`, { method: "DELETE" });
      } else return;
    }
    loadKataster();
  };

  // Historie
  const list = $("#historyList");
  list.textContent = "lade …";
  const data = await api(`/api/measurements?outlet_id=${outlet.id}`);
  list.innerHTML = "";
  let prev = null;
  data.measurements.slice().reverse().forEach((m) => {
    if (prev && m.kind === "autotest" && prev.kind === "autotest") {
      m._diffs = [];
      ["speed", "vlan_ids", "switch_name", "switch_port"].forEach((k) => {
        if (prev[k] !== m[k]) m._diffs.push(`${k}: ${prev[k] ?? "—"} → ${m[k] ?? "—"}`);
      });
    }
    if (m.kind === "autotest") prev = m;
  });
  data.measurements.forEach((m) => {
    const row = document.createElement("div");
    row.className = "meas-row";
    const summary = m.kind === "iperf"
      ? `iperf: ↓${m.iperf_mbps ?? "?"} Mbit/s`
      : `${m.speed ?? "?"} ${m.duplex ?? ""} · VLAN ${m.vlan_ids ?? "—"} · ${m.switch_name ?? "?"} ${m.switch_port ?? ""} · DHCP ${m.dhcp_ok ? "ok" : "✗"}`;
    row.innerHTML = `<span>${fmtTs(m.started_at)}</span><span>${esc(summary)}</span>`;
    if (m._diffs?.length) {
      row.insertAdjacentHTML("beforeend",
        `<span class="diff-hint" title="${esc(m._diffs.join("\n"))}">⚠ geändert</span>`);
    }
    const del = document.createElement("button");
    del.className = "btn-inline";
    del.textContent = "✕";
    del.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm("Messung löschen?")) return;
      await api(`/api/measurements/${m.id}`, { method: "DELETE" });
      showOutletDetail(outlet, room, floor);
    });
    row.appendChild(del);
    list.appendChild(row);
  });
  if (!data.measurements.length) list.textContent = "noch keine Messungen";
}

function assignDialog(measurementId) {
  const options = [];
  TREE.floors.forEach((f) => f.rooms.forEach((r) => r.outlets.forEach((o) =>
    options.push({ id: o.id, label: `${f.name} / ${r.name} / ${o.label}` }))));
  if (!options.length) { alert("Keine Dosen vorhanden."); return; }
  const choice = prompt(
    "Dose wählen (Nummer eingeben):\n" +
    options.map((o, i) => `${i + 1}: ${o.label}`).join("\n"));
  const idx = Number(choice) - 1;
  if (isNaN(idx) || !options[idx]) return;
  patchJson(`/api/measurements/${measurementId}`, { outlet_id: options[idx].id })
    .then(loadKataster);
}

$("#reloadTree").addEventListener("click", loadKataster);

// ------------------------------------------------- Port-Aktionen

function renderPortAktionen() {
  const has = !!LAST_SWITCH;
  $("#paEmpty").style.display = has ? "none" : "block";
  $("#paContent").style.display = has ? "block" : "none";
  if (!has) return;
  $("#paSwitch").textContent = LAST_SWITCH.name || "?";
  $("#paPort").textContent = LAST_SWITCH.portName;
  $("#paIp").textContent = LAST_SWITCH.host;
  $("#descrState").textContent = "—";
  $("#descrEdit").style.display = "none";
  $("#descrStatus").textContent = "";
  $("#vlanState").textContent = "—";
  $("#vlanEdit").style.display = "none";
  $("#vlanStatus").textContent = "";
}

$("#descrPreview").addEventListener("click", async () => {
  $("#descrState").textContent = "löse ifIndex auf …";
  try {
    const outletId = pickOutlet.value ? Number(pickOutlet.value) : null;
    const prev = await postJson("/api/snmp/preview", {
      host: LAST_SWITCH.host, port_name: LAST_SWITCH.portName, outlet_id: outletId,
    });
    if (prev.error) { $("#descrState").textContent = `Fehler: ${prev.error}`; return; }
    PA_IFINDEX = prev.ifindex;
    $("#descrState").innerHTML =
      `Port: <b>${esc(prev.matched_name)}</b> (ifIndex ${esc(prev.ifindex)})<br>` +
      `Aktuell: <b>${esc(prev.current_description ?? "(leer)")}</b>`;
    $("#descrInput").value = prev.proposed_description || "";
    $("#descrEdit").style.display = "block";
  } catch (e) { $("#descrState").textContent = `Fehler: ${e.message}`; }
});

$("#descrWrite").addEventListener("click", async () => {
  if (!PA_IFINDEX) return;
  if (!confirm(`Description "${$("#descrInput").value}" auf ${LAST_SWITCH.host} Port ifIndex ${PA_IFINDEX} schreiben?`)) return;
  $("#descrStatus").textContent = "schreibe …";
  try {
    const res = await postJson("/api/snmp/write", {
      host: LAST_SWITCH.host, ifindex: PA_IFINDEX, description: $("#descrInput").value,
    });
    $("#descrStatus").textContent = res.success ? "✓ geschrieben" : `Fehler: ${res.error}`;
  } catch (e) { $("#descrStatus").textContent = `Fehler: ${e.message}`; }
});

$("#vlanLoad").addEventListener("click", async () => {
  $("#vlanState").textContent = "lade VLAN-Zustand …";
  try {
    if (!PA_IFINDEX) {
      const prev = await postJson("/api/snmp/preview", {
        host: LAST_SWITCH.host, port_name: LAST_SWITCH.portName, outlet_id: null,
      });
      if (prev.error) { $("#vlanState").textContent = `Fehler: ${prev.error}`; return; }
      PA_IFINDEX = prev.ifindex;
    }
    const state = await postJson("/api/snmp/vlan_state", {
      host: LAST_SWITCH.host, ifindex: PA_IFINDEX,
    });
    if (state.error) { $("#vlanState").textContent = `Fehler: ${state.error}`; return; }
    VLAN_CURRENT = state;
    $("#vlanState").innerHTML =
      `PVID (untagged): <b>${esc(state.pvid ?? "?")}</b><br>` +
      `Tagged: <b>${esc(state.tagged_vlans.join(", ") || "keine")}</b>`;
    $("#vlanPvid").value = state.pvid ?? "";
    $("#vlanTagged").value = state.tagged_vlans.join(",");
    $("#vlanEdit").style.display = "block";
    updateVlanDiff();
  } catch (e) { $("#vlanState").textContent = `Fehler: ${e.message}`; }
});

function parseTagged() {
  return $("#vlanTagged").value.split(",").map(s => Number(s.trim())).filter(n => n >= 1 && n <= 4094);
}
function updateVlanDiff() {
  if (!VLAN_CURRENT) return;
  const newPvid = Number($("#vlanPvid").value) || null;
  const newTagged = parseTagged();
  const diffs = [];
  if (newPvid !== VLAN_CURRENT.pvid) diffs.push(`PVID: ${VLAN_CURRENT.pvid} → ${newPvid ?? "?"}`);
  const oldT = VLAN_CURRENT.tagged_vlans.join(","), newT = newTagged.join(",");
  if (oldT !== newT) diffs.push(`Tagged: [${oldT || "—"}] → [${newT || "—"}]`);
  $("#vlanDiff").innerHTML = diffs.length
    ? "Änderungen:<br>" + diffs.map(d => `• ${esc(d)}`).join("<br>")
    : "keine Änderungen";
  return diffs;
}
$("#vlanPvid").addEventListener("input", updateVlanDiff);
$("#vlanTagged").addEventListener("input", updateVlanDiff);

$("#vlanWrite").addEventListener("click", () => {
  const diffs = updateVlanDiff();
  if (!diffs || !diffs.length) { alert("Keine Änderungen."); return; }
  $("#vlanConfirmDiff").innerHTML =
    `Switch: <b>${esc(LAST_SWITCH.host)}</b>, Port: <b>${esc(LAST_SWITCH.portName)}</b><br>` +
    diffs.map(d => `• ${esc(d)}`).join("<br>");
  $("#vlanConfirmCheck").checked = false;
  $("#vlanConfirmGo").disabled = true;
  $("#vlanConfirmDialog").showModal();
});
$("#vlanConfirmCheck").addEventListener("change", (e) => {
  $("#vlanConfirmGo").disabled = !e.target.checked;
});
$("#vlanConfirmCancel").addEventListener("click", () => $("#vlanConfirmDialog").close());
$("#vlanConfirmGo").addEventListener("click", async () => {
  $("#vlanConfirmDialog").close();
  $("#vlanStatus").textContent = "schreibe VLAN-Konfiguration …";
  try {
    const res = await postJson("/api/snmp/vlan_write", {
      host: LAST_SWITCH.host,
      ifindex: PA_IFINDEX,
      pvid: Number($("#vlanPvid").value) || null,
      tagged_vlans: parseTagged(),
    });
    if (res.success) {
      $("#vlanStatus").textContent = "✓ geschrieben — " + res.steps.join(" · ");
      VLAN_CURRENT = null;
    } else {
      $("#vlanStatus").textContent = `Fehler: ${res.error} (${(res.steps || []).join(" · ")})`;
    }
  } catch (e) { $("#vlanStatus").textContent = `Fehler: ${e.message}`; }
});

// ------------------------------------------------- Export-Dialog

$("#openExport").addEventListener("click", async () => {
  const meta = await api("/api/export/columns");
  const box = $("#exportColumns");
  box.innerHTML = "";
  meta.columns.forEach((c) => {
    const label = document.createElement("label");
    label.className = "check-row";
    label.innerHTML = `<input type="checkbox" value="${esc(c.key)}" ${meta.default.includes(c.key) ? "checked" : ""}> ${esc(c.label)}`;
    box.appendChild(label);
  });
  $("#exportDialog").showModal();
});
$("#expCancel").addEventListener("click", () => $("#exportDialog").close());
$("#expRun").addEventListener("click", async () => {
  const columns = [...$$("#exportColumns input:checked")].map((i) => i.value);
  const payload = {
    columns,
    latest_only: $("#expLatestOnly").checked,
    date_from: $("#expFrom").value ? Math.floor(new Date($("#expFrom").value).getTime() / 1000) : null,
    date_to: $("#expTo").value ? Math.floor(new Date($("#expTo").value + "T23:59:59").getTime() / 1000) : null,
  };
  const res = await fetch("/api/export/xlsx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = res.headers.get("content-disposition")?.match(/filename="?([^"]+)"?/)?.[1] || "export.xlsx";
  a.click();
  URL.revokeObjectURL(a.href);
  $("#exportDialog").close();
});

// ------------------------------------------------- Verwaltung

async function loadVerwaltung() {
  await loadTree();
  await loadDeviceTypes();

  const fbox = $("#floorAdmin");
  fbox.innerHTML = "";
  TREE.floors.forEach((f) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${esc(f.name)}</span>`;
    const del = document.createElement("button");
    del.className = "btn-inline"; del.textContent = "✕";
    del.addEventListener("click", () => deleteWithConfirm(`/api/floors/${f.id}`, `Etage "${f.name}"`));
    row.appendChild(del);
    fbox.appendChild(row);
  });

  const sel = $("#adminFloorSelect");
  const prevSel = sel.value;
  sel.innerHTML = '<option value="">Etage wählen…</option>';
  TREE.floors.forEach((f) => {
    const o = document.createElement("option");
    o.value = f.id; o.textContent = f.name;
    sel.appendChild(o);
  });
  if (prevSel) sel.value = prevSel;
  renderRoomAdmin();

  const dbox = $("#deviceAdmin");
  dbox.innerHTML = "";
  DEVICE_TYPES.forEach((dt) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${esc(dt.icon)} ${esc(dt.name)}</span>`;
    const del = document.createElement("button");
    del.className = "btn-inline"; del.textContent = "✕";
    del.addEventListener("click", async () => {
      if (!confirm(`Gerätetyp "${dt.name}" löschen?`)) return;
      await api(`/api/device_types/${dt.id}`, { method: "DELETE" });
      loadVerwaltung();
    });
    row.appendChild(del);
    dbox.appendChild(row);
  });

  const settings = await api("/api/settings");
  $("#setIperf").value = settings.iperf_server || "";
  // Community wird vom Server nie im Klartext geliefert — leer lassen = unverändert
  $("#setCommunity").value = "";
  $("#setCommunity").placeholder = settings.snmp_community_set === "1"
    ? "gespeichert — leer lassen = unverändert"
    : "z.B. private";
  $("#setTemplate").value = settings.snmp_descr_template || "";
}

function renderRoomAdmin() {
  const floor = TREE.floors.find((f) => f.id == $("#adminFloorSelect").value);
  const rbox = $("#roomAdmin");
  rbox.innerHTML = "";
  (floor?.rooms || []).forEach((r) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${esc(r.name)}</span>`;
    const del = document.createElement("button");
    del.className = "btn-inline"; del.textContent = "✕";
    del.addEventListener("click", () => deleteWithConfirm(`/api/rooms/${r.id}`, `Raum "${r.name}"`));
    row.appendChild(del);
    rbox.appendChild(row);
  });
}
$("#adminFloorSelect").addEventListener("change", renderRoomAdmin);

async function deleteWithConfirm(url, label) {
  if (!confirm(`${label} löschen?`)) return;
  try {
    await api(url, { method: "DELETE" });
  } catch (e) {
    if (confirm(`${e.message}\n\nWirklich ALLES löschen (inkl. Messungen)?`)) {
      await api(`${url}?confirm=true`, { method: "DELETE" });
    } else return;
  }
  loadVerwaltung();
}

$("#addFloor").addEventListener("click", async () => {
  const name = $("#newFloorName").value.trim();
  if (!name) return;
  try {
    await postJson("/api/floors", { name });
    $("#newFloorName").value = "";
    loadVerwaltung();
  } catch (e) { alert(e.message); }
});

$("#addRoom").addEventListener("click", async () => {
  const name = $("#newRoomName").value.trim();
  const floorId = $("#adminFloorSelect").value;
  if (!name || !floorId) { alert("Etage wählen und Namen eingeben"); return; }
  try {
    await postJson("/api/rooms", { name, floor_id: Number(floorId) });
    $("#newRoomName").value = "";
    loadVerwaltung();
  } catch (e) { alert(e.message); }
});

$("#addDevice").addEventListener("click", async () => {
  const name = $("#newDeviceName").value.trim();
  const icon = $("#newDeviceIcon").value.trim() || "❓";
  if (!name) return;
  try {
    await postJson("/api/device_types", { name, icon });
    $("#newDeviceName").value = ""; $("#newDeviceIcon").value = "";
    loadVerwaltung();
  } catch (e) { alert(e.message); }
});

$("#saveSettings").addEventListener("click", async () => {
  await api("/api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      iperf_server: $("#setIperf").value.trim(),
      snmp_community: $("#setCommunity").value,
      snmp_descr_template: $("#setTemplate").value.trim() || "{raum}-{dose} {geraet}",
    }),
  });
  $("#settingsStatus").textContent = "✓ gespeichert";
  setTimeout(() => ($("#settingsStatus").textContent = ""), 2000);
});

$("#restoreFile").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  if (!confirm(`Datenbank durch "${file.name}" ERSETZEN?\nAlle aktuellen Daten werden überschrieben (die alte DB wird vorher automatisch gesichert).`)) {
    ev.target.value = ""; return;
  }
  if (!confirm("Wirklich sicher? Dieser Schritt kann nur über die automatische Sicherung rückgängig gemacht werden.")) {
    ev.target.value = ""; return;
  }
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/db/restore", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    $("#dbStatus").textContent = `✓ wiederhergestellt (alte DB: ${data.backup_of_previous})`;
    loadTree().then(fillPicker);
  } catch (e) {
    $("#dbStatus").textContent = `Fehler: ${e.message}`;
  }
  ev.target.value = "";
});

// ------------------------------------------------- Init

(async function init() {
  await Promise.all([loadIfaces(), loadTree(), loadDeviceTypes()]);
  fillPicker();
})();
