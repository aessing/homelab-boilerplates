# Authentik

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Authentik](https://goauthentik.io/), an open-source Identity Provider focused on flexibility and versatility.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
Authentik/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       └── namespace.yaml            # Kubernetes namespace
├── components/
│   ├── _application/                 # Authentik application (HelmChart)
│   │   ├── resources/
│   │   │   ├── certificate.yaml      # TLS certificate
│   │   │   ├── helmchart.yaml        # K3s HelmChart resource
│   │   │   ├── helmchartconfig.yaml  # Helm values configuration
│   │   │   └── ingressroute.yaml     # Traefik ingress route
│   │   └── patches/
│   │       └── target-namespace.yaml # Namespace targeting
│   └── _database/                    # PostgreSQL database (CNPG)
│       └── resources/
│           ├── cluster.yaml          # CNPG cluster definition
│           ├── objectstore.yaml      # Backup object storage
│           └── scheduledbackup.yaml  # Backup schedule
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── generators/               # Secret generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Label transformers
```

## Features

- **Single Sign-On (SSO)**: SAML, OAuth2/OpenID Connect, LDAP support
- **Multi-Factor Authentication**: TOTP, WebAuthn, SMS, Email
- **User Management**: Self-service enrollment, password reset, profile management
- **Application Proxy**: Secure access to applications without native SSO support
- **PostgreSQL Backend**: Highly available database via CloudNativePG
- **Automated Backups**: Scheduled backups to S3-compatible storage
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

**`secrets/secret-authentik-config.env`** - Authentik configuration:

```dotenv
AUTHENTIK_POSTGRESQL__HOST=authentik-database-rw
AUTHENTIK_POSTGRESQL__READ_REPLICAS__0__HOST=authentik-database-ro
AUTHENTIK_SECRET_KEY=<your-secret-key>
AUTHENTIK_LOG_LEVEL=info
AUTHENTIK_EMAIL__HOST=<smtp-host>
AUTHENTIK_EMAIL__PORT=<smtp-port>
AUTHENTIK_EMAIL__USERNAME=<smtp-username>
AUTHENTIK_EMAIL__PASSWORD=<smtp-password>
AUTHENTIK_EMAIL__USE_TLS=false
AUTHENTIK_EMAIL__USE_SSL=true
AUTHENTIK_EMAIL__TIMEOUT=30
AUTHENTIK_EMAIL__FROM=Authentik <authentik@example.com>
```

**`secrets/secret-authentik-database-user.env`** - Database credentials:

```dotenv
username=authentik
password=<your-secure-password>
```

**`secrets/secret-authentik-database-objectstore.env`** - S3 backup credentials:

```dotenv
ACCESS_KEY_ID=<your-access-key-id>
ACCESS_KEY_NAME=<your-access-key-name>
ACCESS_SECRET_KEY=<your-secret-key>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `authentik-database.yaml` | Database instance count, PostgreSQL version, storage |
| `authentik-database-objectstore.yaml` | S3 bucket and endpoint for backups |
| `authentik-database-schedule.yaml` | Backup schedule (cron format) |
| `certificate.yaml` | TLS certificate DNS names and organization |
| `helmchartconfig.yaml` | Helm values (replicas, resources, etc.) |
| `ingressroute.yaml` | External hostname for web access |
| `version.yaml` | Authentik version to deploy |

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
| `###SECRET_KEY###` | `secret-authentik-config.env` | Authentik secret key (generate with `openssl rand -hex 32`) |
| `###SMTP_HOST###` | `secret-authentik-config.env` | SMTP server hostname |
| `###NAME_OF_ORGANISATION###` | `certificate.yaml` | Organization name for TLS cert |
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |

### HelmChartConfig

The `helmchartconfig.yaml` patch allows customization of the Authentik Helm chart values. Common settings include:

- Replica count for server and worker
- Resource requests and limits
- Redis configuration
- Additional environment variables

## Components

This application uses modular components:

| Component | Description |
|-----------|-------------|
| `_application` | Authentik server and worker via HelmChart |
| `_database` | PostgreSQL database via CloudNativePG |

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n authentik
kubectl get helmchart -n kube-system authentik
```

### View application logs

```bash
kubectl logs -n authentik -l app.kubernetes.io/name=authentik-server
kubectl logs -n authentik -l app.kubernetes.io/name=authentik-worker
```

### Check database status

```bash
kubectl get cluster -n authentik
kubectl cnpg status authentik-database -n authentik
```

### Access Authentik

After deployment, access Authentik at your configured domain. The initial setup wizard will guide you through creating the first admin user.

## Related Resources

- [Authentik Documentation](https://docs.goauthentik.io/)
- [Authentik Helm Chart](https://github.com/goauthentik/helm)
- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/)
- [Kustomize Documentation](https://kustomize.io/)
