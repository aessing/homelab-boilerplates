# Monitoring dashboard metric contract

This document describes the public query contract used by the dashboards in
`Applications/MonitoringGrafana`. It contains no environment-specific label
values. The Grafana datasource is named **Monitoring Metrics** and keeps the
stable UID `monitoring-metrics`.

## Collection cadence

Dashboard queries preserve the three collection classes configured in
MonitoringAgent:

| Query class | Minimum step | Typical sources |
| --- | --- | --- |
| Fast | 15 seconds | host, container and Remote Write activity |
| Normal | 30 seconds | Kubernetes and control-plane request metrics |
| Slow | 60 seconds | controllers, certificates, storage and reports |

Rate queries use `$__rate_interval`. Reports use the selected `$__range` only
for bounded counter increases and observed-period summaries. A display step
does not downsample stored data or change the 90-day retention policy.

## Identity rules

- `cluster` is retained in every cross-cluster aggregation.
- Kubernetes resources retain `namespace` and their resource name.
- Nodes retain `node`. Container queries exclude empty containers and the
  `POD` sandbox where appropriate.
- Certificate object identity uses `exported_namespace` and `name`. The
  scraper's own namespace is not the certificate namespace.
- Longhorn object identity uses `pvc_namespace`, `pvc`, `volume` and, where
  applicable, `exported_node`.
- CloudNativePG identity uses `namespace`, `cnpg_cluster`, `cnpg_instance` and
  `cnpg_role`. Logical database size is scoped to primaries.
- Native etcd panels use `job="etcd"` and preserve each member's `node`.

These rules prevent equal resource names in different clusters or namespaces
from being combined accidentally.

## Dashboard coverage

| Dashboard | Primary metric families |
| --- | --- |
| Overview | `up`, node CPU/memory, workload replicas, PVC usage, certificate expiry |
| Cluster and Workloads | kube-state-metrics, cAdvisor CPU/memory, Jobs, CronJobs and scheduling state |
| Node Diagnostics | node-exporter CPU, memory, PSI, filesystem, disk, network and hardware sensors |
| Pod and Container Diagnostics | Pod state, cAdvisor resource use, throttling, OOM, restarts and owners |
| K3s and etcd | API server, scheduler, kubelet and native etcd metrics |
| DNS and Networking | CoreDNS, Traefik, MetalLB and Kube-VIP target/process health |
| Storage and Longhorn | kubelet PVC stats, VolumeAttachment, Longhorn and storage controller metrics |
| PostgreSQL and Backups | CloudNativePG resource, SQL collector, replication, WAL and backup metrics |
| Controllers and Certificates | cert-manager, controller-runtime, workqueue and metrics-server metrics |
| Collection and Metrics Backend | scrape health, Alloy Remote Write, VictoriaMetrics and vmauth metrics |
| Daily Review | bounded increases and observed state during the previous completed day |
| Capacity and Reliability | node, namespace, PVC, Longhorn and VictoriaMetrics trends |

## Missing-data semantics

The dashboards do not convert missing series into healthy zero values. `N/A`
means missing, stale, unsupported or outside the selected scope. Time-series
gaps stay disconnected. Current status panels may show zero only when an
observed inventory establishes the denominator, such as observed targets minus
targets reporting `up=1`.

An absent cluster cannot be distinguished indefinitely from a retired cluster
without a separate expected-inventory source. The current dashboards therefore
describe observed infrastructure, not a formal service-level objective.

## Histograms and counters

Histogram quantiles aggregate retained buckets by `le` before calculating the
quantile. They are labelled coarse where collection intentionally retains fewer
buckets. Counter panels use `rate` or `increase` so counter resets do not appear
as spikes. Storage size metrics are gauges and are not queried with `rate`.

## Known limits

- No SMART values are expected for USB storage that does not expose SMART.
- Kube-VIP currently supplies scrape/process health, not verified VIP ownership
  or failover success.
- Metrics do not reconstruct Kubernetes events or logs between scrapes.
- Backup timestamps prove exported backup state, not restore success.
- Multus, DHCP and complete request-path availability need later synthetic tests.
- Application-specific metrics, UniFi metrics, Loki logs and traces are outside
  this dashboard package.
