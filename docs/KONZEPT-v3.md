# netdiag — Konzept v3 (Gesamtstand vor Umsetzung)

Dieses Dokument fasst alle Entscheidungen seit v2 zusammen. Ersetzt/ergänzt
`docs/KONZEPT.md` im Repo. **Noch nicht umgesetzt** — dient als Grundlage
für die nächste Implementierungsrunde.

---

## 1. Grundidee (unverändert seit v2)

Software-Netzwerktester + Kabelkataster auf Linux-Netbook. Dose (nicht
Messung) ist das langlebige Objekt: Etage → Raum → Dose. Messungen sind
Ereignisse daran, aber — **neu in v3** — nicht mehr automatisch gespeichert.

---

## 2. Neuer Kern-Workflow: Schnelltest / Aufräum-Modus

Größte Verhaltensänderung gegenüber v2: **Messen und Speichern sind jetzt
zwei getrennte Schritte.**

1. Interface wählen (nur LAN, siehe Punkt 5) → Autotest/iperf laufen lassen
2. Ergebnis erscheint **ungespeichert** (visuell markiert)
3. Nur bei Bedarf: Etage/Raum/Dose wählen (sticky) → „Speichern"
4. Ohne Speichern-Klick verfällt das Ergebnis beim nächsten Test — landet
   nie in der DB

Grund: Marc nutzt das Tool auch zum reinen Aufräumen/Prüfen ohne
Dokumentationsabsicht — die DB soll nicht mit Wegwerf-Messungen vollaufen.
Das dreht die v2-Logik um (dort: Speichern war Default, Zuordnung optional).

---

## 3. Erweitertes Domänenmodell

```
Etage
 └─ Raum
     └─ Dose (Nummer/Label)
         ├─ Gerätetyp (Icon: PC, Beamer, AppleTV, Drucker, AP, VoIP, Uplink, frei, Sonstiges)
         ├─ Patchfeld-Name        ← NEU
         ├─ Patchfeld-Port        ← NEU
         ├─ Notizen
         └─ Messung (nur wenn explizit gespeichert)
             ├─ Autotest (Link, LLDP/CDP, VLAN/EAPOL/STP, DHCP, Ping)
             └─ iperf (Down/Up Mbit/s, Retransmits)
```

**Damit ist pro Dose die komplette Strecke dokumentierbar:**
Dose → Patchfeld+Port (Stammdatum, händisch) → Switch+Port (aus Messung,
per LLDP/CDP automatisch erkannt).

### Tabellen-Änderungen ggü. v2
- `outlets`: zwei neue Spalten `patch_panel_name`, `patch_panel_port`
- `measurements`: Verhalten ändert sich (nur bei explizitem Speichern-Call
  angelegt), Schema selbst bleibt gleich

---

## 4. Switch-Eingriffe: Port-Aktionen (neuer eigener Bereich)

Zwei SNMP-Write-Funktionen, beide **ausschließlich für den zuletzt via
Autotest erkannten Port** — kein manuelles Eintippen von Switch-IP/Port.
Grund: verhindert, versehentlich den falschen Switch zu treffen.

### 4a. Port-Description setzen (ifAlias) — wie v2 geplant
- Preview: aktueller Wert + Vorschlag aus Template (`{raum}-{dose} {geraet}`)
- Bestätigen → schreiben

### 4b. VLAN setzen (PVID + tagged VLANs) — neu in v3
- Q-BRIDGE-MIB: `dot1qPvid` (untagged/native VLAN), VLAN-Egress-Bitmaps
  (tagged VLANs) — herstellerabhängig, vor Rollout gegen echte LANCOM-/
  ProCurve-Hardware verifizieren
- Aktuellen Zustand anzeigen (PVID + Liste tagged VLANs), neue Werte
  eingeben, Diff anzeigen
