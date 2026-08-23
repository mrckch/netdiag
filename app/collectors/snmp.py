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


# ================================================================
# Q-BRIDGE-MIB: PVID + VLAN-Mitgliedschaft (EXPERIMENTELL —
# vor produktivem Einsatz gegen die konkreten Switches verifizieren,
# LANCOM/ProCurve setzen die MIB teils unterschiedlich um)
# ================================================================

BASEPORT_IFINDEX_OID = "1.3.6.1.2.1.17.1.4.1.2"        # dot1dBasePortIfIndex
PVID_OID = "1.3.6.1.2.1.17.7.1.4.5.1.1"                # dot1qPvid.<basePort>
VLAN_STATIC_EGRESS_OID = "1.3.6.1.2.1.17.7.1.4.3.1.2"   # dot1qVlanStaticEgressPorts.<vlanId>
VLAN_STATIC_UNTAGGED_OID = "1.3.6.1.2.1.17.7.1.4.3.1.4" # dot1qVlanStaticUntaggedPorts.<vlanId>


def _resolve_baseport(host: str, community: str, ifindex: int) -> int | None:
    """Bridge-BasePort zum ifIndex finden (dot1dBasePortIfIndex invertieren)."""
    mapping = _walk(host, community, BASEPORT_IFINDEX_OID)
    for baseport, val in mapping.items():
        try:
            if int(val) == ifindex:
                return baseport
        except ValueError:
            continue
    return None


def _get_hex(host: str, community: str, oid: str) -> bytes | None:
    """SNMP-GET eines OCTET-STRING als Bytes (Hex-Ausgabe erzwingen)."""
    out = subprocess.run(
        ["snmpget", "-v2c", "-c", community, "-Oqv", "-Ox", "-t", "3", "-r", "1", host, oid],
        capture_output=True, text=True, timeout=10,
    )
    raw = out.stdout.strip().strip('"')
    if not raw or "No Such" in raw:
        return None
    try:
        return bytes.fromhex(raw.replace(" ", ""))
    except ValueError:
        return None


def _port_in_bitmap(bitmap: bytes, baseport: int) -> bool:
    """Bit für basePort in Portlisten-Bitmap prüfen (Bit 1 = MSB von Byte 0)."""
    byte_idx = (baseport - 1) // 8
    bit_idx = 7 - ((baseport - 1) % 8)
    if byte_idx >= len(bitmap):
        return False
    return bool(bitmap[byte_idx] & (1 << bit_idx))


def _set_port_in_bitmap(bitmap: bytes, baseport: int, member: bool) -> bytes:
    byte_idx = (baseport - 1) // 8
    bit_idx = 7 - ((baseport - 1) % 8)
    b = bytearray(bitmap)
    while len(b) <= byte_idx:
        b.append(0)
    if member:
        b[byte_idx] |= (1 << bit_idx)
    else:
        b[byte_idx] &= ~(1 << bit_idx)
    return bytes(b)


def get_vlan_state(host: str, community: str, ifindex: int) -> dict:
    """Aktueller VLAN-Zustand eines Ports: PVID + tagged/untagged Mitgliedschaften."""
    result = {"ifindex": ifindex, "baseport": None, "pvid": None,
              "tagged_vlans": [], "untagged_vlans": [], "error": None}
    if not community:
        result["error"] = "Keine SNMP-Community konfiguriert"
        return result
    try:
        baseport = _resolve_baseport(host, community, ifindex)
        if baseport is None:
            result["error"] = "BasePort zu ifIndex nicht gefunden (Bridge-MIB nicht verfügbar?)"
            return result
        result["baseport"] = baseport

        out = subprocess.run(
            ["snmpget", "-v2c", "-c", community, "-Oqv", "-t", "3", "-r", "1",
             host, f"{PVID_OID}.{baseport}"],
            capture_output=True, text=True, timeout=10,
        )
        val = out.stdout.strip()
        if val.isdigit():
            result["pvid"] = int(val)

        # Alle statisch konfigurierten VLANs durchgehen
        egress_walk = subprocess.run(
            ["snmpwalk", "-v2c", "-c", community, "-Oqn", "-Ox", "-t", "3", "-r", "1",
             host, VLAN_STATIC_EGRESS_OID],
            capture_output=True, text=True, timeout=30,
        )
        vlan_ids = []
        for line in egress_walk.stdout.splitlines():
            m = re.match(r"\.?[\d.]+\.(\d+)\s+", line.strip())
            if m:
                vlan_ids.append(int(m.group(1)))

        for vid in vlan_ids:
            egress = _get_hex(host, community, f"{VLAN_STATIC_EGRESS_OID}.{vid}")
            if not egress or not _port_in_bitmap(egress, baseport):
                continue
            untagged = _get_hex(host, community, f"{VLAN_STATIC_UNTAGGED_OID}.{vid}")
            if untagged and _port_in_bitmap(untagged, baseport):
                result["untagged_vlans"].append(vid)
            else:
                result["tagged_vlans"].append(vid)

    except FileNotFoundError:
        result["error"] = "snmp-Tools nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "SNMP Timeout"
    return result


