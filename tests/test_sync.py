"""Sync zum NetzwerkMonitor: UUID-Vergabe, Payload-Aufbau, Offline-Queue."""
import json
import sqlite3
import urllib.error

import pytest

import app.db as db
import app.sync as sync


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "netdiag.db")
    db.init_db()
    return tmp_path / "netdiag.db"


def _tree(conn) -> int:
    """Etage → Raum → Dose anlegen, gibt die outlet_id zurück."""
    fid = conn.execute("INSERT INTO floors(name) VALUES ('1. OG')").lastrowid
    rid = conn.execute("INSERT INTO rooms(floor_id, name) VALUES (?, 'R204')", (fid,)).lastrowid
    oid = conn.execute(
        "INSERT INTO outlets(room_id, label, patch_panel_name, patch_panel_port) "
        "VALUES (?, 'D3', 'PP-A', '17')", (rid,)
    ).lastrowid
    conn.commit()
    return oid


def test_uuid_trigger_fills_every_insert(tmp_db):
    conn = db.get_conn()
    oid = _tree(conn)
    row = conn.execute("SELECT uuid FROM outlets WHERE id = ?", (oid,)).fetchone()
    conn.close()
    # UUID-v4-Form: 8-4-4-4-12
    assert row["uuid"] and len(row["uuid"]) == 36
    assert row["uuid"][14] == "4"


