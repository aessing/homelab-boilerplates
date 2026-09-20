# MonitoringAgent

Per-cluster metrics collection with Grafana Alloy, node-exporter and
kube-state-metrics, plus an optional dedicated log Alloy DaemonSet. Metrics
are pushed over HTTPS to [MonitoringMetrics](../MonitoringMetrics/README.md).
Logs and Kubernetes Events are pushed to [MonitoringLogs](../MonitoringLogs/README.md).
All components are self-hosted and use open-source software.

## Contents

```text
base/                         Namespace, quota and network policies
components/
  _alloy/                     StatefulSet, RBAC, Service and collection config
  _node-exporter/             Host metrics DaemonSet and Service
  _kube-state-metrics/        Object metrics Deployment, RBAC and Service
  _central-telemetry/         Optional backend self-monitoring
  _etcd/                      Optional native K3s etcd metrics
  _logs/                      Per-node Pod, journal and selected host log collection
  _logs-events/               Cluster-wide Kubernetes Event collection
overlay/
  _SAMPLE/                    Complete example for the central cluster
    configs/alloy.env         Cluster identity, URLs and scrape intervals
    generators/               Environment ConfigMap and credential Secrets
    patches/                  Network destinations, storage and quota
    secrets/                  Public placeholders, replace before deployment
    transformers/             Images, labels and replica counts
  <environment>/              Git-ignored local configuration
```

The overlay file layout is the same for central and remote clusters. Remote
clusters leave the central-telemetry component and its SecretGenerator disabled.
The unused telemetry placeholder file is not rendered into a Secret.

## Features and Coverage

| Source | Default interval | Collected data |
| --- | --- | --- |
| node-exporter | 15s | Host CPU, memory, load, disk, filesystem, network and available hardware sensors |
| Kubelet cAdvisor | 15s | Container CPU, throttling, memory, network and exposed filesystem metrics |
| kube-state-metrics | 60s | Pod states, restarts, requests/limits, workload replicas, jobs, node conditions, PV/PVC and storage objects |
| Kubelet metrics | 60s | Kubelet performance and, on K3s, the shared embedded-component metrics registry |
| Alloy and kube-state-metrics telemetry | 30s | Collector health, scrape status and Remote Write queue |
| Explicit application opt-ins | 30s | Application-owned Prometheus/OpenMetrics metrics |
| Optional central telemetry | 30s | VictoriaMetrics and vmauth operational metrics |
| Infrastructure controllers | 60s | CoreDNS, cert-manager, trust-manager, Traefik, Longhorn, CSI, Reloader and CloudNativePG operator metrics |
| Kube-VIP | 60s | Per-node VIP and leader/controller metrics |
| metrics-server | 60s | Collector health and request-processing self-metrics |
| MetalLB | 60s | Controller and per-node speaker metrics |
| Optional native K3s etcd | 30s | Leader and quorum health, proposals, database size, peer traffic and storage latency |
| CloudNativePG instances | 60s | Per-instance PostgreSQL, replication, WAL, connection and database metrics |
| Optional CNPG resource state | 60s | Desired/ready instances, cluster conditions, backup phases, schedules and Barman recovery-window timestamps |
| Log Alloy, per node | Continuous | All Kubernetes container stdout/stderr, systemd journal, selected K3s/containerd and host maintenance logs |
| Log Alloy Events, once per cluster | Continuous | Kubernetes Events as structured JSON log records |

Each scrape also generates target-health metrics such as `up`.
The server-side writer identity selects the trusted `cluster` label.

This covers core node, workload, collection-pipeline and the listed platform
services. Kubernetes Services do not automatically make arbitrary application
metrics available. Other applications still require explicit opt-in. UniFi is
covered by the dedicated [Unpoller application](../Unpoller/README.md). The
optional `_unifi-telemetry` component monitors that collector's own Alloy
endpoint without scraping UnPoller twice. Multus functional probes remain a
separate coverage item. Detailed SMART collection is deliberately
omitted for storage connected through USB adapters without SMART passthrough.
Log collection excludes traces, SQL statements, query payloads, application
data files and arbitrary private application log files. Application-specific
file logs are added only after a separate review. Dashboards and alerts are not
provided by this application.

