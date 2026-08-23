# Benutzerhandbuch

netdiag hat vier Bereiche, oben als Reiter erreichbar:
**MESSEN · KATASTER · PORT-AKTIONEN · VERWALTUNG**

Diese Anleitung geht sie der Reihe nach durch. Für die Installation
siehe [INSTALLATION.md](INSTALLATION.md).

---

## Grundidee

netdiag ist ein Software-Nachbau eines Hardware-Netzwerktesters
(Fluke LinkIQ, NetAlly LinkRunner, Trend NaviTEK). Anders als diese
Geräte **dokumentiert netdiag dauerhaft**: Jede Messung kann einer
**Dose** (Netzwerkanschluss) an einem festen Ort zugeordnet werden —
Etage → Raum → Dose. So entsteht nach und nach ein vollständiges
Kabelkataster eines Gebäudes, inklusive Mess-Historie pro Dose.

Zentral dabei: **Messen und Speichern sind getrennte Schritte.** Ein
Autotest legt nie automatisch einen Datenbankeintrag an — das
verhindert, dass reine "mal eben testen"-Messungen die Datenbank
zumüllen. Erst ein expliziter Klick auf **SPEICHERN** sichert das
Ergebnis.

---

## MESSEN

Der Startbildschirm, für den täglichen Einsatz beim Durchgehen eines
Gebäudes optimiert.

### Ablauf

1. Netzwerkkabel von der zu testenden Dose ins Gerät stecken.
2. Im Dropdown **PORT** das richtige LAN-Interface wählen (nur echte
   Ethernet-Interfaces werden angezeigt — WLAN ist bewusst nicht
   wählbar, da das Testen einer Netzwerkdose keinen Sinn über WLAN
   ergibt).
3. **AUTOTEST** klicken. Der Test dauert je nach Umgebung ca. 10–15
   Sekunden und führt gleichzeitig aus:
   - **LINK** — Speed, Duplex, Link-Status (`ethtool`)
   - **SWITCH (LLDP/CDP)** — Name des benachbarten Switches, Port-ID,
     Management-IP (per `lldpd`, zusätzlich passives Mitlesen von
     Cisco-CDP-Paketen)
   - **VLAN / 802.1X / STP** — welche 802.1Q-VLAN-Tags auf der Leitung
     sichtbar sind, ob 802.1X-Port-Authentifizierung verlangt wird
     (EAPOL erkannt), ob Spanning Tree aktiv ist (BPDU erkannt)
   - **DHCP** — ob und welcher DHCP-Server antwortet (Angebotene IP,
     Gateway, DNS, Subnetzmaske) — **ohne** dabei selbst einen Lease zu
     belegen
   - **GATEWAY-PING** — Erreichbarkeit und Latenz zum per DHCP
     gemeldeten Gateway
4. Jede Ergebniskarte hat eine LED-Anzeige links im Kopf:
   🟢 grün = ok, 🟡 gelb = Warnung/kein Befund, 🔴 rot = Fehler.