- **Strengere Bestätigung als bei Description:** Klartext-Warnung
  („Port wird sofort umkonfiguriert — angeschlossenes Gerät kann die
  Verbindung verlieren"), zweiter Bestätigungsschritt
- Reihenfolge: Description-Write zuerst produktiv nutzen, VLAN-Write erst
  danach — geringeres Ausfallrisiko zum Einstieg

Beide Aktionen leben in einem **eigenen Tab**, nicht inline im Mess-Screen —
bewusste Entkopplung von der hohen Klickfrequenz beim reinen Durchmessen.

---

## 5. Interface-Auswahl: nur LAN

WLAN-Interfaces werden aus der Auswahl komplett entfernt (Filter über
`/sys/class/net/<iface>/wireless` — existiert der Pfad, raus aus der Liste).
Kein Sonderfall, keine ausgegrauten Karten — WLAN taucht im Messen-Tab
gar nicht erst auf. `/api/interfaces` liefert von vornherein nur Ethernet.

---

## 6. iperf3-Server als LXC (Infrastruktur, nicht Teil der App)

- Ein LXC-Container mit Trunk-Interface (alle relevanten VLANs getaggt)
- Eine feste Server-Adresse in den Settings — unabhängig vom gerade
  gemessenen VLAN, da der Container ohnehin überall erreichbar ist
- App-seitig keine Änderung nötig ggü. v2-Planung (`iperf3 -c <server> -J`,
  beide Richtungen)

---

## 7. GUI-Struktur (final für diese Runde)

```
[ MESSEN ]   [ KATASTER ]   [ PORT-AKTIONEN ]   [ VERWALTUNG ]
```

### MESSEN
- Kopf: LAN-Interface-Dropdown, AUTOTEST-Button, iperf-Button
- Ergebnis-Karten (Link, LLDP, VLAN/802.1X/STP, DHCP, Ping, iperf) —
  Zustand „ungespeichert" bis explizit gesichert
- Zuordnen-Leiste unter dem Ergebnis: Etage→Raum→Dose (sticky) + „+ Dose"
  inline + Speichern-Button

### KATASTER
- Baum Etage→Raum→Dose
- Dosen-Detail: Gerätetyp-Icons, Patchfeld-Name/-Port (editierbar), Notizen,
  Mess-Historie mit Diff-Hinweis bei geänderten Kernwerten
- Liste unzugeordneter gespeicherter Messungen → nachträglich zuweisbar
- XLSX-Export-Dialog: Spaltenwahl (inkl. Patchfeld-Spalten), „letzte
  Messung" vs. „Historie", Zeitraumfilter

### PORT-AKTIONEN
- Nur aktiv nach einem Autotest mit erkanntem Switch (LLDP/CDP) — sonst
  Hinweis „Erst einen Port testen"
- Kontext-Kopf: erkannter Switch/Port/Mgmt-IP (read-only, aus letztem Test)
- Description setzen (Preview → Bestätigen)
- VLAN setzen (aktueller Zustand → neue Werte → Diff → Warnung → Bestätigen)

### VERWALTUNG
- Etagen/Räume/Gerätetypen (CRUD)
- Settings: iperf-Server, SNMP-Community (v2c), SNMP-Description-Template
- Datenbank: Backup-Download, Restore-Upload (mit Sicherheitsabfragen)

---

## 8. Architekturentscheidungen — Ergänzungen ggü. v2

| # | Entscheidung | Begründung |
|---|---|---|
| 8 | Messung nur bei explizitem Speichern-Call in DB | Aufräum-Nutzung ohne DB-Müll |
| 9 | Patchfeld-Felder an der Dose, nicht an der Messung | Ändert sich nicht pro Messung |
| 10 | VLAN-Write in eigenem Tab, striktere Bestätigung als Description | Höheres Ausfallrisiko |
| 11 | Port-Aktionen nur für zuletzt gemessenen Port, kein manueller Host-Eintrag | Verhindert Fehlgriff auf falschen Switch |
| 12 | WLAN-Interfaces aus Auswahl gefiltert, nicht nur ausgegraut | Messen über WLAN ergibt für Dosen-Dokumentation keinen Sinn |
| 13 | iperf-Server: ein LXC, trunked, eine Adresse in Settings | Einfacher als mehrere VLAN-gebundene Server |

---

## 9. Offene Punkte für die Umsetzung

1. VLAN-Write-MIB-Details (Bitmap-Kodierung) müssen gegen die konkreten
   LANCOM-/ProCurve-Switches verifiziert werden, bevor der Schreib-Pfad
   produktiv geht — ggf. erstmal nur Description-Write ausliefern, VLAN-Write
   als Phase danach.
2. Format des Patchfeld-Labels (frei vs. Schema) — bisher nicht festgelegt,
   Vorschlag: frei wie bei Dosen-Label.
3. Soll „Speichern" im Messen-Tab bei bereits bestehender letzter
   Etage/Raum/Dose-Auswahl ein Ein-Klick-Vorgang sein (sticky Werte werden
   sofort übernommen), oder soll die Dose bei jedem Speichern aktiv
   bestätigt werden müssen? Betrifft Tempo beim Raum-für-Raum-Messen.

---

## 10. Phasenplan (aktualisiert)

**Phase A:** Schnelltest-Workflow (Messen ohne Auto-Speichern) + Zuordnen-Leiste,
Patchfeld-Felder im Kataster, GUI-Umbau auf 4 Tabs, LAN-only-Interfacefilter.

**Phase B:** Port-Aktionen-Tab mit Description-Write (aus v2 übernommen,
jetzt als eigener Tab statt Inline-Button).

**Phase C:** VLAN-Write — nach Verifikation der MIB gegen echte Switches.

**Phase D:** iperf-LXC-Anbindung (App-seitig minimal, hauptsächlich
Infrastruktur-Arbeit auf Proxmox-Seite).