def _set_hex(host: str, community: str, oid: str, value: bytes) -> tuple[bool, str]:
    out = subprocess.run(
        ["snmpset", "-v2c", "-c", community, "-t", "5", "-r", "1",
         host, oid, "x", value.hex()],
        capture_output=True, text=True, timeout=15,
    )
    return out.returncode == 0, (out.stderr.strip() or out.stdout.strip())


def set_vlan_state(host: str, community: str, ifindex: int,
                   pvid: int | None, tagged_vlans: list[int]) -> dict:
    """Setzt PVID und tagged-VLAN-Mitgliedschaften eines Ports.

    Ablauf pro VLAN: Egress-Bitmap lesen → Bit setzen/löschen → zurückschreiben.
    Für das PVID-VLAN wird der Port zusätzlich in die Untagged-Bitmap eingetragen.
    """
    result = {"ifindex": ifindex, "success": False, "steps": [], "error": None}
    if not community:
        result["error"] = "Keine SNMP-Community konfiguriert"
        return result
    try:
        baseport = _resolve_baseport(host, community, ifindex)
        if baseport is None:
            result["error"] = "BasePort zu ifIndex nicht gefunden"
            return result

        current = get_vlan_state(host, community, ifindex)
        current_vlans = set(current["tagged_vlans"]) | set(current["untagged_vlans"])
        target_vlans = set(tagged_vlans)
        if pvid:
            target_vlans.add(pvid)

        # 1. Neue VLANs hinzufügen / bestehende anpassen
        for vid in sorted(target_vlans):
            egress = _get_hex(host, community, f"{VLAN_STATIC_EGRESS_OID}.{vid}")
            if egress is None:
                result["steps"].append(f"VLAN {vid}: existiert nicht auf dem Switch — übersprungen")
                continue
            new_egress = _set_port_in_bitmap(egress, baseport, True)
            if new_egress != egress:
                ok, msg = _set_hex(host, community, f"{VLAN_STATIC_EGRESS_OID}.{vid}", new_egress)
                result["steps"].append(f"VLAN {vid} egress: {'ok' if ok else msg}")
                if not ok:
                    result["error"] = f"Egress-Write VLAN {vid} fehlgeschlagen: {msg}"
                    return result

            untagged = _get_hex(host, community, f"{VLAN_STATIC_UNTAGGED_OID}.{vid}")
            if untagged is not None:
                want_untagged = (vid == pvid)
                new_untagged = _set_port_in_bitmap(untagged, baseport, want_untagged)
                if new_untagged != untagged:
                    ok, msg = _set_hex(
                        host, community, f"{VLAN_STATIC_UNTAGGED_OID}.{vid}", new_untagged)
                    result["steps"].append(
                        f"VLAN {vid} untagged={want_untagged}: {'ok' if ok else msg}")
                    if not ok:
                        result["error"] = f"Untagged-Write VLAN {vid} fehlgeschlagen: {msg}"
                        return result

        # 2. PVID setzen
        if pvid:
            out = subprocess.run(
                ["snmpset", "-v2c", "-c", community, "-t", "5", "-r", "1",
                 host, f"{PVID_OID}.{baseport}", "u", str(pvid)],
                capture_output=True, text=True, timeout=15,
            )
            ok = out.returncode == 0
            result["steps"].append(f"PVID {pvid}: {'ok' if ok else out.stderr.strip()}")
            if not ok:
                result["error"] = f"PVID-Write fehlgeschlagen: {out.stderr.strip()}"
                return result

        # 3. Aus nicht mehr gewünschten VLANs entfernen
        for vid in sorted(current_vlans - target_vlans):
            egress = _get_hex(host, community, f"{VLAN_STATIC_EGRESS_OID}.{vid}")
            if egress is None:
                continue
            new_egress = _set_port_in_bitmap(egress, baseport, False)
            if new_egress != egress:
                ok, msg = _set_hex(host, community, f"{VLAN_STATIC_EGRESS_OID}.{vid}", new_egress)
                result["steps"].append(f"VLAN {vid} entfernt: {'ok' if ok else msg}")
                if not ok:
                    result["error"] = f"Entfernen aus VLAN {vid} fehlgeschlagen: {msg}"
                    return result

        result["success"] = True
    except FileNotFoundError:
        result["error"] = "snmp-Tools nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "SNMP Timeout"
    return result
