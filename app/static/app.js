// ===================================================================
// netdiag v2 Frontend — Vanilla JS, kein Build-Step
// ===================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

function fmtTs(unix) {
  return new Date(unix * 1000).toLocaleString("de-DE", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// ---------------------------------------------------------------- Tabs

$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "kataster") loadKataster();
    if (btn.dataset.tab === "verwaltung") loadVerwaltung();
  });
});

// ------------------------------------------------- Globale Stammdaten

let TREE = { floors: [] };
let DEVICE_TYPES = [];
let LAST_AUTOTEST = null; // für SNMP-Button

async function loadTree() {
  TREE = await api("/api/tree");
}
async function loadDeviceTypes() {
  DEVICE_TYPES = (await api("/api/device_types")).device_types;
}

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

// ------------------------------------------- Messen: Dosen-Picker (sticky)

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
  if (prevFloor && [...pickFloor.options].some((o) => o.value === prevFloor)) {
    pickFloor.value = prevFloor;
  }
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
  if (prevRoom && [...pickRoom.options].some((o) => o.value === prevRoom)) {
    pickRoom.value = prevRoom;
  }
  fillOutlets();
}

function fillOutlets() {
  const floor = TREE.floors.find((f) => f.id == pickFloor.value);
  const room = floor?.rooms.find((r) => r.id == pickRoom.value);
  pickOutlet.innerHTML = '<option value="">Dose…</option>';
  pickOutlet.disabled = !room;
  $("#quickAddOutlet").disabled = !room;
  (room?.outlets || []).forEach((o) => {
    const opt = document.createElement("option");
    opt.value = o.id;
    opt.textContent = `${o.label}${o.device_icon ? " " + o.device_icon : ""}`;
    pickOutlet.appendChild(opt);
  });
  updateDeviceRow();
}

function selectedOutlet() {
  const floor = TREE.floors.find((f) => f.id == pickFloor.value);
  const room = floor?.rooms.find((r) => r.id == pickRoom.value);
  return room?.outlets.find((o) => o.id == pickOutlet.value) || null;
}

