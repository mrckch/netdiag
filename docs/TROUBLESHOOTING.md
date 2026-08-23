# Troubleshooting

Lösungen zu Fehlermeldungen und Problemen, sortiert nach Bereich. Die
Fehlertexte hier entsprechen wörtlich dem, was im Dashboard angezeigt
wird — am schnellsten per Suche (Strg+F) finden.

## Installation & Dienst

### `systemctl status netdiag` zeigt „failed" oder „inactive"

```bash
journalctl -u netdiag -n 50 --no-pager
```

Häufigste Ursachen:
- Port 8642 bereits belegt (anderer Dienst) — `NETDIAG_PORT` per
  `sudo systemctl edit netdiag` umstellen.
- `data/`-Verzeichnis unter `/opt/netdiag` nicht beschreibbar (nach
  manuellem Kopieren mit falschen Rechten entstanden) —
  `sudo chown -R root:root /opt/netdiag/data`.
- Python-Abhängigkeiten fehlen, weil die virtualenv unvollständig
  angelegt wurde — `sudo bash scripts/install.sh` erneut ausführen.

### `curl -s localhost:8642/api/health` liefert keine Antwort

Dienst läuft nicht oder lauscht auf einer anderen Adresse/Port. Prüfen:

```bash
sudo systemctl status netdiag
sudo ss -tlnp | grep 8642
```

