"""Durchsatzmessung via iperf3 gegen einen konfigurierten Server (JSON-Modus)."""
import json
import subprocess


def run_iperf(server: str, duration: int = 10) -> dict:
    result = {
        "server": server,
        "mbps_down": None,
        "mbps_up": None,
        "retransmits": None,
        "error": None,
    }
    if not server:
        result["error"] = "Kein iperf-Server konfiguriert (Verwaltung → iperf-Server)"
        return result
    try:
        # Upload-Richtung (Client -> Server)
        up = subprocess.run(
            ["iperf3", "-c", server, "-t", str(duration), "-J"],
            capture_output=True,
            text=True,
            timeout=duration + 15,
        )
        up_data = json.loads(up.stdout or "{}")
        if "error" in up_data:
            result["error"] = up_data["error"]
            return result
        end = up_data.get("end", {})
        sent = end.get("sum_sent", {})
        result["mbps_up"] = round(sent.get("bits_per_second", 0) / 1e6, 1)
        result["retransmits"] = sent.get("retransmits")

        # Download-Richtung (Server -> Client, Reverse-Mode)
        down = subprocess.run(
            ["iperf3", "-c", server, "-t", str(duration), "-J", "-R"],
            capture_output=True,
            text=True,
            timeout=duration + 15,
        )
        down_data = json.loads(down.stdout or "{}")
        if "error" not in down_data:
            recv = down_data.get("end", {}).get("sum_received", {})
            result["mbps_down"] = round(recv.get("bits_per_second", 0) / 1e6, 1)

    except FileNotFoundError:
        result["error"] = "iperf3 nicht installiert (apt install iperf3)"
    except subprocess.TimeoutExpired:
        result["error"] = "iperf3 Timeout — Server erreichbar?"
    except json.JSONDecodeError:
        result["error"] = "iperf3-Ausgabe nicht parsebar"
    return result
