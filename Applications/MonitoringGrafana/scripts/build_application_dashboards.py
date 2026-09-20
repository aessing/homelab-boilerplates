#!/usr/bin/env python3
"""Generate OSS application dashboards from the existing monitoring contracts."""
import copy
import json
from pathlib import Path

from build_dashboards import build, chart, stat, table, gauge, mapped_table, variable, panel, query, place, DASHBOARDS
from build_log_dashboards import logs, log_query

OUTPUT = Path(__file__).resolve().parents[1] / "components/_dashboards/application-dashboards"
C = 'cluster=~"$cluster"'
APP_NAMESPACES = "authentik|authentik-outpost|grafana|homeassistant|homecdn|timeserver|uptimekuma|homepage|scrypted|monitoring-logs|monitoring-metrics|postgres|postgresql|cnpg-system"
ROOT_OUTPUT = OUTPUT.parent / "root-dashboards"
UNIFI_OUTPUT = OUTPUT.parent / "unifi-dashboards"


def metric(name, extra=""):
    return f'{name}{{{C}{"," + extra if extra else ""}}}'


def trend(title, name, unit="short", rate=False, extra="", labels="cluster", description=""):
    expr = metric(name, extra)
    if rate:
        expr = f'rate({expr}[$__rate_interval])'
    return chart(title, [(f'sum by ({labels}) ({expr})', " ".join("{{" + label + "}}" for label in labels.split(",")))], description or title, unit)


def runtime(namespace):
    scope = f'{C},namespace=~"{namespace}"'
    identity = "cluster,namespace,pod,container"
    limit = f'max by ({identity}) (kube_pod_container_resource_limits{{{scope},resource="memory",unit="byte"}}) > 0'
    usage = f'max by ({identity}) (container_memory_working_set_bytes{{{scope},container!="",container!="POD"}})'
    inventory = f'max by ({identity}) (kube_pod_container_info{{{scope}}})'
    memory = table("Memory limit utilization", f'(100 * {usage} / on ({identity}) ({limit})) or (-1 * ({inventory} unless on ({identity}) ({limit})))', "Working set / configured limit. No limit configured means that no percentage can be calculated. It does not mean zero memory use. Consult the absolute memory chart.", "percent", "percent")
    memory["fieldConfig"]["defaults"]["mappings"] = [{"type": "value", "options": {"-1": {"text": "No limit configured", "color": "text"}}}]
    return [
        chart("Container CPU", [(f'sum by (cluster,pod,container) (rate(container_cpu_usage_seconds_total{{{scope},container!="",container!="POD"}}[$__rate_interval]))', '{{cluster}} {{pod}} {{container}}')], "CPU cores consumed by application containers and sidecars.", "cores"),
        chart("Container memory actual and limit", [
            (f'max by (cluster,pod,container) (container_memory_working_set_bytes{{{scope},container!="",container!="POD"}})', 'actual {{cluster}} {{pod}} {{container}}'),
            (f'max by (cluster,pod,container) (kube_pod_container_resource_limits{{{scope},resource="memory",unit="byte"}})', 'limit {{cluster}} {{pod}} {{container}}'),
        ], "Working set and configured limit. Containers without a limit have no limit series. The legend shows current and maximum values.", "bytes"),
        memory,
        table("Container restarts in range", f'sum by (cluster,namespace,pod,container) (increase(kube_pod_container_status_restarts_total{{{scope}}}[$__range]))', "Restarts across the selected time range. Zero does not prove application health.", threshold="warning"),
    ]


def log_panels(namespace):
    selector = f'{{{C},source="pod",namespace=~"{namespace}"}}'
    result = [
        log_query(chart("Application log volume", [], "Entries per second by workload. Quiet applications can return no data.", "logs/s"), f'sum by (cluster,workload) (rate({selector}[$__auto]))', '{{cluster}} {{workload}}'),
        log_query(chart("Error and warning keyword matches", [], "Heuristic text matches, not structured severity. Inspect the records before diagnosing an incident.", "logs/s"), f'sum by (cluster,workload) (rate({selector} |~ "(?i)error|fatal|panic|warn" [$__auto]))', '{{cluster}} {{workload}}'),
        logs("Application logs", selector + ' |= ${search:doublequote}', "Latest 500 sanitized lines in the selected range. Search applies here. Use Log Explorer for individual workload and container filters."),
    ]
    for p in result:
        p["description"] += " No data means no matching log entries in this interval, not a demonstrated delivery failure. Widen the range and check Log Pipeline Health."
        p["fieldConfig"]["defaults"]["noValue"] = "No matching log entries"
    return result


def make(uid, title, namespace, panels, purpose, variables=None, freshness=None):
    variables = variables or []
    variables.append({"name": "search", "label": "Log contains", "type": "textbox", "query": "", "current": {"text": "", "value": ""}, "skipUrlSync": False})
    dashboard = build({"uid": uid, "title": title, "purpose": purpose, "from": "now-1h", "refresh": "1m", "category_title": "Application", "category_tag": "applications", "vars": variables, "panels": panels + runtime(namespace) + log_panels(namespace)})
    dashboard["tags"] = ["monitoring", "applications", "metrics", "logs"]
    dashboard["templating"]["list"][0] = variable("cluster", "kube_pod_info", "cluster", f'namespace=~"{namespace}"')
    # Freshness belongs to the application scope, not unrelated cluster targets.
    fresh = dashboard["panels"][1]
    fresh["targets"][0]["expr"] = f'max(clamp_min(time() - timestamp({freshness or metric("kube_pod_info", f"namespace=~\"{namespace}\"")}), 0))'
    fresh["title"] = "Oldest application telemetry sample"
    fresh["description"] = "Age of currently visible application telemetry. Disappeared targets cannot be detected by sample age alone. N/A means missing data."
    for p in dashboard["panels"]:
        if p["type"] == "table" and "namespace" in p["targets"][0]["expr"]:
            p["fieldConfig"]["defaults"]["links"] = [{"title": "Pod diagnostics", "url": "/d/mon-pod?${__url_time_range}&var-cluster=${__data.fields.cluster}&var-namespace=${__data.fields.namespace}&var-pod=${__data.fields.pod}", "targetBlank": False}]
    return dashboard


def unifi_logs(title, selector, description):
    result = logs(title, selector + ' |= ${search:doublequote}', description)
    result["fieldConfig"]["defaults"]["noValue"] = "No matching UniFi events"
    return result


