# Monitoring dashboard runbook

Use this runbook after the file-provisioned dashboards appear in Grafana under
**Dashboards > Monitoring**. Start with the selected time range and data age
before interpreting an apparent incident.

## First response

1. Open **Overview**.
2. Check **Oldest observed target sample** and **Unavailable targets** first.
3. If collection is stale or targets are down, open **Collection and Metrics
   Backend** before trusting downstream panels.
4. Select one cluster. Keep the time window that contains the problem.
5. Follow the matching specialist dashboard and narrow the namespace, node,
   Pod, PVC, database cluster or controller variable.
6. Use panel inspection or Explore only after the overview identifies the
   affected signal. Preserve `cluster` and resource identity in ad-hoc queries.

## Diagnostic paths

| Symptom | Dashboard path | Confirm with |
| --- | --- | --- |
| Workload unavailable or Pending | Cluster and Workloads → Pod and Container Diagnostics | readiness, scheduling, owner, restarts, CPU/memory and limits |
| Node slow or unstable | Node Diagnostics → Pod and Container Diagnostics | CPU/load/PSI, memory, filesystem, disk latency, network errors, top workload |
| Kubernetes API slow | K3s and etcd → Node Diagnostics | API rate/errors/duration, scheduler, etcd leader/storage latency, control-plane node pressure |
| DNS or ingress errors | DNS and Networking → Collection and Metrics Backend | CoreDNS response codes, Traefik service errors/duration, scrape freshness |
| PVC or Longhorn issue | Storage and Longhorn → Node Diagnostics | logical PVC use, Longhorn state/robustness, physical allocation, node disk behavior |
| PostgreSQL or backup issue | PostgreSQL and Backups → Storage and Longhorn | instance readiness, SQL collector, replication, WAL, latest successful backup, PVC health |
| Certificate/controller issue | Controllers and Certificates → Collection and Metrics Backend | certificate namespace/name, reconciliation errors, workqueue and target freshness |
| Missing or contradictory values | Collection and Metrics Backend | target health, sample age, Remote Write queue, backend read-only/disk/query state |

## Reading states correctly

- Green, amber and red are explicit status states.
- Yellow and orange on quantitative charts are visual emphasis, not alerts.
- `N/A` is not healthy. It means no trustworthy value is available.
- A zero finding is meaningful only when the dashboard observed the underlying
  resource inventory.
- Historical Pod phase and termination panels show sampled state. They are not
  a replacement for the later Loki event and log history.
- Coarse p95 values come from retained histogram buckets. Do not infer precise
  p99 latency from them.

## Daily review

Open **Daily Review** without changing its default range. It uses the
previous completed browser-local day and has automatic refresh disabled.

Review target coverage, Pod restart increases, API/DNS/ingress errors, etcd
leader changes, storage findings, backup freshness and certificate lifetime.
When sharing an investigation, convert the selected range to absolute start and
end timestamps so the link remains reproducible.

## Capacity review

Open **Capacity and Reliability** weekly. Start with seven days, then use
30 or 90 days only when the collection history covers that period. Compare:

- node and namespace CPU/memory trends
- logical PVC use and Longhorn physical allocation separately
- VictoriaMetrics data size, free space and write-stop reserve
- ingestion volume and time-series churn
- current backup freshness

Treat growth as an estimate. Expansion, compaction, retention and workload
changes can invalidate a linear trend.

## No data or stale data

1. Clear overly narrow dashboard variables and select one cluster.
2. Confirm the time range includes recent samples.
3. Open **Collection and Metrics Backend** and locate the affected job.
4. Check target `up`, scrape duration, Remote Write sample age, pending/retried
   samples and VictoriaMetrics read-only/free-space state.
5. Compare the exact metric in Explore using datasource **Monitoring Metrics**.
6. If only an optional hardware or controller metric is absent, keep the panel
   at `N/A`. Do not fabricate zero or broaden collection without a concrete use.

## Updating dashboards

Edit `Applications/MonitoringGrafana/scripts/build_dashboards.py`, then run:

```bash
python3 Applications/MonitoringGrafana/scripts/build_dashboards.py
python3 -m unittest discover -s tests/monitoring -v
```

Render and review the target Grafana overlay before deployment. Keep dashboard
UIDs, panel IDs and datasource UID stable. Do not edit provisioned dashboards in
the Grafana UI because Git is the source of truth.
