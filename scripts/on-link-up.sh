#!/bin/bash
# Wird von udev bei Link-up aufgerufen (siehe udev/99-netdiag-trigger.rules).
# Zeigt eine Desktop-Benachrichtigung statt einen neuen Browser-Tab zu öffnen
# (beim Raum-für-Raum-Umstecken würde sonst jedes Mal ein Tab aufgehen).

set -euo pipefail

USER_NAME=$(who | awk '{print $1}' | head -n1)
[ -z "${USER_NAME}" ] && exit 0
USER_ID=$(id -u "${USER_NAME}")

sudo -u "${USER_NAME}" \
  DISPLAY=:0 \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${USER_ID}/bus" \
  notify-send -i network-wired "netdiag" "Link erkannt — Dashboard: localhost:8642" \
  2>/dev/null || true