def protect_state_table():
    result = mapped_table(
        "Protect device state",
        'max by (cluster,source,name,type,model_key) (unpoller_protect_device_state{cluster=~"$cluster"})',
        "Connection state reported by Protect. Unknown is explicit source data, not missing telemetry.",
        {-1: "Unknown", 0: "Disconnected", 1: "Connecting", 2: "Connected"},
        sort_desc=False,
    )
    colors = {"-1": "#FFB357", "0": "red", "1": "#FFB357", "2": "green"}
    for value, color in colors.items():
        result["fieldConfig"]["defaults"]["mappings"][0]["options"][value]["color"] = color
    result["fieldConfig"]["defaults"]["custom"]["cellOptions"] = {"type": "color-text"}
    return result


def make_unifi(uid, title, panels, purpose, variables=None):
    variables = variables or []
    variables.append({"name": "search", "label": "Log contains", "type": "textbox", "query": "", "current": {"text": "", "value": ""}, "skipUrlSync": False})
    dashboard = build({"uid": uid, "title": title, "purpose": purpose, "from": "now-1h", "refresh": "1m", "category_title": "UniFi", "category_tag": "unifi", "vars": variables, "panels": panels})
    dashboard["tags"] = ["monitoring", "unifi", "metrics", "logs"]
    dashboard["templating"]["list"][0] = variable("cluster", "unpoller_controller_up", "cluster")
    freshness = dashboard["panels"][1]
    freshness["targets"][0]["expr"] = 'max(clamp_min(time() - timestamp(unpoller_prometheus_cache_age_seconds{cluster=~"$cluster"}), 0))'
    freshness["title"] = "Oldest UniFi collector sample"
    freshness["description"] = "Age of the latest cached UnPoller sample. N/A means that the collector has not delivered this metric."
    return reset_layout(dashboard)


