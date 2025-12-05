# FortniteStats2Influx

> [!IMPORTANT]
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

This folder contains Kustomize manifests for deploying FortniteStats2Influx, a tool that collects Fortnite player statistics and stores them in InfluxDB for visualization in Grafana.

## Contents

The deployment is structured using Kustomize with a base/overlay pattern:

```text
FortniteStats2Influx/
├── base/
│   ├── kustomization.yaml
│   └── resources/
│       ├── cronjob.yaml              # Scheduled job for stats collection
│       ├── namespace.yaml            # Kubernetes namespace
│       └── resource-quota.yaml       # Namespace resource quotas
└── overlay/
    └── _SAMPLE/                      # Template overlay
        ├── kustomization.yaml
        ├── configs/
        │   └── player.txt            # List of player names to track
        ├── generators/               # Secret and config generators
        ├── patches/                  # Environment-specific patches
        ├── secrets/                  # Secret environment files
        └── transformers/             # Image and label transformers
```

## Features

- **Scheduled Collection**: CronJob-based periodic stats fetching
- **Multi-Player Tracking**: Track statistics for multiple players
- **InfluxDB Integration**: Stores data in time-series format for trending
- **Grafana Dashboards**: Visualize player statistics and progression

## Prerequisites

Before deploying, ensure you have:

- A Kubernetes cluster (e.g., K3s)
- [InfluxDB](../InfluxDB/) deployed and accessible
- Epic Games API access (API key required)

## Deployment

### 1. Create Your Overlay

Copy the `_SAMPLE` overlay to create your environment-specific configuration:

```bash
cp -r overlay/_SAMPLE overlay/my-environment
```

### 2. Configure Players

Edit the `configs/player.txt` file to list the players you want to track (one per line):

```text
PlayerName1
PlayerName2
PlayerName3
```

### 3. Configure Secrets

Edit the secret file in your overlay's `secrets/` directory:

**`secrets/secret-fortnitestats.env`** - API and InfluxDB credentials:

```dotenv
API_KEY=<your-epic-games-api-key>
INFLUXDB_URL=http://influxdb.influxdb.svc.cluster.local:8086
INFLUXDB_TOKEN=<your-influxdb-token>
INFLUXDB_ORG=<your-organization>
INFLUXDB_BUCKET=<your-bucket>
```

### 4. Configure Patches

Edit the patch files in your overlay's `patches/` directory:

| Patch File | Purpose |
|------------|---------|
| `resource-quota.yaml` | Namespace pod and PVC limits |

### 5. Deploy

Build and apply the manifests:

```bash
# Preview the generated manifests
kustomize build overlay/my-environment

# Apply to the cluster
kustomize build overlay/my-environment | kubectl apply -f -
```

## Configuration

### CronJob Schedule

The default schedule runs the stats collection periodically. To modify the schedule, edit the CronJob in the base or create a patch:

```yaml
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
```

### Resource Quota

The default configuration allows:

- 1 pod (for the CronJob execution)
- 0 persistent volume claims (no storage needed)

## Troubleshooting

### Check job status

```bash
kubectl get cronjobs -n fortnitestats2influx
kubectl get jobs -n fortnitestats2influx
```

### View job logs

```bash
kubectl logs -n fortnitestats2influx -l job-name=<job-name>
```

### Manually trigger a job

```bash
kubectl create job --from=cronjob/fortnitestats2influx manual-run -n fortnitestats2influx
```

### Check recent job history

```bash
kubectl get jobs -n fortnitestats2influx --sort-by=.metadata.creationTimestamp
```

## Related Resources

- [InfluxDB Documentation](https://docs.influxdata.com/influxdb/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Kubernetes CronJob Documentation](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kustomize Documentation](https://kustomize.io/)
