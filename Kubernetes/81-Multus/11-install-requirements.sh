#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ALL NODES 
###############################################################################

# =============================================================================
# Multus Requirements
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://www.andre-essing.de/)
#                                (https://github.com/aessing)
#                                (https://twitter.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

#############################
# NEEDS TO RUN ON ALL NODES #
#############################

set -u -o pipefail

echo ""
echo ""
echo "# ============================================================================="
echo "# Multus Requirements"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://www.andre-essing.de/)"
echo "#                                (https://github.com/aessing)"
echo "#                                (https://twitter.com/aessing)"
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

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CONFIGURING APPARMOR (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Adding some config line to APPARMOR busybox"
sed -i '/  include if exists <local\/busybox>/a \
\
  # Required for MULTUS on K3S to deploy and run\
  owner /etc/ld.so.cache** r,\
  owner /opt/cni/bin/** r,\
  owner /proc/** r,\
  owner /host/opt/cni/bin/** mrw,\
  owner /lib64/** mr,\
  owner /usr/lib64/** mr,' "/etc/apparmor.d/busybox"

echo ""
echo " - Parsing APPARMOR busybox config"
apparmor_parser -r /etc/apparmor.d/busybox

echo ""
echo " - Reloading APPARMOR"
systemctl reload apparmor

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF