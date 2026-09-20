#!/usr/bin/env python3
"""Build the canonical Grafana monitoring dashboards with the Python stdlib."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "components" / "_dashboards" / "dashboards"
DATASOURCE = {"type": "prometheus", "uid": "monitoring-metrics"}
REFRESH_INTERVALS = ["1m", "5m", "15m", "30m", "1h"]
VM_PVC_LABELS = 'namespace="monitoring-metrics",persistentvolumeclaim=~"victoriametrics-data-victoriametrics-.*"'
VM_PVC_CAPACITY = f'max(kubelet_volume_stats_capacity_bytes{{{VM_PVC_LABELS}}})'
VM_PVC_USED = f'max(kubelet_volume_stats_used_bytes{{{VM_PVC_LABELS}}})'
VM_WRITE_STOP = f'{VM_PVC_CAPACITY} - max(vm_free_disk_space_limit_bytes{{job="victoriametrics"}})'


def query(expr, legend="", interval="30s", instant=False, fmt="time_series"):
    return {
        "datasource": DATASOURCE,
        "editorMode": "code",
        "expr": expr,
        "format": fmt,
        "instant": instant,
        "interval": interval,
        "legendFormat": legend,
        "range": not instant,
        "refId": "",
    }


def thresholds(kind="status"):
    if kind == "percent":
        values = [(None, "green"), (75, "#FFB357"), (90, "red")]
    elif kind == "availability":
        values = [(None, "red"), (95, "#FFB357"), (99.5, "green")]
    elif kind == "error_ratio":
        values = [(None, "green"), (0.001, "#FFB357"), (0.01, "red")]
    elif kind == "free":
        values = [(None, "red"), (5, "#FFB357"), (15, "green")]
    elif kind == "age":
        values = [(None, "green"), (90, "#FFB357"), (180, "red")]
    elif kind == "days":
        values = [(None, "red"), (7, "#FFB357"), (14, "green")]
    elif kind in {"status", "critical"}:
        values = [(None, "green"), (1, "red")]
    elif kind == "warning":
        values = [(None, "green"), (1, "#FFB357")]
    elif kind == "finding":
        values = [(None, "green"), (1, "#FFB357"), (5, "red")]
    elif kind == "warning_rate":
        values = [(None, "green"), (0.001, "#FFB357"), (1, "red")]
    elif kind == "ready":
        values = [(None, "red"), (1, "green")]
    else:
        values = [(None, "#8AB8FF"), (50, "#5794F2"), (85, "#1F60C4")]
    return {"mode": "absolute", "steps": [{"color": color, "value": value} for value, color in values]}


def targets(items):
    result = []
    for index, item in enumerate(items):
        target = dict(item)
        target["refId"] = chr(ord("A") + index)
        result.append(target)
    return result


def panel(kind, title, items, description, unit="short", width=12, height=8, threshold="warm"):
    base = {
        "datasource": DATASOURCE,
        "description": description,
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "fixed", "fixedColor": "#5794F2"},
                "custom": {},
                "decimals": 2,
                "mappings": [],
                "noValue": "N/A",
                "thresholds": thresholds(threshold),
                "unit": unit,
            },
            "overrides": [],
        },
        "gridPos": {"h": height, "w": width, "x": 0, "y": 0},
        "id": 0,
        "options": {},
        "targets": targets(items),
        "title": title,
        "type": kind,
    }
    if kind == "timeseries":
        base["fieldConfig"]["defaults"]["color"] = {"mode": "palette-classic-by-name"}
        base["fieldConfig"]["defaults"]["custom"] = {
            "axisCenteredZero": False,
            "axisColorMode": "text",
            "axisLabel": "",
            "axisPlacement": "auto",
            "drawStyle": "line",
            "fillOpacity": 18,
            "gradientMode": "opacity",
            "hideFrom": {"legend": False, "tooltip": False, "viz": False},
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "pointSize": 3,
            "scaleDistribution": {"type": "linear"},
            "showPoints": "never",
            "spanNulls": False,
            "stacking": {"group": "A", "mode": "none"},
            "thresholdsStyle": {"mode": "off"},
        }
        base["options"] = {
            "legend": {"calcs": ["lastNotNull", "max"], "displayMode": "table", "placement": "bottom", "showLegend": True},
            "tooltip": {"hideZeros": False, "mode": "multi", "sort": "desc"},
        }
    elif kind == "stat":
        base["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        base["options"] = {
            "colorMode": "background_solid",
            "graphMode": "area",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showPercentChange": False,
            "textMode": "auto",
            "wideLayout": True,
        }
    elif kind == "table":
        base["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        base["fieldConfig"]["defaults"]["custom"] = {
            "align": "auto",
            "cellOptions": {"type": "auto"},
            "filterable": True,
            "inspect": False,
        }
        base["options"] = {
            "cellHeight": "sm",
            "footer": {"countRows": False, "fields": "", "reducer": ["sum"], "show": False},
            "showHeader": True,
            "sortBy": [{"desc": True, "displayName": "Value"}],
        }
    elif kind == "bargauge":
        base["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        base["options"] = {
            "displayMode": "gradient",
            "legend": {"calcs": [], "displayMode": "list", "placement": "bottom", "showLegend": False},
            "maxVizHeight": 300,
            "minVizHeight": 16,
            "minVizWidth": 8,
            "namePlacement": "auto",
            "orientation": "horizontal",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showUnfilled": True,
            "sizing": "auto",
            "text": {},
            "valueMode": "color",
        }
    return base


def stat(title, expr, description, unit="short", threshold="warm", interval="30s", width=6):
    result = panel("stat", title, [query(expr, interval=interval, instant=True)], description, unit, width, 4, threshold)
    if unit == "short":
        result["fieldConfig"]["defaults"]["decimals"] = 0
    return result


def chart(title, items, description, unit="short", interval="30s", width=12):
    return panel("timeseries", title, [query(expr, legend, interval) for expr, legend in items], description, unit, width, 8)


def table(title, expr, description, unit="short", threshold="warm", interval="60s", width=24, sort_desc=True):
    result = panel("table", title, [query(expr, interval=interval, instant=True, fmt="table")], description, unit, width, 8, threshold)
    result["options"]["sortBy"] = [{"desc": sort_desc, "displayName": "Value"}]
    return result


def gauge(title, expr, description, unit="percent", threshold="percent", interval="30s", width=12, legend="{{cluster}} {{namespace}} {{node}} {{pod}} {{persistentvolumeclaim}}", height=7):
    return panel("bargauge", title, [query(expr, legend, interval, True)], description, unit, width, height, threshold)


def mapped_table(title, expr, description, mappings, unit="short", threshold="warm", interval="60s", width=24, sort_desc=True):
    result = table(title, expr, description, unit, threshold, interval, width, sort_desc)
    result["fieldConfig"]["defaults"]["mappings"] = [{
        "options": {str(value): {"text": label} for value, label in mappings.items()},
        "type": "value",
    }]
    return result


def variable(name, metric, label, dependency="", multi=True):
    selector = f'{{{dependency}}}' if dependency else ""
    expression = f"label_values({metric}{selector}, {label})"
    return {
        "allValue": ".*",
        "current": {"selected": True, "text": "All", "value": "$__all"},
        "datasource": DATASOURCE,
        "definition": expression,
        "description": f"Filter by {name}",
        "hide": 0,
        "includeAll": True,
        "label": name.replace("_", " ").title(),
        "multi": multi,
        "name": name,
        "options": [],
        "query": {"query": expression, "refId": "StandardVariableQuery"},
        "refresh": 1,
        "regex": "",
        "skipUrlSync": False,
        "sort": 1,
        "type": "query",
    }


def intro(text):
    return {
        "datasource": {"type": "datasource", "uid": "grafana"},
        "description": "Dashboard purpose, navigation guidance and data-state semantics.",
        "fieldConfig": {"defaults": {}, "overrides": []},
        "gridPos": {"h": 4, "w": 18, "x": 0, "y": 0},
        "id": 0,
        "options": {
            "code": {"language": "plaintext", "showLineNumbers": False, "showMiniMap": False},
            "content": text + "\n\nGreen, amber and red indicate explicit status. Blue is quantitative emphasis. N/A means missing or unsupported data, never healthy zero.",
            "mode": "markdown",
        },
        "pluginVersion": "13.2.2",
        "title": "About this dashboard",
        "transparent": True,
        "type": "text",
    }


def dashboard_links(category_title, category_tag):
    common = {
        "asDropdown": True,
        "icon": "external link",
        "includeVars": True,
        "keepTime": True,
        "targetBlank": False,
        "type": "dashboards",
    }
    return [
        {
            **common,
            "tags": ["monitoring"],
            "title": "Monitoring dashboards",
            "tooltip": "Open another monitoring dashboard",
        },
        {
            **common,
            "tags": [category_tag],
            "title": f"{category_title} reports",
            "tooltip": f"Open another {category_title.lower()} report",
        },
    ]


FRESHNESS = lambda: stat(
    "Oldest observed target sample",
    'max(clamp_min(time() - timestamp(up{cluster=~"$cluster"}), 0))',
    "Age of the oldest currently returned target sample. A missing result is N/A.",
    "s", "age", "15s", 6,
)


DASHBOARDS = [
    {
        "file": "00-overview.json", "uid": "mon-overview", "title": "Overview", "from": "now-1h", "refresh": "1m",
        "purpose": "Start here to find the cluster or subsystem that needs attention, then follow the linked specialist dashboard.",
        "vars": [],
        "panels": [
            stat("Observed clusters", 'count(count by (cluster) (up{cluster=~"$cluster"}))', "Clusters with at least one current target. Green confirms observed inventory, not that every expected cluster exists.", threshold="ready", width=6),
            stat("Unavailable targets", 'count(up{cluster=~"$cluster"}) - sum(up{cluster=~"$cluster"})', "Targets currently reporting up=0.", threshold="critical", width=6),
            stat("Nodes not Ready", 'count(kube_node_status_condition{cluster=~"$cluster",condition="Ready",status="true"}) - sum(kube_node_status_condition{cluster=~"$cluster",condition="Ready",status="true"})', "Kubernetes nodes without a current Ready=true state.", threshold="critical", width=6),
            stat("Unavailable workload replicas", 'sum(clamp_min(kube_deployment_spec_replicas{cluster=~"$cluster"} - kube_deployment_status_replicas_available{cluster=~"$cluster"}, 0))', "Desired Deployment replicas minus available replicas.", threshold="critical", width=6),
            chart("Cluster CPU utilization", [('100 * (1 - avg by (cluster) (rate(node_cpu_seconds_total{job="node-exporter",cluster=~"$cluster",mode="idle"}[$__rate_interval])))', "{{cluster}}")], "Average host CPU busy time by cluster.", "percent", "15s"),
            chart("Cluster memory utilization", [('100 * (1 - sum by (cluster) (node_memory_MemAvailable_bytes{job="node-exporter",cluster=~"$cluster"}) / sum by (cluster) (node_memory_MemTotal_bytes{job="node-exporter",cluster=~"$cluster"}))', "{{cluster}}")], "Available-memory based host utilization by cluster.", "percent", "30s"),
            table("Targets by cluster and job", 'count by (cluster, job) (up{cluster=~"$cluster"}) - sum by (cluster, job) (up{cluster=~"$cluster"})', "Zero means every observed target in the group is up.", "short", "critical"),
            table("Unavailable workload replicas", 'sum by (cluster, namespace, deployment) (clamp_min(kube_deployment_spec_replicas{cluster=~"$cluster"} - kube_deployment_status_replicas_available{cluster=~"$cluster"}, 0))', "Deployment replica shortages, retaining cluster and namespace identity.", "short", "critical"),
            table("PVC utilization", '100 * max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes{job="kubelet",cluster=~"$cluster"}) / max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{job="kubelet",cluster=~"$cluster"})', "Logical filesystem usage. Longhorn physical use is separate.", "percent", "percent"),
            table("Certificate lifetime", '(min by (cluster, exported_namespace, name) (certmanager_certificate_expiration_timestamp_seconds{cluster=~"$cluster"}) - time()) / 86400', "Days remaining in the certificate object's exported namespace.", "d", "days", sort_desc=False),
        ],
    },
    {
        "file": "10-cluster.json", "uid": "mon-cluster", "title": "Cluster and Workloads", "from": "now-1h", "refresh": "1m",
        "purpose": "Inspect Kubernetes capacity, scheduling and workload availability for a selected cluster and namespace.",
        "vars": [variable("namespace", "kube_namespace_status_phase", "namespace", 'cluster=~"$cluster"')],
        "panels": [
            stat("Ready nodes", 'sum(kube_node_status_condition{cluster=~"$cluster",condition="Ready",status="true"})', "Ready nodes in scope.", threshold="ready"),
            stat("Pending Pods", 'sum(kube_pod_status_phase{cluster=~"$cluster",namespace=~"$namespace",phase="Pending"})', "Current Pending Pods. One to four is a warning, five or more is critical.", threshold="finding"),
            stat("Failed or Unknown Pods", 'sum(kube_pod_status_phase{cluster=~"$cluster",namespace=~"$namespace",phase=~"Failed|Unknown"})', "Current Failed or Unknown Pods.", threshold="critical"),
            stat("Unschedulable Pods", 'sum(kube_pod_status_scheduled{cluster=~"$cluster",namespace=~"$namespace",condition="false"})', "Pods whose current scheduled condition is false. One to four is a warning, five or more is critical.", threshold="finding"),
            chart("CPU used and allocatable", [
                ('sum by (cluster) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",container!="",container!="POD"}[$__rate_interval]))', "used {{cluster}}"),
                ('sum by (cluster) (kube_node_status_allocatable{cluster=~"$cluster",resource="cpu"})', "allocatable {{cluster}}"),
            ], "Actual container CPU versus allocatable cores.", "cores", "15s"),
            chart("Memory used and allocatable", [
                ('sum by (cluster) (container_memory_working_set_bytes{cluster=~"$cluster",container!="",container!="POD"})', "used {{cluster}}"),
                ('sum by (cluster) (kube_node_status_allocatable{cluster=~"$cluster",resource="memory"})', "allocatable {{cluster}}"),
            ], "Container working set versus allocatable memory.", "bytes", "30s"),
            table("Namespace CPU", 'topk(10, sum by (cluster, namespace) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",namespace=~"$namespace",container!="",container!="POD"}[$__rate_interval])))', "Top namespaces by actual CPU use.", "cores", interval="15s"),
            table("Namespace memory", 'topk(10, sum by (cluster, namespace) (container_memory_working_set_bytes{cluster=~"$cluster",namespace=~"$namespace",container!="",container!="POD"}))', "Top namespaces by working-set memory.", "bytes"),
            table("Deployment availability gap", 'sum by (cluster, namespace, deployment) (clamp_min(kube_deployment_spec_replicas{cluster=~"$cluster",namespace=~"$namespace"} - kube_deployment_status_replicas_available{cluster=~"$cluster",namespace=~"$namespace"}, 0))', "Desired minus available Deployment replicas.", "short", "critical"),
            table("StatefulSet readiness gap", 'sum by (cluster, namespace, statefulset) (clamp_min(kube_statefulset_replicas{cluster=~"$cluster",namespace=~"$namespace"} - kube_statefulset_status_replicas_ready{cluster=~"$cluster",namespace=~"$namespace"}, 0))', "Desired minus ready StatefulSet replicas.", "short", "critical"),
            table("DaemonSet unavailable", 'sum by (cluster, namespace, daemonset) (kube_daemonset_status_number_unavailable{cluster=~"$cluster",namespace=~"$namespace"})', "Unavailable DaemonSet Pods.", "short", "critical"),
            table("Failed Jobs and suspended CronJobs", 'label_replace(sum by (cluster, namespace) (kube_job_status_failed{cluster=~"$cluster",namespace=~"$namespace"}), "finding", "failed jobs", "", "") or label_replace(sum by (cluster, namespace) (kube_cronjob_spec_suspend{cluster=~"$cluster",namespace=~"$namespace"}), "finding", "suspended CronJobs", "", "")', "Current failed Jobs and explicitly suspended CronJobs as separate findings. Suspended schedules can be intentional.", "short", "warning"),
            stat("HPA replica gap", 'sum(clamp_min(kube_horizontalpodautoscaler_status_desired_replicas{cluster=~"$cluster",namespace=~"$namespace"} - kube_horizontalpodautoscaler_status_current_replicas{cluster=~"$cluster",namespace=~"$namespace"}, 0)) or (0 * count(kube_namespace_status_phase{cluster=~"$cluster",namespace=~"$namespace",phase="Active"}))', "Total desired minus current HPA replicas. A verified zero also covers namespaces with no configured HPA. N/A remains possible when namespace inventory is missing.", threshold="warning", width=24),
            table("Pod disruption budgets", 'min by (cluster, namespace, poddisruptionbudget) (kube_poddisruptionbudget_status_pod_disruptions_allowed{cluster=~"$cluster",namespace=~"$namespace"})', "Current allowed disruptions. Zero may be intentional and needs workload context.", "short", "warm"),
            table("Ready EndpointSlice endpoints", 'sum by (cluster, namespace, service) (kube_endpointslice_endpoints{cluster=~"$cluster",namespace=~"$namespace",ready="true"})', "Ready service endpoints by cluster, namespace and service.", "short", "warm"),
            gauge("Container CPU request coverage", '100 * count(kube_pod_container_resource_requests{cluster=~"$cluster",namespace=~"$namespace",resource="cpu",unit="core"} > 0) / clamp_min(count(kube_pod_container_info{cluster=~"$cluster",namespace=~"$namespace"}), 1)', "Share of observed regular containers with a positive CPU request.", "percent", "free", "60s", 24),
        ],
    },
    {
        "file": "20-node.json", "uid": "mon-node", "title": "Node Diagnostics", "from": "now-1h", "refresh": "1m",
        "purpose": "Diagnose host saturation, filesystem, disk, network and hardware signals without relying on SMART over USB.",
        "vars": [variable("node", "node_uname_info", "node", 'cluster=~"$cluster"')],
        "panels": [
            stat("Uptime", 'time() - max(node_boot_time_seconds{cluster=~"$cluster",node=~"$node"})', "Time since boot.", "s", "warm"),
            stat("CPU busy", '100 * (1 - avg(rate(node_cpu_seconds_total{cluster=~"$cluster",node=~"$node",mode="idle"}[$__rate_interval])))', "CPU busy percentage.", "percent", "percent", "15s"),
            stat("Memory available", '100 * sum(node_memory_MemAvailable_bytes{cluster=~"$cluster",node=~"$node"}) / sum(node_memory_MemTotal_bytes{cluster=~"$cluster",node=~"$node"})', "Available memory percentage.", "percent", "free"),
            stat("Root filesystem free", '100 * sum(node_filesystem_avail_bytes{cluster=~"$cluster",node=~"$node",mountpoint="/",fstype!~"tmpfs|overlay"}) / sum(node_filesystem_size_bytes{cluster=~"$cluster",node=~"$node",mountpoint="/",fstype!~"tmpfs|overlay"})', "Root filesystem free percentage.", "percent", "free", "60s"),
            chart("CPU by mode", [('100 * avg by (cluster, node, mode) (rate(node_cpu_seconds_total{cluster=~"$cluster",node=~"$node",mode!="idle"}[$__rate_interval]))', "{{cluster}} {{node}} {{mode}}")], "Non-idle CPU modes.", "percent", "15s"),
            chart("Load and CPU pressure", [
                ('node_load1{cluster=~"$cluster",node=~"$node"}', "load1 {{node}}"),
                ('rate(node_pressure_cpu_waiting_seconds_total{cluster=~"$cluster",node=~"$node"}[$__rate_interval])', "CPU PSI waiting {{node}}"),
            ], "Load average and CPU pressure. Units differ, so compare shape and inspect values.", "short", "15s"),
            chart("Memory and I/O pressure", [
                ('sum by (cluster, node, __name__) (rate({__name__=~"node_pressure_memory_waiting_seconds_total|node_pressure_io_waiting_seconds_total|node_pressure_io_stalled_seconds_total",cluster=~"$cluster",node=~"$node"}[$__rate_interval]))', "{{__name__}} {{node}}"),
            ], "Linux PSI fractions. Unsupported signals remain N/A.", "percentunit", "15s"),
            chart("Disk throughput", [
                ('sum by (cluster, node, device) (rate(node_disk_read_bytes_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval]))', "read {{node}} {{device}}"),
                ('sum by (cluster, node, device) (rate(node_disk_written_bytes_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval]))', "write {{node}} {{device}}"),
            ], "Physical-device throughput.", "Bps", "15s"),
            chart("Disk average operation latency", [
                ('sum by (cluster, node, device) (rate(node_disk_read_time_seconds_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval])) / clamp_min(sum by (cluster, node, device) (rate(node_disk_reads_completed_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval])), 0.000001)', "read {{node}} {{device}}"),
                ('sum by (cluster, node, device) (rate(node_disk_write_time_seconds_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval])) / clamp_min(sum by (cluster, node, device) (rate(node_disk_writes_completed_total{cluster=~"$cluster",node=~"$node",device!~"loop.*|ram.*"}[$__rate_interval])), 0.000001)', "write {{node}} {{device}}"),
            ], "Mean service time per completed operation, not a percentile.", "s", "15s"),
            chart("Network throughput", [
                ('sum by (cluster, node, device) (rate(node_network_receive_bytes_total{cluster=~"$cluster",node=~"$node",device!~"lo|veth.*|flannel.*|cni.*"}[$__rate_interval]))', "receive {{node}} {{device}}"),
                ('sum by (cluster, node, device) (rate(node_network_transmit_bytes_total{cluster=~"$cluster",node=~"$node",device!~"lo|veth.*|flannel.*|cni.*"}[$__rate_interval]))', "transmit {{node}} {{device}}"),
            ], "Host interface traffic excluding common virtual interfaces.", "Bps", "15s"),
            table("Network errors and drops", 'sum by (cluster, node, device) (rate(node_network_receive_errs_total{cluster=~"$cluster",node=~"$node"}[$__rate_interval]) + rate(node_network_transmit_errs_total{cluster=~"$cluster",node=~"$node"}[$__rate_interval]) + rate(node_network_receive_drop_total{cluster=~"$cluster",node=~"$node"}[$__rate_interval]) + rate(node_network_transmit_drop_total{cluster=~"$cluster",node=~"$node"}[$__rate_interval]))', "Per-second host interface errors and drops. Small nonzero rates are warnings.", "ops", "warning_rate", "15s"),
            chart("Host filesystems: used, available and capacity", [
                ('max by (cluster, node, mountpoint, device) (node_filesystem_size_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"} - node_filesystem_avail_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"})', "used {{cluster}} {{node}} {{mountpoint}}"),
                ('max by (cluster, node, mountpoint, device) (node_filesystem_avail_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"})', "available {{cluster}} {{node}} {{mountpoint}}"),
                ('max by (cluster, node, mountpoint, device) (node_filesystem_size_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"})', "capacity {{cluster}} {{node}} {{mountpoint}}"),
            ], "Host mounts comparable to df -h. Used is capacity minus filesystem-available bytes. Temporary and overlay filesystems are excluded.", "bytes", "60s", 24),
            table("Filesystem utilization", '100 * (1 - max by (cluster, node, mountpoint, device) (node_filesystem_avail_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"}) / max by (cluster, node, mountpoint, device) (node_filesystem_size_bytes{cluster=~"$cluster",node=~"$node",fstype!~"tmpfs|overlay"}))', "Filesystem utilization by node and mountpoint. Read-only and device-error metrics remain separate evidence in Explore.", "percent", "percent"),
            table("Top Pods on selected nodes", 'topk(10, sum by (cluster, node, namespace, pod) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",node=~"$node",container!="",container!="POD"}[$__rate_interval])))', "Top Pod CPU consumers on the selected node scope.", "cores", "warm", "15s"),
            table("Temperatures and voltage alarms", 'max by (cluster, node, chip, sensor) (node_hwmon_temp_celsius{cluster=~"$cluster",node=~"$node"})', "Available temperature sensors. Voltage alarm metrics are hardware-dependent and should be checked in Explore when present.", "celsius"),
            stat("Failed host services", 'sum(node_systemd_unit_state{cluster=~"$cluster",node=~"$node",state="failed"} == 1) or (0 * count(node_systemd_unit_state{cluster=~"$cluster",node=~"$node"}))', "Failed systemd units. Zero is emitted only while systemd collector telemetry is present.", threshold="critical", width=24),
            table("Host reboot required", 'homelab_host_reboot_required{cluster=~"$cluster",node=~"$node"}', "Pending reboot flag from host maintenance collection.", threshold="warning"),
            table("Maintenance telemetry age", 'time() - homelab_host_maintenance_last_run_unixtime{cluster=~"$cluster",node=~"$node"}', "Collector runs every five minutes. Growing age indicates stale maintenance telemetry.", "s"),
            table("APT metadata update age", 'homelab_host_apt_update_stamp_age_seconds{cluster=~"$cluster",node=~"$node"} >= 0', "Age of the update-success stamp, not proof that security patches are installed. Missing stamps (-1) are excluded.", "s"),
        ],
    },
    {
        "file": "30-pod.json", "uid": "mon-pod", "title": "Pod and Container Diagnostics", "from": "now-1h", "refresh": "1m",
        "purpose": "Explain Pod availability, resource use, throttling, restarts and container termination reasons.",
        "vars": [
            variable("namespace", "kube_namespace_status_phase", "namespace", 'cluster=~"$cluster"'),
            variable("pod", "kube_pod_info", "pod", 'cluster=~"$cluster",namespace=~"$namespace"'),
        ],
        "panels": [
            stat("Running Pods", 'sum(kube_pod_status_phase{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",phase="Running"})', "Current Running phase.", threshold="ready"),
            stat("Not-ready containers", 'sum((1 - kube_pod_container_status_ready{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"}) * on(cluster, namespace, pod) group_left() (kube_pod_status_phase{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",phase="Running"} == 1))', "Containers that are not ready inside Pods whose current phase is Running. Completed Jobs are excluded.", threshold="critical"),
            stat("Restarts in range", 'sum(increase(kube_pod_container_status_restarts_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"}[$__range]))', "Counter increase during the selected range. One to four is a warning, five or more is critical.", threshold="finding"),
            stat("OOM events in range", 'sum(increase(container_oom_events_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!=""}[$__range]))', "Observed cgroup OOM events in the selected range.", threshold="critical", interval="15s"),
            chart("Container CPU", [('sum by (cluster, namespace, pod, container) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!="",container!="POD"}[$__rate_interval]))', "{{pod}} {{container}}")], "CPU cores used by each selected container.", "cores", "15s"),
            chart("Container working set and RSS", [
                ('sum by (cluster, namespace, pod, container) (container_memory_working_set_bytes{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!="",container!="POD"})', "working set {{pod}} {{container}}"),
                ('sum by (cluster, namespace, pod, container) (container_memory_rss{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!="",container!="POD"})', "RSS {{pod}} {{container}}"),
            ], "Working set and resident memory.", "bytes", "30s"),
            chart("CPU throttled periods", [('sum by (cluster, namespace, pod, container) (rate(container_cpu_cfs_throttled_periods_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!="",container!="POD"}[$__rate_interval])) / clamp_min(sum by (cluster, namespace, pod, container) (rate(container_cpu_cfs_periods_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",container!="",container!="POD"}[$__rate_interval])), 0.000001)', "{{pod}} {{container}}")], "Fraction of CFS periods throttled. N/A when no quota periods exist.", "percentunit", "15s"),
            chart("Pod network traffic", [
                ('sum by (cluster, namespace, pod) (rate(container_network_receive_bytes_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"}[$__rate_interval]))', "receive {{pod}}"),
                ('sum by (cluster, namespace, pod) (rate(container_network_transmit_bytes_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"}[$__rate_interval]))', "transmit {{pod}}"),
            ], "Pod network traffic. Host-networked Pods may not have isolated values.", "Bps", "15s"),
            table("Current Pod phases", 'max by (cluster, namespace, pod, phase) (kube_pod_status_phase{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"} == 1)', "One-hot current Pod phase.", "short", "warm"),
            table("Last termination reason", 'max by (cluster, namespace, pod, container, reason) (kube_pod_container_status_last_terminated_reason{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"} == 1)', "Last observed reason, not a complete incident history. Interpret the reason label, because a recorded termination is not always a fault.", "short", "warm"),
            table("Pod owners and nodes", 'max by (cluster, namespace, pod, node, owner_kind, owner_name) (kube_pod_info{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"} * on (cluster, namespace, pod) group_left(owner_kind, owner_name) kube_pod_owner{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",owner_is_controller="true"})', "Current scheduling and owning controller identity.", "short"),
            table("Configured memory limits", 'sum by (cluster, namespace, pod, container) (kube_pod_container_resource_limits{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod",resource="memory",unit="byte"})', "Zero or absent means no configured limit and is not a usage ratio.", "bytes"),
            table("Restart details in range", 'sum by (cluster, namespace, pod, container) (increase(kube_pod_container_status_restarts_total{cluster=~"$cluster",namespace=~"$namespace",pod=~"$pod"}[$__range])) > 0', "Containers whose restart counter increased in the selected range. This is the evidence behind the KPI above.", "short", "warning"),
        ],
    },
    {
        "file": "40-k3s-etcd.json", "uid": "mon-k3s", "title": "K3s and etcd", "from": "now-1h", "refresh": "1m",
        "purpose": "Inspect API server, scheduler, kubelet and native etcd control-plane behavior while retaining per-node identity.",
        "vars": [],
        "panels": [
            stat("API 5xx ratio", 'sum(rate(apiserver_request_total{cluster=~"$cluster",code=~"5.."}[$__rate_interval])) / clamp_min(sum(rate(apiserver_request_total{cluster=~"$cluster"}[$__rate_interval])), 0.000001)', "Server-error share of API requests. Amber starts at 0.1%, red at 1%.", "percentunit", "error_ratio", "30s", 8),
            stat("etcd members without leader", 'count(etcd_server_has_leader{job="etcd",cluster=~"$cluster"}) - sum(etcd_server_has_leader{job="etcd",cluster=~"$cluster"})', "Native etcd members currently reporting no leader.", threshold="critical", width=8),
            stat("etcd leader changes", 'sum(increase(etcd_server_leader_changes_seen_total{job="etcd",cluster=~"$cluster"}[$__range]))', "Leader changes in the selected range. A nonzero value is a review signal, not automatically an outage.", threshold="warning", width=8),
            stat("Failed etcd proposals", 'sum(increase(etcd_server_proposals_failed_total{job="etcd",cluster=~"$cluster"}[$__range]))', "Consensus proposals that did not commit in the selected range. Brief control-plane or leader interruptions can increment this counter. It does not by itself prove data loss.", threshold="critical", width=12),
            stat("Pending etcd proposals", 'sum(etcd_server_proposals_pending{job="etcd",cluster=~"$cluster"})', "Current pending proposals across native etcd members. One to four is a warning, five or more is critical.", threshold="finding", width=12),
            table("Failed etcd proposals by member", 'sum by (cluster, node) (increase(etcd_server_proposals_failed_total{job="etcd",cluster=~"$cluster"}[$__range])) > 0', "Members that observed failed proposals in the selected range. Correlate the timestamp with leader changes, API errors and node networking.", "short", "critical"),
            chart("API request rate", [('sum by (cluster, verb) (rate(apiserver_request_total{cluster=~"$cluster"}[$__rate_interval]))', "{{cluster}} {{verb}}")], "API requests by verb.", "reqps", "30s"),
            chart("API request duration", [
                ('histogram_quantile(0.95, sum by (cluster, le) (rate(apiserver_request_duration_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "coarse p95 {{cluster}}"),
                ('sum by (cluster) (rate(apiserver_request_duration_seconds_sum{cluster=~"$cluster"}[$__rate_interval])) / clamp_min(sum by (cluster) (rate(apiserver_request_duration_seconds_count{cluster=~"$cluster"}[$__rate_interval])), 0.000001)', "mean {{cluster}}"),
            ], "Coarse retained-bucket p95 and mean API duration.", "s", "30s"),
            chart("API inflight requests", [('sum by (cluster, request_kind) (apiserver_current_inflight_requests{cluster=~"$cluster"})', "{{cluster}} {{request_kind}}")], "Current read/write API inflight requests.", "short", "30s"),
            chart("Scheduler attempts", [('sum by (cluster, result) (rate(scheduler_schedule_attempts_total{cluster=~"$cluster"}[$__rate_interval]))', "{{cluster}} {{result}}")], "Scheduling attempt outcome rate.", "ops", "30s"),
            chart("Kubelet Pod startup duration", [('histogram_quantile(0.95, sum by (cluster, node, le) (rate(kubelet_pod_start_duration_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "coarse p95 {{cluster}} {{node}}")], "Per-node coarse p95 Pod start duration.", "s", "30s"),
            chart("etcd database size and quota", [
                ('max by (cluster, node) (etcd_mvcc_db_total_size_in_use_in_bytes{job="etcd",cluster=~"$cluster"})', "used {{cluster}} {{node}}"),
                ('max by (cluster, node) (etcd_mvcc_db_total_size_in_bytes{job="etcd",cluster=~"$cluster"})', "allocated {{cluster}} {{node}}"),
                ('max by (cluster, node) (etcd_server_quota_backend_bytes{job="etcd",cluster=~"$cluster"})', "quota {{cluster}} {{node}}"),
            ], "Per-member in-use, allocated and quota bytes.", "bytes", "30s"),
            chart("etcd storage latency", [
                ('histogram_quantile(0.95, sum by (cluster, node, le) (rate(etcd_disk_wal_fsync_duration_seconds_bucket{job="etcd",cluster=~"$cluster"}[$__rate_interval])))', "WAL fsync p95 {{node}}"),
                ('histogram_quantile(0.95, sum by (cluster, node, le) (rate(etcd_disk_backend_commit_duration_seconds_bucket{job="etcd",cluster=~"$cluster"}[$__rate_interval])))', "backend commit p95 {{node}}"),
            ], "Coarse per-member retained-bucket latency.", "s", "30s"),
            chart("etcd peer round-trip time", [('histogram_quantile(0.95, sum by (cluster, node, le) (rate(etcd_network_peer_round_trip_time_seconds_bucket{job="etcd",cluster=~"$cluster"}[$__rate_interval])))', "peer p95 {{cluster}} {{node}}")], "Coarse per-member peer round-trip p95.", "s", "30s"),
            table("Control-plane workqueue depth", 'sum by (cluster, name) (workqueue_depth{cluster=~"$cluster",job="kubelet"})', "Shared K3s control-plane workqueues are collected once per cluster where possible.", "short", "warm", "30s"),
            table("etcd member state", 'max by (cluster, node) (etcd_server_has_leader{job="etcd",cluster=~"$cluster"})', "Each native member's leader perception.", "short", "ready"),
        ],
    },
    {
        "file": "50-network.json", "uid": "mon-network", "title": "DNS and Networking", "from": "now-1h", "refresh": "1m",
        "purpose": "Follow DNS, ingress and load-balancer metrics. This is not a synthetic end-to-end reachability test.",
        "vars": [],
        "panels": [
            stat("CoreDNS SERVFAIL rate", 'sum(rate(coredns_dns_responses_total{cluster=~"$cluster",rcode="SERVFAIL"}[$__rate_interval]))', "SERVFAIL responses per second. Small nonzero rates are warnings, sustained rates of one per second or more are critical.", "reqps", "warning_rate"),
            stat("Traefik 5xx rate", 'sum(rate(traefik_service_requests_total{cluster=~"$cluster",code=~"5.."}[$__rate_interval]))', "Service-level 5xx responses per second. Small nonzero rates are warnings, sustained rates of one per second or more are critical.", "reqps", "warning_rate"),
            stat("MetalLB stale configs", 'sum(metallb_k8s_client_config_stale_bool{cluster=~"$cluster"})', "MetalLB components reporting stale config.", threshold="critical"),
            stat("Kube-VIP unavailable targets", 'count(up{cluster=~"$cluster",job="kube-vip"}) - sum(up{cluster=~"$cluster",job="kube-vip"})', "Kube-VIP scrape/process health only.", threshold="critical"),
            chart("CoreDNS request and error rate", [
                ('sum by (cluster) (rate(coredns_dns_requests_total{cluster=~"$cluster"}[$__rate_interval]))', "requests {{cluster}}"),
                ('sum by (cluster, rcode) (rate(coredns_dns_responses_total{cluster=~"$cluster",rcode!="NOERROR"}[$__rate_interval]))', "{{rcode}} {{cluster}}"),
            ], "DNS request volume and non-NOERROR responses.", "reqps", "30s"),
            chart("CoreDNS duration", [('histogram_quantile(0.95, sum by (cluster, le) (rate(coredns_dns_request_duration_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "p95 {{cluster}}")], "DNS response p95 from retained buckets.", "s", "30s"),
            gauge("CoreDNS cache hit ratio", '100 * sum by (cluster) (rate(coredns_cache_hits_total{cluster=~"$cluster"}[$__rate_interval])) / clamp_min(sum by (cluster) (rate(coredns_cache_hits_total{cluster=~"$cluster"}[$__rate_interval])) + sum by (cluster) (rate(coredns_cache_misses_total{cluster=~"$cluster"}[$__rate_interval])), 0.000001)', "Cache hit percentage by cluster, calculated from separately aggregated hit and miss counters.", "percent", "free", height=8),
            chart("Traefik request rate", [('sum by (cluster, entrypoint) (rate(traefik_entrypoint_requests_total{cluster=~"$cluster"}[$__rate_interval]))', "{{cluster}} {{entrypoint}}")], "Ingress requests by entrypoint.", "reqps", "30s"),
            chart("Traefik service duration", [('histogram_quantile(0.95, sum by (cluster, service, le) (rate(traefik_service_request_duration_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "{{cluster}} {{service}}")], "Service p95 request duration.", "s", "30s"),
            chart("MetalLB L2 activity", [
                ('sum by (cluster) (rate(metallb_layer2_requests_received{cluster=~"$cluster"}[$__rate_interval]))', "requests {{cluster}}"),
                ('sum by (cluster) (rate(metallb_layer2_responses_sent{cluster=~"$cluster"}[$__rate_interval]))', "responses {{cluster}}"),
                ('sum by (cluster) (rate(metallb_layer2_gratuitous_sent{cluster=~"$cluster"}[$__rate_interval]))', "gratuitous {{cluster}}"),
            ], "L2 counters are exported over HTTP inside the cluster.", "ops", "60s"),
            table("MetalLB pool allocation", '100 * max by (cluster, pool) (metallb_allocator_addresses_in_use_total{cluster=~"$cluster"}) / clamp_min(max by (cluster, pool) (metallb_allocator_addresses_total{cluster=~"$cluster"}), 1)', "Address-pool utilization by cluster and pool.", "percent", "percent"),
            table("Ingress and network target health", 'min by (cluster, job, component) (up{cluster=~"$cluster",job=~"kubernetes-infrastructure|metallb|kube-vip"})', "Worst observed scrape health in each group. Missing targets remain unknown.", "short", "ready"),
        ],
    },
    {
        "file": "60-storage.json", "uid": "mon-storage", "title": "Storage and Longhorn", "from": "now-1h", "refresh": "1m",
        "purpose": "Separate logical PVC use, Longhorn physical allocation, volume health and backup freshness.",
        "vars": [
            variable("namespace", "kube_persistentvolumeclaim_info", "namespace", 'cluster=~"$cluster"'),
            variable("pvc", "kube_persistentvolumeclaim_info", "persistentvolumeclaim", 'cluster=~"$cluster",namespace=~"$namespace"'),
        ],
        "panels": [
            stat("Unbound PVCs", 'sum(kube_persistentvolumeclaim_status_phase{cluster=~"$cluster",namespace=~"$namespace",persistentvolumeclaim=~"$pvc",phase!="Bound"})', "PVCs not currently Bound.", threshold="critical"),
            stat("Degraded or faulted volumes", 'sum(longhorn_volume_robustness{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc",robustness=~"degraded|faulted"} == 1)', "Active Longhorn degraded/faulted one-hot states.", threshold="critical"),
            stat("Volume attachments not attached", 'count(kube_volumeattachment_status_attached{cluster=~"$cluster"}) - sum(kube_volumeattachment_status_attached{cluster=~"$cluster"})', "Current VolumeAttachment objects not attached.", threshold="critical"),
            gauge("PVC filesystem used", 'sort_desc(100 * max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace",persistentvolumeclaim=~"$pvc"}) / max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace",persistentvolumeclaim=~"$pvc"}))', "Deduplicated logical filesystem usage, fullest volume first.", "percent", "percent", "60s", 24),
            chart("PVC used and available bytes", [
                ('max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace",persistentvolumeclaim=~"$pvc"})', "used {{persistentvolumeclaim}}"),
                ('max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_available_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace",persistentvolumeclaim=~"$pvc"})', "available {{persistentvolumeclaim}}"),
            ], "Logical filesystem bytes from kubelet.", "bytes", "60s"),
            chart("Longhorn volume sizes", [
                ('max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_capacity_bytes{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"})', "capacity {{pvc}}"),
                ('max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_actual_size_bytes{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"})', "actual {{pvc}}"),
            ], "Longhorn logical capacity versus physical allocation.", "bytes", "60s"),
            chart("Longhorn I/O", [
                ('sum by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_read_throughput{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"})', "read {{pvc}}"),
                ('sum by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_write_throughput{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"})', "write {{pvc}}"),
            ], "Longhorn volume throughput.", "Bps", "60s"),
            chart("Longhorn volume I/O latency", [
                ('max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_read_latency{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"}) / 1000000000', "read {{cluster}} {{pvc}}"),
                ('max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_write_latency{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"}) / 1000000000', "write {{cluster}} {{pvc}}"),
            ], "Longhorn engine read and write latency, converted from nanoseconds to seconds. This is volume I/O latency, not replica synchronization lag.", "s", "30s"),
            table("Longhorn volume state", 'max by (cluster, pvc_namespace, pvc, volume, state) (longhorn_volume_state{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"} == 1)', "Active one-hot volume state. Interpret the textual state label, not the numeric one-hot value.", "short", "warm"),
            table("Longhorn node storage", '100 * max by (cluster, exported_node) (longhorn_node_storage_usage_bytes{cluster=~"$cluster"}) / clamp_min(max by (cluster, exported_node) (longhorn_node_storage_capacity_bytes{cluster=~"$cluster"}), 1)', "Physical Longhorn node storage utilization.", "percent", "percent"),
            table("Volumes needing attention", 'max by (cluster, pvc_namespace, pvc, volume, state) (longhorn_volume_robustness{cluster=~"$cluster",state!="healthy"} == 1)', "Current Longhorn volumes whose exported robustness state is not healthy. Empty means no current finding while Longhorn metrics are present.", "short", "critical"),
            table("Longhorn replica state", 'max by (cluster, volume, replica, state) (longhorn_replica_state{cluster=~"$cluster"} == 1)', "Active one-hot replica states. Interpret the state label rather than treating every value of one as healthy."),
            table("Replica modes needing attention", 'max by (cluster, volume, replica, mode) (longhorn_engine_replica_mode{cluster=~"$cluster",mode!="RW"} == 1)', "Replica modes other than read-write. The deployed Longhorn exporter does not expose rebuild percentage, so WO and ERR modes are the available rebuild/failure evidence.", "short", "critical"),
            table("Longhorn snapshot overview", 'topk(25, longhorn_snapshot_actual_size_bytes{cluster=~"$cluster"} * on(cluster, volume) group_left(pvc_namespace, pvc) (max by (cluster, volume, pvc_namespace, pvc) (longhorn_volume_capacity_bytes{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"}) > bool 0))', "Largest current Longhorn snapshots by actual size, enriched with PVC namespace and name.", "bytes"),
            table("Last Longhorn backup age", '(time() - max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_last_backup_at{cluster=~"$cluster",pvc_namespace=~"$namespace",pvc=~"$pvc"} > 0)) / 3600', "Hours since the last exported Longhorn volume backup timestamp. Volumes without a backup timestamp remain absent.", "h", "warm"),
            mapped_table("Longhorn backup state", 'max by (cluster, volume, backup, recurring_job) (longhorn_backup_state{cluster=~"$cluster"})', "Backup state codes exported by Longhorn. Completed is healthy history; Error requires review.", {0: "New", 1: "Pending", 2: "In progress", 3: "Completed", 4: "Error", 5: "Unknown"}),
        ],
    },
    {
        "file": "70-postgres.json", "uid": "mon-postgres", "title": "PostgreSQL and Backups", "from": "now-1h", "refresh": "1m",
        "purpose": "Inspect CloudNativePG cluster readiness, SQL collector health, replication and backup evidence. Backup presence does not prove restore success.",
        "vars": [
            variable("namespace", "cnpg_resource_instances_desired", "namespace", 'cluster=~"$cluster"'),
            variable("cnpg_cluster", "cnpg_resource_instances_desired", "cnpg_cluster", 'cluster=~"$cluster",namespace=~"$namespace"'),
        ],
        "panels": [
            stat("Instance readiness gap", 'sum(clamp_min(cnpg_resource_instances_desired{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"} - cnpg_resource_instances_ready{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}, 0))', "Desired minus ready CNPG instances.", threshold="critical"),
            stat("SQL collectors down", 'count(cnpg_collector_up{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}) - sum(cnpg_collector_up{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "Database SQL collectors currently down.", threshold="critical"),
            stat("Latest backup age", '(time() - max(cnpg_resource_backup_last_success_timestamp_seconds{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})) / 3600', "Hours since newest successful backup in scope.", "h", "warm"),
            stat("Suspended backup schedules", 'sum(cnpg_resource_backup_schedule_suspended{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "Explicitly suspended schedules. Suspension may be intentional and is shown as a warning.", threshold="warning"),
            chart("Desired and ready instances", [
                ('max by (cluster, namespace, cnpg_cluster, __name__) ({__name__=~"cnpg_resource_instances_desired|cnpg_resource_instances_ready",cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "{{cluster}} - {{cnpg_cluster}} - {{__name__}}"),
            ], "CNPG control-plane instance state.", "short", "60s"),
            chart("Replication delay", [('1000 * max by (cluster, namespace, cnpg_cluster, cnpg_instance) (cnpg_pg_replication_lag{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "{{cluster}} - {{cnpg_cluster}} - {{cnpg_instance}}")], "How far a standby is behind its primary, shown in milliseconds. A true zero means no measurable delay at scrape time; brief nonzero peaks can still occur.", "ms", "30s"),
            chart("Connections and waits", [
                ('sum by (cluster, namespace, cnpg_cluster, cnpg_instance) (cnpg_backends_total{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "connections {{cluster}} - {{cnpg_cluster}} - {{cnpg_instance}}"),
                ('sum by (cluster, namespace, cnpg_cluster, cnpg_instance) (cnpg_backends_waiting_total{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})', "waiting {{cluster}} - {{cnpg_cluster}} - {{cnpg_instance}}"),
            ], "Backend totals and waiting backends.", "short", "30s"),
            chart("Transactions and deadlocks", [
                ('sum by (cluster, namespace, cnpg_cluster, __name__) (rate({__name__=~"cnpg_pg_stat_database_xact_commit|cnpg_pg_stat_database_xact_rollback|cnpg_pg_stat_database_deadlocks",cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}[$__rate_interval]))', "{{cluster}} - {{cnpg_cluster}} - {{__name__}}"),
            ], "Transaction outcomes and deadlock rate.", "ops", "30s"),
            chart("Database size", [('sum by (cluster, namespace, cnpg_cluster, datname) (cnpg_pg_database_size_bytes{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster",cnpg_role="primary"})', "{{cluster}} - {{cnpg_cluster}} - {{datname}}")], "Logical database size from current primaries.", "bytes", "60s"),
            chart("WAL archival", [
                ('sum by (cluster, namespace, cnpg_cluster) (rate(cnpg_pg_stat_archiver_archived_count{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}[$__rate_interval]))', "archived {{cluster}} - {{cnpg_cluster}}"),
                ('sum by (cluster, namespace, cnpg_cluster) (rate(cnpg_pg_stat_archiver_failed_count{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}[$__rate_interval]))', "failed {{cluster}} - {{cnpg_cluster}}"),
            ], "Archive outcomes from PostgreSQL primaries.", "ops", "60s"),
            table("Backup evidence", '(time() - max by (cluster, namespace, cnpg_cluster) (cnpg_resource_backup_last_success_timestamp_seconds{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})) / 3600', "Hours since each cluster's latest successful backup. Historical failed objects are not counted as failures today.", "h"),
            table("Collector error state in range", 'max by (cluster, namespace, cnpg_cluster, cnpg_instance) (max_over_time(cnpg_last_error{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}[$__range]))', "One means at least one scrape in the selected range reported that the preceding PostgreSQL collection ended with an error. Zero means observed collections were healthy.", "short", "warning"),
            gauge("Database cache hit ratio", '100 * sum by (cluster, namespace, cnpg_cluster, datname) (rate(cnpg_pg_stat_database_blks_hit{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster",datname!=""}[$__rate_interval])) / clamp_min(sum by (cluster, namespace, cnpg_cluster, datname) (rate(cnpg_pg_stat_database_blks_hit{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster",datname!=""}[$__rate_interval])) + sum by (cluster, namespace, cnpg_cluster, datname) (rate(cnpg_pg_stat_database_blks_read{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster",datname!=""}[$__rate_interval])), 0.000001)', "PostgreSQL shared-buffer cache hit percentage by database, calculated from block-hit and block-read counter rates.", "percent", "free", "60s", 12, "{{cluster}} - {{cnpg_cluster}} - {{datname}}"),
            chart("Temporary data written", [('sum by (cluster, namespace, cnpg_cluster, datname) (rate(cnpg_pg_stat_database_temp_bytes{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"}[$__rate_interval]))', "{{cluster}} - {{cnpg_cluster}} - {{datname}}")], "Temporary bytes generated per second.", "Bps", "60s"),
            table("Latest failed backup age", '(time() - max by (cluster, namespace, cnpg_cluster) (cnpg_resource_backup_last_failure_timestamp_seconds{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})) / 3600', "Hours since the latest failed backup, shown separately from the latest success.", "h", "warm"),
            table("CNPG operator reconcile errors", 'sum by (cluster, component, controller) (increase(controller_runtime_reconcile_errors_total{cluster=~"$cluster",component=~"cloudnative.*|cnpg.*"}[$__range]))', "CloudNativePG operator reconcile errors in range. Nonzero counts are review signals.", "short", "warning"),
            table("Recovery window age", '(time() - min by (cluster, namespace, cnpg_cluster) (cnpg_collector_first_recoverability_point{cluster=~"$cluster",namespace=~"$namespace",cnpg_cluster=~"$cnpg_cluster"})) / 3600', "Hours covered back to the first recoverability point reported by the collector.", "h", "warm"),
        ],
    },
    {
        "file": "80-platform.json", "uid": "mon-platform", "title": "Controllers and Certificates", "from": "now-1h", "refresh": "1m",
        "purpose": "Inspect certificate lifecycle, metrics-server and generic infrastructure controller reconciliation.",
        "vars": [variable("component", "up", "component", 'cluster=~"$cluster",job="kubernetes-infrastructure"')],
        "panels": [
            stat("Certificates not Ready", 'count(certmanager_certificate_ready_status{cluster=~"$cluster",condition="True"}) - sum(certmanager_certificate_ready_status{cluster=~"$cluster",condition="True"})', "Certificate resources without Ready=True.", threshold="critical"),
            stat("Certificates below 14 days", 'count((certmanager_certificate_expiration_timestamp_seconds{cluster=~"$cluster"} - time()) / 86400 < 14)', "Certificates inside the initial review window. This count is a warning, while the lifetime table marks certificates below seven days as critical.", threshold="warning"),
            stat("Controller reconcile errors", 'sum(increase(controller_runtime_reconcile_errors_total{cluster=~"$cluster",component=~"$component"}[$__range]))', "Selected infrastructure controller errors in range. Nonzero counts are review signals.", threshold="warning"),
            stat("Infrastructure targets down", 'count(up{cluster=~"$cluster",job="kubernetes-infrastructure",component=~"$component"}) - sum(up{cluster=~"$cluster",job="kubernetes-infrastructure",component=~"$component"})', "Selected infrastructure scrape targets down.", threshold="critical"),
            table("Certificate lifetime", '(min by (cluster, exported_namespace, name) (certmanager_certificate_expiration_timestamp_seconds{cluster=~"$cluster"}) - time()) / 86400', "Days remaining by certificate object namespace and name, shortest lifetime first.", "d", "days", "60s", 24, False),
            chart("Controller reconciliations", [
                ('sum by (cluster, component, controller, result) (rate(controller_runtime_reconcile_total{cluster=~"$cluster",component=~"$component"}[$__rate_interval]))', "{{component}} {{controller}} {{result}}"),
                ('sum by (cluster, component, controller) (rate(controller_runtime_reconcile_errors_total{cluster=~"$cluster",component=~"$component"}[$__rate_interval]))', "errors {{component}} {{controller}}"),
            ], "Selected controller outcome and error rates.", "ops", "60s"),
            chart("Controller workqueue", [
                ('sum by (cluster, component, name) (workqueue_depth{cluster=~"$cluster",component=~"$component"})', "depth {{component}} {{name}}"),
                ('sum by (cluster, component, name) (rate(workqueue_retries_total{cluster=~"$cluster",component=~"$component"}[$__rate_interval]))', "retries {{component}} {{name}}"),
            ], "Queue depth and retry rate for selected components.", "short", "60s"),
            chart("metrics-server API freshness", [('histogram_quantile(0.95, sum by (cluster, le) (rate(metrics_server_api_metric_freshness_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "p95 {{cluster}}")], "Age of metrics served by metrics-server.", "s", "60s"),
            chart("metrics-server kubelet requests", [
                ('sum by (cluster, code) (rate(metrics_server_kubelet_request_total{cluster=~"$cluster"}[$__rate_interval]))', "{{cluster}} {{code}}"),
                ('histogram_quantile(0.95, sum by (cluster, le) (rate(metrics_server_kubelet_request_duration_seconds_bucket{cluster=~"$cluster"}[$__rate_interval])))', "duration p95 {{cluster}}"),
            ], "Request outcomes and coarse p95 duration. The two series use different units, inspect values individually.", "short", "60s"),
            table("Issuer readiness", 'max by (cluster, exported_namespace, name, condition) (certmanager_issuer_ready_status{cluster=~"$cluster"})', "Namespaced issuer state. Cluster issuers are listed separately in Explore when needed.", "short", "ready"),
            table("Selected component health", 'max by (cluster, component, instance) (up{cluster=~"$cluster",job="kubernetes-infrastructure",component=~"$component"})', "Current scrape health by selected component.", "short", "ready"),
        ],
    },
    {
        "file": "90-pipeline.json", "uid": "mon-pipeline", "title": "Collection and Metrics Backend", "from": "now-1h", "refresh": "1m",
        "purpose": "Decide whether dashboard data is trustworthy by following scrape, Remote Write, VictoriaMetrics and vmauth health.",
        "vars": [variable("job", "up", "job", 'cluster=~"$cluster"')],
        "panels": [
            stat("Targets down", 'count(up{cluster=~"$cluster",job=~"$job"}) - sum(up{cluster=~"$cluster",job=~"$job"})', "Selected targets currently down.", threshold="critical"),
            stat("Remote Write sample age", 'clamp_min(time() - max(prometheus_remote_storage_queue_highest_sent_timestamp_seconds{cluster=~"$cluster"}), 0)', "Age of the newest transmitted sample.", "s", "age", "15s"),
            stat("Remote Write pending samples", 'sum(prometheus_remote_storage_samples_pending{cluster=~"$cluster"})', "Current in-flight samples across selected clusters. Short sawtooth growth is normal while batches fill. Investigate sustained growth together with rising sample age, retries or failures.", threshold="warm", interval="15s"),
            stat("VictoriaMetrics read-only", 'max(vm_storage_is_read_only{job="victoriametrics"})', "Central storage read-only status, excluding application HistoryDB.", threshold="critical"),
            chart("Remote Write queue depth", [('sum by (cluster) (prometheus_remote_storage_samples_pending{cluster=~"$cluster"})', "pending {{cluster}}")], "Per-cluster samples waiting to be batched and sent. Regular rises and drops are normal. A continuously rising line with increasing sample age or retries indicates backlog.", "short", "15s"),
            chart("Target scrape duration", [('max by (cluster, job) (scrape_duration_seconds{cluster=~"$cluster",job=~"$job"})', "{{cluster}} {{job}}")], "Worst current scrape duration by cluster and job.", "s", "30s"),
            chart("Remote Write flow", [
                ('sum by (cluster, __name__) (rate({__name__=~"prometheus_remote_storage_samples_in_total|prometheus_remote_storage_samples_total",cluster=~"$cluster"}[$__rate_interval]))', "{{__name__}} {{cluster}}"),
                ('sum by (cluster, __name__) (rate({__name__=~"prometheus_remote_storage_samples_retried_total|prometheus_remote_storage_samples_failed_total",cluster=~"$cluster"}[$__rate_interval]))', "{{__name__}} {{cluster}}"),
            ], "Alloy queue ingestion, transmission, retry and failure rates.", "ops", "15s"),
            chart("Remote Write shards", [('sum by (cluster, __name__) ({__name__=~"prometheus_remote_storage_shards|prometheus_remote_storage_shards_desired|prometheus_remote_storage_shards_max",cluster=~"$cluster"})', "{{__name__}} {{cluster}}")], "Queue shard scaling.", "short", "15s"),
            chart("VictoriaMetrics ingestion", [
                ('sum(rate(vm_rows_inserted_total{job="victoriametrics"}[$__rate_interval]))', "inserted rows"),
                ('sum(rate(vm_slow_row_inserts_total{job="victoriametrics"}[$__rate_interval]))', "slow-path rows"),
                ('sum(rate(vm_rows_invalid_total{job="victoriametrics"}[$__rate_interval]))', "invalid rows"),
            ], "Row ingestion, slow-path and invalid rates. Slow is not failed.", "ops", "30s"),
            chart("VictoriaMetrics disk", [
                (VM_PVC_USED, "PVC used"),
                ('sum(vm_data_size_bytes{job="victoriametrics"})', "data size"),
                (VM_WRITE_STOP, "write-stop threshold"),
                (VM_PVC_CAPACITY, "PVC capacity"),
            ], "All series use the used-capacity scale. VictoriaMetrics stops accepting writes when PVC usage reaches the write-stop threshold, calculated as observed PVC capacity minus its required free-space reserve. Data size excludes filesystem and WAL overhead, so PVC used is authoritative.", "bytes", "60s"),
            chart("VictoriaMetrics queries", [
                ('sum by (__name__) (rate({__name__=~"vm_http_requests_total|vm_http_request_errors_total|vm_slow_queries_total",job="victoriametrics"}[$__rate_interval]))', "{{__name__}}"),
            ], "Backend request, error and slow-query rates.", "reqps", "30s"),
            table("Target health by cluster and job", 'count by (cluster, job) (up{cluster=~"$cluster",job=~"$job"}) - sum by (cluster, job) (up{cluster=~"$cluster",job=~"$job"})', "Zero is healthy for observed targets. A vanished cluster needs an external expected inventory.", "short", "critical"),
            table("vmauth request errors", 'sum by (path) (rate(vmauth_http_request_errors_total[$__rate_interval])) + sum by (path) (rate(vmauth_user_request_errors_total[$__rate_interval]))', "Authentication/proxy request error rate without exposing users or credentials. Small nonzero rates are warnings.", "reqps", "warning_rate", "30s"),
        ],
    },
    {
        "file": "100-daily.json", "uid": "mon-daily", "title": "Daily Review", "from": "now-24h", "refresh": "1m",
        "purpose": "Review the previous completed day. Values describe observed samples and counter changes, not an application SLO or event archive.",
        "vars": [],
        "panels": [
            stat("Observed target availability", '100 * avg(avg_over_time(up{cluster=~"$cluster"}[$__range]))', "Average observed target scrape state over the selected completed day. Green starts at 99.5%.", "percent", "availability", "60s"),
            stat("Pod restarts", 'sum(increase(kube_pod_container_status_restarts_total{cluster=~"$cluster"}[$__range]))', "Restart counter increase in the selected period. One to four is a warning, five or more is critical.", threshold="finding"),
            stat("API 5xx responses", 'sum(increase(apiserver_request_total{cluster=~"$cluster",code=~"5.."}[$__range]))', "API server 5xx responses in the selected period. One to four is a warning, five or more is critical.", threshold="finding"),
            stat("etcd leader changes", 'sum(increase(etcd_server_leader_changes_seen_total{job="etcd",cluster=~"$cluster"}[$__range]))', "Native etcd leader changes in the selected period. A nonzero count is a review signal.", threshold="warning"),
            table("Target availability by cluster and job", '100 * avg by (cluster, job) (avg_over_time(up{cluster=~"$cluster"}[$__range]))', "Observed scrape availability, smallest value first. Missing periods remain unknown.", "percent", "percent", "60s", 24, False),
            table("Pod restart increases", 'topk(20, sum by (cluster, namespace, pod, container) (increase(kube_pod_container_status_restarts_total{cluster=~"$cluster"}[$__range])))', "Largest restart increases in the selected period.", "short", "finding"),
            table("API errors", 'sum by (cluster, code, verb, resource) (increase(apiserver_request_total{cluster=~"$cluster",code=~"4..|5.."}[$__range]))', "API error responses during the selected period. Small counts are warnings because expected client errors can occur.", "short", "finding"),
            table("DNS and ingress errors", 'label_replace(sum by (cluster, rcode) (increase(coredns_dns_responses_total{cluster=~"$cluster",rcode!="NOERROR"}[$__range])), "source", "CoreDNS", "", "") or label_replace(sum by (cluster, code) (increase(traefik_service_requests_total{cluster=~"$cluster",code=~"4..|5.."}[$__range])), "source", "Traefik", "", "")', "DNS non-NOERROR and ingress 4xx/5xx counts as separate findings. Small counts are warnings.", "short", "finding"),
            stat("Storage findings", 'sum(longhorn_volume_robustness{cluster=~"$cluster",state!="healthy"} == 1) or (0 * count(longhorn_volume_robustness{cluster=~"$cluster"}))', "Current Longhorn volumes whose robustness state is not healthy. Zero is valid only while Longhorn telemetry is present.", threshold="critical", width=24),
            table("PostgreSQL backup freshness", '(time() - max by (cluster, namespace, cnpg_cluster) (cnpg_resource_backup_last_success_timestamp_seconds{cluster=~"$cluster"})) / 3600', "End-of-period age of latest successful CNPG backup. Old failed objects are not daily failures.", "h"),
            table("Longhorn backup freshness", '(time() - max by (cluster, pvc_namespace, pvc, volume) (longhorn_volume_last_backup_at{cluster=~"$cluster"} > 0)) / 3600', "Hours since the latest exported Longhorn volume backup. Volumes without a backup timestamp remain absent rather than appearing extremely old.", "h"),
            table("Longhorn snapshot overview", 'topk(25, max by (cluster, volume, snapshot, user_created) (longhorn_snapshot_actual_size_bytes{cluster=~"$cluster"}))', "Largest current Longhorn snapshots by actual size. System snapshots can exist even when they were not created manually.", "bytes"),
            table("Certificate lifetime", '(min by (cluster, exported_namespace, name) (certmanager_certificate_expiration_timestamp_seconds{cluster=~"$cluster"}) - time()) / 86400', "End-of-period certificate lifetime, shortest lifetime first.", "d", "days", sort_desc=False),
            table("Top CPU consumers", 'topk(20, sum by (cluster, namespace, pod) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",container!="",container!="POD"}[$__rate_interval])))', "Top sampled Pod CPU rates near the period end. This is not the day's maximum.", "cores", interval="60s"),
        ],
    },
    {
        "file": "110-capacity.json", "uid": "mon-capacity", "title": "Capacity and Reliability", "from": "now-1h", "refresh": "1m",
        "purpose": "Review 7/30/90-day trends. Forecasting requires at least seven days of sufficiently complete data and is intentionally conservative.",
        "vars": [variable("namespace", "kube_namespace_status_phase", "namespace", 'cluster=~"$cluster"')],
        "panels": [
            stat("Observed history in range", 'time() - min(min_over_time(timestamp(up{cluster=~"$cluster"})[$__range:1h]))', "Age of the oldest observed sample inside the selected range, sampled hourly. Retention does not guarantee complete coverage.", "s", "warm", "60s"),
            stat("Metrics backend used", 'sum(vm_data_size_bytes{job="victoriametrics"})', "Central VictoriaMetrics data size, excluding HistoryDB.", "bytes", "warm", "60s"),
            stat("Metrics backend free", 'max(vm_free_disk_space_bytes{job="victoriametrics"})', "Current free central backend filesystem bytes.", "bytes", "warm", "60s"),
            stat("PVCs above 85%", 'count(100 * max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace"}) / max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace"}) > 85)', "Current logical filesystems above 85%. This is a capacity warning, not automatically an outage.", threshold="warning", interval="60s"),
            stat("CPU request coverage", '100 * count(kube_pod_container_resource_requests{cluster=~"$cluster",namespace=~"$namespace",resource="cpu",unit="core"} > 0) / clamp_min(count(kube_pod_container_info{cluster=~"$cluster",namespace=~"$namespace"}), 1)', "Share of regular containers with positive CPU requests.", "percent", "free", "60s"),
            stat("Memory limit coverage", '100 * count(kube_pod_container_resource_limits{cluster=~"$cluster",namespace=~"$namespace",resource="memory",unit="byte"} > 0) / clamp_min(count(kube_pod_container_info{cluster=~"$cluster",namespace=~"$namespace"}), 1)', "Share of regular containers with positive memory limits.", "percent", "free", "60s"),
            stat("Estimated free space in 30 days", 'predict_linear(vm_free_disk_space_bytes{job="victoriametrics"}[7d], 2592000)', "Linear estimate from the latest seven days. Treat N/A or nonpositive trends as insufficient evidence, not a capacity promise.", "bytes", "warm", "60s"),
            chart("Node CPU utilization", [('100 * (1 - avg by (cluster, node) (rate(node_cpu_seconds_total{job="node-exporter",cluster=~"$cluster",mode="idle"}[$__rate_interval])))', "{{cluster}} {{node}}")], "Long-window CPU trend. Use panel statistics for peaks, not visual guesswork.", "percent", "60s"),
            chart("Node memory utilization", [('100 * (1 - node_memory_MemAvailable_bytes{job="node-exporter",cluster=~"$cluster"} / node_memory_MemTotal_bytes{job="node-exporter",cluster=~"$cluster"})', "{{cluster}} {{node}}")], "Available-memory based utilization.", "percent", "60s"),
            chart("Namespace CPU", [('topk(10, sum by (cluster, namespace) (rate(container_cpu_usage_seconds_total{cluster=~"$cluster",namespace=~"$namespace",container!="",container!="POD"}[$__rate_interval])))', "{{cluster}} {{namespace}}")], "Top namespaces by CPU rate.", "cores", "60s"),
            chart("Namespace memory", [('topk(10, sum by (cluster, namespace) (container_memory_working_set_bytes{cluster=~"$cluster",namespace=~"$namespace",container!="",container!="POD"}))', "{{cluster}} {{namespace}}")], "Top namespaces by memory working set.", "bytes", "60s"),
            chart("PVC logical usage", [('max by (cluster, namespace, persistentvolumeclaim) (kubelet_volume_stats_used_bytes{job="kubelet",cluster=~"$cluster",namespace=~"$namespace"})', "{{cluster}} {{namespace}} {{persistentvolumeclaim}}")], "Logical filesystem growth. Compaction and expansion can invalidate linear extrapolation.", "bytes", "60s"),
            chart("Longhorn physical allocation", [('sum by (cluster) (longhorn_volume_actual_size_bytes{cluster=~"$cluster"})', "{{cluster}}")], "Physical volume allocation, separate from PVC logical usage and backup storage.", "bytes", "60s"),
            chart("Monitoring Metrics Storage", [
                (VM_PVC_USED, "PVC used"),
                ('sum(vm_data_size_bytes{job="victoriametrics"})', "data size"),
                (VM_WRITE_STOP, "write-stop threshold"),
                (VM_PVC_CAPACITY, "PVC capacity"),
            ], "All series use the used-capacity scale. VictoriaMetrics stops accepting writes when PVC usage reaches the write-stop threshold, calculated as observed PVC capacity minus its required free-space reserve. Data size excludes filesystem and WAL overhead, so PVC used is authoritative.", "bytes", "60s"),
            chart("Metrics ingestion and series activity", [
                ('sum(rate(vm_rows_inserted_total{job="victoriametrics"}[$__rate_interval]))', "inserted rows"),
                ('sum(rate(vm_timeseries_precreated_total{job="victoriametrics"}[$__rate_interval]))', "new series"),
                ('sum(rate(vm_timeseries_repopulated_total{job="victoriametrics"}[$__rate_interval]))', "repopulated series"),
            ], "Rows ingested per second and the rate at which time series are newly created or repopulated.", "ops", "60s"),
        ],
    },
]

# PostgreSQL is built from the same specification by the application-dashboard
# generator, so it is provisioned once under Monitoring Applications.
PROVISIONED_DASHBOARDS = [spec for spec in DASHBOARDS if spec["uid"] != "mon-postgres"]


DRILLDOWNS = {
    "mon-overview": {
        "Targets by cluster and job": ("Open pipeline diagnostics", "mon-pipeline", "&var-job=${__data.fields.job}"),
        "Unavailable workload replicas": ("Open cluster diagnostics", "mon-cluster", "&var-namespace=${__data.fields.namespace}"),
        "PVC utilization": ("Open storage diagnostics", "mon-storage", "&var-namespace=${__data.fields.namespace}&var-pvc=${__data.fields.persistentvolumeclaim}"),
        "Certificate lifetime": ("Open certificate diagnostics", "mon-platform", ""),
    },
    "mon-cluster": {
        "Namespace CPU": ("Open namespace diagnostics", "mon-cluster", "&var-namespace=${__data.fields.namespace}"),
        "Namespace memory": ("Open namespace diagnostics", "mon-cluster", "&var-namespace=${__data.fields.namespace}"),
        "Deployment availability gap": ("Open Pod diagnostics", "mon-pod", "&var-namespace=${__data.fields.namespace}"),
        "StatefulSet readiness gap": ("Open Pod diagnostics", "mon-pod", "&var-namespace=${__data.fields.namespace}"),
        "DaemonSet unavailable": ("Open Pod diagnostics", "mon-pod", "&var-namespace=${__data.fields.namespace}"),
    },
    "mon-node": {
        "Top Pods on selected nodes": ("Open Pod diagnostics", "mon-pod", "&var-namespace=${__data.fields.namespace}&var-pod=${__data.fields.pod}"),
    },
    "mon-pod": {
        "Pod owners and nodes": ("Open node diagnostics", "mon-node", "&var-node=${__data.fields.node}"),
    },
    "mon-network": {
        "Ingress and network target health": ("Open pipeline diagnostics", "mon-pipeline", "&var-job=${__data.fields.job}"),
    },
    "mon-storage": {
        "Storage controller reconcile errors": ("Open controller diagnostics", "mon-platform", "&var-component=${__data.fields.component}"),
    },
    "mon-platform": {
        "Selected component health": ("Open pipeline diagnostics", "mon-pipeline", "&var-job=kubernetes-infrastructure"),
    },
    "mon-pipeline": {
        "Target health by cluster and job": ("Keep this target scope", "mon-pipeline", "&var-job=${__data.fields.job}"),
    },
    "mon-daily": {
        "Pod restart increases": ("Open Pod diagnostics", "mon-pod", "&var-namespace=${__data.fields.namespace}&var-pod=${__data.fields.pod}"),
        "Storage findings": ("Open storage diagnostics", "mon-storage", "&var-namespace=${__data.fields.pvc_namespace}&var-pvc=${__data.fields.pvc}"),
        "PostgreSQL backup freshness": ("Open PostgreSQL diagnostics", "mon-postgres", "&var-namespace=${__data.fields.namespace}&var-cnpg_cluster=${__data.fields.cnpg_cluster}"),
    },
}


def place(panels):
    x = 0
    y = 0
    row_height = 0
    for panel_data in panels:
        width = panel_data["gridPos"]["w"]
        height = panel_data["gridPos"]["h"]
        if x + width > 24:
            y += row_height
            x = 0
            row_height = 0
        panel_data["gridPos"].update({"x": x, "y": y})
        x += width
        row_height = max(row_height, height)
    return panels


def build(spec):
    cluster = variable("cluster", "up", "cluster")
    category_title = spec.get("category_title", "Infrastructure")
    category_tag = spec.get("category_tag", "infrastructure")
    panels = [intro(spec["purpose"]), FRESHNESS(), *spec["panels"]]
    for panel_id, panel_data in enumerate(place(panels), start=1):
        panel_data["id"] = panel_id
        drilldown = DRILLDOWNS.get(spec["uid"], {}).get(panel_data["title"])
        if drilldown:
            title, uid, variables = drilldown
            panel_data["fieldConfig"]["defaults"]["links"] = [{
                "targetBlank": False,
                "title": title,
                "url": f"/d/{uid}?${{__url_time_range}}&var-cluster=${{__data.fields.cluster}}{variables}",
            }]
    return {
        "annotations": {"list": [{
            "builtIn": 1,
            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
            "enable": True,
            "hide": True,
            "iconColor": "rgba(87, 148, 242, 1)",
            "name": "Annotations & Alerts",
            "type": "dashboard",
        }]},
        "description": spec["purpose"],
        "editable": False,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": dashboard_links(category_title, category_tag),
        "liveNow": False,
        "panels": panels,
        "preload": False,
        "refresh": spec["refresh"],
        "schemaVersion": 41,
        "tags": ["monitoring", "metrics", category_tag],
        "templating": {"list": [cluster, *spec["vars"]]},
        "time": {"from": spec["from"], "to": spec.get("to", "now")},
        "timepicker": {"refresh_intervals": REFRESH_INTERVALS, "time_options": ["1h", "3h", "6h", "12h", "24h", "2d", "7d", "30d", "90d"]},
        "timezone": "browser",
        "title": spec["title"],
        "uid": spec["uid"],
        "version": 1,
        "weekStart": "monday",
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for spec in PROVISIONED_DASHBOARDS:
        path = OUTPUT / spec["file"]
        path.write_text(json.dumps(build(spec), indent=2, sort_keys=False) + "\n")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
