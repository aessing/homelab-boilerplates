# Longhorn

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [Longhorn](https://longhorn.io/) to a K3s cluster using the HelmChart CRD. Longhorn is a lightweight, reliable, and highly available distributed block storage system for Kubernetes.

## Prerequisites

- K3s cluster with HelmChart CRD support
- cert-manager for TLS certificate management
- Traefik ingress controller for dashboard access
- S3-compatible object storage (e.g. Backblaze B2) for backup storage (recommended)
- Authentik outpost for dashboard authentication (recommended)

> [!NOTE]
> The `_SAMPLE` overlay reflects the deployed reality: **S3-compatible backups (Backblaze B2)** and **Authentik SSO** for the dashboard. Azure Blob Storage backups and Traefik Basic Auth are still supported — see [Alternatives](#alternatives).

### Install Requirements

Before deploying Longhorn, run the requirements installation script on **all nodes**:

```bash
sudo ./11-install-requirements.sh
```

This script:

- Installs required packages (`jq`, `open-iscsi`, `nfs-common`)
- Enables the iSCSI daemon
- Configures multipath blacklisting for local disks
- Creates a patch to set local-path StorageClass as non-default

## Structure

```text
61-Longhorn/
├── 11-install-requirements.sh    # Node preparation script
├── base/
│   ├── kustomization.yaml
│   ├── patches/
│   │   └── target-namespace.yaml # Sets target namespace for Helm deployment
│   ├── resources/
│   │   ├── namespace.yaml
│   │   ├── helmchart.yaml
│   │   ├── helmchartconfig.yaml
│   │   ├── certificate-dashboard.yaml
│   │   ├── middleware-dashboard.yaml
│   │   ├── ingressroute-dashboard.yaml
│   │   ├── storageclass.yaml
│   │   └── jobs.yaml             # RecurringJob definitions
│   └── transformers/
│       ├── helmchart.yaml
│       └── helmchartconfig.yaml
└── overlay/
    ├── _SAMPLE/                  # Template overlay
    └── <cluster>/                # Environment-specific overlays
```

## Overlay Configuration

Each overlay customizes:

### Patches

| Patch | Description |
|-------|-------------|
| `version.yaml` | Longhorn Helm chart version |
| `certificate-dashboard.yaml` | TLS certificate configuration |
| `ingressroute-dashboard.yaml` | Traefik IngressRoute for dashboard |
| `helmchartconfig.yaml` | Helm values configuration |
| `namespace.yaml` | Namespace for generated secrets |
| `storageclass.yaml` | Number of storage replicas |

### RecurringJob Patches

| Patch | Description |
|-------|-------------|
| `jobs-longhorn-job-backup.yaml` | Volume backup schedule and retention |
| `jobs-longhorn-job-snapshot.yaml` | Volume snapshot schedule and retention |
| `jobs-longhorn-job-snapshot-cleanup.yaml` | Snapshot cleanup schedule |
| `jobs-longhorn-job-system-backup.yaml` | System backup schedule and retention |
| `jobs-longhorn-job-trim-daily.yaml` | Daily filesystem trim schedule |
| `jobs-longhorn-job-trim-weekly.yaml` | Weekly filesystem trim schedule |

### Secrets

| Secret | Description |
|--------|-------------|
| `secret-backblaze-backup-store.env` | S3-compatible (Backblaze B2) credentials for backups |

## Usage

1. Copy the `_SAMPLE` overlay to create an environment-specific configuration:

   ```bash
   cp -r overlay/_SAMPLE overlay/<cluster-name>
   ```

2. Update the patches with environment-specific values:
   - `version.yaml`: Set desired Longhorn version
   - `certificate-dashboard.yaml`: Configure certificate DNS names and organization
   - `ingressroute-dashboard.yaml`: Set dashboard hostname
   - `storageclass.yaml`: Set number of replicas based on cluster size
   - Job patches: Configure backup and maintenance schedules

3. Configure secrets:
   - `secret-backblaze-backup-store.env`: Add S3-compatible (Backblaze B2) credentials for backup storage
   - `ingressroute-dashboard.yaml`: Replace `###ENVIRONMENT###` with the Authentik outpost name and `###FQDN_FOR_LONGHORN_DASHBOARD###` with the dashboard hostname

4. Deploy with Kustomize:

   ```bash
   kustomize build overlay/<cluster-name> | kubectl apply --server-side -f -
   ```

## RecurringJobs Overview

Longhorn uses RecurringJobs to automate volume maintenance:

| Job | Task | Purpose |
|-----|------|---------|
| `longhorn-job-backup` | backup | Automated volume backups to external storage |
| `longhorn-job-snapshot` | snapshot | Local volume snapshots for quick recovery |
| `longhorn-job-snapshot-cleanup` | snapshot-cleanup | Remove old snapshots to free space |
| `longhorn-job-system-backup` | system-backup | Backup Longhorn system configuration |
| `longhorn-job-trim-daily` | filesystem-trim | Daily TRIM to reclaim unused space |
| `longhorn-job-trim-weekly` | filesystem-trim | Weekly TRIM for volumes not in daily group |

## Dashboard Access

The Longhorn dashboard is accessible via Traefik IngressRoute at the configured hostname. By default it is protected by an **Authentik proxy outpost** (SSO): the `ingressroute-dashboard.yaml` patch routes the `/outpost.goauthentik.io/` callback to the outpost service and applies the `authentik-outpost-<environment>-proxy-outpost` forward-auth middleware (together with `chain-admin`). To use Traefik Basic Auth instead, see [Alternatives](#alternatives).

## Backup Storage

By default this configuration backs up to **S3-compatible object storage (Backblaze B2)**. Configure the following in `secret-backblaze-backup-store.env`:

```env
AWS_ACCESS_KEY_ID=<key-id>
AWS_ACCESS_KEY_NAME=<key-name>
AWS_SECRET_ACCESS_KEY=<secret-key>
AWS_ENDPOINTS=https://s3.<region>.backblazeb2.com
AWS_REGION=<region>
AWS_PATH_STYLE='true'
```

The backup target itself is set in `helmchartconfig.yaml` (`defaultBackupStore.backupTarget`), e.g. `s3://<bucket>@<region>/<environment>`. To use Azure Blob Storage instead, see [Alternatives](#alternatives).

## Alternatives

The `_SAMPLE` overlay ships the S3/Backblaze + Authentik setup. The two original options are still fully supported — switch back as follows.

### Azure Blob Storage backups (instead of S3/Backblaze)

1. Create `generators/secret-azure-backup-store.yaml`:

   ```yaml
   ---
   apiVersion: builtin
   kind: SecretGenerator
   metadata:
     name: longhorn-backup-secret-azure
   behavior: create
   options:
     disableNameSuffixHash: true
     labels:
       kustomize-base: overlay
   envs:
     - ./secrets/secret-azure-backup-store.env
   ```

2. Create `secrets/secret-azure-backup-store.env`:

   ```env
   AZBLOB_ACCOUNT_NAME=<storage-account-name>
   AZBLOB_ACCOUNT_KEY=<account-shared-access-token>
   ```

3. In `kustomization.yaml`, swap the backup generator and its namespace patch target from `…-backblaze` to:

   ```yaml
   generators:
     - ./generators/secret-azure-backup-store.yaml
   # …
     - path: ./patches/namespace.yaml
       target:
         name: longhorn-backup-secret-azure
   ```

4. In `patches/helmchartconfig.yaml`, point the backup store at Azure:

   ```yaml
   defaultBackupStore:
     backupTarget: 'azblob://<container>@core.windows.net/'
     backupTargetCredentialSecret: 'longhorn-backup-secret-azure'
   ```

### Traefik Basic Auth dashboard (instead of Authentik SSO)

1. Create `resources/middleware-dashboard-auth.yaml`:

   ```yaml
   ---
   apiVersion: traefik.io/v1alpha1
   kind: Middleware
   metadata:
     name: longhorn-dashboard-basicauth
   spec:
     basicAuth:
       secret: longhorn-dashboard-basicauth
       removeHeader: true
   ```

2. Create `generators/secret-dashboard-auth.yaml` (a `SecretGenerator` named `longhorn-dashboard-basicauth`) and `secrets/secret-dashboard-auth.env`:

   ```env
   username=<username>
   password=<htpasswd-or-token>
   ```

3. In `kustomization.yaml`, add the middleware resource, the secret generator, and a `namespace.yaml` patch targeting `longhorn-dashboard-basicauth`.

4. Replace `patches/ingressroute-dashboard.yaml` with a route that uses the `chain-admin` and `longhorn-dashboard-basicauth` middlewares instead of the Authentik outpost (see the base `ingressroute-dashboard.yaml` for the basic-auth shape).

## Useful Commands

### Check Longhorn Status

```bash
kubectl -n longhorn-system get pods
kubectl -n longhorn-system get volumes
```

### List RecurringJobs

```bash
kubectl -n longhorn-system get recurringjobs
```

### Check Backup Status

```bash
kubectl -n longhorn-system get backups
kubectl -n longhorn-system get systembackups
```

### Access Longhorn UI

```bash
kubectl -n longhorn-system port-forward svc/longhorn-frontend 8080:80
```

## Troubleshooting

### Volume Mounting Issues

```bash
# Check if iSCSI is running on all nodes
systemctl status iscsid

# Check Longhorn manager logs
kubectl -n longhorn-system logs -l app=longhorn-manager
```

### Backup Failures

```bash
# Check backup target status
kubectl -n longhorn-system get settings backup-target

# Check backup credential secret
kubectl -n longhorn-system get secret longhorn-backup-secret-backblaze
```

### Node Preparation

```bash
# Re-run requirements on affected node
sudo ./11-install-requirements.sh

# Check Longhorn environment
curl -sSfL https://raw.githubusercontent.com/longhorn/longhorn/v1.10.1/scripts/environment_check.sh | bash
```

## References

- [Longhorn Documentation](https://longhorn.io/docs/)
- [Longhorn GitHub Repository](https://github.com/longhorn/longhorn)
- [RecurringJobs Documentation](https://longhorn.io/docs/latest/snapshots-and-backups/scheduling-backups-and-snapshots/)
- [Backup Target Configuration](https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/)
