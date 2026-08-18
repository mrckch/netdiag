# netdiag

Lokaler Netzwerk-Port-Tester **und Kabelkataster** für ein Linux-Netbook —
Open-Source-Ersatz für Hardware-Handheld-Tester (Fluke LinkIQ, NetAlly
LinkRunner, Trend NaviTEK) für ~0€ statt ~1000€.

**Läuft komplett lokal, keine Cloud, keine externe Abhängigkeit.**

Anders als die Hardware-Tester speichert netdiag jede Messung dauerhaft und
ordnet sie einer Netzwerkdose (Etage → Raum → Dose) zu — inklusive Historie,
Gerätetyp-Zuordnung, XLSX-Export und SNMP-Rückschreiben der Port-Description
auf den Switch.

## Funktionen

### Messen
| Kategorie   | Methode                                   | Info |
|-------------|--------------------------------------------|------|
| Link        | `ethtool`                                  | Speed, Duplex, Link-Status |
| Switch/Port | LLDP via `lldpd`, CDP via Scapy            | Switch-Name, Port-ID, Management-IP |
| VLAN        | Scapy-Sniff auf 802.1Q-Tags                | Tagged VLAN-IDs auf dem Port |
| 802.1X      | Scapy-Sniff auf EAPOL                      | Ob Port-Authentifizierung verlangt wird |
| Spanning Tree | Scapy-Sniff auf BPDU                     | Ob STP aktiv |
| DHCP        | `nmap --script broadcast-dhcp-discover`    | Angebotene IP, Gateway, DNS (kein Lease belegt) |
| Ping        | ICMP zum Gateway                           | Erreichbarkeit, Latenz |
| Durchsatz   | `iperf3` gegen eigenen Server (beide Richtungen) | Mbit/s Down/Up, Retransmits |
| Netz-Scan   | `nmap -sn`                                 | Aktive Geräte im Segment |

### Kabelkataster
- Etagen → Räume → Dosen anlegen und verwalten
- Jede Messung wird der Dose zugeordnet (oder frei gemessen und nachträglich zugeordnet)
- Komplette Mess-Historie pro Dose mit Änderungs-Hinweis (VLAN/Speed/Switch geändert)
- Gerätetyp pro Dose per Icon-Klick (PC, Beamer, AppleTV, Drucker, AP, … — erweiterbar)

### Integration & Export
- **SNMP-Write (v2c):** Port-Description (`ifAlias`) direkt am Switch setzen —
  Switch und Port kommen aus dem LLDP-Ergebnis, die Description aus einem
  Template (`{raum}-{dose} {geraet}`), mit Vorschau vor dem Schreiben
- **XLSX-Export:** sortiert nach Etage → Raum → Dose, Spalten frei wählbar,
  letzte Messung oder komplette Historie, optionaler Zeitraumfilter
- **DB-Backup/-Restore** direkt aus der UI (SQLite-Snapshot via `VACUUM INTO`,
  Restore mit Schema-Prüfung und automatischer Sicherung der alten DB)

## Nicht möglich ohne Zusatzhardware
- PoE-Spannung/-Klasse (braucht Analogmesstechnik)
- Kabel-TDR / Wire-Mapping (braucht spezielle RJ45-Elektronik)

## Setup (Debian/Ubuntu-basiert)

```bash
sudo bash scripts/install.sh
```

Installiert Abhängigkeiten (lldpd, ethtool, nmap, iperf3, snmp), richtet den
systemd-Service und die udev-Regel (Desktop-Notification bei Link-up) ein.

Dashboard: `http://localhost:8642`

### iperf3-Server (Gegenstelle)

Auf einem Server im Netz (z.B. Docker):
```bash
docker run -d --restart unless-stopped --name iperf3 -p 5201:5201 networkstatic/iperf3 -s
```
Adresse dann in netdiag unter Verwaltung → iperf3-Server eintragen.

### SNMP

In der Verwaltung die v2c-Write-Community hinterlegen. Auf den Switches muss
SNMP-Write aktiviert sein. Hinweis: v2c überträgt die Community im Klartext —
idealerweise nur im Management-VLAN nutzen.

## Manueller Start (Entwicklung)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo .venv/bin/python -m app.main   # sudo für raw sockets (Scapy) & nmap
```

## Architektur

```
app/main.py           FastAPI: Mess-, Kataster-, Export-, SNMP-, DB-API
app/db.py             SQLite-Schema (floors/rooms/outlets/measurements/settings)
app/collectors/*.py   Ein Modul pro Datenquelle (link, lldp, sniff, dhcp, reach, iperf, snmp)
app/export_xlsx.py    XLSX-Export (openpyxl)
app/static/           Vanilla JS/HTML Dashboard, 3 Bereiche: Messen/Kataster/Verwaltung
data/netdiag.db       SQLite-Datenbank (wird beim ersten Start angelegt)
udev/, systemd/       Auto-Notification bei Link-up, Autostart
```

Details und Designentscheidungen: `docs/KONZEPT.md`

## Lizenz

MIT
