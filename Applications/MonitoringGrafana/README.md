# MonitoringGrafana

Grafana OSS dashboards for Kubernetes, hosts, infrastructure controllers,
storage, PostgreSQL and the metrics pipeline. This package is loaded by the
existing [Grafana application](../Grafana/README.md).

The dashboard JSON is generated from one deterministic Python definition, then
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
Monitoring Metrics folder and assigns all twelve dashboards to it. Dashboards never
need to be imported individually into the root dashboard list.

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
UIDs from the implementation plan already exist. Reuse the suite's own folder
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
python3 -m unittest discover -s tests/monitoring -v
MONITORING_PRIVATE_OVERLAYS=1 \
  python3 -m unittest discover -s tests/monitoring -v
```

The second test command renders local private overlays. Its output must remain
private because environment-specific names may appear in failures.

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
errors. Then open **Dashboards > Monitoring Metrics**. Expect these twelve dashboards:

- Overview
- Cluster and Workloads
- Node Diagnostics
- Pod and Container Diagnostics
- K3s and etcd
- DNS and Networking
- Storage and Longhorn
- PostgreSQL and Backups
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

Daily Review defaults to the previous completed day. Capacity and Reliability
defaults to seven days, with longer ranges available. Refresh is off by default.
Choose an absolute interval when sharing a reproducible historical report.

Use authorized dashboard links and **Inspect > Data > Download CSV** for panel
data. Supported panel-image rendering can use the existing renderer after it
has been verified. Scheduled PDF/email reports and native dashboard PDF export
are not part of this Grafana OSS package.

## Updating

Edit `scripts/build_dashboards.py`, regenerate the canonical JSON and run the
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

## References

- [Implementation and query-design plan](../../docs/plans/grafana-monitoring-dashboards.md)
- [Metric and label contract](../../docs/monitoring-dashboard-metrics.md)
- [Operational dashboard runbook](../../docs/monitoring-dashboard-runbook.md)
- [Grafana application and datasource](../Grafana/README.md)
- [Grafana file provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
- [Native gradient options](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/time-series/)
- [Sharing and reporting edition requirements](https://grafana.com/docs/grafana/latest/visualizations/dashboards/share-dashboards-panels/)
