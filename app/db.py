"""SQLite-Persistenz für netdiag: Etagen, Räume, Dosen, Gerätetypen,
Messungen, Settings. Eine Datei, Schema-Version via PRAGMA user_version."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "netdiag.db"
SCHEMA_VERSION = 1

DEFAULT_DEVICE_TYPES = [
    ("PC", "🖥"),
    ("Beamer", "📽"),
    ("AppleTV", "📺"),
    ("Drucker", "🖨"),
    ("Access Point", "📡"),
    ("Telefon/VoIP", "☎"),
    ("Switch/Uplink", "🔀"),
    ("frei", "⭕"),
    ("Sonstiges", "❓"),
]

DEFAULT_SETTINGS = {
    "iperf_server": "",
    "snmp_community": "",
    "snmp_descr_template": "{raum}-{dose} {geraet}",
}


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        conn.close()
        return
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS floors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY,
            floor_id INTEGER NOT NULL REFERENCES floors(id) ON DELETE CASCADE,
            name TEXT NOT NULL COLLATE NOCASE,
            UNIQUE(floor_id, name)
        );
        CREATE TABLE IF NOT EXISTS device_types (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            icon TEXT NOT NULL DEFAULT '❓'
        );
        CREATE TABLE IF NOT EXISTS outlets (
            id INTEGER PRIMARY KEY,
            room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
            label TEXT NOT NULL COLLATE NOCASE,
            device_type_id INTEGER REFERENCES device_types(id) ON DELETE SET NULL,
            notes TEXT,
            UNIQUE(room_id, label)
        );
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY,
            outlet_id INTEGER REFERENCES outlets(id) ON DELETE CASCADE,
            started_at INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'autotest',
            result_json TEXT NOT NULL,
            speed TEXT,
            duplex TEXT,
            vlan_ids TEXT,
            switch_name TEXT,
            switch_port TEXT,
            dhcp_ok INTEGER,
            iperf_mbps REAL
        );
        CREATE INDEX IF NOT EXISTS idx_meas_outlet ON measurements(outlet_id);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    for name, icon in DEFAULT_DEVICE_TYPES:
        conn.execute(
            "INSERT OR IGNORE INTO device_types(name, icon) VALUES (?, ?)", (name, icon)
        )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()


def save_measurement(result: dict, outlet_id: int | None, kind: str = "autotest") -> int:
    """Speichert eine Messung mit denormalisierten Summary-Spalten."""
    speed = duplex = vlan_ids = switch_name = switch_port = None
    dhcp_ok = None
    iperf_mbps = None

    if kind == "autotest":
        link = result.get("link") or {}
        speed = link.get("speed")
        duplex = link.get("duplex")
        sniff = result.get("sniff") or {}
        ids = sniff.get("vlan_ids_seen") or []
        vlan_ids = ",".join(str(v) for v in ids) if ids else None
        lldp = result.get("lldp") or {}
        neighbors = lldp.get("neighbors") or []
        if neighbors:
            switch_name = neighbors[0].get("switch_name")
            switch_port = neighbors[0].get("port_id")
        cdp = sniff.get("cdp")
        if cdp and not switch_name:
            switch_name = cdp.get("device_id")
            switch_port = cdp.get("port_id")
        dhcp = result.get("dhcp") or {}
        dhcp_ok = 1 if dhcp.get("server_found") else 0
    elif kind == "iperf":
        iperf_mbps = result.get("mbps_down") or result.get("mbps")

    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO measurements
           (outlet_id, started_at, kind, result_json, speed, duplex, vlan_ids,
            switch_name, switch_port, dhcp_ok, iperf_mbps)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            outlet_id,
            int(time.time()),
            kind,
            json.dumps(result),
            speed,
            duplex,
            vlan_ids,
            switch_name,
            switch_port,
            dhcp_ok,
            iperf_mbps,
        ),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def get_setting(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None
