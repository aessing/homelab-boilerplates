# Linux Server Setup and Hardening

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains installation guides and a comprehensive hardening script for Ubuntu Server 24.04 LTS, designed for both standard x86/x64 servers and Raspberry Pi devices.

## Contents

```text
Linux/
├── 11-install-raspberry.md   # Installation guide for Raspberry Pi
├── 11-install-ubuntu.md      # Installation guide for standard servers
├── 21-harden-ubuntu.sh       # Comprehensive hardening script
├── 22-repair-ubuntu-pro-apparmor.sh # Targeted Ubuntu Pro firmware policy repair
├── 31-install-nut-client.sh  # NUT (Network UPS Tools) client setup
├── 41-configure-unattended-logging.sh # Disable update mail, retain logging
├── 42-remove-dumbledore-smartmontools.sh # Remove unsupported SMART tooling
├── 43-configure-host-maintenance.sh # Targeted fwupd, rkhunter and SSH policy
├── 44-update-host-packages.sh # Checked package upgrade and cleanup
├── 45-clean-rkhunter-artifacts.py # Verify and remove unused scanner artifacts
├── 46-configure-rkhunter-usbguard.py # Exact active USBGuard scanner policy
└── environments/
    └── _SAMPLE.env           # Template environment configuration
```

## Features

The hardening script implements security best practices based on:

