#!/usr/bin/env python3
"""Build the two OSS log dashboards using the established monitoring theme."""
import copy
import json
from pathlib import Path

from build_dashboards import build, chart, stat, table, variable

OUTPUT = Path(__file__).resolve().parents[1] / "components/_dashboards/log-dashboards"
LOKI = {"type": "loki", "uid": "monitoring-logs"}


def log_variable(name, selector):
    query = f"label_values({selector}, {name})"
    result = variable(name, "", name)
    result.update(datasource=LOKI, definition=query, query=query, refresh=2)
    if name in ("cluster", "source"):
        result["allValue"] = ".+"
    return result


def log_query(panel, expr, legend="", instant=False):
    result = copy.deepcopy(panel)
    result["datasource"] = LOKI
    result["targets"] = [{"datasource": LOKI, "editorMode": "code", "expr": expr,
                          "legendFormat": legend, "queryType": "instant" if instant else "range",
                          "refId": "A", "maxLines": 500}]
    return result


def logs(title, expr, description):
    return {
        "type": "logs", "title": title, "description": description,
        "datasource": LOKI, "gridPos": {"h": 13, "w": 24, "x": 0, "y": 0},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"refId": "A", "datasource": LOKI, "editorMode": "code", "expr": expr,
                     "queryType": "range", "maxLines": 500}],
        "options": {"showTime": True, "showLabels": False, "showCommonLabels": False,
                    "wrapLogMessage": True, "prettifyLogMessage": True, "enableLogDetails": True,
                    "dedupStrategy": "none", "sortOrder": "Descending"},
    }


SELECTOR = '{cluster=~"$cluster",source=~"$source",node=~"$node",namespace=~"$namespace",workload=~"$workload",container=~"$container"}'
FILTER = ' |= ${search:doublequote}'
# Pod logs are deliberately kept as their original lines. `unpack` assumes every
# entry is valid packed JSON, which is not true for interrupted or malformed CRI
# records and makes a whole Loki query fail with JSONParserErr.
POD = '{cluster=~"$cluster",source="pod",node=~"$node",namespace=~"$namespace",workload=~"$workload",container=~"$container"}'
HOST = '{cluster=~"$cluster",source=~"journal|host-file|containerd",node=~"$node"}'
EVENTS = '{cluster=~"$cluster",source="event",namespace=~"$namespace"}'


def explorer():
    vars = [log_variable("source", '{cluster=~"$cluster"}'),
            log_variable("node", '{cluster=~"$cluster",source=~"$source"}'),
            log_variable("namespace", '{cluster=~"$cluster",source="pod"}'),
            log_variable("workload", '{cluster=~"$cluster",source="pod",namespace=~"$namespace"}'),
            log_variable("container", '{cluster=~"$cluster",source="pod",namespace=~"$namespace",workload=~"$workload"}'),
            {"name": "search", "label": "Contains", "type": "textbox", "query": "", "current": {"text": "", "value": ""}, "skipUrlSync": False}]
    spec = {
        "uid": "mon-log-explorer", "title": "Log Explorer", "from": "now-1h", "refresh": "1m", "category_title": "Log", "category_tag": "logs", "vars": vars,
        "purpose": "Find operational incidents across clusters. The main views follow all filters. Dedicated Pod, Host and Event views use their own source and applicable filters. Quiet services may have no logs. SQL and data-bearing records are intentionally excluded. Each log view is capped at 500 lines, narrow the time range or use Explore for more.",
        "panels": [
            log_query(stat("Observed log clusters", "", "Clusters emitting selected logs, not an expected-inventory health check.", threshold="warm"), f'count(sum by (cluster) (count_over_time({SELECTOR}{FILTER}[$__range])))', instant=True),
            log_query(stat("Selected log entries", "", "Entries matching the filters in the selected range. No result means no observed matching entries.", threshold="warm"), f'sum(count_over_time({SELECTOR}{FILTER}[$__range]))', instant=True),
            log_query(stat("Error keyword matches", "", "Heuristic error/fatal/panic text matches. This is not a complete severity classification.", threshold="warning"), f'sum(count_over_time({SELECTOR}{FILTER} |~ "(?i)error|fatal|panic" [$__range]))', instant=True),
            log_query(stat("Warning keyword matches", "", "Heuristic warn text matches. Not all applications use common severity fields.", threshold="warning"), f'sum(count_over_time({SELECTOR}{FILTER} |~ "(?i)warn" [$__range]))', instant=True),
            log_query(chart("Log volume by source", [], "Selected entries per second. Gaps remain missing, not zero.", "logs/s"), f'sum by (cluster, source) (rate({SELECTOR}{FILTER}[$__auto]))', "{{cluster}} {{source}}"),
            log_query(chart("Error keyword rate", [], "Text matches per second. Use individual records to confirm the cause.", "logs/s"), f'sum by (cluster) (rate({SELECTOR}{FILTER} |~ "(?i)error|fatal|panic" [$__auto]))', "{{cluster}}"),
            logs("Selected logs", SELECTOR + FILTER, "All active filters apply. Expand a row for its labels and packed Pod identity."),
            log_query(table("Most active workloads", "", "Top 15 Pod workloads in the selected range, not a count of unique errors."), f'topk(15, sum by (cluster, namespace, workload) (count_over_time({POD}{FILTER}[$__range])))', instant=True),
            logs("Pod diagnostics", POD + FILTER, "Pod-only view of sanitized original messages. Expand records to inspect available labels. No JSON unpacking is required."),
            logs("Host and K3s journal", HOST + FILTER, "Host view follows cluster, node and search. Namespace/workload/container/source selections do not constrain it."),
            logs("Kubernetes Events", EVENTS + FILTER, "Event view follows cluster, namespace and search. Events are diagnostic records, not API audit logs."),
        ],
    }
    dashboard = build(spec)
    dashboard["templating"]["list"][0] = log_variable("cluster", '{source=~".+"}')
    # A Loki explorer must not claim scrape freshness as log-delivery freshness.
    dashboard["panels"][1] = log_query(stat("Latest selected log", "", "Timestamp of the latest matching record in the selected range. Silence alone does not indicate failure.", "dateTimeAsIso", "warm"), f'max(max_over_time({SELECTOR}{FILTER} | label_format observed_ts="{{{{ __timestamp__ | unixEpoch }}}}" | unwrap observed_ts | __error__="" [$__range])) * 1000', instant=True)
    dashboard["panels"][1]["id"] = 2
    dashboard["panels"][1]["gridPos"] = {"h": 4, "w": 6, "x": 18, "y": 0}
    return finalize(dashboard)


