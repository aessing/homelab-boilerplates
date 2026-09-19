# MonitoringGrafana

Grafana OSS dashboards for Kubernetes, hosts, infrastructure controllers,
storage, PostgreSQL, applications and the metrics pipeline. This package is loaded by the
existing [Grafana application](../Grafana/README.md).

The dashboard JSON is generated from deterministic Python definitions, then
validated and provisioned through the existing Grafana deployment.

## Design and location

- Repository: `Applications/MonitoringGrafana/components/_dashboards/`.
- Grafana UI: `Dashboards > Monitoring Metrics`, folder UID `monitoring-infrastructure`.
- Datasource: **Monitoring Metrics**, using the stable Prometheus-compatible
  `monitoring-metrics` UID.
- Visuals: stable multi-series colors for readable charts, blue
  quantitative accents, clear independent status colors, and compact dashboard
  headers without a Grafana logo.
- Navigation: a tag-based Monitoring dropdown plus context-preserving table
  drill-downs for cluster, namespace, Pod, node, PVC, job and database scope.
- Edition: Grafana OSS. No Enterprise license or external panel plugin required.

The package does not deploy another Grafana instance. Provisioning creates the
Monitoring Metrics folder and assigns eleven infrastructure dashboards to it. Dashboards never
need to be imported individually into the root dashboard list.

Eleven dashboards are also provisioned into **Monitoring Applications** (UID
`monitoring-applications`). They use the existing Monitoring Metrics and
Monitoring Logs datasources, with no new collectors or Grafana plugins:

| Dashboard | Purpose |
| --- | --- |
| Applications Overview | Namespace-filtered readiness, scrape failures, CPU, memory, restarts and logs, including applications without native metrics |
| Uptime Kuma | Application health, event loop, MariaDB, container resources and logs |
| Uptime Kuma Monitors | Paginated status history, rolling availability, latency and certificate lifetime |
| Authentik | Server, worker, outpost connectivity, request load and background tasks |
| Grafana and Renderer | Requests, rendering queue, browser activity, Redis and memory pressure |
| Home Assistant and MQTT | Entity availability, automation activity, broker connectivity, traffic and VictoriaMetrics HistoryDB |
| HomeCDN | NGINX status, connections, requests, container resources and logs |
| Timeserver (Chrony) | Collection health, reference, stratum, offset, delay and application logs |
| Monitoring Logs (Loki) | Ingestion, rejected entries, compaction, requests, storage and logs |
| Monitoring Metrics (VictoriaMetrics) | Ingestion, read-only state, write reserve, requests, storage and logs |
| PostgreSQL and Backups | CloudNativePG readiness, collectors, backups, replication, resources and logs. This is the only PostgreSQL dashboard. |

**Operations Center** is provisioned at Grafana's root, outside the monitoring
folders. It summarizes cluster and node health, monitors, workloads, capacity,
databases and telemetry delivery, with links to diagnostic dashboards.

Kuma group monitors and individual monitors have separate status-history panels.
The exporter does not provide parent-child relationships, so this is not a nested
copy of Kuma's tree. History is sampled telemetry, with 20 rows per page and up to
120 time samples. Short transitions can be missed when viewing long periods.
Missing samples remain gaps. All application dashboards start at one hour.
Healthy, quiet deployments can therefore have an empty log panel without a
collection failure.

Home Assistant's availability metric includes both `unavailable` and `unknown`
states. The dashboard labels this explicitly. Containers without a memory limit
show **No limit configured**, not a fabricated utilization percentage.

Each application dashboard refreshes once a minute. Tables and logs use full
width. Cluster filters persist in the URL. The overview adds a namespace filter,
and Uptime Kuma adds monitor ID and rolling-window filters. The log search field
filters displayed log lines, not the volume charts. Each log view is capped at
500 lines. Missing data remains N/A. Exporter HTTP health and backend collection
health are separate signals. An unavailable Chrony backend cannot establish clock
synchronization, and NGINX stub_status supplies neither HTTP status codes nor
traffic bytes. HistoryDB has a separate backend scope from central metrics.

