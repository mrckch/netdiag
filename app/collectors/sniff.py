"""Passives Mitschneiden von VLAN-Tags, CDP, EAPOL (802.1X) und STP/BPDU.

Braucht CAP_NET_RAW (root oder gesetzte Capability, siehe scripts/install.sh).
"""
from scapy.all import sniff, Dot1Q, Ether
from scapy.contrib.cdp import CDPMsgDeviceID, CDPMsgPortID, CDPMsgMgmtAddr, CDPMsgGeneric

STP_DST_MAC = "01:80:c2:00:00:00"
EAPOL_ETHERTYPE = 0x888E


def sniff_port(interface: str, duration: int = 8) -> dict:
    """Sniff duration Sekunden lang und werte VLAN/CDP/EAPOL/STP aus."""
    result = {
        "interface": interface,
        "duration": duration,
        "vlan_ids_seen": [],
        "eapol_seen": False,
        "stp_seen": False,
        "cdp": None,
        "error": None,
        "packets_captured": 0,
    }

    vlan_ids = set()
    eapol_seen = False
    stp_seen = False
    cdp_info = None
    packet_count = 0

    def handle(pkt):
        nonlocal eapol_seen, stp_seen, cdp_info, packet_count
        packet_count += 1

        if pkt.haslayer(Dot1Q):
            vlan_ids.add(pkt[Dot1Q].vlan)

        if pkt.haslayer(Ether):
            if pkt[Ether].type == EAPOL_ETHERTYPE:
                eapol_seen = True
            if pkt[Ether].dst.lower() == STP_DST_MAC:
                stp_seen = True

        if pkt.haslayer(CDPMsgGeneric) or pkt.haslayer(CDPMsgDeviceID):
            if cdp_info is None:
                cdp_info = {"device_id": None, "port_id": None, "mgmt_ip": None}
            if pkt.haslayer(CDPMsgDeviceID):
                cdp_info["device_id"] = pkt[CDPMsgDeviceID].val.decode(errors="ignore")
            if pkt.haslayer(CDPMsgPortID):
                cdp_info["port_id"] = pkt[CDPMsgPortID].iface.decode(errors="ignore")
            if pkt.haslayer(CDPMsgMgmtAddr):
                try:
                    cdp_info["mgmt_ip"] = pkt[CDPMsgMgmtAddr].addr
                except Exception:
                    pass

    try:
        sniff(iface=interface, timeout=duration, prn=handle, store=False)
    except PermissionError:
        result["error"] = "Keine Berechtigung — Root oder CAP_NET_RAW nötig"
        return result
    except OSError as e:
        result["error"] = f"Sniff-Fehler: {e}"
        return result

    result["packets_captured"] = packet_count
    result["vlan_ids_seen"] = sorted(vlan_ids)
    result["eapol_seen"] = eapol_seen
    result["stp_seen"] = stp_seen
    result["cdp"] = cdp_info
    return result
