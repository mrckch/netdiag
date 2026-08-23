from app.collectors.reach import parse_scan_output

NMAP_SN = """Starting Nmap 7.94 ( https://nmap.org ) at 2026-08-23
Nmap scan report for fritz.box (192.168.10.1)
Host is up (0.0011s latency).
MAC Address: AA:BB:CC:11:22:33 (AVM)
Nmap scan report for 192.168.10.57
Host is up.
Nmap scan report for printer.local (192.168.10.20)
Host is up (0.023s latency).
MAC Address: 00:11:22:33:44:55 (Hewlett Packard)
Nmap done: 256 IP addresses (3 hosts up) scanned in 2.50 seconds
"""


def test_parse_scan():
    hosts = parse_scan_output(NMAP_SN)
    assert len(hosts) == 3
    assert hosts[0] == {"ip": "192.168.10.1", "hostname": "fritz.box",
                        "mac": "AA:BB:CC:11:22:33", "vendor": "AVM"}
    assert hosts[1]["ip"] == "192.168.10.57"
    assert hosts[1]["hostname"] is None
    assert hosts[2]["vendor"] == "Hewlett Packard"


def test_parse_scan_no_ip_does_not_crash():
    # Regression: Report-Zeile ohne IP fuehrte zu AttributeError
    hosts = parse_scan_output("Nmap scan report for weird-host\nHost is up.\n")
    assert hosts[0]["ip"] is None
    assert hosts[0]["hostname"] is None


def test_parse_scan_empty():
    assert parse_scan_output("") == []
