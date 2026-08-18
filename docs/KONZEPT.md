# netdiag — Konzept v2

Software-Netzwerktester auf Linux-Netbook. Ersetzt Hardware-Handhelds
(LinkIQ/NaviTEK-Klasse) für Port-Diagnose **und** dokumentiert die
Verkabelungs-Infrastruktur eines Gebäudes dauerhaft.

Damit verschiebt sich der Charakter des Projekts:
**v1 war ein Messgerät. v2 ist ein Messgerät + Kabelkataster.**
Diese Unterscheidung prägt das ganze Design.

---

## 1. Domänenmodell

Zentrale Einsicht: Gemessen wird nicht "ein Port", sondern eine
**Netzwerkdose (Outlet)** an einem festen Ort. Die Dose ist das langlebige
Objekt, Messungen sind Ereignisse daran.

```
Standort (optional, Phase 3)
 └─ Etage
     └─ Raum
         └─ Dose (Nummer, z.B. "2.OG-R201-D03" oder frei)
             └─ Messung (Zeitstempel + Ergebnisse)
                 ├─ Autotest-Ergebnis (Link, LLDP, VLAN, DHCP, Ping)
                 └─ iperf-Ergebnis (optional, eigener Messtyp)
```

### Tabellen (SQLite)

| Tabelle | Felder (Kern) |
|---|---|
| `floors` | id, name, sort_order |
| `rooms` | id, floor_id (FK), name |
| `outlets` | id, room_id (FK), label, notes |
| `measurements` | id, outlet_id (FK, nullable!), started_at, kind (`autotest`/`iperf`), result_json, summary-Spalten* |
| `settings` | key, value (z.B. iperf-Server-Adresse) |

*Summary-Spalten: die 5–6 wichtigsten Werte (speed, duplex, vlan_ids,
switch_name, switch_port, dhcp_ok, iperf_mbps) **zusätzlich** als echte
Spalten denormalisiert — nicht nur im JSON-Blob. Grund: Sortierung,
Filterung und XLSX-Export brauchen sie direkt; JSON-Parsing bei jedem
Export wäre unnötig fragil. Das Roh-JSON bleibt als Vollarchiv daneben.

**`outlet_id` nullable:** Man muss auch "mal eben messen" können, ohne
vorher eine Dose anzulegen. Ungebundene Messungen landen in einem
"Nicht zugeordnet"-Eimer und können **nachträglich** einer Dose
zugewiesen werden. Das ist der wichtigste Workflow-Fix gegenüber der
naiven Umsetzung — beim Begehen eines Gebäudes will man erst stecken
und messen, nicht erst Formulare ausfüllen.

---

## 2. Workflows (aus Nutzersicht)

### W1: Freie Messung (wie v1)
Stecker rein → Autotest → Ergebnis sehen. Fertig. Keine Pflichtfelder.

### W2: Dokumentierte Messung (Kernworkflow v2)
1. Stecker rein
2. Dose wählen: Etage-Dropdown → Raum-Dropdown → Dose wählen **oder**
   inline neu anlegen ("+ Neue Dose in diesem Raum")
3. Autotest → Ergebnis wird automatisch der Dose zugeschrieben
4. Optional: iperf-Messung nachschieben (gleiche Dose, eigener Eintrag)

Wichtig: Die zuletzt gewählte Etage/der Raum bleibt **vorausgewählt**
(sticky), weil man beim Begehen typischerweise Raum für Raum arbeitet
und in einem Raum mehrere Dosen misst.

### W3: Nachträgliche Zuordnung
Liste ungebundener Messungen → Dose zuweisen (auch mehrere auf einmal).

### W4: Stammdatenpflege
Eigener Bereich "Verwaltung": Etagen und Räume anlegen/umbenennen/löschen.
Löschen nur mit Schutz: Raum mit Dosen bzw. Dose mit Messungen löschen
verlangt explizite Bestätigung ("...und 14 Messungen ebenfalls löschen?").
Duplikat-Schutz: Anlegen prüft case-insensitiv auf existierende Namen.

### W5: Historie & Auswertung
Pro Dose: chronologische Liste aller Messungen, aufklappbar aufs Detail.
Vergleichshinweis, wenn sich Kernwerte geändert haben (z.B. "VLAN war
bei letzter Messung 20, jetzt 30" — einfacher Diff der Summary-Spalten,
keine komplexe Trend-Engine. Phase-2-Feature, bewusst simpel).

### W6: Export/Import
- **DB-Backup:** Download der SQLite-Datei aus der UI (via SQLite
  `VACUUM INTO` für konsistenten Snapshot bei laufendem Betrieb).
- **DB-Restore:** Upload ersetzt die DB — mit doppelter
  Sicherheitsabfrage + automatischem Backup der alten DB vor dem
  Ersetzen (`.db.bak-<timestamp>`). Schema-Versionsprüfung beim Import.
- **XLSX-Export:** 
  - Sortierung: Etage → Raum → Dose
  - Wählbar: welche Spalten (Checkbox-Liste, dynamisch aus den
    Summary-Feldern generiert)
  - Wählbar: "nur letzte Messung pro Dose" (Standard, für
    Kabelkataster/Abnahme) vs. "komplette Historie" (Audit)
  - Wählbar: Zeitraumfilter (von/bis)
  - Umsetzung mit openpyxl, ein Sheet, eingefrorene Kopfzeile,
    Autofilter — bewusst schlicht.

