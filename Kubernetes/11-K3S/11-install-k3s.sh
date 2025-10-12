#!/usr/bin/env bash

###############################################################################
# NEEDS TO RUN ON ALL NODES WITH CLUSTER ENVIRONMENT FILE
###############################################################################

# =============================================================================
# K3s Installation Script
# -----------------------------------------------------------------------------
# Developer.......: Andre Essing (https://github.com/aessing)
#                                (https://www.linkedin.com/in/aessing/)
# Inspired by.....: https://downloads.cisecurity.org/
#                   https://docs.k3s.io
# -----------------------------------------------------------------------------
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.
# =============================================================================

# https://update.k3s.io/v1-release/channels

set -u -o pipefail

LOG_FILE="11-install-k3s.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo ""
echo "# ============================================================================="
echo "# K3s Installation Script"
echo "# $(cat /etc/lsb-release | grep -i -E DISTRIB_DESCRIPTION | sed 's/DISTRIB_DESCRIPTION=//' | sed 's/\"//g')"
echo "# -----------------------------------------------------------------------------"
echo "# Developer.......: Andre Essing (https://github.com/aessing)"
echo "#                                (https://www.linkedin.com/in/aessing/)"
echo "# Inspired by.....: https://downloads.cisecurity.org/"
echo "#                   https://docs.k3s.io"
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
echo " - Is jq installed?"
if ! [ -x "$(command -v jq)" ]; then
  echo " -  - 'jq' is required but not installed."
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
REQUIRED_VARS=(ADMIN_IPS K3S_CHANNEL K3S_CLUSTER_TOKEN K3S_AGENT_TOKEN K3S_NODES_FIRST K3S_NODES_SERVERS K3S_TLSSAN_VIP K3S_CLUSTER_DOMAIN K3S_NETWORK_CLUSTER K3S_NETWORK_SERVICES K3S_NODE_CIDR_SIZE_IPV4 K3S_FLANNEL_BACKEND K3S_MAX_PODS K3S_KUBECONFIG_MODE K3S_SERVICE_DISABLE K3S_EMBEDDED_REGISTRY PSAD_INSTALLED)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo " - ERROR: Required variable '$var' not set in environment file"
    exit 1
  fi
done

echo ""
echo " - Setting some path variables"
FSTAB_CONF='/etc/fstab'
K3S_CONF='/etc/rancher/k3s/config.yaml'
K3S_REGISTRIES='/etc/rancher/k3s/registries.yaml'
PSAD_DL='/etc/psad/auto_dl'
SYSCTLD='/etc/sysctl.d'

echo ""
echo " - Setting some other variables"
K3S_TLS_CIPHER_SUITES="TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305,TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305"
K3S_API_SERVER_REQUEST_TIMEOUT="300s"
K3S_NODES_ALL="$K3S_NODES_SERVERS"
if [ -n "${K3S_NODES_AGENTS:-}" ]; then
  K3S_NODES_ALL+=" $K3S_NODES_AGENTS"
