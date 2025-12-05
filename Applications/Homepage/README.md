# Homepage

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Homepage](https://gethomepage.dev/), a highly customizable application dashboard.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Homepage/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── clusterrole.yaml          # RBAC cluster role
│       ├── clusterrolebinding.yaml   # RBAC binding
│       ├── deployment.yaml           # Homepage deployment
│       ├── ingressroute.yaml         # Traefik ingress route
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       ├── secret.yaml               # Configuration secret
│       ├── service.yaml              # Kubernetes service
│       └── serviceaccount.yaml       # Service account
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── configs/                  # Dashboard configuration
        │   ├── bookmarks.yaml        # Bookmark links
        │   ├── docker.yaml           # Docker integration
        │   ├── kubernetes.yaml       # Kubernetes integration
        │   ├── services.yaml         # Service widgets
        │   ├── settings.yaml         # Dashboard settings
        │   └── widgets.yaml          # Widget configuration
        ├── generators/               # ConfigMap generators
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **Customizable Dashboard**: Widgets, bookmarks, and service integrations
- **Kubernetes Integration**: Display pod status and resource usage
- **Service Widgets**: Pre-built widgets for popular applications
- **TLS Encryption**: Secure connections via cert-manager
- **RBAC Support**: Kubernetes cluster access for service discovery

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Dashboard

Edit the configuration files in your overlay's `configs/` directory:

**`configs/settings.yaml`** - Global dashboard settings:

```yaml
title: My Homepage
background: https://example.com/background.jpg
theme: dark
color: slate
```

**`configs/services.yaml`** - Service widgets and groups:

```yaml
- Infrastructure:
    - Proxmox:
        icon: proxmox.svg
        href: https://proxmox.example.com
        description: Hypervisor
```

**`configs/bookmarks.yaml`** - Quick access links:

```yaml
- Developer:
    - GitHub:
        - icon: github.svg
          href: https://github.com
```

**`configs/widgets.yaml`** - Dashboard widgets:

```yaml
- resources:
    cpu: true
    memory: true
    disk: /
```

**`configs/kubernetes.yaml`** - Kubernetes integration:

```yaml
mode: cluster
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `deployment-env.yaml` | Allowed hosts configuration |
| `ingressroute.yaml` | External hostname for web access |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 4. Deploy

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
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml`, `deployment-env.yaml` | External domain name |

### Allowed Hosts

Configure the `HOMEPAGE_ALLOWED_HOSTS` environment variable in `deployment-env.yaml`:

```yaml
- op: replace
  path: /spec/template/spec/containers/0/env/0/value
  value: "gethomepage.dev,homepage.example.com"
```

### Service Widgets

Homepage supports many service widgets. Common examples:

- **Proxmox**: Hypervisor status
- **Pi-hole**: DNS statistics
- **Traefik**: Ingress metrics
- **Portainer**: Container management
- **Home Assistant**: Smart home status

See [Homepage Widget Documentation](https://gethomepage.dev/widgets/) for all options.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n homepage
kubectl get deployment homepage -n homepage
```

### View application logs

```bash
kubectl logs -n homepage -l app.kubernetes.io/name=homepage
```

### Check configuration

```bash
kubectl get configmap -n homepage
kubectl describe configmap homepage-config -n homepage
```

### Validate RBAC

```bash
kubectl auth can-i list pods --as=system:serviceaccount:homepage:homepage -n homepage
```

### Configuration not updating

Homepage caches configuration. Restart the deployment to apply changes:

```bash
kubectl rollout restart deployment homepage -n homepage
```

## Related Resources

- [Homepage Documentation](https://gethomepage.dev/)
- [Homepage Widgets](https://gethomepage.dev/widgets/)
- [Homepage Services](https://gethomepage.dev/configs/services/)
- [Homepage GitHub](https://github.com/gethomepage/homepage)
- [Kustomize Documentation](https://kustomize.io/)