Homepage and Scrypted intentionally have workload/resource/log coverage only.
PostgreSQL and backup diagnostics live in Monitoring Applications. Application logs
are operational, sanitized records, and empty results may indicate a quiet source.
Queries can reveal runtime entity or monitor names to authorized Grafana readers,
but no personal names, endpoints or credentials are embedded in the JSON.

Two additional dashboards are provisioned into **Monitoring Logs**, folder UID
`monitoring-logs`, from `components/_dashboards/log-dashboards/`:

| Dashboard | Purpose | Datasources |
| --- | --- | --- |
| Log Explorer | Filtered Pod logs, host/K3s journal and Kubernetes Events, with volume and keyword trends | Monitoring Logs |
| Log Pipeline Health | Collector coverage, delivery retries/drops, deliberate exclusions, central Loki health, retention and storage | Monitoring Metrics |

Enable Grafana's `_monitoring-logs-datasource` component and configure its query
reader Secret before using the explorer. Enable MonitoringAgent's central
`_logs-telemetry` component so backend health panels have data. Rebuild the log
JSON with `python3 Applications/MonitoringGrafana/scripts/build_log_dashboards.py`.
The existing dashboard component installs both folders automatically. Each new
dashboard refreshes every 30 seconds and opens a one-hour window. Log panels are
full width, wrap text, and cap each query at 500 lines. Filters and time ranges
are URL-backed. Grafana handles narrow-screen stacking and panel inspection.

Errors and warnings in the explorer are keyword heuristics, not a guarantee of
complete severity classification. Empty log results can mean a quiet source.
N/A in health panels means absent telemetry, never a healthy zero. The last-log
timestamp and oldest metric-sample age make the different freshness signals
explicit. The shared central backend panels intentionally ignore the agent
cluster filter. No live tail WebSocket or scheduled email/PDF reports are enabled.

## Installation

### 1. Check prerequisites

Use an existing configured Grafana overlay, a working Monitoring Metrics
datasource, `kubectl` and standalone `kustomize`. The dashboard component depends
on the Grafana Deployment named `grafana`. Its server and datasource remain in
`Applications/Grafana`.

Run the commands from the repository root, in Bash. Replace the two example
values with your existing Grafana context and overlay directory name:

```bash
set -euo pipefail
export GRAFANA_CONTEXT='your-grafana-context'
export GRAFANA_OVERLAY='my-environment'

kubectl --context "$GRAFANA_CONTEXT" -n grafana get deployment grafana
test -f "Applications/Grafana/overlay/$GRAFANA_OVERLAY/kustomization.yaml"
test -f Applications/MonitoringGrafana/components/_dashboards/kustomization.yaml
```

Do not create a new overlay by overwriting an existing environment. For a new
Grafana installation, first follow the Grafana application guide and configure
its private overlay. The public sample is a template, not a live environment.

### 2. Verify the datasource and check for UID conflicts

In Grafana, open **Connections > Data sources > Monitoring Metrics** and use
**Save & test** where available. In **Explore**, select this datasource and query:

```promql
count by (cluster, job) (up)
```

The provisioned datasource UID must be `monitoring-metrics`. Credentials stay
in the existing private Secret inputs. Do not insert credentials into dashboard
JSON or share links.

Check whether a folder with UID `monitoring-infrastructure` or dashboards with
UIDs from the supplied dashboard JSON already exist. Reuse the suite's own folder
when updating. Resolve unrelated UID conflicts before provisioning, which can
overwrite dashboards sharing the same UID.

### 3. Save the previous desired configuration

Before changing the overlay, capture its current rendered configuration in an
owner-only temporary directory. This contains Secrets, so keep it private:

```bash
umask 077
GRAFANA_REVIEW_DIR=$(mktemp -d)
export GRAFANA_REVIEW_DIR

kustomize build "Applications/Grafana/overlay/$GRAFANA_OVERLAY" \
  > "$GRAFANA_REVIEW_DIR/before.yaml"
```

This is a snapshot of the local desired configuration, not a backup of Grafana's
database or a guarantee that the local overlay matches the current deployment.
Confirm that relationship and preserve any existing dashboards before deployment.

