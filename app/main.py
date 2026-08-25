import os
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Body, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from app.db import get_conn, init_db, save_measurement, get_setting, DB_PATH, SCHEMA_VERSION
from app.collectors.link import get_link_info
from app.collectors.lldp import get_lldp_neighbors
from app.collectors.sniff import sniff_port
from app.collectors.dhcp import discover_dhcp
from app.collectors.reach import ping_test, scan_subnet
from app.collectors.iperf import run_iperf
from app.collectors.snmp import (resolve_ifindex, get_current_alias, set_port_description,
    get_vlan_state, set_vlan_state, get_port_errors)
from app.export_xlsx import export_xlsx, COLUMNS, DEFAULT_COLUMNS
from app import sync as sync_mod

APP_VERSION = "3.1.0"

app = FastAPI(title="netdiag", version=APP_VERSION,
              description="Lokaler Netzwerk-Port-Tester + Kabelkataster")
init_db()

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION, "schema_version": SCHEMA_VERSION}


# ---------------------------------------------------------------- Messen

@app.get("/api/interfaces")
def api_interfaces():
    """Physische Ethernet-Interfaces des Geräts (kein lo, kein virtuelles)."""
    ifaces = []
    net = Path("/sys/class/net")
    if net.exists():
        for p in sorted(net.iterdir()):
            if p.name == "lo":
                continue
            if (p / "wireless").exists():  # WLAN raus — Messen nur über LAN
                continue
            if (p / "device").exists():  # nur echte Hardware
                ifaces.append(p.name)
    return {"interfaces": ifaces or ["eth0"]}


@app.get("/api/autotest")
def autotest(
    interface: str = Query("eth0"),
    sniff_seconds: int = Query(6, ge=2, le=30),
):
    # Collectors parallel: sniff (~6s) und DHCP-Discover (bis 20s) dominieren
    # die Laufzeit — nebenläufig statt seriell halbiert den Autotest.
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_link = pool.submit(get_link_info, interface)
        f_lldp = pool.submit(get_lldp_neighbors, interface)
        f_sniff = pool.submit(sniff_port, interface, sniff_seconds)
        f_dhcp = pool.submit(discover_dhcp, interface)
        link = f_link.result()
        lldp = f_lldp.result()
        sniff = f_sniff.result()
        dhcp = f_dhcp.result()

    ping_gateway = None
    if dhcp.get("router"):
        ping_gateway = ping_test(dhcp["router"], count=3)

    result = {
        "interface": interface,
        "link": link,
        "lldp": lldp,
        "sniff": sniff,
        "dhcp": dhcp,
        "ping_gateway": ping_gateway,
    }
    # v3: kein Auto-Save — Speichern erfolgt explizit via POST /api/measurements
    return result


@app.get("/api/iperf")
def api_iperf(duration: int = Query(10, ge=3, le=60)):
    server = get_setting("iperf_server")
    return run_iperf(server, duration=duration)


@app.get("/api/ping")
def api_ping(target: str = Query(...), count: int = Query(4, ge=1, le=20)):
    return ping_test(target, count=count)


@app.get("/api/scan")
def api_scan(subnet: str = Query(...)):
    return scan_subnet(subnet)


# ------------------------------------------------------------ Stammdaten

@app.get("/api/tree")
def api_tree():
    """Kompletter Baum Etagen→Räume→Dosen inkl. Gerätetyp und Messungszahl."""
    conn = get_conn()
    floors = [dict(r) for r in conn.execute(
        "SELECT * FROM floors ORDER BY sort_order, name").fetchall()]
    for f in floors:
        f["rooms"] = [dict(r) for r in conn.execute(
            "SELECT * FROM rooms WHERE floor_id = ? ORDER BY name", (f["id"],)).fetchall()]
        for room in f["rooms"]:
            room["outlets"] = [dict(r) for r in conn.execute(
                """SELECT o.*, dt.name AS device_name, dt.icon AS device_icon,
                          (SELECT COUNT(*) FROM measurements m
                           WHERE m.outlet_id = o.id) AS n_measurements
                   FROM outlets o LEFT JOIN device_types dt ON dt.id = o.device_type_id
                   WHERE o.room_id = ? ORDER BY o.label""", (room["id"],)).fetchall()]
    conn.close()
    return {"floors": floors}


