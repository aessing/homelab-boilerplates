# InfluxDB

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying [InfluxDB](https://www.influxdata.com/products/influxdb/), a high-performance time-series database.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
InfluxDB/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── certificate.yaml          # TLS certificate
│       ├── ingressroute.yaml         # Traefik ingress route
│       ├── namespace.yaml            # Kubernetes namespace
│       ├── network-policy.yaml       # Network security policies
│       ├── resource-quota.yaml       # Namespace resource quotas
│       ├── service.yaml              # Kubernetes service
│       └── statefulset.yaml          # InfluxDB StatefulSet
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── patches/                  # Environment-specific patches
        └── transformers/             # Image and label transformers
```

## Features

- **Time-Series Database**: Optimized for high-write and query workloads
- **Persistent Storage**: Data stored on persistent volumes
- **TLS Encryption**: Secure connections via cert-manager
- **Traefik Integration**: Web UI access via ingress

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
| `pvc-application.yaml` | Storage sizes for config and data volumes |
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 3. Deploy

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
| `###FQDN_OF_APPLICATION###` | `certificate.yaml`, `ingressroute.yaml` | External domain name |

### Storage Configuration

The `pvc-application.yaml` patch controls storage sizes:

```yaml
# Config Volume
- op: replace
  path: /spec/volumeClaimTemplates/0/spec/resources/requests/storage
  value: "1Gi"

# Data Volume
- op: replace
  path: /spec/volumeClaimTemplates/1/spec/resources/requests/storage
  value: "50Gi"
```

### Initial Setup

After deployment, access the InfluxDB web UI to complete initial setup:

1. Navigate to your configured domain
2. Create initial user and organization
3. Create buckets for your data
4. Generate API tokens for applications

## Data Sources

InfluxDB is commonly used with:

- **Telegraf**: Metrics collection agent
- **Grafana**: Visualization dashboards
- **Home Assistant**: Home automation metrics
- **FortniteStats2Influx**: Gaming statistics

## Troubleshooting

### Check deployment status

```bash
kubectl get pods -n influxdb
kubectl get statefulset influxdb -n influxdb
```

### View application logs

```bash
kubectl logs -n influxdb -l app.kubernetes.io/name=influxdb
```

### Check persistent volumes

```bash
kubectl get pvc -n influxdb
```

### Access InfluxDB CLI

```bash
kubectl exec -it -n influxdb influxdb-0 -- influx
```

### Check database health

```bash
kubectl exec -it -n influxdb influxdb-0 -- influx ping
```

### Backup data

```bash
kubectl exec -it -n influxdb influxdb-0 -- influx backup /tmp/backup
kubectl cp influxdb/influxdb-0:/tmp/backup ./influxdb-backup
```

## Related Resources

- [InfluxDB Documentation](https://docs.influxdata.com/influxdb/)
- [InfluxDB API Reference](https://docs.influxdata.com/influxdb/v2/api/)
- [Telegraf Documentation](https://docs.influxdata.com/telegraf/)
- [Grafana InfluxDB Data Source](https://grafana.com/docs/grafana/latest/datasources/influxdb/)
- [Kustomize Documentation](https://kustomize.io/)
