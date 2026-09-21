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
    dashboard = build({"uid": uid, "title": title, "purpose": purpose, "from": "now-1h", "refresh": "1m", "category_title": "Monitoring Applications", "category_tag": "monitoring-applications", "vars": variables, "panels": panels + runtime(namespace) + log_panels(namespace)})
    dashboard["tags"] = ["monitoring", "monitoring-applications", "applications", "metrics", "logs"]
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


def dual_throughput_chart(title, series, description, width=24):
    """Show the same traffic truthfully in Bytes/s and bit/s without a second panel."""
    items = []
    for expr, legend in series:
        items.extend([
            (expr, f"{legend} Byte/s"),
            (f"8 * ({expr})", f"{legend} bit/s"),
        ])
    result = chart(title, items, description + " Byte/s is on the left axis; bit/s is on the right axis and is the primary network-rate unit.", "Bps", width=width)
    result["fieldConfig"]["defaults"]["custom"]["axisPlacement"] = "left"
    result["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byRegexp", "options": ".* bit/s$"},
        "properties": [
            {"id": "unit", "value": "bps"},
            {"id": "custom.axisPlacement", "value": "right"},
        ],
    })
    return result


def hide_table_time(dashboard):
    """Metric tables are instant queries, so their timestamp adds no useful detail."""
    for item in dashboard["panels"]:
        if item["type"] != "table":
            continue
        transformations = list(item.get("transformations") or [])
        transformations.append({"id": "organize", "options": {"excludeByName": {"Time": True}}})
        item["transformations"] = transformations
    return dashboard


def poe_draw_chart(scope):
    result = chart(
        "PoE draw",
        [(f'sum by (name) (unpoller_device_port_poe_watts{{{scope}}})', "PoE draw {{name}}")],
        "Current PoE consumption by switch. Series are stacked so the total PoE load remains visible; switch budgets are shown separately below.",
        "watt",
        width=24,
    )
    result["fieldConfig"]["defaults"]["custom"]["stacking"] = {"group": "A", "mode": "normal"}
    return result


def port_link_speed_table(scope):
    result = table("Port link speed", f'max by (location,site_name,name,port_name,port_num) (unpoller_device_port_port_speed_bps{{{scope}}})', "Negotiated port speed.", "bps")
    result["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byName", "options": "port_num"},
        "properties": [{"id": "unit", "value": "string"}, {"id": "decimals", "value": 0}],
    })
    return result


def radio_percentage_table(title, expr, description):
    """Keep the radio-band label numeric while formatting only the measurement as a percentage."""
    result = table(title, expr, description, "percent", "percent")
    result["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byName", "options": "band"},
        "properties": [{"id": "unit", "value": "string"}, {"id": "decimals", "value": 0}],
    })
    return result


def radio_band_table(title, expr, description, unit="short", threshold="warm"):
    """Render the numeric radio band consistently as an unformatted label."""
    result = table(title, expr, description, unit, threshold)
    result["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byName", "options": "band"},
        "properties": [{"id": "unit", "value": "string"}, {"id": "decimals", "value": 0}],
    })
    return result


def rogue_access_points_table(scope):
    """Join two equally labelled UniFi metrics so each rogue AP is a single row."""
    labels = "location,site_name,source,name,mac,security,band,ap_mac,radio,radio_name,oui"
    identity = ", ".join(
        f'"{label}"'
        for label in ("location", "site_name", "source", "name", "mac", "band", "ap_mac", "radio", "radio_name")
    )
    rssi = f'label_join(max by ({labels}) (unpoller_rogueap_rssi{{{scope}}}), "observation", " / ", {identity})'
    channel = f'label_join(max by ({labels}) (unpoller_rogueap_channel{{{scope}}}), "observation", " / ", {identity})'
    result = table(
        "Rogue access points",
        rssi,
        "Latest signal and channel reported for each rogue AP observation. Signal and channel share the same source, AP and radio identity.",
        "dBm",
        "warning",
    )
    rssi_target = query(rssi, interval="60s", instant=True, fmt="table")
    channel_target = query(channel, interval="60s", instant=True, fmt="table")
    channel_target["refId"] = "B"
    result["targets"] = [rssi_target, channel_target]
    result["transformations"] = [{
        "id": "joinByField",
        "options": {"byField": "observation", "mode": "outer"},
    }, {
        "id": "organize",
        "options": {
            "excludeByName": {},
            "indexByName": {},
            "renameByName": {"Value #A": "Signal (dBm)", "Value #B": "Channel"},
        },
    }]
    result["fieldConfig"]["overrides"].extend([
        {
            "matcher": {"id": "byName", "options": "band"},
            "properties": [{"id": "unit", "value": "string"}, {"id": "decimals", "value": 0}],
        }, {
            "matcher": {"id": "byName", "options": "Value #B"},
            "properties": [{"id": "unit", "value": "short"}, {"id": "decimals", "value": 0}],
        },
    ])
    return result


