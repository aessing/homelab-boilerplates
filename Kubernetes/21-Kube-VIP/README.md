# Kube-VIP Installation

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains a script for installing [Kube-VIP](https://kube-vip.io/) on a K3s cluster to provide a highly available virtual IP for the Kubernetes API server.

## Contents

| Script | Description |
|--------|-------------|
| `11-install-kube-vip.sh` | Installs Kube-VIP as a DaemonSet on control plane nodes |

## What is Kube-VIP?

Kube-VIP provides a virtual IP and load balancer for the Kubernetes control plane. In a multi-server K3s cluster, it ensures that if one control plane node fails, the virtual IP automatically moves to another healthy node, maintaining API server availability.

## Features

- **Virtual IP (VIP)**: Single IP address for Kubernetes API access
- **Leader Election**: Automatic failover between control plane nodes
- **ARP Mode**: Layer 2 load balancing using ARP announcements
- **DaemonSet Deployment**: Runs on all control plane nodes
- **Automatic Version Detection**: Fetches latest Kube-VIP release

## Prerequisites

- K3s cluster with at least one server node running
- Root access on a server node
- `jq` installed
- `kubectl` access to the cluster
- Environment file configured in `../environments/`

## Required Environment Variables

The script requires these variables from your environment file:

| Variable | Description | Example |
|----------|-------------|---------|
| `K3S_NODES_SERVERS` | Space-separated list of server node IPs | `192.168.0.101 192.168.0.102 192.168.0.103` |
| `K3S_TLSSAN_VIP` | Virtual IP address for the cluster | `192.168.0.100` |

## Quick Start

### 1. Ensure K3s is Running

The K3s cluster must be running before installing Kube-VIP:

```bash
kubectl get nodes
```

### 2. Run the Installation Script

Execute on any server node (first node recommended):

```bash
sudo ./11-install-kube-vip.sh <environment-name>
```

Example:

```bash
sudo ./11-install-kube-vip.sh mycluster
```

### 3. Verify Installation

Check that Kube-VIP pods are running:

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=kube-vip-ds
```

Verify the VIP is responding:

```bash
ping <K3S_TLSSAN_VIP>
curl -k https://<K3S_TLSSAN_VIP>:6443
```

## How It Works

1. **RBAC Setup**: Applies necessary RBAC rules for Kube-VIP
2. **Image Pull**: Downloads the latest Kube-VIP container image
3. **Manifest Generation**: Uses `kube-vip manifest daemonset` to generate the deployment
4. **Deployment**: Applies the DaemonSet to run on all control plane nodes
5. **Cleanup**: Removes the container image from local storage

### Kube-VIP Configuration

The script deploys Kube-VIP with these settings:

| Option | Value | Description |
|--------|-------|-------------|
| `--interface` | Auto-detected | Network interface for VIP |
| `--address` | `K3S_TLSSAN_VIP` | Virtual IP address |
| `--port` | `6443` | Kubernetes API server port |
| `--inCluster` | enabled | Use in-cluster configuration |
| `--taint` | enabled | Only run on control plane nodes |
| `--controlplane` | enabled | Enable control plane load balancing |
| `--arp` | enabled | Use ARP for Layer 2 VIP |
| `--leaderElection` | enabled | Enable leader election for HA |

## Updating Kube-VIP

After initial installation, Kube-VIP can be updated by changing the image version in the DaemonSet:

```bash
# Check current version
kubectl get daemonset -n kube-system kube-vip-ds -o jsonpath='{.spec.template.spec.containers[0].image}'

# Update to a new version
kubectl set image daemonset/kube-vip-ds -n kube-system kube-vip=ghcr.io/kube-vip/kube-vip:<NEW_VERSION>
```

The DaemonSet will perform a rolling update, replacing pods one at a time to maintain VIP availability.

## Troubleshooting

### Check Kube-VIP status

```bash
kubectl get pods -n kube-system | grep kube-vip
kubectl logs -n kube-system -l app.kubernetes.io/name=kube-vip-ds
```

### Verify VIP is active

```bash
# Check which node holds the VIP
kubectl get lease -n kube-system kube-vip-lease -o yaml

# Check ARP table
arp -a | grep <K3S_TLSSAN_VIP>
```

### Common issues

**VIP not responding:**
- Ensure the VIP is in the same subnet as the server nodes
- Check that no firewall is blocking ARP traffic
- Verify the network interface was detected correctly

**Pods not starting:**
- Check RBAC was applied: `kubectl get clusterrole kube-vip-role`
- Verify nodes have the control plane taint

## Related Resources

- [Kube-VIP Documentation](https://kube-vip.io/)
- [Kube-VIP GitHub Repository](https://github.com/kube-vip/kube-vip)
- [K3s High Availability](https://docs.k3s.io/datastore/ha-embedded)