K3s shares its metrics registry between embedded Kubernetes components.
The registry is shared **per process/node**, not across the whole cluster.
Keep each node's endpoint and the `node`/`instance` labels. The included
`20-metric-filters.alloy` reduces selected API-server and etcd-client histogram
buckets after scraping and before the Remote Write WAL. It retains boundaries
`0.1`, `0.4`, `1`, `5` and `+Inf` for request-duration histograms, plus their
sums and counts. Percentiles are therefore coarser, especially above 5 seconds.
Payload-size, watch/cache-detail and SLI-duration buckets are dropped. Their
sums/counts and other metric families remain available. Existing stored data
is not deleted. Filtering reduces storage/network/WAL load, not endpoint
generation or HTTP scrape size. Use `sum(rate(...[5m]))` across nodes for
counters, not a single arbitrarily selected control-plane node.
Do not add duplicate API server, scheduler and controller-manager scrapes
without checking which families the existing endpoint already exposes.
See the [K3s metrics documentation](https://docs.k3s.io/reference/metrics).

The optional `_etcd` component discovers server nodes and scrapes their native
K3s etcd endpoint every 30 seconds. K3s exposes this endpoint on plain HTTP port
2381 without authentication. It must therefore stay inside the cluster network
and be restricted by exact-source UFW rules and the included NetworkPolicy.
Because the endpoint also contains the K3s shared metrics registry,
`40-etcd.alloy` keeps only native `etcd_*` and scrape-health metrics. It removes
unnecessary histogram buckets while retaining sums, counts and coarse latency
boundaries for quorum, peer-network and storage paths.

`30-infrastructure-filters.alloy` removes generic API machinery, REST-client,
workqueue and Go runtime histogram buckets from metrics-server and MetalLB.
Component-specific counters, gauges, sums and counts remain. metrics-server
keeps its own Kubelet-request and metric-freshness histograms. MetalLB keeps
four coarse controller-reconcile boundaries (`0.1`, `1`, `5` and `+Inf`).

## Prerequisites

- Kubernetes on Linux, `kubectl` and standalone `kustomize`.
- A CNI enforcing NetworkPolicies.
- A ready MonitoringMetrics HTTPS endpoint with a trusted certificate and a
  dedicated writer identity for this cluster.
- When enabling logs, a ready MonitoringLogs HTTPS endpoint with a trusted
  certificate and a dedicated writer token for this cluster.
- Longhorn with the expandable `longhorn-retain` StorageClass, or an equivalent
  class configured by an overlay patch.
- Kubelet certificates valid for the node addresses used by discovery.
- CoreDNS in `kube-system` with label `k8s-app=kube-dns`. Adapt the DNS policy
  if using a different DNS deployment or node-local DNS.
- Port 9100 available on every node's internal IP. Remove conflicting host
  exporters before deploying this DaemonSet.
- Node firewall rules permitting 9100, 2112, 9120 and, when `_etcd` is enabled,
  2381 only from the intended same-cluster collector node sources and required
  local health probes.
- K3s server nodes configured with `etcd-expose-metrics: true` before enabling
  `_etcd`. Roll the server nodes one at a time and verify cluster health.
- Destination ingress policies permitting Alloy to the selected Longhorn manager
  and CloudNativePG instance metrics ports. The repository supplies these rules
  for its Longhorn and PostgreSQL bases.

node-exporter uses host networking because its network collectors must inspect
the node network namespace. It binds to the node IP from the Downward API,
not every interface. Host-network traffic is not reliably isolated by ordinary
Pod NetworkPolicies. Protect it using node/network firewall rules, accounting
for the Pod or node source IP seen after NAT. Do not expose it publicly.
There is no LoadBalancer or Ingress for the agent.

## Deployment

Run these commands from `Applications/MonitoringAgent`.

### 1. Create Your Overlay

```sh
umask 077
cp -r overlay/_SAMPLE overlay/my-environment
chmod 600 overlay/my-environment/secrets/secret-monitoring-agent-remote-write.env
chmod 600 overlay/my-environment/secrets/secret-monitoring-agent-telemetry.env
chmod 600 overlay/my-environment/secrets/secret-monitoring-agent-logs.env
```

Use an overlay name that does not start with an underscore so it stays ignored
by Git. Keep real credentials and environment-specific values in that overlay.
Never force-add them or rendered Secret manifests.

### 2. Configure Credentials and the Cluster Role

Replace the placeholder in
`secrets/secret-monitoring-agent-remote-write.env` with the exact token assigned
to this cluster in MonitoringMetrics:

```dotenv
token=<matching-central-writer-token>
```

Do not generate an unrelated token on the agent side. Each cluster gets a
different writer identity. Never reuse the Grafana reader password.

When log collection is enabled, replace the placeholder in
`secrets/secret-monitoring-agent-logs.env` with the matching MonitoringLogs
writer token and set its endpoint in `configs/alloy-logs.env`:

```dotenv
LOKI_WRITE_URL=https://logs.example.com/loki/api/v1/push
```

The Metrics and Logs writer tokens are distinct. Do not use a Loki query-reader
credential or a Metrics Remote Write token for log ingestion.

The sample enables central backend telemetry. Enable it on only one collector,
normally in the backend's cluster. Set
`secrets/secret-monitoring-agent-telemetry.env` to the central telemetry token.

The sample also enables native etcd collection. Keep the `_etcd` component only
when the cluster uses embedded K3s etcd, every server has
`etcd-expose-metrics: true`, and UFW permits TCP 2381 from every node where Alloy
can run. Otherwise comment out `../../components/_etcd` until those prerequisites
are ready.

For other clusters, comment out these two entries in `kustomization.yaml`:

- `../../components/_central-telemetry` under `components` (remove/comment the
  empty `components:` key as well).
- `./generators/secret-monitoring-agent-telemetry.yaml` under `generators`.

Also remove the final local-Traefik `op: add` rule from
`patches/network-policy-alloy-egress.yaml` when the backend is in another cluster.
The unused telemetry generator and placeholder input can remain for a consistent
overlay layout. They are not deployed when disabled.

Keep generated name suffixes enabled. Credential and ConfigMap input changes
then update workload references and trigger an Alloy rollout.

### 3. Configure Patches and Transformers

| File | Configuration |
| --- | --- |
| `configs/alloy.env` | Unique cluster name, Remote Write URL, telemetry hostname, 15/30/60 intervals |
| `configs/alloy-logs.env` | Loki push URL for the dedicated log collector |
| `patches/network-policy-alloy-egress.yaml` | API Service IP, API node IPs, kubelet/exporter node IPs and backend ingress IP |
| `patches/network-policy-kubernetes-api-egress.yaml` | API Service and API node IPs |
| `patches/network-policy-alloy-logs-egress.yaml` | API Service, API node IPs on 6443, Loki ingress IP and local Traefik Pods on 8443 |
| `patches/pvc.yaml` | Initial Alloy WAL size, default 2 GiB |
| `patches/resource-quota.yaml` | Pod and PVC quotas, extend resource quotas if needed |
| `transformers/images.yaml` | Pinned image versions |
| `transformers/labels.yaml` | Deployment labels |
| `transformers/replicas.yaml` | One Alloy and one kube-state-metrics replica |
| `kustomization.yaml` | Components, generators, patches and version label |

The sample uses reserved documentation IPs in `192.0.2.0/24` and
`metrics.example.com`. Replace them before deployment. Use exact `/32` node
and service addresses instead of allowing entire private address ranges.
Update the policies when adding or replacing nodes.

The defaults assume IPv4 and the `monitoring-agent` namespace. Internal static
targets use namespace-local service names and therefore do not assume a specific
cluster DNS suffix. Adjust addresses and policies if changing those assumptions.

Do not increase Alloy replicas without implementing target sharding. Otherwise
each replica scrapes the same targets and produces duplicate samples.

### 4. Validate and Deploy

```sh
kubectl config current-context
kustomize build overlay/my-environment > /dev/null
```

Confirm the intended context, then deploy:

```sh
set -o pipefail
kustomize build overlay/my-environment | kubectl apply -f -
kubectl -n monitoring-agent rollout status statefulset/alloy-metrics
kubectl -n monitoring-agent rollout status deployment/kube-state-metrics
kubectl -n monitoring-agent rollout status daemonset/node-exporter
kubectl -n monitoring-agent rollout status daemonset/alloy-logs
kubectl -n monitoring-agent get pods,pvc
```

Keep exactly one metrics collector per cluster and preserve its WAL PVC during
updates. Verify that no legacy collector scrapes the same targets before deployment.

Apply the repository's Longhorn and CSI Snapshot Controller changes before the
agent. They provide the Longhorn metrics ingress rule and enable the snapshot
controller's internal metrics listener. Apply the PostgreSQL base change before
expecting database instance metrics through a default-deny ingress policy.

Rendering checks composition, not connectivity or the Alloy runtime. Never
print rendered private overlays to shared logs or save them in shared temporary
files. They contain credentials.

### 5. Verify Collection

Inspect Alloy and exporter logs locally. Check for TLS, permission, discovery
and Remote Write errors. Through the authenticated Grafana datasource, verify:

- `up` grouped by `cluster`, `job` and `node`, with the expected node count.
- Container CPU/memory and Pod restart/state metrics for running workloads.
- `node_network_receive_bytes_total` for real node interfaces, not just an
  exporter Pod interface.
- Remote Write pending, failed and dropped samples.
- Alloy WAL/PVC space, CPU throttling, memory usage and container restarts.
- `count by (cluster) (up{job="etcd"})` and
  `sum by (cluster) (up{job="etcd"})`, both matching the server-node count.
- `min by (cluster) (etcd_server_has_leader) == 1` and exactly one
  `etcd_server_is_leader == 1` series per cluster.
- Pending and failed etcd proposals, database size versus quota, peer latency
  and WAL/backend commit latency.
- In Grafana's **Monitoring Logs** datasource, run `{cluster="<cluster>"}` and
  confirm Pod logs, journal records and Kubernetes Events arrive with the
  expected `cluster`, `node` and `source` labels.

An Alloy readiness success does not prove that all scrapes or Remote Write
requests succeed. Deploy one cluster first and check coverage before expanding.

## Network Requirements

| Source | Destination | Protocol / destination port |
| --- | --- | --- |
| Alloy and kube-state-metrics | Kubernetes API Service | TCP 443 |
| Alloy and kube-state-metrics | API node endpoints after DNAT | TCP 6443 |
| Alloy | Local cluster kubelets | TCP 10250 |
| Alloy | Embedded K3s etcd server nodes | TCP 2381 (HTTP) |
| Alloy | Local cluster node-exporters on node IPs | TCP 9100 |
| Alloy | Local kube-vip listeners on node IPs | TCP 2112 |
| Alloy | Local MetalLB speakers on node IPs | TCP 9120 (HTTPS) |
| Alloy | MetalLB controller Pods | TCP 9120 (HTTPS) |
| Alloy | metrics-server Pods | TCP 10250 (HTTPS) |
| Alloy | kube-state-metrics Pods | TCP 8080 and 8081 |
| Alloy | CoreDNS Pods | TCP 9153 |
| Alloy | CSI snapshot-controller and CloudNativePG operator Pods | TCP 8080 |
| Alloy | Longhorn CSI sidecars | TCP 8000 |
| Alloy | cert-manager and trust-manager Pods | TCP 9402 |
| Alloy | Traefik Pods | TCP 9100 |
| Alloy | Longhorn manager Pods | TCP 9500 |
| Alloy | Reloader Pods | TCP 9090 |
| Alloy | CloudNativePG database Pods | TCP 9187 |
| Alloy | Explicitly opted-in application Pods | TCP port named `metrics` |
| Alloy | Central Traefik ingress IP | TCP 443 |
| Central-cluster Alloy | Local Traefik Pods after DNAT | TCP 8443 |
| Log Alloy, per node | Kubernetes API Service | TCP 443 |
| Log Alloy, per node | Central Loki Traefik ingress IP | TCP 443 |
| Metrics Alloy | Local Log Alloy metrics endpoint | TCP 12345 |
| Non-host-network agent Pods | CoreDNS Pods | UDP/TCP 53 |

Ports and policy processing depend on the actual Service targets and CNI.
Adjust the defaults for a different deployment. Health probes also need the
kubelet-to-Pod or local node path. The backend never initiates cross-cluster
connections to agents.

MetalLB and metrics-server generate short-lived self-signed serving
certificates. Their scrapes use Kubernetes ServiceAccount bearer authentication,
TLS 1.2 or newer, narrow NetworkPolicies and same-cluster destinations.
Certificate verification is intentionally disabled for these two internal
endpoints because there is no stable CA to trust. Traffic remains encrypted,
but the collector does not cryptographically verify the endpoint identity.

The embedded K3s etcd metrics endpoint on TCP 2381 is different. It uses HTTP
without endpoint authentication. Do not expose it through an Ingress or
LoadBalancer. Its protection comes from the cluster-local network path, exact
UFW source rules and the agent NetworkPolicy.

## Application Metric Opt-in

For an HTTP endpoint at `/metrics`, label the application's Pod template
`monitoring-metrics-scrape: "true"` and name its container port `metrics`.
If the destination is isolated by ingress policies, add an ingress rule in the
application's own overlay:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-monitoring-agent
spec:
  podSelector:
    matchLabels:
      monitoring-metrics-scrape: 'true'
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring-agent
          podSelector:
            matchLabels:
              app.kubernetes.io/name: monitoring-agent
              app.kubernetes.io/component: alloy
      ports:
        - protocol: TCP
          port: metrics
```

Apply it in the destination application's namespace. It does not grant access
to other application ports. Review metric labels for sensitive data and
cardinality before opting in.

Endpoints requiring HTTPS, authentication or a different path need an explicit
Alloy scrape configuration. ServiceMonitor/PodMonitor CRDs are not consumed by
this configuration. UniFi can be added through a local exporter later.
The log collector is separate from metric Alloy. Its DaemonSet runs once per
node and owns only log tailing. The singleton metrics Alloy collects Kubernetes
Events, which avoids duplicate Events from every node.

The coverage and network tables above describe the implemented sources and
their prerequisites. Scrape health does not prove end-to-end service availability.

## Resources and Retention

### PostgreSQL and backup state

The `_cnpg-state` component is enabled in the sample. It requires CloudNativePG
`v1` Cluster, Backup and ScheduledBackup CRDs and the Barman Cloud `v1`
ObjectStore CRD. Remove the component when these operators are not installed.
It extends the existing kube-state-metrics instance, with list/watch access to
those resources and CRD discovery only. No Secret access or new exporter is
needed. Instance discovery continues to cover all matching PostgreSQL Pods,
including new clusters, provided their namespace permits Alloy on TCP 9187.

For restricted databases, follow the PostgreSQL deployment guide's
[monitoring permission step](../PostgreSQL/README.md#monitoring-permissions-after-initialization).
Both `postgres` and the bootstrap database must allow the operator-managed
`cnpg_metrics_exporter` role to connect. Check actual SQL metric collection,
not just HTTP target health:

```promql
min by (cluster) (cnpg_collector_up)
max by (cluster) (cnpg_collector_last_collection_error)
cnpg_resource_instances_ready
cnpg_resource_condition{condition="ContinuousArchiving"}
time() - cnpg_resource_backup_last_success_timestamp_seconds
cnpg_resource_backup_phase{phase="failed"} == 1
```

Backup timestamps come from the Barman ObjectStore catalogue. Unused templates,
unfinished backups and stores with no backup history may legitimately have
absent timestamps. Absence must not be interpreted as a healthy backup. Backup
state does not prove restorability, which requires a separate restore test.
The instance endpoint can also expose `barman_cloud_cloudnative_pg_io_*`
metrics. Prefer those over deprecated CNPG collector backup timestamps.

### Resource budgets

| Component | CPU request / limit | Memory request / limit |
| --- | --- | --- |
| Alloy, once per cluster | 0 / 500m | 0 / 512Mi |
| kube-state-metrics, once per cluster | 0 / 200m | 0 / 128Mi |
| node-exporter, per node | 0 / 100m | 0 / 64Mi |
| Log Alloy, per node | 0 / 250m | 0 / 256Mi |

CPU and memory requests are explicitly zero, so these containers reserve no
scheduling capacity. Omitting requests while keeping limits would make Kubernetes
default requests to the limits. This increases overcommit and eviction risk
under node pressure. PVC storage requests remain unchanged. Limits cap usage and can
cause throttling or OOM restarts. These are starting budgets, not measured
capacity guarantees. Observe a representative workload and backlog recovery
before reducing them further. Adjust namespace quotas along with any increases.
The agent namespace permits 2 CPU and 2 GiB of limits. This covers all three
components on a three-node cluster and a temporary kube-state-metrics rollout.
This quota does not reserve CPU or memory.

The Remote Write queue is capped at four shards to reduce memory overhead.
The 2 GiB WAL survives Pod replacement and can retain unsent samples for up to
eight hours, subject to storage and ingestion rate. It has no automatic
size-based guarantee. Monitor free space and backlog. Expired unsent samples
can be lost. Exporters have no PVC.

Keep 15/30/60 seconds as a low-overhead default. Changing the fast group from
15s to 10s generates 50% more samples for that group and does not guarantee
higher-resolution source data. Configure intervals in `configs/alloy.env`,
keeping each interval at least as long as its configured scrape timeout.

Historical retention belongs to MonitoringMetrics. Ninety days is usually
sufficient for incident investigation and short-term trends. Use 180 days for
six-month comparisons. Shortening retention can delete existing history and
does not reduce collector CPU or memory consumption.

## Troubleshooting

- **Exporter restarts:** Verify liveness `/livez:8080`, API access and memory.
- **Node exporter bind failure:** Check for another listener on the node's 9100.
- **Discovery timeouts:** Check API Service and node IPs, ports and policies.
- **Scrape timeout:** Check destination ingress rules and node firewall.
- **TLS error:** Check certificate SANs, CA trust and the endpoint hostname.
- **Remote Write 401/403:** Check the central writer identity and token match.
- **Remote Write backlog:** Check backend disk space, connectivity and queue
  metrics before increasing shards or memory.
- **Log Agent not ready:** Check that `/var/log/pods`, `/var/log/journal`,
  `/run/log/journal` and the K3s containerd directory exist on the affected
  node, then check the dedicated Loki token and HTTPS route.
- **Pending PVC:** Check Longhorn capacity, StorageClass and PVC events.

Preserve the WAL PVC during rollout troubleshooting. Redact infrastructure
details and credentials before sharing logs.

## Log Collection Security

The Log Alloy DaemonSet runs as UID 0 only because Linux journal and CRI log
files commonly require root-level read access. It is not privileged, has no
host network or host PID namespace, drops all Linux capabilities, uses a
read-only root filesystem and mounts only the required host log paths as
read-only. Its only writable host path is `/var/lib/alloy-logs`, which stores
tail positions. The WAL has a separate disk-backed 512 MiB `emptyDir`, and the
container has a 768 MiB ephemeral-storage limit with zero request. Kubernetes
evicts a Pod that exceeds these limits after detecting usage, so this is not an
instantaneous filesystem quota. Positions survive Pod replacement, but unsent
WAL data does not. The one-hour segment retention also bounds outage recovery.
Monitor node disk pressure and dropped-entry counters. It does not mount host root, other workloads' Secrets,
application data directories or audit logs.

The collector tails every Kubernetes Pod's standard CRI log, but only a fixed
list of host-maintenance files under `/var/log`. It does not blindly glob all
host files. Journal and runtime-journal directories are required host paths and
are mounted as existing directories, so a misconfigured node fails visibly
instead of the DaemonSet creating log directories on that host.

Newly discovered log files are read from the beginning within a one-hour
discovery window, including short-lived and init-container output. PostgreSQL
records are rebuilt from an allowlist of severity, SQLSTATE and logger fields.
Their free text is deliberately omitted because even error messages can contain
SQL and application data. Known query/payload records are dropped before WAL
ingestion and credential patterns are redacted. These rules cannot guarantee
that arbitrary application text contains no personal information.

Enable `_logs-telemetry` only in the backend cluster, along with its Secret
generator. Its token must match MonitoringLogs' `TELEMETRY_TOKEN`, and
`LOKI_TELEMETRY_HOST` is configured in `configs/alloy-logs.env`. Both backend
scrapes use authenticated HTTPS, never a direct unauthenticated Loki port.

## Repository Validation

With Python 3, kubectl and Kustomize installed, run from the repository root:

```sh
python3 -m unittest discover -s tests/monitoring -v
MONITORING_PRIVATE_OVERLAYS=1 python3 -m unittest discover -s tests/monitoring -v
MONITORING_ALLOY_RUNTIME=1 python3 -m unittest discover -s tests/monitoring -p test_logs.py -v
```

The first command checks public samples. The second also checks local overlays.
The third requires Podman and the pinned Alloy image and executes isolated
synthetic log fixtures, including privacy filtering, CRI fragments, file rotation
and persistent-position restart. It does not access live cluster logs.
The tests cover references, probes, network ports, rollout memory quota,
placeholder token alignment and consistent agent overlay layouts. They do not
connect to Kubernetes. Validate the Alloy configuration separately with the
pinned Alloy image, both with and without the optional telemetry file.
