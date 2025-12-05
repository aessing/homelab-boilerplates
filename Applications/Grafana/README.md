# Grafana

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Grafana](https://grafana.com/), the open-source platform for monitoring and observability.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Grafana/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       └── resource-quota.yaml       # Namespace resource quotas
├── components/
│   ├── _application/                 # Grafana server deployment
│   │   └── resources/
│   │       ├── certificate.yaml      # TLS certificate
│   │       ├── deployment.yaml       # Grafana deployment
│   │       ├── ingressroute.yaml     # Traefik ingress route
│   │       └── service.yaml          # Kubernetes service
│   ├── _database/                    # PostgreSQL database (CNPG)
│   │   └── resources/
│   │       ├── cluster.yaml          # CNPG cluster definition
│   │       ├── objectstore.yaml      # Backup object storage
│   │       └── scheduledbackup.yaml  # Backup schedule
│   ├── _haengine/                    # Home Assistant engine integration
│   └── _renderer/                    # Image renderer for alerts
│       └── configs/
│           └── config.json           # Renderer configuration
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **Dashboards**: Visualize metrics from multiple data sources
- **Alerting**: Configure alerts with multiple notification channels
- **PostgreSQL Backend**: Highly available database via CloudNativePG
- **Image Renderer**: Server-side rendering for alert notifications
- **Home Assistant Integration**: Custom engine for HA dashboards
- **Automated Backups**: Scheduled database backups to S3
- **TLS Encryption**: Secure connections via cert-manager

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [CloudNativePG Operator](https://cloudnative-pg.io/documentation/current/installation_upgrade/) installed
- [cert-manager](https://cert-manager.io/) installed and configured
- [Traefik](https://traefik.io/) ingress controller
- S3-compatible object storage for backups (optional but recommended)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-grafana-admin.env`** - Admin credentials:

```dotenv
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=<your-secure-password>
```

**`secrets/secret-grafana-database-user.env`** - Database credentials:

```dotenv
username=grafana
password=<your-secure-password>
```

**`secrets/secret-grafana-database-objectstore.env`** - S3 backup credentials:

```dotenv
ACCESS_KEY_ID=<your-access-key-id>
ACCESS_KEY_NAME=<your-access-key-name>
ACCESS_SECRET_KEY=<your-secret-key>
```

**`secrets/secret-grafana-secretkey.env`** - Grafana secret key:

```dotenv
GF_SECURITY_SECRET_KEY=<your-secret-key>
```

**`secrets/secret-grafana-smtp.env`** - SMTP configuration:

```dotenv
GF_SMTP_ENABLED=true
GF_SMTP_HOST=<smtp-host>:<smtp-port>
GF_SMTP_USER=<smtp-username>
GF_SMTP_PASSWORD=<smtp-password>
GF_SMTP_FROM_ADDRESS=grafana@example.com
```

**`secrets/secret-grafana-renderer-auth.env`** - Renderer authentication:

```dotenv
GF_RENDERING_SERVER_URL=http://grafana-renderer:8081/render
GF_RENDERING_CALLBACK_URL=http://grafana:3000/
```

**`secrets/secret-grafana-metrics.env`** - Metrics endpoint credentials:

```dotenv
GF_METRICS_BASIC_AUTH_USERNAME=metrics
GF_METRICS_BASIC_AUTH_PASSWORD=<your-secure-password>
```

**`secrets/secret-grafana-haengine-auth.env`** - HA Engine authentication:

```dotenv
HA_ENGINE_TOKEN=<your-ha-token>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `env-grafana.yaml` | Environment variables for Grafana |
| `grafana-database.yaml` | Database instance count, PostgreSQL version, storage |
| `grafana-database-objectstore.yaml` | S3 bucket and endpoint for backups |
| `grafana-database-schedule.yaml` | Backup schedule (cron format) |
| `ingressroute.yaml` | External hostname for web access |
| `network-policy.yaml` | Client IP ranges for access |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 4. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply --server-side -f -
```

## Components

This application uses modular components:

| Component | Description |
|-----------|-------------|
| `_application` | Grafana server deployment |
| `_database` | PostgreSQL database via CloudNativePG |
| `_haengine` | Home Assistant custom engine |
| `_renderer` | Image renderer for alert notifications |

Enable components in your overlay's `kustomization.yaml`:

```yaml
components:
  - ../../components/_database
  - ../../components/_application
  - ../../components/_renderer
  # - ../../components/_haengine  # Optional
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |
| `###INSTANCE_COUNT(3)###` | `grafana-database.yaml` | Number of database instances |
| `###PGSQL_VERSION###` | `grafana-database.yaml` | PostgreSQL version (16, 17, 18) |
| `###PVC_SIZE###` | `grafana-database.yaml` | Database storage size |
| `###CLUSTER_CIDR###` | `network-policy.yaml` | Allowed client CIDR |

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n grafana
kubectl get deployment grafana -n grafana
```

### View application logs

```bash
kubectl logs -n grafana -l app.kubernetes.io/name=grafana
```

### Check database status

```bash
kubectl get cluster -n grafana
kubectl cnpg status grafana-database -n grafana
```

### Check renderer status

```bash
kubectl logs -n grafana -l app.kubernetes.io/name=grafana-renderer
```

### Reset admin password

```bash
kubectl exec -it -n grafana deployment/grafana -- grafana-cli admin reset-admin-password <new-password>
```

## Related Resources

- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/)
- [Kustomize Documentation](https://kustomize.io/)
