from app.collectors.dhcp import parse_dhcp_output

NMAP_OUT = """Starting Nmap 7.94 ( https://nmap.org )
Pre-scan script results:
| broadcast-dhcp-discover:
|   Response 1 of 1:
|     Interface: enp0s25
|     IP Offered: 192.168.10.57
|     DHCP Message Type: DHCPOFFER
|     Server Identifier: 192.168.10.1
|     IP Address Lease Time: 1d00h00m00s
|     Subnet Mask: 255.255.255.0
|     Router: 192.168.10.1
|_    Domain Name Server: 192.168.10.1
Nmap done: 0 IP addresses (0 hosts up) scanned in 3.21 seconds
"""


def test_parse_offer():
    p = parse_dhcp_output(NMAP_OUT)
    assert p["server_found"] is True
    assert p["offered_ip"] == "192.168.10.57"
    assert p["server_identifier"] == "192.168.10.1"
    assert p["subnet_mask"] == "255.255.255.0"
    assert p["router"] == "192.168.10.1"
    assert p["dns_servers"] == "192.168.10.1"
    assert p["lease_time"] == "1d00h00m00s"


def test_parse_no_answer():
    p = parse_dhcp_output("Starting Nmap...\nNmap done: 0 IP addresses\n")
    assert p["server_found"] is False
