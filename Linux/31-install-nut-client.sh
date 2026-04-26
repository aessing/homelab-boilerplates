#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN WITH ENVIRONMENT FILE
###############################################################################

# =============================================================================
# NUT Client Installation Script
# Ubuntu Server 24.04 LTS
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================

set -euo pipefail

LOG_FILE="31-install-nut-client.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# NUT Client Installation Script"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://github.com/aessing)"
echo "#                                (https://www.linkedin.com/in/aessing/)"
echo "# -----------------------------------------------------------------------------"
echo "# THIS CODE AND INFORMATION ARE PROVIDED \"AS IS\" WITHOUT WARRANTY OF ANY KIND,"
echo "# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED"
echo "# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE."
echo "# ============================================================================="

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SETTING WORK ENVIRONMENT ($(date '+%F %T.%N'))"
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
echo "# PERFORMING SOME CHECKS ($(date '+%F %T.%N'))"
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
  exit 1
fi

echo ""
echo " - Are you running Ubuntu?"
if [ "$(lsb_release -is 2>/dev/null)" != "Ubuntu" ]; then
  echo ""
  echo " - Ubuntu only. Exiting."
  exit 1
fi

echo ""
echo " - Have you started the script with parameter?"
if [ "$#" -ne 1 ]; then
  echo ""
  echo " - Script needs environment file with variables as parameter."
  echo "   Usage: $0 <server-name> || <env-file-name-without-extension>"
  echo "   Exiting."
  exit 1
fi

ENV_FILE="./environments/$1.env"

echo ""
echo " - Does the .env file exist?"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo " - Script needs environment file with variables."
  echo "   File '$ENV_FILE' not found!"
  echo "   Exiting."
  exit 1
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# VARIABLES ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Loading environment variables from '$ENV_FILE'"
set -o allexport
# shellcheck disable=SC1090
if ! source "$ENV_FILE"; then
  echo " - ERROR: Could not load environment file '$ENV_FILE'"
  exit 1
fi
set +o allexport

echo ""
echo " - Validating required environment variables"
REQUIRED_VARS=(UPS_NUT_HOST UPS_NUT_NAME UPS_NUT_USER UPS_NUT_PASSWORD UPS_NUT_BATTERY_DELAY)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo " - ERROR: Required variable '$var' not set in environment file"
    exit 1
  fi
done

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# STARTING NUT CLIENT INSTALLATION ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# UPDATE PACKAGE LIST ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Updating package list"
apt-get update -qq

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# INSTALL NUT CLIENT ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Installing nut-client package"
apt-get install -y nut-client

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# BACKUP ORIGINAL CONFIGURATION ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Backing up original configuration files"
if [ -f /etc/nut/nut.conf ]; then
    cp /etc/nut/nut.conf /etc/nut/nut.conf.backup.$(date +%Y%m%d%H%M%S)
    echo "   Backed up nut.conf"
fi
if [ -f /etc/nut/upsmon.conf ]; then
    cp /etc/nut/upsmon.conf /etc/nut/upsmon.conf.backup.$(date +%Y%m%d%H%M%S)
    echo "   Backed up upsmon.conf"
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CONFIGURE NUT MODE ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Configuring NUT in netclient mode"
cat > /etc/nut/nut.conf << EOF
# NUT Configuration
# MODE: Standalone, netserver, or netclient
# netclient = This system is a client (no local UPS devices)
MODE=netclient
EOF

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CONFIGURE UPS MONITORING ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Configuring UPS monitoring"
cat > /etc/nut/upsmon.conf << EOF
# NUT UPS Monitor Configuration

# Monitor the remote UPS
# Format: MONITOR <system> <powervalue> <username> <password> ("master"|"slave")
# powervalue: number of power supplies driven by this UPS (typically 1)
# "slave" means this system is powered by the UPS but doesn't manage it
MONITOR ${UPS_NUT_NAME}@${UPS_NUT_HOST} 1 ${UPS_NUT_USER} ${UPS_NUT_PASSWORD} slave

