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
        self.assertIn("loki.secretfilter", alloy)
        self.assertNotIn("https://", alloy)
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
        self.assertEqual(set(dashboards), {"unifi-overview.json", "unifi-network.json", "unifi-protect.json", "unifi-unas.json"})
        for name, dashboard in dashboards.items():
            self.assertEqual((UNIFI_OUTPUT / name).read_text(), json.dumps(dashboard, indent=2) + "\n")
            self.assertFalse(dashboard["editable"])
            self.assertEqual(dashboard["templating"]["list"][0]["name"], "cluster")
            self.assertIn("unifi", dashboard["tags"])
            expressions = " ".join(target.get("expr", "") for panel in dashboard["panels"] for target in panel.get("targets", []))
            self.assertIn('cluster=~"$cluster"', expressions)
        grafana = render(ROOT / "Applications" / "Grafana" / "overlay" / "_SAMPLE")
        index = objects(grafana)
        configmaps = [d for d in grafana if d["kind"] == "ConfigMap" and d["metadata"]["name"].startswith("grafana-monitoring-dashboards-unifi-")]
        self.assertEqual({name for cm in configmaps for name in cm["data"]}, set(dashboards))
        deployment = index["Deployment", "grafana"]
        mount = next(m for m in deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] if m["name"] == "monitoring-unifi-dashboards")
        self.assertEqual(mount["mountPath"], "/var/lib/grafana/monitoring-unifi-dashboards")
        self.assertIn("folder: Monitoring UniFi", (GRAFANA / "components/_dashboards/configs/providers.yaml").read_text())

    def test_unifi_dashboard_queries_match_exported_metric_semantics(self):
        dashboards = unifi_dashboards()
        overview = " ".join(target.get("expr", "") for panel in dashboards["unifi-overview.json"]["panels"] for target in panel.get("targets", []))
        network = " ".join(target.get("expr", "") for panel in dashboards["unifi-network.json"]["panels"] for target in panel.get("targets", []))
        protect = dashboards["unifi-protect.json"]

        self.assertIn('count(max without (tag) (unpoller_device_info', overview)
        for metric in ("receive_rate_bytes", "transmit_rate_bytes", "poe_watts"):
            self.assertIn(f'max without (tag) (unpoller_device_port_{metric}', network)
        self.assertIn('max without (tag) (increase(unpoller_device_port_receive_errors_total', network)
        self.assertIn("unpoller_rogueap_channel", network)
        self.assertIn("source,name,mac,security,band,ap_mac,radio,radio_name,oui", network)
        self.assertNotIn("band,channel", network)

        protect_panel_expressions = {
            panel["title"]: " ".join(target.get("expr", "") for target in panel.get("targets", []))
            for panel in protect["panels"]
        }
        self.assertIn("unpoller_protect_sensor_is_opened", protect_panel_expressions["Open sensors"])
        self.assertIn("unpoller_protect_sensor_is_motion_detected", protect_panel_expressions["Motion sensors"])

        network_panel_expressions = {
            panel["title"]: " ".join(target.get("expr", "") for target in panel.get("targets", []))
            for panel in dashboards["unifi-network.json"]["panels"]
        }
        dpi = network_panel_expressions["DPI traffic by category"]
        self.assertIn("unpoller_client_dpi_receive_bytes", dpi)
        self.assertIn("unpoller_client_dpi_transmit_bytes", dpi)
        self.assertNotIn("unpoller_site_dpi_", dpi)
if __name__ == "__main__":
    unittest.main()
