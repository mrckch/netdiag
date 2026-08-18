"""Link-Status via ethtool: Speed, Duplex, Link-Detected."""
import re
import subprocess


def get_link_info(interface: str) -> dict:
    result = {
        "interface": interface,
        "link_detected": None,
        "speed": None,
        "duplex": None,
        "auto_negotiation": None,
        "error": None,
    }
    try:
        out = subprocess.run(
            ["ethtool", interface], capture_output=True, text=True, timeout=5
        )
        text = out.stdout
        if out.returncode != 0:
            result["error"] = out.stderr.strip() or "ethtool fehlgeschlagen"
            return result

        m = re.search(r"Speed:\s*(\S+)", text)
        if m:
            result["speed"] = m.group(1)

        m = re.search(r"Duplex:\s*(\S+)", text)
        if m:
            result["duplex"] = m.group(1)

        m = re.search(r"Auto-negotiation:\s*(\S+)", text)
        if m:
            result["auto_negotiation"] = m.group(1)

        m = re.search(r"Link detected:\s*(\S+)", text)
        if m:
            result["link_detected"] = m.group(1) == "yes"

    except FileNotFoundError:
        result["error"] = "ethtool nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "ethtool Timeout"
    return result