def unifi_dashboards():
    site = 'cluster=~"$cluster",site_name=~"$site"'
    network_devices = 'max without (tag) (unpoller_device_info{cluster=~"$cluster"})'
    port_rx = f'max without (tag) (unpoller_device_port_receive_rate_bytes{{{site}}})'
    port_tx = f'max without (tag) (unpoller_device_port_transmit_rate_bytes{{{site}}})'
    port_errors = (
        f'max without (tag) ('
        f'increase(unpoller_device_port_receive_errors_total{{{site}}}[$__range]) + '
        f'increase(unpoller_device_port_transmit_errors_total{{{site}}}[$__range]) + '
        f'increase(unpoller_device_port_receive_dropped_total{{{site}}}[$__range]) + '
        f'increase(unpoller_device_port_transmit_dropped_total{{{site}}}[$__range]))'
    )
    port_poe = f'max without (tag) (unpoller_device_port_poe_watts{{{site}}})'
    return {
        "unifi-overview.json": make_unifi("mon-unifi-overview", "UniFi Overview", [
            stat("UnPoller target", 'min(up{cluster=~"$cluster",job="unpoller"})', "Reachability of the UnPoller Prometheus endpoint. This does not prove controller login success.", threshold="ready"),
            stat("Controller collection", 'min(unpoller_controller_up{cluster=~"$cluster"})', "Lowest reported controller status.", threshold="ready"),
            stat("Collector cache age", 'max(unpoller_prometheus_cache_age_seconds{cluster=~"$cluster"})', "Age of the cached controller data.", "s", "freshness"),
            stat("Refresh failures", 'sum(increase(unpoller_prometheus_refresh_failures_total{cluster=~"$cluster"}[$__range]))', "Refresh failures in the selected range.", threshold="warning"),
            stat("Network devices", f'count({network_devices})', "Observed adopted Network devices, deduplicated across UniFi device tags."),
            stat("Protect devices", 'sum(unpoller_protect_device_present{cluster=~"$cluster"})', "Protect devices returned by the controller."),
            stat("UNAS consoles", 'sum(unpoller_unas_device_present{cluster=~"$cluster"})', "UNAS consoles returned by the storage API."),
            stat("UniFi Alloy target", 'min(up{cluster=~"$cluster",job="alloy-unpoller"})', "Scrape status for the dedicated UniFi Alloy instance.", threshold="ready"),
            log_query(chart("SIEM event volume", [], "Incoming UDM and UNAS SIEM records per second.", "logs/s"), 'sum by (cluster,appliance) (rate({cluster=~"$cluster",source="unifi-siem"}[$__auto]))', '{{cluster}} {{appliance}}'),
            log_query(chart("API event volume", [], "Events obtained from supported UniFi APIs.", "logs/s"), 'sum by (cluster) (rate({cluster=~"$cluster",source="unpoller-api"}[$__auto]))', '{{cluster}}'),
            unifi_logs("Recent UniFi security and system events", '{cluster=~"$cluster",source=~"unifi-siem|unpoller-api"}', "Sanitized SIEM and API records. Image payloads are disabled."),
        ], "Health and event intake for the dedicated ADMIN01 UniFi monitoring path."),
        "unifi-network.json": make_unifi("mon-unifi-network", "UniFi Network", [
            stat("Gateways", f'sum(unpoller_site_gateways{{{site}}})', "Gateways reported for the selected sites."),
            stat("Switches", f'sum(unpoller_site_switches{{{site}}})', "Switches reported for the selected sites."),
            stat("Access points", f'sum(unpoller_site_aps{{{site}}})', "Access points reported for the selected sites."),
            stat("Stations", f'sum(unpoller_site_stations{{{site}}})', "Associated stations reported for the selected sites."),
            chart("Site traffic", [(f'sum by (cluster,site_name) (unpoller_site_receive_rate_bytes{{{site}}})', 'receive {{cluster}} {{site_name}}'), (f'sum by (cluster,site_name) (unpoller_site_transmit_rate_bytes{{{site}}})', 'transmit {{cluster}} {{site_name}}')], "Current site receive and transmit rates.", "Bps", width=24),
            chart("Switch port traffic", [(f'sum by (cluster,name,port_name) ({port_rx})', 'receive {{name}} {{port_name}}'), (f'sum by (cluster,name,port_name) ({port_tx})', 'transmit {{name}} {{port_name}}')], "Per-port receive and transmit rates, deduplicated across UniFi device tags.", "Bps", width=24),
            table("Switch port errors and drops", f'sum by (cluster,site_name,name,port_name) ({port_errors})', "Combined error and drop increases, deduplicated across UniFi device tags.", threshold="warning"),
            gauge("PoE consumption", f'sum by (cluster,site_name,name,port_name) ({port_poe})', "Current power draw per PoE port, deduplicated across UniFi device tags.", "watt", "warm", legend="{{cluster}} {{name}} {{port_name}}"),
            chart("DPI traffic by category", [(f'sum by (cluster,site_name,category) (unpoller_client_dpi_receive_bytes{{{site}}})', 'receive {{site_name}} {{category}}'), (f'sum by (cluster,site_name,category) (unpoller_client_dpi_transmit_bytes{{{site}}})', 'transmit {{site_name}} {{category}}')], "DPI byte counters by category, aggregated across clients and applications.", "bytes", width=24),
            table("Rogue access point signal", f'max by (cluster,site_name,source,name,mac,security,band,ap_mac,radio,radio_name,oui) (unpoller_rogueap_rssi{{{site}}})', "Latest rogue-AP RSSI observations per detecting access point and radio.", "dBm", "warning"),
            table("Rogue access point channel", f'max by (cluster,site_name,source,name,mac,security,band,ap_mac,radio,radio_name,oui) (unpoller_rogueap_channel{{{site}}})', "Latest channel reported per rogue access point observation."),
            unifi_logs("IDS, IPS and Network events", '{cluster=~"$cluster",source=~"unifi-siem|unpoller-api"} |~ "(?i)ids|ips|threat|intrusion|rogue|network"', "Detailed security and Network records."),
        ], "Network inventory, traffic, DPI, switch ports, rogue access points and IDS or IPS details.", [variable("site", "unpoller_site_aps", "site_name", 'cluster=~"$cluster"')]),
        "unifi-protect.json": make_unifi("mon-unifi-protect", "UniFi Protect", [
            stat("Protect devices", 'sum(unpoller_protect_device_present{cluster=~"$cluster"})', "Protect devices returned by the controller."),
            stat("Disconnected devices", 'count(unpoller_protect_device_state{cluster=~"$cluster"} == 0)', "Devices explicitly reporting disconnected state.", threshold="warning"),
            protect_state_table(),
            table("Low sensor batteries", 'max by (cluster,source,name,type,model_key) (unpoller_protect_sensor_battery_low{cluster=~"$cluster"} == 1)', "Sensors explicitly reporting a low battery.", threshold="warning"),
            chart("Sensor battery", [('unpoller_protect_sensor_battery_percent{cluster=~"$cluster"}', '{{cluster}} {{name}}')], "Battery percentage where supported.", "percent"),
            chart("Sensor environment", [('unpoller_protect_sensor_temperature_celsius{cluster=~"$cluster"}', 'temperature {{name}}'), ('unpoller_protect_sensor_humidity_percent{cluster=~"$cluster"}', 'humidity {{name}}')], "Temperature and humidity where supported."),
            table("Open sensors", 'max by (cluster,source,name,type) (unpoller_protect_sensor_is_opened{cluster=~"$cluster"})', "Open-state metadata only. No image or audio content is collected.", threshold="warning"),
            table("Motion sensors", 'max by (cluster,source,name,type) (unpoller_protect_sensor_is_motion_detected{cluster=~"$cluster"})', "Motion-state metadata only. No image or audio content is collected.", threshold="warning"),
            unifi_logs("Protect events", '{cluster=~"$cluster",source="unpoller-api"} |~ "(?i)protect|camera|sensor|doorbell|nvr"', "Protect event metadata without thumbnails or images."),
        ], "Protect device state and event metadata without thumbnails, snapshots, video or audio payloads."),
        "unifi-unas.json": make_unifi("mon-unifi-unas", "UniFi UNAS", [
            stat("UNAS reachable", 'min(unpoller_unas_device_present{cluster=~"$cluster"})', "UNAS consoles returned by the API.", threshold="ready"),
            gauge("CPU load", 'max by (cluster,source,name) (unpoller_unas_cpu_load_percent{cluster=~"$cluster"})', "Current console CPU load.", "percent", "percent", legend="{{cluster}} {{name}}"),
            gauge("Memory use", '100 * (1 - max by (cluster,source,name) (unpoller_unas_memory_available_bytes{cluster=~"$cluster"}) / max by (cluster,source,name) (unpoller_unas_memory_total_bytes{cluster=~"$cluster"}))', "Used memory based on available versus total.", "percent", "percent", legend="{{cluster}} {{name}}"),
            gauge("Pool occupancy", '100 * max by (cluster,source,name,pool_id,pool_type,status) (unpoller_unas_pool_usage_bytes{cluster=~"$cluster"}) / max by (cluster,source,name,pool_id,pool_type,status) (unpoller_unas_pool_capacity_bytes{cluster=~"$cluster"})', "Used versus total pool capacity.", "percent", "percent", legend="{{cluster}} {{name}} {{pool_id}}"),
            table("RAID protection gap", 'max by (cluster,source,name,pool_id,raid_group_id,current_level,config_level) (unpoller_unas_raid_group_expected_protection{cluster=~"$cluster"} - unpoller_unas_raid_group_current_protection{cluster=~"$cluster"})', "Positive values mean current protection is below expected.", threshold="warning"),
            chart("RAID operation progress", [('unpoller_unas_raid_group_progress_percent{cluster=~"$cluster"}', '{{cluster}} {{name}} {{pool_id}} {{raid_group_id}}')], "Rebuild or expansion progress.", "percent", width=24),
            table("Disk health", 'min by (cluster,source,name,slot_id,pool_id,disk_type,state,model,serial) (unpoller_unas_disk_health_score{cluster=~"$cluster"})', "Health score reported by UNAS. The state label carries the appliance classification; the score remains quantitative rather than inventing local health thresholds."),
            chart("Disk temperature", [('unpoller_unas_disk_temperature_celsius{cluster=~"$cluster"}', '{{cluster}} {{name}} slot {{slot_id}}')], "Physical disk temperature.", "celsius"),
            table("Disk media errors", 'max by (cluster,source,name,slot_id,pool_id,model,serial) (unpoller_unas_disk_bad_sectors{cluster=~"$cluster"} + unpoller_unas_disk_uncorrectable_sectors{cluster=~"$cluster"} + unpoller_unas_disk_smart_read_errors{cluster=~"$cluster"})', "Combined bad, uncorrectable and SMART read-error counts.", threshold="warning"),
            unifi_logs("UNAS SIEM events", '{cluster=~"$cluster",source="unifi-siem",appliance="unas"}', "Sanitized SIEM records sent directly by UNAS."),
        ], "UNAS console, pools, RAID groups, disks, shares and direct SIEM records."),
    }


def state_colors(p):
    p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    p["fieldConfig"]["defaults"]["mappings"] = [{"type": "value", "options": {
        "0": {"text": "Down", "color": "red"},
        "1": {"text": "Up", "color": "green"},
        "2": {"text": "Pending", "color": "orange"},
        "3": {"text": "Maintenance", "color": "orange"},
    }}]
    return p


