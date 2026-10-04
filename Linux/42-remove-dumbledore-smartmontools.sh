#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
if [ "$#" -gt 1 ] || { [ "$MODE" != '--check' ] && [ "$MODE" != '--apply' ]; }; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi
if [ "$(hostname -s | tr '[:upper:]' '[:lower:]')" != 'dumbledore' ]; then
  echo 'This removal is authorized only on dumbledore.' >&2
  exit 1
fi
if [ "$MODE" = '--apply' ] && [ "$EUID" -ne 0 ]; then
  echo 'Root privileges are required for --apply.' >&2
  exit 1
fi

export LC_ALL=C
FAILED_UNITS=()
for unit in smartmontools.service smartd.service; do
  if systemctl is-failed --quiet "$unit"; then
    FAILED_UNITS+=("$unit")
  fi
done

STATUS="$(dpkg-query -W -f='${db:Status-Status}' smartmontools 2>/dev/null || true)"
if [ "$STATUS" = 'installed' ] || [ "$STATUS" = 'config-files' ]; then
  PLAN="$(apt-get -s purge smartmontools)"
  printf '%s\n' "$PLAN"
  # Do not remove dependencies or accept an unrelated installation/upgrade.
  if ! awk '
    /^(Remv|Purg) / && $2 !~ /^smartmontools(:[a-z0-9]+)?$/ { unsafe=1 }
    /^(Inst|Conf) / { unsafe=1 }
    END { exit unsafe }
  ' <<< "$PLAN"; then
    echo 'Refusing: APT simulation would change other packages.' >&2
    exit 1
  fi
  if [ "$MODE" = '--apply' ]; then
    apt-get --assume-yes purge smartmontools
  fi
elif [ -z "$STATUS" ] || [ "$STATUS" = 'not-installed' ]; then
  echo 'smartmontools is already absent.'
else
  echo "Refusing: unexpected smartmontools package state: $STATUS" >&2
  exit 1
fi

if [ "$MODE" = '--apply' ]; then
  STATUS="$(dpkg-query -W -f='${db:Status-Status}' smartmontools 2>/dev/null || true)"
  if [ -n "$STATUS" ] && [ "$STATUS" != 'not-installed' ]; then
    echo 'FAIL: smartmontools was not completely purged.' >&2
    exit 1
  fi
  systemctl daemon-reload
  for unit in "${FAILED_UNITS[@]}"; do
    FRAGMENT_PATH="$(systemctl show "$unit" --property=FragmentPath --value)"
    if [ -z "$FRAGMENT_PATH" ] || [ ! -e "$FRAGMENT_PATH" ]; then
      if systemctl is-failed --quiet "$unit"; then
        systemctl reset-failed "$unit"
      fi
    else
      echo "FAIL: $unit still has a unit file, keeping its failed state." >&2
      exit 1
    fi
  done
  echo 'PASS: smartmontools is absent and removed failed units are cleared.'
else
  echo 'CHECK ONLY: no packages or service states changed.'
fi
