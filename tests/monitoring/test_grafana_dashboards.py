"""Regression checks for the file-provisioned Grafana monitoring dashboards."""

import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "Applications" / "MonitoringGrafana"
DASHBOARDS = APP / "components" / "_dashboards" / "dashboards"
PROVIDER = APP / "components" / "_dashboards" / "configs" / "providers.yaml"
BUILDER = APP / "scripts" / "build_dashboards.py"
EXPECTED = {
    "00-overview.json": "mon-overview",
    "10-cluster.json": "mon-cluster",
    "20-node.json": "mon-node",
    "30-pod.json": "mon-pod",
    "40-k3s-etcd.json": "mon-k3s",
    "50-network.json": "mon-network",
    "60-storage.json": "mon-storage",
    "80-platform.json": "mon-platform",
    "90-pipeline.json": "mon-pipeline",
    "100-daily.json": "mon-daily",
    "110-capacity.json": "mon-capacity",
}
EXPECTED_TITLES = {
    "Overview",
    "Cluster and Workloads",
    "Node Diagnostics",
    "Pod and Container Diagnostics",
    "K3s and etcd",
    "DNS and Networking",
    "Storage and Longhorn",
    "Controllers and Certificates",
    "Collection and Metrics Backend",
    "Daily Review",
    "Capacity and Reliability",
}