def history(title, expr, legend, height=18):
    p = state_colors(panel("status-history", title, [query(expr, legend)], "Sampled monitor status in time. Green=up, red=down, amber=pending or maintenance. Gaps are missing telemetry. History begins when collection started, not when the monitor was created.", width=24, height=height))
    p["maxDataPoints"] = 120
    p["fieldConfig"]["defaults"]["custom"] = {"fillOpacity": 100, "lineWidth": 0, "axisWidth": 360}
    p["options"] = {"colWidth": 0.85, "rowHeight": 0.75, "perPage": 20, "showValue": "never", "legend": {"showLegend": False}, "tooltip": {"mode": "single", "sort": "none"}}
    return p


def binary_history(title, expr, legend, description, height=10):
    p = panel("status-history", title, [query(expr, legend)], description, width=24, height=height)
    p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
    p["fieldConfig"]["defaults"]["mappings"] = [{"type": "value", "options": {
        "0": {"text": "Down", "color": "red"},
        "1": {"text": "Up", "color": "green"},
    }}]
    p["fieldConfig"]["defaults"]["custom"] = {"fillOpacity": 100, "lineWidth": 0, "axisWidth": 180}
    p["maxDataPoints"] = 120
    p["options"] = {"colWidth": 0.85, "rowHeight": 0.75, "showValue": "never", "legend": {"showLegend": False}, "tooltip": {"mode": "single", "sort": "none"}}
    return p


def reset_layout(dashboard):
    for i, p in enumerate(place(dashboard["panels"]), 1):
        p["id"] = i
    return dashboard


def disk_panels(namespace):
    scope = f'{C},namespace="{namespace}"'
    items = [(f'max by (cluster,persistentvolumeclaim) (kubelet_volume_stats_used_bytes{{{scope}}})', 'used {{cluster}} {{persistentvolumeclaim}}'), (f'max by (cluster,persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{{{scope}}})', 'capacity {{cluster}} {{persistentvolumeclaim}}')]
    description = "Filesystem usage including WAL and index overhead. Provisioned capacity is not data size."
    if namespace == "monitoring-metrics":
        items.append((f'max(kubelet_volume_stats_capacity_bytes{{{scope}}}) - max(vm_free_disk_space_limit_bytes{{{C},job="victoriametrics"}})', 'write-stop threshold'))
        description += " The write-stop threshold is provisioned capacity minus VictoriaMetrics' configured free-space reserve."
    return [
        chart("Persistent storage", items, description, "bytes", width=24),
    ]


