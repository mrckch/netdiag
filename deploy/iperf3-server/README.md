# iperf3-Gegenstelle für netdiag

> **Status: zurückgestellt (2026-08-24).** Der Server läuft auf DockerVM1 und deckt
> drei VLANs ab; der Ausbau auf alle VLANs (Trunk-Port, Patchen, Proxmox-Bridge)
> wird vorerst nicht verfolgt. Alles hier ist einsatzbereit dokumentiert, damit es
> beim Wiederaufgreifen nur noch abgearbeitet werden muss.

netdiag misst den Durchsatz an der Dose mit `iperf3` gegen einen festen Server.
Ohne diese Gegenstelle bleibt die Spalte „Durchsatz" leer.

Aufgestellt auf **DockerVM1 (Schule)** — dort läuft bereits der NetzwerkMonitor-Agent,
die VM hängt an mehreren Netzen und ist per Tailscale administrierbar.

## Betrieb

```bash
cd /home/docker/iperf3-server
docker compose up -d --build
docker compose logs -f
```

Prüfen (von irgendwo im selben Netz):

```bash
iperf3 -c <IP> -p 5201 -t 5
```

In netdiag: *Verwaltung → iperf-Server* auf die passende IP setzen.

## Erreichbarkeit — der eigentliche Knackpunkt

Der Tester steckt beim Messen in einer **beliebigen Dose**, also in einem beliebigen
VLAN. Der iperf3-Server muss aus genau diesem VLAN erreichbar sein. Zwei Wege:

1. **Routing** — ein L3-Gateway routet zwischen den VLANs. Dann genügt **eine** IP.
   *Stand 2026-08-24: nicht gegeben* (Gegenprobe von DockerVM1 aus: keine Antwort
   von den Gateways der übrigen VLANs).
2. **Server steht selbst in jedem VLAN** — ein Trunk-Port zum Host, dort je VLAN
   ein Subinterface mit eigener IP. Das ist der Weg, der hier verfolgt wird.

`network_mode: host` sorgt dafür, dass der Container jedes neue Subinterface
automatisch mitbedient — der iperf3-Server bindet auf `0.0.0.0:5201`.

### Ist-Stand DockerVM1 (Schule)

| Interface | Netz | VLAN | Switchport |
|---|---|---|---|
| `ens18` | 192.168.200.145/24 | 200 (Verwaltung) | Switch-Verwaltung-Server, Port 11 (`PVE1-eno1-Verwaltung-Uplink`) |
| `ens19` | 10.255.242.69/8 | 1001 (IServ) | Switch-Verwaltung-Server, Port 15 (`PVE1-eno3-IServ-Uplink`) |
| `ens20` | 192.168.150.134/24 | 1 (Management, untagged) | Switch-Verwaltung-Server, Port 13 (`PVE1-eno2-Man-Uplink`) |

PVE1 nutzt also **drei getrennte Access-Ports**, keinen Trunk. Damit ist der
iperf3-Server heute in drei von zehn VLANs erreichbar.

### Ausbau auf alle VLANs

VLANs laut Registry der Zentrale:
`2 (Transfer)`, `120 (Telefon)`, `130 (GManage)`, `140 (Gaeste)`, `148 (Beamer)`,
`149 (APs)`, `200 (Verwaltung)`, `201 (Verwaltung2)`, `1001 (IServ)`, `1100 (EndoLAN)`.

**Variante A — freier Port + freie NIC (empfohlen, risikoarm)**

1. Freien Port auf `Switch-Verwaltung-Server` (192.168.150.92) als **hybrid** setzen
   und alle zehn VLANs **tagged** aufnehmen. Frei sind u. a. 23–45, 49, 50.
2. Freie NIC von PVE1 dorthin patchen.
3. In Proxmox eine **VLAN-aware Bridge** auf dieser NIC anlegen, DockerVM1 eine
   zusätzliche vNIC daran geben.
4. Im Gast Subinterfaces je VLAN anlegen (`vlan-interfaces.example`).

Vorteil: kein Eingriff an einem produktiven Uplink. Nachteil: einmal patchen.

**Variante B — bestehenden Uplink zum Trunk machen (ohne Patcharbeit)**

Port 11 (Verwaltung-Uplink) auf **hybrid** umstellen, PVID 200 untagged behalten,
alle übrigen VLANs tagged ergänzen; Bridge in PVE1 VLAN-aware machen.

⚠ Das ist der produktive Uplink der Verwaltungs-VMs. Ein Fehler beim Umstellen
(z. B. `frame-type` falsch) trennt die VMs vom Netz — dann hilft nur noch Konsole
am Proxmox. Nur mit Wartungsfenster.

### Subinterfaces im Gast

`vlan-interfaces.example` enthält die fertige `ifupdown`-Konfiguration
(`/etc/network/interfaces.d/vlans`). Zwei Details, die sonst weh tun:

- **`post-up ip route del default`** je Subinterface — sonst kippen zehn zusätzliche
  DHCP-Default-Routen die Routingtabelle der VM.
- **`rp_filter=2`** (loose) — bei vielen Interfaces in vielen Subnetzen verwirft der
  strikte Reverse-Path-Filter sonst gültige Antworten.

Ohne DHCP im jeweiligen VLAN stattdessen feste IPs eintragen (keine Gateways setzen).

## Sicherheit

iperf3 läuft **ohne Authentifizierung** — jeder im Netz kann Last erzeugen. Das ist
für ein Messwerkzeug im internen Netz vertretbar; der Container läuft als `nobody`
und der Dienst kann nichts außer Traffic senden/empfangen. Wer es enger will:
`--rsa-private-key-path` + `--authorized-users-path` (iperf3 ≥ 3.7).
