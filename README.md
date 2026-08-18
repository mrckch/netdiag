# netdiag

Lokaler Netzwerk-Port-Tester für ein Linux-Netbook — Open-Source-Ersatz für
Hardware-Handheld-Tester (Fluke LinkIQ, NetAlly LinkRunner, Trend NaviTEK) für
~0€ statt ~1000€.

**Läuft komplett lokal, keine Cloud, keine externe Abhängigkeit.**

## Was es kann

| Kategorie   | Methode                                   | Info |
|-------------|--------------------------------------------|------|
| Link        | `ethtool`                                  | Speed, Duplex, Link-Status |
| Switch/Port | LLDP via `lldpd`/`lldpcli`, CDP via Scapy  | Switch-Name, Port-ID, Management-IP |
| VLAN        | Scapy-Sniff auf 802.1Q-Tags                | Tagged VLAN-IDs auf dem Port |
| 802.1X      | Scapy-Sniff auf EAPOL                      | Ob Port-Authentifizierung verlangt wird |
| Spanning Tree | Scapy-Sniff auf BPDU (01:80:C2:00:00:00) | Root Bridge, ob STP aktiv |
| DHCP        | `nmap --script broadcast-dhcp-discover`    | Angebotene IP, Gateway, DNS (non-invasiv, kein Lease) |
| Ping        | ICMP zu Gateway/Internet                   | Erreichbarkeit, Latenz |
| Netz-Scan   | `nmap -sn`                                 | Aktive Geräte im Segment |

## Nicht möglich ohne Zusatzhardware
- PoE-Spannung/-Klasse (braucht Analogmesstechnik)
- Kabel-TDR / Wire-Mapping (braucht spezielle RJ45-Elektronik)

## Setup (Debian/Ubuntu-basiert)

```bash
sudo bash scripts/install.sh
```

Das Skript installiert Abhängigkeiten, richtet `lldpd`, den systemd-Service
und die udev-Regel für Auto-Trigger bei Link-up ein.

Danach ist das Dashboard erreichbar unter: `http://localhost:8642`

## Manueller Start (Entwicklung)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo .venv/bin/python -m app.main   # sudo nötig für raw sockets (Scapy) & nmap
```

## Warum root/sudo?

Scapy-Sniffing (VLAN-Tags, EAPOL, BPDU) und `nmap`-Discovery brauchen
CAP_NET_RAW. Für ein dediziertes Diagnose-Netbook ist ein root-Service
pragmatisch (YAGNI) — alternativ lässt sich das via
`setcap cap_net_raw,cap_net_admin=eip` auf das Python-Binary einschränken,
siehe `scripts/install.sh`.

## Architektur

```
app/main.py          FastAPI-App, orchestriert alle Collectors
app/collectors/*.py   Ein Modul pro Datenquelle (ethtool, lldp, vlan, dhcp, scan)
app/static/           Vanilla JS/HTML Dashboard (Autotest-Style wie LinkIQ)
udev/                 Regel: bei Link-up automatisch Test antriggern
systemd/              Service-Unit für Autostart auf dem Netbook
```

## Lizenz

MIT
