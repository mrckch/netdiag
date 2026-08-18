#!/bin/bash
# Wird von udev bei Link-up aufgerufen (siehe udev/99-netdiag-trigger.rules).
# Öffnet das netdiag-Dashboard im Browser des aktiven Desktop-Users.
# Läuft als root (via udev), daher muss der Zielnutzer/DISPLAY ermittelt werden.

set -euo pipefail

USER_NAME=$(who | awk '{print $1}' | head -n1)
if [ -z "${USER_NAME}" ]; then
  exit 0
fi

USER_ID=$(id -u "${USER_NAME}")
export DISPLAY=:0
export XDG_RUNTIME_DIR="/run/user/${USER_ID}"

sudo -u "${USER_NAME}" DISPLAY=:0 XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR}" \
  xdg-open "http://localhost:8642" >/tmp/netdiag-open.log 2>&1 || true