def full_width_poe_gauge(scope):
    result = gauge("PoE consumption", f'sum by (location,site_name,name,port_name) (max without (tag) (unpoller_device_port_poe_watts{{{scope}}}))', "Current power draw per PoE port, deduplicated across UniFi device tags.", "watt", "warm", legend="{{location}} {{name}} {{port_name}}")
    result["gridPos"]["w"] = 24
    return result


def protect_state_table(scope, title="Protect device state"):
    result = mapped_table(
        title,
        f'max by (location,source,name,type,model_key) (unpoller_protect_device_state{{{scope}}})',
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
    variables = list(variables or [])
    variables.append({"name": "search", "label": "Log contains", "type": "textbox", "query": "", "current": {"text": "", "value": ""}, "skipUrlSync": False})
    dashboard = build({"uid": uid, "title": title, "purpose": purpose, "from": "now-1h", "refresh": "1m", "category_title": "Monitoring UniFi", "category_tag": "monitoring-unifi", "vars": variables, "panels": panels})
    dashboard["tags"] = ["monitoring", "monitoring-unifi", "unifi", "metrics", "logs"]
    cluster = variable("cluster", "unpoller_controller_up", "cluster")
    cluster["hide"] = 2
    location = variable("location", "unpoller_controller_up", "location", 'cluster=~"$cluster"')
    dashboard["templating"]["list"] = [location, cluster, *dashboard["templating"]["list"][1:]]
    freshness = dashboard["panels"][1]
    freshness["targets"][0]["expr"] = 'max(clamp_min(time() - timestamp(unpoller_prometheus_cache_age_seconds{cluster=~"$cluster",location=~"$location"}), 0))'
    freshness["title"] = "Oldest UniFi collector sample"
    freshness["description"] = "Age of the latest cached UnPoller sample. N/A means that the collector has not delivered this metric."
    return hide_table_time(reset_layout(dashboard))


def unifi_dashboards():
    base = 'cluster=~"$cluster",location=~"$location"'
    site = f'{base},site_name=~"$site"'
    network_devices = f'max without (tag) (unpoller_device_info{{{base}}})'
    unifi_log_scope = '{cluster=~"$cluster",location=~"$location",source=~"unifi-siem|unpoller-api"}'
    camera_scope = f'{base},name=~"$camera"'
    camera_logs = '{cluster=~"$cluster",location=~"$location",source=~"unifi-siem|unpoller-api",unifi_application="UniFi Protect",camera=~"$camera"}'
    switch_scope = f'{site},name=~"$switch"'
    switch_port_scope = f'{switch_scope},port_name=~"$port"'
    ap_scope = f'{site},name=~"$ap"'
    lte_info = f'max by (cluster,location,site_name,name) (unpoller_device_info{{{site},model="ULTEPEU"}})'
    return {
        "unifi-overview.json": make_unifi("mon-unifi-overview", "UniFi Overview", [
            stat("UnPoller target", f'min(up{{{base},job="unpoller"}})', "Reachability of the UnPoller Prometheus endpoint. This does not prove controller login success.", threshold="ready"),
            stat("Controller collection", f'min(unpoller_controller_up{{{base}}})', "Lowest reported controller status.", threshold="ready"),
            stat("Collector cache age", f'max(unpoller_prometheus_cache_age_seconds{{{base}}})', "Age of the cached controller data.", "s", "age"),
            stat("Refresh failures", f'sum(increase(unpoller_prometheus_refresh_failures_total{{{base}}}[$__range]))', "Refresh failures in the selected range.", threshold="warning"),
            stat("Network devices", f'count({network_devices})', "Observed adopted Network devices, deduplicated across UniFi device tags."),
            stat("Protect devices", f'sum(unpoller_protect_device_present{{{base}}})', "Protect devices returned by the controller."),
            stat("UNAS consoles", f'sum(unpoller_unas_device_present{{{base}}})', "UNAS consoles returned by the storage API."),
            stat("UniFi Alloy target", 'min(up{cluster=~"$cluster",job="alloy-unpoller"})', "Scrape status for the dedicated UniFi Alloy instance.", threshold="ready"),
            table("Device uptime", f'max by (location,site_name,name,type) (unpoller_device_uptime_seconds{{{base}}})', "Device uptime reported by UniFi.", "s"),
            table("Device firmware", f'max by (location,site_name,name,type,model,version) (unpoller_device_info{{{base}}})', "Observed firmware versions for Network devices."),
            table("Available device updates", f'max by (location,site_name,name,type) (unpoller_device_upgradable{{{base}}})', "One means UniFi reports an available update.", threshold="warning"),
            log_query(chart("API event volume", [], "Events obtained from supported UniFi APIs.", "logs/s", width=24), 'sum by (location) (rate({cluster=~"$cluster",location=~"$location",source="unpoller-api"}[$__auto]))', '{{location}}'),
            chart("UniFi metric ingestion rate", [(f'sum by (location) (rate(prometheus_remote_storage_samples_in_total{{{base},job="alloy-unpoller"}}[$__rate_interval]))', "samples {{location}}")], "Samples entering remote write from the dedicated UniFi Alloy instance. This measures pipeline input, not a backend commit acknowledgement.", "ops"),
            chart("UniFi log delivery rate", [(f'sum by (location) (rate(loki_write_sent_entries_total{{{base},job="alloy-unpoller"}}[$__rate_interval]))', "entries {{location}}")], "Log entries successfully sent by the dedicated UniFi Alloy instance.", "logs/s"),
            unifi_logs("All UniFi log events", unifi_log_scope, "Latest sanitized SIEM and supported API records for the selected UniFi location."),
        ], "Health, API event intake and telemetry delivery for the selected UniFi location."),
        "unifi-gateway.json": make_unifi("mon-unifi-gateway", "UniFi Gateway and WAN", [
            stat("Internet receive", f'8 * sum(unpoller_device_wan_receive_rate_bytes{{{site}}})', "Current primary gateway WAN receive rate.", "bps"),
            stat("Internet transmit", f'8 * sum(unpoller_device_wan_transmit_rate_bytes{{{site}}})', "Current primary gateway WAN transmit rate.", "bps"),
            stat("Internet outages", f'sum(increase(unpoller_site_intenet_drops_total{{{site}}}[$__range]))', "Internet drop counter increases in the selected range.", threshold="warning"),
            stat("Primary WAN uptime", f'max(unpoller_wan_uptime_percentage{{{site},wan_networkgroup="WAN"}})', "Controller-reported WAN uptime percentage.", "percent", "availability"),
            stat("Rolling 30d download", f'sum(increase(unpoller_device_wan_receive_bytes_total{{{site}}}[30d]))', "Rolling 30-day gateway WAN receive bytes. This is not a calendar-month billing counter.", "bytes", width=8),
            stat("Rolling 30d upload", f'sum(increase(unpoller_device_wan_transmit_bytes_total{{{site}}}[30d]))', "Rolling 30-day gateway WAN transmit bytes. This is not a calendar-month billing counter.", "bytes", width=8),
            stat("Rolling 30d total", f'sum(increase(unpoller_device_wan_receive_bytes_total{{{site}}}[30d])) + sum(increase(unpoller_device_wan_transmit_bytes_total{{{site}}}[30d]))', "Rolling 30-day gateway WAN traffic total.", "bytes", width=8),
            stat("LTE device traffic 30d", f'sum((increase(unpoller_device_receive_bytes_total{{{site},type="uap"}}[30d]) + increase(unpoller_device_transmit_bytes_total{{{site},type="uap"}}[30d])) * on (cluster,location,site_name,name) group_left() ({lte_info}))', "Traffic observed on the LTE device over 30 days. This is device traffic, not a carrier billing counter." , "bytes"),
            stat("Speed test download", f'max(unpoller_device_speedtest_download{{{site}}})', "Latest controller speed-test download result.", "Mbits"),
            stat("Speed test upload", f'max(unpoller_device_speedtest_upload{{{site}}})', "Latest controller speed-test upload result.", "Mbits"),
            stat("WAN latency", f'max(unpoller_site_latency_seconds{{{site}}})', "Latest WAN latency reported by the controller.", "s"),
            dual_throughput_chart("Site traffic", [
                (f'sum by (location,site_name) (unpoller_site_receive_rate_bytes{{{site}}})', 'receive {{location}} {{site_name}}'),
                (f'sum by (location,site_name) (unpoller_site_transmit_rate_bytes{{{site}}})', 'transmit {{location}} {{site_name}}'),
            ], "Current site receive and transmit rates for the selected gateway sites."),
            dual_throughput_chart("Internet throughput", [(f'sum(unpoller_device_wan_receive_rate_bytes{{{site}}})', "receive"), (f'sum(unpoller_device_wan_transmit_rate_bytes{{{site}}})', "transmit")], "Gateway WAN receive and transmit rate."),
            dual_throughput_chart("LTE device throughput", [(f'sum(unpoller_device_rate_bytes{{{site},type="uap"}} * on (cluster,location,site_name,name) group_left() ({lte_info}))', "LTE device")], "Current LTE device traffic. It does not prove cellular failover use or match carrier accounting."),
            chart("DPI traffic by category", [(f'sum by (location,site_name,category) (unpoller_client_dpi_receive_bytes{{{site}}})', 'receive {{site_name}} {{category}}'), (f'sum by (location,site_name,category) (unpoller_client_dpi_transmit_bytes{{{site}}})', 'transmit {{site_name}} {{category}}')], "DPI byte counters by category, aggregated across clients and applications.", "bytes", width=24),
            mapped_table("WAN interfaces", f'max by (location,site_name,wan_interface,wan_networkgroup,state) (unpoller_wan_interface_state{{{site}}})', "Controller-reported interface state. Disabled backup interfaces can legitimately be inactive.", {0: "Inactive or disabled", 1: "Active"}, sort_desc=False),
            table("WAN availability", f'max by (location,site_name,wan_name,wan_networkgroup,wan_type) (unpoller_wan_uptime_percentage{{{site}}} >= 0)', "Controller-reported WAN uptime. Interfaces without a nonnegative availability value are omitted.", "percent", "availability", sort_desc=False),
            table("Gateway and LTE uptime", f'max by (location,site_name,name,type) (unpoller_device_uptime_seconds{{{site},type="udm"}} or (unpoller_device_uptime_seconds{{{site},type="uap"}} * on (cluster,location,site_name,name) group_left() ({lte_info})))', "Controller-reported uptime for the gateway and LTE modem.", "s"),
            table("Gateway and LTE firmware", f'max by (location,site_name,name,type,model,version) (unpoller_device_info{{{site},type="udm"}} or unpoller_device_info{{{site},model="ULTEPEU"}})', "Observed UDM and LTE modem firmware."),
            table("Gateway and LTE updates", f'max by (location,site_name,name,type) (unpoller_device_upgradable{{{site},type="udm"}} or (unpoller_device_upgradable{{{site},type="uap"}} * on (cluster,location,site_name,name) group_left() ({lte_info})))', "One means UniFi reports an available update.", threshold="warning"),
            log_query(chart("Gateway and WAN SIEM event volume", [], "Incoming UDM and UNAS SIEM records per second for the selected location.", "logs/s", width=24), 'sum by (location,appliance) (rate({cluster=~"$cluster",location=~"$location",source="unifi-siem"}[$__auto]))', '{{location}} {{appliance}}'),
            unifi_logs("Gateway, WAN, IDS, IPS and Network events", unifi_log_scope + ' |~ "(?i)gateway|wan|internet|lte|failover|dhcp|dns|dpi|ids|ips|threat|intrusion|rogue|network"', "Gateway, WAN, LTE, IDS, IPS and Network records."),
        ], "Gateway, primary WAN, LTE failover device and rolling traffic totals. LTE values are device telemetry, not carrier billing data.", [variable("site", "unpoller_site_gateways", "site_name", base)]),
        "unifi-switches.json": make_unifi("mon-unifi-switches", "UniFi Switches", [
            stat("Selected switches", f'count(max without (tag) (unpoller_device_info{{{switch_scope},type="usw"}}))', "Standalone switches in the selected scope. The UDM integrated switch is covered by the Gateway and WAN dashboard."),
            stat("Switch throughput", f'8 * (sum(unpoller_device_port_receive_rate_bytes{{{switch_port_scope}}}) + sum(unpoller_device_port_transmit_rate_bytes{{{switch_port_scope}}}))', "Current receive plus transmit rate for selected switch ports.", "bps"),
            stat("PoE output", f'sum(unpoller_device_port_poe_watts{{{switch_port_scope}}})', "Current PoE output for selected switch ports.", "watt"),
            stat("Updates available", f'sum(unpoller_device_upgradable{{{switch_scope},type="usw"}})', "Selected switches with an available firmware update.", threshold="warning"),
            dual_throughput_chart("Port throughput", [(f'sum by (name,port_name) (unpoller_device_port_receive_rate_bytes{{{switch_port_scope}}})', "receive {{name}} {{port_name}}"), (f'sum by (name,port_name) (unpoller_device_port_transmit_rate_bytes{{{switch_port_scope}}})', "transmit {{name}} {{port_name}}")], "Per-port switch traffic."),
            poe_draw_chart(switch_scope),
            table("Switch PoE budget", f'max by (location,site_name,name) (unpoller_device_max_power_total{{{switch_scope},type="usw"}})', "Controller-reported maximum PoE budget per switch.", "watt"),
            table("Port errors and drops", f'sum by (location,site_name,name,port_name) (increase(unpoller_device_port_receive_errors_total{{{switch_port_scope}}}[$__range]) + increase(unpoller_device_port_transmit_errors_total{{{switch_port_scope}}}[$__range]) + increase(unpoller_device_port_receive_dropped_total{{{switch_port_scope}}}[$__range]) + increase(unpoller_device_port_transmit_dropped_total{{{switch_port_scope}}}[$__range]))', "Combined port errors and drops in the selected range.", threshold="warning"),
            port_link_speed_table(switch_port_scope),
            chart("Switch CPU and memory", [(f'100 * max by (name) (unpoller_device_cpu_utilization_ratio{{{switch_scope},type="usw"}})', "CPU {{name}}"), (f'100 * max by (name) (unpoller_device_memory_utilization_ratio{{{switch_scope},type="usw"}})', "memory {{name}}")], "Controller-reported switch CPU and memory utilization.", "percent", width=24),
            table("Switch uptime", f'max by (location,site_name,name) (unpoller_device_uptime_seconds{{{switch_scope},type="usw"}})', "Controller-reported switch uptime.", "s"),
            table("Switch firmware", f'max by (location,site_name,name,model,version) (unpoller_device_info{{{switch_scope},type="usw"}})', "Observed switch model and firmware."),
            table("Switch updates", f'max by (location,site_name,name) (unpoller_device_upgradable{{{switch_scope},type="usw"}})', "One means UniFi reports an available update.", threshold="warning"),
            unifi_logs("Switch SIEM events", unifi_log_scope + ' |~ "(?i)switch|port|poe|stp|loop|link|duplex|vlan"', "Switch, port and PoE records."),
        ], "Switch capacity, traffic, PoE, port errors, resource use, uptime and firmware.", [
            variable("site", "unpoller_device_info", "site_name", f'{base},type="usw"'),
            variable("switch", "unpoller_device_info", "name", f'{site},type="usw"'),
            variable("port", "unpoller_device_port_receive_rate_bytes", "port_name", f'{site},name=~"$switch"'),
        ]),
        "unifi-access-points.json": make_unifi("mon-unifi-access-points", "UniFi Access Points", [
            stat("Selected access points", f'count(max without (tag) (unpoller_device_info{{{ap_scope},type="uap",model!="ULTEPEU"}}))', "Access points in scope. The LTE modem is excluded."),
            stat("Associated stations", f'sum(max without (tag) (unpoller_device_stations{{{ap_scope},type="uap"}}))', "Stations associated with selected access points."),
            stat("Access point throughput", f'8 * sum(unpoller_device_rate_bytes{{{ap_scope},type="uap"}})', "Current aggregate traffic for selected access points.", "bps"),
            stat("Updates available", f'sum(unpoller_device_upgradable{{{ap_scope},type="uap"}})', "Selected access points with an available firmware update.", threshold="warning"),
            dual_throughput_chart("Access point throughput", [(f'sum by (name) (unpoller_device_rate_bytes{{{ap_scope},type="uap"}})', "{{name}}")], "Current traffic by access point."),
            chart("Radio channel utilization", [(f'100 * max by (name,band,radio_name) (unpoller_device_radio_channel_utilization_total_ratio{{{ap_scope}}})', "{{name}} {{band}} GHz")], "Total channel utilization by radio.", "percent", width=24),
            radio_band_table("Radio channels", f'max by (location,site_name,name,band,radio_name) (unpoller_device_radio_channel{{{ap_scope}}})', "Current channel per access point radio."),
            radio_band_table("Radio transmit retries", f'max by (location,site_name,name,band,radio_name) (unpoller_device_radio_transmit_retries{{{ap_scope}}})', "Current controller-reported transmit retry count. Compare radios rather than treating this as a cumulative counter.", threshold="warning"),
            radio_percentage_table("Radio retry percentage", f'100 * max by (location,site_name,name,band,radio_name) (unpoller_device_radio_transmit_retries{{{ap_scope}}}) / clamp_min(max by (location,site_name,name,band,radio_name) (unpoller_device_radio_transmit_retries{{{ap_scope}}}) + max by (location,site_name,name,band,radio_name) (unpoller_device_radio_transmit_packets{{{ap_scope}}}), 1)', "Retries divided by controller-reported transmit attempts plus retries. This percentage is calculated only from the available radio counters."),
            radio_percentage_table("Wireless satisfaction", f'100 * max by (location,site_name,name,band,essid) (unpoller_device_vap_satisfaction_ratio{{{ap_scope}}} >= 0)', "Client satisfaction where UniFi provides a nonnegative value."),
            rogue_access_points_table(site),
            chart("Access point CPU and memory", [(f'100 * max by (name) (unpoller_device_cpu_utilization_ratio{{{ap_scope},type="uap"}})', "CPU {{name}}"), (f'100 * max by (name) (unpoller_device_memory_utilization_ratio{{{ap_scope},type="uap"}})', "memory {{name}}")], "Controller-reported access point CPU and memory utilization.", "percent", width=24),
            table("Access point uptime", f'max by (location,site_name,name) (unpoller_device_uptime_seconds{{{ap_scope},type="uap"}})', "Controller-reported access point uptime.", "s"),
            table("Access point firmware", f'max by (location,site_name,name,model,version) (unpoller_device_info{{{ap_scope},type="uap",model!="ULTEPEU"}})', "Observed access point model and firmware."),
            table("Access point updates", f'max by (location,site_name,name) (unpoller_device_upgradable{{{ap_scope},type="uap"}})', "One means UniFi reports an available update.", threshold="warning"),
            unifi_logs("Access point SIEM events", unifi_log_scope + ' |~ "(?i)access.?point|\\buap\\b|wifi|wlan|wireless|radio|rogue"', "Wireless, radio and rogue-access-point records."),
        ], "Wireless capacity, radio utilization, stations, retries, uptime and firmware. The LTE modem is intentionally excluded.", [
            variable("site", "unpoller_device_info", "site_name", f'{base},type="uap",model!="ULTEPEU"'),
            variable("ap", "unpoller_device_info", "name", f'{site},type="uap",model!="ULTEPEU"'),
        ]),
        "unifi-protect.json": make_unifi("mon-unifi-protect", "UniFi Protect", [
            stat("Cameras", f'sum(unpoller_protect_device_present{{{camera_scope},model_key="camera"}})', "Protect cameras returned by the controller."),
            stat("Disconnected cameras", f'sum(unpoller_protect_device_state{{{camera_scope},model_key="camera"}} == bool 0)', "Cameras explicitly reporting disconnected state.", threshold="warning"),
            stat("Microphones enabled", f'sum(unpoller_protect_camera_mic_enabled{{{camera_scope}}})', "Selected cameras with microphone enabled. Audio content is not collected."),
            log_query(stat("Detection events", "", "Motion, smart-detection and smart-audio records in the selected range.", threshold="warm"), f'sum(count_over_time({camera_logs} | label_format level=detected_level |~ "(?i)motion|smartDetect|smartAudio" [$__range]))', instant=True),
            protect_state_table(f'{camera_scope},model_key="camera"'),
            chart("Camera network traffic", [(f'sum by (name) (rate(unpoller_client_receive_bytes_total{{{camera_scope},network="CCTV"}}[$__rate_interval]))', "receive {{name}}"), (f'sum by (name) (rate(unpoller_client_transmit_bytes_total{{{camera_scope},network="CCTV"}}[$__rate_interval]))', "transmit {{name}}")], "Network traffic for CCTV clients whose UniFi Network name matches the selected Protect camera. This is not NVR disk or application throughput.", "Bps", width=24),
            log_query(chart("Protect event rate", [], "Protect motion, smart-detection and smart-audio event rate for the selected camera name.", "logs/s", width=24), f'sum by (unifi_application) (rate({camera_logs} | label_format level=detected_level |~ "(?i)motion|smartDetect|smartAudio" [$__auto]))', '{{unifi_application}}'),
            table("Camera network attachment", f'max by (location,name,ip,mac,sw_name,sw_port,ap_name,wired) (unpoller_client_receive_bytes_total{{{camera_scope},network="CCTV"}} >= bool 0)', "Latest Network identity and attachment metadata for matching CCTV clients."),
            protect_state_table(f'{base},model_key="nvr"', "NVR state"),
            table("Protect host firmware", f'max by (location,site_name,name,type,model,version) (unpoller_device_info{{{base},type="udm"}})', "Firmware of the UDM hosting Protect. Camera firmware is not exported by the available Protect metrics."),
            table("Protect host updates", f'max by (location,site_name,name,type) (unpoller_device_upgradable{{{base},type="udm"}})', "One means UniFi reports an available UDM update. Camera firmware update state is not exported.", threshold="warning"),
            unifi_logs("Protect events", camera_logs + ' | label_format level=detected_level |~ "(?i)protect|camera|motion|smartDetect|smartAudio|doorbell|nvr"', "Protect event metadata without thumbnails, snapshots, video or audio payloads."),
        ], "Protect camera state, actual CCTV network traffic and detection metadata. UnPoller does not export NVR disk or application throughput. No images, thumbnails, video or audio payloads are collected.", [variable("camera", "unpoller_protect_device_present", "name", f'{base},model_key="camera"')]),
        "unifi-ups.json": make_unifi("mon-unifi-ups", "UniFi UPS", [
            stat("UPS devices", f'count(max by (device_name) (unpoller_device_ups_battery_level_percent{{{base}}}))', "Observed UniFi UPS devices with battery telemetry."),
            stat("Lowest battery level", f'min(unpoller_device_ups_battery_level_percent{{{base},device_name=~"$ups"}})', "Lowest reported charge among selected UPS devices.", "percent", "warning"),
            stat("Shortest battery runtime", f'min(unpoller_device_ups_battery_time_remaining_seconds{{{base},device_name=~"$ups"}})', "Shortest controller-reported remaining battery runtime among selected UPS devices.", "s", "warm"),
            stat("Current output power", f'sum(unpoller_device_ups_power_output_watts{{{base},device_name=~"$ups"}})', "Combined current output power of selected UPS devices.", "watt"),
            chart("Battery level and load", [(f'max by (device_name) (unpoller_device_ups_battery_level_percent{{{base},device_name=~"$ups"}})', "battery {{device_name}}"), (f'max by (device_name) (unpoller_device_ups_load_percent{{{base},device_name=~"$ups"}})', "load {{device_name}}")], "Reported battery charge and load percentage per UPS.", "percent", width=24),
            chart("Battery runtime", [(f'max by (device_name) (unpoller_device_ups_battery_time_remaining_seconds{{{base},device_name=~"$ups"}})', "{{device_name}}")], "Controller-reported remaining runtime per UPS.", "s", width=12),
            chart("Output power", [(f'max by (device_name) (unpoller_device_ups_power_output_watts{{{base},device_name=~"$ups"}})', "{{device_name}}")], "Current output power per UPS.", "watt", width=12),
            chart("Output voltage", [(f'max by (device_name) (unpoller_device_ups_output_voltage{{{base},device_name=~"$ups"}})', "{{device_name}}")], "Measured output voltage per UPS.", "volt", width=12),
            chart("Output current", [(f'max by (device_name) (unpoller_device_ups_output_current_amps{{{base},device_name=~"$ups"}})', "{{device_name}}")], "Measured output current per UPS.", "amp", width=12),
            table("UPS power budget", f'max by (location,site_name,device_name) (unpoller_device_ups_power_budget_watts{{{base},device_name=~"$ups"}})', "Configured power budget per UPS.", "watt"),
            table("UPS BMS anomalies", f'max by (location,site_name,device_name) (unpoller_device_ups_bms_anomaly_count{{{base},device_name=~"$ups"}})', "Battery-management anomalies reported by each UPS.", threshold="warning"),
            table("UPS battery mode", f'max by (location,site_name,device_name) (unpoller_device_ups_battery_mode{{{base},device_name=~"$ups"}})', "Controller-reported battery operating mode. The numeric mode is retained because the exporter does not provide a stable text mapping."),
        ], "Battery, load and electrical-output telemetry for the UniFi UPS devices. All values come directly from the controller and are shown per device where possible.", [variable("ups", "unpoller_device_ups_battery_level_percent", "device_name", base)]),
        "unifi-unas.json": make_unifi("mon-unifi-unas", "UniFi UNAS", [
            stat("UNAS reachable", f'min(unpoller_unas_device_present{{{base}}})', "UNAS consoles returned by the API.", threshold="ready", width=6),
            stat("CPU load", f'max(unpoller_unas_cpu_load_percent{{{base}}})', "Current console CPU load.", "percent", "percent", width=6),
            stat("Memory use", f'100 * (1 - max(unpoller_unas_memory_available_bytes{{{base}}}) / max(unpoller_unas_memory_total_bytes{{{base}}}))', "Used memory based on available versus total.", "percent", "percent", width=6),
            stat("Pool occupancy", f'100 * max(unpoller_unas_pool_usage_bytes{{{base}}}) / max(unpoller_unas_pool_capacity_bytes{{{base}}})', "Used versus total pool capacity.", "percent", "percent", width=6),
            chart("Disk throughput", [(f'sum by (name,slot_id) (unpoller_unas_disk_read_kbps{{{base}}}) * 1000', "read {{name}} slot {{slot_id}}"), (f'sum by (name,slot_id) (unpoller_unas_disk_write_kbps{{{base}}}) * 1000', "write {{name}} slot {{slot_id}}")], "Per-disk read and write throughput reported by UNAS.", "Bps", width=24),
            dual_throughput_chart("UNAS network throughput", [(f'sum by (name) (unpoller_unas_receive_kbps{{{base}}}) * 1000', "receive {{name}}"), (f'sum by (name) (unpoller_unas_transmit_kbps{{{base}}}) * 1000', "transmit {{name}}")], "Console network receive and transmit throughput reported by UNAS."),
            chart("CPU load trend", [(f'max by (name) (unpoller_unas_cpu_load_percent{{{base}}})', "{{name}}")], "UNAS CPU utilization over time.", "percent", width=12),
            chart("CPU temperature", [(f'max by (name) (unpoller_unas_cpu_temperature_celsius{{{base}}})', "{{name}}")], "UNAS CPU temperature over time.", "celsius", width=12),
            table("RAID protection gap", f'max by (location,source,name,pool_id,raid_group_id,current_level,config_level) (unpoller_unas_raid_group_expected_protection{{{base}}} - unpoller_unas_raid_group_current_protection{{{base}}})', "Positive values mean current protection is below expected.", threshold="warning"),
            chart("RAID operation progress", [(f'unpoller_unas_raid_group_progress_percent{{{base}}}', '{{location}} {{name}} {{pool_id}} {{raid_group_id}}')], "Rebuild or expansion progress.", "percent", width=12),
            chart("Disk temperature", [(f'unpoller_unas_disk_temperature_celsius{{{base}}}', '{{location}} {{name}} slot {{slot_id}}')], "Physical disk temperature.", "celsius", width=12),
            table("Disk health", f'min by (location,source,name,slot_id,pool_id,disk_type,state,model,serial) (unpoller_unas_disk_health_score{{{base}}})', "Health score reported by UNAS. The state label carries the appliance classification; the score remains quantitative rather than inventing local health thresholds."),
            table("Disk media errors", f'max by (location,source,name,slot_id,pool_id,model,serial) (unpoller_unas_disk_bad_sectors{{{base}}} + unpoller_unas_disk_uncorrectable_sectors{{{base}}} + unpoller_unas_disk_smart_read_errors{{{base}}})', "Combined bad, uncorrectable and SMART read-error counts.", threshold="warning"),
            table("Disk power-on hours", f'max by (location,source,name,slot_id,pool_id,model,serial) (unpoller_unas_disk_power_on_hours{{{base}}})', "Drive power-on time reported by UNAS.", "h"),
            unifi_logs("UNAS SIEM events", '{cluster=~"$cluster",location=~"$location",source="unifi-siem",appliance="unas"}', "Sanitized SIEM records sent directly by UNAS."),
        ], "UNAS console, pools, RAID, disk and network telemetry plus direct SIEM records. The current exporter and SIEM stream do not expose a reliable backup-status contract, so no backup status is inferred."),
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

    authentik_targets = (
        f'min by (cluster,namespace,job,pod,authentik_component) ({metric("up", "job=~\"authentik|authentik-outpost\"")}) '
        f'* on (cluster,namespace,pod) group_left(version) max by (cluster,namespace,pod,version) '
        f'(label_replace(kube_pod_container_info{{{C},namespace=~"authentik|authentik-outpost",container=~"server|worker|proxy|ldap"}}, '
        '"version", "$1", "image", ".*:([^:]+)$"))'
    )
    result["authentik.json"] = make("mon-app-authentik", "Authentik", "authentik|authentik-outpost", [
        table("Server, worker and outpost targets", authentik_targets, "Scrape state for each observed process. Version is derived from the running container image tag. Missing targets are not healthy zeros.", threshold="ready", sort_desc=False),
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
        "category_title": "Monitoring Applications", "category_tag": "monitoring-applications",
        "vars": [variable("monitor", "monitor_status", "monitor_id", C), variable("monitor_type", "monitor_status", "monitor_type", C), copy.deepcopy(window)],
        "purpose": "Control-room view of Kuma monitors, with sampled status history and rolling availability. Group monitors are separate from individual monitors. Prometheus does not expose the parent-child hierarchy, so nested groups cannot be reconstructed. Monitor type and ID filters apply throughout. Missing history is never painted green.",
        "panels": [*copy.deepcopy(outcomes[:4]),
            history("Group monitor history", 'sort_by_label(max by (cluster,monitor_name,monitor_id) (' + metric("monitor_status", monitor_selector + ',monitor_type="group"') + '), "monitor_name", "cluster")', '{{monitor_name}} · {{cluster}} · #{{monitor_id}}', 14),
            history("Monitor status history", 'sort_by_label(max by (cluster,monitor_name,monitor_id) (' + metric("monitor_status", monitor_selector + ',monitor_type!="group"') + '), "monitor_name", "cluster")', '{{monitor_name}} · {{cluster}} · #{{monitor_id}}'),
            *copy.deepcopy(outcomes[4:])],
    })
    monitor_dashboard["tags"] = ["monitoring", "monitoring-applications", "applications", "metrics"]
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
        "category_title": None, "category_tag": None,
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
