#!/usr/bin/env bash
# Keep package maintenance bounded on hosts that also run etcd and storage.
set -euo pipefail
export LC_ALL=C LANG=C DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
MODE="${1:---check}"
if [ "$#" -gt 1 ] || { [ "$MODE" != '--check' ] && [ "$MODE" != '--apply' ]; }; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi
if [ "$EUID" -ne 0 ]; then
  echo 'Run as root to inspect APT locks and the complete package state.' >&2
  exit 1
fi
for command_name in apt-get dpkg dpkg-query uname flock nice ionice; do
  command -v "$command_name" >/dev/null
 done
exec 9>/run/lock/homelab-package-maintenance.lock
flock -n 9 || { echo 'Another homelab package maintenance is running.' >&2; exit 1; }
AUDIT="$(dpkg --audit)"
if [ -n "$AUDIT" ]; then
  printf '%s\n' "$AUDIT" >&2
  echo 'Refusing: repair the existing dpkg state before upgrading.' >&2
  exit 1
fi
APT=(apt-get -o DPkg::Lock::Timeout=120 -o APT::Get::AutomaticRemove=false
  -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
run_apt() { nice -n 10 ionice -c 2 -n 7 "${APT[@]}" "$@"; }
KERNEL="$(uname -r)"
KERNEL_REGEX="${KERNEL//./\.}"
KERNEL_REGEX="${KERNEL_REGEX//+/\+}"
# Keep this guard in the real APT transaction as well as the simulation.
APT+=(-o "APT::NeverAutoRemove::=^linux-(image|headers|modules|modules-extra)(-unsigned)?-${KERNEL_REGEX}$")
APT+=(-o 'APT::NeverAutoRemove::=^(apt|dpkg|sudo|openssh-server|systemd|systemd-sysv|udev|iproute2|iptables|nftables|nfs-common|open-iscsi|multipath-tools|linux-raspi|linux-image-raspi|linux-generic|linux-image-generic|k3s|containerd|containerd.io)$')
check_removals() {
  local plan="$1" package
  while read -r package; do
    package="${package%%:*}"
    case "$package" in
      linux-image-"$KERNEL"|linux-image-unsigned-"$KERNEL"|linux-modules-"$KERNEL"|linux-modules-extra-"$KERNEL"|linux-headers-"$KERNEL")
        echo "Refusing: removal of running-kernel package $package." >&2; return 1 ;;
      apt|dpkg|sudo|openssh-server|systemd|systemd-sysv|udev|iproute2|iptables|nftables|nfs-common|open-iscsi|multipath-tools|linux-raspi|linux-image-raspi|linux-generic|linux-image-generic|k3s|containerd|containerd.io)
        echo "Refusing: removal of host or storage dependency $package." >&2; return 1 ;;
    esac
  done < <(awk '/^(Remv|Purg) / { print $2 }' <<< "$plan")
}
if [ "$MODE" = '--apply' ]; then
  run_apt update --error-on=any
fi
PLAN="$(run_apt -s --with-new-pkgs --no-remove upgrade)"
printf '%s\n' "$PLAN"
if grep -Eq '^(Remv|Purg) ' <<< "$PLAN"; then
  echo 'Refusing: the upgrade plan removes packages.' >&2
  exit 1
fi
if [ "$MODE" = '--apply' ]; then
  run_apt --assume-yes --with-new-pkgs --no-remove upgrade
fi
PLAN="$(run_apt -s autoremove)"
printf '%s\n' "$PLAN"
check_removals "$PLAN"
if [ "$MODE" = '--apply' ]; then
  run_apt --assume-yes autoremove
  run_apt --assume-yes autoclean
  run_apt check
  AUDIT="$(dpkg --audit)"
  if [ -n "$AUDIT" ]; then
    printf '%s\n' "$AUDIT" >&2
    exit 1
  fi
  if [ -e /var/run/reboot-required ]; then
    echo 'REBOOT REQUIRED: not performed by this helper.'
    if [ -r /var/run/reboot-required.pkgs ]; then cat /var/run/reboot-required.pkgs; fi
  fi
  echo 'PASS: APT upgrade, checked autoremove and autoclean completed.'
else
  echo 'CHECK ONLY: package indexes and installed packages were not changed.'
fi
