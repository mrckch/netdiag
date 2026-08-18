"""Erreichbarkeit: Ping-Test und optionaler Netzwerk-Scan (nmap -sn)."""
import re
import subprocess


def ping_test(target: str, count: int = 4) -> dict:
    result = {"target": target, "reachable": False, "avg_ms": None, "raw": None, "error": None}
    try:
        out = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", target],
            capture_output=True,
            text=True,
            timeout=count * 2 + 5,
        )
        result["raw"] = out.stdout
        result["reachable"] = out.returncode == 0
        m = re.search(r"= [\d.]+/([\d.]+)/", out.stdout)
        if m:
            result["avg_ms"] = float(m.group(1))
    except subprocess.TimeoutExpired:
        result["error"] = "Ping Timeout"
    except FileNotFoundError:
        result["error"] = "ping nicht gefunden"
    return result


def scan_subnet(subnet: str) -> dict:
    """z.B. subnet='192.168.1.0/24'. Kann einige Sekunden dauern."""
    result = {"subnet": subnet, "hosts": [], "error": None}
    try:
        out = subprocess.run(
            ["nmap", "-sn", subnet], capture_output=True, text=True, timeout=60
        )
        blocks = out.stdout.split("Nmap scan report for ")[1:]
        for block in blocks:
            first_line = block.splitlines()[0]
            ip_match = re.search(r"\(?([\d.]+)\)?$", first_line)
            hostname = first_line.split(" (")[0] if " (" in first_line else None
            mac_match = re.search(r"MAC Address:\s*([0-9A-Fa-f:]+)\s*(\((.+)\))?", block)
            result["hosts"].append(
                {
                    "ip": ip_match.group(1) if ip_match else None,
                    "hostname": hostname if hostname and hostname != ip_match.group(1) else None,
                    "mac": mac_match.group(1) if mac_match else None,
                    "vendor": mac_match.group(3) if mac_match and mac_match.group(3) else None,
                }
            )
    except FileNotFoundError:
        result["error"] = "nmap nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "Scan Timeout"
    return result
