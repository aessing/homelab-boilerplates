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
├── 31-install-nut-client.sh  # NUT (Network UPS Tools) client setup
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
- Log all actions to `11-install-k3s.log`

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

3. **Clean up backup files** after verifying everything works:

   ```bash
   sudo find /etc -name "*.hardening-backup" -type f -exec rm -f "{}" \;
   ```

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

### Check Script Logs

```bash
cat 11-install-k3s.log
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

### Restore from Backup

If something goes wrong, backup files are saved with `.hardening-backup` extension:

```bash
# List all backup files
find /etc -name "*.hardening-backup" -type f

# Restore a specific file
sudo cp /etc/ssh/sshd_config.hardening-backup /etc/ssh/sshd_config
sudo systemctl restart ssh
```

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

## Related Resources

- [Ubuntu Server Guide](https://ubuntu.com/server/docs)
- [CIS Benchmarks](https://www.cisecurity.org/benchmark/ubuntu_linux)
- [Ubuntu Security Notices](https://ubuntu.com/security/notices)
- [Auditd Documentation](https://linux.die.net/man/8/auditd)
- [AppArmor Wiki](https://gitlab.com/apparmor/apparmor/-/wikis/home)