# Number of UPS devices that must be available to keep system running
MINSUPPLIES 1

# Commands to run when shutting down
SHUTDOWNCMD "/sbin/shutdown -h +0"

# How long to wait after initial UPS communications failure before declaring it dead
DEADTIME 15

# Delay before initiating shutdown after UPS goes on battery (in seconds)
# Set to 5 seconds as upssched will handle the actual delay
FINALDELAY 5

# Polling interval (seconds) - how often to check the UPS status
POLLFREQ 5

# Interval to poll when UPS is on battery
POLLFREQALERT 5

# Interval to wait if UPS connection lost before declaring dead
HOSTSYNC 15

# User to run as (dropped privileges)
RUN_AS_USER nut

# Notification settings - use upssched to handle timed events
NOTIFYCMD /usr/sbin/upssched
NOTIFYFLAG ONLINE   SYSLOG+WALL+EXEC
NOTIFYFLAG ONBATT   SYSLOG+WALL+EXEC
NOTIFYFLAG LOWBATT  SYSLOG+WALL+EXEC
NOTIFYFLAG FSD      SYSLOG+WALL+EXEC
NOTIFYFLAG COMMOK   SYSLOG+WALL+EXEC
NOTIFYFLAG COMMBAD  SYSLOG+WALL+EXEC
NOTIFYFLAG SHUTDOWN SYSLOG+WALL+EXEC
NOTIFYFLAG REPLBATT SYSLOG+WALL+EXEC
NOTIFYFLAG NOCOMM   SYSLOG+WALL+EXEC
NOTIFYFLAG NOPARENT SYSLOG+WALL+EXEC

# Notification messages
NOTIFYMSG ONLINE    "UPS %s is back online"
NOTIFYMSG ONBATT    "UPS %s is on battery"
NOTIFYMSG LOWBATT   "UPS %s has a low battery"
NOTIFYMSG FSD       "UPS %s: forced shutdown in progress"
NOTIFYMSG COMMOK    "Communications with UPS %s established"
NOTIFYMSG COMMBAD   "Communications with UPS %s lost"
NOTIFYMSG SHUTDOWN  "System shutdown in progress"
NOTIFYMSG REPLBATT  "UPS %s: battery needs to be replaced"
NOTIFYMSG NOCOMM    "UPS %s is unavailable"
NOTIFYMSG NOPARENT  "upsmon parent process died - shutdown impossible"

# Power status on ONBATT event - system will shutdown after FINALDELAY seconds
POWERDOWNFLAG /etc/killpower
EOF

# Configure upssched for delayed shutdown with cancellation support
log_info "Configuring UPS scheduler..."
cat > /etc/nut/upssched.conf << EOF
# NUT UPS Scheduler Configuration
# Handles timed events and allows cancellation when power returns

# Command script to execute for events
CMDSCRIPT /etc/nut/upssched-cmd

# Directory for lock files
PIPEFN /run/nut/upssched.pipe
LOCKFN /run/nut/upssched.lock

# Timer definitions:
# AT <notifytype> <upsname> <command> <interval>
# - Starts a timer, executes command after interval seconds
# CANCEL <notifytype> <upsname> <command>
# - Cancels a pending timer

# When UPS goes on battery, start a ${UPS_NUT_BATTERY_DELAY} second timer
AT ONBATT * start-shutdown-timer ${UPS_NUT_BATTERY_DELAY}

# When UPS comes back online, cancel the shutdown timer
CANCEL ONBATT * start-shutdown-timer

# Execute immediately on low battery (don't wait)
AT LOWBATT * execute-shutdown 0

# Execute immediately on communication loss
AT COMMBAD * comms-lost 0

# Execute immediately when comms restored
AT COMMOK * comms-ok 0

# Execute immediately when back online
AT ONLINE * ups-back-online 0
EOF