def pipeline():
    scoped = '{cluster=~"$cluster",job=~"alloy|alloy-logs"}'
    spec = {
        "uid": "mon-log-pipeline", "title": "Log Pipeline Health", "from": "now-1h", "refresh": "1m", "category_title": "Log", "category_tag": "logs", "vars": [],
        "purpose": "Check collection, delivery and the central Loki backend. Agent panels follow the cluster filter. Central backend and storage panels show the shared backend across all clusters. N/A is missing telemetry. Host-local tail positions survive replacement, but the bounded 512 MiB WAL does not.",
        "panels": [
            stat("Log collectors not Ready", 'sum(kube_daemonset_status_desired_number_scheduled{cluster=~"$cluster",namespace="monitoring-agent",daemonset="alloy-logs"}) - sum(kube_daemonset_status_number_ready{cluster=~"$cluster",namespace="monitoring-agent",daemonset="alloy-logs"})', "Desired minus ready log collectors. Compare with per-cluster coverage below.", threshold="critical"),
            stat("Backend targets down", 'count(up{job=~"loki|logs-vmauth"}) - sum(up{job=~"loki|logs-vmauth"})', "Central Loki and auth proxy targets currently unreachable. Missing series remain N/A.", threshold="critical"),
            stat("Delivery drops last 5m", f'sum(increase(loki_write_dropped_entries_total{scoped}[5m]))', "New entries abandoned in the last five minutes. Historical drops remain visible in the range table below.", threshold="critical"),
            stat("Loki rejected entries last 5m", 'sum(increase(loki_discarded_samples_total{job="loki"}[5m]))', "New shared-backend rejections in the last five minutes. Range totals remain grouped by reason below.", threshold="critical"),
            chart("Agent delivery rate", [(f'sum by (cluster) (rate(loki_write_sent_entries_total{scoped}[$__rate_interval]))', "{{cluster}}")], "Successfully sent entries per second.", "logs/s"),
            chart("Retries and delivery drops", [(f'sum by (cluster) (rate(loki_write_batch_retries_total{scoped}[$__rate_interval]))', "retries {{cluster}}"), (f'sum by (cluster) (rate(loki_write_dropped_entries_total{scoped}[$__rate_interval]))', "drops {{cluster}}")], "Sustained retries indicate connectivity, authentication or backend capacity issues.", "ops"),
            chart("Deliberate exclusions", [('sum by (cluster, reason) (rate(loki_process_dropped_lines_total{cluster=~"$cluster",job="alloy-logs"}[$__rate_interval]))', "{{cluster}} {{reason}}")], "Privacy/access exclusions are intentional. An unexpected increase still deserves investigation.", "logs/s"),
            chart("Secrets redacted", [('sum by (cluster) (rate(loki_secretfilter_secrets_redacted_total{cluster=~"$cluster",job=~"alloy|alloy-logs"}[$__rate_interval]))', "{{cluster}}")], "Patterns recognized by the secret filter. Zero does not prove that arbitrary text is safe.", "ops"),
            table("Collector coverage by cluster", 'sum by (cluster) (kube_daemonset_status_number_ready{namespace="monitoring-agent",daemonset="alloy-logs",cluster=~"$cluster"}) / sum by (cluster) (kube_daemonset_status_desired_number_scheduled{namespace="monitoring-agent",daemonset="alloy-logs",cluster=~"$cluster"})', "Ready/desired collectors. Missing cluster inventory is unknown.", "percentunit", "ready"),
            table("Collector target health", 'min by (cluster, node, instance) (up{cluster=~"$cluster",job="alloy-logs"})', "Each observed log collector's metrics endpoint.", threshold="ready"),
            chart("Loki received bytes", [('sum(rate(loki_distributor_bytes_received_total{job="loki"}[$__rate_interval]))', "received")], "Shared backend ingestion, before long-term storage compression.", "Bps"),
            chart("Loki HTTP errors", [('sum by (route, status_code) (rate(loki_request_duration_seconds_count{job="loki",status_code=~"4..|5.."}[$__rate_interval]))', "{{route}} {{status_code}}")], "Shared backend request failures. Not all errors indicate data loss.", "reqps"),
            table("Rejections by reason", 'sum by (reason) (increase(loki_discarded_samples_total{job="loki"}[$__range]))', "Missing rows can mean no rejection series has been created yet.", threshold="warning"),
            table("Delivery drops by cluster and reason", f'sum by (cluster, reason) (increase(loki_write_dropped_entries_total{scoped}[$__range]))', "Historical drops in the selected range. These remain visible after delivery has recovered and roll out when the time window advances.", threshold="warning"),
            stat("Compactor running", 'max(loki_boltdb_shipper_compactor_running{job="loki"})', "Compactor leadership/running state in the single-binary TSDB backend.", threshold="ready", width=8),
            stat("Last retention success age", 'time() - max(loki_compactor_apply_retention_last_successful_run_timestamp_seconds{job="loki"} > 0)', "Age of a completed retention pass. N/A is expected before the first successful pass.", "s", "warm", width=8),
            stat("Loki PVC used", '100 * max(kubelet_volume_stats_used_bytes{namespace="monitoring-logs",persistentvolumeclaim="loki-data-loki-0"}) / max(kubelet_volume_stats_capacity_bytes{namespace="monitoring-logs",persistentvolumeclaim="loki-data-loki-0"})', "Shared backend filesystem usage. 50 GiB initial allocation, expand before it fills.", "percent", "percent", width=8),
            chart("Loki storage growth", [('max(kubelet_volume_stats_used_bytes{namespace="monitoring-logs",persistentvolumeclaim="loki-data-loki-0"})', "used"), ('max(kubelet_volume_stats_capacity_bytes{namespace="monitoring-logs",persistentvolumeclaim="loki-data-loki-0"})', "capacity")], "Includes chunks, index, cache, WAL and compactor data.", "bytes", "60s", 24),
            table("Agent memory / limit", 'max by (cluster, pod) (container_memory_working_set_bytes{cluster=~"$cluster",namespace="monitoring-agent",container="alloy-logs"}) / on (cluster, pod) max by (cluster, pod) (kube_pod_container_resource_limits{cluster=~"$cluster",namespace="monitoring-agent",container="alloy-logs",resource="memory"}) * 100', "Zero requests do not reserve memory. The limit still applies.", "percent", "percent"),
            table("Agent restarts", 'sum by (cluster, pod) (increase(kube_pod_container_status_restarts_total{cluster=~"$cluster",namespace="monitoring-agent",container="alloy-logs"}[$__range]))', "Inspect OOM, eviction and configuration errors when restarts increase.", threshold="warning"),
        ],
    }
    return finalize(build(spec))


def finalize(dashboard):
    dashboard["tags"] = ["monitoring", "logs"]
    return dashboard


def dashboards():
    return {"log-explorer.json": explorer(), "log-pipeline-health.json": pipeline()}


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, dashboard in dashboards().items():
        (OUTPUT / name).write_text(json.dumps(dashboard, indent=2) + "\n")
        print(name)
