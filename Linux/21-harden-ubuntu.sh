#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ALL NODES WITH NODE ENVIRONMENT FILE
###############################################################################

# =============================================================================
# Linux Hardening Script
# Ubuntu Server 24.04 LTS
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# Inspired by.....: https://downloads.cisecurity.org/
#                   https://github.com/konstruktoid/hardening
#                   https://github.com/Neo23x0/auditd
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

set -u -o pipefail

LOG_FILE="11-install-k3s.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# Linux Hardening Script"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://github.com/aessing)"
echo "#                                (https://www.linkedin.com/in/aessing/)"
echo "# Inspired by.....: https://downloads.cisecurity.org/"
echo "#                   https://github.com/konstruktoid/hardening"
echo "#                   https://github.com/Neo23x0/auditd"
echo "# -----------------------------------------------------------------------------"
echo "# THIS CODE AND INFORMATION ARE PROVIDED \"AS IS\" WITHOUT WARRANTY OF ANY KIND,"
echo "# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED"
echo "# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE."
echo "# ============================================================================="

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SETTING WORK ENVIRONMENT (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Switching to script directory"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || {
    echo " - Error: Couldn't change into script directory $SCRIPT_DIR"
    exit 1
}

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# PERFORMING SOME CHECKS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Are you running BASH?"
if [ -z "${BASH_VERSION:-}" ]; then
  echo ""
  echo " - Sorry, this script requires bash. Exiting."
  exit 1
fi

echo ""
echo " - Are you using SYSTEMCTL?"
if ! [ -x "$(command -v systemctl)" ]; then
  echo ""
  echo " - systemctl required. Exiting."
  exit 1
fi

echo ""
echo " - Are you root?"
if [ "$EUID" -ne 0 ]; then
  echo ""
  echo " - Not root or not enough privileges. Exiting."
  echo
  exit 1
fi

echo ""
echo " - Are you running Ubuntu?"
if ! lsb_release -i | grep -sq 'Ubuntu'; then
  echo ""
  echo " - Ubuntu only. Exiting."
  echo
  exit 1
fi

echo ""
echo " - Have you started the script with parameter?"
if [ "$#" -ne 1 ]; then
  echo ""
  echo " - Script needs environment file with variables as parameter."
  echo "   Usage: $0 <server-name> || <env-file-name-without-extension>"
  echo "   Exiting."
  echo
  exit 1
fi

ENV_FILE="./environments/$1.env"

echo ""
echo " - Does the .env file exists?"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo " - Script needs environment file with variables."
  echo "   File '$ENV_FILE' not found!"
  echo "   Exiting."
  echo
  exit 1
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# VARIABLES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Loading environment variables from '$ENV_FILE'"
set -o allexport
if ! source "$ENV_FILE"; then
  echo " - ERROR: Could not load environment file '$ENV_FILE'"
  exit 1
fi
set +o allexportreboot

echo ""
echo " - Validating required environment variables"
REQUIRED_VARS=(HOST_NAME HOST_CHASSIS HOST_DEPLOYMENT HOST_LOCATION ADMIN_EMAIL ADMIN_IPS ADMIN_PUBLICKEY ADMIN_USER NTP_SERVER NTP_FALLBACKSERVER TIMEZONE SSH_GROUP SSH_PORT ISSUE_SHORT ISSUE_TEXT MOTD_TEXT AIDE_ENABLE AUDIT_ENABLE PSAD_ENABLE)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo " - ERROR: Required variable '$var' not set in environment file"
    exit 1
  fi
done

echo ""
echo " - Setting some path variables"
ADDUSER_CONF='/etc/adduser.conf'
AIDE_CONF='/etc/aide/aide.conf'
AIDED='/etc/aide/aide.conf.d'
APT_CONF_HARDENING='/etc/apt/apt.conf.d/90hardening-ubuntu'
APT_CONF_PERIODIC='/etc/apt/apt.conf.d/90hardening-periodic'
APT_CONF_UNATTENDED='/etc/apt/apt.conf.d/50unattended-upgrades'
AUDITD_CONF='/etc/audit/auditd.conf'
AUDITD_CONF_SERVICE='/lib/systemd/system/auditd.service'
AUDITD_RULES='/etc/audit/rules.d/hardening.rules'
AUTOLOGOUT_SCRIPT='/etc/profile.d/hardening-autologout.sh'
CLOUDINIT_CONF='/etc/cloud/cloud.cfg'
COMMONACCOUNT_CONF='/etc/pam.d/common-account'
COMMONAUTH_CONF='/etc/pam.d/common-auth'
COMMONPASSWD_CONF='/etc/pam.d/common-password'
COREDUMP_CONF='/etc/systemd/coredump.conf'
FAIL2BAN_CONF='/etc/fail2ban/jail.local'
FAILLOCK_CONF='/etc/security/faillock.conf'
FSTAB_CONF='/etc/fstab'
GRUB_CONF_DEFAULT='/etc/default/grub'
GRUB_DEFAULT='/etc/default/grub.d'
HASHSIZE="/sys/module/nf_conntrack/parameters/hashsize"
HOSTS_ALLOW='/etc/hosts.allow'
HOSTS_DENY='/etc/hosts.deny'
INITPATH_SCRIPT='/etc/profile.d/hardening-initpath.sh'
ISSUE_CONF='/etc/issue'
ISSUENET_CONF='/etc/issue.net'
JOURNALD_CONF='/etc/systemd/journald.conf'
LIMITS_CONF='/etc/security/limits.conf'
LOCKDOWN="/sys/kernel/security/lockdown"
LOGROTATE_CONF='/etc/logrotate.conf'
LOGIND_CONF='/etc/systemd/logind.conf'
LOGINDEFS_CONF='/etc/login.defs'
MOTD_CONF='/etc/motd'
NSSWITCH_CONF='/etc/nsswitch.conf'
PAM_CONF_LOGIN='/etc/pam.d/login'
PAM_CONF_SU='/etc/pam.d/su'
PSAD_CONF='/etc/psad/psad.conf'
PSAD_DL='/etc/psad/auto_dl'
RESOLVED_CONF='/etc/systemd/resolved.conf'
RKHUNTER_CONF='/etc/default/rkhunter'
RSYSLOG_CONF='/etc/rsyslog.conf'
SECURITYACCESS_CONF='/etc/security/access.conf'
SSH_CONF='/etc/ssh/ssh_config'
SSHD_CONF='/etc/ssh/sshd_config'
SSHDD=/etc/ssh/sshd_config.d
SUDOERSD='/etc/sudoers.d/'
SYSCTL_CONF='/etc/sysctl.conf'
SYSCTLD='/etc/sysctl.d'
SYSSTAT_DEFAULT='/etc/default/sysstat'
SYSTEM_CONF='/etc/systemd/system.conf'
TIMESYNCD_CONF='/etc/systemd/timesyncd.conf'
UFW_DEFAULT='/etc/default/ufw'
UFW_CONF_BEFORE='/etc/ufw/before.rules'
UFW_CONF_BEFORE6='/etc/ufw/before6.rules'
UFW_CONF_AFTER='/etc/ufw/after.rules'
UFW_CONF_AFTER6='/etc/ufw/after6.rules'
USBGUARD_CONF='/etc/usbguard/rules.conf'
USERADD_CONF='/etc/default/useradd'
USER_CONF='/etc/systemd/user.conf'

echo ""
echo " - Setting up some lists"
APT_PACKAGES="apt-utils bind9-dnsutils cracklib-runtime debsums fwupd gnupg2 haveged htop jq iputils-ping libpam-pwquality libpam-tmpdir nano needrestart net-tools procps secureboot-db tcpd update-notifier-common vim vlock"
APT_PACKAGES_PURGE='apache2 apport* alsa-* autofs avahi* beep bind9 chrony cups cyrus-imapd dovecot-core dovecot-imapd dovecot-pop3d ftp gdm3 git iptables-persistent isc-dhcp-server ldap-utils mcstrans nfs-kernel-server nis nginx ntp pastebinit popularity-contest rpcbind rsh* rsync samba slapd snmp squid talk* telnet* tftp* ubuntu-report vsftpd whoopsie wpasupplicant xinetd xserver-xorg* yp-tools ypbind* ypserv'
MODULES_DISABLE_CMN='bluetooth bnep btusb cpia2 firewire-core floppy n_hdlc net-pf-31 pcspkr soundcore thunderbolt usb-midi usb-storage uvcvideo v4l2_common'
MODULES_DISABLE_FS='cifs cramfs fat freevxfs gfs2 jffs2 hfs hfsplus nfs nfsv3 nfsv4 squashfs udf vfat'
MODULES_DISABLE_NET='appletalk dccp sctp rds tipc'

echo ""
echo " - Setting up some aliases"
APT="apt-get --assume-yes --no-install-recommends -qq"

echo ""
echo " - Setting up some more stuff"
if resolvectl status >/dev/null 2>&1; then
  SERVERIP="$(ip route get "$(resolvectl status | grep -E 'DNS (Server:|Servers:)' | tail -n1 | awk '{print $NF}')" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | tail -n1)"
else
  SERVERIP="$(ip route get "$(grep '^nameserver' /etc/resolv.conf | tail -n1 | awk '{print $NF}')" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | tail -n1)"
fi

export TERM='linux'
export DEBIAN_FRONTEND='noninteractive'
export NEEDRESTART_MODE='a'

echo ""
echo " - Stopping Unattended Upgrades to not interfere with the next steps"
systemctl stop unattended-upgrades.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# HOSTNAME (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Setting hostname"
hostnamectl set-hostname "$HOST_NAME"

echo ""
echo " - Setting host chassis type"
hostnamectl set-chassis "$HOST_CHASSIS"

echo ""
echo " - Setting host deployment environment"
hostnamectl set-deployment "$HOST_DEPLOYMENT"