def test_migration_v2_to_v3_backfills_uuids(tmp_path, monkeypatch):
    """Bestands-DB (v2) bekommt UUIDs und den Sync-Marker nachgereicht."""
    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE floors (id INTEGER PRIMARY KEY, name TEXT, sort_order INTEGER DEFAULT 0);
        CREATE TABLE rooms (id INTEGER PRIMARY KEY, floor_id INTEGER, name TEXT);
        CREATE TABLE outlets (id INTEGER PRIMARY KEY, room_id INTEGER, label TEXT,
            device_type_id INTEGER, patch_panel_name TEXT, patch_panel_port TEXT, notes TEXT);
        CREATE TABLE measurements (id INTEGER PRIMARY KEY, outlet_id INTEGER,
            started_at INTEGER, kind TEXT, result_json TEXT, speed TEXT, duplex TEXT,
            vlan_ids TEXT, switch_name TEXT, switch_port TEXT, dhcp_ok INTEGER,
            iperf_mbps REAL);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE device_types (id INTEGER PRIMARY KEY, name TEXT, icon TEXT);
        INSERT INTO floors(id, name) VALUES (1, 'EG');
        INSERT INTO measurements(id, outlet_id, started_at, kind, result_json)
            VALUES (1, NULL, 1700000000, 'autotest', '{}');
        PRAGMA user_version = 2;
    """)
    conn.commit()
    conn.close()

    db.init_db()

    conn = db.get_conn()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT uuid FROM floors WHERE id = 1").fetchone()["uuid"]
    row = conn.execute("SELECT uuid, synced_at FROM measurements WHERE id = 1").fetchone()
    conn.close()
    assert row["uuid"]
    # Bestandsmessungen gelten als offen und wandern beim ersten Sync mit.
    assert row["synced_at"] is None


def test_build_payload_contains_cadastre_and_measurement(tmp_db):
    conn = db.get_conn()
    oid = _tree(conn)
    conn.close()

    db.save_measurement(
        {
            "link": {"speed": "1000Mb/s", "duplex": "Full", "mac": "AA:BB:CC:DD:EE:FF"},
            "sniff": {"vlan_ids_seen": [10]},
            "lldp": {"neighbors": [{
                "switch_name": "Switch-OG1",
                "switch_mgmt_ip": "192.168.150.88",
                "port_id": "Port 5",
                "port_descr": "R204",
            }]},
            "dhcp": {"server_found": True},
        },
        outlet_id=oid,
    )

    payload = sync.build_payload()
    assert payload["schema_version"] == sync.SCHEMA_VERSION
    assert payload["full_tree"] is True
    assert [f["name"] for f in payload["floors"]] == ["1. OG"]
    assert payload["rooms"][0]["floor_uuid"] == payload["floors"][0]["uuid"]

    outlet = payload["outlets"][0]
    assert outlet["patch_panel_name"] == "PP-A"
    assert outlet["patch_panel_port"] == "17"
    assert outlet["room_uuid"] == payload["rooms"][0]["uuid"]

    meas = payload["measurements"][0]
    assert meas["outlet_uuid"] == outlet["uuid"]
    assert meas["lldp_switch_mgmt_ip"] == "192.168.150.88"
    assert meas["lldp_port_id"] == "Port 5"
    assert meas["tester_mac"] == "AA:BB:CC:DD:EE:FF"
    assert meas["measured_at"].endswith("+00:00")


def test_iperf_measurement_carries_both_directions(tmp_db):
    db.save_measurement(
        {"mbps_down": 941.0, "mbps_up": 936.2, "retransmits": 3},
        outlet_id=None,
        kind="iperf",
    )
    meas = sync.build_payload()["measurements"][0]
    assert meas["iperf_mbps_down"] == 941.0
    assert meas["iperf_mbps_up"] == 936.2
    assert meas["iperf_retransmits"] == 3


def test_push_marks_only_acknowledged_measurements(tmp_db, monkeypatch):
    db.save_measurement({"link": {}, "dhcp": {}, "lldp": {}, "sniff": {}}, outlet_id=None)
    db.save_measurement({"link": {}, "dhcp": {}, "lldp": {}, "sniff": {}}, outlet_id=None)
    assert sync.pending_count() == 2

    sent = {}

    def fake_request(cfg, path, body):
        sent["path"] = path
        sent["body"] = body
        # Zentrale quittiert nur die erste Messung.
        return {
            "accepted_measurement_uuids": [body["measurements"][0]["uuid"]],
            "locations_upserted": 0,
            "outlets_upserted": 0,
            "measurements_added": 1,
        }

    _configure(monkeypatch, fake_request)
    result = sync.push()

    assert result["ok"] is True
    assert sent["path"] == "/api/netdiag/sync"
    assert result["marked_synced"] == 1
    # Die nicht quittierte Messung bleibt in der Warteschlange.
    assert sync.pending_count() == 1


def test_push_survives_unreachable_central(tmp_db, monkeypatch):
    db.save_measurement({"link": {}, "dhcp": {}, "lldp": {}, "sniff": {}}, outlet_id=None)

    def boom(cfg, path, body):
        raise urllib.error.URLError("Name or service not known")

    _configure(monkeypatch, boom)
    result = sync.push()

    assert result["ok"] is False
    assert "nicht erreichbar" in result["error"]
    # Nichts abgehakt — die Messung geht beim nächsten Versuch erneut raus.
    assert sync.pending_count() == 1


def test_push_reports_rejected_token(tmp_db, monkeypatch):
    def unauthorized(cfg, path, body):
        raise urllib.error.HTTPError(
            "https://example/api/netdiag/sync", 401, "Unauthorized", {}, None
        )

    _configure(monkeypatch, unauthorized)
    result = sync.push()
    assert result["ok"] is False
    assert "401" in result["error"]


def test_push_without_configuration_raises(tmp_db):
    with pytest.raises(sync.SyncNotConfigured):
        sync.push()


def test_push_quietly_never_raises(tmp_db):
    # Nicht eingerichtet, kein Netz, egal — der Messbetrieb darf nie hängen.
    sync.push_quietly()


def test_status_reports_pending(tmp_db):
    db.save_measurement({"link": {}, "dhcp": {}, "lldp": {}, "sniff": {}}, outlet_id=None)
    st = sync.status()
    assert st["configured"] is False
    assert st["pending"] == 1


def test_token_is_never_returned_by_settings_api(tmp_db):
    from fastapi.testclient import TestClient

    from app.main import app

    db.set_setting("monitor_token", "geheim")
    with TestClient(app) as c:
        body = c.get("/api/settings").json()
    assert body["monitor_token"] == ""
    assert body["monitor_token_set"] == "1"


def _configure(monkeypatch, request_fn) -> None:
    db.set_setting("monitor_url", "https://pmon.example")
    db.set_setting("monitor_source", "netbook-tester")
    db.set_setting("monitor_token", "t0ken")
    db.set_setting("sync_enabled", "1")
    monkeypatch.setattr(sync, "_request", request_fn)


def test_export_payload_includes_synced(tmp_db):
    """Der Export ist für den Erstimport da — er nimmt auch abgehakte Messungen mit."""
    db.save_measurement({"link": {}, "dhcp": {}, "lldp": {}, "sniff": {}}, outlet_id=None)
    payload = sync.build_payload()
    sync.mark_synced([payload["measurements"][0]["uuid"]])

    assert sync.build_payload()["measurements"] == []
    assert len(sync.build_payload(include_synced=True)["measurements"]) == 1
    assert json.dumps(sync.build_payload(include_synced=True))  # serialisierbar
