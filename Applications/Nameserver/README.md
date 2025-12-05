# Nameserver (BIND9)

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying an authoritative DNS server using [BIND9](https://www.isc.org/bind/).

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Nameserver/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── deployment.yaml           # BIND9 deployment
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── service.yaml              # LoadBalancer service
├── components/
│   ├── _SAMPLE/                      # Sample zone configuration
│   │   ├── config/                   # BIND configuration
│   │   │   └── named.conf            # Main BIND config
│   │   └── zones/                    # Zone files
│   │       └── example.com.zone      # Sample zone
│   └── internal/                     # Internal zone configuration
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **Authoritative DNS**: Serve your own DNS zones
- **DNSSEC Support**: Secure DNS responses
- **LoadBalancer Access**: Direct DNS access via MetalLB
- **TLS Encryption**: DNS over TLS support
- **Multiple Zones**: Host multiple DNS zones

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [MetalLB](https://metallb.universe.tf/) for LoadBalancer services

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure DNS Zones

Create or modify components for your DNS zones. Each component should include:

**`config/named.conf`** - BIND configuration:

```
options {
    directory "/var/cache/bind";
    listen-on { any; };
    listen-on-v6 { any; };
    allow-query { any; };
    recursion no;
};

zone "example.com" {
    type master;
    file "/etc/bind/zones/example.com.zone";
};
```

**`zones/example.com.zone`** - Zone file:

```
$TTL 86400
@   IN  SOA ns1.example.com. admin.example.com. (
        2024010101  ; Serial
        3600        ; Refresh
        1800        ; Retry
        604800      ; Expire
        86400       ; Minimum TTL
    )
    IN  NS  ns1.example.com.
    IN  A   192.168.1.10

ns1 IN  A   192.168.1.10
www IN  A   192.168.1.20
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
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
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml` | Domain name for TLS cert |
| `###NUMBER_OF_ALLOWED_PODS###` | `resource-quota.yaml` | Number of allowed pods |
| `###IP_ADDRESS_FOR_SERVICE###` | `service.yaml` | MetalLB IP for DNS |

### Zone Configuration

Create a new component for each environment's zones:

```bash
cp -r components/_SAMPLE components/production
```

Edit the zone files and named.conf for your domains.

### DNSSEC

To enable DNSSEC, add to named.conf:

```
dnssec-validation auto;
```

And generate zone signing keys using `dnssec-keygen`.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n nameserver
kubectl get deployment nameserver -n nameserver
```

### View BIND logs

```bash
kubectl logs -n nameserver -l app.kubernetes.io/name=nameserver
```

### Check service

```bash
kubectl get svc -n nameserver
```

### Test DNS resolution

```bash
dig @<nameserver-ip> example.com
dig @<nameserver-ip> example.com NS
dig @<nameserver-ip> example.com SOA
```

### Check zone syntax

```bash
kubectl exec -it -n nameserver deployment/nameserver -- named-checkzone example.com /etc/bind/zones/example.com.zone
```

### Reload zones

```bash
kubectl exec -it -n nameserver deployment/nameserver -- rndc reload
```

## Related Resources

- [BIND9 Documentation](https://bind9.readthedocs.io/)
- [DNS Zone File Format](https://bind9.readthedocs.io/en/latest/reference.html#zone-file)
- [DNSSEC Guide](https://bind9.readthedocs.io/en/latest/dnssec-guide.html)
- [Kustomize Documentation](https://kustomize.io/)
