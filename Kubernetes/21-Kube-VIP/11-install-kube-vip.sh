#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ONE SERVER NODE (FIRST NODE RECOMMENDED) 
# WITH CLUSTER ENVIRONMENT FILE
###############################################################################

# =============================================================================
# Kube-VIP Installation
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

# https://github.com/kube-vip/kube-vip

set -u -o pipefail

LOG_FILE="11-install-kube-vip.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# Kube-VIP Installation"
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
echo " - Is jq installed?"
if ! command -v jq &> /dev/null; then
  echo " -  - 'jq' is required but not installed."
  echo
  exit 1
fi

echo ""
echo " - Have you started the script with parameter?"
if [ "$#" -ne 1 ]; then
  echo ""
  echo " - Script needs environment file with variables as parameter."
  echo "   Usage: $0 <k8s-environment-name> || <env-file-name-without-extension>"
  echo "   Exiting."
  echo
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
set +o allexport

echo ""
echo " - Validating required environment variables"
REQUIRED_VARS=(K3S_NODES_SERVERS K3S_TLSSAN_VIP)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo " - ERROR: Required variable '$var' not set in environment file"
    exit 1
  fi
done

echo ""
echo " - Set some variables"
for ip in $K3S_NODES_SERVERS; do
  int=$(ip -4 route | grep "$ip" | awk '{print $3}')
  if [ -n "$int" ]; then
    INTERFACE=$int
    break
  fi
done

KVVERSION=$(curl -sL https://api.github.com/repos/kube-vip/kube-vip/releases | jq -r ".[0].name")

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# INSTALLING KUBE-VIP (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Apply RBAC rules"
kubectl apply -f https://kube-vip.io/manifests/rbac.yaml

echo ""
echo " - Download kube-vip image"
k3s ctr image pull ghcr.io/kube-vip/kube-vip:$KVVERSION

echo ""
echo " - Deploy kube-vip as a daemonset"
k3s ctr run --rm --net-host ghcr.io/kube-vip/kube-vip:$KVVERSION vip /kube-vip manifest daemonset \
  --interface $INTERFACE \
  --address $K3S_TLSSAN_VIP \
  --inCluster \
  --taint \
  --controlplane \
  --arp \
  --leaderElection | kubectl apply -f -

echo ""
echo " - Deleting kube-vip image"
k3s ctr image delete ghcr.io/kube-vip/kube-vip:$KVVERSION

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF