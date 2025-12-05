# CloudNativePG Operator

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying the [CloudNativePG (CNPG)](https://cloudnative-pg.io/) operator and its Barman Cloud backup plugin on Kubernetes.

## Contents

The deployment is structured using Kustomize with a components/overlay pattern:

```text
CloudNativePG/
├── components/
│   ├── _barman/                    # Barman Cloud backup plugin component
│   │   ├── kustomization.yaml
│   │   └── resources/
│   │       └── barman-objectstore.yaml
│   └── _cnpg/                      # CNPG operator component
│       ├── kustomization.yaml
│       └── resources/
│           └── cnpg-controller-manager-config.yaml
└── overlay/
    └── _SAMPLE/                    # Template overlay for deployments
        ├── kustomization.yaml
        ├── generators/             # Secret generators
        ├── patches/                # Environment-specific patches
        └── secrets/                # Secret environment files
```

## Features

- **CloudNativePG Operator**: Manages PostgreSQL clusters on Kubernetes
- **Barman Cloud Plugin**: Provides backup and restore capabilities to S3-compatible storage
- **Image Catalogs**: Includes PostgreSQL image catalogs for different versions
- **High Availability**: Supports running multiple operator replicas
- **Configurable**: Environment-specific settings via Kustomize overlays

## Components

### CNPG Operator (`_cnpg`)

Deploys the CloudNativePG operator with:

- CNPG controller manager (from official release)
- Controller manager configuration secret
- PostgreSQL image catalogs:
  - `catalog-minimal-trixie` - Minimal PostgreSQL images
  - `catalog-standard-trixie` - Standard PostgreSQL images
  - `postgis-standard-trixie` - PostGIS-enabled images

### Barman Cloud Plugin (`_barman`)

Deploys the Barman Cloud backup plugin with:

- Barman Cloud plugin (from official release)
- Default ObjectStore configuration for S3-compatible backup storage

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- `kubectl` configured to access your cluster
- `kustomize` installed (or use `kubectl kustomize`)
- S3-compatible object storage for backups (e.g., Backblaze B2, MinIO, AWS S3)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-cluster
```

### 2. Configure Secrets

Edit the secret file in your overlay's `secrets/` directory:

**`secrets/barman-objectstore-default-credentials.env`** - S3 backup storage credentials:

```dotenv
ACCESS_KEY_ID=<your-access-key-id>
ACCESS_KEY_NAME=<your-access-key-name>
ACCESS_SECRET_KEY=<your-secret-key>
```

### 3. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `cnpg-controller-manager.yaml` | Operator replica count |
| `cnpg-controller-manager-config.yaml` | Operator configuration settings |
| `barman-objectstore.yaml` | Default S3 bucket and endpoint configuration |

#### ObjectStore Configuration

Update `patches/barman-objectstore.yaml` with your S3 settings:

```yaml
apiVersion: barmancloud.cnpg.io/v1
kind: ObjectStore
metadata:
  name: barman-objectstore-default
spec:
  configuration:
    destinationPath: s3://<bucket-name>/<folder>/
    endpointURL: https://<s3-endpoint-url>
```

### 4. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-cluster

# Apply to the cluster
kustomize build overlay/my-cluster | kubectl apply --server-side -f -
```

## The _SAMPLE Overlay Explained

The `_SAMPLE` overlay demonstrates how to configure the CNPG operator for your environment.

### Directory Structure

```text
_SAMPLE/
├── kustomization.yaml                              # Main kustomization file
├── generators/
│   └── barman-objectstore-default-credentials.yaml # Secret generator for S3 credentials
├── patches/
│   ├── barman-objectstore.yaml                     # S3 bucket/endpoint configuration
│   ├── cnpg-controller-manager.yaml                # Operator replica count
│   └── cnpg-controller-manager-config.yaml         # Operator settings
└── secrets/
    └── barman-objectstore-default-credentials.env  # S3 credentials
```

### Key Configuration Values

Replace these placeholders in the patch files:

| Placeholder | File | Description |
|-------------|------|-------------|
| `###BUCKET###` | `barman-objectstore.yaml` | S3 bucket name |
| `###FOLDER(CLUSTERNAME)###` | `barman-objectstore.yaml` | Folder path in bucket |
| `###ENDPOINT_URL###` | `barman-objectstore.yaml` | S3 endpoint URL |
| `###ACCESS_KEY_ID###` | `barman-objectstore-default-credentials.env` | S3 access key ID |
| `###ACCESS_KEY_NAME###` | `barman-objectstore-default-credentials.env` | S3 access key name |
| `###ACCESS_SECRET_KEY###` | `barman-objectstore-default-credentials.env` | S3 secret access key |

## Operator Configuration

The CNPG controller manager can be configured via the `cnpg-controller-manager-config` secret:

| Setting | Default | Description |
|---------|---------|-------------|
| `CERTIFICATE_DURATION` | `90` | Days until certificates expire |
| `CLUSTERS_ROLLOUT_DELAY` | `0` | Delay between cluster rollouts (seconds) |
| `CREATE_ANY_SERVICE` | `false` | Allow creating services of any type |
| `ENABLE_INSTANCE_MANAGER_INPLACE_UPDATES` | `false` | Enable in-place instance updates |
| `EXPIRING_CHECK_THRESHOLD` | `7` | Days before expiry to trigger renewal |
| `INSTANCES_ROLLOUT_DELAY` | `0` | Delay between instance rollouts (seconds) |
| `KUBERNETES_CLUSTER_DOMAIN` | `cluster.local` | Kubernetes cluster domain |
| `STANDBY_TCP_USER_TIMEOUT` | `0` | TCP timeout for standby connections |

## Troubleshooting

### Check Operator Status

```bash
kubectl get deployment -n cnpg-system cnpg-controller-manager
kubectl get pods -n cnpg-system
```

### View Operator Logs

```bash
kubectl logs -n cnpg-system -l app.kubernetes.io/name=cloudnative-pg
```

### Check Barman Plugin Status

```bash
kubectl get deployment -n cnpg-system barman-cloud
kubectl get objectstore -n cnpg-system
```

### Verify Image Catalogs

```bash
kubectl get clusterimagecatalog
```

## Updating the Operator

To update CNPG to a new version:

1. Update the release URL in `components/_cnpg/kustomization.yaml`
2. Update the Barman plugin URL in `components/_barman/kustomization.yaml` if needed
3. Rebuild and apply:

```bash
kustomize build overlay/my-cluster | kubectl apply --server-side -f -
```

## Related Resources

- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/)
- [CloudNativePG GitHub](https://github.com/cloudnative-pg/cloudnative-pg)
- [Barman Cloud Plugin](https://github.com/cloudnative-pg/plugin-barman-cloud)
- [kubectl-cnpg Plugin](https://cloudnative-pg.io/documentation/current/kubectl-plugin/)
- [PostgreSQL Cluster Deployment](../../Applications/PostgreSQL/README.md)
