"""SNMP v2c: Port-Description (ifAlias) am Switch setzen.

Ablauf:
1. resolve_ifindex(): per snmpwalk über ifName/ifDescr den ifIndex zum
   LLDP-Port-Namen finden (z.B. "24" oder "GigabitEthernet1/0/24").
2. set_port_description(): snmpset auf ifAlias.<ifIndex>.

Nutzt net-snmp CLI-Tools (snmpwalk/snmpset) — robust und überall verfügbar.
"""
import re
import subprocess

IFNAME_OID = "1.3.6.1.2.1.31.1.1.1.1"   # ifName
IFDESCR_OID = "1.3.6.1.2.1.2.2.1.2"      # ifDescr
IFALIAS_OID = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias (Port-Description)


def _walk(host: str, community: str, oid: str) -> dict[int, str]:
    """Gibt {ifIndex: wert} zurück."""
    out = subprocess.run(
        ["snmpwalk", "-v2c", "-c", community, "-Oqn", "-t", "3", "-r", "1", host, oid],
        capture_output=True,
        text=True,
        timeout=20,
    )
    result = {}
    for line in out.stdout.splitlines():
        # Format: .1.3.6.1.2.1.31.1.1.1.1.24 GigabitEthernet1/0/24
        m = re.match(r"\.?[\d.]+\.(\d+)\s+(.*)", line.strip())
        if m:
            result[int(m.group(1))] = m.group(2).strip().strip('"')
    return result


def resolve_ifindex(host: str, community: str, port_name: str) -> dict:
    """Findet den ifIndex zu einem Port-Namen (aus LLDP/CDP)."""
    result = {"host": host, "port_name": port_name, "ifindex": None,
              "matched_name": None, "candidates": [], "error": None}
    if not community:
        result["error"] = "Keine SNMP-Community konfiguriert (Verwaltung)"
        return result
    try:
        names = _walk(host, community, IFNAME_OID)
        if not names:
            names = _walk(host, community, IFDESCR_OID)
        if not names:
            result["error"] = "SNMP-Walk lieferte nichts — Community/Erreichbarkeit prüfen"
            return result

        needle = port_name.strip().lower()
        # 1. exakte Übereinstimmung
        for idx, name in names.items():
            if name.lower() == needle:
                result["ifindex"], result["matched_name"] = idx, name
                return result
        # 2. Teilstring in beide Richtungen (LLDP liefert je nach Switch
        #    mal "24", mal "Port 24", mal "GigabitEthernet1/0/24")
        matches = [
            (idx, name) for idx, name in names.items()
            if needle in name.lower() or name.lower() in needle
        ]
        if len(matches) == 1:
            result["ifindex"], result["matched_name"] = matches[0]
        elif len(matches) > 1:
            result["candidates"] = [{"ifindex": i, "name": n} for i, n in matches]
            result["error"] = "Port-Name nicht eindeutig — bitte Kandidat wählen"
        else:
            result["error"] = f"Port '{port_name}' nicht in ifName/ifDescr gefunden"
    except FileNotFoundError:
        result["error"] = "snmpwalk nicht installiert (apt install snmp)"
    except subprocess.TimeoutExpired:
        result["error"] = "SNMP Timeout"
    return result


def get_current_alias(host: str, community: str, ifindex: int) -> str | None:
    try:
        out = subprocess.run(
            ["snmpget", "-v2c", "-c", community, "-Oqv", "-t", "3", "-r", "1",
             host, f"{IFALIAS_OID}.{ifindex}"],
            capture_output=True, text=True, timeout=10,
        )
        val = out.stdout.strip().strip('"')
        return val if val and "No Such" not in val else None
    except Exception:
        return None


def set_port_description(host: str, community: str, ifindex: int, description: str) -> dict:
    result = {"host": host, "ifindex": ifindex, "description": description,
              "success": False, "error": None}
    if not community:
        result["error"] = "Keine SNMP-Community konfiguriert"
        return result
    try:
        out = subprocess.run(
            ["snmpset", "-v2c", "-c", community, "-t", "3", "-r", "1",
             host, f"{IFALIAS_OID}.{ifindex}", "s", description],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0:
            result["success"] = True
        else:
            result["error"] = out.stderr.strip() or out.stdout.strip() or "snmpset fehlgeschlagen"
    except FileNotFoundError:
        result["error"] = "snmpset nicht installiert (apt install snmp)"
    except subprocess.TimeoutExpired:
        result["error"] = "SNMP Timeout"
    return result