function updateDeviceRow() {
  const outlet = selectedOutlet();
  const row = $("#deviceRow");
  if (!outlet) { row.style.display = "none"; return; }
  row.style.display = "flex";
  const box = $("#deviceIcons");
  box.innerHTML = "";
  DEVICE_TYPES.forEach((dt) => {
    const btn = document.createElement("button");
    btn.className = "device-icon" + (outlet.device_type_id === dt.id ? " active" : "");
    btn.textContent = dt.icon;
    btn.title = dt.name;
    btn.addEventListener("click", async () => {
      const newVal = outlet.device_type_id === dt.id ? null : dt.id;
      await api(`/api/outlets/${outlet.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_type_id: newVal }),
      });
      await loadTree();
      fillPicker();
    });
    box.appendChild(btn);
  });
}

pickFloor.addEventListener("change", fillRooms);
pickRoom.addEventListener("change", fillOutlets);
pickOutlet.addEventListener("change", updateDeviceRow);

$("#quickAddOutlet").addEventListener("click", async () => {
  const label = prompt("Bezeichnung der neuen Dose (z.B. D03):");
  if (!label) return;
  try {
    const created = await api("/api/outlets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_id: Number(pickRoom.value), label }),
    });
    await loadTree();
    fillPicker();
    pickOutlet.value = created.id;
    updateDeviceRow();
  } catch (e) { alert(e.message); }
});

// ------------------------------------------------- Messen: Ergebnis-UI

function setLed(cardId, state) {
  const led = document.querySelector(`#${cardId} [data-led]`);
  led.classList.remove("ok", "warn", "bad");
  if (state) led.classList.add(state);
}
function setBody(cardId, rows) {
  const dds = document.querySelectorAll(`#${cardId} [data-body] dd`);
  rows.forEach((val, i) => { if (dds[i]) dds[i].textContent = val ?? "—"; });
}

async function runAutotest() {
  const iface = $("#iface").value;
  const outletId = pickOutlet.value || null;
  const btn = $("#runAutotest");
  btn.disabled = true;
  $("#runStatus").textContent = `teste ${iface} … (~10s)`;
  $("#snmpBtn").style.display = "none";

  try {
    let url = `/api/autotest?interface=${encodeURIComponent(iface)}`;
    if (outletId) url += `&outlet_id=${outletId}`;
    const data = await api(url);
    LAST_AUTOTEST = data;

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
    if (swIp && swPort && outletId) $("#snmpBtn").style.display = "inline-block";

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

    const saved = outletId ? " · gespeichert ✓" : " · gespeichert (nicht zugeordnet)";
    $("#runStatus").textContent = `fertig ${new Date().toLocaleTimeString()}${saved}`;
  } catch (e) {
    $("#runStatus").textContent = `Fehler: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}
$("#runAutotest").addEventListener("click", runAutotest);

async function runIperf() {
  const outletId = pickOutlet.value || null;
  const btn = $("#runIperf");
  btn.disabled = true;
  $("#runStatus").textContent = "iperf läuft … (~25s beide Richtungen)";
  try {
    let url = `/api/iperf`;
    if (outletId) url += `?outlet_id=${outletId}`;
    const data = await api(url);
    if (data.error) {
      setBody("card-iperf", [`Fehler: ${data.error}`, "—", "—"]);
      setLed("card-iperf", "bad");
    } else {
      setBody("card-iperf", [
        data.mbps_down != null ? `${data.mbps_down} Mbit/s` : "—",
        data.mbps_up != null ? `${data.mbps_up} Mbit/s` : "—",
        data.retransmits ?? "—",
      ]);
      setLed("card-iperf", "ok");
    }
    $("#runStatus").textContent = `iperf fertig ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $("#runStatus").textContent = `Fehler: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}
$("#runIperf").addEventListener("click", runIperf);

// Netz-Scan
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
      row.innerHTML = `<span>${h.ip ?? "—"}</span><span>${h.hostname ?? h.vendor ?? ""}</span><span>${h.mac ?? "—"}</span>`;
      box.appendChild(row);
    });
    if (!data.hosts.length) box.textContent = "keine Geräte gefunden";
  } catch (e) { box.textContent = `Fehler: ${e.message}`; }
});

// ------------------------------------------------- SNMP-Dialog

$("#snmpBtn").addEventListener("click", async () => {
  const neighbor = LAST_AUTOTEST?.lldp?.neighbors?.[0];
  const cdp = LAST_AUTOTEST?.sniff?.cdp;
  const host = neighbor?.switch_mgmt_ip || cdp?.mgmt_ip;
  const portName = neighbor?.port_id || cdp?.port_id;
  const outletId = pickOutlet.value || null;
  const dlg = $("#snmpDialog");
  $("#snmpInfo").textContent = "löse ifIndex auf …";
  $("#snmpConfirm").disabled = true;
  $("#snmpStatus").textContent = "";
  dlg.showModal();
  try {
    const prev = await api("/api/snmp/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, port_name: portName, outlet_id: outletId ? Number(outletId) : null }),
    });
    if (prev.error) {
      $("#snmpInfo").textContent = `Fehler: ${prev.error}`;
      return;
    }
    $("#snmpInfo").innerHTML =
      `Switch: <b>${host}</b><br>Port: <b>${prev.matched_name}</b> (ifIndex ${prev.ifindex})<br>` +
      `Aktuelle Description: <b>${prev.current_description ?? "(leer)"}</b>`;
    $("#snmpDescr").value = prev.proposed_description || "";
    $("#snmpConfirm").disabled = false;
    $("#snmpConfirm").onclick = async () => {
      $("#snmpConfirm").disabled = true;
      $("#snmpStatus").textContent = "schreibe …";
      try {
        const res = await api("/api/snmp/write", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ host, ifindex: prev.ifindex, description: $("#snmpDescr").value }),
        });
        $("#snmpStatus").textContent = res.success ? "✓ geschrieben" : `Fehler: ${res.error}`;
        if (res.success) setTimeout(() => dlg.close(), 1200);
      } catch (e) {
        $("#snmpStatus").textContent = `Fehler: ${e.message}`;
      } finally {
        $("#snmpConfirm").disabled = false;
      }
    };
  } catch (e) {
    $("#snmpInfo").textContent = `Fehler: ${e.message}`;
  }
});
$("#snmpCancel").addEventListener("click", () => $("#snmpDialog").close());

// ------------------------------------------------- Kataster

async function loadKataster() {
  await loadTree();
  const tree = $("#tree");
  tree.innerHTML = "";
  $("#historyPanel").style.display = "none";

  // ungebundene Messungen
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
        `<span>${m.kind} · ${m.speed ?? ""} ${m.switch_name ?? ""} ${m.switch_port ?? ""}</span>`;
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
    fl.innerHTML = `<summary>${f.name}</summary>`;
    f.rooms.forEach((r) => {
      const rm = document.createElement("details");
      rm.className = "tree-room";
      rm.innerHTML = `<summary>${r.name}</summary>`;
      r.outlets.forEach((o) => {
        const row = document.createElement("div");
        row.className = "tree-outlet";
        row.innerHTML =
          `<span class="outlet-icon">${o.device_icon ?? "·"}</span>` +
          `<span class="outlet-label">${o.label}</span>` +
          `<span class="outlet-meta">${o.n_measurements} Messung(en)</span>`;
        row.addEventListener("click", () => showHistory(o, r, f));
        rm.appendChild(row);
      });
      if (!r.outlets.length) {
        rm.insertAdjacentHTML("beforeend", '<div class="tree-empty">keine Dosen</div>');
      }
      fl.appendChild(rm);
    });
    tree.appendChild(fl);
  });
  if (!TREE.floors.length) {
    tree.innerHTML = '<div class="tree-empty">Noch keine Etagen angelegt — siehe Verwaltung.</div>';
  }
}

async function showHistory(outlet, room, floor) {
  const panel = $("#historyPanel");
  panel.style.display = "block";
  $("#historyTitle").textContent = `HISTORIE — ${floor.name} / ${room.name} / ${outlet.label}`;
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
    row.innerHTML = `<span>${fmtTs(m.started_at)}</span><span>${summary}</span>`;
    if (m._diffs?.length) {
      row.insertAdjacentHTML("beforeend",
        `<span class="diff-hint" title="${m._diffs.join("\n")}">⚠ geändert</span>`);
    }
    const del = document.createElement("button");
    del.className = "btn-inline";
    del.textContent = "✕";
    del.title = "Messung löschen";
    del.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm("Messung löschen?")) return;
      await api(`/api/measurements/${m.id}`, { method: "DELETE" });
      showHistory(outlet, room, floor);
    });
    row.appendChild(del);
    list.appendChild(row);
  });
  if (!data.measurements.length) list.textContent = "noch keine Messungen";
}

function assignDialog(measurementId) {
  // simpel: prompt-Kette über Dropdown wäre schöner, aber prompt reicht v1-mäßig nicht —
  // wir bauen ein kleines dynamisches Auswahlmenü:
  const options = [];
  TREE.floors.forEach((f) => f.rooms.forEach((r) => r.outlets.forEach((o) =>
    options.push({ id: o.id, label: `${f.name} / ${r.name} / ${o.label}` }))));
  if (!options.length) { alert("Keine Dosen vorhanden — erst im Kataster/Verwaltung anlegen."); return; }
  const choice = prompt(
    "Dose wählen (Nummer eingeben):\n" +
    options.map((o, i) => `${i + 1}: ${o.label}`).join("\n"));
  const idx = Number(choice) - 1;
  if (isNaN(idx) || !options[idx]) return;
  api(`/api/measurements/${measurementId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outlet_id: options[idx].id }),
  }).then(loadKataster);
}

$("#reloadTree").addEventListener("click", loadKataster);

// ------------------------------------------------- Export-Dialog

$("#openExport").addEventListener("click", async () => {
  const meta = await api("/api/export/columns");
  const box = $("#exportColumns");
  box.innerHTML = "";
  meta.columns.forEach((c) => {
    const label = document.createElement("label");
    label.className = "check-row";
    label.innerHTML = `<input type="checkbox" value="${c.key}" ${meta.default.includes(c.key) ? "checked" : ""}> ${c.label}`;
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

  // Etagen
  const fbox = $("#floorAdmin");
  fbox.innerHTML = "";
  TREE.floors.forEach((f) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${f.name}</span>`;
    const del = document.createElement("button");
    del.className = "btn-inline"; del.textContent = "✕";
    del.addEventListener("click", () => deleteWithConfirm(`/api/floors/${f.id}`, `Etage "${f.name}"`));
    row.appendChild(del);
    fbox.appendChild(row);
  });

  // Etagen-Select für Räume
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

  // Gerätetypen
  const dbox = $("#deviceAdmin");
  dbox.innerHTML = "";
  DEVICE_TYPES.forEach((dt) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${dt.icon} ${dt.name}</span>`;
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

  // Settings
  const settings = await api("/api/settings");
  $("#setIperf").value = settings.iperf_server || "";
  $("#setCommunity").value = settings.snmp_community || "";
  $("#setTemplate").value = settings.snmp_descr_template || "";
}

function renderRoomAdmin() {
  const floor = TREE.floors.find((f) => f.id == $("#adminFloorSelect").value);
  const rbox = $("#roomAdmin");
  rbox.innerHTML = "";
  (floor?.rooms || []).forEach((r) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = `<span>${r.name}</span>`;
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
    // 409: enthält Messungen
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
    await api("/api/floors", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $("#newFloorName").value = "";
    loadVerwaltung();
  } catch (e) { alert(e.message); }
});

$("#addRoom").addEventListener("click", async () => {
  const name = $("#newRoomName").value.trim();
  const floorId = $("#adminFloorSelect").value;
  if (!name || !floorId) { alert("Etage wählen und Namen eingeben"); return; }
  try {
    await api("/api/rooms", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, floor_id: Number(floorId) }),
    });
    $("#newRoomName").value = "";
    loadVerwaltung();
  } catch (e) { alert(e.message); }
});

$("#addDevice").addEventListener("click", async () => {
  const name = $("#newDeviceName").value.trim();
  const icon = $("#newDeviceIcon").value.trim() || "❓";
  if (!name) return;
  try {
    await api("/api/device_types", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, icon }),
    });
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

// DB restore
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