Falls `NETDIAG_HOST` per Override auf eine andere Adresse gesetzt wurde
(siehe [Installation → Fernzugriff](INSTALLATION.md#fernzugriff-aktivieren-optional)),
muss diese Adresse statt `localhost` verwendet werden.

### Nach `git pull && sudo bash scripts/install.sh` sind alte Daten weg

Sollte nicht passieren — `install.sh` schließt `data/` beim rsync
ausdrücklich aus. Falls doch: die automatische Sicherung der DB (siehe
unten) oder ein zuvor gezogenes Backup (`Verwaltung → Datenbank`)
verwenden. Zur Kontrolle nach jedem Update:

```bash
ls -la /opt/netdiag/data/
```

## Kein LAN-Interface im Dropdown wählbar

`/api/interfaces` liefert nur Interfaces, die unter
`/sys/class/net/<iface>/device` existieren (echte Hardware) und **kein**
`wireless`-Unterverzeichnis haben. Prüfen:

```bash
ls /sys/class/net/
```

USB-Ethernet-Adapter werden normalerweise automatisch erkannt, sobald
der passende Kernel-Treiber geladen ist (`dmesg | tail` nach dem
Einstecken prüfen).

## „LINK" — ethtool-Fehler

| Meldung | Ursache / Lösung |
|---|---|
| `ethtool nicht installiert` | `sudo apt install ethtool` (sollte bereits durch `install.sh` erledigt sein) |
| `ethtool Timeout` | Interface reagiert nicht — Kabel/Adapter prüfen |
| `ethtool fehlgeschlagen` (mit Zusatztext) | Der Zusatztext ist `ethtool`s eigene Fehlermeldung — meist ein falscher Interface-Name oder das Interface existiert nicht mehr (USB-Adapter gezogen) |

## „SWITCH (LLDP/CDP)" — kein Nachbar erkannt

| Meldung | Ursache / Lösung |
|---|---|
| `lldpd/lldpcli nicht installiert` | `sudo apt install lldpd`, danach `sudo systemctl enable --now lldpd` |
| `lldpcli Timeout — evtl. läuft lldpd nicht` | `sudo systemctl status lldpd` prüfen, ggf. `sudo systemctl restart lldpd` |
| `lldpcli Antwort konnte nicht geparst werden` | Ungewöhnliche `lldpd`-Version — `lldpcli -f json0 show neighbors details` manuell ausführen und Ausgabe prüfen |
| kein Fehler, aber „kein Nachbar erkannt" | Der Switch sendet kein LLDP (bei vielen Consumer-/Billig-Switches normal, oder LLDP ist am konkreten Port deaktiviert — siehe unten). CDP wird zusätzlich passiv mitgelesen (nur bei Cisco-Geräten, die CDP senden) — sonst bleibt der Switch für netdiag unsichtbar. |

LLDP braucht typischerweise **mehrere Sekunden**, bis der Switch sein
erstes LLDP-Paket sendet (Standardintervall oft 30s) — ein Autotest
direkt nach dem Einstecken kann den Nachbarn verpassen. Bei Bedarf den
Autotest einfach wiederholen.

### LLDP global aktiv, aber trotzdem kein Nachbar (z. B. D-Link DGS-1210-Serie)

Bei manchen Switches (bestätigt am D-Link DGS-1210-24) reicht der globale
LLDP-Schalter nicht — es gibt zusätzlich eine **Pro-Port-Einstellung**
(im D-Link-Webinterface unter *L2 Features → LLDP → LLDP Port Settings*),
die je Port auf `Disable`, `TX Only`, `RX Only` oder `TX_and_RX` steht.
Steht der Port, an dem netdiag angeschlossen ist, auf `Disable` oder
`RX Only`, sendet der Switch auf genau diesem Port kein LLDP — selbst
wenn LLDP global aktiv ist. Lösung: den Port im Switch-Webinterface
auf `TX_and_RX` (oder mindestens `TX Only`) stellen.

Diagnose zur Eingrenzung, ob es am Switch oder an `lldpd` liegt:

```bash
sudo lldpcli show neighbors details   # direkt gegen lldpd, ohne netdiag
sudo timeout 40 tcpdump -i <interface> -n ether proto 0x88cc   # kommen ueberhaupt Pakete an?
```

Zeigt `lldpcli` nichts und `tcpdump` auch nicht: Switch sendet nicht
(Port-Einstellung wie oben prüfen). Zeigt `tcpdump` Pakete, aber
`lldpcli` nichts: Problem liegt bei `lldpd` selbst — Interface in
`/etc/lldpd.conf` prüfen bzw. `sudo systemctl restart lldpd`.

## „VLAN / 802.1X / STP" — Sniff-Fehler

| Meldung | Ursache / Lösung |
|---|---|
| `Keine Berechtigung — Root oder CAP_NET_RAW nötig` | netdiag läuft nicht mit ausreichenden Rechten. Bei systemd-Betrieb (`User=root` in der Unit) sollte das nicht auftreten — bei manuellem Start `sudo` verwenden |
| `Sniff-Fehler: ...` | Interface im Sniff-Moment nicht mehr vorhanden (z. B. USB-Adapter während der Messung gezogen) |
| keine VLAN-Tags erkannt, obwohl der Port getaggt sein sollte | Sniff-Dauer (Standard 6s) reicht nicht, um ein Paket mit dem Tag mitzubekommen — Dauer über den Query-Parameter `sniff_seconds` erhöhen (`/api/autotest?...&sniff_seconds=15`), oder erneut testen |

## „DHCP" — kein Server geantwortet

| Meldung | Ursache / Lösung |
|---|---|
| `nmap nicht installiert` | `sudo apt install nmap` |
| `nmap Timeout` | Selten — `nmap`-Skript selbst hat ein internes Timeout von einigen Sekunden |
| `Kein DHCP-Server geantwortet (Timeout oder kein DHCP im Segment)` | Entweder ist im angeschlossenen VLAN/Segment tatsächlich kein DHCP-Server aktiv, oder der Port ist noch nicht im richtigen VLAN (z. B. wartet auf 802.1X-Authentifizierung, siehe VLAN-Karte) |

Der DHCP-Discover-Test **belegt keinen Lease** — beliebig wiederholbar.

## „DURCHSATZ (iperf3)"

| Meldung | Ursache / Lösung |
|---|---|
| `Kein iperf-Server konfiguriert (Verwaltung → iperf-Server)` | Server-Adresse unter Verwaltung eintragen |
| `iperf3 nicht installiert` | `sudo apt install iperf3` |
| `iperf3 Timeout — Server erreichbar?` | Server per `ping <adresse>` und `nc -zv <adresse> 5201` prüfen; ggf. Firewall auf dem Server-Host |
| `iperf3-Ausgabe nicht parsebar` | Unerwartetes iperf3-Ausgabeformat, z. B. sehr alte/neue iperf3-Version auf einer der beiden Seiten — Versionen abgleichen (`iperf3 --version`) |

## Port-Aktionen / SNMP

| Meldung | Ursache / Lösung |
|---|---|
| `Keine SNMP-Community konfiguriert` | Community unter Verwaltung eintragen (write-fähige v2c-Community) |
| `SNMP-Walk lieferte nichts — Community/Erreichbarkeit prüfen` | Community falsch, SNMP auf dem Switch nicht aktiv, oder ACL/Firewall blockiert den Zugriff von diesem Gerät aus. Manuell testen: `snmpwalk -v2c -c <community> <switch-ip> 1.3.6.1.2.1.31.1.1.1.1` |
| `snmpwalk nicht installiert` / `snmpset nicht installiert` | `sudo apt install snmp` |
| `SNMP Timeout` | Switch nicht erreichbar (falsches Management-VLAN/IP) oder Firewall blockiert UDP/161 |
| `Port 'X' nicht in ifName/ifDescr gefunden` | Der von LLDP/CDP gemeldete Port-Name entspricht keinem `ifName`/`ifDescr`-Wert am Switch — je nach Hersteller unterschiedliche Formate (z. B. `24` vs. `GigabitEthernet1/0/24`). Betrifft vor allem Switches, deren SNMP-Agent andere Namenskonventionen nutzt als LLDP |
| `Port-Name nicht eindeutig — bitte Kandidat wählen` | Mehrere Interfaces am Switch matchen den Teilstring — aktuell muss dieser Fall in den Server-Logs (`journalctl -u netdiag`) nachvollzogen und ggf. der SNMP-Description-Vorschlag manuell korrigiert werden |
| `BasePort zu ifIndex nicht gefunden (Bridge-MIB nicht verfügbar?)` | Nur bei VLAN-Zustand/-Write: Der Switch unterstützt die BRIDGE-MIB (`dot1dBasePortIfIndex`) nicht oder nicht in der erwarteten Form — VLAN-Write ist laut README **experimentell** und modellabhängig; vor dem produktiven Einsatz gegen die konkrete Switch-Firmware verifizieren |
| VLAN-Write schlägt mit `Egress-Write VLAN X fehlgeschlagen` o. ä. fehl | Die Q-BRIDGE-MIB-Umsetzung des Switches weicht ab (siehe README-Hinweis „experimentell, vor produktivem Einsatz verifizieren"). Betroffenes VLAN existiert eventuell nicht auf dem Switch, oder die MIB ist read-only für diesen Bereich |
| Port-Fehlerstatistik: einzelner Zähler zeigt dauerhaft „nicht verfügbar" | Der Switch unterstützt diese konkrete EtherLike-MIB-OID nicht vollständig — betrifft meist Symbol-Fehler auf älteren/günstigeren Switches. Die generischen `if_in_errors`/`if_out_errors` (IF-MIB) sind praktisch immer verfügbar und bleiben als Fallback nutzbar |
| Port-Fehlerstatistik: alle Zähler zeigen „nicht verfügbar", Fehlermeldung „Switch liefert keine Fehlerzähler" | Community falsch, ifIndex falsch aufgelöst, oder der Switch unterstützt weder IF-MIB- noch EtherLike-MIB-Zähler für diesen Port — mit `snmpget -v2c -c <community> <switch-ip> 1.3.6.1.2.1.2.2.1.14.<ifindex>` (ifInErrors) manuell gegenprüfen |

**Sicherheitshinweis:** SNMP v2c überträgt die Community im Klartext.
Diese Funktionen nur in einem abgeschotteten Management-VLAN einsetzen.

## Dashboard von einem anderen Gerät nicht erreichbar

Standardmäßig gewollt — netdiag bindet nur auf `localhost`. Siehe
[Installation → Fernzugriff aktivieren](INSTALLATION.md#fernzugriff-aktivieren-optional).

## Datenbank-Wiederherstellung schlägt fehl

| Meldung | Ursache / Lösung |
|---|---|
| `Datei ist keine gültige SQLite-Datenbank` | Die hochgeladene Datei ist beschädigt oder kein SQLite-Format — mit einem bekannten Backup erneut versuchen |
| `Datenbank hat nicht das netdiag-Schema` | Falsche Datei hochgeladen (nicht von netdiag erzeugt) |
| `Datenbank-Schemaversion X ist neuer als diese App-Version` | Das Backup stammt von einer neueren netdiag-Version als der aktuell installierten — zuerst `git pull && sudo bash scripts/install.sh` ausführen, dann erneut wiederherstellen |

Bei jedem Restore-Versuch (auch fehlgeschlagenen) bleibt die alte
Datenbank unangetastet, solange die Validierung fehlschlägt. Nur nach
erfolgreicher Prüfung wird sie ersetzt — und dabei automatisch als
`netdiag.db.bak-<Zeitstempel>` im selben Verzeichnis gesichert.

## Sonstiges

**Frage/Problem nicht gelistet?** Serverseitige Logs geben meist den
entscheidenden Hinweis:

```bash
journalctl -u netdiag -f
```

Damit live mitverfolgen, während im Dashboard die problematische
Aktion ausgeführt wird. Für Fehlerberichte oder Beiträge:
[Issues auf GitHub](https://github.com/mrckch/netdiag/issues).