### 4. Enable the dashboard component

The public sample already contains the dashboard component. For an existing
private overlay, ensure its `components` list contains:

```yaml
components:
  - ../../components/_monitoring-metrics-datasource
  - ../../../MonitoringGrafana/components/_dashboards
```

Keep other existing component entries. Do not add the datasource a second time
if it is already enabled. Real environment configuration stays in the ignored
overlay. The reusable dashboard package contains no private environment values.

The component's provider must have these settings:

```yaml
apiVersion: 1
providers:
  - name: monitoring-infrastructure
    orgId: 1
    folder: Monitoring Metrics
    folderUid: monitoring-infrastructure
    type: file
    disableDeletion: true
    allowUiUpdates: false
    updateIntervalSeconds: 60
    options:
      path: /var/lib/grafana/monitoring-dashboards
```

The component supplies this file. Do not create a second provider manually.
The explicit `folder`/`folderUid` settings create the UI folder association.

### 5. Render, validate and review

```bash
kustomize build "Applications/Grafana/overlay/$GRAFANA_OVERLAY" \
  > "$GRAFANA_REVIEW_DIR/after.yaml"

kubectl --context "$GRAFANA_CONTEXT" apply --dry-run=server \
  -f "$GRAFANA_REVIEW_DIR/after.yaml"
```

Review the two private manifests locally. The intended change adds dashboard
and provider ConfigMaps and Grafana mounts/references. Resolve any unrelated
pending changes before applying the full Grafana overlay. Do not paste rendered
manifests or Secret diffs into shared logs. Do not disable Kustomize load
restrictions to make the component build.

Regenerate the canonical JSON and run the repository checks:

```bash
python3 Applications/MonitoringGrafana/scripts/build_dashboards.py
python3 Applications/MonitoringGrafana/scripts/build_log_dashboards.py
python3 Applications/MonitoringGrafana/scripts/build_application_dashboards.py
python3 -m unittest discover -s tests/monitoring -v
MONITORING_PRIVATE_OVERLAYS=1 \
  python3 -m unittest discover -s tests/monitoring -v
```

The second test command renders local private overlays. Its output must remain
private because environment-specific names may appear in failures.

Optionally validate application expressions against the running backends before
deployment. This read-only check prints query status and result counts, never log
lines or metric label values. Zero result counts require interpretation, they do
not indicate healthy services:

```bash
# In a separate terminal, stop with Ctrl-C after checking:
kubectl --context your-monitoring-context -n monitoring-logs \
  port-forward pod/loki-0 19100:3100
```

```bash
python3 Applications/MonitoringGrafana/scripts/check_application_queries.py \
  --context your-monitoring-context --loki-url http://127.0.0.1:19100
```

### 6. Deploy to the Grafana cluster

After reviewing the target context and changes:

```bash
kubectl --context "$GRAFANA_CONTEXT" apply \
  -f "$GRAFANA_REVIEW_DIR/after.yaml"

kubectl --context "$GRAFANA_CONTEXT" -n grafana \
  rollout status deployment/grafana --timeout=5m

kubectl --context "$GRAFANA_CONTEXT" -n grafana get pods
```

Generated ConfigMap names change with their content, updating the Grafana Pod
template. A single-replica Grafana deployment can have a brief interruption
during the rollout. The agent/backend deployments do not need dashboard changes.

### 7. Check logs and provisioned dashboards

Choose the actual Grafana server Pod from the Pod list, not a renderer or cache
Pod. Replace the example name below:

```bash
kubectl --context "$GRAFANA_CONTEXT" -n grafana logs \
  pod/your-grafana-server-pod -c grafana --since=10m
```

Check for dashboard provisioning, duplicate UID, invalid JSON and datasource
errors. Then open **Dashboards > Monitoring Metrics**. Expect these eleven dashboards:

- Overview
- Cluster and Workloads
- Node Diagnostics
- Pod and Container Diagnostics
- K3s and etcd
- DNS and Networking
- Storage and Longhorn
- Controllers and Certificates
- Collection and Metrics Backend
- Daily Review
- Capacity and Reliability

