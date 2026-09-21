#!/bin/sh
set -eu

OUTPUT_DIR=/var/lib/node_exporter/textfile_collector
OUTPUT_FILE="$OUTPUT_DIR/host_maintenance.prom"

metric_age_seconds() {
  path="$1"
  now=$(date +%s)
  if [ -e "$path" ]; then
    modified=$(stat -c %Y "$path" 2>/dev/null || echo "$now")
    echo $((now - modified))
  else
    echo -1
  fi
}

while true; do
  now=$(date +%s)
  reboot_required=0
  [ -e /host/var/run/reboot-required ] && reboot_required=1

  update_age=$(metric_age_seconds /host/var/lib/apt/periodic/update-success-stamp)
  unattended_log_age=$(metric_age_seconds /host/var/log/unattended-upgrades/unattended-upgrades.log)

  temp_file="$OUTPUT_FILE.$$"
  {
    echo '# HELP homelab_host_maintenance_collector_success Whether the host maintenance collector completed successfully.'
    echo '# TYPE homelab_host_maintenance_collector_success gauge'
    echo 'homelab_host_maintenance_collector_success 1'
    echo '# HELP homelab_host_maintenance_last_run_unixtime Unix time of the most recent host maintenance collection.'
    echo '# TYPE homelab_host_maintenance_last_run_unixtime gauge'
    echo "homelab_host_maintenance_last_run_unixtime $now"
    echo '# HELP homelab_host_reboot_required Whether the host reports a pending reboot.'
    echo '# TYPE homelab_host_reboot_required gauge'
    echo "homelab_host_reboot_required $reboot_required"
    echo '# HELP homelab_host_apt_update_stamp_age_seconds Age of the host APT update-success stamp, or -1 when absent.'
    echo '# TYPE homelab_host_apt_update_stamp_age_seconds gauge'
    echo "homelab_host_apt_update_stamp_age_seconds $update_age"
    echo '# HELP homelab_host_unattended_upgrades_log_age_seconds Age of the unattended-upgrades log, or -1 when absent.'
    echo '# TYPE homelab_host_unattended_upgrades_log_age_seconds gauge'
    echo "homelab_host_unattended_upgrades_log_age_seconds $unattended_log_age"
  } > "$temp_file"
  mv "$temp_file" "$OUTPUT_FILE"
  sleep 300
done
