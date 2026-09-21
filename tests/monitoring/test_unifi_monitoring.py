"""UniFi collector, security boundary and dashboard regression tests."""
import base64
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "Applications" / "Unpoller"
GRAFANA = ROOT / "Applications" / "MonitoringGrafana"
sys.path.insert(0, str(GRAFANA / "scripts"))

from build_application_dashboards import UNIFI_OUTPUT, unifi_dashboards  # noqa: E402
from test_kustomize import objects, render  # noqa: E402


class UniFiMonitoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = render(APP / "overlay" / "_SAMPLE")
        cls.index = objects(cls.docs)

    def test_collector_topology_and_hardening(self):
        unpoller = self.index["Deployment", "unpoller"]
        alloy = self.index["StatefulSet", "alloy-unpoller"]
        self.assertEqual(unpoller["spec"]["replicas"], 1)
        self.assertEqual(unpoller["spec"]["strategy"]["type"], "Recreate")
        self.assertEqual(alloy["spec"]["replicas"], 1)
        self.assertEqual(alloy["spec"]["persistentVolumeClaimRetentionPolicy"], {"whenDeleted": "Retain", "whenScaled": "Retain"})
        self.assertEqual(alloy["spec"]["volumeClaimTemplates"][0]["spec"]["resources"]["requests"]["storage"], "5Gi")
        for workload in (unpoller, alloy):
            pod = workload["spec"]["template"]["spec"]
            self.assertFalse(pod["automountServiceAccountToken"])
            self.assertTrue(pod["securityContext"]["runAsNonRoot"])
            container = pod["containers"][0]
            self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
            self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
            self.assertNotIn("livenessProbe", container)
        self.assertEqual(unpoller["spec"]["template"]["spec"]["containers"][0]["image"], "ghcr.io/unpoller/unpoller:v5.2.7")
        self.assertEqual(alloy["spec"]["template"]["spec"]["containers"][0]["image"], "grafana/alloy:v1.19.2")

    def test_syslog_load_balancer_is_fixed_and_source_restricted(self):
        service = self.index["Service", "alloy-unpoller-syslog"]
        self.assertEqual(service["spec"]["type"], "LoadBalancer")
        self.assertEqual(service["spec"]["externalTrafficPolicy"], "Local")
        self.assertEqual(service["spec"]["loadBalancerIP"], "192.0.2.30")
        self.assertEqual(service["metadata"]["annotations"]["metallb.io/address-pool"], "default-pool")
        self.assertNotIn("metallb.io/loadBalancerIPs", service["metadata"]["annotations"])
        self.assertEqual(service["spec"]["loadBalancerSourceRanges"], ["192.0.2.10/32", "192.0.2.20/32"])
        self.assertEqual(
            {(p["protocol"], p["port"], p["targetPort"]) for p in service["spec"]["ports"]},
            {("UDP", 514, "syslog-udp"), ("TCP", 514, "syslog-tcp")},
        )
        self.assertNotIn("10.0.1.20", json.dumps(self.docs))
        self.assertNotIn("ADMIN01", json.dumps(self.docs))
        self.assertNotIn("admin01", json.dumps(self.docs))

    def test_unpoller_data_contract_excludes_media_and_out_of_scope_inputs(self):
        config = next(d["data"]["up.conf"] for d in self.docs if d["kind"] == "ConfigMap" and "up.conf" in d.get("data", {}))
        for setting in ("save_ids", "save_events", "save_syslog", "save_alarms", "save_anomalies",
                        "save_protect_logs", "save_protect_devices", "save_dpi", "save_traffic", "save_rogue"):
            self.assertIn(f"{setting} = true", config)
        self.assertIn("protect_thumbnails = false", config)
        self.assertIn("verify_ssl = true", config)
        self.assertIn("http://alloy-unpoller:1515/loki/api/v1/push", config)
        self.assertEqual(config.count('interval = "60s"'), 2)
        for forbidden in ("talk", "netconsole", "netflow", "ipfix", "snapshot", "base64"):
            self.assertNotIn(forbidden, config.lower())
        self.assertIn("file:///var/run/secrets/unpoller/network_password", config)
        self.assertIn("file:///var/run/secrets/unpoller/protect_api_key", config)
        self.assertNotIn("file:///var/run/secrets/unpoller/unas_password", config)
        self.assertEqual(config.count("[[unifi.controller]]"), 2)
        self.assertIn("# Use separate clients for Network and Protect.", config)
        self.assertIn("disable_network = true", config)
        self.assertIn("save_protect_devices = false", config)
        deployment = self.index["Deployment", "unpoller"]
        env = {entry["name"]: entry for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
        unas_password = env["UP_UNAS_DEFAULT_PASS"]["valueFrom"]["secretKeyRef"]
        self.assertEqual(unas_password["key"], "unas_password")
        self.assertTrue(unas_password["name"].startswith("unpoller-credentials-"))
        self.assertNotIn("replace-with", config)

    def test_alloy_uses_only_internal_write_paths_and_bounded_syslog(self):
        alloy = next(d["data"]["unpoller.alloy"] for d in self.docs if d["kind"] == "ConfigMap" and "unpoller.alloy" in d.get("data", {}))
        env = next(d["data"] for d in self.docs if d["kind"] == "ConfigMap" and "METRICS_WRITE_URL" in d.get("data", {}))
        self.assertEqual(env["METRICS_WRITE_URL"], "http://vmauth.monitoring-metrics.svc.cluster.local:8427/api/v1/write")
        self.assertEqual(env["LOKI_WRITE_URL"], "http://vmauth.monitoring-logs.svc.cluster.local:8427/loki/api/v1/push")
        self.assertIn('"__address__" = "unpoller:9130"', alloy)
        self.assertIn("max_message_length = 65536", alloy)
        self.assertIn("udp_queue_size     = 4096", alloy)
        self.assertEqual(alloy.count("relabel_rules = loki.relabel.syslog.rules"), 2)
        self.assertEqual(alloy.count("forward_to    = [loki.process.syslog.receiver]"), 2)
        self.assertNotIn("forward_to = [loki.relabel.syslog.receiver]", alloy)
        self.assertIn('source       = "unifi-siem"', alloy)
        self.assertIn('source       = "unpoller-api"', alloy)
        self.assertIn('cluster      = "example-cluster"', alloy)
        self.assertEqual(env["UNPOLLER_LOCATION"], "example-site")
        self.assertIn('replacement  = sys.env("UNPOLLER_LOCATION")', alloy)
        self.assertEqual(alloy.count('location     = sys.env("UNPOLLER_LOCATION")'), 2)
        self.assertIn("loki.secretfilter", alloy)
        self.assertNotIn("https://", alloy)
        self.assertIn('selector = "{cef_severity=~\\"[1-3]\\"}"', alloy)
        self.assertIn('selector = "{cef_severity=~\\"[4-6]\\"}"', alloy)
        self.assertIn('selector = "{cef_severity=~\\"[7-9]|10\\"}"', alloy)
        self.assertEqual(alloy.count('values = { detected_level = "'), 3)
        self.assertIn('values = ["detected_level_extracted"]', alloy)
        writers = next(
            d for d in self.docs
            if d["kind"] == "Secret" and d["metadata"]["name"].startswith("alloy-unpoller-writers-")
        )
        for value in writers["data"].values():
            self.assertTrue(base64.b64decode(value).decode().startswith("replace-with-unpoller-"))

    def test_network_policies_have_narrow_flows(self):
        alloy = self.index["NetworkPolicy", "alloy-unpoller-traffic"]["spec"]
        unpoller = self.index["NetworkPolicy", "unpoller-traffic"]["spec"]
        self.assertEqual({target["ipBlock"]["cidr"] for target in alloy["ingress"][2]["from"]}, {"192.0.2.10/32", "192.0.2.20/32"})
        self.assertEqual({target["ipBlock"]["cidr"] for target in unpoller["egress"][0]["to"]}, {"192.0.2.10/32", "192.0.2.20/32"})
        self.assertEqual({port["port"] for rule in alloy["egress"] for port in rule["ports"]}, {9130, 8427})
        self.assertEqual({port["port"] for rule in unpoller["egress"] for port in rule["ports"]}, {443, 1515})
        self.assertIn(("NetworkPolicy", "default-deny"), self.index)

    def test_backend_writer_contracts_and_ingress(self):
        for app, path in (("MonitoringMetrics", "/api/v1/write"), ("MonitoringLogs", "/loki/api/v1/push")):
            docs = render(ROOT / "Applications" / app / "overlay" / "_SAMPLE")
            index = objects(docs)
            policy = index["NetworkPolicy", "unpoller-to-vmauth"]
            source = policy["spec"]["ingress"][0]["from"][0]
            self.assertEqual(source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"], "unpoller")
            self.assertEqual(source["podSelector"]["matchLabels"]["app.kubernetes.io/component"], "collector")
            auth = next(d["data"]["auth.yml"] for d in docs if d["kind"] == "ConfigMap" and "auth.yml" in d.get("data", {}))
            self.assertIn("name: unpoller-writer", auth)
            self.assertNotIn("unifi-admin01-writer", auth)
            self.assertNotIn("UNIFI_ADMIN01_WRITER_TOKEN", auth)
            self.assertIn(path, auth)
            secret = next(d for d in docs if d["kind"] == "Secret")
            self.assertIn("WRITER_UNPOLLER_TOKEN", secret["data"])
            if app == "MonitoringMetrics":
                self.assertIn("extra_label=cluster=example-cluster", auth)

    def test_existing_metrics_agent_scrapes_only_alloy_unpoller(self):
        docs = render(ROOT / "Applications" / "MonitoringAgent" / "overlay" / "_SAMPLE")
        config = next(d["data"] for d in docs if d["kind"] == "ConfigMap" and "65-unpoller-telemetry.alloy" in d.get("data", {}))["65-unpoller-telemetry.alloy"]
        env = next(d["data"] for d in docs if d["kind"] == "ConfigMap" and "NORMAL_SCRAPE_INTERVAL" in d.get("data", {}))
        self.assertIn('"alloy-unpoller.unpoller.svc:12345"', config)
        self.assertNotIn("unpoller:9130", config)
        self.assertEqual(config.count('job_name        = "alloy-unpoller"'), 1)
        self.assertIn('scrape_interval = sys.env("NORMAL_SCRAPE_INTERVAL")', config)
        self.assertEqual(env["FAST_SCRAPE_INTERVAL"], "15s")
        self.assertEqual(env["NORMAL_SCRAPE_INTERVAL"], "30s")
        self.assertEqual(env["SLOW_SCRAPE_INTERVAL"], "60s")
        alloy = objects(docs)["StatefulSet", "alloy-metrics"]
        config_volume = next(
            volume for volume in alloy["spec"]["template"]["spec"]["volumes"]
            if volume["name"] == "config"
        )
        source_names = [source["configMap"]["name"] for source in config_volume["projected"]["sources"]]
        self.assertTrue(any(name.startswith("alloy-config-") for name in source_names))
        self.assertTrue(any(name.startswith("alloy-unpoller-telemetry-") for name in source_names))

    def test_unifi_dashboards_are_reproducible_and_provisioned(self):
        dashboards = unifi_dashboards()
        self.assertEqual(set(dashboards), {
            "unifi-overview.json", "unifi-gateway.json", "unifi-switches.json",
            "unifi-access-points.json", "unifi-protect.json", "unifi-ups.json", "unifi-unas.json",
        })
        for name, dashboard in dashboards.items():
            self.assertEqual((UNIFI_OUTPUT / name).read_text(), json.dumps(dashboard, indent=2) + "\n")
            self.assertFalse(dashboard["editable"])
            self.assertEqual(dashboard["time"], {"from": "now-1h", "to": "now"})
            self.assertEqual(dashboard["refresh"], "1m")
            self.assertEqual([link["title"] for link in dashboard["links"]], ["Monitoring dashboards", "Monitoring UniFi"])
            self.assertEqual(dashboard["links"][1]["tags"], ["monitoring-unifi"])
            self.assertEqual(dashboard["templating"]["list"][0]["name"], "location")
            self.assertEqual(dashboard["templating"]["list"][1]["name"], "cluster")
            self.assertEqual(dashboard["templating"]["list"][1]["hide"], 2)
            self.assertIn("unifi", dashboard["tags"])
            for index, panel in enumerate(dashboard["panels"]):
                if panel["type"] == "timeseries":
                    self.assertEqual(panel["fieldConfig"]["defaults"]["color"]["mode"], "palette-classic-by-name")
                position = panel["gridPos"]
                for other in dashboard["panels"][index + 1:]:
                    candidate = other["gridPos"]
                    self.assertFalse(
                        position["x"] < candidate["x"] + candidate["w"]
                        and candidate["x"] < position["x"] + position["w"]
                        and position["y"] < candidate["y"] + candidate["h"]
                        and candidate["y"] < position["y"] + position["h"]
                    )
            expressions = " ".join(target.get("expr", "") for panel in dashboard["panels"] for target in panel.get("targets", []))
            self.assertIn('cluster=~"$cluster"', expressions)
            self.assertIn('location=~"$location"', expressions)
        grafana = render(ROOT / "Applications" / "Grafana" / "overlay" / "_SAMPLE")
        index = objects(grafana)
        configmaps = [d for d in grafana if d["kind"] == "ConfigMap" and d["metadata"]["name"].startswith("grafana-monitoring-dashboards-unifi-")]
        self.assertEqual(len(configmaps), 5)
        self.assertEqual({name for cm in configmaps for name in cm["data"]}, set(dashboards))
        for configmap in configmaps:
            self.assertLess(len(json.dumps(configmap).encode()), 150 * 1024)
        deployment = index["Deployment", "grafana"]
        mount = next(m for m in deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] if m["name"] == "monitoring-unifi-dashboards")
        self.assertEqual(mount["mountPath"], "/var/lib/grafana/monitoring-unifi-dashboards")
        volume = next(v for v in deployment["spec"]["template"]["spec"]["volumes"] if v["name"] == "monitoring-unifi-dashboards")
        self.assertEqual(len(volume["projected"]["sources"]), 5)
        self.assertIn("folder: Monitoring UniFi", (GRAFANA / "components/_dashboards/configs/providers.yaml").read_text())

    def test_unifi_dashboard_queries_match_exported_metric_semantics(self):
        dashboards = unifi_dashboards()
        overview_dashboard = dashboards["unifi-overview.json"]
        overview = " ".join(target.get("expr", "") for panel in overview_dashboard["panels"] for target in panel.get("targets", []))
        gateway_dashboard = dashboards["unifi-gateway.json"]
        gateway = " ".join(target.get("expr", "") for panel in gateway_dashboard["panels"] for target in panel.get("targets", []))
        protect = dashboards["unifi-protect.json"]

        self.assertIn('count(max without (tag) (unpoller_device_info', overview)
        self.assertNotIn("unpoller_site_receive_rate_bytes", overview)
        self.assertIn("unpoller_rogueap_channel", " ".join(
            target.get("expr", "") for panel in dashboards["unifi-access-points.json"]["panels"] for target in panel.get("targets", [])
        ))
        self.assertIn("unpoller_site_receive_rate_bytes", gateway)
        self.assertIn("unpoller_client_dpi_receive_bytes", gateway)
        gateway_panels = {panel["title"]: panel for panel in gateway_dashboard["panels"]}
        self.assertIn("Gateway, WAN, IDS, IPS and Network events", gateway_panels)
        self.assertIn("ids|ips|threat|intrusion|rogue|network", gateway_panels["Gateway, WAN, IDS, IPS and Network events"]["targets"][0]["expr"])
        self.assertEqual(gateway_panels["Gateway and WAN SIEM event volume"]["gridPos"]["w"], 24)

        overview_panels = {panel["title"]: panel for panel in overview_dashboard["panels"]}
        self.assertEqual(overview_panels["API event volume"]["gridPos"]["w"], 24)
        self.assertIn("prometheus_remote_storage_samples_in_total", overview_panels["UniFi metric ingestion rate"]["targets"][0]["expr"])
        self.assertIn("loki_write_sent_entries_total", overview_panels["UniFi log delivery rate"]["targets"][0]["expr"])
        self.assertEqual(overview_dashboard["panels"][-1]["title"], "All UniFi log events")

        protect_panel_expressions = {
            panel["title"]: " ".join(target.get("expr", "") for target in panel.get("targets", []))
            for panel in protect["panels"]
        }
        self.assertNotIn("unpoller_protect_sensor_", " ".join(protect_panel_expressions.values()))
        self.assertIn("unpoller_client_receive_bytes_total", protect_panel_expressions["Camera network traffic"])
        self.assertIn("count_over_time", protect_panel_expressions["Detection events"])
        self.assertEqual(next(panel for panel in protect["panels"] if panel["title"] == "Protect event rate")["gridPos"]["w"], 24)
        self.assertIn("unpoller_device_info", protect_panel_expressions["Protect host firmware"])
        self.assertIn("unpoller_device_upgradable", protect_panel_expressions["Protect host updates"])

        for title in ("UnPoller target", "Controller collection", "UniFi Alloy target"):
            self.assertEqual(
                overview_panels[title]["fieldConfig"]["defaults"]["thresholds"]["steps"],
                [{"color": "red", "value": None}, {"color": "green", "value": 1}],
            )
        unas = {panel["title"]: panel for panel in dashboards["unifi-unas.json"]["panels"]}
        self.assertEqual(
            unas["UNAS reachable"]["fieldConfig"]["defaults"]["thresholds"]["steps"],
            [{"color": "red", "value": None}, {"color": "green", "value": 1}],
        )
        self.assertEqual(unas["Disk health"]["fieldConfig"]["defaults"]["thresholds"]["steps"][0]["color"], "#5794F2")
        self.assertEqual({unas[title]["gridPos"]["y"] for title in ("UNAS reachable", "CPU load", "Memory use", "Pool occupancy")}, {4})
        disk_throughput = " ".join(target.get("expr", "") for target in unas["Disk throughput"]["targets"])
        self.assertIn("unpoller_unas_disk_read_kbps", disk_throughput)
        self.assertIn("unpoller_unas_disk_write_kbps", disk_throughput)
        state = next(panel for panel in protect["panels"] if panel["title"] == "Protect device state")
        mappings = state["fieldConfig"]["defaults"]["mappings"][0]["options"]
        self.assertEqual(
            {value: (mapping["text"], mapping["color"]) for value, mapping in mappings.items()},
            {
                "-1": ("Unknown", "#FFB357"),
                "0": ("Disconnected", "red"),
                "1": ("Connecting", "#FFB357"),
                "2": ("Connected", "green"),
            },
        )
        self.assertEqual(state["fieldConfig"]["defaults"]["custom"]["cellOptions"]["type"], "color-text")


    def test_unifi_dashboard_details_use_available_metrics_and_consistent_layout(self):
        dashboards = unifi_dashboards()
        for dashboard in dashboards.values():
            for panel in dashboard["panels"]:
                if panel["type"] == "table":
                    transformations = panel["transformations"]
                    self.assertIn({"id": "organize", "options": {"excludeByName": {"Time": True}}}, transformations)

        def panel(dashboard, title):
            return next(item for item in dashboards[dashboard]["panels"] if item["title"] == title)

        for dashboard, title in (
            ("unifi-gateway.json", "Site traffic"),
            ("unifi-gateway.json", "Internet throughput"),
            ("unifi-gateway.json", "LTE device throughput"),
            ("unifi-switches.json", "Port throughput"),
            ("unifi-access-points.json", "Access point throughput"),
            ("unifi-unas.json", "UNAS network throughput"),
        ):
            chart = next(item for item in dashboards[dashboard]["panels"] if item["title"] == title and item["type"] == "timeseries")
            self.assertEqual(chart["fieldConfig"]["defaults"]["unit"], "Bps")
            override = chart["fieldConfig"]["overrides"][0]
            self.assertEqual(override["matcher"], {"id": "byRegexp", "options": ".* bit/s$"})
            self.assertIn({"id": "unit", "value": "bps"}, override["properties"])
            self.assertIn({"id": "custom.axisPlacement", "value": "right"}, override["properties"])

        retries = panel("unifi-access-points.json", "Radio retry percentage")
        expression = retries["targets"][0]["expr"]
        self.assertIn("unpoller_device_radio_transmit_retries", expression)
        self.assertIn("unpoller_device_radio_transmit_packets", expression)
        self.assertEqual(retries["fieldConfig"]["defaults"]["unit"], "percent")
        self.assertIn({"id": "unit", "value": "string"}, retries["fieldConfig"]["overrides"][0]["properties"])
        self.assertEqual(panel("unifi-access-points.json", "Wireless satisfaction")["fieldConfig"]["defaults"]["unit"], "percent")
        rogue = panel("unifi-access-points.json", "Rogue access points")
        self.assertEqual(len(rogue["targets"]), 2)
        self.assertEqual(rogue["transformations"][0], {"id": "joinByField", "options": {"byField": "observation", "mode": "outer"}})
        self.assertIn('"location", "site_name", "source", "name", "mac", "band", "ap_mac", "radio", "radio_name"', rogue["targets"][0]["expr"])

        ups = dashboards["unifi-ups.json"]
        self.assertIn("unpoller_device_ups_battery_level_percent", " ".join(target.get("expr", "") for panel in ups["panels"] for target in panel.get("targets", [])))
        self.assertEqual(ups["templating"]["list"][2]["name"], "ups")

        switches = dashboards["unifi-switches.json"]
        poe = panel("unifi-switches.json", "PoE draw")
        self.assertEqual(poe["fieldConfig"]["defaults"]["custom"]["stacking"]["mode"], "normal")
        self.assertNotIn("max_power_total", poe["targets"][0]["expr"])
        self.assertIn("max_power_total", panel("unifi-switches.json", "Switch PoE budget")["targets"][0]["expr"])
        speed = panel("unifi-switches.json", "Port link speed")
        self.assertIn({"id": "unit", "value": "string"}, speed["fieldConfig"]["overrides"][0]["properties"])

        unas_progress = panel("unifi-unas.json", "RAID operation progress")["gridPos"]
        unas_temperature = panel("unifi-unas.json", "Disk temperature")["gridPos"]
        self.assertEqual((unas_progress["y"], unas_progress["w"], unas_temperature["y"], unas_temperature["w"]), (unas_temperature["y"], 12, unas_progress["y"], 12))

        for dashboard, title in (
            ("unifi-access-points.json", "Access point SIEM events"),
            ("unifi-gateway.json", "Gateway, WAN, IDS, IPS and Network events"),
            ("unifi-switches.json", "Switch SIEM events"),
            ("unifi-protect.json", "Protect events"),
        ):
            self.assertEqual(dashboards[dashboard]["panels"][-1]["title"], title)

    def test_admin01_location_is_displayed_without_changing_cluster_identity(self):
        env = (APP / "overlay" / "ADMIN01" / "configs" / "alloy.env").read_text()
        alloy = (APP / "overlay" / "ADMIN01" / "configs" / "unpoller.alloy").read_text()
        self.assertIn("UNPOLLER_LOCATION=Walpertskirchen", env)
        self.assertIn('cluster      = "ADMIN01"', alloy)
        self.assertEqual(alloy.count('location     = sys.env("UNPOLLER_LOCATION")'), 2)
if __name__ == "__main__":
    unittest.main()
