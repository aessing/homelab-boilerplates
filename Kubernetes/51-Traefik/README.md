# Traefik Ingress Controller

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Traefik](https://traefik.io/) as the ingress controller on a K3s cluster with TLS termination, middleware chains, and dashboard access.

## Contents

| Item | Description |
|------|-------------|
| `base/` | Base Kustomize manifests for Traefik deployment |
| `overlay/` | Environment-specific overlay configurations |

## What is Traefik?

Traefik is a modern HTTP reverse proxy and load balancer designed for deploying microservices. It automatically discovers services and configures itself dynamically, making it ideal for Kubernetes environments.

## Features

- **Automatic TLS**: Integration with cert-manager for Let's Encrypt certificates
- **IngressRoute CRDs**: Native Traefik routing with powerful matching rules
- **Middleware Chains**: Security headers, rate limiting, IP allowlists, compression
- **Dashboard**: Secured Traefik dashboard with basic auth or Authentik SSO
- **Helm Deployment**: Installed via K3s HelmChart controller
- **Multi-entrypoint**: HTTP, HTTPS, and custom TCP/UDP entrypoints

## Prerequisites

- K3s cluster running
- cert-manager installed (for TLS certificates)
- MetalLB configured (for LoadBalancer IP assignment)
- `kubectl` access to the cluster
- Environment file configured in `../environments/`

## Directory Structure

```text
51-Traefik/
├── README.md
├── base/
│   ├── kustomization.yaml            # Base kustomization
│   ├── resources/
│   │   ├── namespace.yaml            # traefik-system namespace
│   │   ├── helmchart.yaml            # HelmChart for Traefik
│   │   ├── helmchartconfig.yaml      # HelmChart base configuration
│   │   ├── certificate-dashboard.yaml # Dashboard TLS certificate
│   │   ├── ingressroute-dashboard.yaml # Dashboard IngressRoute
│   │   ├── middleware.yaml           # Common middlewares
│   │   ├── middleware-tcp.yaml       # TCP middlewares
│   │   └── middleware-admin.yaml     # Admin middleware chain
│   ├── patches/
│   │   └── target-namespace.yaml     # Namespace patch for HelmChart
│   └── transformers/
│       ├── helmchart.yaml            # Transformer for HelmChart
│       └── helmchartconfig.yaml      # Transformer for HelmChartConfig
└── overlay/
    └── _SAMPLE/
        ├── kustomization.yaml        # Sample overlay configuration
        ├── generators/
        │   └── secret-dashboard-auth.yaml  # Basic auth secret generator
        ├── patches/
        │   ├── version.yaml          # Traefik version patch
        │   ├── certificate-dashboard.yaml  # Dashboard certificate config
        │   ├── ingressroute-dashboard.yaml # Dashboard route config
        │   ├── helmchartconfig.yaml  # Helm values patch
        │   └── namespace.yaml        # Namespace patch for secrets
        ├── resources/
        │   └── middleware-dashboard-auth.yaml  # Basic auth middleware
        └── secrets/
            └── secret-dashboard-auth.env  # Basic auth credentials
```

## Quick Start

### 1. Create Your Overlay

Copy the sample overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Dashboard Certificate

Edit `overlay/my-environment/patches/certificate-dashboard.yaml`:

```yaml
- op: replace
  path: /spec/subject/organizations
  value:
    - Your Organization
- op: replace
  path: /spec/dnsNames
  value:
    - traefik.yourdomain.com
```

### 3. Configure Dashboard IngressRoute

Edit `overlay/my-environment/patches/ingressroute-dashboard.yaml`:

```yaml
- op: replace
  path: /spec/routes/0/match
  value: "Host(`traefik.yourdomain.com`)"
```

### 4. Configure Helm Values

Edit `overlay/my-environment/patches/helmchartconfig.yaml` to set:

- Number of replicas
- LoadBalancer IP
- Entrypoints configuration
- Additional arguments

### 5. Configure Dashboard Authentication

For basic auth, edit `overlay/my-environment/secrets/secret-dashboard-auth.env`:

```env
username=admin
password=your-htpasswd-hash
```

Generate a password hash with:

```bash
htpasswd -nb admin your-password
```

**Note:** Add this file to `.gitignore` to prevent committing secrets.

### 6. Configure Version (Optional)

Edit `overlay/my-environment/patches/version.yaml`:

```yaml
- op: replace
  path: /spec/version
  value: v37.3.0
```

### 7. Deploy Traefik

```bash
# Preview the manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

### 8. Verify Installation

```bash
# Check Traefik pods
kubectl get pods -n traefik-system

# Check services
kubectl get svc -n traefik-system

# Check IngressRoutes
kubectl get ingressroutes -n traefik-system

# Check certificates
kubectl get certificates -n traefik-system
```

## Included Middlewares

### Security Middlewares

| Middleware | Description |
|------------|-------------|
| `forwarded-headers` | Adds X-Forwarded-Proto header |
| `security-headers` | HSTS, XSS protection, content-type nosniff |
| `rate-limit` | Request rate limiting |
| `ipallowlist-rfc1918` | Allow only RFC1918 private IPs |
| `compression` | Gzip compression |

### Middleware Chains

| Chain | Description |
|-------|-------------|
| `chain-admin` | Full admin chain with security headers and IP allowlist |

### TCP Middlewares

| Middleware | Description |
|------------|-------------|
| `ipallowlist-rfc1918` | TCP IP allowlist for private networks |

## Creating IngressRoutes

### Basic IngressRoute

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: my-app
  namespace: my-namespace
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`app.yourdomain.com`)
      kind: Rule
      services:
        - name: my-app
          port: 80
  tls:
    secretName: my-app-tls
```

### IngressRoute with Middlewares

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: my-app
  namespace: my-namespace
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`app.yourdomain.com`)
      kind: Rule
      middlewares:
        - name: chain-admin
          namespace: traefik-system
      services:
        - name: my-app
          port: 80
  tls:
    secretName: my-app-tls
