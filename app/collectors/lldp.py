"""Switch-Erkennung via LLDP (lldpd/lldpcli).

Der Parser versteht beide lldpcli-JSON-Varianten:
- "json0": alles Listen von Dicts, Blattwerte als {"value": ...}
- "json":  verschachtelte Dicts, chassis nach Switch-Namen gekeyt
"""
import json
import subprocess


def _first(x):
    """Erstes Element, falls Liste — json0 verpackt alles in Listen."""
    if isinstance(x, list):
        return x[0] if x else None
    return x


def _val(x):
    """Blattwert extrahieren: json0 liefert {"value": ...}, json den Wert direkt."""
    x = _first(x)
    if isinstance(x, dict):
        return x.get("value")
    return x


def _iface_entries(interfaces) -> list[dict]:
    """Interface-Knoten beider Formate auf eine Liste von Einträgen normieren."""
    if interfaces is None:
        return []
    if isinstance(interfaces, list):
        return [e for e in interfaces if isinstance(e, dict)]
    if isinstance(interfaces, dict):
        if "chassis" in interfaces or "port" in interfaces:
            return [interfaces]  # direkt ein Eintrag
        # "json"-Format: {ifname: {...}} — ggf. mehrere Interfaces
        out = []
        for v in interfaces.values():
            if isinstance(v, dict):
                out.append(v)
            elif isinstance(v, list):
                out.extend(e for e in v if isinstance(e, dict))
        return out
    return []


def _chassis_info(chassis) -> tuple[str | None, dict]:
    """(Switch-Name, Chassis-Dict) aus beiden Formaten."""
    c = _first(chassis)
    if not isinstance(c, dict):
        return None, {}
    if "name" in c or "id" in c or "mgmt-ip" in c:
        return _val(c.get("name")), c
    # "json"-Format: {switchname: {...}}
    for name, info in c.items():
        if isinstance(info, dict):
            return _val(info.get("name")) or name, info
    return None, {}


def parse_lldp_json(data: dict) -> list[dict]:
    """Nachbarn aus lldpcli-JSON extrahieren (reine Funktion, testbar)."""
    neighbors = []
    lldp = _first(data.get("lldp")) or {}
    if not isinstance(lldp, dict):
        return neighbors
    for entry in _iface_entries(lldp.get("interface")):
        name, chassis_info = _chassis_info(entry.get("chassis"))
        port = _first(entry.get("port")) or {}
        vlan = _first(entry.get("vlan")) or {}

        mgmt = chassis_info.get("mgmt-ip")
        mgmt_ip = _val(mgmt)
        if mgmt_ip is None and isinstance(mgmt, list) and mgmt:
            mgmt_ip = _val(mgmt[0])

        neighbors.append({
            "switch_name": name,
            "switch_mgmt_ip": mgmt_ip,
            "port_id": _val(port.get("id")) if isinstance(port, dict) else None,
            "port_descr": _val(port.get("descr")) if isinstance(port, dict) else None,
            "vlan": vlan.get("vlan-id") if isinstance(vlan, dict) else None,
        })
    return neighbors


def get_lldp_neighbors(interface: str) -> dict:
    result = {"interface": interface, "found": False, "neighbors": [], "error": None}
    try:
        out = subprocess.run(
            ["lldpcli", "-f", "json0", "show", "neighbors", "details", "ports", interface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            result["error"] = out.stderr.strip() or "lldpcli fehlgeschlagen"
            return result

        data = json.loads(out.stdout or "{}")
        result["neighbors"] = parse_lldp_json(data)
        result["found"] = len(result["neighbors"]) > 0

    except FileNotFoundError:
        result["error"] = "lldpd/lldpcli nicht installiert (siehe scripts/install.sh)"
    except subprocess.TimeoutExpired:
        result["error"] = "lldpcli Timeout — evtl. läuft lldpd nicht"
    except json.JSONDecodeError:
        result["error"] = "lldpcli Antwort konnte nicht geparst werden"
    return result