5. Optional: **DURCHSATZ (iperf)** klicken, um zusätzlich Down-/Upload
   in Mbit/s gegen den konfigurierten iperf3-Server zu messen (siehe
   [Verwaltung](#verwaltung) für die Server-Adresse). Dauert ca. 20–25
   Sekunden (beide Richtungen).

### Ergebnis zuordnen und speichern

Sobald ein Ergebnis vorliegt, erscheint unten die **Zuordnen-Leiste**
mit dem Hinweis „UNGESPEICHERT":

- Etage → Raum → Dose per Dropdown wählen. Die Auswahl ist **sticky**:
  Sie bleibt für den nächsten Test erhalten, praktisch beim
  Raum-für-Raum-Durchmessen.
- Existiert die Dose noch nicht, direkt per **+ Dose** anlegen (fragt
  nach einer Bezeichnung, z. B. `D03`).
- **SPEICHERN** klicken. Ohne Dosen-Auswahl landet die Messung als
  „nicht zugeordnet" in der Datenbank und kann später im Kataster-Tab
  nachträglich zugewiesen werden.
- Wird **kein** neuer Test gestartet und stattdessen zur nächsten Dose
  weitergegangen, verfällt ein ungespeichertes Ergebnis beim nächsten
  Autotest kommentarlos — das ist gewollt (Aufräum-/Prüfmodus ohne
  Dokumentationsabsicht).

### Netz-Scan

Der Kartenblock **NETZ-SCAN** unten auf der Seite ist unabhängig vom
Autotest: Subnetz eingeben (z. B. `192.168.1.0/24`) und **SCAN**
klicken, um aktive Geräte im Segment zu listen (IP, Hostname/Hersteller,
MAC-Adresse). Scan-Ergebnisse werden **nie** gespeichert.

---

## KATASTER

Der Bereich für Stammdaten und Historie — das eigentliche
Kabelkataster.

### Baumansicht

Etagen → Räume → Dosen, aufklappbar. Jede Dose zeigt:
- ihr Gerätetyp-Icon (falls gesetzt)
- Bezeichnung und ggf. Patchfeld-Zuordnung (`PF-EG-01/12`)
- Anzahl gespeicherter Messungen

Klick auf eine Dose öffnet das **Dosen-Detail**.

### Dosen-Detail

- **Patchfeld** und **Patchfeld-Port**: händisch gepflegt, dokumentiert
  die physische Verkabelung Dose → Patchfeld. Switch und Switch-Port
  müssen hier nicht eingetragen werden — die kommen automatisch aus der
  letzten Messung (LLDP/CDP).
- **Notizen**: Freitext.
- **Gerät**: Icon-Auswahl (PC, Beamer, AppleTV, Drucker, Access Point,
  Telefon/VoIP, Switch/Uplink, frei, Sonstiges — erweiterbar unter
  Verwaltung). Erneutes Klicken auf das aktive Icon hebt die Auswahl
  wieder auf.
- **ÄNDERUNGEN SPEICHERN** sichert die drei obigen Felder.
- **Dose löschen**: fragt zur Sicherheit nach, und falls die Dose
  bereits Messungen hat, ein zweites Mal ausdrücklich mit dem Hinweis
  auf die Anzahl betroffener Messungen.
- **HISTORIE**: alle gespeicherten Messungen dieser Dose,
  chronologisch, mit Kurzzusammenfassung. Ändert sich zwischen zwei
  aufeinanderfolgenden Autotest-Messungen z. B. das VLAN oder der
  erkannte Switch/Port, erscheint ein **⚠ geändert**-Hinweis mit den
  konkreten Unterschieden (Tooltip). Einzelne Messungen können über das
  ✕ gelöscht werden.

### Nicht zugeordnete Messungen

Erscheint eine gelbe Box **⚠ NICHT ZUGEORDNETE MESSUNGEN** oben in der
Baumansicht, gibt es gespeicherte Messungen ohne Dosen-Zuordnung (weil
beim Speichern keine Dose gewählt wurde). Über **zuordnen…** lässt sich
jede nachträglich einer Dose zuweisen.

### XLSX-Export

**XLSX-EXPORT…** öffnet einen Dialog:

- **Spalten**: frei wählbar per Checkbox (Etage, Raum, Dose, Patchfeld,
  Patchfeld-Port, Gerät, Zeitpunkt, Messart, Speed, Duplex, VLAN-IDs,
  Switch, Switch-Port, DHCP, iperf Mbit/s, Notizen).
- **nur letzte Messung pro Dose** (Standard) vs. abgehakt lassen für
  die **komplette Historie** aller Messungen.
- **Zeitraumfilter** (von/bis) optional.

Der Export ist sortiert nach Etage → Raum → Dose, mit eingefrorener
Kopfzeile und Autofilter — direkt in Excel/LibreOffice weiterverwendbar.

---

## PORT-AKTIONEN

Schreibzugriffe auf den zuletzt gemessenen Switch-Port per SNMP.
**Wichtig:** Es gibt hier keine manuelle Eingabe von Switch-IP oder
Portname — alle Aktionen beziehen sich ausschließlich auf den Switch
und Port, der beim letzten Autotest im Bereich MESSEN per LLDP/CDP
erkannt wurde. Das verhindert, versehentlich den falschen Switch zu
treffen.

Ohne vorherigen Autotest mit erkanntem Nachbarn zeigt der Tab nur den
Hinweis „KEIN PORT ERKANNT". Voraussetzung ist außerdem eine
konfigurierte SNMP-Community unter Verwaltung.

### Port-Description setzen

1. **VORSCHAU LADEN**: löst den Port-Namen aus LLDP/CDP zum SNMP-ifIndex
   auf und zeigt die aktuell am Switch hinterlegte Description an. Ein
   Vorschlagstext wird aus dem Template (`Verwaltung → SNMP
   Description-Template`, Standard `{raum}-{dose} {geraet}`) berechnet
   — nur wenn im Messen-Tab bereits eine Dose zugeordnet wurde.
2. Text bei Bedarf anpassen.
3. **AM SWITCH SCHREIBEN** — fragt vor dem tatsächlichen Schreiben noch
   einmal per Bestätigungsdialog nach.

### VLAN setzen (⚠ Experimentell)

Setzt das native/untagged VLAN (PVID) und die getaggten VLANs eines
Ports über die Q-BRIDGE-MIB.

**Als experimentell markiert, weil** die MIB-Umsetzung je nach
Switch-Hersteller (u. a. LANCOM, HP/Aruba ProCurve) leicht variiert.
**Vor produktivem Einsatz gegen die konkreten im Einsatz befindlichen
Switch-Modelle verifizieren** — am besten zunächst an einem
unkritischen Testport ausprobieren.

1. **AKTUELLEN ZUSTAND LADEN**: zeigt PVID und getaggte VLANs des Ports.
2. Neue Werte eintragen (Untagged-VLAN als Zahl, getaggte VLANs
   kommagetrennt, z. B. `20,30,99`). Ein Diff der Änderungen erscheint
   automatisch.
3. **PORT UMKONFIGURIEREN…** öffnet einen zweiten Bestätigungsdialog
   mit deutlicher Warnung: *„Das angeschlossene Gerät kann die
   Verbindung sofort verlieren. Falls dieses Netbook über denselben
   Port verbunden ist, bricht auch die Verbindung zu netdiag ab."*
   Erst nach Anhaken „Ich habe den Diff geprüft" lässt sich **JETZT
   SCHREIBEN** anklicken.

**Praktischer Rat:** Diese Funktion niemals über den Port ausführen,
über den das eigene Netbook selbst am Netz hängt, außer man ist sich
der Konsequenzen bewusst — die eigene Verbindung kann dabei sofort
abreißen.

### Port-Fehlerstatistik

Rein lesende Karte — kein Schreibzugriff, kein Risiko für die Verbindung.
Zeigt die physikalischen Ethernet-Fehlerzähler des zuletzt erkannten
Switch-Ports per SNMP. Der eigentliche Zweck: unterscheiden, ob ein
Problem an der **Konfiguration** liegt (VLAN, Duplex, DHCP — siehe die
anderen Karten) oder an der **Physik** — Kabel, Stecker, Patchfeld,
Störung. Bei Verdacht auf Letzteres ist das der Beleg, um gezielt einen
Elektriker mit der Prüfung der Verkabelung an genau diesem Port zu
beauftragen, statt auf Zuruf zu raten.

Angezeigte Zähler:

| Zähler | Sagt etwas aus über |
|---|---|
| CRC/FCS-Fehler | Bitfehler durch Störung, Kabelschaden oder schlechten Crimp — der direkteste Kabel-Indikator |
| Alignment-Fehler | Bit-Ausrichtungsfehler auf physischer Ebene — ebenfalls Kabel/Hardware |
| Symbol-Fehler | Entsprechung zu FCS-Fehlern auf Leitungscodierungsebene bei Gigabit+-Links |
| Late Collisions | Klassisches Zeichen für zu langes Kabel oder Duplex-Mismatch |
| Excessive Collisions | Stark überlastetes Segment oder Duplex-Mismatch |
| Carrier-Sense-Fehler | Problem beim Erkennen des Trägersignals — meist Hardware/Kabel |
| Eingehende/Ausgehende Fehler gesamt | Generischer IF-MIB-Zähler als Fallback, falls der Switch die detaillierteren Zähler oben nicht unterstützt |

Alle sechs oberen Zähler sollten auf einem gesunden Vollduplex-Link
**dauerhaft bei 0 bleiben**. Steht einer davon ungleich 0 und wächst
weiter, ist das ein starkes Indiz für ein physisches Problem an genau
diesem Port oder Kabel.

**Nutzung:**

1. **SCHNAPPSCHUSS LADEN** — liest die aktuellen (kumulativen, seit dem
   letzten Switch-Neustart zählenden) Werte. Zähler, die schon jetzt
   ungleich 0 sind, werden rot hervorgehoben.
2. **ALS BASIS MERKEN** — merkt sich den zuletzt geladenen Schnappschuss
   als Vergleichspunkt.
3. Etwas Zeit vergehen lassen (z. B. Kabel bewegen/wackeln, um einen
   Wackelkontakt zu provozieren, oder einfach eine Weile Traffic
   laufen lassen) und erneut **SCHNAPPSCHUSS LADEN** klicken — die
   Spalte „seit Basis" zeigt jetzt die Differenz seit dem gemerkten
   Zeitpunkt. So lässt sich sagen „12 CRC-Fehler in den letzten 2
   Minuten", statt nur eine nicht einordenbare Gesamtsumme zu sehen.
4. **Basis löschen** setzt den Vergleichspunkt zurück.

Zeigt ein Zähler „nicht verfügbar": Der Switch unterstützt diese
konkrete MIB nicht vollständig — betrifft meist nur die spezielleren
EtherLike-MIB-Zähler, nicht die generischen IF-MIB-Fehlerzähler.

---

## VERWALTUNG

Stammdaten- und Systemverwaltung.

### Etagen / Räume / Gerätetypen

Einfache Listen mit Anlegen (Name eingeben, **+**) und Löschen (**✕**).
Enthält eine Etage noch Räume bzw. ein Raum noch Dosen mit Messungen,
fragt das System vor dem Löschen ausdrücklich nach einer Bestätigung
inklusive Löschung aller untergeordneten Daten.

Neue Gerätetypen bekommen ein frei wählbares Icon (Emoji, z. B. 🖥) und
einen Namen.

### Einstellungen

- **iperf3-Server**: Adresse (IP oder Hostname) der iperf3-Gegenstelle
  für Durchsatzmessungen.
- **SNMP Community (v2c, write)**: wird für Port-Aktionen benötigt.
  Aus Sicherheitsgründen zeigt das Dashboard den gespeicherten Wert
  **nie** im Klartext an — das Feld bleibt leer und zeigt nur per
  Platzhaltertext an, ob bereits eine Community hinterlegt ist. Leer
  lassen und speichern ändert den gespeicherten Wert **nicht**; nur
  eine Eingabe überschreibt ihn.
- **SNMP Description-Template**: Platzhalter `{raum}`, `{dose}`,
  `{geraet}` verfügbar, Standard `{raum}-{dose} {geraet}`.

### Datenbank

- **BACKUP HERUNTERLADEN**: erzeugt einen konsistenten Snapshot der
  SQLite-Datenbank (auch während des laufenden Betriebs, via `VACUUM
  INTO`) und lädt ihn als Datei herunter.
- **WIEDERHERSTELLEN…**: ersetzt die aktuelle Datenbank durch eine
  hochgeladene `.db`-Datei. Vor dem Ersetzen wird die alte Datenbank
  automatisch als `netdiag.db.bak-<Zeitstempel>` gesichert. Zwei
  Sicherheitsabfragen müssen bestätigt werden. Die hochgeladene Datei
  wird auf gültiges SQLite-Format und passendes Tabellenschema geprüft;
  ist ihre Schema-Version neuer als die der laufenden App-Version, wird
  der Import abgelehnt (erst netdiag aktualisieren).

---

## Tipps für den praktischen Einsatz

- **Raumweise vorgehen**: Etage und Raum bleiben nach dem Speichern
  ausgewählt — beim Durchgehen eines Raums mit mehreren Dosen muss nur
  noch die Dose gewechselt werden.
- **Erst dokumentieren, dann Port-Aktionen**: Die Beschreibung/VLAN
  eines Ports sinnvoll setzen erfordert eine zuvor zugeordnete Dose
  (für den Description-Vorschlag) und einen erkannten Switch (für
  beides) — also erst Autotest + Speichern, dann in
  PORT-AKTIONEN wechseln.
- **Regelmäßige Backups**: Insbesondere vor größeren Updates oder bevor
  mit der Wiederherstellungsfunktion experimentiert wird, ein manuelles
  Backup über Verwaltung → Datenbank ziehen.
- **DHCP-Test kostet keinen Lease**: Der DHCP-Discover-Test bindet
  keine IP-Adresse — beliebig oft wiederholbar, ohne den DHCP-Pool zu
  belasten.

Bei Problemen siehe [Troubleshooting](TROUBLESHOOTING.md).