echo ""
echo " - Setting host location"
hostnamectl set-location "$HOST_LOCATION"

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CLOUDINIT (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Disable Cloud-Init"
touch /etc/cloud/cloud-init.disabled

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# APT (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Configuring APT settings"
if ! grep '^Acquire::http::AllowRedirect' /etc/apt/apt.conf.d/* ; then
  echo 'Acquire::http::AllowRedirect "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*Acquire::http::AllowRedirect*/Acquire::http::AllowRedirect "false";/g' "$(grep -l 'Acquire::http::AllowRedirect' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^APT::Get::AllowUnauthenticated' /etc/apt/apt.conf.d/* ; then
  echo 'APT::Get::AllowUnauthenticated "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*APT::Get::AllowUnauthenticated.*/APT::Get::AllowUnauthenticated "false";/g' "$(grep -l 'APT::Get::AllowUnauthenticated' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^APT::Periodic::AutocleanInterval' /etc/apt/apt.conf.d/*; then
  echo 'APT::Periodic::AutocleanInterval "7";' >> "$APT_CONF_PERIODIC"
else
  sed -i 's/.*APT::Periodic::AutocleanInterval.*/APT::Periodic::AutocleanInterval "7";/g' "$(grep -l 'APT::Periodic::AutocleanInterval' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^APT::Install-Recommends' /etc/apt/apt.conf.d/*; then
  echo 'APT::Install-Recommends "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*APT::Install-Recommends.*/APT::Install-Recommends "false";/g' "$(grep -l 'APT::Install-Recommends' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^APT::Get::AutomaticRemove' /etc/apt/apt.conf.d/*; then
  echo 'APT::Get::AutomaticRemove "true";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*APT::Get::AutomaticRemove.*/APT::Get::AutomaticRemove "true";/g' "$(grep -l 'APT::Get::AutomaticRemove' /etc/apt/apt.conf.d/*)"
fi 

if ! grep '^APT::Install-Suggests' /etc/apt/apt.conf.d/*; then
  echo 'APT::Install-Suggests "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*APT::Install-Suggests.*/APT::Install-Suggests "false";/g' "$(grep -l 'APT::Install-Suggests' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Acquire::AllowDowngradeToInsecureRepositories' /etc/apt/apt.conf.d/*; then
  echo 'Acquire::AllowDowngradeToInsecureRepositories "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*Acquire::AllowDowngradeToInsecureRepositories.*/Acquire::AllowDowngradeToInsecureRepositories "false";/g' "$(grep -l 'Acquire::AllowDowngradeToInsecureRepositories' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Acquire::AllowInsecureRepositories' /etc/apt/apt.conf.d/*; then
  echo 'Acquire::AllowInsecureRepositories "false";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*Acquire::AllowInsecureRepositories.*/Acquire::AllowInsecureRepositories "false";/g' "$(grep -l 'Acquire::AllowInsecureRepositories' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^APT::Sandbox::Seccomp' /etc/apt/apt.conf.d/*; then
  echo 'APT::Sandbox::Seccomp "1";' >> "$APT_CONF_HARDENING"
else
  sed -i 's/.*APT::Sandbox::Seccomp.*/APT::Sandbox::Seccomp "1";/g' "$(grep -l 'APT::Sandbox::Seccomp' /etc/apt/apt.conf.d/*)"
fi

if ! grep -iq "Raspberry" /sys/firmware/devicetree/base/model 2>/dev/null; then
  echo ""
  echo " - Remount /tmp before APT operations, so that it is noexec doesn't affect updates"
  echo 'DPkg::Pre-Invoke {"mount -o remount,nodev,exec,nosuid,noatime /tmp";};' >> /etc/apt/apt.conf.d/90hardening-noexec-tmp
  echo 'DPkg::Post-Invoke {"mount -o remount,nodev,noexec,nosuid,noatime /tmp";};' >> /etc/apt/apt.conf.d/90hardening-noexec-tmp
fi

echo ""
echo " - Updating APT cache"
$APT update

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# REMOVING PACKAGES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Remove packages that are not required or unsafe"
for deb_remove in $APT_PACKAGES_PURGE; do
  echo ""
  echo "   - Purging $deb_remove"
  $APT purge "$deb_remove"
done

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# UPGRADING PACKAGES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Upgrading Installing packages to latest version"
$APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" dist-upgrade

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# INSTALLING PACKAGES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Detecting hypervisor"
if dmesg | grep -i -E "dmi.*vmware"; then
  APT_PACKAGES_HYPERVISOR="open-vm-tools"
elif dmesg | grep -i -E "dmi.*virtualbox"; then
  APT_PACKAGES_HYPERVISOR="virtualbox-guest-dkms virtualbox-guest-utils"
elif dmesg | grep -i -E "dmi.*QEMU"; then
  APT_PACKAGES_HYPERVISOR="qemu-guest-agent"
elif dmesg | grep -i -E "dmi.*Parallels"; then
  APT_PACKAGES_HYPERVISOR=" "
else
  APT_PACKAGES_HYPERVISOR=" "
fi

echo ""
echo " - Installing additional packages"
PACKAGE_INSTALL="$APT_PACKAGES $APT_PACKAGES_HYPERVISOR"
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# UNATTENDED UPGRADES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='unattended-upgrades'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$APT_CONF_UNATTENDED"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
    cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Change configuration"
if ! grep '^Unattended-Upgrade::Mail\b' /etc/apt/apt.conf.d/*; then
  echo 'Unattended-Upgrade::Mail "root";' >> "$APT_CONF_UNATTENDED"
else
  sed -i 's/.*Unattended-Upgrade::Mail\b.*/Unattended-Upgrade::Mail "root";/g' "$(grep -l 'Unattended-Upgrade::Mail "root";' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Unattended-Upgrade::Remove-Unused-Kernel-Packages\b' /etc/apt/apt.conf.d/*; then
  echo 'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";' >> "$APT_CONF_UNATTENDED"
else
  sed -i 's/.*Unattended-Upgrade::Remove-Unused-Kernel-Packages\b.*/Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";/g' "$(grep -l 'Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Unattended-Upgrade::Remove-New-Unused-Dependencies\b' /etc/apt/apt.conf.d/*; then
  echo 'Unattended-Upgrade::Remove-New-Unused-Dependencies "true";' >> "$APT_CONF_UNATTENDED"
else
  sed -i 's/.*Unattended-Upgrade::Remove-New-Unused-Dependencies\b.*/Unattended-Upgrade::Remove-New-Unused-Dependencies "true";/g' "$(grep -l 'Unattended-Upgrade::Remove-New-Unused-Dependencies "true";' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Unattended-Upgrade::Remove-Unused-Dependencies\b' /etc/apt/apt.conf.d/*; then
  echo 'Unattended-Upgrade::Remove-Unused-Dependencies "true";' >> "$APT_CONF_UNATTENDED"
else
  sed -i 's/.*Unattended-Upgrade::Remove-Unused-Dependencies\b.*/Unattended-Upgrade::Remove-Unused-Dependencies "true";/g' "$(grep -l 'Unattended-Upgrade::Remove-Unused-Dependencies "true";' /etc/apt/apt.conf.d/*)"
fi

if ! grep '^Unattended-Upgrade::SyslogEnable\b.*' /etc/apt/apt.conf.d/*; then
  echo 'Unattended-Upgrade::SyslogEnable "true";' >> "$APT_CONF_UNATTENDED"
else
  sed -i 's/.*Unattended-Upgrade::SyslogEnable\b.*/Unattended-Upgrade::SyslogEnable "true";/g' "$(grep -l 'Unattended-Upgrade::SyslogEnable "true";' /etc/apt/apt.conf.d/*)"
fi

echo ""
echo " - Stopping Unattended Upgrades to not interfere with the next steps"
systemctl stop unattended-upgrades.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# PRELINK (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Removing PRELINK"
if dpkg -l | grep prelink 1> /dev/null; then
  "$(command -v prelink)" -ua 2> /dev/null
  $APT purge prelink
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# FSTAB (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$FSTAB_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
    cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
done

echo ""
echo " - Remove floppy from FSTAB"
sed -i '/floppy/d' "$FSTAB_CONF"

if ! cat /sys/firmware/devicetree/base/model 2>/dev/null | grep -iq "Raspberry"; then
  echo ""
  echo " - Creating temporary FSTAB"
  TMPFSTAB=$(mktemp --tmpdir fstab.XXXXX)

  echo ""
  echo " - Write partions wihout changes to temporary FSTAB"
  grep -v -E '[[:space:]]/boot[[:space:]]|[[:space:]]/home[[:space:]]|[[:space:]]/tmp[[:space:]]|[[:space:]]/var[[:space:]]|[[:space:]]/var/crash[[:space:]]|[[:space:]]/var/log[[:space:]]|[[:space:]]/var/log/audit[[:space:]]|[[:space:]]/var/tmp[[:space:]]' "$FSTAB_CONF"  > "$TMPFSTAB"

  echo ""
  echo " - Write partions with enhanced security to temporary FSTAB"
  if grep -q '[[:space:]]/boot[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/boot[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,nosuid/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/home[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/home[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,nosuid,usrquota,grpquota/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/tmp[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/tmp[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,noexec,nosuid,noatime/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/var[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/var[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,nosuid/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/var/crash[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/var/crash[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,noexec,nosuid/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/var/log[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/var/log[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,noexec,nosuid/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/var/log/audit[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/var/log/audit[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,noexec,nosuid/g' >> "$TMPFSTAB"
  fi

  if grep -q '[[:space:]]/var/tmp[[:space:]].*' "$FSTAB_CONF"; then
    grep '[[:space:]]/var/tmp[[:space:]].*' "$FSTAB_CONF" | sed 's/defaults/defaults,nodev,noexec,nosuid,noatime/g' >> "$TMPFSTAB"
  fi

  echo ""
  echo " - Copy temporary fstab to FSTAB"
  cp "$TMPFSTAB" "$FSTAB_CONF"
fi

echo ""
echo " - Add secure temporary filesystems to FSTAB"
echo '' >> "$FSTAB_CONF"
if ! grep -q '/run/shm ' "$FSTAB_CONF"; then
  echo 'none /run/shm tmpfs rw,nodev,noexec,nosuid 0 0' >> "$FSTAB_CONF"
fi
if ! grep -q '/dev/shm ' "$FSTAB_CONF"; then
  echo 'none /dev/shm tmpfs rw,nodev,noexec,nosuid 0 0' >> "$FSTAB_CONF"
fi
if ! grep -q '/proc ' "$FSTAB_CONF"; then
  echo 'none /proc proc rw,nodev,noexec,nosuid,relatime,hidepid=2 0 0' >> "$FSTAB_CONF"
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SYSSTAT (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='sysstat'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$SYSSTAT_DEFAULT"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Enabling SYSSTAT"
sed -i 's/ENABLED=.*/ENABLED="true"/' "$SYSSTAT_DEFAULT"
systemctl daemon-reload
systemctl enable sysstat
systemctl restart sysstat

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# PROCESS ACCOUNTING (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='acct'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Enabling Process Accounting service"
systemctl daemon-reload
systemctl enable acct.service
systemctl restart acct.service
accton on

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# KERNEL PARAMETERS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Configuring netfilter hashsize"
if [[ -f "$HASHSIZE" && -w "$HASHSIZE" ]]; then
  echo 1048576 > /sys/module/nf_conntrack/parameters/hashsize
fi

echo ""
echo " - Configuring kernel lockdown mode"
if [[ -f /boot/firmware/cmdline.txt ]]; then
  sed -i 's/^console=serial0,115200.*/& lockdown=confidentiality/g' /boot/firmware/cmdline.txt
else
  if [[ -f "$LOCKDOWN" && -w "$LOCKDOWN" ]]; then
    if ! grep -q 'lockdown=' /proc/cmdline; then
      echo "GRUB_CMDLINE_LINUX=\"\$GRUB_CMDLINE_LINUX lockdown=confidentiality\"" > "$GRUB_DEFAULT/99-hardening-lockdown.cfg"
      update-grub
    fi
  fi
fi

echo ""
echo " - Setting SYSCTL hardening parameters"
echo "
# Disable packet forwarding for IPv4
net.ipv4.ip_forward = 0

# Disable packet forwarding for IPv6
#  Enabling this option disables Stateless Address Autoconfiguration
#  based on Router Advertisements for this host
net.ipv6.conf.all.forwarding = 0
net.ipv6.conf.default.forwarding = 0

# Do not accept ICMP redirects (prevent MITM attacks)
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# Do not send ICMP redirects (we are not a router)
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Accept ICMP redirects only for gateways listed in our default
# gateway list (enabled by default)
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0

# Do not accept IP source route packets (we are not a router)
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# Uncomment the next two lines to enable Spoof protection (reverse-path filter)
# Turn on Source Address Verification in all interfaces to
# prevent some spoofing attacks
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Log Martian Packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Ignore Directed pings
net.ipv4.icmp_echo_ignore_all = 1

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore ICMP bogus error responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Uncomment the next line to enable TCP/IP SYN cookies
# See http://lwn.net/Articles/277146/
# Note: This may impact IPv6 TCP sessions too
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Turning off timestamps could improve security but degrade performance.
# TCP timestamps are used to improve performance as well as protect against
# late packets messing up your data flow. A side effect of this feature is 
# that the uptime of the host can sometimes be computed.
# If you disable TCP timestamps, you should expect worse performance 
# and less reliable connections.
net.ipv4.tcp_timestamps = 1

# disable IPv6 if not required
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1

# [IPv6] Number of Router Solicitations to send until assuming no routers are present.
# This is host and not router.
net.ipv6.conf.all.router_solicitations = 0
net.ipv6.conf.default.router_solicitations = 0

# Accept Router Preference in RA
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.default.accept_ra = 0
net.ipv6.conf.all.accept_ra_rtr_pref = 0
net.ipv6.conf.default.accept_ra_rtr_pref = 0

# Learn prefix information in router advertisement.
net.ipv6.conf.all.accept_ra_pinfo = 0
net.ipv6.conf.default.accept_ra_pinfo = 0

# Setting controls whether the system will accept Hop Limit settings from a router advertisement.
net.ipv6.conf.all.accept_ra_defrtr = 0
net.ipv6.conf.default.accept_ra_defrtr = 0

# Router advertisements can cause the system to assign a global unicast address to an interface.
net.ipv6.conf.all.autoconf = 0
net.ipv6.conf.default.autoconf = 0

# How many neighbor solicitations to send out per address?
net.ipv6.conf.all.dad_transmits = 0
net.ipv6.conf.default.dad_transmits = 0

# How many global unicast IPv6 addresses can be assigned to each interface?
net.ipv6.conf.all.max_addresses = 1
net.ipv6.conf.default.max_addresses = 1

# IPv6 typically uses a device's MAC address when choosing an IPv6 address
# to use in autoconfiguration. Privacy extensions allow using a randomly
# generated IPv6 address, which increases privacy.
#
# Acceptable values:
#    0 - don't use privacy extensions.
#    1 - generate privacy addresses
#    2 - prefer privacy addresses and use them over the normal addresses.
net.ipv6.conf.all.use_tempaddr = 2
net.ipv6.conf.default.use_tempaddr = 2

net.core.bpf_jit_harden = 2
net.ipv4.conf.all.shared_media = 0
net.ipv4.conf.default.shared_media = 0
net.ipv4.tcp_challenge_ack_limit = 2147483647
net.ipv4.tcp_invalid_ratelimit = 500
net.ipv4.tcp_rfc1337 = 1
net.netfilter.nf_conntrack_max = 2000000
net.netfilter.nf_conntrack_tcp_loose = 0
" > "$SYSCTLD/99-hardening-network.conf"

for n in $(find /sys/class/net -mindepth 1 -maxdepth 1 -printf '%f\n' | sort | uniq | sort | uniq); do
  echo "net.ipv6.conf.$n.forwarding = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.accept_redirects = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.accept_redirects = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.send_redirects = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.secure_redirects = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.accept_source_route = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.rp_filter = 1" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.log_martians = 1" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv4.conf.$n.shared_media = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.disable_ipv6 = 1" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.router_solicitations = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.accept_ra = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.accept_ra_rtr_pref = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.accept_ra_pinfo = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.accept_ra_defrtr = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.autoconf = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.dad_transmits = 0" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.max_addresses = 1" >> "$SYSCTLD/99-hardening-network.conf"
  echo "net.ipv6.conf.$n.use_tempaddr = 2" >> "$SYSCTLD/99-hardening-network.conf"
done

echo "
# Magic system request Key
# 0=disable, 1=enable all, >1 bitmask of sysrq functions
# See https://www.kernel.org/doc/html/latest/admin-guide/sysrq.html
# for what other values do
# Disable System Request debugging functionalityv
kernel.sysrq = 0
" > "$SYSCTLD/99-hardening-magicsysreqkey.conf"

echo "
# In rare occasions, it may be beneficial to reboot your server reboot if it runs out of memory.
# This simple solution can avoid you hours of down time. The vm.panic_on_oom=1 line enables panic
# on OOM; the kernel.panic=10 line tells the kernel to reboot ten seconds after panicking.
vm.panic_on_oom = 1
kernel.panic = 10
" > "$SYSCTLD/99-hardening-panic.conf"

echo "
# ExecShield is security Linux kernel patch to avoid worms and other problems.
kernel.exec-shield = 1
" > "$SYSCTLD/99-hardening-execshield.conf"

echo "
# Controls Address Space Layout Randomization (ASLR), which can help defeat certain
# types of buffer overflow attacks
kernel.randomize_va_space = 2
" > "$SYSCTLD/99-hardening-vaspace.conf"

echo "
# Disable core dumps
fs.suid_dumpable = 0
" > "$SYSCTLD/99-hardening-coredumps.conf"

echo "
# Restrict access to kernel logs
kernel.dmesg_restrict = 1
" > "$SYSCTLD/99-hardening-kernellogs.conf"

echo "
# Restrict access to PTRACE system
kernel.yama.ptrace_scope = 1
" > "$SYSCTLD/99-hardening-ptrace.conf"

echo "
# Hide kernel pointers
kernel.kptr_restrict = 2
" > "$SYSCTLD/99-hardening-kernelpointers.conf"

echo "
# Protect the zero page of memory from userspace mmap to prevent kernel
# NULL-dereference attacks against potential future kernel security
# vulnerabilities.  (Added in kernel 2.6.23.)
#
# While this default is built into the Ubuntu kernel, there is no way to
# restore the kernel default if the value is changed during runtime; for
# example via package removal (e.g. wine, dosemu).  Therefore, this value
# is reset to the secure default each time the sysctl values are loaded.
vm.mmap_min_addr = 65536
" > "$SYSCTLD/99-hardening-zeropage.conf"

echo "
fs.protected_fifos = 2
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
" > "$SYSCTLD/99-hardening-fs.conf"

echo "
dev.tty.ldisc_autoload = 0
" > "$SYSCTLD/99-hardening-dev.conf"

echo "
kernel.core_uses_pid = 1
kernel.panic_on_oops = 60
kernel.perf_event_paranoid = 3
kernel.unprivileged_bpf_disabled = 1
" > "$SYSCTLD/99-hardening-kernel.conf"

chmod 0600 $SYSCTLD/99-hardening-*

echo ""
echo " - Restart SYSCTL"
systemctl restart systemd-sysctl.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# COREDUMP (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='systemd-coredump'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$COREDUMP_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Ensure COREDUMP storage is disabled"
sed -i 's/^#\?Storage=.*/Storage=none/' "$COREDUMP_CONF"

echo ""
echo " - Ensure COREDUMP backtraces are disabled"
sed -i 's/^#\?ProcessSizeMax=.*/ProcessSizeMax=0/' "$COREDUMP_CONF"

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# MODULES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

MODULES_DISABLE="$MODULES_DISABLE_CMN $MODULES_DISABLE_FS $MODULES_DISABLE_NET"

echo ""
echo " - Disable unsecure and unused modules"
for MODULE in $MODULES_DISABLE
do
  echo "   - Create file to block module $MODULE"
  echo "install $MODULE /bin/false" > "/etc/modprobe.d/hardening-$MODULE.conf"
  echo "blacklist $MODULE" >> "/etc/modprobe.d/hardening-$MODULE.conf"
done

[ -d /sys/firmware/efi ] && fw="UEFI" || fw="BIOS"
if [ "$fw" == "UEFI" ]; then
  echo ""
  echo " - Enable FAT and VFAT as the filesystems are used by UEFI"
  rm -f /etc/modprobe.d/hardening-fat.conf
  rm -f /etc/modprobe.d/hardening-vfat.conf
fi
if [[ -f /boot/firmware/cmdline.txt ]]; then
  echo ""
  echo " - Enable USB storage to allow Raspberry PI to boot from USB"
  rm -f /etc/modprobe.d/hardening-usb-storage.conf
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# WIRELESS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Disable wireless interfaces if any"
if command -v nmcli >/dev/null 2>&1 ; then
  nmcli radio all off
else
  if [ -n "$(find /sys/class/net/*/ -type d -name wireless)" ]; then
    mname=$(for driverdir in $(find /sys/class/net/*/ -type d -name wireless | xargs -0 dirname); do basename "$(readlink -f "$driverdir"/device/driver/module)";done | sort -u)
    for dm in $mname; do
      echo "install $dm /bin/false" >> /etc/modprobe.d/hardening-wireless.conf
    done
  fi
fi

#echo ""
#echo " - Disable WPA Supplicant Service"
#systemctl stop wpa_supplicant.service 
#systemctl disable wpa_supplicant.service
#systemctl unmask wpa_supplicant.service

#echo ""
#echo " - Reloading SYSTEMD"
#systemctl daemon-reload

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CONFIGS AND LIMITS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$LIMITS_CONF $SYSTEM_CONF $USER_CONF $LOGINDEFS_CONF /etc/init.d/rc /etc/profile /etc/bash.bashrc /etc/environment $LOGIND_CONF $LOGINDEFS_CONF $ADDUSER_CONF $USERADD_CONF $COMMONPASSWD_CONF $COMMONAUTH_CONF $FAILLOCK_CONF $COMMONACCOUNT_CONF $PAM_CONF_LOGIN $SYSTEM_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Setting soft and hard limits"
sed -i 's/^#\? End of file*//' "$LIMITS_CONF"
{ echo '* hard maxlogins 10'
  echo '* hard core 0'
  echo '* soft nproc 512'
  echo '* hard nproc 1024'
  echo '# End of file'
 } >> "$LIMITS_CONF"

echo ""
echo " - Setting crash settings and limits for system"
sed -i 's/^#\?DumpCore=.*/DumpCore=no/' "$SYSTEM_CONF"
sed -i 's/^#\?CrashShell=.*/CrashShell=no/' "$SYSTEM_CONF"
sed -i 's/^#\?DefaultLimitCORE=.*/DefaultLimitCORE=0/' "$SYSTEM_CONF"
sed -i 's/^#\?DefaultLimitNOFILE=.*/DefaultLimitNOFILE=1024/' "$SYSTEM_CONF"
sed -i 's/^#\?DefaultLimitNPROC=.*/DefaultLimitNPROC=1024/' "$SYSTEM_CONF"

echo ""
echo " - Setting limits for users"
sed -i 's/^#\?DefaultLimitCORE=.*/DefaultLimitCORE=0/' "$USER_CONF"
sed -i 's/^#\?DefaultLimitNOFILE=.*/DefaultLimitNOFILE=1024/' "$USER_CONF"
sed -i 's/^#\?DefaultLimitNPROC=.*/DefaultLimitNPROC=1024/' "$USER_CONF"

echo ""
echo " - Setting a more secure UMASK for users"
sed -i 's/^UMASK.*/UMASK 027/' "$LOGINDEFS_CONF"

if [ -f /etc/init.d/rc ]; then
  sed -i 's/umask 022/umask 027/g' /etc/init.d/rc
fi

if ! grep -q -i "umask" "/etc/profile" 2> /dev/null; then
  echo "umask 027" >> /etc/profile
fi

if ! grep -q -i "umask" "/etc/bash.bashrc" 2> /dev/null; then
  echo "umask 027" >> /etc/bash.bashrc
fi

echo ""
echo " - Create automatic logout variable TMOUT"
if ! grep -q -i "TMOUT" "/etc/profile.d/*" 2> /dev/null; then
  echo -e 'TMOUT=600\nreadonly TMOUT\nexport TMOUT' > "$AUTOLOGOUT_SCRIPT"
  #chmod +x "$AUTOLOGOUT_SCRIPT"
fi

echo ""
echo " - Setting PATH variable for users"
sed -i 's/PATH=.*/PATH=\"\/usr\/local\/bin:\/usr\/sbin:\/usr\/bin:\/bin:\/snap\/bin"/' /etc/environment
sed -i 's|^PATH=.*|PATH=/usr/local/bin:/usr/sbin:/usr/bin:/bin:/snap/bin|' /etc/environment
echo '
#!/bin/bash

if [[ $EUID -eq 0 ]]; then
  export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin
else
  export PATH=/usr/local/bin:/usr/sbin:/usr/bin:/bin:/snap/bin
fi
' > "$INITPATH_SCRIPT"
chown root:root "$INITPATH_SCRIPT"
chmod 0644 "$INITPATH_SCRIPT"

echo ""
echo " - Setting login configuration"
sed -i 's/^#\?KillUserProcesses=no/KillUserProcesses=1/' "$LOGIND_CONF"
sed -i 's/^#\?KillExcludeUsers=root/KillExcludeUsers=root/' "$LOGIND_CONF"
sed -i 's/^#\?IdleAction=ignore/IdleAction=lock/' "$LOGIND_CONF"
sed -i 's/^#\?IdleActionSec=30min/IdleActionSec=15min/' "$LOGIND_CONF"
sed -i 's/^#\?RemoveIPC=yes/RemoveIPC=yes/' "$LOGIND_CONF"
sed -i 's/^.*LOG_OK_LOGINS.*/LOG_OK_LOGINS yes/' "$LOGINDEFS_CONF"
sed -i 's/^PASS_MIN_DAYS.*/PASS_MIN_DAYS 1/' "$LOGINDEFS_CONF"
sed -i 's/^PASS_MAX_DAYS.*/PASS_MAX_DAYS 365/' "$LOGINDEFS_CONF"
sed -i 's/^PASS_WARN_AGE.*/PASS_WARN_AGE 14/' "$LOGINDEFS_CONF"
sed -i 's/DEFAULT_HOME.*/DEFAULT_HOME no/' "$LOGINDEFS_CONF"
sed -i 's/ENCRYPT_METHOD.*/ENCRYPT_METHOD YESCRYPT/' "$LOGINDEFS_CONF"
sed -i 's/USERGROUPS_ENAB.*/USERGROUPS_ENAB no/' "$LOGINDEFS_CONF"
sed -i 's/LOGIN_RETRIES.*/LOGIN_RETRIES 3/' "$LOGINDEFS_CONF"

echo ""
echo " - Setting ADDUSER configuration"
sed -i -e 's/^DIR_MODE=.*/DIR_MODE=0750/' -e 's/^#DIR_MODE=.*/DIR_MODE=0750/' "$ADDUSER_CONF"
sed -i -e 's/^DSHELL=.*/DSHELL=\/bin\/false/' -e 's/^#DSHELL=.*/DSHELL=\/bin\/false/' "$ADDUSER_CONF"
sed -i -e 's/^USERGROUPS=.*/USERGROUPS=yes/' -e 's/^#USERGROUPS=.*/USERGROUPS=yes/' "$ADDUSER_CONF"

echo ""
echo " - Setting USERADD configuration"
sed -i 's/^SHELL=.*/SHELL=\/bin\/false/' "$USERADD_CONF"
sed -i 's/^#\? INACTIVE=.*/INACTIVE=30/' "$USERADD_CONF"

echo ""
echo " - Setting the password history to keep"
if ! grep pam_pwhistory.so "$COMMONPASSWD_CONF"; then
  sed -i '/the "Primary" block/apassword\trequired\t\t\tpam_pwhistory.so remember=14' "$COMMONPASSWD_CONF"
fi

echo ""
echo " - Setting the password complexity"
echo "
difok = 14
dictcheck = 1
enforcing = 1
maxrepeat = 3
minclass = 3
minlen = 14
dcredit = -1
lcredit = -1
ocredit = -1
ucredit = -1
" > /etc/security/pwquality.conf
chmod 0644 /etc/security/pwquality.conf

echo ""
echo " - Setting password hashing algorithm"
sed -i 's/use_authtok try_first_pass .*/use_authtok try_first_pass yescrypt rounds=655360/' "$COMMONPASSWD_CONF"

echo ""
echo " - Prohibit login with a blank password"
sed -i -E 's/(nullok|nullok_secure)//g' "$COMMONAUTH_CONF"

echo ""
echo " - Allow 3 retries at login before closing the session"
if ! grep retry= "$COMMONPASSWD_CONF"; then
  echo 'password requisite pam_pwquality.so retry=3' >> "$COMMONPASSWD_CONF"
fi

echo ""
echo " - Lock accounts after multiple failed login attempts"
if [ -f "$FAILLOCK_CONF" ]; then
  if ! grep faillock "$COMMONAUTH_CONF"; then
    sed -i 's/^#\? audit$/audit/' "$FAILLOCK_CONF"
    sed -i 's/^#\? local_users_only$/local_users_only/' "$FAILLOCK_CONF"
    sed -i 's/^#\? deny.*/deny = 5/' "$FAILLOCK_CONF"
    sed -i 's/^#\? fail_interval.*/fail_interval = 900/' "$FAILLOCK_CONF"
    sed -i 's/^#\? unlock_time.*/unlock_time = 900/' "$FAILLOCK_CONF"
    sed -i 's/^#\? even_deny_root$/even_deny_root/' "$FAILLOCK_CONF"
    sed -i 's/^#\? root_unlock_time.*/root_unlock_time = 900/' "$FAILLOCK_CONF"
    sed -i '/pam_tally.*/d' "$COMMONACCOUNT_CONF"
    sed -i 's/auth.*pam_unix.so/auth required pam_faillock.so preauth\nauth [success=1 default=ignore] pam_unix.so\nauth [default=die] pam_faillock.so authfail\nauth sufficient pam_faillock.so authsucc\n/' "$COMMONAUTH_CONF"
  fi
  if ! grep faillock "$COMMONACCOUNT_CONF"; then
    echo 'account required pam_faillock.so' >> "$COMMONACCOUNT_CONF"
  fi
else
  if ! grep tally2 "$COMMONAUTH_CONF"; then
    sed -i '/^$/a auth required pam_tally2.so onerr=fail audit silent deny=5 unlock_time=900' "$COMMONAUTH_CONF"
    sed -i '/pam_tally/d' "$COMMONACCOUNT_CONF"
  fi
  if ! grep tally2 "$COMMONACCOUNT_CONF"; then
    sed -i '/^$/a account required pam_tally2.so' "$COMMONACCOUNT_CONF"
  fi
fi

echo ""
echo " - Show failed login attempts"
sed -i 's/pam_lastlog.so.*/pam_lastlog.so showfailed/' "$PAM_CONF_LOGIN"

echo ""
echo " - Raise the wait time after failed login attempts"
sed -i 's/delay=.*/delay=4000000/' "$PAM_CONF_LOGIN"

echo ""
echo " - Ensure inactive password lock"
useradd -D -f 30

echo ""
echo " - Disable ctrl-alt-del to reboot the system"
sed -i 's/^#\?CtrlAltDelBurstAction=.*/CtrlAltDelBurstAction=none/' "$SYSTEM_CONF"
systemctl stop ctrl-alt-del.target
#systemctl disable ctrl-alt-del.target
systemctl mask ctrl-alt-del.target

echo ""
echo " - Reloading SYSTEMD"
systemctl daemon-reload

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SUDO (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='sudo'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$PAM_CONF_SU"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Configuring SUDO"
if ! grep -qER '^Defaults.*use_pty$' /etc/sudo*; then
  echo "Defaults use_pty" > "$SUDOERSD/90_hardening_use_pty"
fi
if ! grep -qER '^Defaults.*logfile' /etc/sudo*; then
  echo 'Defaults logfile="/var/log/sudo.log"' > "$SUDOERSD/90_hardening_logfile"
fi
if ! grep -qER '^Defaults.*pwfeedback' /etc/sudo*; then
  echo 'Defaults !pwfeedback' > "$SUDOERSD/90_hardening_pwfeedback"
fi
if ! grep -qER '^Defaults.*visiblepw' /etc/sudo*; then
  echo 'Defaults !visiblepw' > "$SUDOERSD/90_hardening_visiblepw"
fi
if ! grep -qER '^Defaults.*passwd_timeout' /etc/sudo*; then
  echo 'Defaults passwd_timeout=1' > "$SUDOERSD/90_hardening_passwdtimeout"
fi
if ! grep -qER '^Defaults.*timestamp_timeout' /etc/sudo*; then
  echo 'Defaults timestamp_timeout=15' > "$SUDOERSD/90_hardening_timestamptimeout"
fi

echo ""
echo " - Set permissions for sudoers.d"
find "$SUDOERSD" -type f -name '[0-9]*' -exec chmod 0440 {} \;

echo ""
echo " - Removing NOPASSWD from sudoers"
if [ -f "$CLOUDINIT_CONF" ]; then
 sed -i 's/sudo: \["ALL=(ALL) NOPASSWD:ALL"\]/#&/g' "$CLOUDINIT_CONF"
fi
if grep -R -E 'NOPASSWD:' /etc/sudoers.d/*; then
  sed -i 's/NOPASSWD://g' /etc/sudoers.d/*
fi

echo ""
echo " - Use PAM to restrict access to SU"
if ! grep -qER '^auth required pam_wheel.so' "$PAM_CONF_SU"; then
  echo 'auth required pam_wheel.so use_uid group=sudo' >> "$PAM_CONF_SU"
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SSH (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='openssh-server'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$SSH_CONF /etc/ssh/moduli $SSHD_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Configure SSH client"
if ! grep -q "^\s.*HashKnownHosts" "$SSH_CONF" 2> /dev/null; then
  sed -i '/HashKnownHosts/d' "$SSH_CONF"
  echo "    HashKnownHosts yes" >> "$SSH_CONF"
fi
sed -i 's/#.*Ciphers .*/    Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes256-ctr/g' "$SSH_CONF"
sed -i 's/#.*MACs .*/    MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256/' "$SSH_CONF"

echo ""
echo " - Deleting old host keys"
rm -f /etc/ssh/ssh_host_*_key
rm -f /etc/ssh/ssh_host_*_key.pub

echo ""
echo " - Generating new strong host keys"
ssh-keygen -b 4096 -t rsa -N "" -f /etc/ssh/ssh_host_rsa_key
ssh-keygen -b 521 -t ecdsa -N "" -f /etc/ssh/ssh_host_ecdsa_key
ssh-keygen -t ed25519 -N "" -f /etc/ssh/ssh_host_ed25519_key

echo ""
echo " - Remove all Diffie-Hellman-Moduli which are smaller than 3072 Bit"
awk '$5 >= 3071' /etc/ssh/moduli > /etc/ssh/moduli.tmp
mv /etc/ssh/moduli.tmp /etc/ssh/moduli

echo ""
echo " - Creating public key for Admin User"
echo "$ADMIN_PUBLICKEY" > "/home/$ADMIN_USER/.ssh/authorized_keys"

echo ""
echo " - Creating a SSHD users group and adding admin user $ADMIN_USER"
groupadd -r "$SSH_GROUP"
usermod -aG "$SSH_GROUP" "$ADMIN_USER"

echo ""
echo " - Disable SFTP subsystem in main config"
sed -i -e 's/^Subsystem\s*sftp\s*.*/#&/g' "$SSHD_CONF"

echo ""
echo " - Create SSHD config"
echo "
Port $SSH_PORT
RekeyLimit 512M 1h
LogLevel VERBOSE
LoginGraceTime 30
PermitRootLogin no
StrictModes yes
MaxAuthTries 3
MaxSessions 3
HostbasedAuthentication no
IgnoreUserKnownHosts yes
IgnoreRhosts yes
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
KbdInteractiveAuthentication no
KerberosAuthentication no
GSSAPIAuthentication no
GSSAPICleanupCredentials no
ChallengeResponseAuthentication no
UsePAM yes
AllowAgentForwarding no
AllowTcpForwarding no
GatewayPorts no
X11Forwarding no
PrintLastLog yes
PrintMotd no
TCPKeepAlive no
PermitUserEnvironment no
Compression no
ClientAliveInterval 15
ClientAliveCountMax 3
UseDNS no
MaxStartups 10:30:60
PermitTunnel no
Banner /etc/issue.net
Subsystem sftp internal-sftp
AllowGroups $SSH_GROUP
KexAlgorithms curve25519-sha256@libssh.org,ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group-exchange-sha256
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes256-ctr
Macs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256
" > "$SSHDD/00-hardening.conf"
chown root:root /etc/ssh/sshd_config
chmod og-rwx /etc/ssh/sshd_config
chown root:root "$SSHDD/00-hardening.conf"
chmod 0600 "$SSHDD/00-hardening.conf"

echo ""
echo " - Enabling SSH"
systemctl daemon-reload
systemctl enable ssh.service
systemctl restart ssh.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# IPV6 (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Disable IPv6"
if [[ -f /boot/firmware/cmdline.txt ]]; then
  sed -i 's/^console=serial0,115200.*/& ipv6.disable=1/g' /boot/firmware/cmdline.txt
else
  if ! grep -q 'ipv6.disable=1' /proc/cmdline; then
    echo "GRUB_CMDLINE_LINUX=\"\$GRUB_CMDLINE_LINUX ipv6.disable=1\"" > "$GRUB_DEFAULT/99-hardening-ipv6.cfg"
    update-grub
  fi
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# FIREWALL (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='ufw'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$UFW_DEFAULT $UFW_CONF_BEFORE $UFW_CONF_BEFORE6 $UFW_CONF_AFTER $UFW_CONF_AFTER6"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Enabling UFW"
sed -i 's/IPV6=.*/IPV6=yes/' "$UFW_DEFAULT"
sed -i 's/IPT_SYSCTL=.*/IPT_SYSCTL=\/etc\/sysctl\.conf/' "$UFW_DEFAULT"
systemctl daemon-reload
systemctl enable ufw.service
systemctl restart ufw.service
ufw --force enable

echo ""
echo " - Set before and after rules for PSAD"
sed -i '/^COMMIT/i -A ufw-before-output -p icmp -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT' $UFW_CONF_BEFORE
sed -i '/^COMMIT/i -A ufw-before-output -p icmp -m state --state ESTABLISHED,RELATED -j ACCEPT' $UFW_CONF_BEFORE
sed -i '/^COMMIT/i -A INPUT -j LOG --log-tcp-options --log-prefix "[UFW INPUT] "' $UFW_CONF_BEFORE
sed -i '/^COMMIT/i -A FORWARD -j LOG --log-tcp-options --log-prefix "[UFW FORWARD] "' $UFW_CONF_BEFORE

sed -i '/^COMMIT/i -A ufw6-before-output -p icmpv6 -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT' $UFW_CONF_BEFORE6
sed -i '/^COMMIT/i -A ufw6-before-output -p icmpv6 -m state --state ESTABLISHED,RELATED -j ACCEPT' $UFW_CONF_BEFORE6
sed -i '/^COMMIT/i -A INPUT -j LOG --log-tcp-options --log-prefix "[UFW INPUT] "' $UFW_CONF_BEFORE6
sed -i '/^COMMIT/i -A FORWARD -j LOG --log-tcp-options --log-prefix "[UFW FORWARD] "' $UFW_CONF_BEFORE6

sed -i '/^COMMIT/i -A INPUT -j LOG --log-tcp-options --log-prefix "[UFW INPUT] "' $UFW_CONF_AFTER
sed -i '/^COMMIT/i -A FORWARD -j LOG --log-tcp-options --log-prefix "[UFW FORWARD] "' $UFW_CONF_AFTER

sed -i '/^COMMIT/i -A FORWARD -j LOG --log-tcp-options --log-prefix "[UFW FORWARD] "' $UFW_CONF_AFTER6
sed -i '/^COMMIT/i -A INPUT -j LOG --log-tcp-options --log-prefix "[UFW INPUT] "' $UFW_CONF_AFTER6

echo ""
echo " - Configure loopback traffic"
ufw allow in on lo
ufw deny in from 127.0.0.0/8
if ip -6 addr | grep -q 'inet6'; then
  ufw deny in from ::1
fi
ufw deny in to 224.0.0.1
ufw allow out on lo

echo ""
echo " - Allow admins to connect to SSH"
for admin_ip in $ADMIN_IPS; do
  ufw allow from $admin_ip to any port $SSH_PORT proto tcp comment 'SSH TCP - Admins'
done

echo ""
echo " - Enable logging"
ufw logging on
ufw reload

echo ""
echo " - Set deny all as default"
ufw default deny incoming

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# HOSTS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Set allowed hosts"
echo "sshd : ALL : ALLOW" > $HOSTS_ALLOW
echo "ALL: LOCAL, 127.0.0.1" >> $HOSTS_ALLOW
chmod 644 $HOSTS_ALLOW

echo ""
echo " - Set denied hosts"
echo "ALL: ALL" > $HOSTS_DENY
chmod 644 $HOSTS_DENY

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# TIMESYNCD (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$TIMESYNCD_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Set timezone"
timedatectl set-timezone "$TIMEZONE"

echo ""
echo " - Configuring TIMESYNCD"
sed -i "s/^#NTP=.*/NTP=$NTP_SERVER/" "$TIMESYNCD_CONF"
sed -i "s/^#FallbackNTP=.*/FallbackNTP=$NTP_FALLBACKSERVER/" "$TIMESYNCD_CONF"
timedatectl set-ntp true

echo ""
echo " - Enabling TIMESYNCD"
systemctl daemon-reload
systemctl enable systemd-timesyncd
systemctl restart systemd-timesyncd

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# RESOLVED (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$RESOLVED_CONF $RESOLVED_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Configuring RESOLVED"
if cat /sys/firmware/devicetree/base/model 2>/dev/null | grep -iq "Raspberry"; then
  sed -i "s/^#DNSSEC=.*/DNSSEC=false/" "$RESOLVED_CONF"
else
  sed -i "s/^#DNSSEC=.*/DNSSEC=allow-downgrade/" "$RESOLVED_CONF"
fi
sed -i "s/^#DNSOverTLS=.*/DNSOverTLS=opportunistic/" "$RESOLVED_CONF"

echo ""
echo " - Changing NSSwitch to use RESOLVED"
sed -i '/^hosts:/ s/files dns/files resolve dns/' $NSSWITCH_CONF

echo ""
echo " - Reloading SYSTEMD"
systemctl daemon-reload

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SYSLOG (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='rsyslog'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$RSYSLOG_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Disable incoming logs"
sed -i -e "s/^module(load=\"imudp\")\s*.*/#&/g" "$RSYSLOG_CONF"
sed -i -e "s/^input(type=\"imudp\" port=*.*/#&/g" "$RSYSLOG_CONF"
sed -i -e "s/^module(load=\"imtcp\")\s*.*/#&/g" "$RSYSLOG_CONF"
sed -i -e "s/^input(type=\"imtcp\" port=*.*/#&/g" "$RSYSLOG_CONF"

echo ""
echo " - Setting CreateModes"
sed -i "s/^\$FileCreateMode.*/\$FileCreateMode 0640/g" "$RSYSLOG_CONF"
sed -i "s/^\$DirCreateMode.*/\$DirCreateMode 0750/g" "$RSYSLOG_CONF"

echo ""
echo " - Correct permissions on log files and directories"
find /var/log/ -type f -perm /g+wx,o+rwx -exec chmod --changes g-wx,o-rwx "{}" +
find /var/log/ -type d -perm /g+w,o+rwx -exec chmod --changes g-w,o-rwx "{}" +

echo ""
echo " - Enabling RSYSLOG daemon"
systemctl daemon-reload
systemctl enable rsyslog
systemctl restart rsyslog

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# JOURNALD (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$JOURNALD_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Configuring journaling daemon"
sed -i "s/.*Storage\s*=\s*.*/Storage=persistent/g" "$JOURNALD_CONF"
sed -i "s/.*Compress\s*=\s*.*/Compress=yes/g" "$JOURNALD_CONF"
sed -i "s/.*SystemMaxUse\s*=\s*.*/SystemMaxUse=512M/g" "$JOURNALD_CONF"
sed -i "s/.*SystemKeepFree\s*=\s*.*/SystemKeepFree=512M/g" "$JOURNALD_CONF"
sed -i "s/.*SystemMaxFileSize\s*=\s*.*/SystemMaxFileSize=32M/g" "$JOURNALD_CONF"
sed -i "s/.*ForwardToSyslog\s*=\s*.*/ForwardToSyslog=yes/g" "$JOURNALD_CONF"

echo ""
echo " - Restarting JOURNALD"
systemctl restart systemd-journald.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# LOGROTATE (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='logrotate'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$LOGROTATE_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Generating LOGROTATE config"
echo "
# see "man logrotate" for details
# rotate log files daily
daily

# use the syslog group by default, since this is the owning group
# of /var/log/syslog.
su root syslog

# keep 30 days worth of backlogs
rotate 30

# create new (empty) log files after rotating old ones
create

# use date as a suffix of the rotated file
dateext

# compressed log files
compress

# use xz to compress
compresscmd /usr/bin/xz
uncompresscmd /usr/bin/unxz
compressext .xz

# packages drop log rotation information into this directory
include /etc/logrotate.d

# system-specific logs may be also be configured here.
" > "$LOGROTATE_CONF"

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# MOTD (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$ISSUE_CONF $ISSUENET_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Setting welcome messages"
echo "$ISSUE_SHORT" > "$ISSUE_CONF"
echo "$ISSUE_TEXT" >> "$ISSUE_CONF"
echo "$ISSUE_SHORT" > "$ISSUENET_CONF"
echo "$ISSUE_TEXT" >> "$ISSUENET_CONF"
echo "$MOTD_TEXT" > "$MOTD_CONF"

echo ""
echo " - Set correct permissions for messages"
chown root:root "$ISSUE_CONF"
chmod 644 "$ISSUE_CONF"
chown root:root "$ISSUENET_CONF"
chmod 644 "$ISSUENET_CONF"
chown root:root "$MOTD_CONF"
chmod 644 "$MOTD_CONF"

echo ""
echo " - Disable MOTD news"
if test -f /etc/default/motd-news; then
  sed -i 's/ENABLED=.*/ENABLED=0/' /etc/default/motd-news
fi
systemctl disable motd-news.timer
systemctl mask motd-news.timer
systemctl daemon-reload

echo ""
echo " - Disable MOTD updates"
chmod a-x /etc/update-motd.d/*

echo ""
echo " - Disable APT news"
if command -v pro 2>/dev/null 1>&2; then
  pro config set apt_news=false
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SCHEDULERS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='cron'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="/etc/rsyslog.d/50-default.conf"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Set permissions on CRON files"
if [[ -f /etc/crontab ]]; then
  chown root:root /etc/crontab
  chmod og-rwx /etc/crontab
fi
if [[ -d /etc/cron.hourly ]]; then
  chown root:root /etc/cron.hourly/
  chmod og-rwx /etc/cron.hourly/
fi
if [[ -d /etc/cron.daily ]]; then
  chown root:root /etc/cron.daily/
  chmod og-rwx /etc/cron.daily/
fi
if [[ -d /etc/cron.weekly ]]; then
  chown root:root /etc/cron.weekly/
  chmod og-rwx /etc/cron.weekly/
fi
if [[ -d /etc/cron.monthly ]]; then
  chown root:root /etc/cron.monthly/
  chmod og-rwx /etc/cron.monthly/
fi
if [[ -d /etc/cron.yearly ]]; then
  chown root:root /etc/cron.yearly/
  chmod og-rwx /etc/cron.yearly/
fi
if [[ -d /etc/cron.d ]]; then
  chown root:root /etc/cron.d/
  chmod og-rwx /etc/cron.d/
fi

echo ""
echo " - Enable CRON"
systemctl daemon-reload
systemctl enable cron
systemctl restart cron

echo ""
echo " - Creating scheduler allow-lists"
echo 'root' > /etc/cron.allow
echo 'root' > /etc/at.allow
chown root:root /etc/cron.allow
chmod g-wx,o-rwx /etc/cron.allow
chown root:root /etc/at*
chmod og-rwx /etc/at*

echo ""
echo " - Removing schedule deny-lists"
rm -f /etc/cron.deny 2> /dev/null
rm -f /etc/at.deny 2> /dev/null

echo ""
echo " - Disable ATD daemon"
#systemctl disable atd.service
systemctl mask atd.service

echo ""
echo " - Allow CRON its own log-file"
sed -i 's/^#\?cron./cron./' /etc/rsyslog.d/50-default.conf

echo ""
echo " - Reloading SYSTEMD"
systemctl daemon-reload

echo ""
echo " - Restarting RSYSLOG daemon"
systemctl restart rsyslog

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# ROOT (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$SECURITYACCESS_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Allow root login only from localhost"
if ! grep -E '^\+\s:\sroot\s:\s127.0.0.1$|^:root:127.0.0.1' "$SECURITYACCESS_CONF"; then
  sed -i 's/^#\?.*root.*:.*127.0.0.1$/+:root:127.0.0.1/' "$SECURITYACCESS_CONF"
fi

echo ""
echo " - Generating random root password"
ROOT_PASSWORD=$(tr -dc 'A-Za-z0-9!@#$%^&*()_+-=' < /dev/urandom | head -c 64)

echo ""
echo " - Changing root password"
echo "root:$ROOT_PASSWORD" | chpasswd

echo ""
echo " - Locking root account"
usermod -L root

echo ""
echo " - Disable DEBUG-SHELL"
systemctl stop debug-shell.service
systemctl disable debug-shell.service
systemctl mask debug-shell.service

echo ""
echo " - Reloading SYSTEMD"
systemctl daemon-reload

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# RKHUNTER (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='rkhunter'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Backing up original config files"
CONFIG_FILES="$RKHUNTER_CONF"
for CONFIG_FILE in $CONFIG_FILES
do
  if [ -f $CONFIG_FILE ]; then
      cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
  fi
done

echo ""
echo " - Configuring RKHUNTER"
sed -i 's/^CRON_DAILY_RUN=.*/CRON_DAILY_RUN="yes"/' "$RKHUNTER_CONF"
sed -i 's/^APT_AUTOGEN=.*/APT_AUTOGEN="yes"/' "$RKHUNTER_CONF"

echo ""
echo " - Update file properties database"
rkhunter --propupd

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# USBGUARD (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='usbguard'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Generate policy from actually connected devices"
usbguard generate-policy > /tmp/rules.conf
echo 'allow with-interface one-of { 03:00:01  03:01:01 } if !allowed-matches(with-interface one-of { 03:00:01 03:01:01 })' >> /tmp/rules.conf
install -m 0600 -o root -g root /tmp/rules.conf "$USBGUARD_CONF"
rm -f /tmp/rules.conf

echo ""
echo " - Activate USBGUARD"
systemctl daemon-reload
systemctl enable usbguard.service
systemctl restart usbguard.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CALL HOME (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Disable APPORT"
if command -v gsettings 2>/dev/null 1>&2; then
  gsettings set com.ubuntu.update-notifier show-apport-crashes false
fi

if [ -f /etc/default/apport ]; then
  sed -i 's/enabled=.*/enabled=0/' /etc/default/apport
  systemctl stop apport.service
  systemctl disable apport.service
  systemctl mask apport.service

  echo ""
  echo " - Reloading SYSTEMD"
  systemctl daemon-reload
fi

echo ""
echo " - Disable Ubuntu reporting"
if command -v ubuntu-report 2>/dev/null 1>&2; then
  ubuntu-report -f send no
fi

echo ""
echo " - Uninstall popularity contest"
if dpkg -l | grep -E '^ii.*popularity-contest' 2>/dev/null 1>&2; then
  $APT purge popularity-contest
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# ACCOUNTS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Remove main hosts.equiv file"
if [[ -f /etc/hosts.equiv ]]; then
  rm -f /etc/hosts.equiv
fi

echo ""
echo " - Remove users hosts.equiv, .rhosts, and .netrc files"
while read -r hostpasswd; do
  find "$hostpasswd" \( -name "hosts.equiv" -o -name ".rhosts" -o -name ".netrc"\) -exec rm -f {} \; 2> /dev/null
done <<< "$(awk -F ":" '{print $6}' /etc/passwd)"

echo ""
echo " - Remove accounts that are not required"
for users in games gnats irc list news sync uucp; do
  echo "   - Removing $users"
  userdel -r "$users" 2> /dev/null
done

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# COMPILER (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Restrict execution of Installing compilers"
while read -r x; do
  if [ -f "$x" ] && [ -x "$x" ]; then
    if ! test -L "$x"; then
      echo "   - Restricting $x"
      chmod 0750 "$x"
    fi
  fi
done <<< "$(dpkg-query -L $(dpkg -l | grep compil | awk '{print $2}'))"

echo ""
echo " - Restrict execution of portable assembler compilers"
ASCOMP="$(command -v as)"
if [ -f "$ASCOMP" ] && [ -x "$ASCOMP" ]; then
  echo "   - Restricting $ASCOMP"
  chmod 0750 "$(readlink -e $(command -v as))"
fi

# -------------------------------------------------------------------------------------

if [ "$PSAD_ENABLE" = "true" ]; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# POSTFIX (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Prepare POSTFIX installation"
  echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections
  echo "postfix postfix/mailname string $(hostname -f)" | debconf-set-selections

  echo ""
  echo " - Installing Packages"
  PACKAGE_INSTALL='postfix'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installing $deb_install"
    $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
  done

  echo ""
  echo " - Configuring POSTFIX"
  postconf -e inet_protocols=ipv4
  postconf -e disable_vrfy_command=yes
  postconf -e smtpd_banner="\$myhostname ESMTP"
  postconf -e smtpd_client_restrictions=permit_mynetworks,reject
  postconf -e inet_interfaces=loopback-only

  echo ""
  echo " - Enabling POSTFIX "
  systemctl daemon-reload
  systemctl enable postfix.service
  systemctl restart postfix.service

  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# PSAD (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Installing Packages"
  PACKAGE_INSTALL='psad'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installing $deb_install"
    $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
  done

  echo ""
  echo " - Backing up original config files"
  CONFIG_FILES="$PSAD_DL $PSAD_CONF"
  for CONFIG_FILE in $CONFIG_FILES
  do
    if [ -f $CONFIG_FILE ]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
    fi
  done

  echo ""
  echo " - Configuring danger levels by IP"
  echo "127.0.0.1    0;" >> "$PSAD_DL"
  echo "$SERVERIP    0;" >> "$PSAD_DL"

  echo ""
  echo " - Configuring PSAD"
  sed -i "s/EMAIL_ADDRESSES  .*/EMAIL_ADDRESSES             root@localhost;/" "$PSAD_CONF"
  sed -i "s/HOSTNAME  .*/HOSTNAME                    $(hostname --fqdn);/" "$PSAD_CONF"
  sed -i 's/DANGER_LEVEL2  .*/DANGER_LEVEL2               15;/' "$PSAD_CONF"
  sed -i 's/DANGER_LEVEL3  .*/DANGER_LEVEL3               150;/' "$PSAD_CONF"
  sed -i 's/DANGER_LEVEL4  .*/DANGER_LEVEL4               1500;/' "$PSAD_CONF"
  sed -i 's/DANGER_LEVEL5  .*/DANGER_LEVEL5               10000;/' "$PSAD_CONF"
  sed -i 's/IPT_SYSLOG_FILE  .*/IPT_SYSLOG_FILE             \/var\/log\/syslog;/' "$PSAD_CONF"
  sed -i 's/EXPECT_TCP_OPTIONS  .*/EXPECT_TCP_OPTIONS             Y;/' "$PSAD_CONF"
  sed -i 's/IGNORE_PORTS  .*/IGNORE_PORTS             NONE;/' "$PSAD_CONF"
  sed -i 's/EMAIL_ALERT_DANGER_LEVEL  .*;/EMAIL_ALERT_DANGER_LEVEL    5;/' "$PSAD_CONF"
  sed -i 's/ENABLE_MAC_ADDR_REPORTING  .*/ENABLE_MAC_ADDR_REPORTING   Y;/' "$PSAD_CONF"
  sed -i 's/EMAIL_LIMIT  .*/EMAIL_LIMIT                 5;/' "$PSAD_CONF"
  sed -i 's/ENABLE_AUTO_IDS  .*/ENABLE_AUTO_IDS               Y;/' "$PSAD_CONF"
  sed -i 's/AUTO_IDS_DANGER_LEVEL  .*/AUTO_IDS_DANGER_LEVEL       1;/' "$PSAD_CONF"
  sed -i 's/ENABLE_AUTO_IDS_EMAILS  .*/ENABLE_AUTO_IDS_EMAILS      Y;/' "$PSAD_CONF"
  sed -i 's/SIG_UPDATE_URL  .*/SIG_UPDATE_URL              https:\/\/www.cipherdyne.org\/psad\/signatures;/'  "$PSAD_CONF"

  echo ""
  echo " - Update PSAD signatures"
  psad --sig-update
  psad -H

  echo ""
  echo " - Analyze the local IPTABLES ruleset"
  psad --fw-analyze

  echo ""
  echo " - Enable PSAD daemon"
  systemctl daemon-reload
  systemctl enable psad
  systemctl restart psad
fi

# -------------------------------------------------------------------------------------

if [ "$AUDIT_ENABLE" = "true" ]; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# AUDITD (`date '+%F %T.%N'`) // https://github.com/Neo23x0/auditd"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Installing Packages"
  PACKAGE_INSTALL='auditd audispd-plugins'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installing $deb_install"
    $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
  done

  echo ""
  echo " - Backing up original config files"
  CONFIG_FILES="$AUDITD_CONF"
  for CONFIG_FILE in $CONFIG_FILES
  do
    if [ -f $CONFIG_FILE ]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.hardening-backup"
    fi
  done

  echo ""
  echo " - Ensure auditing for processes that start prior to AUDITD is enabled"
  echo ""
  echo " - Configuring kernel lockdown mode"
  if [[ -f /boot/firmware/cmdline.txt ]]; then
    sed -i 's/^console=serial0,115200.*/& audit=1 audit_backlog_limit=8192/g' /boot/firmware/cmdline.txt
  else
    if ! grep -q 'audit=1' /proc/cmdline; then
      echo "GRUB_CMDLINE_LINUX=\"\$GRUB_CMDLINE_LINUX audit=1 audit_backlog_limit=8192\"" > "$GRUB_DEFAULT/99-hardening-audit.cfg"
      update-grub
    fi
  fi

  echo ""
  echo " - Configuring AUDITD"
  sed -i -e 's/^admin_space_left\s*=\s*.*/admin_space_left = 5/' "$AUDITD_CONF"
  sed -i -e 's/^admin_space_left_action\s*=\s*.*/admin_space_left_action = email/' "$AUDITD_CONF"
  sed -i -e 's/^action_mail_acct\s*=\s*.*/action_mail_acct = root/' "$AUDITD_CONF"
  sed -i -e 's/^disk_error_action\s*=\s*.*/disk_error_action = SUSPEND/' "$AUDITD_CONF"
  sed -i -e 's/^disk_full_action\s*=\s*.*/disk_full_action = SUSPEND/' "$AUDITD_CONF"
  sed -i -e 's/^flush\s*=\s*.*/flush = INCREMENTAL_ASYNC/' "$AUDITD_CONF"
  sed -i -e 's/^local_events\s*=\s*.*/local_events = yes/' "$AUDITD_CONF"
  sed -i -e 's/^log_file\s*=\s*.*/log_file = \/var\/log\/audit\/audit.log/' "$AUDITD_CONF"
  sed -i -e 's/^log_format\s*=\s*.*/log_format = ENRICHED/' "$AUDITD_CONF"
  sed -i -r 's/^\s*#?\s*log_group\s*=\s*\S+(\s*#.*)?.*$/log_group = adm\1/' "$AUDITD_CONF"
  sed -i -e 's/^max_log_file\s*=\s*.*/max_log_file = 256/' "$AUDITD_CONF"
  sed -i -e 's/^max_log_file_action\s*=\s*.*/max_log_file_action = ROTATE/' "$AUDITD_CONF"
  sed -i -e 's/^num_logs\s*=\s*.*/num_logs = 14/' "$AUDITD_CONF"
  sed -i -e 's/^space_left\s*=\s*.*/space_left = 10/' "$AUDITD_CONF"
  sed -i -e 's/^space_left_action\s*=\s*.*/space_left_action = email/' "$AUDITD_CONF"
  sed -i -e 's/^write_logs\s*=\s*.*/write_logs = yes/' "$AUDITD_CONF"

  echo ""
  echo " - Generate AUDITD rules (https://github.com/Neo23x0/auditd)"
  echo "
#      ___             ___ __      __
#     /   | __  ______/ (_) /_____/ /
#    / /| |/ / / / __  / / __/ __  /
#   / ___ / /_/ / /_/ / / /_/ /_/ /
#  /_/  |_\__,_/\__,_/_/\__/\__,_/
#
# Linux Audit Daemon - Best Practice Configuration
# /etc/audit/audit.rules
#
# Compiled by Florian Roth
#
# Created  : 2017/12/05
# Modified : 2023/01/25
#
# Based on rules published here:
#   Gov.uk auditd rules
#   	https://github.com/gds-operations/puppet-auditd/pull/1
# 	CentOS 7 hardening
# 		https://highon.coffee/blog/security-harden-centos-7/#auditd---audit-daemon
# 	Linux audit repo
# 		https://github.com/linux-audit/audit-userspace/tree/master/rules
# 	Auditd high performance linux auditing
# 		https://linux-audit.com/tuning-auditd-high-performance-linux-auditing/
#
# Further rules
# 	For PCI DSS compliance see:
# 		https://github.com/linux-audit/audit-userspace/blob/master/rules/30-pci-dss-v31.rules
# 	For NISPOM compliance see:
# 		https://github.com/linux-audit/audit-userspace/blob/master/rules/30-nispom.rules

# Remove any existing rules
-D

# Buffer Size
## Feel free to increase this if the machine panic's
-b 8192

# Failure Mode
## Possible values: 0 (silent), 1 (printk, print a failure message), 2 (panic, halt the system)
-f 1

# Ignore errors
## e.g. caused by users or files not found in the local environment
-i

# Self Auditing ---------------------------------------------------------------

## Audit the audit logs
### Successful and unsuccessful attempts to read information from the audit records
-w /var/log/audit/ -p wra -k auditlog
-w /var/audit/ -p wra -k auditlog

## Auditd configuration
### Modifications to audit configuration that occur while the audit collection functions are operating
-w /etc/audit/ -p wa -k auditconfig
-w /etc/libaudit.conf -p wa -k auditconfig
-w /etc/audisp/ -p wa -k audispconfig

## Monitor for use of audit management tools
-w /sbin/auditctl -p x -k audittools
-w /sbin/auditd -p x -k audittools
-w /usr/sbin/auditd -p x -k audittools
-w /usr/sbin/augenrules -p x -k audittools

## Access to all audit trails

-a always,exit -F path=/usr/sbin/ausearch -F perm=x -k audittools
-a always,exit -F path=/usr/sbin/aureport -F perm=x -k audittools
-a always,exit -F path=/usr/sbin/aulast -F perm=x -k audittools
-a always,exit -F path=/usr/sbin/aulastlogin -F perm=x -k audittools
-a always,exit -F path=/usr/sbin/auvirt -F perm=x -k audittools

# Filters ---------------------------------------------------------------------

### We put these early because audit is a first match wins system.

## Ignore current working directory records
-a always,exclude -F msgtype=CWD

## Cron jobs fill the logs with stuff we normally don't want (works with SELinux)
-a never,user -F subj_type=crond_t
-a never,exit -F subj_type=crond_t

## This prevents chrony from overwhelming the logs
#-a never,exit -F arch=b64 -S adjtimex -F auid=-1 -F uid=chrony -F subj_type=chronyd_t

## This is not very interesting and wastes a lot of space if the server is public facing
-a always,exclude -F msgtype=CRYPTO_KEY_USER

## Open VM Tools
-a exit,never -F arch=b64 -S all -F exe=/usr/bin/vmtoolsd

## High Volume Event Filter (especially on Linux Workstations)
-a never,exit -F arch=b32 -F dir=/dev/shm/ -F key=sharedmemaccess
-a never,exit -F arch=b64 -F dir=/dev/shm/ -F key=sharedmemaccess

-a never,exit -F arch=b32 -F dir=/var/lock/lvm/ -F key=locklvm
-a never,exit -F arch=b64 -F dir=/var/lock/lvm/ -F key=locklvm

## Filebeat 
### https://www.elastic.co/guide/en/beats/filebeat/current/directory-layout.html

#-a never,exit -F arch=b32 -F path=/opt/filebeat -F perm=wa -F key=filebeat
#-a never,exit -F arch=b64 -F path=/opt/filebeat -F perm=wa -F key=filebeat

#-a always,exit -F arch=b32 -F dir=/etc/filebeat/ -F perm=wa -F key=filebeat
#-a always,exit -F arch=b64 -F dir=/etc/filebeat/ -F perm=wa -F key=filebeat

#-a always,exit -F arch=b32 -F dir=/usr/share/filebeat/ -F perm=wa -F key=filebeat
#-a always,exit -F arch=b64 -F dir=/usr/share/filebeat/ -F perm=wa -F key=filebeat

#-a always,exit -F arch=b64 -F dir=/usr/share/filebeat/bin/ -F perm=x -F key=filebeat
#-a always,exit -F arch=b32 -F dir=/usr/share/filebeat/bin/ -F perm=x -F key=filebeat

### macOS
#### https://www.elastic.co/guide/en/beats/filebeat/7.17/directory-layout.html
#-a always,exit -F arch=b32 -F path=/usr/local/var/homebrew/linked/filebeat-full -F perm=x -F key=filebeat
#-a always,exit -F arch=b64 -F path=/usr/local/var/homebrew/linked/filebeat-full -F perm=x -F key=filebeat

#-a always,exit -F arch=b32 -F dir=/usr/local/var/homebrew/linked/filebeat-full/bin/ -F perm=x -F key=filebeat 
#-a always,exit -F arch=b64 -F dir=/usr/local/var/homebrew/linked/filebeat-full/bin/ -F perm=x -F key=filebeat

#-a always,exit -F arch=b32 -F dir=/usr/local/etc/filebeat/ -F perm=wa -F key=filebeat  
#-a always,exit -F arch=b64 -F dir=/usr/local/etc/filebeat/ -F perm=wa -F key=filebeat

## More information on how to filter events
### https://access.redhat.com/solutions/2482221

# Rules -----------------------------------------------------------------------

## Kernel parameters
-w /etc/sysctl.conf -p wa -k sysctl
-w /etc/sysctl.d -p wa -k sysctl

## Kernel module loading and unloading
-a always,exit -F perm=x -F auid!=-1 -F path=/sbin/insmod -k modules
-a always,exit -F perm=x -F auid!=-1 -F path=/sbin/modprobe -k modules
-a always,exit -F perm=x -F auid!=-1 -F path=/sbin/rmmod -k modules
-a always,exit -F arch=b64 -S finit_module -S init_module -S delete_module -F auid!=-1 -k modules

## Modprobe configuration
-w /etc/modprobe.conf -p wa -k modprobe
-w /etc/modprobe.d -p wa -k modprobe

## KExec usage (all actions)
-a always,exit -F arch=b64 -S kexec_load -k KEXEC

## Special files
#-a always,exit -F arch=b64 -S mknod -S mknodat -k specialfiles

## Mount operations (only attributable)
-a always,exit -F arch=b64 -S mount -S umount2 -F auid!=-1 -k mount

### NFS mount
-a always,exit -F path=/sbin/mount.nfs -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
-a always,exit -F path=/usr/sbin/mount.nfs -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts

## Change swap (only attributable)
-a always,exit -F arch=b64 -S swapon -S swapoff -F auid!=-1 -k swap

## Time
#-a always,exit -F arch=b64 -F uid!=ntp -S adjtimex -S settimeofday -S clock_settime -k time
### Local time zone
-w /etc/localtime -p wa -k localtime

## Stunnel
-w /usr/sbin/stunnel -p x -k stunnel
-w /usr/bin/stunnel -p x -k stunnel

## Cron configuration & scheduled jobs
-w /etc/cron.allow -p wa -k cron
-w /etc/cron.deny -p wa -k cron
-w /etc/cron.d/ -p wa -k cron
-w /etc/cron.daily/ -p wa -k cron
-w /etc/cron.hourly/ -p wa -k cron
-w /etc/cron.monthly/ -p wa -k cron
-w /etc/cron.weekly/ -p wa -k cron
-w /etc/crontab -p wa -k cron
-w /var/spool/cron/ -p wa -k cron

## User, group, password databases
-w /etc/group -p wa -k etcgroup
-w /etc/passwd -p wa -k etcpasswd
-w /etc/gshadow -k etcgroup
-w /etc/shadow -k etcpasswd
-w /etc/security/opasswd -k opasswd

## Sudoers file changes
-w /etc/sudoers -p wa -k actions
-w /etc/sudoers.d/ -p wa -k actions

## Passwd
-w /usr/bin/passwd -p x -k passwd_modification

## Tools to change group identifiers
-w /usr/sbin/groupadd -p x -k group_modification
-w /usr/sbin/groupmod -p x -k group_modification
-w /usr/sbin/addgroup -p x -k group_modification
-w /usr/sbin/useradd -p x -k user_modification
-w /usr/sbin/userdel -p x -k user_modification
-w /usr/sbin/usermod -p x -k user_modification
-w /usr/sbin/adduser -p x -k user_modification

## Login configuration and information
-w /etc/login.defs -p wa -k login
-w /etc/securetty -p wa -k login
-w /var/log/faillog -p wa -k login
-w /var/log/lastlog -p wa -k login
-w /var/log/tallylog -p wa -k login

## Network Environment
### Changes to hostname
-a always,exit -F arch=b64 -S sethostname -S setdomainname -k network_modifications

### Detect Remote Shell Use
-a always,exit -F arch=b64 -F exe=/bin/bash -F success=1 -S connect -k "remote_shell"
-a always,exit -F arch=b64 -F exe=/usr/bin/bash -F success=1 -S connect -k "remote_shell"

### Successful IPv4 Connections
-a always,exit -F arch=b64 -S connect -F a2=16 -F success=1 -F key=network_connect_4

### Successful IPv6 Connections
-a always,exit -F arch=b64 -S connect -F a2=28 -F success=1 -F key=network_connect_6

### Changes to other files
-w /etc/hosts -p wa -k network_modifications
#-w /etc/sysconfig/network -p wa -k network_modifications
#-w /etc/sysconfig/network-scripts -p w -k network_modifications
-w /etc/network/ -p wa -k network
#-a always,exit -F dir=/etc/NetworkManager/ -F perm=wa -k network_modifications

### Changes to issue
-w /etc/issue -p wa -k etcissue
-w /etc/issue.net -p wa -k etcissue

## System startup scripts
-w /etc/inittab -p wa -k init
-w /etc/init.d/ -p wa -k init
-w /etc/init/ -p wa -k init

## Library search paths
-w /etc/ld.so.conf -p wa -k libpath
-w /etc/ld.so.conf.d -p wa -k libpath

## Systemwide library preloads (LD_PRELOAD)
-w /etc/ld.so.preload -p wa -k systemwide_preloads

## Pam configuration
-w /etc/pam.d/ -p wa -k pam
-w /etc/security/limits.conf -p wa  -k pam
-w /etc/security/limits.d -p wa  -k pam
-w /etc/security/pam_env.conf -p wa -k pam
-w /etc/security/namespace.conf -p wa -k pam
-w /etc/security/namespace.d -p wa -k pam
-w /etc/security/namespace.init -p wa -k pam

## Mail configuration
-w /etc/aliases -p wa -k mail
-w /etc/postfix/ -p wa -k mail
-w /etc/exim4/ -p wa -k mail

## SSH configuration
-w /etc/ssh/sshd_config -k sshd
-w /etc/ssh/sshd_config.d -k sshd

## root ssh key tampering
-w /root/.ssh -p wa -k rootkey

# Systemd
-w /bin/systemctl -p x -k systemd
-w /etc/systemd/ -p wa -k systemd
-w /usr/lib/systemd -p wa -k systemd

## https://systemd.network/systemd.generator.html
-w /etc/systemd/system-generators/ -p wa -k systemd_generator
#-w /usr/local/lib/systemd/system-generators/ -p wa -k systemd_generator
-w /usr/lib/systemd/system-generators -p wa -k systemd_generator

-w /etc/systemd/user-generators/ -p wa -k systemd_generator
#-w /usr/local/lib/systemd/user-generators/ -p wa -k systemd_generator
-w /lib/systemd/system-generators/ -p wa -k systemd_generator

## SELinux events that modify the system's Mandatory Access Controls (MAC)
-w /etc/selinux/ -p wa -k mac_policy

## Critical elements access failures
#-a always,exit -F arch=b64 -S open -F dir=/etc -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/bin -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/sbin -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/usr/bin -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/usr/sbin -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/var -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/home -F success=0 -k unauthedfileaccess
#-a always,exit -F arch=b64 -S open -F dir=/srv -F success=0 -k unauthedfileaccess

## Process ID change (switching accounts) applications
-w /bin/su -p x -k priv_esc
-w /usr/bin/sudo -p x -k priv_esc

## Power state
-w /sbin/shutdown -p x -k power
-w /sbin/poweroff -p x -k power
-w /sbin/reboot -p x -k power
-w /sbin/halt -p x -k power

## Session initiation information
-w /var/run/utmp -p wa -k session
-w /var/log/btmp -p wa -k session
-w /var/log/wtmp -p wa -k session

## Discretionary Access Control (DAC) modifications
#-a always,exit -F arch=b64 -S chmod  -F auid>=1000 -F auid!=-1 -k perm_mod
#-a always,exit -F arch=b64 -S chown -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fchmod -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fchmodat -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fchown -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fchownat -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fremovexattr -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S fsetxattr -F auid>=1000 -F auid!=-1 -k perm_mod
#-a always,exit -F arch=b64 -S lchown -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S lremovexattr -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S lsetxattr -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S removexattr -F auid>=1000 -F auid!=-1 -k perm_mod
-a always,exit -F arch=b64 -S setxattr -F auid>=1000 -F auid!=-1 -k perm_mod

# Special Rules ---------------------------------------------------------------

## Reconnaissance
-w /usr/bin/whoami -p x -k recon
-w /usr/bin/id -p x -k recon
-w /bin/hostname -p x -k recon
-w /bin/uname -p x -k recon
-w /etc/issue -p r -k recon
-w /etc/hostname -p r -k recon

## Suspicious activity
-w /usr/bin/wget -p x -k susp_activity
-w /usr/bin/curl -p x -k susp_activity
-w /usr/bin/base64 -p x -k susp_activity
-w /bin/nc -p x -k susp_activity
-w /bin/netcat -p x -k susp_activity
-w /usr/bin/ncat -p x -k susp_activity
-w /usr/bin/ss -p x -k susp_activity
-w /usr/bin/netstat -p x -k susp_activity
-w /usr/bin/ssh -p x -k susp_activity
-w /usr/bin/scp -p x -k susp_activity
-w /usr/bin/sftp -p x -k susp_activity
-w /usr/bin/ftp -p x -k susp_activity
-w /usr/bin/socat -p x -k susp_activity
-w /usr/bin/wireshark -p x -k susp_activity
-w /usr/bin/tshark -p x -k susp_activity
-w /usr/bin/rawshark -p x -k susp_activity
-w /usr/bin/rdesktop -p x -k susp_activity
-w /usr/local/bin/rdesktop -p x -k susp_activity
-w /usr/bin/wlfreerdp -p x -k susp_activity
-w /usr/bin/xfreerdp -p x -k susp_activity
-w /usr/local/bin/xfreerdp -p x -k susp_activity
-w /usr/bin/nmap -p x -k susp_activity

### uftp
### https://sourceforge.net/projects/uftp-multicast/
### UFTP is an encrypted multicast file transfer program, designed to securely, reliably, 
### and efficiently transfer files to multiple receivers simultaneously.
### FTP also has the capability to communicate over disjoint networks separated by one or 
### more firewalls (NAT traversal) and without full end-to-end multicast capability 
### (multicast tunneling) through the use of a UFTP proxy server.
### T1133_External_Remote_Services
-w /usr/bin/uftp -p x -k susp_activity
-w /usr/sbin/uftp -p x -k susp_activity

-w /lib/systemd/system/uftp.service -k susp_activity
-w /usr/lib/systemd/system/uftp.service -k susp_activity

### atftpd
### https://sourceforge.net/projects/atftp/
### https://github.com/madmartin/atftp
### atftp is a client/server implementation of the TFTP protocol that implements RFCs 1350, 2090, 2347, 2348, 2349 and 7440. 
### The server is multi-threaded and the client presents a friendly interface using libreadline.
### T1133_External_Remote_Services
-w /usr/bin/atftpd -p x -k susp_activity
-w /usr/sbin/atftpd -p x -k susp_activity

-w /usr/bin/in.tftpd -p x -k susp_activity
-w /usr/sbin/in.tftpd -p x -k susp_activity

-w /lib/systemd/system/atftpd.service -k susp_activity
-w /usr/lib/systemd/system/atftpd.service -k susp_activity

-w /lib/systemd/system/atftpd.socket -k susp_activity
-w /usr/lib/systemd/system/atftpd.socket -k susp_activity

## sssd
#-a always,exit -F path=/usr/libexec/sssd/p11_child -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/libexec/sssd/krb5_child -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/libexec/sssd/ldap_child -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/libexec/sssd/selinux_child -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/libexec/sssd/proxy_child -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts

## vte-2.91
#-a always,exit -F path=/lib64/vte-2.91/gnome-pty-helper -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/lib64/vte-2.91/gnome-pty-helper -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts

## T1002 Data Compressed

-w /usr/bin/zip -p x -k Data_Compressed
-w /usr/bin/gzip -p x -k Data_Compressed
-w /usr/bin/tar -p x -k Data_Compressed
-w /usr/bin/bzip2 -p x -k Data_Compressed

-w /usr/bin/lzip -p x -k Data_Compressed
-w /usr/local/bin/lzip -p x -k Data_Compressed

-w /usr/bin/lz4 -p x -k Data_Compressed
-w /usr/local/bin/lz4 -p x -k Data_Compressed

-w /usr/bin/lzop -p x -k Data_Compressed
-w /usr/local/bin/lzop -p x -k Data_Compressed

-w /usr/bin/plzip -p x -k Data_Compressed
-w /usr/local/bin/plzip -p x -k Data_Compressed

-w /usr/bin/pbzip2 -p x -k Data_Compressed
-w /usr/local/bin/pbzip2 -p x -k Data_Compressed

-w /usr/bin/lbzip2 -p x -k Data_Compressed
-w /usr/local/bin/lbzip2 -p x -k Data_Compressed

-w /usr/bin/pixz -p x -k Data_Compressed
-w /usr/local/bin/pixz -p x -k Data_Compressed

-w /usr/bin/pigz -p x -k Data_Compressed
-w /usr/local/bin/pigz -p x -k Data_Compressed
-w /usr/bin/unpigz -p x -k Data_Compressed
-w /usr/local/bin/unpigz -p x -k Data_Compressed

-w /usr/bin/zstd -p x -k Data_Compressed
-w /usr/local/bin/zstd -p x -k Data_Compressed

## Added to catch netcat on Ubuntu
-w /bin/nc.openbsd -p x -k susp_activity
-w /bin/nc.traditional -p x -k susp_activity

## Sbin suspicious activity
-w /sbin/iptables -p x -k sbin_susp
-w /sbin/ip6tables -p x -k sbin_susp
-w /sbin/ifconfig -p x -k sbin_susp
-w /usr/sbin/arptables -p x -k sbin_susp
-w /usr/sbin/ebtables -p x -k sbin_susp
-w /sbin/xtables-nft-multi -p x -k sbin_susp
-w /usr/sbin/nft -p x -k sbin_susp
-w /usr/sbin/tcpdump -p x -k sbin_susp
-w /usr/sbin/traceroute -p x -k sbin_susp
-w /usr/sbin/ufw -p x -k sbin_susp

### kde4
#-a always,exit -F path=/usr/libexec/kde4/kpac_dhcp_helper -F perm=x -F auid>=1000 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/libexec/kde4/kdesud -F perm=x -F auid>=1000 -F auid!=4294967295 -k T1078_Valid_Accounts

## dbus-send invocation
### may indicate privilege escalation CVE-2021-3560
-w /usr/bin/dbus-send -p x -k dbus_send
-w /usr/bin/gdbus -p x -k gdubs_call

## setfiles
#-a always,exit -F path=/usr/bin/setfiles -F perm=x -F auid>=500 -F auid!=4294967295 -k -F T1078_Valid_Accounts
#-a always,exit -F path=/usr/sbin/setfiles -F perm=x -F auid>=500 -F auid!=4294967295 -k -F T1078_Valid_Accounts

### dbus
#-a always,exit -F path=/lib64/dbus-1/dbus-daemon-launch-helper -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts
#-a always,exit -F path=/usr/lib64/dbus-1/dbus-daemon-launch-helper -F perm=x -F auid>=500 -F auid!=4294967295 -k T1078_Valid_Accounts

## pkexec invocation
### may indicate privilege escalation CVE-2021-4034
-w /usr/bin/pkexec -p x -k pkexec

## Suspicious shells
-w /bin/ash -p x -k susp_shell
-w /bin/csh -p x -k susp_shell
-w /bin/fish -p x -k susp_shell
-w /bin/tcsh -p x -k susp_shell
-w /bin/tclsh -p x -k susp_shell
-w /bin/xonsh -p x -k susp_shell
-w /usr/local/bin/xonsh -p x -k susp_shell
-w /bin/open -p x -k susp_shell
-w /bin/rbash -p x -k susp_shell

### https://gtfobins.github.io/gtfobins/wish/
-w /bin/wish -p x -k susp_shell
-w /usr/bin/wish -p x -k susp_shell

### https://gtfobins.github.io/gtfobins/yash/
-w /bin/yash -p x -k susp_shell
-w /usr/bin/yash -p x -k susp_shell

# Web Server Activity
## Change the number "33" to the ID of your WebServer user. Default: www-data:x:33:33
-a always,exit -F arch=b64 -S execve -F euid=33 -k detect_execve_www

### https://clustershell.readthedocs.io/
-w /bin/clush -p x -k susp_shell
-w /usr/local/bin/clush -p x -k susp_shell
#-w /etc/clustershell/clush.conf -p x -k susp_shell

### https://github.com/tmux/tmux
-w /bin/tmux -p x -k susp_shell
-w /usr/local/bin/tmux -p x -k susp_shell

## Shell/profile configurations
-w /etc/profile.d/ -p wa -k shell_profiles
-w /etc/profile -p wa -k shell_profiles
-w /etc/shells -p wa -k shell_profiles
-w /etc/bashrc -p wa -k shell_profiles
-w /etc/csh.cshrc -p wa -k shell_profiles
-w /etc/csh.login -p wa -k shell_profiles
-w /etc/fish/ -p wa -k shell_profiles
-w /etc/zsh/ -p wa -k shell_profiles

### https://github.com/xxh/xxh
-w /usr/local/bin/xxh.bash -p x -k susp_shell
-w /usr/local/bin/xxh.xsh -p x -k susp_shell
-w /usr/local/bin/xxh.zsh -p x -k susp_shell

## Injection
### These rules watch for code injection by the ptrace facility.
### This could indicate someone trying to do something bad or just debugging
-a always,exit -F arch=b64 -S ptrace -F a0=0x4 -k code_injection
-a always,exit -F arch=b64 -S ptrace -F a0=0x5 -k data_injection
-a always,exit -F arch=b64 -S ptrace -F a0=0x6 -k register_injection
-a always,exit -F arch=b64 -S ptrace -k tracing

## Anonymous File Creation
### These rules watch the use of memfd_create
### "memfd_create" creates anonymous file and returns a file descriptor to access it
### When combined with "fexecve" can be used to stealthily run binaries in memory without touching disk
-a always,exit -F arch=b64 -S memfd_create -F key=anon_file_create

## Privilege Abuse
### The purpose of this rule is to detect when an admin may be abusing power by looking in user's home dir.
-a always,exit -F dir=/home -F uid=0 -F auid>=1000 -F auid!=-1 -C auid!=obj_uid -k power_abuse

# Socket Creations
# will catch both IPv4 and IPv6

-a always,exit -F arch=b32 -S socket -F a0=2  -k network_socket_created
-a always,exit -F arch=b64 -S socket -F a0=2  -k network_socket_created

-a always,exit -F arch=b32 -S socket -F a0=10 -k network_socket_created
-a always,exit -F arch=b64 -S socket -F a0=10 -k network_socket_created

# Software Management ---------------------------------------------------------

# RPM (Redhat/CentOS)
-w /usr/bin/rpm -p x -k software_mgmt
-w /usr/bin/yum -p x -k software_mgmt

# DNF (Fedora/RedHat 8/CentOS 8)
-w /usr/bin/dnf -p x -k software_mgmt

# YAST/Zypper/RPM (SuSE)
-w /sbin/yast -p x -k software_mgmt
-w /sbin/yast2 -p x -k software_mgmt
-w /bin/rpm -p x -k software_mgmt
-w /usr/bin/zypper -k software_mgmt

# DPKG / APT-GET (Debian/Ubuntu)
-w /usr/bin/dpkg -p x -k software_mgmt
-w /usr/bin/apt -p x -k software_mgmt
-w /usr/bin/apt-add-repository -p x -k software_mgmt
-w /usr/bin/apt-get -p x -k software_mgmt
-w /usr/bin/aptitude -p x -k software_mgmt
-w /usr/bin/wajig -p x -k software_mgmt
-w /usr/bin/snap -p x -k software_mgmt

# PIP(3) (Python installs)
-w /usr/bin/pip -p x -k third_party_software_mgmt
-w /usr/local/bin/pip -p x -k third_party_software_mgmt
-w /usr/bin/pip3 -p x -k third_party_software_mgmt
-w /usr/local/bin/pip3 -p x -k third_party_software_mgmt
-w /usr/bin/pipx -p x -k third_party_software_mgmt
-w /usr/local/bin/pipx -p x -k third_party_software_mgmt

# npm
## T1072 third party software
## https://www.npmjs.com
## https://docs.npmjs.com/cli/v6/commands/npm-audit
-w /usr/bin/npm -p x -k third_party_software_mgmt

# Comprehensive Perl Archive Network (CPAN) (CPAN installs)
## T1072 third party software
## https://www.cpan.org
-w /usr/bin/cpan -p x -k third_party_software_mgmt

# Ruby (RubyGems installs)
## T1072 third party software
## https://rubygems.org
-w /usr/bin/gem -p x -k third_party_software_mgmt

# LuaRocks (Lua installs)
## T1072 third party software
## https://luarocks.org
-w /usr/bin/luarocks -p x -k third_party_software_mgmt

# Pacman (Arch Linux)
## https://wiki.archlinux.org/title/Pacman
## T1072 third party software
-w /etc/pacman.conf -p x -k third_party_software_mgmt
-w /etc/pacman.d -p x -k third_party_software_mgmt

# Special Software ------------------------------------------------------------

## GDS specific secrets
#-w /etc/puppet/ssl -p wa -k puppet_ssl

## IBM Bigfix BESClient
#-a always,exit -F arch=b64 -S open -F dir=/opt/BESClient -F success=0 -k soft_besclient
-w /var/opt/BESClient/ -p wa -k soft_besclient

## CHEF https://www.chef.io/chef/
-w /etc/chef -p wa -k soft_chef

## Salt
## https://saltproject.io/
## https://docs.saltproject.io/en/latest/ref/configuration/master.html
-w /etc/salt -p wa -k soft_salt
-w /usr/local/etc/salt -p wa -k soft_salt

## Otter
## https://inedo.com/otter
-w /etc/otter -p wa -k soft_otter

## T1081 Credentials In Files
-w /usr/bin/grep -p x -k string_search
-w /usr/bin/egrep -p x -k string_search
-w /usr/bin/ugrep -p x -k string_search

### https://github.com/tmbinc/bgrep
-w /usr/bin/bgrep -p x -k string_search

### https://github.com/BurntSushi/ripgrep
-w /usr/bin/rg -p x -k string_search

### https://github.com/awgn/cgrep

-w /usr/bin/cgrep -p x -k string_search

### https://github.com/jpr5/ngrep
-w /usr/bin/ngrep -p x -k string_search

### https://github.com/vrothberg/vgrep
-w /usr/bin/vgrep -p x -k string_search

### https://github.com/monochromegane/the_platinum_searcher
-w /usr/bin/pt -p x -k string_search

### https://github.com/gvansickle/ucg
-w /usr/bin/ucg -p x -k string_search

### https://github.com/ggreer/the_silver_searcher
-w /usr/bin/ag -p x -k string_search

### https://github.com/beyondgrep/ack3
### https://beyondgrep.com
-w /usr/bin/ack -p x -k string_search
-w /usr/local/bin/ack -p x -k string_search
-w /usr/bin/semgrep -p x -k string_search

# CrowdStrike Falcon
# Identify CrowdStrike Falcon Sensor updates
#-a always,exit -F arch=b32 -F path=/etc/crowdstrike/falcon-sensor.conf -p wa -F key=falcon_sensor_update
#-a always,exit -F arch=b64 -F path=/etc/crowdstrike/falcon-sensor.conf -p wa -F key=falcon_sensor_update

#-a always,exit -F arch=b32 -F path=/usr/lib/crowdstrike/falcon-sensor.conf -p wa -F key=falcon_sensor_update
#-a always,exit -F arch=b64 -F path=/usr/lib/crowdstrike/falcon-sensor.conf -p wa -F key=falcon_sensor_update

# Identify CrowdStrike Falcon Sensor
#-a always,exit -F arch=b32 -F dir=/etc/crowdstrike/ -p wa -F key=falcon_sensor
#-a always,exit -F arch=b64 -F dir=/etc/crowdstrike/ -p wa -F key=falcon_sensor

#-a always,exit -F arch=b32 -F dir=/usr/lib/crowdstrike/ -p wa -F key=falcon_sensor
#-a always,exit -F arch=b64 -F dir=/usr/lib/crowdstrike/ -p wa -F key=falcon_sensor

#-a always,exit -F arch=b32 -F dir=/opt/CrowdStrike/ -p wa -F key=falcon_sensor
#-a always,exit -F arch=b64 -F dir=/opt/CrowdStrike/ -p wa -F key=falcon_sensor

#-a always,exit -F arch=b32 -F dir=/var/log/crowdstrike/ -p wa -F key=falcon_sensor
#-a always,exit -F arch=b64 -F dir=/var/log/crowdstrike/ -p wa -F key=falcon_sensor

# Identify CrowdStrike Falcon Agent activity
-a always,exit -F arch=b32 -F path=/usr/bin/falcon-scout -p x -F key=falcon_agent
-a always,exit -F arch=b64 -F path=/usr/bin/falcon-scout -p x -F key=falcon_agent

-a always,exit -F arch=b32 -F path=/usr/bin/falcon-agent -p x -F key=falcon_agent
-a always,exit -F arch=b64 -F path=/usr/bin/falcon-agent -p x -F key=falcon_agent

# Identify CrowdStrike Falcon Sensor network
#-a always,exit -F arch=b32 -S connect -F dir=+ -F obj=/opt/CrowdStrike/falcon-sensor -F key=crowdstrike_network
#-a always,exit -F arch=b64 -S connect -F dir=+ -F obj=/opt/CrowdStrike/falcon-sensor -F key=crowdstrike_network

## Docker
-w /usr/bin/dockerd -k docker
-w /usr/bin/docker -k docker
-w /usr/bin/docker-containerd -k docker
-w /usr/bin/docker-runc -k docker
-w /var/lib/docker -p wa -k docker
-w /etc/docker -k docker
#-w /etc/sysconfig/docker -k docker
#-w /etc/sysconfig/docker-storage -k docker
-w /usr/lib/systemd/system/docker.service -k docker
-w /usr/lib/systemd/system/docker.socket -k docker

## Virtualization stuff
-w /usr/bin/qemu-system-x86_64 -p x -k qemu-system-x86_64
-w /usr/bin/qemu-img -p x -k qemu-img
-w /usr/bin/qemu-kvm -p x -k qemu-kvm
-w /usr/bin/qemu -p x -k qemu
-w /usr/bin/virtualbox -p x -k virtualbox
-w /usr/bin/virt-manager -p x -k virt-manager
-w /usr/bin/VBoxManage -p x -k VBoxManage

## Kubelet
-w /usr/bin/kubelet -k kubelet

# ipc system call
# /usr/include/linux/ipc.h

## msgctl
#-a always,exit -S ipc -F a0=14 -k Inter-Process_Communication
## msgget
#-a always,exit -S ipc -F a0=13 -k Inter-Process_Communication
## Use these lines on x86_64, ia64 instead
-a always,exit -F arch=b64 -S msgctl -k Inter-Process_Communication
-a always,exit -F arch=b64 -S msgget -k Inter-Process_Communication

## semctl
#-a always,exit -S ipc -F a0=3 -k Inter-Process_Communication
## semget
#-a always,exit -S ipc -F a0=2 -k Inter-Process_Communication
## semop
#-a always,exit -S ipc -F a0=1 -k Inter-Process_Communication
## semtimedop
#-a always,exit -S ipc -F a0=4 -k Inter-Process_Communication
## Use these lines on x86_64, ia64 instead
-a always,exit -F arch=b64 -S semctl -k Inter-Process_Communication
-a always,exit -F arch=b64 -S semget -k Inter-Process_Communication
-a always,exit -F arch=b64 -S semop -k Inter-Process_Communication
-a always,exit -F arch=b64 -S semtimedop -k Inter-Process_Communication

## shmctl
#-a always,exit -S ipc -F a0=24 -k Inter-Process_Communication
## shmget
#-a always,exit -S ipc -F a0=23 -k Inter-Process_Communication
## Use these lines on x86_64, ia64 instead
-a always,exit -F arch=b64 -S shmctl -k Inter-Process_Communication
-a always,exit -F arch=b64 -S shmget -k Inter-Process_Communication

# High Volume Events ----------------------------------------------------------

## Disable these rules if they create too many events in your environment

## Common Shells
-w /bin/bash -p x -k susp_shell
-w /bin/dash -p x -k susp_shell
-w /bin/busybox -p x -k susp_shell
-w /bin/zsh -p x -k susp_shell
-w /bin/sh -p x -k susp_shell
-w /bin/ksh -p x -k susp_shell

## Root command executions
-a always,exit -F arch=b64 -F euid=0 -F auid>=1000 -F auid!=-1 -S execve -k rootcmd

## File Deletion Events by User
#-a always,exit -F arch=b64 -S rmdir -S unlink -S unlinkat -S rename -S renameat -F auid>=1000 -F auid!=-1 -k delete

## File Access
### Unauthorized Access (unsuccessful)
#-a always,exit -F arch=b64 -S creat -S open -S openat -S open_by_handle_at -S truncate -S ftruncate -F exit=-EACCES -F auid>=1000 -F auid!=-1 -k file_access
#-a always,exit -F arch=b64 -S creat -S open -S openat -S open_by_handle_at -S truncate -S ftruncate -F exit=-EPERM -F auid>=1000 -F auid!=-1 -k file_access

### Unsuccessful Creation
#-a always,exit -F arch=b64 -S mkdir,creat,link,symlink,mknod,mknodat,linkat,symlinkat -F exit=-EACCES -k file_creation
#-a always,exit -F arch=b64 -S mkdir,link,symlink,mkdirat -F exit=-EPERM -k file_creation

### Unsuccessful Modification
#-a always,exit -F arch=b64 -S rename -S renameat -S truncate -S chmod -S setxattr -S lsetxattr -S removexattr -S lremovexattr -F exit=-EACCES -k file_modification
#-a always,exit -F arch=b64 -S rename -S renameat -S truncate -S chmod -S setxattr -S lsetxattr -S removexattr -S lremovexattr -F exit=-EPERM -k file_modification

## 32bit API Exploitation
### If you are on a 64 bit platform, everything _should_ be running
### in 64 bit mode. This rule will detect any use of the 32 bit syscalls
### because this might be a sign of someone exploiting a hole in the 32
### bit API.
-a always,exit -F arch=b32 -S all -k 32bit_api

# Make The Configuration Immutable --------------------------------------------

##-e 2
" > "$AUDITD_RULES"

  echo ""
  echo " - Enabling AUDITD"
  systemctl daemon-reload
  systemctl enable auditd.service
  systemctl restart auditd.service

  echo ""
  echo " - Prevent AUDITD to be manually stopped"
  sed -i "4i RefuseManualStop=yes" "$AUDITD_CONF_SERVICE"

  echo ""
  echo " - Reloading SYSTEMD"
  systemctl daemon-reload
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# APPARMOR (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing Packages"
PACKAGE_INSTALL='apparmor apparmor-profiles apparmor-utils libpam-apparmor'
for deb_install in $PACKAGE_INSTALL; do
  echo ""
  echo "   - Installing $deb_install"
  $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
done

echo ""
echo " - Create APPARMOR PAM profile"
if ! grep 'session.*pam_apparmor.so order=user,group,default' /etc/pam.d/*; then
  echo 'session optional pam_apparmor.so order=user,group,default' > /etc/pam.d/hardening-apparmor
fi

echo ""
echo " - Enabling APPARMOR during boot"
echo ""
echo " - Configuring kernel lockdown mode"
if [[ -f /boot/firmware/cmdline.txt ]]; then
  sed -i 's/^console=serial0,115200.*/& apparmor=1 security=apparmor/g' /boot/firmware/cmdline.txt
else
  if ! grep -q 'apparmor=1' /proc/cmdline; then
    echo "GRUB_CMDLINE_LINUX=\"\$GRUB_CMDLINE_LINUX apparmor=1 security=apparmor\"" > "$GRUB_DEFAULT/99-hardening-apparmor.cfg"
    update-grub
  fi
fi

echo ""
echo " - Enabling and starting APPARMOR"
systemctl daemon-reload
systemctl enable apparmor.service
systemctl restart apparmor.service

echo ""
echo " - Enforcing APPARMOR profiles"
find /etc/apparmor.d/ -maxdepth 1 -type f -exec aa-enforce {} \;

# -------------------------------------------------------------------------------------

if [ "$AIDE_ENABLE" = "true" ]; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# AIDE (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Installing Packages"
  PACKAGE_INSTALL='aide aide-common'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installing $deb_install"
    $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
  done

  echo ""
  echo " - Exclude some paths from AIDE scanning"
  echo '!/var/lib/lxcfs/cgroup' > "$AIDED/90_hardening_lxcfs"
  echo '!/var/lib/docker/.*' > "$AIDED/90_hardening_docker"
  echo '!/var/lib/rancher/.*' > "$AIDED/90_hardening_k3s"
  echo '!/var/lib/kubelet/pods/.*' >> "$AIDED/90_hardening_k3s"
  echo '!/var/lib/kubelet/plugins/.*' >> "$AIDED/90_hardening_k3s"
  echo '!/run/k3s/containerd/.*' >> "$AIDED/90_hardening_k3s"
  echo '!/var/lib/longhorn/.*' >> "$AIDED/90_hardening_k3s"
  echo '!/var/log/pods/.*' >> "$AIDED/90_hardening_k3s"
  echo '!/var/log/audit/.*' > "$AIDED/90_hardening_audit"
  echo '!/var/log/account/.*' > "$AIDED/90_hardening_pacct"
  echo '!/var/log/psad/.*' > "$AIDED/90_hardening_psad"
  echo '!/var/log/journal/.*' > "$AIDED/90_hardening_journal"
  echo '!/var/log/sysstat/.*' > "$AIDED/90_hardening_sysstat"

  echo ""
  echo " - Initialize AIDE - This will take a while"
  aideinit --yes

  echo ""
  echo " - Scheduling AIDE check every day at midnight"
  echo "
[Unit]
Description=Aide Check

[Service]
Type=simple
ExecStart=/usr/bin/aide --check --config "$AIDE_CONF"

[Install]
WantedBy=multi-user.target
" > /etc/systemd/system/aidecheck.service

  echo "
[Unit]
Description=Aide check every day at midnight

[Timer]
OnCalendar=*-*-* 03:00:00
Unit=aidecheck.service

[Install]
WantedBy=multi-user.target
" > /etc/systemd/system/aidecheck.timer

  chmod 0644 /etc/systemd/system/aidecheck.*

  echo ""
  echo " - Reloading SYSTEMD"
  systemctl daemon-reload

  echo ""
  echo " - Enabling AIDE check and reloading systemd"
  systemctl enable aidecheck.timer
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CLEANUP (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Removing unnecessary files"
rm -f /var/log/messages 2> /dev/null

echo ""
echo " - Cleanup not fully removed packages"
for deb_clean in $(dpkg -l | grep '^rc' | awk '{print $2}'); do
  echo "   - Purging $deb_clean"
  $APT purge "$deb_clean"
  echo ""
done

echo ""
echo " - Clean APT"
$APT clean
$APT autoremove

echo ""
echo " - Secure cfg-files in /boot"
find /boot/ -type f -name '*.cfg' -exec chmod 0400 "{}" \;

if ! [[ -f /boot/firmware/cmdline.txt ]]; then
  echo ""
  echo " - Update GRUB"
  update-grub
fi

echo ""
echo " - Start Unattended Upgrades"
systemctl start unattended-upgrades.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# LAST NOTES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Password $ADMIN_USER"
echo "   Please don't forget to set a new password for the user $ADMIN_USER. This will"
echo "   will create a fresh password, that uses the new password hashing algorithm."
echo "   You can set the password with the following command:"
echo "   passwd $ADMIN_USER"  

echo ""
echo " - Ubuntu Pro"
echo "   If you want to add your Ubuntu Server to a Ubuntu Pro subscription, you can"
echo "   do so by running the following commands:"
echo "   apt install ubuntu-advantage-tools"
echo "   pro attach <token>"
echo "   pro enable esm-apps"
echo "   pro enable esm-infra"
echo "   pro enable livepatch (only on supported kernels - amd64)"

echo ""
echo " - Reboot"
echo "   Please reboot your system to activate all changes."

echo ""
echo " - Cleanup backup files"
echo "   After the hardening script has finished and you have verified that everything"
echo "   is working as expected, you should remove the backup files with the following"
echo "   command:"
echo "   find /etc -name \"*.hardening-backup\" -type f -exec rm -f \"{}\" \;"

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF