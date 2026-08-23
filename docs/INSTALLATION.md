# Installation

Diese Anleitung richtet netdiag auf einem dedizierten Linux-Netbook ein,
das als Diagnosegerät durchs Gebäude getragen und an Netzwerkdosen
gesteckt wird.

## Voraussetzungen

- **Betriebssystem:** Debian oder Ubuntu (getestet mit Debian 12/13 und
  Ubuntu 22.04/24.04). Andere Distributionen funktionieren nur mit
  angepasstem `scripts/install.sh` (andere Paketnamen).
- **Hardware:** ein Laptop/Netbook mit mindestens einem Ethernet-Port
  (RJ45, ggf. per USB-Adapter). WLAN-Interfaces werden von netdiag
  ignoriert — Messen findet ausschließlich über LAN statt.
- **Root-Zugriff** (sudo) für die Installation. Der netdiag-Dienst läuft
  selbst dauerhaft als root, weil Paket-Sniffing (Scapy) und `nmap`
  Raw-Sockets brauchen (`CAP_NET_RAW`). Das ist für ein dediziertes
  Diagnosegerät ein akzeptabler Kompromiss (siehe [CLAUDE.md](../CLAUDE.md)),
  aber kein Gerät, das man produktiv als Server oder für andere Zwecke
  mitnutzen sollte.
- **Internetzugang** während der Installation (zum Herunterladen der
  Pakete). Danach läuft netdiag komplett offline.

## 1. Repository klonen

```bash
git clone https://github.com/mrckch/netdiag.git
cd netdiag
```

## 2. Installationsskript ausführen

```bash
sudo bash scripts/install.sh
```

Das Skript:

1. installiert die Systempakete `lldpd`, `ethtool`, `nmap`, `iperf3`,
   `snmp` (net-snmp CLI-Tools), `python3-venv`, `python3-pip`,
   `libnotify-bin`
2. aktiviert und startet den `lldpd`-Dienst (nötig für Switch-Erkennung)
3. kopiert das Projekt nach `/opt/netdiag` (per `rsync`, `.venv`,
   `__pycache__`, `.git` und ein vorhandenes `data/`-Verzeichnis werden
   dabei ausgeschlossen — die Datenbank bleibt bei einem erneuten Lauf
   unangetastet)
4. legt unter `/opt/netdiag/.venv` eine Python-virtualenv an und
   installiert die Abhängigkeiten aus `requirements.txt`
5. richtet den systemd-Service `netdiag.service` ein und startet ihn
6. richtet die udev-Regel ein, die bei Link-up eine Desktop-Notification
   auslöst

Am Ende meldet das Skript:

```
Fertig. Dashboard: http://localhost:8642
Status prüfen:     systemctl status netdiag
Health-Check:      curl -s localhost:8642/api/health
```

## 3. Installation prüfen

```bash
systemctl status netdiag
curl -s localhost:8642/api/health
```

Die Health-Antwort sollte etwa so aussehen:

```json
{"status": "ok", "version": "3.1.0", "schema_version": 2}
```

Das Dashboard ist dann unter `http://localhost:8642` erreichbar — am
einfachsten direkt am Gerät im Browser öffnen.