```

## Configuration Reference

### HelmChartConfig Values

Key Helm values configured in the overlay:

| Value | Description |
|-------|-------------|
| `deployment.replicas` | Number of Traefik replicas |
| `ingressClass.isDefaultClass` | Set as default ingress class |
| `providers.kubernetesCRD.allowCrossNamespace` | Allow cross-namespace references |
| `ports.web.redirections` | HTTP to HTTPS redirect |
| `ports.websecure.tls.enabled` | Enable TLS on websecure port |
| `service.spec.loadBalancerIP` | Fixed LoadBalancer IP |

### Entrypoints

| Entrypoint | Port | Description |
|------------|------|-------------|
| `web` | 80 | HTTP (redirects to HTTPS) |
| `websecure` | 443 | HTTPS with TLS |
| `traefik` | 9000 | Traefik dashboard (internal) |

## Troubleshooting

### Check Traefik logs

```bash
kubectl logs -n traefik-system -l app.kubernetes.io/name=traefik
```

### Check IngressRoute status

```bash
# List all IngressRoutes
kubectl get ingressroutes -A

# Describe an IngressRoute
kubectl describe ingressroute my-app -n my-namespace
```

### Check certificate status

```bash
# List certificates
kubectl get certificates -n traefik-system

# Describe certificate
kubectl describe certificate traefik-dashboard -n traefik-system
```

### Common Issues

**Dashboard not accessible:**

- Verify certificate is issued and ready
- Check IngressRoute match rule is correct
- Ensure middleware secret exists
- Verify LoadBalancer has external IP

**502 Bad Gateway:**

- Check backend service is running
- Verify service port matches IngressRoute
- Check network policies allow traffic

**TLS certificate errors:**

- Verify cert-manager ClusterIssuer is ready
- Check certificate resource for errors
- Ensure DNS is correctly configured

**Middleware not applied:**

- Verify middleware exists in referenced namespace
- Check middleware name matches exactly
- Ensure `allowCrossNamespace: true` is set

## Related Resources

- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Traefik Helm Chart](https://github.com/traefik/traefik-helm-chart)
- [Traefik IngressRoute](https://doc.traefik.io/traefik/routing/providers/kubernetes-crd/)
- [Traefik Middlewares](https://doc.traefik.io/traefik/middlewares/overview/)
- [K3s HelmChart Controller](https://docs.k3s.io/helm)