---

## 3. iperf-Integration

- **Server:** eigenständiger iperf3-Server im Netz (Docker-Container auf
  dem ML350 oder ein Pi im Verteilerraum). Nicht Teil von netdiag —
  netdiag ist nur Client.
- **Client:** netdiag ruft `iperf3 -c <server> -J` auf (JSON-Output,
  sauber parsebar), speichert Down-/Upload-Mbps und Retransmits.
- **Konfiguration:** Server-Adresse in der `settings`-Tabelle, in der UI
  unter Verwaltung pflegbar. Mehrere Server möglich (z.B. einer pro
  Gebäude/VLAN), mit Namen.
- **Bewusst getrennt vom Autotest:** iperf dauert 10+ Sekunden und
  belastet das Netz — läuft nur auf expliziten Klick, nicht automatisch
  bei jedem Autotest. Eigener Button "Durchsatz messen" am
  Ergebnis-Screen, Ergebnis hängt sich als eigene Messung an dieselbe
  Dose.

---

## 4. UI-Struktur (3 Bereiche statt 1 Seite)

```
[ MESSEN ]   [ KATASTER ]   [ VERWALTUNG ]
```

1. **Messen** — der v1-Screen, erweitert um die Dosen-Auswahl oben und
   den iperf-Button. Bleibt der Startscreen, optimiert für schnelles
   Arbeiten mit Touchpad/kleinem Display.
2. **Kataster** — Baumansicht Etage→Raum→Dose, pro Dose die
   Messhistorie, Liste ungebundener Messungen, XLSX-Export-Dialog.
3. **Verwaltung** — Etagen/Räume-Pflege, iperf-Server, DB-Backup/Restore.

Weiterhin Vanilla JS/HTML, kein Build-Step, kein Framework. Die
Testgerät-Optik von v1 bleibt.

---

## 5. Architekturentscheidungen (ADR-Kurzform)

| # | Entscheidung | Begründung |
|---|---|---|
| 1 | SQLite, eine Datei | Einzelgerät, ein Nutzer, YAGNI. Backup = Dateikopie. |
| 2 | Summary-Spalten + JSON-Blob | Export/Sortierung braucht echte Spalten; JSON bewahrt Vollständigkeit. |
| 3 | Messung ohne Dosen-Pflicht | Feldarbeit-Realität; nachträgliche Zuordnung möglich. |
| 4 | iperf getrennt vom Autotest | Dauer + Netzlast; explizite Aktion. |
| 5 | Schema-Version in DB (`PRAGMA user_version`) | Import-Prüfung + spätere Migrationen. |
| 6 | Kein Auth | Gerät ist physisch bei dir, Dienst lauscht auf localhost. Falls je Remote-Zugriff: dann Authelia-Pattern, nicht vorher. |
| 7 | Export via openpyxl | XLSX nativ, keine LibreOffice-Abhängigkeit. |

---

## 6. Phasenplan

**Phase 1 — Fundament (als nächstes):**
DB-Schema + Migrationslogik, Dosen-CRUD, Messung-Speichern,
Dosen-Auswahl im Mess-Screen, Kataster-Baumansicht mit Historie.

**Phase 2 — Export & Komfort:**
XLSX-Export mit Spaltenwahl, DB-Backup/Restore, nachträgliche
Zuordnung, Diff-Hinweis in der Historie.

**Phase 3 — iperf & Ausbau:**
iperf-Client + Server-Verwaltung, optional Standort-Ebene (mehrere
Gebäude), optional Zeitraumfilter im Export.

Jede Phase ist für sich nutzbar — nach Phase 1 hat das Gerät bereits
den Kern-Mehrwert (Kataster + Historie) gegenüber jedem 1000€-Handheld,
denn die speichern gar keine Ortszuordnung.

---

## 7. Getroffene Entscheidungen (ehem. offene Fragen)

1. Dosen-Label: frei, mit Duplikat-Schutz pro Raum (UNIQUE-Constraint). ✓
2. Keine Gebäude-Ebene — es gibt nur ein Gebäudeteil. Etage bleibt oberste Ebene. ✓
3. udev-Trigger: Desktop-Notification statt Browser-Tab. ✓
4. SNMP: v2c (Entscheidung des Betreibers; Community nur im Management-VLAN nutzen). ✓

## 8. Ergänzungen v2.1

- **SNMP-Write:** ifAlias am Switch setzen. Zwei Schritte: Preview
  (ifIndex-Auflösung via ifName/ifDescr-Walk + aktuelle Description anzeigen)
  → bestätigtes Schreiben. Description aus Template `{raum}-{dose} {geraet}`
  (Settings). Kein stiller Write.
- **Gerätetyp pro Dose:** Icon-Leiste (PC, Beamer, AppleTV, Drucker, AP,
  Telefon/VoIP, Switch/Uplink, frei, Sonstiges), als Stammdaten pflegbar.
  Fließt in SNMP-Template und XLSX-Export ein.
