#!/bin/bash
# Setup für netdiag auf einem Debian/Ubuntu-basierten Linux-Netbook.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausführen: sudo bash scripts/install.sh"
  exit 1
fi

INSTALL_DIR="/opt/netdiag"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installiere Systempakete (lldpd, ethtool, nmap, python3-venv) ..."
apt-get update -qq
apt-get install -y lldpd ethtool nmap python3-venv python3-pip xdg-utils

echo "==> Aktiviere lldpd ..."
systemctl enable --now lldpd

echo "==> Kopiere Projekt nach ${INSTALL_DIR} ..."
mkdir -p "${INSTALL_DIR}"
rsync -a --exclude ".venv" --exclude "__pycache__" "${SRC_DIR}/" "${INSTALL_DIR}/"

echo "==> Erstelle virtualenv und installiere Python-Abhängigkeiten ..."
python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q

chmod +x "${INSTALL_DIR}/scripts/on-link-up.sh"

echo "==> Richte systemd-Service ein ..."
cp "${INSTALL_DIR}/systemd/netdiag.service" /etc/systemd/system/netdiag.service
systemctl daemon-reload
systemctl enable --now netdiag

echo "==> Richte udev-Regel ein ..."
cp "${INSTALL_DIR}/udev/99-netdiag-trigger.rules" /etc/udev/rules.d/99-netdiag-trigger.rules
udevadm control --reload-rules

echo ""
echo "Fertig. Dashboard: http://localhost:8642"
echo "Status prüfen:     systemctl status netdiag"
