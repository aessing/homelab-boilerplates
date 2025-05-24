#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ALL NODES WITH CLUSTER ENVIRONMENT FILE
###############################################################################

# =============================================================================
# MetalLB Firewall Rules
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

set -u -o pipefail

LOG_FILE="11-configure-firewall.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# MetalLB Firewall Rules"
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
if ! ps -p $$ | grep -sqi bash; then
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
  echo "   Usage: $0 <k8s-environment-name> || <env-file-name-without-extension>"
  echo "   Exiting."
  exit 1

  exit 1
fi

ENV_FILE="./../environments/$1.env"

echo ""
echo " - Does the .env file exists?"
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
echo "# VARIABLES (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Loading environment variables from '$ENV_FILE'"
set -o allexport
if ! source "$ENV_FILE"; then
  echo " - ERROR: Could not load environment file '$ENV_FILE'"
  exit 1
fi
set +o allexport

echo ""
echo " - Validating required environment variables"
REQUIRED_VARS=(K3S_NODES_SERVERS)
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
echo "# CONFIGURING FIREWALL (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Allow K3S nodes to connect to each other for MetalLB"
K3S_NODES_ALL="$K3S_NODES_SERVERS"
if [ -n "${K3S_NODES_AGENTS:-}" ]; then
  K3S_NODES_ALL+=" $K3S_NODES_AGENTS"
fi

for ip in $K3S_NODES_ALL; do
  ufw allow from "$ip" to any port 7946 proto tcp comment 'MetalLB UDP - All Nodes'
  ufw allow from "$ip" to any port 7946 proto udp comment 'MetalLB UDP - All Nodes'
done

echo ""
echo " - Reloading UFW to apply all new rules"
ufw reload

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF