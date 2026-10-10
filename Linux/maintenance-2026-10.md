# Homelab maintenance, October 2026

This records the maintenance cycle of 2026-10-04/05 and its verification limits.
It is an operational result, not a requirement to repeat changes on new hosts.
Private overlays, credentials and detailed host reports remain outside Git.

## Completed host work

- All twelve hosts completed authorized APT upgrade, guarded autoremove and autoclean. There were 174 package upgrades. Final APT checks showed no remaining upgrades or held-back packages, and dpkg audits were clean.
- Unattended-upgrades email is disabled. Local logs and syslog remain enabled, with host events verified in Loki.
- Targeted Ubuntu Pro AppArmor profile repairs passed parser checks and actual firmware model reads on all twelve hosts. A paid Ubuntu Pro subscription is not required for these retained local profiles.
- The unused fwupd Flashrom plugin is disabled on the three affected APPS02 Pi 5 hosts. Existing NVMe devices remain available.
- smartmontools was removed only from DUMBLEDORE. Its smartd services and process are absent. Existing nodes do not support SMART, so no SMART probes were performed.
- The known rkhunter resolver, legacy blkid and inactive USBGuard SHM findings were resolved through helpers 45 and 46. Active verified USBGuard mappings remain intact with exact daily refreshed exceptions.
- Final focused rkhunter checks and the composed helper 43 check passed on all twelve hosts. Production file-property and passwd/group references were preserved during these checks.

The shared policies are integrated into the hardening script and both installation guides. Existing hosts use the focused maintenance helpers, not a rerun of new-installation hardening. No additional backups were created. The single nightly Longhorn/PostgreSQL backup-status check for the update cycle was reused.

## Staged K3s update

The official stable binary **v1.36.5+k3s1** is installed on disk on all twelve hosts with `INSTALL_K3S_SKIP_START=true`. Running K3s processes and kubelets remain **v1.36.4+k3s1**. Process identities and start times, service configuration, environment files and YAML configuration were verified unchanged. All twelve nodes were Ready without MemoryPressure, DiskPressure or PIDPressure at the final health check.

No host reboot or K3s restart was performed. All twelve hosts report a required reboot. Activation and post-restart validation are deferred to a separately approved maintenance window.

## Verification and limits

The final repository checks include 101 Linux regression tests, all seven Linux shell syntax checks, seven Python files and both embedded Python blocks. The known rkhunter findings have twelve successful focused final scans and twelve successful composed maintenance checks. Earlier file-property checks verified 135 paths per host.

An extended rkhunter scan completed on APPS02. Nine slower hosts reached the bounded 600-second limit during that extended audit. The successful focused checks resolve the known findings but are not a complete malware-negative assessment. No baseline refresh was used to hide unexplained changes. An earlier package purge triggered the then-existing APT_AUTOGEN hook on DUMBLEDORE, this automatic baseline change was documented and the hook subsequently disabled.

## Remaining operational work

| Item | Evidence and next step |
| --- | --- |
| SNAPE etcd I/O latency | A five-minute post-maintenance window still showed WAL fsync p99 of 386 ms, backend commit p99 of 462 ms, 115 slow applies and four ReadIndex delays. Quorum and leader remained healthy, without failed proposals. Capture disk/process I/O during the same burst before choosing a storage change. Sharing a disk with Longhorn is a candidate, not a proven cause. |
| Deferred activation | Schedule the twelve host reboots and activate the staged K3s release, then verify quorum, storage, nodes and workloads. |
| Vendor fixes | Unpoller PDU cycle/relay metrics and the Longhorn Endpoints API warning require their supported vendor fixes. Local workarounds were not substituted for a release. |

Home Assistant device findings are excluded by the operator. All NSE applications, including CURANDA, remain excluded from maintenance and error lists.
