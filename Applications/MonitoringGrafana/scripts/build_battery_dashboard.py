#!/usr/bin/env python3
"""Home Assistant battery overview using the existing Prometheus export."""

from build_dashboards import build, chart, place, stat, table, variable


BATTERY_THRESHOLDS = {"mode": "absolute", "steps": [
    {"color": "text", "value": None},
    {"color": "red", "value": 0},
    {"color": "#FFB357", "value": 10.000001},
    {"color": "green", "value": 20.000001},
]}


def battery_dashboard():
    scope = 'cluster=~"$cluster",job="homeassistant"'
    selection = scope + ',entity=~"$battery",entity!~".*_(predicted_battery_level|trip_end_battery_level)"'
    source = f'homeassistant_sensor_battery_percent{{{selection}}}'
    availability = f'homeassistant_entity_available{{{selection}}}'
    identity = "cluster,entity"
    metadata = f'(0 * max by (cluster,entity,friendly_name) ({availability}) + 1)'
    # Historical values identify battery entities only. They never supply charge.
    inventory = f'((0 * max by ({identity}) (last_over_time({source}[30d])) + 1) * on ({identity}) group_left(friendly_name) {metadata})'
    healthy_export = f'(min by (cluster) (up{{{scope}}}) == 1)'
    valid = (
        f'(({source} >= 0 and {source} <= 100) '
        f'and (time() - timestamp({source}) < 120) '
        f'and on ({identity}) ({availability} == 1) '
        f'and on (cluster) {healthy_export})'
    )
    current = f'(min by ({identity}) ({valid}) * on ({identity}) group_left(friendly_name) {metadata})'
    missing = f'({inventory} unless on ({identity}) {current})'
    levels = f'({current} or (-1 * {missing}))'
    categories = [
        ("Healthy", f"{levels} > 20"),
        ("Warning", f"(({levels} <= 20) > 10)"),
        ("Critical", f"(({levels} <= 10) >= 0)"),
        ("Unknown", f"{levels} < 0"),
    ]
    classified = " or ".join(
        f'label_replace({expr}, "status", "{name}", "entity", ".*")'
        for name, expr in categories
    )
    info = f'max by (cluster,entity,area) (homeassistant_entity_info{{{scope}}})'
    areas = f'({info} or on ({identity}) (0 * {inventory} + 1))'
    classified = f'({classified}) * on ({identity}) group_left(area) {areas}'

    def count(expr):
        # Empty categories are zero only when battery inventory exists.
        return f'count({expr}) or (0 * count({inventory}))'

    def battery_table(title, expr, description):
        result = table(title, expr, description, "percent", width=24, sort_desc=False)
        result["fieldConfig"]["defaults"].update({
            "decimals": 1, "min": 0, "max": 100,
            "thresholds": BATTERY_THRESHOLDS,
            "mappings": [{"type": "value", "options": {"-1": {"text": "Unknown / unavailable", "color": "text"}}}],
        })
        result["fieldConfig"]["overrides"] = [{
            "matcher": {"id": "byName", "options": "Value"},
            "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}}],
        }]
        result["transformations"] = [{"id": "organize", "options": {
            "excludeByName": {"Time": True, "__name__": True},
            "indexByName": {"friendly_name": 0, "area": 1, "Value": 2, "status": 3, "entity": 4, "cluster": 5},
            "renameByName": {"friendly_name": "Device / battery", "area": "Area", "Value": "Battery", "status": "Status", "entity": "Entity", "cluster": "Cluster"},
        }}]
        result["options"]["sortBy"] = [{"desc": False, "displayName": "Battery"}]
        result["gridPos"]["h"] = 14
        return result

    description = (
        "Home Assistant battery sensors. Healthy >20%, warning >10% to 20%, critical 0% to 10%. "
        "Counts are distinct battery entities, not guaranteed unique physical devices. "
        "Predicted charge and trip-end estimates are excluded. Unknown means missing, unavailable, "
        "invalid or stale telemetry. Inventory uses battery sensors seen in the last 30 days that "
        "still have an availability entity. Never-observed battery sensors and voltage-only devices are not covered."
    )
    kpis = [
        stat("Observed batteries", f'count({inventory})', "Distinct battery entities in the selected scope. Several battery entities can belong to one physical device.", width=4),
        stat("Healthy (>20%)", count(f'{current} > 20'), "Batteries above 20% with valid current telemetry.", width=4),
        stat("Warning (10–20%)", count(f'({current} > 10 and {current} <= 20)'), "Above 10% and at most 20%. Critical batteries are counted separately.", threshold="warning", width=4),
        stat("Almost empty (≤10%)", count(f'{current} <= 10'), "At most 10%, including empty batteries at 0%.", threshold="critical", width=4),
        stat("Unknown / unavailable", count(missing), "Known battery entities without valid current charge. Check Home Assistant availability and scrape health.", threshold="warning", width=4),
        stat("Lowest battery", f'min({current})', "Lowest valid current charge. Missing values never become 0%.", "percent", width=4),
    ]
    kpis[-1]["fieldConfig"]["defaults"].update({"thresholds": BATTERY_THRESHOLDS, "decimals": 1})
    for item in kpis:
        item["options"]["graphMode"] = "none"
        item["fieldConfig"]["defaults"]["noValue"] = "No battery telemetry"
    kpis[-1]["fieldConfig"]["defaults"]["noValue"] = "No valid charge"
    battery_variable = variable("battery", "homeassistant_sensor_battery_percent", "entity", scope)
    battery_variable["label"] = "Battery sensor"
    history = chart("Battery history", [(current, "{{friendly_name}} · {{cluster}}")], "Sampled charge history. Unavailable periods remain gaps. Select individual battery sensors to compare trends.", "percent", width=24)
    history["fieldConfig"]["defaults"].update({"min": 0, "max": 100, "decimals": 1})
    result = build({
        "uid": "mon-app-device-batteries", "title": "Device Batteries", "from": "now-24h", "refresh": "1m",
        "category_title": "Monitoring Applications", "category_tag": "monitoring-applications",
        "vars": [battery_variable], "purpose": description,
        "panels": [*kpis,
            battery_table("Batteries needing attention", f'({classified}) <= 20', "Warning, critical and unknown batteries first. Unknown is a status, not a charge of 0%."),
            battery_table("All device batteries", classified, "Current percentage, status, area and entity. Lowest charge first. Use column filters to narrow the list."),
            history,
            stat("Home Assistant scrape healthy", f'min(up{{{scope}}})', "All observed Home Assistant targets must report up=1. Missing targets cannot be inferred.", threshold="ready", width=12),
        ],
    })
    result["templating"]["list"][0] = variable("cluster", "homeassistant_sensor_battery_percent", "cluster", 'job="homeassistant"')
    result["panels"][0]["gridPos"]["w"] = 24
    freshness = result["panels"].pop(1)
    freshness["title"] = "Oldest Home Assistant scrape sample"
    freshness["description"] = "Age of currently visible Home Assistant scrape telemetry. This is not the time of the device's last radio transmission. Battery samples older than 120 seconds are unknown."
    freshness["targets"][0]["expr"] = f'max(clamp_min(time() - timestamp(up{{{scope}}}), 0))'
    freshness["gridPos"]["w"] = 12
    result["panels"].append(freshness)
    for item in result["panels"]:
        if item["title"] in {"Home Assistant scrape healthy", "Oldest Home Assistant scrape sample"}:
            item["fieldConfig"]["defaults"]["noValue"] = "No scrape telemetry"
    for index, item in enumerate(place(result["panels"]), 1):
        item["id"] = index
    return result
