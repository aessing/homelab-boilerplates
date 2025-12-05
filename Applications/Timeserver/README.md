# Timeserver (Chrony)

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying an NTP time server using [Chrony](https://chrony-project.org/).

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Timeserver/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── deployment.yaml           # Chrony deployment
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── service.yaml              # LoadBalancer service
├── components/
│   ├── _SAMPLE/                      # Sample chrony configuration
│   │   └── configs/
│   │       └── chrony.conf           # Chrony config file
│   └── config/                       # Production configuration
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **NTP Server**: Provide accurate time to network devices
- **Multiple Sources**: Sync from multiple upstream NTP servers
- **Stratum Control**: Configure stratum level
- **LoadBalancer Access**: Direct NTP access via MetalLB
- **High Accuracy**: Chrony provides excellent timekeeping

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [MetalLB](https://metallb.universe.tf/) for LoadBalancer services

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Chrony

Create or modify the chrony configuration component:

**`components/config/configs/chrony.conf`** - Chrony configuration:

```
# Upstream NTP servers
server 0.pool.ntp.org iburst
server 1.pool.ntp.org iburst
server 2.pool.ntp.org iburst
server 3.pool.ntp.org iburst

# Allow NTP client access from local networks
allow 192.168.0.0/16
allow 10.0.0.0/8

# Serve time even when not synchronized
local stratum 10

# Record the rate at which the system clock gains/loses time
driftfile /var/lib/chrony/drift

# Enable kernel synchronization of the real-time clock
rtcsync

# Log files location
logdir /var/log/chrony
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `resource-quota.yaml` | Namespace pod and PVC limits |
| `service.yaml` | LoadBalancer IP address |

### 4. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NUMBER_OF_ALLOWED_PODS###` | `resource-quota.yaml` | Number of allowed pods |
| `###IP_ADDRESS_FOR_SERVICE###` | `service.yaml` | MetalLB IP for NTP |

### Upstream Servers

Configure reliable upstream NTP servers:

| Server | Description |
|--------|-------------|
| `pool.ntp.org` | Global NTP pool |
| `time.google.com` | Google's NTP servers |
| `time.cloudflare.com` | Cloudflare's NTP servers |
| Regional pools | e.g., `0.de.pool.ntp.org` |

### Client Configuration

Configure network devices to use your timeserver:

**Linux (chrony/systemd-timesyncd):**
```
NTP=192.168.1.123
```

**Windows:**
```
w32tm /config /manualpeerlist:"192.168.1.123" /syncfromflags:manual /reliable:yes /update
```

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n timeserver
kubectl get deployment timeserver -n timeserver
```

### View chrony logs

```bash
kubectl logs -n timeserver -l app.kubernetes.io/name=timeserver
```

### Check service

```bash
kubectl get svc -n timeserver
```

### Check synchronization status

```bash
kubectl exec -it -n timeserver deployment/timeserver -- chronyc tracking
kubectl exec -it -n timeserver deployment/timeserver -- chronyc sources -v
```

### Test NTP connection

```bash
ntpdate -q <timeserver-ip>
# or
chronyc -h <timeserver-ip> tracking
```

### Check clients

```bash
kubectl exec -it -n timeserver deployment/timeserver -- chronyc clients
```

## Related Resources

- [Chrony Documentation](https://chrony-project.org/documentation.html)
- [Chrony Configuration](https://chrony-project.org/doc/4.4/chrony.conf.html)
- [NTP Pool Project](https://www.ntppool.org/)
- [Kustomize Documentation](https://kustomize.io/)
