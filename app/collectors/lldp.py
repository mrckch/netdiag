"""Switch-Erkennung via LLDP (lldpd/lldpcli JSON-Output)."""
import json
import subprocess


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
        lldp = data.get("lldp", {})
        interfaces = lldp.get("interface", [])
        if isinstance(interfaces, dict):
            interfaces = [interfaces]

        for iface_entry in interfaces:
            chassis = iface_entry.get("chassis", {})
            chassis_name = next(iter(chassis.keys()), None) if chassis else None
            chassis_info = chassis.get(chassis_name, {}) if chassis_name else {}

            port = iface_entry.get("port", {})
            vlan = iface_entry.get("vlan", {})

            neighbor = {
                "switch_name": chassis_info.get("name", {}).get("value")
                if isinstance(chassis_info.get("name"), dict)
                else chassis_info.get("name"),
                "switch_mgmt_ip": None,
                "port_id": port.get("id", {}).get("value")
                if isinstance(port.get("id"), dict)
                else None,
                "port_descr": port.get("descr"),
                "vlan": vlan.get("vlan-id") if isinstance(vlan, dict) else None,
            }

            mgmt = chassis_info.get("mgmt-ip")
            if mgmt:
                if isinstance(mgmt, list):
                    neighbor["switch_mgmt_ip"] = mgmt[0]
                else:
                    neighbor["switch_mgmt_ip"] = mgmt

            result["neighbors"].append(neighbor)

        result["found"] = len(result["neighbors"]) > 0

    except FileNotFoundError:
        result["error"] = "lldpd/lldpcli nicht installiert (siehe scripts/install.sh)"
    except subprocess.TimeoutExpired:
        result["error"] = "lldpcli Timeout — evtl. läuft lldpd nicht"
    except json.JSONDecodeError:
        result["error"] = "lldpcli Antwort konnte nicht geparst werden"
    return result