cat > /etc/nut/upssched-cmd << 'EOFCMD'
#!/bin/bash
# UPS Scheduler Command Script
# Handles timed events from upssched

case "$1" in
    start-shutdown-timer)
        logger -t upssched-cmd "UPS on battery for configured delay - initiating shutdown"
        /usr/sbin/upsmon -c fsd
        ;;
    execute-shutdown)
        logger -t upssched-cmd "UPS battery low - initiating immediate shutdown"
        /usr/sbin/upsmon -c fsd
        ;;
    ups-back-online)
        logger -t upssched-cmd "UPS back online - shutdown cancelled"
        # Cancel any pending shutdown if it hasn't started yet
        /bin/shutdown -c 2>/dev/null || true
        ;;
    comms-lost)
        logger -t upssched-cmd "Communications with UPS lost"
        ;;
    comms-ok)
        logger -t upssched-cmd "Communications with UPS restored"
        ;;
    *)
        logger -t upssched-cmd "Unknown command: $1"
        ;;
esac
EOFCMD

chmod +x /etc/nut/upssched-cmd

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SET FILE PERMISSIONS ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Setting proper file permissions"
chmod 640 /etc/nut/nut.conf
chmod 640 /etc/nut/upsmon.conf
chmod 640 /etc/nut/upssched.conf
chown root:nut /etc/nut/nut.conf
chown root:nut /etc/nut/upsmon.conf
chown root:nut /etc/nut/upssched.conf

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DISABLE NUT SERVER COMPONENTS ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Disabling NUT server components"
systemctl stop nut-server 2>/dev/null || true
systemctl disable nut-server 2>/dev/null || true

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# ENABLE AND START NUT MONITOR ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Enabling and starting NUT monitor service"
systemctl daemon-reload
systemctl enable nut-monitor
systemctl restart nut-monitor

# Wait a moment for service to start
sleep 2

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# TEST CONNECTION ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Checking NUT monitor status"
if systemctl is-active --quiet nut-monitor; then
    echo "   NUT monitor service is running"
    
    echo ""
    echo " - Testing UPS connection"
    if timeout 5 upsc ${UPS_NUT_NAME}@${UPS_NUT_HOST} 2>/dev/null | head -5; then
        echo ""
        echo "   Successfully connected to UPS!"
    else
        echo ""
        echo "   WARNING: Could not query UPS status. Please check:"
        echo "     - Network connectivity to ${UPS_NUT_HOST}"
        echo "     - UPS server is running and accessible"
        echo "     - Username and password are correct"
        echo "     - Firewall allows port 3493"
    fi
else
    echo ""
    echo " - ERROR: NUT monitor service failed to start"
    echo "   Check logs with: journalctl -u nut-monitor -n 50"
    exit 1
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# INSTALLATION COMPLETE ($(date '+%F %T.%N'))"
echo "# -----------------------------------------------------------------------------"

echo ""
echo "NUT Client installation and configuration complete!"
echo ""
echo "Configuration summary:"
echo "  - UPS: ${UPS_NUT_NAME}@${UPS_NUT_HOST}"
echo "  - Mode: netclient (client only)"
echo "  - Shutdown delay: ${UPS_NUT_BATTERY_DELAY} seconds after going on battery"
echo "  - Auto-cancel: Shutdown will be cancelled if power returns within ${UPS_NUT_BATTERY_DELAY} seconds"
echo ""
echo "Useful commands:"
echo "  - Check UPS status:    upsc ${UPS_NUT_NAME}@${UPS_NUT_HOST}"
echo "  - Monitor service:     systemctl status nut-monitor"
echo "  - View logs:           journalctl -u nut-monitor -f"
echo "  - View events:         journalctl -t upssched-cmd -f"
echo "  - Test connection:     upsc -l ${UPS_NUT_HOST}"
echo ""

# -------------------------------------------------------------------------------------
# EOF
# -------------------------------------------------------------------------------------
