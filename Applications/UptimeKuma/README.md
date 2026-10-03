# Uptime Kuma

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Uptime Kuma](https://uptime.kuma.pet/), a self-hosted monitoring tool.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
UptimeKuma/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       └── resource-quota.yaml       # Namespace resource quotas
├── components/
│   ├── _application/                 # Uptime Kuma application
│   │   └── resources/
│   │       ├── certificate.yaml      # TLS certificate
│   │       ├── ingressroute.yaml     # Traefik ingress route
│   │       ├── service.yaml          # Kubernetes service
│   │       └── statefulset.yaml      # Uptime Kuma StatefulSet
│   └── _database/                    # MariaDB database
│       └── resources/
│           ├── service.yaml          # Database service
│           └── statefulset.yaml      # MariaDB StatefulSet
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **Uptime Monitoring**: HTTP(S), TCP, DNS, and more
- **Status Pages**: Public status pages for services
- **Notifications**: Discord, Slack, Telegram, Email, and many more
- **MariaDB Backend**: Persistent database for monitoring data
- **TLS Encryption**: Secure connections via cert-manager
- **Multi-Monitor**: Support for many concurrent monitors

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

### 2. Configure Secrets

Edit the secret files in your overlay's `secrets/` directory:

**`secrets/secret-uptimekuma-database-root.env`** - MariaDB root credentials:

```dotenv
MARIADB_ROOT_PASSWORD=<your-secure-password>
```

**`secrets/secret-uptimekuma-database-user.env`** - Application database credentials:

```dotenv
MARIADB_USER=uptimekuma
MARIADB_PASSWORD=<your-secure-password>
MARIADB_DATABASE=uptimekuma
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `certificate.yaml` | TLS certificate DNS names and organization |
| `ingressroute.yaml` | External hostname for web access |
| `pvc-application.yaml` | Uptime Kuma storage size |
| `pvc-database.yaml` | MariaDB storage size |
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
| `_application` | Uptime Kuma web application |
| `_database` | MariaDB database |

Enable components in your overlay's `kustomization.yaml`:

```yaml
components:
  - ../../components/_database
  - ../../components/_application
```

## Configuration

### Key Placeholder Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |

### Monitor Types

Uptime Kuma supports various monitor types:

| Type | Description |
|------|-------------|
| **HTTP(S)** | Web endpoint monitoring |
| **TCP Port** | Port availability checks |
| **DNS** | DNS record validation |
| **Ping** | ICMP ping checks |
| **Docker** | Container health monitoring |
| **Push** | Heartbeat-based monitoring |
| **Steam Game Server** | Game server monitoring |
| **MQTT** | MQTT broker checks |

### Notification Channels

Configure notifications in the web interface:

- Discord, Slack, Telegram
- Email (SMTP)
- Pushover, Gotify
- Webhooks
- And many more...

## MariaDB Major Upgrades

The current target is MariaDB 13.0.2 with Uptime Kuma 2.5.5. Before upgrading an existing 12.3.3 database:

1. Stop Uptime Kuma during the maintenance window. Create a consistent logical database dump including routines, events and triggers. Preserve the application data directory, database credentials, user grants and the previous manifests separately.
2. Restore the dump into a separate database and verify the application can log in, read monitoring history and write data. Keep the production data directory intact during this test.
3. Upgrade the existing database through the StatefulSet. `MARIADB_AUTO_UPGRADE=1` lets the official image migrate required system tables. Its automatic system-table backup is not a complete application backup. The startup probe allows about ten minutes for initialization and migration, adjust this budget before rollout if a representative test needs longer.
4. Wait for the database to become ready, then restart Uptime Kuma and verify login, monitors, history, status pages and new writes. Check database and application logs from the upgrade start. If recovery is needed, restore the complete pre-upgrade backup into a separate data directory using the previous MariaDB version. Reverting only the image tag is not a verified rollback after a major migration.

An isolated ARM64 test on 2026-10-03 verified the 12.3.3 → 13.0.2 upgrade with the official image, UID/GID 999 and Uptime Kuma 2.5.5. It covered schema initialization, login, monitor writes and restoring the pre-upgrade logical dump back into a fresh 12.3.3 database. This test used a small synthetic dataset. It does not replace a backup and restore test of the actual installation.

See the [MariaDB 13.0.2 release notes](https://mariadb.com/docs/release-notes/community-server/13.0/13.0.2) and the [official image upgrade behavior](https://hub.docker.com/_/mariadb).

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n uptimekuma
kubectl get statefulset -n uptimekuma
```

### View application logs

```bash
kubectl logs -n uptimekuma -l app.kubernetes.io/name=uptimekuma
```

### View database logs

```bash
kubectl logs -n uptimekuma -l app.kubernetes.io/name=mariadb
```

### Check persistent volumes

```bash
kubectl get pvc -n uptimekuma
```

### Database connection

```bash
kubectl exec -it -n uptimekuma uptimekuma-database-0 -- mariadb -u uptimekuma -p
```

### Reset admin password

Access the container and use the built-in reset functionality:

```bash
kubectl exec -it -n uptimekuma uptimekuma-0 -- /bin/sh
```

## Related Resources

- [Uptime Kuma Documentation](https://github.com/louislam/uptime-kuma/wiki)
- [Uptime Kuma GitHub](https://github.com/louislam/uptime-kuma)
- [MariaDB Documentation](https://mariadb.com/kb/en/documentation/)
- [Kustomize Documentation](https://kustomize.io/)