fi
K3S_STREAMING_CONNECTION_IDLE_TIMEOUT="5m"
K3S_TERMINATED_POD_GC_THRESHOLD="10"
ETCD_VERSION=$(curl -sL https://api.github.com/repos/etcd-io/etcd/releases | jq -r ".[0].name")

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

K3S_NODES_SERVERS_COUNT=0
for server in $K3S_NODES_SERVERS; do
    let "K3S_NODES_SERVERS_COUNT=$K3S_NODES_SERVERS_COUNT+1"
done

K3S_NODES_AGENTS_COUNT=0
for server in $K3S_NODES_AGENTS; do
    let "K3S_NODES_AGENTS_COUNT=$K3S_NODES_AGENTS_COUNT+1"
done

K3S_NODES_ALL_COUNT=0
for server in $K3S_NODES_ALL; do
    let "K3S_NODES_ALL_COUNT=$K3S_NODES_ALL_COUNT+1"
done

export TERM="linux"
export DEBIAN_FRONTEND="noninteractive"
export NEEDRESTART_MODE="a"

echo ""
echo " - Setting up functions"
function exists_in_list() {
  LIST=$1
  DELIMITER=$2
  VALUE=$3
  echo $LIST | tr "$DELIMITER" '\n' | grep -F -q -x "$VALUE"
}

echo ""
echo " - Stopping Unattended Upgrades to not interfere with the next steps"
systemctl stop unattended-upgrades.service

# -------------------------------------------------------------------------------------

if cat /sys/firmware/devicetree/base/model 2>/dev/null | grep -iq "Raspberry"; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# KERNEL MODULES (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Install kernel module to support vxlan support on Raspberry Pi"
  PACKAGE_INSTALL='linux-modules-extra-raspi'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installed $deb_install"
    $APT -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install "$deb_install"
  done
fi

# -------------------------------------------------------------------------------------

if [[ -f /boot/firmware/cmdline.txt ]]; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# CGROUPS (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Enable cgroups"
  sed -i 's/^console=serial0,115200.*/& cgroup_memory=1 cgroup_enable=memory/g' /boot/firmware/cmdline.txt
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# KERNEL PARAMETERS (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo " - Set some K3S CIS compliant kernel hardening"
echo "
vm.panic_on_oom=0
vm.overcommit_memory=1
kernel.panic=10
kernel.panic_on_oops=1
kernel.keys.root_maxbytes=25000000
" > "$SYSCTLD/k3s.conf"

echo ""
echo " - Restart SYSCTL"
systemctl restart systemd-sysctl.service

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# SWAP (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo " - Disable SWAP"
swapoff -a -v

echo ""
echo " - Remove SWAP from FSTAB"
sed -i '/swap/d' $FSTAB_CONF

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# FIREWALL (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

if exists_in_list "$K3S_NODES_SERVERS" " " $SERVERIP; then
  echo ""
  echo " - Allow admins to connect to Kubernetes API Server"
  for ip in $ADMIN_IPS; do
    ufw allow from "$ip" to any port 6443 proto tcp comment 'K3S API TCP - Admins'
  done

  echo ""
  echo " - Allow server nodes to connect to Kubernetes API Server"
  for ip in $K3S_NODES_SERVERS; do
    ufw allow from "$ip" to any port 6443 proto tcp comment 'K3S API TCP - Server Nodes'
  done

  echo ""
  echo " - Allow agent nodes to connect to Kubernetes API Server"
  for ip in $K3S_NODES_AGENTS; do
    ufw allow from "$ip" to any port 6443 proto tcp comment 'K3S API TCP - Agent Nodes'
  done

  if [ $K3S_NODES_SERVERS_COUNT -ge 3 ]; then
    echo ""
    echo " - Allow embedded etcd communication"
    for ip in $K3S_NODES_SERVERS; do
      ufw allow from "$ip" to any port 2379:2380 proto tcp comment 'ETCD TCP - Server Nodes'
    done
  fi
fi

echo ""
echo " - Allow communication between nodes for embedded distributed registry (Spegel)"
for ip in $K3S_NODES_ALL; do
  ufw allow from "$ip" to any port 5001 proto tcp comment 'Embedded distributed registry (Spegel) TCP - All Nodes'
done

echo ""
echo " - Allow communication between nodes for Kubelet metrics"
for ip in $K3S_NODES_ALL; do
  ufw allow from "$ip" to any port 10250 proto tcp comment 'Kubelet metrics - All Nodes'
done

if [[ "$K3S_FLANNEL_BACKEND" == "vxlan" ]]; then
  echo ""
  echo " - Allow communication between nodes for Flannel VXLAN"
  for ip in $K3S_NODES_ALL; do
    ufw allow from "$ip" to any port 8472 proto udp comment 'Flannel VXLAN UDP - All Nodes'
  done
elif [[ "$K3S_FLANNEL_BACKEND" == "wireguard-native" ]]; then
  echo ""
  echo " - Allow communication between nodes for Flannel Wireguard"
  for ip in $K3S_NODES_ALL; do
    ufw allow from "$ip" to any port 51820 proto udp comment 'Flannel Wireguard IPv4 UDP - All Nodes'
    ufw allow from "$ip" to any port 51821 proto udp comment 'Flannel Wireguard IPv6 UDP - All Nodes'
  done
fi

echo ""
echo " - Allow pods and services network communication"
ufw allow from $K3S_NETWORK_CLUSTER to any comment 'POD communication - ANY'
ufw allow in on cni0 from $K3S_NETWORK_CLUSTER comment 'POD communication - CNI0'
ufw allow in on kube-bridge from $K3S_NETWORK_CLUSTER comment 'POD communication - KUBE-BRIDGE'
ufw allow from $K3S_NETWORK_SERVICES to any comment 'Service communication - ANY'
ufw allow in on cni0 from $K3S_NETWORK_SERVICES comment 'Service communication - CNI0'
ufw allow in on kube-bridge from $K3S_NETWORK_SERVICES comment 'CNI communication - KUBE-BRIDGE'
ufw allow in on cni0 comment 'Network IN - CNI0'
ufw allow out on cni0 comment 'Network OUT - CNI0'
ufw allow in on flannel.1 comment 'Network IN - FLANNEL.1'
ufw allow out on flannel.1 comment 'Network OUT - FLANNEL.1'

echo ""
echo " - Allow routed traffic"
ufw default allow routed

echo ""
echo " - Reload UFW"
ufw reload

# -------------------------------------------------------------------------------------

if [ "$PSAD_INSTALLED" = "true" ]; then
  echo ""
  echo ""
  echo "# -----------------------------------------------------------------------------"
  echo "# PSAD (`date '+%F %T.%N'`)"
  echo "# -----------------------------------------------------------------------------"

  echo ""
  echo " - Configuring danger levels for cluster and service networks"
  for ip in $K3S_NODES_ALL; do
    if ! [[ "$ip" == "$SERVERIP" ]]; then
      echo "$ip   0;"  >> "$PSAD_DL"
    fi
  done
  for cidr in $K3S_NETWORK_CLUSTER; do
      echo "$cidr   0;"  >> "$PSAD_DL"
  done
  for cidr in $K3S_NETWORK_SERVICES; do
      echo "$cidr   0;"  >> "$PSAD_DL"
  done

  echo ""
  echo " - Restart PSAD daemon"
  systemctl restart psad
fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# K3S (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Create K3s configuration file"
mkdir --mode=750 -p /etc/rancher/k3s
if exists_in_list "$K3S_NODES_SERVERS" " " $SERVERIP; then
  # Cluster Options
  echo "token: $K3S_CLUSTER_TOKEN" > "$K3S_CONF"
  echo "agent-token: $K3S_AGENT_TOKEN" >> "$K3S_CONF"
  if [ $K3S_NODES_SERVERS_COUNT -ge 2 ]; then
    if [[ $K3S_NODES_FIRST == $SERVERIP ]]; then
      echo "cluster-init: true" >> "$K3S_CONF"
    else
      echo "server: https://$K3S_NODES_FIRST:6443" >> "$K3S_CONF"
    fi
  fi

  # Database options
  echo "etcd-expose-metrics: false" >> "$K3S_CONF"
  echo "etcd-snapshot-retention: $K3S_ETCD_SNAPSHOT_RETENTION" >> "$K3S_CONF"
  echo "etcd-snapshot-schedule-cron: \"$K3S_ETCD_SNAPSHOT_SCHEDULE_CRON\"" >> "$K3S_CONF"
  echo "etcd-s3: $K3S_ETCD_SNAPSHOT_S3_ENABLED" >> "$K3S_CONF"
  echo "etcd-s3-config-secret: $K3S_ETCD_SNAPSHOT_S3_SECRET_NAME" >> "$K3S_CONF"

  # Admin Kubeconfig Options
  echo "write-kubeconfig-mode: $K3S_KUBECONFIG_MODE" >> "$K3S_CONF"

  # Listeners Options
  echo "tls-san:" >> "$K3S_CONF"
  echo "  - $K3S_CLUSTER_DOMAIN" >> "$K3S_CONF"
  #for ip in $K3S_NODES_ALL; do
  #    echo "  - $ip" >> "$K3S_CONF"
  #done  
  for ip in $K3S_TLSSAN_VIP; do
      echo "  - $ip" >> "$K3S_CONF"
  done  
  
  # Secrets Encryption
  echo "secrets-encryption: true" >> "$K3S_CONF"

  # Networking
  echo "cluster-cidr:" >> "$K3S_CONF"
  for cidr in $K3S_NETWORK_CLUSTER; do
      echo "  - $cidr" >> "$K3S_CONF"
  done
  echo "service-cidr:" >> "$K3S_CONF"
  for cidr in $K3S_NETWORK_SERVICES; do
      echo "  - $cidr" >> "$K3S_CONF"
  done
  echo "cluster-domain: $K3S_CLUSTER_DOMAIN" >> "$K3S_CONF"
  echo "flannel-backend: $K3S_FLANNEL_BACKEND" >> "$K3S_CONF"

  # Kubernetes Components
  if [ -n "$K3S_SERVICE_DISABLE" ]; then
    echo "disable:" >> "$K3S_CONF"
    for service in $K3S_SERVICE_DISABLE; do
      echo "  - $service" >> "$K3S_CONF"
    done
  fi
  echo "disable-scheduler: false" >> "$K3S_CONF"
  echo "disable-cloud-controller: false" >> "$K3S_CONF"
  echo "disable-kube-proxy: false" >> "$K3S_CONF"
  echo "disable-network-policy: false" >> "$K3S_CONF"
  echo "disable-helm-controller: false" >> "$K3S_CONF"
  echo "disable-apiserver: false" >> "$K3S_CONF"
  echo "disable-controller-manager: false" >> "$K3S_CONF"

  # Kube API Server Options
  echo "kube-apiserver-arg:" >> "$K3S_CONF"
  echo "  - \"request-timeout=$K3S_API_SERVER_REQUEST_TIMEOUT\"" >> "$K3S_CONF"

  # Kube Controller Manager Options
  echo "kube-controller-manager-arg:" >> "$K3S_CONF"
  echo "  - 'terminated-pod-gc-threshold=$K3S_TERMINATED_POD_GC_THRESHOLD'" >> "$K3S_CONF"
  if [ -n "$K3S_NODE_CIDR_SIZE_IPV4" ]; then
    echo "  - \"node-cidr-mask-size-ipv4=$K3S_NODE_CIDR_SIZE_IPV4\"" >> "$K3S_CONF"
  fi

  # Kubelet Options
  echo "kubelet-arg:" >> "$K3S_CONF"
  echo "  - \"max-pods=$K3S_MAX_PODS\"" >> "$K3S_CONF"
  echo "  - 'streaming-connection-idle-timeout=$K3S_STREAMING_CONNECTION_IDLE_TIMEOUT'" >> "$K3S_CONF"
  echo "  - \"tls-cipher-suites=$K3S_TLS_CIPHER_SUITES\"" >> "$K3S_CONF"

  # Experimental Options
  echo "embedded-registry: $K3S_EMBEDDED_REGISTRY" >> "$K3S_CONF"

  # Other Options
  echo "protect-kernel-defaults: true" >> "$K3S_CONF"
elif exists_in_list "$K3S_NODES_AGENTS" " " $SERVERIP; then
  # Cluster Options
  echo "token: $K3S_AGENT_TOKEN" > $K3S_CONF
  echo "server: https://$K3S_NODES_FIRST:6443" >> "$K3S_CONF"

  # Kubelet Options
  echo "kubelet-arg:" >> "$K3S_CONF"
  echo "  - \"max-pods=$K3S_MAX_PODS\"" >> "$K3S_CONF"
  echo "  - 'streaming-connection-idle-timeout=$K3S_STREAMING_CONNECTION_IDLE_TIMEOUT'" >> "$K3S_CONF"
  echo "  - \"tls-cipher-suites=$K3S_TLS_CIPHER_SUITES\"" >> "$K3S_CONF"

  # Other Options
  echo "protect-kernel-defaults: true" >> "$K3S_CONF"
else
  echo " - ERROR: This node is not in the list of K3S Servers or Agents"
  exit 1
fi

# Create K3s registries file
echo ""
echo " - Create K3s registries file"
tee "$K3S_REGISTRIES" > /dev/null <<EOF
mirrors:
  docker.io:
  registry.k8s.io:
  ghcr.io:
  quay.io:
  "*":
EOF

# Install Wireguard if needed
if [[ $K3S_FLANNEL_BACKEND == "wireguard-native" ]]; then
echo ""
  echo " - Install Wireguard because of your choice of Flannel backend"
  PACKAGE_INSTALL='wireguard'
  for deb_install in $PACKAGE_INSTALL; do
    echo ""
    echo "   - Installed $deb_install"
    $APT install "$deb_install"
  done
fi

# Install K3S
echo ""
echo " - Install K3S"
if exists_in_list "$K3S_NODES_SERVERS" " " $SERVERIP; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=$K3S_CHANNEL INSTALL_K3S_SKIP_START=true INSTALL_K3S_EXEC="server" sh -s -
elif exists_in_list "$K3S_NODES_AGENTS" " " $SERVERIP; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=$K3S_CHANNEL INSTALL_K3S_SKIP_START=true INSTALL_K3S_EXEC="agent" sh -s -
else
  echo " - ERROR: This node is not in the list of K3S Servers or Agents"
  exit 1
fi

# -------------------------------------------------------------------------------------

# if [ $K3S_NODES_SERVERS_COUNT -ge 3 ]; then
#   echo ""
#   echo ""
#   echo "# -----------------------------------------------------------------------------"
#   echo "# ETCDCTL (`date '+%F %T.%N'`)"
#   echo "# -----------------------------------------------------------------------------"

#   echo ""
#   echo " - Installing ETCDCTL"
#   ETCD_URL="https://github.com/etcd-io/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-linux-arm64.tar.gz"
#   curl -sL ${ETCD_URL} | sudo tar -zxv --strip-components=1 -C /usr/local/bin

#   echo ""
#   echo " - Configuring ETCDCTL to use K3s-managed certificates"
#   etcdctl version --cacert=/var/lib/rancher/k3s/server/tls/etcd/server-ca.crt --cert=/var/lib/rancher/k3s/server/tls/etcd/client.crt  --key=/var/lib/rancher/k3s/server/tls/etcd/client.key

#   echo ""
#   echo " - Cleanup ETCDCTL"
#   rm -f /usr/local/bin/README-etcdctl.md
#   rm -f /usr/local/bin/README-etcdutl.md
#   rm -f /usr/local/bin/README.md
#   rm -f /usr/local/bin/READMEv2-etcdctl.md
#   rm -f -r /usr/local/bin/Documentation
# fi

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# CLEANUP (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"

echo ""
echo " - Clean APT"
$APT clean
$APT autoremove

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
echo " - Reboot"
echo "   Please reboot your system to apply changes."

# -------------------------------------------------------------------------------------

echo ""
echo ""
echo "# -----------------------------------------------------------------------------"
echo "# DONE! (`date '+%F %T.%N'`)"
echo "# -----------------------------------------------------------------------------"
echo ""

################################################################################
#EOF