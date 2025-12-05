# HomeCDN

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying HomeCDN, a simple static content delivery server using Nginx.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
HomeCDN/
├── base/
│   ├── kustomization.yaml
│   ├── configs/                      # Nginx configuration
│   ├── generators/                   # ConfigMap generators
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── deployment.yaml           # Nginx deployment
│       ├── ingressroute.yaml         # Traefik ingress route
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── pvc.yaml                  # Persistent volume claim
│       ├── resource-quota.yaml       # Namespace resource quotas
│       └── service.yaml              # Kubernetes service
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **Static Content Serving**: Nginx-based file serving
- **Persistent Storage**: Files stored on persistent volume
- **TLS Encryption**: Secure connections via cert-manager
- **Traefik Integration**: Ingress routing via Traefik

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller
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
| `pvc.yaml` | Persistent volume size |
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

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |

### Storage Configuration

The `pvc.yaml` patch controls the storage size:

```yaml
- op: replace
  path: /spec/resources/requests/storage
  value: "10Gi"
```

### Image Transformer

Update the `transformers/images.yaml` to set the Nginx version:

```yaml
images:
  - name: nginx
    newName: nginxinc/nginx-unprivileged
    newTag: "1.29.2"
```

## Uploading Content

After deployment, upload files to the persistent volume:

```bash
# Get the pod name
POD=$(kubectl get pods -n homecdn -l app.kubernetes.io/name=homecdn -o jsonpath='{.items[0].metadata.name}')

# Copy files to the pod
kubectl cp /local/path/to/files $POD:/usr/share/nginx/html/ -n homecdn
```

Alternatively, mount the PVC to a maintenance pod for file management.

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n homecdn
kubectl get deployment homecdn -n homecdn
```

### View Nginx logs

```bash
kubectl logs -n homecdn -l app.kubernetes.io/name=homecdn
```

### Check persistent volume

```bash
kubectl get pvc -n homecdn
kubectl describe pvc homecdn-data -n homecdn
```

### Test content delivery

```bash
curl -k https://<your-domain>/
```

## Related Resources

- [Nginx Documentation](https://nginx.org/en/docs/)
- [Nginx Unprivileged Image](https://hub.docker.com/r/nginxinc/nginx-unprivileged)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Kustomize Documentation](https://kustomize.io/)
