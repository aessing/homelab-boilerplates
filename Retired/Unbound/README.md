# Unbound

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Unbound](https://nlnetlabs.nl/projects/unbound/about/), a validating, recursive, and caching DNS resolver.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Unbound/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── deployment.yaml           # Unbound deployment
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── service.yaml              # Kubernetes service
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **Recursive Resolution**: Resolve DNS queries from root servers
- **DNSSEC Validation**: Cryptographic verification of DNS responses
- **Caching**: Improve performance with DNS caching
- **Privacy**: No third-party DNS providers needed
- **Pi-hole Integration**: Use as upstream resolver for Pi-hole

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)

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
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 3. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

## Configuration

### Unbound Configuration

The base deployment includes a default Unbound configuration. To customize, create a ConfigMap with your `unbound.conf`:

```yaml
server:
    interface: 0.0.0.0
    port: 53
    do-ip4: yes
    do-ip6: no
    do-udp: yes
    do-tcp: yes
    
    # Security
    hide-identity: yes
    hide-version: yes
    harden-glue: yes
    harden-dnssec-stripped: yes
    use-caps-for-id: yes
    
    # DNSSEC
    auto-trust-anchor-file: "/var/lib/unbound/root.key"
    
    # Performance
    num-threads: 2
    msg-cache-size: 50m
    rrset-cache-size: 100m
    cache-min-ttl: 3600
    cache-max-ttl: 86400
    
    # Access control
    access-control: 10.0.0.0/8 allow
    access-control: 192.168.0.0/16 allow
    access-control: 127.0.0.0/8 allow
```

### Pi-hole Integration

Configure Pi-hole to use Unbound as upstream DNS:

```bash
Custom DNS: 10.43.x.x#53  (Unbound service IP)
```

Enable DNSSEC in Pi-hole settings for end-to-end validation.

### Root Hints

Unbound includes root hints for recursive resolution. These are periodically updated in the container image.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n unbound
kubectl get deployment unbound -n unbound
```

### View Unbound logs

```bash
kubectl logs -n unbound -l app.kubernetes.io/name=unbound
```

### Test DNS resolution

```bash
# From within the cluster
kubectl run -it --rm debug --image=alpine --restart=Never -- nslookup google.com <unbound-service-ip>

# Direct query
dig @<unbound-service-ip> google.com
```

### Check DNSSEC validation

```bash
dig @<unbound-service-ip> dnssec-failed.org
# Should return SERVFAIL for invalid DNSSEC
```

### Check cache statistics

```bash
kubectl exec -it -n unbound deployment/unbound -- unbound-control stats
```

### Flush cache

```bash
kubectl exec -it -n unbound deployment/unbound -- unbound-control flush_zone .
```

### Check configuration

```bash
kubectl exec -it -n unbound deployment/unbound -- unbound-checkconf
```

## Performance Tuning

### Cache Size

Adjust cache sizes based on available memory:

```bash
msg-cache-size: 50m
rrset-cache-size: 100m
```

### Thread Count

Match `num-threads` to available CPU cores for optimal performance.

### Prefetching

Enable prefetching for frequently accessed domains:

```bash
prefetch: yes
prefetch-key: yes
```

## Related Resources

- [Unbound Documentation](https://nlnetlabs.nl/documentation/unbound/)
- [Unbound Configuration](https://nlnetlabs.nl/documentation/unbound/unbound.conf/)
- [DNSSEC](https://www.icann.org/resources/pages/dnssec-what-is-it-why-important-2019-03-05-en)
- [Pi-hole with Unbound](https://docs.pi-hole.net/guides/dns/unbound/)
- [Kustomize Documentation](https://kustomize.io/)
