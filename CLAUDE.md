# CLAUDE.md

## Projektziel
Software-Nachbau eines Hardware-Netzwerktesters (LinkIQ/NaviTEK-Klasse) auf
einem Linux-Netbook. Läuft rein lokal, kein Cloud-Bezug, kein DSGVO-Thema
(keine Personendaten).

## Prinzipien
- YAGNI: keine Multi-User-Auth, keine DB — ein Nutzer, ein Gerät, In-Memory
  bzw. optional lokale JSON-Historie.
- Deterministische Auswertung: reine Protokoll-Parser (ethtool/lldpd/scapy),
  keine LLM-Komponente nötig oder gewünscht in diesem Projekt.
- Root-Rechte sind hier akzeptabel (dediziertes Diagnosegerät), aber im Code
  sauber kapseln (ein Modul `privileged.py` für alles was CAP_NET_RAW braucht).

## Stack
- Python 3.11+, FastAPI, Uvicorn
- Scapy für Paket-Sniffing (VLAN/EAPOL/STP)
- Subprocess-Wrapper für ethtool, lldpcli, nmap, ping
- Vanilla JS/HTML Frontend, kein Build-Step

## Konventionen (wie in anderen Projekten)
- ADRs in `docs/adr/` bei größeren Design-Entscheidungen
- Kein Docker Compose nötig hier — Zielumgebung ist ein einzelnes Netbook,
  systemd-Service ist einfacher und robuster für den Zweck.
