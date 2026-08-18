"""Non-invasive DHCP-Discovery: fragt DHCP-Server ab, ohne einen Lease zu
belegen. Nutzt nmap's broadcast-dhcp-discover Skript.
"""
import re
import subprocess


def discover_dhcp(interface: str) -> dict:
    result = {
        "interface": interface,
        "server_found": False,
        "offered_ip": None,
        "server_identifier": None,
        "subnet_mask": None,
        "router": None,
        "dns_servers": None,
        "lease_time": None,
        "raw": None,
        "error": None,
    }
    try:
        out = subprocess.run(
            ["nmap", "-e", interface, "--script", "broadcast-dhcp-discover"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = out.stdout
        result["raw"] = text

        if "Response 1 of 1" not in text and "IP Offered" not in text:
            result["error"] = "Kein DHCP-Server geantwortet (Timeout oder kein DHCP im Segment)"
            return result

        result["server_found"] = True

        patterns = {
            "offered_ip": r"IP Offered:\s*(\S+)",
            "server_identifier": r"Server Identifier:\s*(\S+)",
            "subnet_mask": r"Subnet Mask:\s*(\S+)",
            "router": r"Router:\s*(\S+)",
            "dns_servers": r"Domain Name Server:\s*(\S+)",
            "lease_time": r"IP Address Lease Time:\s*(.+)",
        }
        for key, pat in patterns.items():
            m = re.search(pat, text)
            if m:
                result[key] = m.group(1).strip()

    except FileNotFoundError:
        result["error"] = "nmap nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "nmap Timeout"
    return result