def dashboards():
    scope = f'{C},namespace=~"$namespace"'
    result = {}
    result["applications-overview.json"] = make("mon-app-overview", "Applications Overview", "$namespace", [
        stat("Observed application pods", f'count(kube_pod_info{{{scope}}})', "Observed inventory, not a fixed expected count."),
        stat("Containers not ready", f'sum(1 - kube_pod_container_status_ready{{{scope}}})', "Containers in the observed inventory which are not ready.", threshold="critical"),
        stat("Restarts in range", f'sum(increase(kube_pod_container_status_restarts_total{{{scope}}}[$__range]))', "Use the detail table below to locate affected containers.", threshold="warning"),
        stat("Observed scrape failures", f'count(up{{{scope}}}) - sum(up{{{scope}}})', "Only observed application endpoints carrying a namespace label. Exporter backend health is separate.", threshold="critical"),
        table("Application container readiness", f'min by (cluster,namespace,pod,container) (kube_pod_container_status_ready{{{scope}}})', "Includes applications with no native metrics, such as Homepage and Scrypted.", threshold="ready", sort_desc=False),
        table("Application scrape health", f'min by (cluster,namespace,job,pod) (up{{{scope}}})', "Scrape reachability does not prove backend health.", threshold="ready", sort_desc=False),
        table("Namespace resource quota utilization", f'100 * max by (cluster,namespace,resource) (kube_resourcequota{{{scope},type="used"}}) / clamp_min(max by (cluster,namespace,resource) (kube_resourcequota{{{scope},type="hard"}}), 0.000001)', "Used versus hard namespace quota for Pods, PVCs, CPU or memory where a ResourceQuota exists. Missing namespaces have no exported quota, not zero utilization.", "percent", "percent"),
    ], "Start with availability, then inspect workload resources and logs. Homepage and Scrypted have platform coverage only. Application dashboards provide native metrics where available. Central database details remain in PostgreSQL and Backups.", [variable("namespace", "kube_pod_info", "namespace", f'{C},namespace=~"{APP_NAMESPACES}"')])
    # Namespace must exist before it is used by dependent variables.
    result["applications-overview.json"]["templating"]["list"][0] = variable("cluster", "kube_pod_info", "cluster", f'namespace=~"{APP_NAMESPACES}"')
    result["applications-overview.json"]["templating"]["list"][1]["allValue"] = APP_NAMESPACES

    mon = metric("monitor_status", 'job="uptimekuma",monitor_id=~"$monitor"')
    win = 'job="uptimekuma",monitor_id=~"$monitor",window=~"$window"'
    result["uptime-kuma.json"] = make("mon-app-uptime", "Uptime Kuma", "uptimekuma", [
        stat("Selected monitors", f'count({mon})', "Monitors exported by Kuma, identified by monitor ID."),
        stat("Down monitors", f'sum({mon} == bool 0)', "DOWN only. Pending and maintenance are shown separately.", threshold="critical"),
        stat("Pending monitors", f'sum({mon} == bool 2)', "Pending monitor checks.", threshold="warning"),
        stat("Maintenance monitors", f'sum({mon} == bool 3)', "Maintenance is intentional, not a failure.", threshold="warning"),
        mapped_table("Monitor status", mon, "0 DOWN, 1 UP, 2 PENDING, 3 MAINTENANCE. This checks monitored services, not only the Kuma process.", {0: "Down", 1: "Up", 2: "Pending", 3: "Maintenance"}, sort_desc=False),
        table("Monitor availability", metric("monitor_uptime_ratio", win) + ' * 100', "Kuma's own rolling window. This is independent of the dashboard time range.", "percent", "availability", sort_desc=False),
        chart("Monitor response time", [(metric("monitor_response_time_seconds", win), '{{cluster}} {{monitor_name}} {{window}}')], "Kuma rolling mean, in seconds. Narrow the monitor selection for readability.", "s", width=24),
        table("Certificate days remaining", metric("monitor_cert_days_remaining", 'job="uptimekuma",monitor_id=~"$monitor"'), "Only monitors that report certificate metrics.", "d", "days", sort_desc=False),
        stat("MariaDB reachable", 'min(mysql_up{cluster=~"$cluster",job="integrations/mysql"})', "Database exporter connectivity, separate from HTTP scrape health.", threshold="ready"),
        trend("MariaDB connections", "mysql_global_status_threads_connected"),
        trend("MariaDB statements", "mysql_global_status_questions", "ops", True),
        trend("MariaDB slow queries", "mysql_global_status_slow_queries", "ops", True),
    ], "Monitor outcomes, rolling availability, latency and certificates. A successful scrape does not mean all monitored services are up. Database and application logs help explain failures.", [variable("monitor", "monitor_status", "monitor_id", C), variable("window", "monitor_uptime_ratio", "window", C)])

    result["authentik.json"] = make("mon-app-authentik", "Authentik", "authentik|authentik-outpost", [
        table("Server, worker and outpost targets", f'min by (cluster,namespace,job,pod,authentik_component) ({metric("up", "job=~\"authentik|authentik-outpost\"")})', "Scrape state for each observed process. Missing targets are not healthy zeros.", threshold="ready", sort_desc=False),
        trend("Server requests", "authentik_main_request_duration_seconds_count", "reqps", True),
        trend("Proxy requests", "authentik_outpost_proxy_request_duration_seconds_count", "reqps", True),
        trend("Tasks queued", "authentik_tasks_queued", labels="cluster,pod"),
        trend("Tasks in progress", "authentik_tasks_in_progress", labels="cluster,pod"),
        table("Outpost connectivity", metric("authentik_outpost_connection"), "Exporter-reported connection state. Inspect outpost logs for reconnection errors.", threshold="ready", sort_desc=False),
    ], "Server, worker and outpost health plus background task pressure. Logs support authentication incident diagnosis. Shared PostgreSQL health is available in PostgreSQL and Backups. No login identities or sessions are hardcoded.")

    result["grafana.json"] = make("mon-app-grafana", "Grafana and Renderer", "grafana", [
        table("Grafana and renderer scrape health", metric("up", 'job=~"grafana|grafana-renderer"'), "Observed native endpoints.", threshold="ready", sort_desc=False),
        trend("Grafana requests", "grafana_http_request_duration_seconds_count", "reqps", True),
        trend("Render queue", "grafana_rendering_queue_size"),
        trend("Active browser instances", "browser_instances_active", extra='job="grafana-renderer"'),
        trend("Completed render observations", "browser_render_duration_count", "ops", True, 'job="grafana-renderer"'),
        stat("Redis reachable", f'min({metric("redis_up", "job=\"integrations/redis\"")})', "Exporter connectivity to Grafana Redis.", threshold="ready"),
        trend("Redis memory", "redis_memory_used_bytes", "bytes", extra='job="integrations/redis"'),
        trend("Redis operations", "redis_commands_processed_total", "ops", True, 'job="integrations/redis"'),
        trend("Redis evictions", "redis_evicted_keys_total", "ops", True, 'job="integrations/redis"'),
    ], "Grafana request load, renderer activity, Redis and resource pressure. Container memory includes the renderer. Queue growth and restarts help explain slow dashboards and failed renders.")

    result["home-assistant.json"] = make("mon-app-homeassistant", "Home Assistant and MQTT", "homeassistant", [
        stat("Core scrape healthy", f'min({metric("up", "job=\"homeassistant\"")})', "Prometheus endpoint reachability, not health of every integration.", threshold="ready"),
        stat("Unavailable or unknown entities", f'sum({metric("homeassistant_entity_available")} == bool 0)', "Home Assistant exports availability=0 for BOTH unavailable and unknown states. This is not a count of offline devices. Unknown can be normal for event-only entities.", threshold="warning"),
        stat("MQTT exporter connected", f'min({metric("mosquitto_broker_connected")})', "The exporter must connect to the broker, not merely serve HTTP.", threshold="ready"),
        stat("MQTT clients", f'sum({metric("broker_clients_connected")})', "Currently connected clients."),
        trend("Automation triggers", "homeassistant_automation_triggered_count_total", "ops", True),
        trend("MQTT publish drops", "broker_publish_messages_dropped_total", "ops", True),
        trend("MQTT messages received", "broker_messages_received_total", "ops", True),
        trend("MQTT messages sent", "broker_messages_sent_total", "ops", True),
        table("Entities reported unavailable or unknown", metric("homeassistant_entity_available") + ' == 0', "The exported metric cannot distinguish unavailable from unknown. Check the current entity state in Home Assistant. Entity series may lag a live state transition."),
        chart("HistoryDB ingestion", [(f'sum(rate({metric("vm_rows_inserted_total", "job=\"home-assistant-historydb\"")}[$__rate_interval]))', "rows")], "HistoryDB is a separate VictoriaMetrics instance, not the shared CNPG database.", "ops"),
        chart("HistoryDB data size", [(f'sum({metric("vm_data_size_bytes", "job=\"home-assistant-historydb\"")})', "data")], "Compressed HistoryDB storage, not PVC capacity.", "bytes"),
    ], "Operational Home Assistant and MQTT health. No occupancy, device-tracker, camera or sensor readings are displayed. Entity names may appear as runtime diagnostics. HistoryDB is VictoriaMetrics.")

    result["homecdn-timeserver.json"] = make("mon-app-services", "HomeCDN and Timeserver", "homecdn|timeserver", [
        table("Exporter scrape health", metric("up", 'namespace=~"homecdn|timeserver",job="kubernetes-applications"'), "HTTP exporter reachability, separate from successful backend collection.", threshold="ready", sort_desc=False),
        table("NGINX backend health", metric("nginx_up"), "Whether the exporter can read NGINX stub_status.", threshold="ready", sort_desc=False),
        table("Chrony backend health", metric("chrony_up"), "0 means the exporter cannot collect from chronyd. It does not prove clock desynchronization. Offset and stratum cannot be claimed when collection fails.", threshold="ready", sort_desc=False),
        trend("NGINX requests", "nginx_http_requests_total", "reqps", True),
        trend("NGINX active connections", "nginx_connections_active"),
        trend("NGINX waiting connections", "nginx_connections_waiting"),
        trend("NGINX writing connections", "nginx_connections_writing"),
    ], "Web serving and time-service diagnostics. stub_status does not expose HTTP status codes or traffic bytes. Chrony collection health is distinct from clock synchronization. Use logs when backend collection fails.")
    status = next(p for p in result["uptime-kuma.json"]["panels"] if p["title"] == "Monitor status")
    window = next(v for v in result["uptime-kuma.json"]["templating"]["list"] if v["name"] == "window")
    window["current"] = {"selected": True, "text": "1d", "value": "1d"}
    window["multi"] = False
    window["includeAll"] = False
    # Pending and maintenance are not failures.
    for value, color in {"0": "red", "1": "green", "2": "orange", "3": "orange"}.items():
        status["fieldConfig"]["defaults"]["mappings"][0]["options"][value]["color"] = color
    status["fieldConfig"]["overrides"].append({"matcher": {"id": "byName", "options": "Value"}, "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}]})

    # Separate monitor outcomes from the health of the Kuma application itself.
    outcomes = result["uptime-kuma.json"]["panels"][2:10]
    monitor_selector = 'job="uptimekuma",monitor_id=~"$monitor",monitor_type=~"$monitor_type"'
    values = metric("monitor_status", monitor_selector)
    monitor_dashboard = build({
        "uid": "mon-app-uptime-monitors", "title": "Uptime Kuma Monitors", "from": "now-1h", "refresh": "1m",
        "category_title": "Application", "category_tag": "applications",
        "vars": [variable("monitor", "monitor_status", "monitor_id", C), variable("monitor_type", "monitor_status", "monitor_type", C), copy.deepcopy(window)],
        "purpose": "Control-room view of Kuma monitors, with sampled status history and rolling availability. Group monitors are separate from individual monitors. Prometheus does not expose the parent-child hierarchy, so nested groups cannot be reconstructed. Monitor type and ID filters apply throughout. Missing history is never painted green.",
        "panels": [*copy.deepcopy(outcomes[:4]),
            history("Group monitor history", 'sort_by_label(max by (cluster,monitor_name,monitor_id) (' + metric("monitor_status", monitor_selector + ',monitor_type="group"') + '), "monitor_name", "cluster")', '{{monitor_name}} · {{cluster}} · #{{monitor_id}}', 14),
            history("Monitor status history", 'sort_by_label(max by (cluster,monitor_name,monitor_id) (' + metric("monitor_status", monitor_selector + ',monitor_type!="group"') + '), "monitor_name", "cluster")', '{{monitor_name}} · {{cluster}} · #{{monitor_id}}'),
            *copy.deepcopy(outcomes[4:])],
    })
    monitor_dashboard["tags"] = ["monitoring", "applications", "metrics"]
    monitor_dashboard["templating"]["list"][0] = variable("cluster", "monitor_status", "cluster")
    monitor_dashboard["panels"][1]["targets"][0]["expr"] = 'max(clamp_min(time() - timestamp(' + metric("up", 'job="uptimekuma"') + '), 0))'
    for p in monitor_dashboard["panels"]:
        for t in p.get("targets", []):
            if 'monitor_id=~"$monitor"' in t["expr"] and 'monitor_type=~"$monitor_type"' not in t["expr"]:
                t["expr"] = t["expr"].replace('monitor_id=~"$monitor"', 'monitor_id=~"$monitor",monitor_type=~"$monitor_type"')
        if p["type"] == "table" and p["title"] == "Monitor status":
            state_colors(p)
        if p["type"] == "table":
            for t in p["targets"]:
                t["expr"] = 'sort_by_label(max by (cluster,monitor_name,monitor_id,monitor_type) (' + t["expr"] + '), "monitor_name", "cluster")'
            p["fieldConfig"]["overrides"].append({"matcher": {"id": "byName", "options": "monitor_id"}, "properties": [{"id": "unit", "value": "string"}, {"id": "mappings", "value": []}]})
            p["transformations"] = [{"id": "organize", "options": {"excludeByName": {"Time": True}, "indexByName": {"monitor_name": 0, "Value": 1, "cluster": 2, "monitor_type": 3, "monitor_id": 4}}}]
    result["uptime-kuma-monitors.json"] = monitor_dashboard
    result["uptime-kuma.json"] = make("mon-app-uptime", "Uptime Kuma", "uptimekuma", [
        stat("Application scrape healthy", 'min(up{cluster=~"$cluster",job="uptimekuma"})', "Kuma metrics HTTP endpoint.", threshold="ready"),
        stat("MariaDB reachable", 'min(mysql_up{cluster=~"$cluster",job="integrations/mysql"})', "Exporter connection to the database.", threshold="ready"),
        stat("Process uptime", 'time() - max(process_start_time_seconds{cluster=~"$cluster",job="uptimekuma"})', "Time since the most recently started Kuma process.", "s"),
        stat("Database connections", 'sum(mysql_global_status_threads_connected{cluster=~"$cluster",job="integrations/mysql"})', "Current database connections."),
        trend("MariaDB statements", "mysql_global_status_questions", "ops", True),
        trend("MariaDB slow queries", "mysql_global_status_slow_queries", "ops", True),
        chart("Node.js event loop delay", [(metric("nodejs_eventloop_lag_p99_seconds", 'job="uptimekuma"'), '{{cluster}}')], "Exporter-reported p99 event loop delay.", "s"),
        chart("Database uptime", [(metric("mysql_global_status_uptime", 'job="integrations/mysql"'), '{{cluster}}')], "Database uptime in seconds.", "s"),
    ], "Health of Kuma itself and its database. Monitor outcomes have their own Uptime Kuma Monitors dashboard. A quiet hour can contain no logs, so missing logs alone are not evidence of failed delivery.")

    # Keep the existing combined dashboard UID for HomeCDN to avoid orphaning links.
    del result["homecdn-timeserver.json"]
    result["homecdn.json"] = make("mon-app-services", "HomeCDN", "homecdn", [
        stat("NGINX reachable", 'min(nginx_up{cluster=~"$cluster"})', "Exporter can collect stub_status.", threshold="ready"),
        stat("Active connections", 'sum(nginx_connections_active{cluster=~"$cluster"})', "Current connections."),
        trend("Requests", "nginx_http_requests_total", "reqps", True),
        trend("Waiting connections", "nginx_connections_waiting"),
        trend("Reading connections", "nginx_connections_reading"),
        trend("Writing connections", "nginx_connections_writing"),
    ], "NGINX serving activity and workload health. stub_status does not export HTTP response codes, bandwidth or cache-hit ratios. Logs and resource panels provide operational context.")
    for title in ("NGINX reachable", "Active connections"):
        next(p for p in result["homecdn.json"]["panels"] if p["title"] == title)["gridPos"].update({"h": 4, "w": 12})
    result["timeserver.json"] = make("mon-app-timeserver", "Timeserver (Chrony)", "timeserver", [
        table("Chrony collection healthy", metric("chrony_up"), "1 means chronyd replied to collection requests, not that its clock is synchronized.", threshold="ready", sort_desc=False),
        table("Remote time reference", metric("chrony_tracking_remote_reference"), "Whether Chrony reports a remote source rather than local reference.", threshold="ready", sort_desc=False),
        table("Stratum", metric("chrony_tracking_stratum"), "Stratum hierarchy is not a direct accuracy score. Zero means unsynchronized."),
        chart("Clock offset", [(metric("chrony_tracking_last_offset_seconds"), '{{cluster}} last'), (metric("chrony_tracking_rms_offset_seconds"), '{{cluster}} RMS')], "Last and RMS offset in seconds. Negative values are valid.", "s"),
        chart("Root delay and dispersion", [(metric("chrony_tracking_root_delay_seconds"), '{{cluster}} delay'), (metric("chrony_tracking_root_dispersion_seconds"), '{{cluster}} dispersion')], "Path delay and estimated accumulated measurement error.", "s"),
        chart("Reference age", [('time() - ' + metric("chrony_tracking_reference_timestamp_seconds"), '{{cluster}}')], "Age of the last reference update. Compare with the tracking update interval.", "s"),
        chart("Frequency correction", [(metric("chrony_tracking_frequency_ppms"), '{{cluster}}')], "Clock frequency correction in parts per million.", "ppm"),
    ], "Chrony time synchronization, collection health and resource usage. Both collection and remote-reference state matter. A read-only socket directory prevents exporter communication. Clock offset and dispersion should be interpreted after startup settling.")

    result["loki.json"] = make("mon-app-loki", "Monitoring Logs (Loki)", "monitoring-logs", [
        stat("Loki scrape healthy", 'min(up{cluster=~"$cluster",job="loki"})', "Backend metrics reachability.", threshold="ready"),
        stat("Compactor running", 'max(loki_boltdb_shipper_compactor_running{cluster=~"$cluster",job="loki"})', "Retention compactor running state.", threshold="ready"),
        stat("Retention success age", 'time() - max(loki_compactor_apply_retention_last_successful_run_timestamp_seconds{cluster=~"$cluster",job="loki"} > 0)', "Seconds since a successful retention pass, not proof of restoreability.", "s"),
        stat("Rejected entries in range", 'sum(increase(loki_discarded_samples_total{cluster=~"$cluster",job="loki"}[$__range]))', "Rejected lines, separate from intentional agent exclusions.", threshold="critical"),
        trend("Received log bytes", "loki_distributor_bytes_received_total", "Bps", True, 'job="loki"'),
        trend("Received log entries", "loki_distributor_lines_received_total", "logs/s", True, 'job="loki"'),
        chart("HTTP requests by status", [('sum by (cluster,status_code) (rate(loki_request_duration_seconds_count{cluster=~"$cluster",job="loki"}[$__rate_interval]))', '{{cluster}} {{status_code}}')], "HTTP request outcomes.", "reqps"),
        trend("In-memory chunks", "loki_ingester_memory_chunks", extra='job="loki"'),
        *disk_panels("monitoring-logs"),
    ], "The central Loki application: ingestion, requests, retention, storage, resources and backend logs. Cluster selects the hosting cluster. Agent delivery and privacy exclusions remain in Log Pipeline Health.")
    result["victoriametrics.json"] = make("mon-app-victoriametrics", "Monitoring Metrics (VictoriaMetrics)", "monitoring-metrics", [
        stat("Backend scrape healthy", 'min(up{cluster=~"$cluster",job="victoriametrics"})', "Central metrics endpoint reachability.", threshold="ready"),
        stat("Storage read-only", 'max(vm_storage_is_read_only{cluster=~"$cluster",job="victoriametrics"})', "Read-only storage stops ingestion.", threshold="critical"),
        stat("Free disk", 'min(vm_free_disk_space_bytes{cluster=~"$cluster",job="victoriametrics"})', "Filesystem bytes available.", "bytes"),
        stat("Free-space reserve", 'max(vm_free_disk_space_limit_bytes{cluster=~"$cluster",job="victoriametrics"})', "Ingestion stops when free space drops below this reserve.", "bytes"),
        trend("Rows inserted", "vm_rows_inserted_total", "ops", True, 'job="victoriametrics"'),
        trend("Invalid rows", "vm_rows_invalid_total", "ops", True, 'job="victoriametrics"'),
        trend("Query requests", "vm_http_requests_total", "reqps", True, 'job="victoriametrics"'),
        trend("Query errors", "vm_http_request_errors_total", "reqps", True, 'job="victoriametrics"'),
        *disk_panels("monitoring-metrics"),
    ], "Central VictoriaMetrics service and auth-proxy workload logs. HistoryDB is explicitly excluded. Cluster selects the backend hosting cluster. Use Collection and Metrics Backend for per-cluster Alloy delivery queues.")

    pg = next(s for s in DASHBOARDS if s["uid"] == "mon-postgres")
    result["postgresql.json"] = make("mon-postgres", "PostgreSQL and Backups", "$namespace", copy.deepcopy(pg["panels"]), "CloudNativePG-managed PostgreSQL readiness, collectors, replication, backups, workload resources and logs. This is the single PostgreSQL dashboard and is provisioned under Monitoring Applications.", copy.deepcopy(pg["vars"]))
    result["postgresql.json"]["templating"]["list"][0] = variable("cluster", "cnpg_resource_instances_desired", "cluster")
    # Expand All to the discovered database namespaces, never every namespace.
    result["postgresql.json"]["templating"]["list"][1]["allValue"] = ""
    return {name: reset_layout(d) for name, d in result.items()}


def operations_center():
    spec = {
        "uid": "mon-operations-center", "title": "Operations Center", "from": "now-1h", "refresh": "1m", "vars": [],
        "category_title": "Operations", "category_tag": "operations",
        "purpose": "Fleet operations at a glance. Read left to right: cluster readiness, active incidents, service history, capacity and telemetry delivery. Green means an observed healthy signal, not guaranteed total coverage. N/A means missing evidence. Use the links for focused diagnostics.",
        "panels": [
            stat("Observed clusters", 'count(count by (cluster) (kube_node_info{cluster=~"$cluster"}))', "Clusters reporting node inventory. Compare with your expected fleet, missing clusters are not automatically detected."),
            stat("Nodes not ready", 'sum(kube_node_status_condition{cluster=~"$cluster",condition="Ready",status="true"} == bool 0)', "Not-ready nodes in observed inventory.", threshold="critical"),
            stat("Application monitors down", 'sum(monitor_status{cluster=~"$cluster",monitor_type!="group"} == bool 0)', "Individual Kuma monitors DOWN. Group monitors excluded to avoid counting incidents twice.", threshold="critical"),
            stat("Containers not ready", 'sum((1 - kube_pod_container_status_ready{cluster=~"$cluster"}) * on (cluster,namespace,pod) group_left() max by (cluster,namespace,pod) (kube_pod_status_phase{cluster=~"$cluster",phase=~"Pending|Running"} == 1))', "Unready containers in pending or running pods, including system workloads. Completed jobs are excluded.", threshold="warning"),
            stat("Monitors needing attention", 'sum(monitor_status{cluster=~"$cluster",monitor_type!="group"} != bool 1) or (0 * count(monitor_status{cluster=~"$cluster",monitor_type!="group"}))', "Down, pending or maintenance monitors. Zero is valid while Kuma monitor telemetry is present.", threshold="warning"),
            stat("Storage volumes unhealthy", 'sum(longhorn_volume_robustness{cluster=~"$cluster",state!="healthy"} == 1) or (0 * count(longhorn_volume_robustness{cluster=~"$cluster"}))', "Current Longhorn volumes whose robustness state is not healthy.", threshold="critical"),
            stat("Database readiness gap", 'sum(clamp_min(cnpg_resource_instances_desired{cluster=~"$cluster"} - cnpg_resource_instances_ready{cluster=~"$cluster"}, 0))', "Desired minus ready CloudNativePG instances.", threshold="critical"),
            stat("Log drops last 5m", 'sum(increase(loki_write_dropped_entries_total{cluster=~"$cluster",job=~"alloy|alloy-logs"}[5m]))', "New delivery drops in the last five minutes. Use Log Pipeline Health for range and reason detail.", threshold="critical"),
            gauge("Node readiness by cluster", '100 * sum by (cluster) (kube_node_status_condition{cluster=~"$cluster",condition="Ready",status="true"}) / count by (cluster) (kube_node_info{cluster=~"$cluster"})', "Ready nodes as a fraction of current cluster inventory.", "percent", "availability", legend="{{cluster}}", height=8),
            gauge("Deployment availability by cluster", '100 * sum by (cluster) (kube_deployment_status_replicas_available{cluster=~"$cluster"}) / clamp_min(sum by (cluster) (kube_deployment_spec_replicas{cluster=~"$cluster"}), 1)', "Available Deployment replicas divided by desired replicas. DaemonSets and StatefulSets have dedicated diagnostic dashboards.", "percent", "availability", legend="{{cluster}}", height=8),
            history("Service group status", 'sort_by_label(max by (cluster,monitor_name,monitor_id) (monitor_status{cluster=~"$cluster",monitor_type="group"}), "monitor_name", "cluster")', '{{monitor_name}} · {{cluster}}', 14),
            binary_history("Monitoring backend health", 'sort_by_label(min by (cluster,job) (up{cluster=~"$cluster",job=~"victoriametrics|vmauth|loki|logs-vmauth|grafana|uptimekuma"}), "job", "cluster")', '{{job}} · {{cluster}}', "Observed central monitoring endpoints over time. Green is reachable, red is unreachable and a gap means missing telemetry."),
            chart("Host resource pressure", [
                ('100 * (1 - avg by (cluster) (rate(node_cpu_seconds_total{cluster=~"$cluster",mode="idle"}[$__rate_interval])))', 'CPU · {{cluster}}'),
                ('100 * (1 - sum by (cluster) (node_memory_MemAvailable_bytes{cluster=~"$cluster"}) / sum by (cluster) (node_memory_MemTotal_bytes{cluster=~"$cluster"}))', 'Memory · {{cluster}}'),
            ], "Cluster-level CPU busy and host memory utilization. Use Cluster and Node Health for node-level diagnosis.", "percent", width=24),
            gauge("Persistent volume occupancy", 'topk(10, 100 * max by (cluster,namespace,persistentvolumeclaim) (kubelet_volume_stats_used_bytes{cluster=~"$cluster"}) / max by (cluster,namespace,persistentvolumeclaim) (kubelet_volume_stats_capacity_bytes{cluster=~"$cluster"}))', "Ten most occupied observed PVC filesystems.", "percent", "percent", legend="{{cluster}} · {{namespace}} · {{persistentvolumeclaim}}", height=10),
            gauge("Database readiness", '100 * cnpg_resource_instances_ready{cluster=~"$cluster"} / clamp_min(cnpg_resource_instances_desired{cluster=~"$cluster"}, 1)', "Ready versus desired CloudNativePG instances for each managed database cluster.", "percent", "availability", legend="{{cluster}} · {{namespace}} · {{cnpg_cluster}}", height=10),
            chart("Metrics delivery backlog", [('sum by (cluster) (prometheus_remote_storage_samples_pending{cluster=~"$cluster"})', '{{cluster}}')], "Short batches are normal. Persistent growth requires pipeline diagnosis."),
            chart("Log delivery drops", [('sum by (cluster) (rate(loki_write_dropped_entries_total{cluster=~"$cluster",job=~"alloy|alloy-logs"}[$__rate_interval]))', '{{cluster}}')], "Abandoned log entries, not deliberate privacy exclusions.", "logs/s"),
            gauge("Container restarts in range", 'topk(10, sum by (cluster,namespace,pod,container) (increase(kube_pod_container_status_restarts_total{cluster=~"$cluster"}[$__range])))', "Largest restart increases in the selected range. Zero-value series remain visible as healthy context.", "short", "warning", legend="{{cluster}} · {{namespace}} · {{pod}} · {{container}}", height=10),
            state_colors(table("Active monitor incident details", 'sort_by_label(max by (cluster,monitor_id,monitor_name,monitor_type) (monitor_status{cluster=~"$cluster",monitor_type!="group"} != 1), "monitor_name", "cluster")', "The only detail table on this overview. It lists down, pending and maintenance monitors. Empty is expected when the attention KPI is zero.")),
        ],
    }
    d = build(spec)
    for p in d["panels"]:
        if p["type"] == "bargauge":
            p["options"]["displayMode"] = "basic"
    next(p for p in d["panels"] if p["title"] == "Active monitor incident details")["fieldConfig"]["defaults"]["noValue"] = "No active monitor incidents"
    d["tags"] = ["monitoring", "operations", "metrics"]
    # Explicit links work even when Grafana's tag menu is collapsed in kiosk mode.
    for title, uid in [("Applications", "mon-app-overview"), ("UniFi", "mon-unifi-overview"), ("Monitors", "mon-app-uptime-monitors"), ("Metrics pipeline", "mon-pipeline"), ("Logs", "mon-log-explorer"), ("Storage", "mon-storage"), ("PostgreSQL", "mon-postgres")]:
        d["links"].append({"type": "link", "title": title, "url": f"/d/{uid}", "includeVars": True, "keepTime": True, "targetBlank": False})
    return d


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, dashboard in dashboards().items():
        (OUTPUT / name).write_text(json.dumps(dashboard, indent=2) + "\n")
        print(name)
    ROOT_OUTPUT.mkdir(parents=True, exist_ok=True)
    (ROOT_OUTPUT / "operations-center.json").write_text(json.dumps(operations_center(), indent=2) + "\n")
    UNIFI_OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, dashboard in unifi_dashboards().items():
        (UNIFI_OUTPUT / name).write_text(json.dumps(dashboard, indent=2) + "\n")
        print(name)


if __name__ == "__main__":
    main()
