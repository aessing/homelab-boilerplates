# Pi-hole

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Pi-hole](https://pi-hole.net/), a network-wide ad blocking solution.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Pi-hole/
├── base/
│   ├── kustomization.yaml
│   ├── patches/                      # Base patches
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── ingressroute.yaml         # Traefik ingress route
│       ├── multus.yaml               # Multi-network configuration
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       ├── service.yaml              # Kubernetes services
│       └── statefulset.yaml          # Pi-hole StatefulSet
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **DNS Sinkhole**: Block ads and trackers at the DNS level
- **DHCP Server**: Optional DHCP functionality
- **Web Interface**: Admin dashboard for management
- **Multi-Network Support**: Multus CNI for direct network access
- **Persistent Storage**: Configuration and data persistence
- **TLS Encryption**: Secure web interface via cert-manager

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller
- [Multus CNI](https://github.com/k8snetworkplumbingwg/multus-cni) for network access
- Persistent storage provisioner (e.g., Longhorn)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-pihole-passwords.env`** - Admin credentials:

```dotenv
WEBPASSWORD=<your-secure-password>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `config.yaml` | Pi-hole configuration (DNS, timezone, etc.) |
| `ingressroute.yaml` | External hostname for web access |
| `multus.yaml` | Network interface configuration |
| `pvc.yaml` | Persistent volume size |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 4. Configure Multus

Edit the `multus.yaml` patch to configure the network interface:

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
      "addresses": [{"address": "192.168.1.53/24", "gateway": "192.168.1.1"}],
      "routes": [{"dst": "0.0.0.0/0"}]
    }
  }'
```

### 5. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |

### Pi-hole Configuration

Common environment variables for `config.yaml`:

```yaml
- name: TZ
  value: "Europe/Berlin"
- name: PIHOLE_DNS_
  value: "1.1.1.1;1.0.0.1"
- name: DNSSEC
  value: "true"
- name: QUERY_LOGGING
  value: "true"
```

### Network Configuration

Pi-hole requires direct network access to serve DNS. Use Multus to attach a secondary network interface with a static IP on your LAN.

### Upstream DNS

Configure upstream DNS servers in the Pi-hole configuration or web interface:

- Cloudflare: `1.1.1.1`, `1.0.0.1`
- Google: `8.8.8.8`, `8.8.4.4`
- Unbound (local): Configure with [Unbound](../Unbound/)

## High Availability

For Pi-hole HA, deploy multiple instances and use [Nebula-Sync](../Nebula-Sync/) to synchronize configurations.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n pihole
kubectl get statefulset pihole -n pihole
```

### View application logs

```bash
kubectl logs -n pihole -l app.kubernetes.io/name=pihole
```

### Check DNS resolution

```bash
dig @<pihole-ip> google.com
dig @<pihole-ip> ads.google.com
```

### Access admin interface

Navigate to `https://<your-domain>/admin` and login with your configured password.

### Check persistent volume

```bash
kubectl get pvc -n pihole
```

### Flush DNS cache

```bash
kubectl exec -it -n pihole pihole-0 -- pihole restartdns
```

### Update gravity database

```bash
kubectl exec -it -n pihole pihole-0 -- pihole -g
```

## Related Resources

- [Pi-hole Documentation](https://docs.pi-hole.net/)
- [Pi-hole Docker](https://github.com/pi-hole/docker-pi-hole)
- [Blocklists](https://firebog.net/)
- [Multus CNI Documentation](https://github.com/k8snetworkplumbingwg/multus-cni/blob/master/docs/README.md)
- [Kustomize Documentation](https://kustomize.io/)
