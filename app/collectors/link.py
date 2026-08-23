"""Link-Status via ethtool: Speed, Duplex, Link-Detected."""
import re
import subprocess


def parse_ethtool(text: str) -> dict:
    """Parst die ethtool-Textausgabe (reine Funktion, testbar)."""
    parsed: dict = {"speed": None, "duplex": None, "auto_negotiation": None,
                    "link_detected": None}
    m = re.search(r"Speed:\s*(\S+)", text)
    if m:
        parsed["speed"] = m.group(1)
    m = re.search(r"Duplex:\s*(\S+)", text)
    if m:
        parsed["duplex"] = m.group(1)
    m = re.search(r"Auto-negotiation:\s*(\S+)", text)
    if m:
        parsed["auto_negotiation"] = m.group(1)
    m = re.search(r"Link detected:\s*(\S+)", text)
    if m:
        parsed["link_detected"] = m.group(1) == "yes"
    return parsed


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
        if out.returncode != 0:
            result["error"] = out.stderr.strip() or "ethtool fehlgeschlagen"
            return result
        result.update(parse_ethtool(out.stdout))
    except FileNotFoundError:
        result["error"] = "ethtool nicht installiert"
    except subprocess.TimeoutExpired:
        result["error"] = "ethtool Timeout"
    return result
