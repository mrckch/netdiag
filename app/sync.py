"""Push des Kabelkatasters in den NetzwerkMonitor.

Warum Push und nicht Pull: der Tester ist mobil und hängt per DHCP an wechselnden
Ports — die Zentrale kann ihn nicht erreichen. Also meldet er sich selbst.

Warum `urllib` statt `requests`: ein Netbook im Feld soll möglichst wenig
mitschleppen; ein einzelner POST rechtfertigt keine zusätzliche Abhängigkeit.

Offline-fest: Gemessen und gespeichert wird immer, auch ohne Netz. Jede Messung
trägt `synced_at`; abgehakt wird nur, was die Zentrale ausdrücklich quittiert hat.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from app.db import get_conn, get_setting, set_setting

SCHEMA_VERSION = 1
TIMEOUT_SECONDS = 30

# Zeitpunkt/Ergebnis des letzten Laufs — reine Anzeigewerte für die UI.
_LAST_AT = "sync_last_at"
_LAST_ERROR = "sync_last_error"
_LAST_SUMMARY = "sync_last_summary"


class SyncNotConfigured(RuntimeError):
    """Sync ist nicht (vollständig) eingerichtet — kein Fehlerfall, nur nichts zu tun."""


def config() -> dict:
    return {
        "url": (get_setting("monitor_url") or "").strip().rstrip("/"),
        "source": (get_setting("monitor_source") or "").strip(),
        "token": (get_setting("monitor_token") or "").strip(),
        "enabled": (get_setting("sync_enabled") or "0") == "1",
        "instance_uuid": get_setting("instance_uuid") or "",
    }


def _require_config() -> dict:
    cfg = config()
    if not (cfg["url"] and cfg["source"] and cfg["token"]):
        raise SyncNotConfigured(
            "NetzwerkMonitor nicht eingerichtet (Verwaltung → NetzwerkMonitor)"
        )
    return cfg


def _iso_utc(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()


def _measurement_payload(row) -> dict:
    """Eine DB-Zeile in das Austauschformat übersetzen.

    Die Rohdaten liegen als `result_json` vor; daraus kommen die Felder, die die
    Zentrale für die Zuordnung zum Switch-Port braucht (LLDP + MAC des Testers).
    """
    try:
        raw = json.loads(row["result_json"] or "{}")
    except json.JSONDecodeError:
        raw = {}

    entry = {
        "uuid": row["uuid"],
        "outlet_uuid": row["outlet_uuid"],
        "measured_at": _iso_utc(row["started_at"]),
        "kind": row["kind"],
        "speed": row["speed"],
        "duplex": row["duplex"],
        "vlan_ids": row["vlan_ids"],
        "dhcp_ok": None if row["dhcp_ok"] is None else bool(row["dhcp_ok"]),
        "raw": raw or None,
    }

    link = raw.get("link") or {}
    entry["tester_mac"] = link.get("mac")

    neighbors = (raw.get("lldp") or {}).get("neighbors") or []
    if neighbors:
        first = neighbors[0]
        entry["lldp_switch_name"] = first.get("switch_name")
        entry["lldp_switch_mgmt_ip"] = first.get("switch_mgmt_ip")
        entry["lldp_port_id"] = first.get("port_id")
        entry["lldp_port_descr"] = first.get("port_descr")
    else:
        # CDP als Rückfallebene — dieselbe Aussage, andere Quelle.
        cdp = (raw.get("sniff") or {}).get("cdp") or {}
        entry["lldp_switch_name"] = cdp.get("device_id") or row["switch_name"]
        entry["lldp_port_id"] = cdp.get("port_id") or row["switch_port"]

    if row["kind"] == "iperf":
        entry["iperf_mbps_down"] = raw.get("mbps_down")
        entry["iperf_mbps_up"] = raw.get("mbps_up")
        entry["iperf_retransmits"] = raw.get("retransmits")

    return entry


def build_payload(include_synced: bool = False) -> dict:
    """Kompletter Ortsbaum + offene Messungen.

    Der Baum geht immer vollständig raus (er ist klein) — nur so kann die Zentrale
    erkennen, was hier gelöscht wurde. Messungen dagegen nur die offenen.
    """
    cfg = config()
    conn = get_conn()
    try:
        floors = [
            {"uuid": r["uuid"], "name": r["name"], "sort_order": r["sort_order"]}
            for r in conn.execute("SELECT * FROM floors ORDER BY sort_order, name")
        ]
        rooms = [
            {"uuid": r["uuid"], "floor_uuid": r["floor_uuid"], "name": r["name"]}
            for r in conn.execute(
                "SELECT r.uuid, r.name, f.uuid AS floor_uuid "
                "FROM rooms r JOIN floors f ON f.id = r.floor_id"
            )
        ]
        outlets = [
            {
                "uuid": r["uuid"],
                "room_uuid": r["room_uuid"],
                "label": r["label"],
                "device_type": r["device_type"],
                "device_icon": r["device_icon"],
                "patch_panel_name": r["patch_panel_name"],
                "patch_panel_port": r["patch_panel_port"],
                "notes": r["notes"],
            }
            for r in conn.execute(
                """SELECT o.uuid, o.label, o.patch_panel_name, o.patch_panel_port, o.notes,
                          rm.uuid AS room_uuid,
                          dt.name AS device_type, dt.icon AS device_icon
                   FROM outlets o
                   JOIN rooms rm ON rm.id = o.room_id
                   LEFT JOIN device_types dt ON dt.id = o.device_type_id"""
            )
        ]

        where = "" if include_synced else "WHERE m.synced_at IS NULL"
        measurements = [
            _measurement_payload(r)
            for r in conn.execute(
                f"""SELECT m.*, o.uuid AS outlet_uuid
                    FROM measurements m
                    LEFT JOIN outlets o ON o.id = m.outlet_id
                    {where}
                    ORDER BY m.started_at"""
            )
        ]
    finally:
        conn.close()

    return {
        "schema_version": SCHEMA_VERSION,
        "instance_uuid": cfg["instance_uuid"],
        "full_tree": True,
        "floors": floors,
        "rooms": rooms,
        "outlets": outlets,
        "measurements": measurements,
    }


def pending_count() -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM measurements WHERE synced_at IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()


def mark_synced(uuids: list[str]) -> int:
    if not uuids:
        return 0
    now = int(time.time())
    conn = get_conn()
    try:
        conn.executemany(
            "UPDATE measurements SET synced_at = ? WHERE uuid = ?",
            [(now, u) for u in uuids],
        )
        conn.commit()
        return len(uuids)
    finally:
        conn.close()


def _request(cfg: dict, path: str, body: dict | None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{cfg['url']}{path}",
        data=data,
        method="POST" if body is not None else "GET",
        headers={
            "Content-Type": "application/json",
            "X-Netdiag-Source": cfg["source"],
            "X-Netdiag-Token": cfg["token"],
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _error_text(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
        except Exception:  # noqa: BLE001 — Fehlertext ist best effort
            pass
        if exc.code == 401:
            return "Zentrale lehnt den Token ab (401)"
        return f"HTTP {exc.code}{': ' + str(detail) if detail else ''}"
    if isinstance(exc, urllib.error.URLError):
        return f"Zentrale nicht erreichbar: {exc.reason}"
    return str(exc)


def test_connection() -> dict:
    cfg = _require_config()
    try:
        data = _request(cfg, "/api/netdiag/ping", None)
    except Exception as exc:  # noqa: BLE001 — jede Störung ist hier eine Anzeige, kein Crash
        return {"ok": False, "error": _error_text(exc)}
    return {"ok": True, "source": data.get("source")}


def push() -> dict:
    """Überträgt Baum + offene Messungen. Bricht nie hart ab — der Tester muss
    auch dann weiterarbeiten, wenn die Zentrale gerade nicht da ist."""
    cfg = _require_config()
    payload = build_payload()

    try:
        result = _request(cfg, "/api/netdiag/sync", payload)
    except Exception as exc:  # noqa: BLE001
        error = _error_text(exc)
        set_setting(_LAST_ERROR, error)
        return {"ok": False, "error": error, "pending": pending_count()}

    marked = mark_synced(result.get("accepted_measurement_uuids") or [])
    summary = (
        f"{result.get('locations_upserted', 0)} Orte, "
        f"{result.get('outlets_upserted', 0)} Dosen, "
        f"{result.get('measurements_added', 0)} neue Messungen"
    )
    set_setting(_LAST_AT, str(int(time.time())))
    set_setting(_LAST_ERROR, "")
    set_setting(_LAST_SUMMARY, summary)

    return {
        "ok": True,
        "summary": summary,
        "marked_synced": marked,
        "pending": pending_count(),
        "warnings": result.get("warnings") or [],
    }


def push_quietly() -> None:
    """Feuer-und-vergiss-Variante für den Hintergrund nach dem Speichern.

    Ein fehlgeschlagener Sync ist hier kein Fehler: die Messung liegt lokal,
    der nächste Lauf holt sie nach.
    """
    try:
        if not config()["enabled"]:
            return
        push()
    except SyncNotConfigured:
        return
    except Exception:  # noqa: BLE001 — darf den Messbetrieb niemals stören
        return


def status() -> dict:
    cfg = config()
    last_at = get_setting(_LAST_AT)
    return {
        "configured": bool(cfg["url"] and cfg["source"] and cfg["token"]),
        "enabled": cfg["enabled"],
        "url": cfg["url"],
        "source": cfg["source"],
        "pending": pending_count(),
        "last_sync_at": int(last_at) if last_at else None,
        "last_summary": get_setting(_LAST_SUMMARY) or "",
        "last_error": get_setting(_LAST_ERROR) or "",
    }
