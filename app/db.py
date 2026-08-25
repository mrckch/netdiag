"""SQLite-Persistenz für netdiag: Etagen, Räume, Dosen, Gerätetypen,
Messungen, Settings. Eine Datei, Schema-Version via PRAGMA user_version."""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("NETDIAG_DATA_DIR",
                               Path(__file__).parent.parent / "data"))
DB_PATH = DATA_DIR / "netdiag.db"
SCHEMA_VERSION = 3

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
    # Anbindung an den NetzwerkMonitor (Push-Sync, siehe app/sync.py)
    "monitor_url": "",
    "monitor_source": "",
    "monitor_token": "",
    "sync_enabled": "0",
}

# UUID-v4 in reinem SQL. Grund: die IDs müssen unabhängig vom Code-Pfad entstehen —
# ein Trigger erwischt jeden INSERT, auch künftige. Die UUID ist die Identität der
# Zeile gegenüber dem NetzwerkMonitor; die INTEGER-ids sind rein lokal.
_UUID_EXPR = (
    "lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || "
    "substr(hex(randomblob(2)), 2) || '-' || "
    "substr('89ab', abs(random()) % 4 + 1, 1) || "
    "substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6)))"
)

_UUID_TABLES = ("floors", "rooms", "outlets", "measurements")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS floors (
    id INTEGER PRIMARY KEY,
    uuid TEXT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    uuid TEXT,
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
    uuid TEXT,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    label TEXT NOT NULL COLLATE NOCASE,
    device_type_id INTEGER REFERENCES device_types(id) ON DELETE SET NULL,
    patch_panel_name TEXT,
    patch_panel_port TEXT,
    notes TEXT,
    UNIQUE(room_id, label)
);
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY,
    uuid TEXT,
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
    iperf_mbps REAL,
    synced_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_meas_outlet ON measurements(outlet_id);
CREATE INDEX IF NOT EXISTS idx_meas_unsynced ON measurements(synced_at);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _install_uuid_triggers(conn: sqlite3.Connection) -> None:
    for table in _UUID_TABLES:
        conn.execute(
            f"CREATE TRIGGER IF NOT EXISTS trg_{table}_uuid AFTER INSERT ON {table} "
            f"WHEN NEW.uuid IS NULL "
            f"BEGIN UPDATE {table} SET uuid = {_UUID_EXPR} WHERE id = NEW.id; END"
        )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_uuid ON {table}(uuid)"
        )


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Patchfeld-Felder an der Dose."""
    conn.execute("ALTER TABLE outlets ADD COLUMN patch_panel_name TEXT")
    conn.execute("ALTER TABLE outlets ADD COLUMN patch_panel_port TEXT")


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """UUIDs als systemübergreifende Identität + Sync-Marker je Messung.

    Bestandszeilen bekommen ihre UUID nachträglich; alle Messungen gelten als
    noch nicht übertragen und wandern beim ersten Sync in den NetzwerkMonitor.
    """
    for table in _UUID_TABLES:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
        conn.execute(f"UPDATE {table} SET uuid = {_UUID_EXPR} WHERE uuid IS NULL")
    conn.execute("ALTER TABLE measurements ADD COLUMN synced_at INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meas_unsynced ON measurements(synced_at)")


def _ensure_seed_data(conn: sqlite3.Connection) -> None:
    for name, icon in DEFAULT_DEVICE_TYPES:
        conn.execute(
            "INSERT OR IGNORE INTO device_types(name, icon) VALUES (?, ?)", (name, icon)
        )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
    # Identität dieser Tester-Installation; bleibt für immer stehen.
    conn.execute(
        "INSERT OR IGNORE INTO settings(key, value) VALUES ('instance_uuid', ?)",
        (str(uuid.uuid4()),),
    )


def init_db():
    conn = get_conn()
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version == 0:
        conn.executescript(_SCHEMA_SQL)
        version = SCHEMA_VERSION
    if version == 1:
        _migrate_v1_to_v2(conn)
        version = 2
    if version == 2:
        _migrate_v2_to_v3(conn)
        version = 3

    _install_uuid_triggers(conn)
    _ensure_seed_data(conn)
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


def set_setting(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
