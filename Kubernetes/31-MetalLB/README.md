# MetalLB Load Balancer

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests and scripts for deploying [MetalLB](https://metallb.universe.tf/) on a K3s cluster to provide LoadBalancer services in bare-metal environments.

## Contents

| Item | Description |
|------|-------------|
| `11-configure-firewall.sh` | Configures UFW firewall rules for MetalLB communication |
| `base/` | Base Kustomize manifests for MetalLB deployment |
| `overlay/` | Environment-specific overlay configurations |

## What is MetalLB?

MetalLB is a load-balancer implementation for bare-metal Kubernetes clusters. It provides a network LoadBalancer implementation, allowing you to create Kubernetes services of type `LoadBalancer` in environments that don't have cloud provider load balancers.

## Features

- **Layer 2 Mode**: Uses ARP to announce service IPs on the local network
- **IP Address Pools**: Define ranges of IPs for LoadBalancer services
- **Helm Deployment**: Installed via K3s HelmChart controller
- **Automatic IP Assignment**: Optional auto-assignment of IPs to services

## Prerequisites

- K3s cluster running
- `kubectl` access to the cluster
- Environment file configured in `../environments/`
- IP address range available for LoadBalancer services

## Directory Structure

```text
31-MetalLB/
├── 11-configure-firewall.sh      # Firewall configuration script
├── base/
│   ├── kustomization.yaml        # Base kustomization
│   ├── resources/
│   │   ├── namespace.yaml        # metallb-system namespace
│   │   ├── helmchart.yaml        # HelmChart for MetalLB
│   │   ├── helmchartconfig.yaml  # HelmChart configuration
│   │   ├── ipaddresspool.yaml    # IP address pool definition
│   │   └── l2advertisement.yaml  # L2 advertisement configuration
│   ├── patches/
│   │   └── target-namespace.yaml # Namespace patch for HelmChart
│   └── transformers/
│       ├── helmchart.yaml        # Transformer for HelmChart
│       └── helmchartconfig.yaml  # Transformer for HelmChartConfig
└── overlay/
    └── _SAMPLE/
        ├── kustomization.yaml    # Sample overlay configuration
        └── patches/
            ├── version.yaml      # MetalLB version patch
            └── ip-range.yaml     # IP address range patch
```

## Quick Start

### 1. Configure Firewall on All Nodes

Run the firewall script on **all cluster nodes** to allow MetalLB communication:

```bash
sudo ./11-configure-firewall.sh <environment-name>
```

This opens port 7946 (TCP/UDP) for MetalLB memberlist communication between nodes.

### 2. Create Your Overlay

Copy the sample overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 3. Configure IP Address Range

Edit `overlay/my-environment/patches/ip-range.yaml` to define your LoadBalancer IP range:

```yaml
- op: replace
  path: /spec/addresses
  value:
    - 192.168.1.200-192.168.1.250
```

You can specify:

- A range: `192.168.1.200-192.168.1.250`
- A CIDR: `192.168.1.0/24`
- Individual IPs: `192.168.1.200/32`

### 4. Configure Version (Optional)

Edit `overlay/my-environment/patches/version.yaml` to set the MetalLB version:

```yaml
- op: replace
  path: /spec/version
  value: v0.15.2
```

### 5. Deploy MetalLB

```bash
# Preview the manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

### 6. Verify Installation

```bash
# Check MetalLB pods
kubectl get pods -n metallb-system

# Check IPAddressPool
kubectl get ipaddresspool -n metallb-system

# Check L2Advertisement
kubectl get l2advertisement -n metallb-system
```

## Using LoadBalancer Services

Once MetalLB is deployed, create a LoadBalancer service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  annotations:
    metallb.universe.tf/address-pool: default-pool  # Optional: specify pool
    metallb.universe.tf/loadBalancerIPs: 192.168.1.200  # Optional: request specific IP
spec:
  type: LoadBalancer
  # loadBalancerIP: 192.168.1.200  # Alternative: request specific IP
  ports:
    - port: 80
      targetPort: 8080
  selector:
    app: my-app
```

**Note:** The base configuration sets `autoAssign: false`, so you must either:

- Specify `loadBalancerIP` in the service spec, or
- Use the `metallb.universe.tf/loadBalancerIPs` annotation

## Configuration Reference

### IPAddressPool Options

| Field | Description |
|-------|-------------|
| `spec.addresses` | List of IP ranges for the pool |
| `spec.autoAssign` | Auto-assign IPs to services (default: false) |
| `spec.avoidBuggyIPs` | Avoid .0 and .255 addresses |

### L2Advertisement Options

| Field | Description |
|-------|-------------|
| `spec.ipAddressPools` | List of pools to advertise |
| `spec.nodeSelectors` | Limit which nodes advertise IPs |
| `spec.interfaces` | Limit which interfaces to use |

## Troubleshooting

### Check MetalLB status

```bash
kubectl get pods -n metallb-system
kubectl logs -n metallb-system -l app.kubernetes.io/component=controller
kubectl logs -n metallb-system -l app.kubernetes.io/component=speaker
```

### Check service IP assignment

```bash
kubectl get svc -A | grep LoadBalancer
kubectl describe svc <service-name> -n <namespace>
```

### Common issues

**Service stuck in Pending:**

- Verify IPAddressPool has available IPs
- Check if `autoAssign` is enabled or IP is specified
- Ensure MetalLB pods are running

**IP not reachable:**

- Verify firewall rules are configured on all nodes
- Check that the IP range is in the same subnet
- Ensure L2Advertisement is configured correctly

## Related Resources

- [MetalLB Documentation](https://metallb.universe.tf/)
- [MetalLB GitHub Repository](https://github.com/metallb/metallb)
- [K3s HelmChart Controller](https://docs.k3s.io/helm)