Confirm none of the suite dashboards is in root/General. Open Overview first,
then Collection and Metrics Backend. Check cluster discovery, recent timestamps,
query errors and clear Unknown/N/A handling. Compare representative values to
Explore. Follow a Pod-to-node or PVC link and confirm that scope and time persist.

Verify distinct series colors, blue quantitative accents and readable
legends in dark/light mode. Status findings must retain explicit text. Dashboard
headers contain no Grafana logo. Check at least one dashboard on a narrow mobile
viewport.

### 8. Use the report views

Daily Review defaults to the rolling previous 24 hours.
All other dashboards default to the previous hour, with longer ranges available.
Choose an absolute interval when sharing a reproducible historical report.

Use authorized dashboard links and **Inspect > Data > Download CSV** for panel
data. Supported panel-image rendering can use the existing renderer after it
has been verified. Scheduled PDF/email reports and native dashboard PDF export
are not part of this Grafana OSS package.

## Updating

Edit `scripts/build_dashboards.py` or `scripts/build_log_dashboards.py`,
regenerate the corresponding canonical JSON and run the
tests. Validate, render and review the Grafana overlay, then repeat the deployment
and verification steps. Keep dashboard/panel UIDs stable so links continue
working. File provisioning is the source of truth, so UI changes cannot be saved
over these dashboards.

## Rollback and removal

To roll back dashboard content, restore the prior reviewed package/configuration
and reapply the Grafana overlay. A reviewed `before.yaml` can also be applied if
it still represents the intended previous configuration. It may include Secrets
and unrelated resources, so inspect its relevance before use.

`disableDeletion: true` deliberately retains dashboards in Grafana when their
source disappears. Disabling the component stops provisioning but does not
automatically remove its stored dashboards or folder. Reapply the previous
provider plus JSON for content rollback. Explicit dashboard deletion is a
separate operation after checking ownership and backups. Do not delete the
Grafana namespace, database, PVCs or full application to remove this package.

Private render files contain credentials. Remove only the exact temporary
directory created for this installation after the rollback copies are no
longer needed. Do not commit or upload those files.

## Troubleshooting and Query Semantics

Start with Overview and check sample age and unavailable targets. If collection
is stale, inspect Collection and Metrics Backend before interpreting downstream
panels. Select a cluster and preserve the incident time range when moving to
the relevant workload, node, network, storage, database or controller dashboard.
For log investigations, use Log Explorer and Log Pipeline Health.

- `N/A` means missing, stale, unsupported or out-of-scope data, not healthy zero.
  Observed cluster counts do not establish an expected cluster inventory.
- Queries preserve `cluster` and resource identity. Certificate namespaces use
  `exported_namespace`, Longhorn PVCs use `pvc_namespace` and `pvc`, and CNPG
  instances use `cnpg_cluster` and `cnpg_instance` alongside `namespace`.
- Native etcd queries use `job="etcd"` and retain each member's `node`.
- Rate queries use `$__rate_interval`. Fast, normal and slow collection defaults
  are 15, 30 and 60 seconds. Dashboard query steps do not downsample stored data
  or change backend retention.
- Counters use `rate` or `increase`. Histogram quantiles aggregate by `le` and
  reflect the retained bucket boundaries, so reduced histograms are coarse.
- Backup timestamps describe backup state, not successful restore tests.
  USB hardware may not expose SMART values. Multus, DHCP and complete service
  availability require separate functional checks.
- Compare logical PVC usage and Longhorn physical allocation separately.
  Capacity projections can change with retention, compaction and workload changes.
- Deliberate log exclusions are intentional filtering. Delivery drops and
  retries describe transport behavior and require separate investigation.

If a panel has no data, clear narrow filters, check recent source samples and
compare its exact query in Explore. Keep unsupported metrics at `N/A`.

## References

- [Grafana application and datasource](../Grafana/README.md)
- [Grafana file provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Native gradient options](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/time-series/)
- [Sharing and reporting edition requirements](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/)
