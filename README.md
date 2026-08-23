# netdiag

![CI](https://github.com/mrckch/netdiag/actions/workflows/ci.yml/badge.svg)

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

### Schnelltest-Workflow (v3)
Messen und Speichern sind getrennt: Autotest/iperf laufen zunächst ohne
DB-Eintrag (Aufräum-Modus). Erst der Speichern-Klick — mit sticky
vorausgewählter Etage/Raum/Dose als Ein-Klick — legt die Messung ab.
Messen ist nur über LAN-Interfaces möglich (WLAN wird ausgefiltert).

### Kabelkataster
- Etagen → Räume → Dosen anlegen und verwalten
- **Patchfeld-Name und -Port pro Dose** — dokumentiert die komplette Strecke
  Dose → Patchfeld → Switch (Switch+Port kommen automatisch aus LLDP/CDP)
- Komplette Mess-Historie pro Dose mit Änderungs-Hinweis (VLAN/Speed/Switch geändert)
- Gerätetyp pro Dose per Icon-Klick (PC, Beamer, AppleTV, Drucker, AP, … — erweiterbar)
- Nachträgliches Zuordnen frei gespeicherter Messungen

### Integration & Export
- **Port-Aktionen (SNMP v2c),** strikt gebunden an den zuletzt gemessenen Port:
  - **Description setzen** (`ifAlias`) — Vorschlag aus Template
    (`{raum}-{dose} {geraet}`), Vorschau vor dem Schreiben
  - **VLAN setzen** (PVID + tagged VLANs via Q-BRIDGE-MIB) — mit
    Zustandsanzeige, Diff und doppelter Bestätigung. **Experimentell:**
    vor produktivem Einsatz gegen die konkreten Switch-Modelle verifizieren
- **XLSX-Export:** sortiert nach Etage → Raum → Dose, Spalten frei wählbar,
  letzte Messung oder komplette Historie, optionaler Zeitraumfilter
- **DB-Backup/-Restore** direkt aus der UI (SQLite-Snapshot via `VACUUM INTO`,
  Restore mit Schema-Prüfung und automatischer Sicherung der alten DB)

## Nicht möglich ohne Zusatzhardware
- PoE-Spannung/-Klasse (braucht Analogmesstechnik)
- Kabel-TDR / Wire-Mapping (braucht spezielle RJ45-Elektronik)

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Setup, Update, Fernzugriff, Deinstallation |
| [docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md) | Bedienung aller vier Bereiche (Messen/Kataster/Port-Aktionen/Verwaltung) |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Lösungen zu allen im Dashboard sichtbaren Fehlermeldungen |
| [docs/KONZEPT-v3.md](docs/KONZEPT-v3.md) | Designentscheidungen und Domänenmodell |

Alle drei Bedienungs-Dokumente gibt es auch als ein zusammenhängendes
[PDF](docs/netdiag-dokumentation.pdf) (Titelseite, Inhaltsverzeichnis,
klickbare interne Links) — praktisch zum Ausdrucken oder Offline-Lesen.
Neu erzeugen nach Änderungen an den `.md`-Dateien:

```bash
pip install -r requirements-dev.txt
python scripts/build_docs_pdf.py
```

## Schnellstart (Debian/Ubuntu-basiert)

```bash
git clone https://github.com/mrckch/netdiag.git
cd netdiag
sudo bash scripts/install.sh
```

Dashboard danach: `http://localhost:8642` (standardmäßig nur lokal
erreichbar — Details und Fernzugriff siehe
[Installation](docs/INSTALLATION.md)).

**Update** auf einem bereits installierten Gerät:

```bash
cd netdiag && git pull && sudo bash scripts/install.sh
```

## Manueller Start (Entwicklung)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo .venv/bin/python -m app.main   # sudo für raw sockets (Scapy) & nmap
```

Umgebungsvariablen: `NETDIAG_HOST` (Default `127.0.0.1`), `NETDIAG_PORT`
(Default `8642`), `NETDIAG_DATA_DIR` (Default `data/` im Projekt).

### Tests

```bash
pip install -r requirements-dev.txt
ruff check app tests
pytest
```

Die Tests decken die reinen Parser (ethtool/LLDP/DHCP/nmap), die
Q-BRIDGE-Bitmap-Logik, das DB-Schema inkl. Migration und die API ab —
läuft ohne Root und ohne Netzwerk, auch in CI.

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

Details und Designentscheidungen: [docs/KONZEPT-v3.md](docs/KONZEPT-v3.md)
(ersetzt/ergänzt die ältere [docs/KONZEPT.md](docs/KONZEPT.md))

## Lizenz

MIT
