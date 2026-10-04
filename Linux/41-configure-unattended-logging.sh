#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
if [ "$#" -gt 1 ] || { [ "$MODE" != '--check' ] && [ "$MODE" != '--apply' ]; }; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi

command -v apt-config >/dev/null
CONFIG_FILE='/etc/apt/apt.conf.d/99zz-homelab-unattended-upgrades'

check_configuration() {
  local effective
  effective="$(apt-config dump)"
  if ! grep -Fxq 'Unattended-Upgrade::Mail "";' <<< "$effective"; then
    echo 'FAIL: unattended-upgrades mail is not explicitly disabled.' >&2
    return 1
  fi
  if ! grep -Fxq 'Unattended-Upgrade::SyslogEnable "true";' <<< "$effective"; then
    echo 'FAIL: unattended-upgrades syslog logging is not enabled.' >&2
    return 1
  fi
  echo 'PASS: unattended-upgrades mail is disabled and syslog logging is enabled.'
}

if [ "$MODE" = '--apply' ]; then
  if [ "$EUID" -ne 0 ]; then
    echo 'Root privileges are required for --apply.' >&2
    exit 1
  fi
  TEMP_FILE="$(mktemp "${CONFIG_FILE}.XXXXXX")"
  trap 'rm -f -- "$TEMP_FILE"' EXIT
  cat > "$TEMP_FILE" <<'EOF'
// Keep update results in local logs and the existing journal/Loki pipeline.
Unattended-Upgrade::Mail "";
Unattended-Upgrade::SyslogEnable "true";
EOF
  chown root:root "$TEMP_FILE"
  chmod 0644 "$TEMP_FILE"
  mv -f -- "$TEMP_FILE" "$CONFIG_FILE"
fi

check_configuration
