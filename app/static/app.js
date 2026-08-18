const ifaceSelect = document.getElementById("iface");
const runBtn = document.getElementById("runAutotest");
const runStatus = document.getElementById("runStatus");

function setLed(cardId, state) {
  const led = document.querySelector(`#${cardId} [data-led]`);
  led.classList.remove("ok", "warn", "bad");
  if (state) led.classList.add(state);
}

function setBody(cardId, rows) {
  const dl = document.querySelector(`#${cardId} [data-body]`);
  const dds = dl.querySelectorAll("dd");
  rows.forEach((val, i) => {
    if (dds[i]) dds[i].textContent = val ?? "—";
  });
}

// Interface-Liste kommt vom Browser nicht direkt (kein Netzwerk-API im Browser),
// daher pflegt der Nutzer die gängigen Interfacenamen hier / oder erweitert die
// Liste serverseitig. Fallback: freie Eingabe per <select> mit editierbaren Werten.
const COMMON_IFACES = ["eth0", "enp0s25", "enp1s0", "eno1"];

function loadIfaces() {
  ifaceSelect.innerHTML = "";
  COMMON_IFACES.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    ifaceSelect.appendChild(opt);
  });
}
loadIfaces();
document.getElementById("refreshIfaces").addEventListener("click", loadIfaces);

async function runAutotest() {
  const iface = ifaceSelect.value;
  runBtn.disabled = true;
  runStatus.textContent = `teste ${iface} … (Sniff läuft ~6s)`;

  try {
    const res = await fetch(`/api/autotest?interface=${encodeURIComponent(iface)}`);
    const data = await res.json();

    // LINK
    const link = data.link;
    setBody("card-link", [
      link.error ? `Fehler: ${link.error}` : (link.link_detected ? "verbunden" : "kein Link"),
      link.speed,
      link.duplex,
    ]);
    setLed("card-link", link.error ? "bad" : (link.link_detected ? "ok" : "warn"));

    // LLDP
    const lldp = data.lldp;
    const neighbor = lldp.neighbors && lldp.neighbors[0];
    setBody("card-lldp", [
      neighbor ? neighbor.switch_name : (lldp.error ? `Fehler: ${lldp.error}` : "kein LLDP-Nachbar"),
      neighbor ? neighbor.port_id : "—",
      neighbor ? neighbor.switch_mgmt_ip : "—",
    ]);
    setLed("card-lldp", neighbor ? "ok" : "warn");

    // VLAN / EAPOL / STP
    const sniff = data.sniff;
    setBody("card-vlan", [
      sniff.error ? `Fehler: ${sniff.error}` : (sniff.vlan_ids_seen.length ? sniff.vlan_ids_seen.join(", ") : "keine tagged VLANs gesehen"),
      sniff.eapol_seen ? "ja — Port verlangt 802.1X" : "nein",
      sniff.stp_seen ? "aktiv (BPDU gesehen)" : "keine BPDU gesehen",
    ]);
    setLed("card-vlan", sniff.error ? "bad" : "ok");

    // DHCP
    const dhcp = data.dhcp;
    setBody("card-dhcp", [
      dhcp.offered_ip || (dhcp.error ? `Fehler: ${dhcp.error}` : "keine Antwort"),
      dhcp.router,
      dhcp.dns_servers,
      dhcp.subnet_mask,
    ]);
    setLed("card-dhcp", dhcp.server_found ? "ok" : "bad");

    // PING
    const ping = data.ping_gateway;
    if (ping) {
      setBody("card-ping", [
        ping.reachable ? "ja" : "nein",
        ping.avg_ms ? `${ping.avg_ms} ms` : "—",
      ]);
      setLed("card-ping", ping.reachable ? "ok" : "bad");
    } else {
      setBody("card-ping", ["kein Gateway aus DHCP bekannt", "—"]);
      setLed("card-ping", "warn");
    }

    runStatus.textContent = `fertig — ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    runStatus.textContent = `Fehler: ${e}`;
  } finally {
    runBtn.disabled = false;
  }
}

runBtn.addEventListener("click", runAutotest);

// Netz-Scan
document.getElementById("runScan").addEventListener("click", async () => {
  const subnet = document.getElementById("subnetInput").value.trim();
  const box = document.getElementById("scanResults");
  if (!subnet) return;
  box.textContent = "scanne …";
  try {
    const res = await fetch(`/api/scan?subnet=${encodeURIComponent(subnet)}`);
    const data = await res.json();
    if (data.error) {
      box.textContent = `Fehler: ${data.error}`;
      return;
    }
    box.innerHTML = "";
    data.hosts.forEach((h) => {
      const row = document.createElement("div");
      row.className = "scan-row";
      row.innerHTML = `<span>${h.ip ?? "—"}</span><span>${h.hostname ?? h.vendor ?? ""}</span><span>${h.mac ?? "—"}</span>`;
      box.appendChild(row);
    });
    if (!data.hosts.length) box.textContent = "keine Geräte gefunden";
  } catch (e) {
    box.textContent = `Fehler: ${e}`;
  }
});
