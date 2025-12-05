# Longhorn

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


This folder contains Kustomize manifests for deploying [Longhorn](https://longhorn.io/) to a K3s cluster using the HelmChart CRD. Longhorn is a lightweight, reliable, and highly available distributed block storage system for Kubernetes.

## Prerequisites

- K3s cluster with HelmChart CRD support
- cert-manager for TLS certificate management
- Traefik ingress controller for dashboard access
- Azure Blob Storage account for backup storage (optional but recommended)
- Authentik outpost for authentication (optional)

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
| `secret-azure-backup-store.env` | Azure Blob Storage credentials for backups |
| `secret-dashboard-auth.env` | Basic auth credentials for dashboard (if enabled) |

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
   - `secret-azure-backup-store.env`: Add Azure credentials for backup storage
   - `secret-dashboard-auth.env`: Set basic auth credentials (if using)

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

The Longhorn dashboard is accessible via Traefik IngressRoute at the configured hostname. Authentication is provided by:

- Authentik proxy outpost (recommended for SSO)
- Basic auth middleware (optional fallback)

## Backup Storage

This configuration uses Azure Blob Storage for backup storage. Configure the following in `secret-azure-backup-store.env`:

```env
AZURE_STORAGE_ACCOUNT=<storage-account-name>
AZURE_STORAGE_ACCESS_KEY=<access-key>
```

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

# Check Azure secret
kubectl -n longhorn-system get secret longhorn-backup-secret-azure
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