@app.post("/api/floors")
def create_floor(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name fehlt")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO floors(name, sort_order) VALUES (?, ?)",
            (name, payload.get("sort_order", 0)))
        conn.commit()
        return {"id": cur.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Etage '{name}' existiert bereits")
    finally:
        conn.close()


@app.delete("/api/floors/{floor_id}")
def delete_floor(floor_id: int, confirm: bool = Query(False)):
    conn = get_conn()
    n = conn.execute(
        """SELECT COUNT(*) FROM measurements m
           JOIN outlets o ON o.id = m.outlet_id
           JOIN rooms r ON r.id = o.room_id WHERE r.floor_id = ?""",
        (floor_id,)).fetchone()[0]
    if n > 0 and not confirm:
        conn.close()
        raise HTTPException(409, f"Etage enthält {n} Messungen — mit confirm=true löschen")
    conn.execute("DELETE FROM floors WHERE id = ?", (floor_id,))
    conn.commit()
    conn.close()
    return {"deleted": floor_id}


@app.post("/api/rooms")
def create_room(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    floor_id = payload.get("floor_id")
    if not name or not floor_id:
        raise HTTPException(400, "Name oder Etage fehlt")
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO rooms(floor_id, name) VALUES (?, ?)", (floor_id, name))
        conn.commit()
        return {"id": cur.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Raum '{name}' existiert in dieser Etage bereits")
    finally:
        conn.close()


@app.delete("/api/rooms/{room_id}")
def delete_room(room_id: int, confirm: bool = Query(False)):
    conn = get_conn()
    n = conn.execute(
        """SELECT COUNT(*) FROM measurements m
           JOIN outlets o ON o.id = m.outlet_id WHERE o.room_id = ?""",
        (room_id,)).fetchone()[0]
    if n > 0 and not confirm:
        conn.close()
        raise HTTPException(409, f"Raum enthält {n} Messungen — mit confirm=true löschen")
    conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    conn.commit()
    conn.close()
    return {"deleted": room_id}


@app.post("/api/outlets")
def create_outlet(payload: dict = Body(...)):
    label = (payload.get("label") or "").strip()
    room_id = payload.get("room_id")
    if not label or not room_id:
        raise HTTPException(400, "Label oder Raum fehlt")
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO outlets(room_id, label, device_type_id, notes,
               patch_panel_name, patch_panel_port) VALUES (?, ?, ?, ?, ?, ?)""",
            (room_id, label, payload.get("device_type_id"), payload.get("notes"),
             payload.get("patch_panel_name"), payload.get("patch_panel_port")))
        conn.commit()
        return {"id": cur.lastrowid, "label": label}
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Dose '{label}' existiert in diesem Raum bereits")
    finally:
        conn.close()


@app.patch("/api/outlets/{outlet_id}")
def update_outlet(outlet_id: int, payload: dict = Body(...)):
    conn = get_conn()
    fields, params = [], []
    for key in ("label", "device_type_id", "notes", "patch_panel_name", "patch_panel_port"):
        if key in payload:
            fields.append(f"{key} = ?")
            params.append(payload[key])
    if fields:
        params.append(outlet_id)
        conn.execute(f"UPDATE outlets SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return {"updated": outlet_id}


@app.delete("/api/outlets/{outlet_id}")
def delete_outlet(outlet_id: int, confirm: bool = Query(False)):
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM measurements WHERE outlet_id = ?",
                     (outlet_id,)).fetchone()[0]
    if n > 0 and not confirm:
        conn.close()
        raise HTTPException(409, f"Dose hat {n} Messungen — mit confirm=true löschen")
    conn.execute("DELETE FROM outlets WHERE id = ?", (outlet_id,))
    conn.commit()
    conn.close()
    return {"deleted": outlet_id}


@app.get("/api/device_types")
def list_device_types():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM device_types ORDER BY id").fetchall()]
    conn.close()
    return {"device_types": rows}


@app.post("/api/device_types")
def create_device_type(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name fehlt")
    conn = get_conn()
    try:
        cur = conn.execute("INSERT INTO device_types(name, icon) VALUES (?, ?)",
                           (name, payload.get("icon") or "❓"))
        conn.commit()
        return {"id": cur.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Gerätetyp existiert bereits")
    finally:
        conn.close()


@app.delete("/api/device_types/{dt_id}")
def delete_device_type(dt_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM device_types WHERE id = ?", (dt_id,))
    conn.commit()
    conn.close()
    return {"deleted": dt_id}


# ------------------------------------------------------------ Messungen

@app.post("/api/measurements")
def save_measurement_endpoint(background_tasks: BackgroundTasks, payload: dict = Body(...)):
    """v3: Messung explizit speichern (Ein-Klick mit sticky Dose)."""
    result = payload.get("result")
    if not result:
        raise HTTPException(400, "result fehlt")
    kind = payload.get("kind", "autotest")
    outlet_id = payload.get("outlet_id")
    mid = save_measurement(result, outlet_id, kind=kind)
    # Übertragung läuft NACH der Antwort und darf scheitern: die Messung liegt
    # lokal, der nächste Sync holt sie nach.
    background_tasks.add_task(sync_mod.push_quietly)
    return {"measurement_id": mid, "outlet_id": outlet_id}


@app.get("/api/measurements")
def list_measurements(outlet_id: int | None = Query(None), unassigned: bool = Query(False)):
    conn = get_conn()
    if unassigned:
        rows = conn.execute(
            """SELECT id, started_at, kind, speed, duplex, vlan_ids, switch_name,
                      switch_port, dhcp_ok, iperf_mbps
               FROM measurements WHERE outlet_id IS NULL
               ORDER BY started_at DESC LIMIT 200""").fetchall()
    elif outlet_id:
        rows = conn.execute(
            """SELECT id, started_at, kind, speed, duplex, vlan_ids, switch_name,
                      switch_port, dhcp_ok, iperf_mbps
               FROM measurements WHERE outlet_id = ?
               ORDER BY started_at DESC""", (outlet_id,)).fetchall()
    else:
        rows = []
    conn.close()
    return {"measurements": [dict(r) for r in rows]}


@app.get("/api/measurements/{mid}")
def measurement_detail(mid: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (mid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Messung nicht gefunden")
    return dict(row)


@app.patch("/api/measurements/{mid}")
def assign_measurement(mid: int, payload: dict = Body(...)):
    conn = get_conn()
    conn.execute("UPDATE measurements SET outlet_id = ? WHERE id = ?",
                 (payload.get("outlet_id"), mid))
    conn.commit()
    conn.close()
    return {"updated": mid}


@app.delete("/api/measurements/{mid}")
def delete_measurement(mid: int):
    conn = get_conn()
    conn.execute("DELETE FROM measurements WHERE id = ?", (mid,))
    conn.commit()
    conn.close()
    return {"deleted": mid}


# ------------------------------------------------------------ Settings

SECRET_SETTINGS = {"snmp_community", "monitor_token"}


@app.get("/api/settings")
def list_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    out = {}
    for r in rows:
        if r["key"] in SECRET_SETTINGS:
            # Nie im Klartext ausliefern — nur ob gesetzt
            out[r["key"]] = ""
            out[r["key"] + "_set"] = "1" if r["value"] else "0"
        else:
            out[r["key"]] = r["value"]
    return out


@app.put("/api/settings")
def update_settings(payload: dict = Body(...)):
    conn = get_conn()
    for key, value in payload.items():
        if key in SECRET_SETTINGS and not str(value):
            continue  # leeres Feld = unverändert lassen (Wert wird nie zurückgeliefert)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)))
    conn.commit()
    conn.close()
    return {"updated": list(payload.keys())}


# --------------------------------------------------- NetzwerkMonitor-Sync

@app.get("/api/sync/status")
def sync_status():
    return sync_mod.status()


@app.post("/api/sync/test")
def sync_test():
    try:
        return sync_mod.test_connection()
    except sync_mod.SyncNotConfigured as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sync/now")
def sync_now():
    try:
        return sync_mod.push()
    except sync_mod.SyncNotConfigured as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/sync/export")
def sync_export(include_synced: bool = Query(True)):
    """Derselbe Payload als Datei — für den Erstimport oder wenn die Zentrale
    vom Messort aus nicht erreichbar ist."""
    return sync_mod.build_payload(include_synced=include_synced)


# ------------------------------------------------------------ SNMP

@app.post("/api/snmp/preview")
def snmp_preview(payload: dict = Body(...)):
    """Schritt 1: ifIndex auflösen + Description-Vorschlag berechnen, nichts schreiben."""
    host = payload.get("host")
    port_name = payload.get("port_name")
    outlet_id = payload.get("outlet_id")
    if not host or not port_name:
        raise HTTPException(400, "host und port_name erforderlich")

    community = get_setting("snmp_community") or ""
    resolved = resolve_ifindex(host, community, port_name)

    description = None
    if outlet_id:
        conn = get_conn()
        row = conn.execute(
            """SELECT o.label, r.name AS room, COALESCE(dt.name, '') AS device
               FROM outlets o JOIN rooms r ON r.id = o.room_id
               LEFT JOIN device_types dt ON dt.id = o.device_type_id
               WHERE o.id = ?""", (outlet_id,)).fetchone()
        conn.close()
        if row:
            template = get_setting("snmp_descr_template") or "{raum}-{dose} {geraet}"
            description = template.format(
                raum=row["room"], dose=row["label"], geraet=row["device"]).strip()

    current = None
    if resolved.get("ifindex"):
        current = get_current_alias(host, community, resolved["ifindex"])

    return {**resolved, "proposed_description": description, "current_description": current}


@app.post("/api/snmp/write")
def snmp_write(payload: dict = Body(...)):
    """Schritt 2: nach Bestätigung tatsächlich schreiben."""
    host = payload.get("host")
    ifindex = payload.get("ifindex")
    description = payload.get("description")
    if not host or not ifindex or description is None:
        raise HTTPException(400, "host, ifindex und description erforderlich")
    community = get_setting("snmp_community") or ""
    return set_port_description(host, community, int(ifindex), description)


@app.post("/api/snmp/port_errors")
def snmp_port_errors(payload: dict = Body(...)):
    """Ethernet-Fehlerzähler eines Ports lesen (CRC/FCS, Alignment, Late
    Collisions etc.) — Hinweis auf Kabel-/Hardwareprobleme statt Konfiguration."""
    host = payload.get("host")
    ifindex = payload.get("ifindex")
    if not host or not ifindex:
        raise HTTPException(400, "host und ifindex erforderlich")
    community = get_setting("snmp_community") or ""
    return get_port_errors(host, community, int(ifindex))


@app.post("/api/snmp/vlan_state")
def snmp_vlan_state(payload: dict = Body(...)):
    """Aktuellen VLAN-Zustand (PVID, tagged/untagged) eines Ports lesen."""
    host = payload.get("host")
    ifindex = payload.get("ifindex")
    if not host or not ifindex:
        raise HTTPException(400, "host und ifindex erforderlich")
    community = get_setting("snmp_community") or ""
    return get_vlan_state(host, community, int(ifindex))


@app.post("/api/snmp/vlan_write")
def snmp_vlan_write(payload: dict = Body(...)):
    """VLAN-Konfiguration eines Ports schreiben (EXPERIMENTELL)."""
    host = payload.get("host")
    ifindex = payload.get("ifindex")
    if not host or not ifindex:
        raise HTTPException(400, "host und ifindex erforderlich")
    community = get_setting("snmp_community") or ""
    return set_vlan_state(
        host, community, int(ifindex),
        pvid=payload.get("pvid"),
        tagged_vlans=payload.get("tagged_vlans") or [],
    )


# ------------------------------------------------------------ Export/Import

@app.get("/api/export/columns")
def export_columns():
    return {
        "columns": [{"key": k, "label": v[0]} for k, v in COLUMNS.items()],
        "default": DEFAULT_COLUMNS,
    }


@app.post("/api/export/xlsx")
def api_export_xlsx(payload: dict = Body(...)):
    path = export_xlsx(
        columns=payload.get("columns") or DEFAULT_COLUMNS,
        latest_only=payload.get("latest_only", True),
        date_from=payload.get("date_from"),
        date_to=payload.get("date_to"),
    )
    filename = f"kabelkataster-{time.strftime('%Y%m%d-%H%M')}.xlsx"
    return FileResponse(
        path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(os.remove, path),
    )


@app.get("/api/db/backup")
def db_backup():
    """Konsistenter Snapshot via VACUUM INTO, auch bei laufendem Betrieb."""
    snapshot = DB_PATH.parent / f"backup-{time.strftime('%Y%m%d-%H%M%S')}.db"
    conn = get_conn()
    conn.execute("VACUUM INTO ?", (str(snapshot),))
    conn.close()
    return FileResponse(
        snapshot,
        filename=f"netdiag-backup-{time.strftime('%Y%m%d-%H%M')}.db",
        media_type="application/octet-stream",
        background=BackgroundTask(os.remove, snapshot),
    )


@app.post("/api/db/restore")
async def db_restore(file: UploadFile):
    tmp = DB_PATH.parent / "restore-upload.db"
    with open(tmp, "wb") as fh:
        shutil.copyfileobj(file.file, fh)

    # Validierung: ist es SQLite mit passendem Schema?
    try:
        check = sqlite3.connect(tmp)
        version = check.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        check.close()
    except Exception:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "Datei ist keine gültige SQLite-Datenbank")

    required = {"floors", "rooms", "outlets", "measurements", "settings"}
    if not required.issubset(tables):
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "Datenbank hat nicht das netdiag-Schema")
    if version > SCHEMA_VERSION:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400,
            f"Datenbank-Schemaversion {version} ist neuer als diese App-Version ({SCHEMA_VERSION})")

    # Alte DB sichern, dann ersetzen
    bak = DB_PATH.parent / f"netdiag.db.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, bak)
    shutil.move(tmp, DB_PATH)
    init_db()  # falls ältere Schemaversion: hier später Migration
    return {"restored": True, "backup_of_previous": bak.name}


if __name__ == "__main__":
    import uvicorn

    # Default: nur localhost — die API hat keine Auth und kann SNMP-Writes
    # auslösen. Fernzugriff bewusst freischalten: NETDIAG_HOST=0.0.0.0
    uvicorn.run(
        app,
        host=os.environ.get("NETDIAG_HOST", "127.0.0.1"),
        port=int(os.environ.get("NETDIAG_PORT", "8642")),
    )
