# Scrypted

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Scrypted](https://www.scrypted.app/), a high-performance home video integration platform.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Scrypted/
├── base/
│   ├── kustomization.yaml
│   ├── configs/                      # Configuration files
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── ingressroute.yaml         # Traefik ingress route
│       ├── multus.yaml               # Multi-network configuration
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       ├── service.yaml              # Kubernetes service
│       └── statefulset.yaml          # Scrypted StatefulSet
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **HomeKit Integration**: Expose cameras and sensors to Apple Home
- **Google Home Integration**: Connect devices to Google Assistant
- **Alexa Integration**: Amazon Echo device support
- **ONVIF Support**: Compatible with ONVIF cameras
- **Multi-Network Support**: Multus CNI for camera network access
- **Hardware Acceleration**: GPU support for video processing
- **TLS Encryption**: Secure connections via cert-manager

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller
- [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni) for camera network access
- Persistent storage provisioner (e.g., Longhorn)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `ingressroute.yaml` | External hostname for web access |
| `multus.yaml` | Network interface configuration |
| `pvc-application.yaml` | Persistent volume size |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 3. Configure Multus

Edit the `multus.yaml` patch to configure the network interface for camera access:

```yaml
- op: replace
  path: /spec/config
  value: '{
    "cniVersion": "0.3.1",
    "type": "ipvlan",
    "master": "eth0",
    "mode": "l2",
    "ipam": {
      "type": "static",
      "addresses": [{"address": "192.168.1.100/24", "gateway": "192.168.1.1"}],
      "routes": [{"dst": "192.168.1.0/24"}]
    }
  }'
```

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
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_SCRYPTED###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |
| `###NUMBER_OF_ALLOWED_PODS(1)###` | `resource-quota.yaml` | Number of allowed pods |
| `###NUMBER_OF_ALLOWED_VOLUMES(1)###` | `resource-quota.yaml` | Number of allowed PVCs |

### Network Configuration

Scrypted needs direct access to camera networks. Use Multus to attach a secondary network interface that can reach your cameras.

### Hardware Acceleration

For GPU-accelerated video processing, add device mappings to the StatefulSet:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```

Or for Intel QuickSync:

```yaml
securityContext:
  privileged: true
volumeMounts:
  - name: dev-dri
    mountPath: /dev/dri
```

## Initial Setup

After deployment:

1. Access Scrypted at your configured domain
2. Create an admin account
3. Install plugins for your camera brands
4. Add cameras using ONVIF or manufacturer plugins
5. Configure HomeKit, Google Home, or Alexa integration

## Supported Integrations

- **HomeKit Secure Video**: Full HKSV support with motion clips
- **Google Home**: Camera streaming and motion detection
- **Alexa**: Echo Show camera viewing
- **Home Assistant**: Native integration
- **MQTT**: Event publishing

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n scrypted
kubectl get statefulset scrypted -n scrypted
```

### View application logs

```bash
kubectl logs -n scrypted -l app.kubernetes.io/name=scrypted
```

### Check network connectivity

```bash
kubectl exec -it -n scrypted scrypted-0 -- ping <camera-ip>
```

### Check persistent volume

```bash
kubectl get pvc -n scrypted
```

### Access console

Navigate to your configured domain. The web console provides camera management, plugin installation, and configuration.

### Plugin issues

Check plugin logs in the Scrypted web console under the plugin settings.

## Related Resources

- [Scrypted Documentation](https://docs.scrypted.app/)
- [Scrypted GitHub](https://github.com/koush/scrypted)
- [Scrypted Discord](https://discord.gg/DcFzmBHYGq)
- [Multus CNI Documentation](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/docs/README.md)
- [Kustomize Documentation](https://kustomize.io/)