- [CIS Benchmarks](https://downloads.cisecurity.org/)
- [Konstruktoid Hardening](https://github.com/konstruktoid/hardening)
- [Neo23x0 Auditd Rules](https://github.com/Neo23x0/auditd)

### Security Hardening Components

| Component | Description |
|-----------|-------------|
| **APT Configuration** | Secure package manager settings, disable insecure repositories |
| **Kernel Parameters** | Sysctl hardening for network, memory, and process security |
| **SSH Hardening** | Strong ciphers, key-based auth, restricted access groups |
| **Firewall (UFW)** | Configured firewall with logging and admin access rules |
| **PAM Configuration** | Password policies, account lockout, login restrictions |
| **File System** | Secure mount options, partition hardening, tmpfs security |
| **Auditing** | Comprehensive auditd rules for system monitoring (optional) |
| **AppArmor** | Mandatory Access Control enforcement |
| **Fail2Ban/PSAD** | Intrusion detection and prevention (optional) |
| **AIDE** | File integrity monitoring (optional) |
| **Time Sync** | Secure NTP configuration with systemd-timesyncd |
| **Logging** | Journald, rsyslog, and logrotate configuration |
| **USB Guard** | USB device access control |
| **RKHunter** | Rootkit detection |

## Prerequisites

- Ubuntu Server 24.04 LTS (freshly installed)
- Root or sudo access
- Network connectivity for package installation
- SSH public key for admin user

## Quick Start

### 1. Install Ubuntu Server

Follow the appropriate installation guide:

- **Standard Servers**: See [11-install-ubuntu.md](11-install-ubuntu.md)
- **Raspberry Pi**: See [11-install-raspberry.md](11-install-raspberry.md)

### 2. Create Your Environment File

Copy the sample environment file and customize it for your server:

```bash
cd Linux/environments
cp _SAMPLE.env myserver.env
```

Edit the file with your configuration:

```bash
nano myserver.env
```

### 3. Run the Hardening Script

Execute the script with your environment file name (without the `.env` extension):

```bash
sudo ./21-harden-ubuntu.sh myserver
```

The script will:

- Validate the environment file
- Apply all hardening configurations
- Apply the shared unattended logging, Ubuntu Pro AppArmor and host maintenance policies
- Initialize an absent rkhunter baseline only for this trusted new installation
- Preserve an existing rkhunter baseline and any existing backup files
- Log all actions to `21-harden-ubuntu.log`

### 4. Post-Installation Steps

After the script completes:

1. **Set a new password** for the admin user (uses new hashing algorithm):

   ```bash
   passwd <admin_user>
   ```

2. **Reboot** to apply all changes:

   ```bash
   sudo reboot
   ```

3. **Verify the resulting system** before putting it into service. The script
   creates no additional configuration backups and does not delete existing
   backup files. Read the script log, check SSH access and review any remaining
   security warnings before accepting the installation.

## Environment File Configuration

The `_SAMPLE.env` file contains all configurable parameters. Copy it and customize for each server.

### Host Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `HOST_NAME` | Server hostname | `webserver01` |
| `HOST_CHASSIS` | System type | `server`, `vm`, `container`, `desktop` |
| `HOST_DEPLOYMENT` | Environment | `production`, `staging`, `development` |
| `HOST_LOCATION` | Physical location | `Datacenter`, `Munich`, `Rack-A1` |

### User Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `ADMIN_EMAIL` | Admin contact email | `admin@example.com` |
| `ADMIN_IPS` | Allowed SSH source IPs (space-separated) | `192.168.1.0/24 10.0.0.0/8` |
| `ADMIN_PUBLICKEY` | SSH public key for admin | `ssh-rsa AAAA...` |
| `ADMIN_USER` | Admin username (created during install) | `administrator` |

### Time Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `NTP_SERVER` | Primary NTP servers (space-separated) | `0.de.pool.ntp.org 1.de.pool.ntp.org` |
| `NTP_FALLBACKSERVER` | Fallback NTP servers | `141.76.10.160 130.149.7.7` |
| `TIMEZONE` | Server timezone | `Europe/Berlin` |

### SSH Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `SSH_GROUP` | Group allowed SSH access | `sshd_users` |
| `SSH_PORT` | SSH listen port | `22` or custom port |

### Monitoring Firewall Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `MONITORING_CLUSTER_NODE_IPS` | Same-cluster node IPs allowed to scrape node-exporter on TCP 9100, kube-vip on TCP 2112 and MetalLB speaker on TCP 9120 | `192.0.2.11 192.0.2.12 192.0.2.13` |

### Login Banner Configuration

| Variable | Description |
|----------|-------------|
| `ISSUE_SHORT` | Short warning message for login prompt |
| `ISSUE_TEXT` | Full legal warning text (displayed before login) |
| `MOTD_TEXT` | Message of the day (displayed after login) |

### Optional Security Services

| Variable | Description | Default |
|----------|-------------|---------|
| `AIDE_ENABLE` | Enable AIDE file integrity monitoring | `false` |
| `AUDIT_ENABLE` | Enable auditd system auditing | `false` |
| `PSAD_ENABLE` | Enable PSAD intrusion detection | `false` |

### NUT (Network UPS Tools) Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `UPS_NUT_HOST` | Hostname or IP of the NUT server | `ups-network.example.com` |
| `UPS_NUT_NAME` | Name of the UPS on the server | `ups` |
| `UPS_NUT_USER` | Username for NUT authentication | `nutuser` |
| `UPS_NUT_PASSWORD` | Password for NUT authentication | `secure_password` |
| `UPS_NUT_BATTERY_DELAY` | Shutdown delay (seconds) after UPS goes on battery | `10` |

## Scripts

### 21-harden-ubuntu.sh - System Hardening

Comprehensive hardening script for Ubuntu Server 24.04 LTS based on CIS benchmarks and security best practices.

**Usage:**

```bash
sudo ./21-harden-ubuntu.sh <server-name>
```

**Features:**

#### Package Management

- Configures APT security settings
- Removes unnecessary/insecure packages
- Installs security tools (debsums, haveged, rkhunter, etc.)
- Enables unattended security updates
- Disables unattended-upgrades mail and enables syslog logging

#### Kernel Hardening

- Disables IPv6 (configurable)
- Hardens network stack (sysctl parameters)
- Disables unused kernel modules (filesystems, network protocols)
- Configures kernel lockdown mode

##### Authentication & Authorization

- Configures PAM for strong passwords (pwquality)
- Sets password aging policies
- Implements account lockout (faillock)
- Restricts su access to sudo group
- Configures sudo logging and security

#### SSH Security

- Generates new strong host keys
- Removes weak Diffie-Hellman moduli
- Configures strong ciphers and MACs
- Disables password authentication
- Restricts access to specified group and IPs

#### Firewall Configuration

- Enables UFW with deny-all default
- Configures logging for PSAD integration
- Allows SSH from specified admin IPs only
- Optionally allows same-cluster nodes to scrape node-exporter, kube-vip and MetalLB speaker metrics
- Configures TCP wrapper (hosts.allow/deny)

#### System Security

- Hardens file permissions
- Secures GRUB configuration
- Disables core dumps
- Configures secure mount options
- Restricts compiler access

#### Monitoring & Logging

- Configures journald for persistent logging
- Sets up logrotate with compression
- Optionally enables auditd with comprehensive rules
- Optionally enables AIDE file integrity checking
- Optionally enables PSAD port scan detection

---

### 31-install-nut-client.sh - NUT Client Setup

Installs and configures Network UPS Tools (NUT) client for graceful shutdown during power outages.

**Usage:**

```bash
sudo ./31-install-nut-client.sh <server-name>
```

**Features:**

- Installs nut-client package
- Configures netclient mode (client only, no UPS server)
- Connects to remote NUT server with authentication
- Implements delayed shutdown with auto-cancellation
- Shuts down server after configurable delay when UPS goes on battery
- Automatically cancels shutdown if power returns within delay period
- Provides comprehensive logging and status monitoring

**Configuration:**

All settings are configured via environment variables in the server's `.env` file:

- `UPS_NUT_HOST`: NUT server hostname/IP
- `UPS_NUT_NAME`: UPS device name on the server
- `UPS_NUT_USER`: Authentication username
- `UPS_NUT_PASSWORD`: Authentication password
- `UPS_NUT_BATTERY_DELAY`: Shutdown delay in seconds (default: 10)

**Monitoring:**

After installation, use these commands to monitor UPS status:

```bash
# Check UPS status
upsc ups@ups-server.example.com

# Monitor service status
systemctl status nut-monitor

# View real-time logs
journalctl -u nut-monitor -f

# View UPS events
journalctl -t upssched-cmd -f
```

---

## Troubleshooting

### Focused Maintenance on Existing Hosts

Do not rerun the full hardening script on existing cluster nodes. The focused
configuration helpers create no backups and do not trigger package upgrades or
node reboots. They may reload the specific policy named in their documentation. Apply the
fwupd plugin configuration with a separate controlled fwupd service restart,
then verify that the actual NVMe devices remain visible and no SPI errors recur. Package maintenance is a separate, explicitly authorized step.

Disable unattended-upgrades mail on each host and keep update results in the
existing local log, journal and Loki pipeline:

```bash
sudo bash Linux/41-configure-unattended-logging.sh --apply
bash Linux/41-configure-unattended-logging.sh --check
```

The helper writes `/etc/apt/apt.conf.d/99zz-homelab-unattended-upgrades` with an
empty `Unattended-Upgrade::Mail` and `Unattended-Upgrade::SyslogEnable "true"`.
It checks the effective APT configuration, including overrides from other files.
The setting applies on the next unattended-upgrades run, without a service restart.
Existing `/var/log/unattended-upgrades/` files remain available. Verify journal
collection separately in Loki because enabling syslog does not configure a collector.
The [unattended-upgrades configuration reference](https://github.com/mvo5/unattended-upgrades#supported-options)
documents both settings.

```bash
journalctl -t unattended-upgrade --since today
```

On **dumbledore only**, remove smartmontools because the node's storage does not
expose SMART:

```bash
sudo bash Linux/42-remove-dumbledore-smartmontools.sh --check
sudo bash Linux/42-remove-dumbledore-smartmontools.sh --apply
```

The helper verifies the hostname and simulates the purge before changing anything.
It refuses a plan that changes other packages, does not use autoremove, and only
clears failed `smartmontools.service` or `smartd.service` states after their unit
files are gone. It makes no disk or hardware queries. Removing this package does
not prove disk health, use kernel and storage logs for nodes without SMART support.

### Package Upgrades and Cleanup

```bash
sudo bash Linux/44-update-host-packages.sh --check
sudo bash Linux/44-update-host-packages.sh --apply
```

`--check` uses the currently cached package indexes and reports both simulations.
`--apply` refreshes indexes, performs an upgrade with new dependencies allowed
and package removals forbidden, then simulates and validates `autoremove` before
removing unused packages. It finishes with `autoclean` and package-state checks.
The helper rejects an autoremove plan containing the running kernel or the
listed core host/storage dependencies. It preserves local dpkg configuration,
uses bounded lock waits and lowers CPU/I/O priority. Review any held-back or
phased packages instead of silently switching to `dist-upgrade`.

The helper sets needrestart to list-only mode and never reboots a node. Package
maintainer scripts can still restart their own services during an upgrade.
Use the approved maintenance window, check cluster/volume health after each
batch and schedule any reported reboot separately. The full new-installation
hardening script retains its separate `dist-upgrade` path. See the
[APT reference](https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html),
[needrestart reference](https://manpages.ubuntu.com/manpages/noble/man1/needrestart.1.html)
and [Canonical's service-restart explanation](https://discourse.ubuntu.com/t/needrestart-changes-in-ubuntu-24-04-service-restarts/44671).

### Ubuntu Pro AppArmor Policy Repair

```bash
sudo bash Linux/22-repair-ubuntu-pro-apparmor.sh --check
sudo bash Linux/22-repair-ubuntu-pro-apparmor.sh --apply
```

The helper verifies the installed vendor hashes, adds only the two official
firmware-read rules to the retained ESM policy and preserves APT News byte for
byte. It parses both files, reloads only their profiles and verifies all expected
labels in the kernel, including child profiles. It needs no Pro subscription
and does not attach the host. Missing or changed vendor input is an error.

### Shared Host Maintenance Policy

```bash
sudo bash Linux/43-configure-host-maintenance.sh --check
sudo bash Linux/43-configure-host-maintenance.sh --apply
```

On a **Raspberry Pi 5**, add `--disable-flashrom` to either command to disable the
unused fwupd Flashrom plugin on the existing homelab hosts. The helper verifies the firmware model before
accepting that option. Other models use the normal command without this flag.
The full hardening script selects the flag from the firmware model automatically.
This is not a reason to disable firmware updates globally.

The helper makes the already effective `PermitRootLogin no` visible in the SSH
main file to rkhunter 1.4.6, preserving the complete effective SSH configuration.
It disables rkhunter APT_AUTOGEN while preserving its scheduled checks and
existing file-property database. It removes quotes only from the unsupported
`WEB_CMD="/bin/false"` setting, retaining the disabled download command. An exact
`ALLOWHIDDENFILE=/etc/.updated` exception is added only after verifying the
root-owned, regular systemd timestamp marker against its complete expected
content and mode. Unknown content is an error, and no broad path exception is
added. It does not modify USBGuard or trust a suspicious
port merely because a known process owns its socket.
Validate the process, package hash and destination before a narrow exception.
Do not use a global port whitelist or refresh the rkhunter baseline to hide an
unexplained warning.

Helper 43 then runs helpers 45 and 46 with the same `--check` or `--apply` mode.
Check mode reports planned changes without removing artifacts or installing
policy. Apply removes only verified, unused resolver and libqb/USBGuard SHM
artifacts. Legacy blkid files are device-discovery caches, not filesystem data.
They are removed only after validating their content, proving that the modern
cache is present and confirming that configuration and running processes do
not use the old paths. Unknown files and active mappings are retained.

The USBGuard helper verifies the active process and its mapped SHM files before
recording exact paths in the rkhunter policy. It installs a policy refresh before
the existing vendor cron scan, so newly created mappings are checked again.
It uses no path globs or blanket hidden-file exceptions. Existing file-property
baselines and backups are preserved. These focused helpers create no additional
backups and restart no service. New-host hardening already invokes helper 43
after activating USBGuard, so do not duplicate that integration.

An existing rkhunter APT hook with `APT_AUTOGEN` enabled can automatically update
its file-property baseline during a package purge. This occurred during the
smartmontools purge on dumbledore. The shared policy disables that automatic
baseline regeneration. Investigate changed files before accepting a new baseline.
The full hardening script initializes a missing baseline only at the end of a
trusted new installation. It preserves every existing baseline. A missing
baseline on an existing host must be investigated, not treated as proof of a
clean installation. See the [rkhunter reference](https://manpages.ubuntu.com/manpages/noble/man8/rkhunter.8.html).

The existing twelve homelab nodes do not expose SMART according to the operator.
Do not install SMART tools or run SMART probes on them. Check bounded kernel and
K3s logs, storage paths, temperature/voltage indicators and I/O metrics instead.
For different new hardware, confirm its capabilities separately.

### Check Script Logs

```bash
cat 21-harden-ubuntu.log
```

### Verify SSH Configuration

```bash
sudo sshd -t
sudo systemctl status ssh
```

### Check Firewall Status

```bash
sudo ufw status verbose
```

### Verify AppArmor Status

```bash
sudo aa-status
```

### Check Auditd Status (if enabled)

```bash
sudo auditctl -s
sudo aureport --summary
```

### Check AIDE Status (if enabled)

```bash
sudo systemctl status aidecheck.timer
```

### Backup Policy

Do not create additional backups, volume snapshots or restore tests for this
maintenance workflow. Reuse the single nightly Longhorn/PostgreSQL backup-status
check for the update cycle and report missing or failed evidence. Those backups
do not by themselves prove that host configuration files are recoverable.
Pre-existing `.hardening-backup` files are left untouched, the current hardening
script no longer creates them.

## Security Considerations

⚠️ **Important Security Notes:**

1. **Do not expose servers to the internet** before running the hardening script
2. **Test in a non-production environment** first
3. **Verify SSH access** before disconnecting from the initial session
4. **Keep backup access** (console access) available during initial setup
5. **Review firewall rules** to ensure they match your network requirements
6. **Optional services** (AIDE, auditd, PSAD) add security but consume resources

## Ubuntu Pro Integration

After hardening, you can optionally enable Ubuntu Pro for additional security updates:

```bash
sudo apt install ubuntu-advantage-tools
sudo pro attach <token>
sudo pro enable esm-apps
sudo pro enable esm-infra
sudo pro enable livepatch  # Only on supported kernels (amd64)
```

### Repair retained Ubuntu Pro AppArmor policy

An Ubuntu Pro package update can leave a new `ubuntu_pro_esm_cache.dpkg-dist`
beside a retained local policy. If that retained policy lacks the upstream
firmware read rules, the cache process can be denied access to the hardware
model. The dedicated helper adds only these two official read rules:

- `/sys/firmware/devicetree/base/model` in `ubuntu_pro_esm_cache`.
- `/sys/firmware/dmi/entries/0-0/raw` in the related
  `ubuntu_pro_esm_cache_systemd_detect_virt` profile declared in the same file.

Run the check first, then explicitly apply the reviewed repair:

```bash
sudo bash ./22-repair-ubuntu-pro-apparmor.sh --check
sudo bash ./22-repair-ubuntu-pro-apparmor.sh --apply
```

Omitting the option also selects `--check`. Both modes require root, the
installed `ubuntu-pro-client` package, Python 3 and `apparmor_parser`. No
environment file or credentials are read. The helper checks the `.dpkg-dist`
against the installed package's conffile hash and verifies both rules in their
proper scopes. If `.dpkg-dist` is absent, the active file must itself match the
installed package hash. Unrecognized or ambiguous profile structures stop the
repair.

Existing policy content and local override files are preserved. The check
compiles a private temporary candidate with `-Q -K --jobs=1`, using the existing
AppArmor include directory, without replacing files or loading kernel policy.
The temporary candidate is removed on exit. The helper creates no backup,
snapshot or original-file copy.

Apply rechecks the original file and its permissions before an atomic
replacement, preserves ownership and mode, and reloads only the repaired file
and the other profiles declared in that same policy file. It creates no
additional rules on a repeated run.
If the targeted reload fails after replacement, the helper reports the repaired
on-disk state separately from the unverified loaded state. Resolve that parser
error and rerun `--apply`.

The helper is not called automatically by the hardening script. It does not
replace the entire vendor profile, enforce all host profiles, modify
`ubuntu_pro_apt_news`, or change AppArmor's global mode. Verify the original
denied operation and fresh logs after applying. A parser check alone does not
prove that the application's hardware read succeeds.

References: [Canonical's firmware-access regression test](https://github.com/canonical/ubuntu-pro-client/blob/main/sru/release-37/test-apparmor-firmware-access.sh)
and [Ubuntu's AppArmor parser documentation](https://manpages.ubuntu.com/manpages/noble/man8/apparmor_parser.8.html).

## Related Resources

- [Ubuntu Server Guide](https://ubuntu.com/server/docs)
- [CIS Benchmarks](https://www.cisecurity.org/benchmark/ubuntu_linux)
- [Ubuntu Security Notices](https://ubuntu.com/security/notices)
- [Auditd Documentation](https://linux.die.net/man/8/auditd)
- [AppArmor Wiki](https://gitlab.com/apparmor/apparmor/-/wikis/home)