def load_builder():
    spec = importlib.util.spec_from_file_location("monitoring_dashboard_builder", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(path):
    built = subprocess.run(
        ["kustomize", "build", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    result = subprocess.run(
        ["kubectl", "create", "--dry-run=client", "-f", "-", "-o", "json"],
        input=built.stdout,
        capture_output=True,
        text=True,
        check=True,
    )
    decoder = json.JSONDecoder()
    documents = []
    offset = 0
    while offset < len(result.stdout):
        document, offset = decoder.raw_decode(result.stdout, offset)
        documents.append(document)
        while offset < len(result.stdout) and result.stdout[offset].isspace():
            offset += 1
    return documents


class GrafanaDashboards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = sorted(DASHBOARDS.glob("*.json"))
        cls.dashboards = {path.name: json.loads(path.read_text()) for path in cls.files}

    def test_expected_files_uids_and_folder_provider(self):
        self.assertEqual({path.name for path in self.files}, set(EXPECTED))
        self.assertEqual(
            {dashboard["uid"] for dashboard in self.dashboards.values()},
            set(EXPECTED.values()),
        )
        self.assertEqual(
            {dashboard["title"] for dashboard in self.dashboards.values()},
            EXPECTED_TITLES,
        )
        for dashboard in self.dashboards.values():
            self.assertNotRegex(dashboard["title"], r"^\d")
        provider = PROVIDER.read_text()
        for value in (
            "apiVersion: 1",
            "name: monitoring-infrastructure",
            "folder: Monitoring Metrics",
            "folderUid: monitoring-infrastructure",
            "type: file",
            "disableDeletion: false",
            "allowUiUpdates: false",
            "path: /var/lib/grafana/monitoring-dashboards",
        ):
            self.assertIn(value, provider)
        self.assertNotIn("foldersFromFilesStructure", provider)

    def test_generated_json_is_canonical(self):
        builder = load_builder()
        by_file = {spec["file"]: spec for spec in builder.PROVISIONED_DASHBOARDS}
        self.assertEqual(set(by_file), set(EXPECTED))
        for name, dashboard in self.dashboards.items():
            with self.subTest(dashboard=name):
                expected = json.dumps(builder.build(by_file[name]), indent=2, sort_keys=False) + "\n"
                self.assertEqual((DASHBOARDS / name).read_text(), expected)
                self.assertEqual(dashboard["id"], None)
                self.assertFalse(dashboard["editable"])

    def test_queries_datasource_intervals_and_panel_budget(self):
        for name, dashboard in self.dashboards.items():
            with self.subTest(dashboard=name):
                query_count = 0
                panel_ids = set()
                for panel in dashboard["panels"]:
                    self.assertNotIn(panel["id"], panel_ids)
                    panel_ids.add(panel["id"])
                    for target in panel.get("targets", []):
                        query_count += 1
                        self.assertEqual(target["datasource"]["uid"], "monitoring-metrics")
                        self.assertIn(target["interval"], {"15s", "30s", "60s"})
                        expr = target["expr"]
                        self.assertNotIn("or vector(0)", expr.lower())
                        if "rate(" in expr:
                            self.assertIn("$__rate_interval", expr)
                self.assertGreaterEqual(len(dashboard["panels"]), 12)
                # Node diagnostics also includes four host-maintenance queries.
                self.assertLessEqual(query_count, 27 if name == "20-node.json" else 22)

    def test_layout_does_not_overlap(self):
        for name, dashboard in self.dashboards.items():
            with self.subTest(dashboard=name):
                panels = dashboard["panels"]
                for index, left in enumerate(panels):
                    a = left["gridPos"]
                    self.assertGreater(a["h"], 0)
                    self.assertGreater(a["w"], 0)
                    self.assertLessEqual(a["x"] + a["w"], 24)
                    for right in panels[index + 1:]:
                        b = right["gridPos"]
                        overlap = not (
                            a["x"] + a["w"] <= b["x"]
                            or b["x"] + b["w"] <= a["x"]
                            or a["y"] + a["h"] <= b["y"]
                            or b["y"] + b["h"] <= a["y"]
                        )
                        self.assertFalse(overlap, f"overlap: {left['title']} / {right['title']}")

    def test_navigation_variables_and_report_defaults(self):
        for name, dashboard in self.dashboards.items():
            with self.subTest(dashboard=name):
                self.assertEqual(dashboard["templating"]["list"][0]["name"], "cluster")
                self.assertEqual(dashboard["templating"]["list"][0]["allValue"], ".*")
                self.assertEqual(len(dashboard["links"]), 2)
                all_dashboards, category = dashboard["links"]
                self.assertEqual(all_dashboards["title"], "Monitoring dashboards")
                self.assertEqual(all_dashboards["tags"], ["monitoring"])
                self.assertEqual(category["title"], "Monitoring Metrics")
                self.assertEqual(category["tags"], ["monitoring-metrics"])
                for link in dashboard["links"]:
                    self.assertEqual(link["type"], "dashboards")
                    self.assertTrue(link["asDropdown"])
                    self.assertTrue(link["includeVars"])
                    self.assertTrue(link["keepTime"])
                for panel in dashboard["panels"]:
                    for data_link in panel.get("fieldConfig", {}).get("defaults", {}).get("links", []):
                        target_uid = data_link["url"].split("/d/", 1)[1].split("?", 1)[0]
                        self.assertIn(target_uid, set(EXPECTED.values()) | {"mon-postgres"})
                        self.assertIn("${__url_time_range}", data_link["url"])
                        self.assertIn("var-cluster=", data_link["url"])
        operational = set(EXPECTED) - {"100-daily.json"}
        for name in operational:
            self.assertEqual(self.dashboards[name]["time"], {"from": "now-1h", "to": "now"})
            self.assertEqual(self.dashboards[name]["refresh"], "1m")
        for dashboard in self.dashboards.values():
            self.assertIn("metrics", dashboard["tags"])
            description = next(panel for panel in dashboard["panels"] if panel["type"] == "text")
            self.assertEqual(description["title"], "About this dashboard")
            self.assertNotIn("**Purpose**", description["options"]["content"])
            self.assertTrue(description["options"]["content"].startswith(dashboard["description"]))
            self.assertIn(dashboard["description"], description["options"]["content"])
        self.assertEqual(self.dashboards["100-daily.json"]["time"], {"from": "now-24h", "to": "now"})
        self.assertEqual(self.dashboards["100-daily.json"]["refresh"], "1m")
        self.assertEqual(self.dashboards["110-capacity.json"]["time"]["from"], "now-1h")
        self.assertEqual(self.dashboards["110-capacity.json"]["refresh"], "1m")
        for dashboard in self.dashboards.values():
            self.assertEqual(dashboard["timepicker"]["refresh_intervals"], ["1m", "5m", "15m", "30m", "1h"])

    def test_visual_and_missing_data_contract(self):
        suite_text = ""
        for name, dashboard in self.dashboards.items():
            text = json.dumps(dashboard)
            suite_text += text
            with self.subTest(dashboard=name):
                self.assertNotRegex(text.lower(), r"grafana[_ -]?logo|grafana_icon|\.svg")
                self.assertIn("N/A", text)
                for panel in dashboard["panels"]:
                    if panel["type"] == "timeseries":
                        self.assertEqual(
                            panel["fieldConfig"]["defaults"]["color"]["mode"],
                            "palette-classic-by-name",
                        )
                        self.assertEqual(panel["fieldConfig"]["overrides"], [])
                        self.assertFalse(panel["fieldConfig"]["defaults"]["custom"]["spanNulls"])
                    if panel["type"] == "table":
                        self.assertEqual(panel["gridPos"]["w"], 24)
        self.assertIn("#5794F2", suite_text)
        self.assertNotIn("#8AB8FF", suite_text)
        self.assertNotIn("#1F60C4", suite_text)
        self.assertIn("#FFB357", suite_text)
        self.assertNotIn("#F2CC0C", suite_text)
        self.assertNotIn("#FF780A", suite_text)

    def test_cache_hit_ratios_use_source_counters(self):
        def expression(dashboard, title):
            panel = next(item for item in dashboard["panels"] if item["title"] == title)
            return panel["targets"][0]["expr"]

        coredns = expression(self.dashboards["50-network.json"], "CoreDNS cache hit ratio")
        self.assertIn("sum by (cluster) (rate(coredns_cache_hits_total", coredns)
        self.assertIn("sum by (cluster) (rate(coredns_cache_misses_total", coredns)
        self.assertIn(")) + sum by (cluster) (rate(coredns_cache_misses_total", coredns)

        builder = load_builder()
        database = expression(builder.build(next(spec for spec in builder.DASHBOARDS if spec["uid"] == "mon-postgres")), "Database cache hit ratio")
        self.assertIn("cnpg_pg_stat_database_blks_hit", database)
        self.assertIn("cnpg_pg_stat_database_blks_read", database)
        self.assertNotIn("cnpg_cache_hits", database)
        self.assertNotIn("cnpg_cache_miss", database)

    def test_remote_write_queue_has_detailed_chart(self):
        pipeline = self.dashboards["90-pipeline.json"]
        stat_panel = next(panel for panel in pipeline["panels"] if panel["title"] == "Remote Write pending samples")
        self.assertIn("normal", stat_panel["description"].lower())
        chart_panel = next(panel for panel in pipeline["panels"] if panel["title"] == "Remote Write queue depth")
        self.assertEqual(chart_panel["type"], "timeseries")
        self.assertEqual(chart_panel["targets"][0]["interval"], "15s")
        self.assertIn("sum by (cluster) (prometheus_remote_storage_samples_pending", chart_panel["targets"][0]["expr"])

    def test_requested_sorting_naming_and_layout(self):
        def panel(dashboard, title):
            return next(item for item in dashboard["panels"] if item["title"] == title)

        for dashboard_name in ("00-overview.json", "80-platform.json", "100-daily.json"):
            certificate = panel(self.dashboards[dashboard_name], "Certificate lifetime")
            self.assertEqual(certificate["options"]["sortBy"], [{"desc": False, "displayName": "Value"}])

        availability = panel(self.dashboards["100-daily.json"], "Target availability by cluster and job")
        self.assertEqual(availability["options"]["sortBy"], [{"desc": False, "displayName": "Value"}])
        pvc = panel(self.dashboards["60-storage.json"], "PVC filesystem used")
        self.assertIn("sort_desc(", pvc["targets"][0]["expr"])

        capacity_titles = {item["title"] for item in self.dashboards["110-capacity.json"]["panels"]}
        self.assertIn("Monitoring Metrics Storage", capacity_titles)
        self.assertIn("Metrics ingestion and series activity", capacity_titles)
        self.assertNotIn("VictoriaMetrics growth", capacity_titles)
        self.assertNotIn("Ingestion and churn", capacity_titles)

        for dashboard_name, title in (
            ("90-pipeline.json", "VictoriaMetrics disk"),
            ("110-capacity.json", "Monitoring Metrics Storage"),
        ):
            storage = panel(self.dashboards[dashboard_name], title)
            legends = [target["legendFormat"] for target in storage["targets"]]
            expressions = [target["expr"] for target in storage["targets"]]
            self.assertEqual(legends, ["PVC used", "data size", "write-stop threshold", "PVC capacity"])
            self.assertIn("kubelet_volume_stats_capacity_bytes", expressions[2])
            self.assertIn("vm_free_disk_space_limit_bytes", expressions[2])
            self.assertIn("kubelet_volume_stats_used_bytes", expressions[0])

        daily_titles = {item["title"] for item in self.dashboards["100-daily.json"]["panels"]}
        self.assertIn("PostgreSQL backup freshness", daily_titles)
        self.assertIn("Longhorn backup freshness", daily_titles)
        self.assertIn("Longhorn snapshot overview", daily_titles)

        network = self.dashboards["50-network.json"]
        cache = panel(network, "CoreDNS cache hit ratio")["gridPos"]
        request_rate = panel(network, "Traefik request rate")["gridPos"]
        self.assertEqual(cache["h"], request_rate["h"])
        duration = panel(network, "Traefik service duration")["gridPos"]
        l2 = panel(network, "MetalLB L2 activity")["gridPos"]
        self.assertEqual(duration["y"], l2["y"])
        self.assertEqual(duration["x"] + duration["w"], l2["x"])

        k3s = self.dashboards["40-k3s-etcd.json"]
        api_chart = panel(k3s, "API request rate")["gridPos"]
        pending = panel(k3s, "Pending etcd proposals")["gridPos"]
        self.assertGreater(api_chart["y"], pending["y"])
        self.assertEqual(api_chart["x"], 0)

    def test_corrected_metric_semantics_and_legends(self):
        def panel(dashboard, title):
            return next(item for item in dashboard["panels"] if item["title"] == title)

        pod = self.dashboards["30-pod.json"]
        not_ready = panel(pod, "Not-ready containers")["targets"][0]["expr"]
        self.assertIn("1 - kube_pod_container_status_ready", not_ready)
        self.assertIn('kube_pod_status_phase{', not_ready)
        self.assertIn('phase="Running"', not_ready)
        self.assertNotIn("Container filesystem usage", {item["title"] for item in pod["panels"]})

        storage = self.dashboards["60-storage.json"]
        backup_state = panel(storage, "Longhorn backup state")
        self.assertNotIn("== 1", backup_state["targets"][0]["expr"])
        self.assertIn("Completed", json.dumps(backup_state["fieldConfig"]["defaults"]["mappings"]))
        storage_titles = [item["title"] for item in storage["panels"]]
        self.assertIn("Longhorn snapshot overview", storage_titles)
        self.assertEqual(storage_titles.index("Last Longhorn backup age") + 1, storage_titles.index("Longhorn backup state"))
        io = panel(storage, "Longhorn I/O")["gridPos"]
        latency = panel(storage, "Longhorn volume I/O latency")["gridPos"]
        self.assertEqual(io["y"], latency["y"])
        self.assertEqual(io["x"] + io["w"], latency["x"])

        builder = load_builder()
        postgres = builder.build(next(spec for spec in builder.DASHBOARDS if spec["uid"] == "mon-postgres"))
        replication = panel(postgres, "Replication delay")
        self.assertEqual(replication["fieldConfig"]["defaults"]["unit"], "ms")
        self.assertIn("1000 *", replication["targets"][0]["expr"])
        cache = panel(postgres, "Database cache hit ratio")
        self.assertEqual(cache["targets"][0]["legendFormat"], "{{cluster}} - {{cnpg_cluster}} - {{datname}}")
        transactions = panel(postgres, "Transactions and deadlocks")
        self.assertEqual(transactions["targets"][0]["legendFormat"], "{{cluster}} - {{cnpg_cluster}} - {{__name__}}")

    def test_status_colors_match_panel_semantics(self):
        def panel(dashboard, title):
            return next(item for item in dashboard["panels"] if item["title"] == title)

        overview = self.dashboards["00-overview.json"]
        observed_steps = panel(overview, "Observed clusters")["fieldConfig"]["defaults"]["thresholds"]["steps"]
        self.assertEqual(observed_steps, [
            {"color": "red", "value": None},
            {"color": "green", "value": 1},
        ])

        cluster = self.dashboards["10-cluster.json"]
        pending_steps = panel(cluster, "Pending Pods")["fieldConfig"]["defaults"]["thresholds"]["steps"]
        self.assertEqual(pending_steps, [
            {"color": "green", "value": None},
            {"color": "#FFB357", "value": 1},
            {"color": "red", "value": 5},
        ])

        builder = load_builder()
        postgres = builder.build(next(spec for spec in builder.DASHBOARDS if spec["uid"] == "mon-postgres"))
        suspended_steps = panel(postgres, "Suspended backup schedules")["fieldConfig"]["defaults"]["thresholds"]["steps"]
        self.assertEqual(suspended_steps, [
            {"color": "green", "value": None},
            {"color": "#FFB357", "value": 1},
        ])

    def test_public_artifacts_have_no_private_data_or_secrets(self):
        files = [BUILDER, PROVIDER, *self.files]
        secret_words = re.compile(r"(?i)(bearer\s+[a-z0-9]|basicAuthPassword\s*[:=]\s*[^$]|password\s*[:=]\s*[^$]|api[_-]?key\s*[:=])")
        domain = re.compile(r"(?i)home\.essing\.org")
        address = re.compile(r"(?<![\w.])(?:10|127|169\.254|172\.(?:1[6-9]|2\d|3[01])|192\.168)(?:\.\d{1,3}){2,3}(?![\w.])")
        for path in files:
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIsNone(secret_words.search(text))
                self.assertIsNone(domain.search(text))
                for match in address.finditer(text):
                    value = match.group(0)
                    try:
                        ip = ipaddress.ip_address(value)
                    except ValueError:
                        continue
                    self.fail(f"private address in {path}: {ip}")

    def test_dashboard_files_and_configmaps_are_bounded(self):
        for path in self.files:
            self.assertLess(path.stat().st_size, 200 * 1024, path.name)
        docs = render(ROOT / "Applications" / "Grafana" / "overlay" / "_SAMPLE")
        configmaps = [doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"].startswith("grafana-monitoring-dashboard")]
        self.assertEqual(len(configmaps), 13)
        for configmap in configmaps:
            total = sum(len(value.encode()) for value in configmap.get("data", {}).values())
            self.assertLess(total, 1024 * 1024)
            self.assertLess(len(json.dumps(configmap).encode()), 250 * 1024)

    def test_sample_render_mounts_all_dashboard_configmaps(self):
        docs = render(ROOT / "Applications" / "Grafana" / "overlay" / "_SAMPLE")
        deployment = next(doc for doc in docs if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "grafana")
        pod = deployment["spec"]["template"]["spec"]
        container = next(item for item in pod["containers"] if item["name"] == "grafana")
        self.assertEqual(container["resources"]["requests"]["memory"], "256Mi")
        self.assertEqual(container["resources"]["limits"]["memory"], "2Gi")
        environment = {item["name"]: item.get("value") for item in container["env"]}
        self.assertEqual(environment["GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES"], "false")
        self.assertEqual(environment["GF_PLUGINS_PREINSTALL_AUTO_UPDATE"], "false")
        self.assertEqual(environment["GF_PLUGINS_PREINSTALL_DISABLED"], "true")
        mounts = {item["name"]: item for item in container["volumeMounts"]}
        self.assertEqual(mounts["monitoring-dashboard-provider"]["mountPath"], "/etc/grafana/provisioning/dashboards/monitoring.yaml")
        self.assertEqual(mounts["monitoring-dashboards"]["mountPath"], "/var/lib/grafana/monitoring-dashboards")
        volumes = {item["name"]: item for item in pod["volumes"]}
        projected = volumes["monitoring-dashboards"]["projected"]["sources"]
        self.assertEqual(len(projected), 3)
        datasource = next(doc for doc in docs if doc["kind"] == "ConfigMap" and doc["metadata"]["name"].startswith("grafana-monitoring-metrics-datasource"))
        self.assertIn("name: Monitoring Metrics", datasource["data"]["monitoring-metrics.yaml"])
        datasource_secret = next(doc for doc in docs if doc["kind"] == "Secret" and doc["metadata"]["name"].startswith("grafana-monitoring-datasource"))
        env_by_name = {item["name"]: item for item in container["env"]}
        self.assertEqual(
            env_by_name["VM_USERNAME"]["valueFrom"]["secretKeyRef"],
            {"name": datasource_secret["metadata"]["name"], "key": "username"},
        )
        self.assertEqual(
            env_by_name["VM_PASSWORD"]["valueFrom"]["secretKeyRef"],
            {"name": datasource_secret["metadata"]["name"], "key": "password"},
        )
        historydb_secret = next(doc for doc in docs if doc["kind"] == "Secret" and doc["metadata"]["name"].startswith("grafana-home-assistant-historydb-datasource"))
        self.assertEqual(
            env_by_name["HA_HISTORYDB_USERNAME"]["valueFrom"]["secretKeyRef"],
            {"name": historydb_secret["metadata"]["name"], "key": "username"},
        )
        self.assertEqual(
            env_by_name["HA_HISTORYDB_PASSWORD"]["valueFrom"]["secretKeyRef"],
            {"name": historydb_secret["metadata"]["name"], "key": "password"},
        )

    @unittest.skipUnless(os.getenv("MONITORING_PRIVATE_OVERLAYS"), "private overlays disabled")
    def test_private_grafana_overlay_renders(self):
        docs = render(ROOT / "Applications" / "Grafana" / "overlay" / "apps01")
        names = {doc["metadata"]["name"] for doc in docs if doc["kind"] == "ConfigMap"}
        self.assertTrue(any(name.startswith("grafana-monitoring-dashboard-provider") for name in names))


if __name__ == "__main__":
    unittest.main()
