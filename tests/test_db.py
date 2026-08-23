import sqlite3

import pytest

import app.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "netdiag.db")
    return tmp_path / "netdiag.db"


def test_init_fresh(tmp_db):
    db.init_db()
    conn = db.get_conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"floors", "rooms", "outlets", "measurements", "settings",
            "device_types"} <= tables
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == db.SCHEMA_VERSION
    conn.close()


def test_migration_v1_to_v2(tmp_db):
    # v1-Schema von Hand: outlets ohne Patchfeld-Spalten
    conn = sqlite3.connect(tmp_db)
    conn.executescript("""
        CREATE TABLE floors (id INTEGER PRIMARY KEY, name TEXT, sort_order INTEGER);
        CREATE TABLE rooms (id INTEGER PRIMARY KEY, floor_id INTEGER, name TEXT);
        CREATE TABLE outlets (id INTEGER PRIMARY KEY, room_id INTEGER, label TEXT,
            device_type_id INTEGER, notes TEXT);
        CREATE TABLE measurements (id INTEGER PRIMARY KEY);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE device_types (id INTEGER PRIMARY KEY, name TEXT, icon TEXT);
        PRAGMA user_version = 1;
    """)
    conn.commit()
    conn.close()

    db.init_db()
    conn = db.get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(outlets)").fetchall()}
    assert "patch_panel_name" in cols and "patch_panel_port" in cols
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    conn.close()


def test_save_measurement_summary(tmp_db):
    db.init_db()
    result = {
        "link": {"speed": "1000Mb/s", "duplex": "Full"},
        "sniff": {"vlan_ids_seen": [10, 20], "cdp": None},
        "lldp": {"neighbors": [{"switch_name": "sw1", "port_id": "24"}]},
        "dhcp": {"server_found": True},
    }
    mid = db.save_measurement(result, outlet_id=None, kind="autotest")
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (mid,)).fetchone()
    conn.close()
    assert row["speed"] == "1000Mb/s"
    assert row["vlan_ids"] == "10,20"
    assert row["switch_name"] == "sw1"
    assert row["switch_port"] == "24"
    assert row["dhcp_ok"] == 1


def test_save_measurement_cdp_fallback(tmp_db):
    db.init_db()
    result = {
        "link": {}, "dhcp": {},
        "sniff": {"cdp": {"device_id": "cisco-sw", "port_id": "Fa0/3"}},
        "lldp": {"neighbors": []},
    }
    mid = db.save_measurement(result, outlet_id=None)
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (mid,)).fetchone()
    conn.close()
    assert row["switch_name"] == "cisco-sw"
    assert row["switch_port"] == "Fa0/3"


def test_save_iperf_measurement(tmp_db):
    db.init_db()
    mid = db.save_measurement({"mbps_down": 941.3, "mbps_up": 880.1},
                              outlet_id=None, kind="iperf")
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (mid,)).fetchone()
    conn.close()
    assert row["kind"] == "iperf"
    assert row["iperf_mbps"] == 941.3