**Wichtig:** Das Dashboard lauscht standardmäßig **nur auf `localhost`**.
Das ist Absicht — die API hat keine Authentifizierung und kann über den
Port-Aktionen-Tab Schreibzugriffe auf Switches auslösen. Für Fernzugriff
siehe Abschnitt [Fernzugriff aktivieren](#fernzugriff-aktivieren-optional).

## 4. iperf3-Gegenstelle einrichten (optional, für Durchsatzmessung)

netdiag misst Durchsatz als **Client** gegen einen iperf3-**Server**, der
irgendwo im Netz erreichbar sein muss (nicht auf dem netdiag-Gerät selbst).

Am einfachsten als Docker-Container auf einem beliebigen Server:

```bash
docker run -d --restart unless-stopped --name iperf3 -p 5201:5201 \
  networkstatic/iperf3 -s
```

Die Adresse dieses Servers danach im Dashboard unter **Verwaltung →
iperf3-Server** eintragen.

## 5. SNMP-Write einrichten (optional, für Port-Aktionen)

Für die Funktionen im Tab **PORT-AKTIONEN** (Port-Description und
VLAN setzen) muss SNMP-Write auf den betroffenen Switches aktiviert
sein und eine v2c-Community mit Schreibrechten konfiguriert werden.
Diese Community wird im Dashboard unter **Verwaltung → SNMP Community
(v2c, write)** hinterlegt.

**Sicherheitshinweis:** SNMP v2c überträgt die Community **im
Klartext**. Nur in einem abgeschotteten Management-VLAN einsetzen, nicht
über ein offenes oder gemeinsam genutztes Netz. Details zur
VLAN-Write-Funktion (experimentell, MIB-Umsetzung variiert je nach
Switch-Modell) siehe [Benutzerhandbuch](BENUTZERHANDBUCH.md#port-aktionen).

## Update

Sobald eine neue Version im Repository verfügbar ist:

```bash
cd ~/netdiag        # oder wo auch immer geklont wurde
git pull
sudo bash scripts/install.sh
```

Das Skript ist **idempotent** und für genau diesen Zweck gebaut: Es
kopiert den neuen Stand nach `/opt/netdiag`, lässt aber
`/opt/netdiag/data/` (die SQLite-Datenbank) unberührt, und startet den
Dienst am Ende neu. Bestehende Messungen und Stammdaten gehen dabei
nicht verloren.

Vor einem größeren Update empfiehlt sich trotzdem ein manuelles Backup
über das Dashboard (**Verwaltung → Datenbank → Backup herunterladen**)
oder direkt per Dateikopie:

```bash
sudo cp /opt/netdiag/data/netdiag.db ~/netdiag-backup-$(date +%Y%m%d).db
```

## Fernzugriff aktivieren (optional)

Standardmäßig ist das Dashboard nur vom Gerät selbst aus erreichbar.
Um es z. B. aus dem Management-VLAN heraus erreichbar zu machen:

```bash
sudo systemctl edit netdiag
```

Im sich öffnenden Editor folgenden Override einfügen:

```ini
[Service]
Environment=NETDIAG_HOST=0.0.0.0
```

Danach:

```bash
sudo systemctl restart netdiag
```

**Vor dem Aktivieren beachten:** Die API hat keine Authentifizierung.
Jeder mit Netzwerkzugriff auf den konfigurierten Host/Port kann Messungen
auslösen, den Kabelkataster einsehen/ändern und — sofern eine
SNMP-Write-Community hinterlegt ist — Switch-Ports umkonfigurieren.
Nur in einem vertrauenswürdigen, abgeschotteten Netzsegment freigeben.

## Manueller Start (Entwicklung, ohne systemd)

Für Entwicklung oder um netdiag ohne Installation nach `/opt/netdiag`
direkt aus dem geklonten Repo zu starten:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo .venv/bin/python -m app.main   # sudo für Raw Sockets (Scapy) & nmap
```

Relevante Umgebungsvariablen:

| Variable | Default | Zweck |
|---|---|---|
| `NETDIAG_HOST` | `127.0.0.1` | Bind-Adresse des Webservers |
| `NETDIAG_PORT` | `8642` | Bind-Port |
| `NETDIAG_DATA_DIR` | `<Projektverzeichnis>/data` | Ort der SQLite-Datenbank |

## Deinstallation

```bash
sudo systemctl disable --now netdiag
sudo rm /etc/systemd/system/netdiag.service
sudo rm /etc/udev/rules.d/99-netdiag-trigger.rules
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo rm -rf /opt/netdiag
```

Die Systempakete (`lldpd`, `ethtool`, `nmap`, `iperf3`, `snmp`) werden
dabei nicht entfernt, da sie auch für andere Zwecke nützlich sein können.
Bei Bedarf zusätzlich: `sudo apt remove lldpd ethtool nmap iperf3 snmp`.

## Bei Problemen

Siehe [Troubleshooting](TROUBLESHOOTING.md) für Lösungen zu häufigen
Installations- und Betriebsproblemen.
