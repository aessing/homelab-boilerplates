# K3s Installation and Configuration

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains scripts for installing and configuring a highly available [K3s](https://k3s.io/) Kubernetes cluster with CIS-compliant security hardening.

## Contents

| Script | Description |
|--------|-------------|
| `11-install-k3s.sh` | Main K3s installation script with security hardening |
| `21-create-etcd-snapshot-secret.sh` | Creates Kubernetes secret for etcd S3 backup configuration |
| `22-raise-k3-reliability.sh` | Increases replica count for critical system components |
| `23-set-storageclass-nondefault.sh` | Removes default annotation from local-path StorageClass |

## Features

- **High Availability**: Multi-node cluster with embedded etcd
- **CIS Hardening**: Kernel parameters and security configurations
- **Automated Backups**: etcd snapshots to S3-compatible storage
- **Embedded Registry**: Distributed container image caching (Spegel)
- **Firewall Integration**: Automatic UFW rules for cluster communication
- **PSAD Support**: Optional integration with Port Scan Attack Detector

## Prerequisites

- Ubuntu Server (24.04 LTS recommended)
- Root access on all nodes
- `jq` installed on all nodes
- Network connectivity between all nodes
- Environment file configured in `../environments/`

## Quick Start

### 1. Create Environment File

Copy the sample environment file and configure it for your cluster:

```bash
cp ../environments/_SAMPLE.env ../environments/mycluster.env
```

### 2. Configure Environment Variables

Edit the environment file with your cluster settings. Key variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `K3S_NODES_FIRST` | IP of the first server node | `192.168.0.101` |
| `K3S_NODES_SERVERS` | Space-separated list of server IPs | `192.168.0.101 192.168.0.102 192.168.0.103` |
| `K3S_NODES_AGENTS` | Space-separated list of agent IPs | `192.168.0.111 192.168.0.112` |
| `K3S_TLSSAN_VIP` | Virtual IP for the cluster (Kube-VIP) | `192.168.0.100` |
| `K3S_CLUSTER_TOKEN` | Shared secret for server nodes | Random secure string |
| `K3S_AGENT_TOKEN` | Shared secret for agent nodes | Random secure string |
| `K3S_CLUSTER_DOMAIN` | Cluster domain name | `cluster.example.tld` |
| `ADMIN_IPS` | IPs allowed to access API server | `192.168.0.0/24` |

### 3. Install K3s on All Nodes

Run the installation script on each node, starting with the first server:

```bash
# On the FIRST server node
sudo ./11-install-k3s.sh mycluster

# On remaining server nodes (after first node is ready)
sudo ./11-install-k3s.sh mycluster

# On agent nodes (after all servers are ready)
sudo ./11-install-k3s.sh mycluster
```

### 4. Post-Installation Configuration

After all nodes are joined, run the following on any server node:

```bash
# Increase replicas for reliability
sudo ./22-raise-k3-reliability.sh

# Remove default StorageClass (if using Longhorn)
sudo ./23-set-storageclass-nondefault.sh

# Configure etcd S3 backups (optional)
sudo ./21-create-etcd-snapshot-secret.sh mycluster
```

## Environment Variables Reference

### Cluster Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `K3S_CHANNEL` | K3s release channel | `stable` |
| `K3S_NETWORK_CLUSTER` | Pod network CIDR | `192.168.128.0/18` |
| `K3S_NETWORK_SERVICES` | Service network CIDR | `192.168.192.0/18` |
| `K3S_NODE_CIDR_SIZE_IPV4` | CIDR size per node | `22` |
| `K3S_FLANNEL_BACKEND` | CNI backend | `vxlan` |
| `K3S_MAX_PODS` | Max pods per node | `250` |
| `K3S_KUBECONFIG_MODE` | Kubeconfig file permissions | `600` |
| `K3S_SERVICE_DISABLE` | Services to disable | `local-storage servicelb traefik` |
| `K3S_EMBEDDED_REGISTRY` | Enable Spegel registry | `true` |

### etcd Backup Configuration

| Variable | Description |
|----------|-------------|
| `K3S_ETCD_SNAPSHOT_RETENTION` | Local snapshot retention count |
| `K3S_ETCD_SNAPSHOT_SCHEDULE_CRON` | Backup schedule (cron format) |
| `K3S_ETCD_SNAPSHOT_S3_ENABLED` | Enable S3 backups |
| `K3S_ETCD_SNAPSHOT_S3_ENDPOINT` | S3 endpoint URL |
| `K3S_ETCD_SNAPSHOT_S3_BUCKET` | S3 bucket name |
| `K3S_ETCD_SNAPSHOT_S3_REGION` | S3 region |

## Security Hardening

The installation script applies CIS-compliant security configurations:

- **Kernel Parameters**: Panic on OOM, memory overcommit settings
- **TLS Cipher Suites**: Strong cipher configuration for API server
- **Swap Disabled**: Required for Kubernetes
- **Firewall Rules**: Automatic UFW configuration for cluster ports
- **PSAD Integration**: Optional port scan detection

## Troubleshooting

### Check cluster status

```bash
kubectl get nodes
kubectl get pods -A
```

### View K3s logs

```bash
# Server nodes
journalctl -u k3s -f

# Agent nodes
journalctl -u k3s-agent -f
```

## Updating K3s

Kubernetes regularly releases updates with bug fixes and new features. Kubernetes has a [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/) that describes which versions are supported.

> [!NOTE]
> New Kubernetes versions typically receive 1 year of patch support. Within this timeframe, you should upgrade to the next stable Kubernetes version.

### K3s Release Channels

For a stable K3s installation, we use the `stable` release channel instead of `latest`.

The `stable` channel may not always be the most current version (e.g., when `latest` is 1.30, `stable` is typically 1.29), but it is better tested and generally more reliable.

You can view the version mapping in the [K3s Channel Service API](https://update.k3s.io/v1-release/channels).

To retrieve the current `stable` version via command line:

```bash
curl -s https://update.k3s.io/v1-release/channels | jq -r '.data[] | select(.id=="stable") | .latest'
```

### Performing the Update

Updating K3s is straightforward and typically results in minimal to no downtime. The simplicity comes from storing all important K3s parameters in `/etc/rancher/k3s/config.yaml` during the initial installation. This allows the setup to reuse these parameters automatically.

> [!IMPORTANT]
> The update must be executed as root user.

#### Update a Server Node

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=stable INSTALL_K3S_EXEC="server" sh -s -
```

#### Update an Agent Node

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_CHANNEL=stable INSTALL_K3S_EXEC="agent" sh -s -
```

### Update Order

When updating a multi-node cluster, follow this sequence:

1. **Update server nodes first** - Start with server nodes to ensure the control plane is updated
2. **Update agent nodes** - After all servers are updated, proceed with agents
3. **Verify cluster health** - Check that all nodes are `Ready` after updates

```bash
kubectl get nodes
```

## Related Resources

- [K3s Documentation](https://docs.k3s.io/)
- [K3s GitHub Repository](https://github.com/k3s-io/k3s)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
