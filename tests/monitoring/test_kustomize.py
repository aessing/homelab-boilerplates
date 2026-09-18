"""Regression checks for monitoring manifests. Requires kustomize and kubectl.

Run: python3 -m unittest discover -s tests/monitoring -v
Set MONITORING_PRIVATE_OVERLAYS=1 to include local, Git-ignored overlays.
No Kubernetes credentials or live cluster access are used.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "Applications"


def render(path):
    built = subprocess.run(
        ["kustomize", "build", str(path)],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        ["kubectl", "create", "--dry-run=client", "-f", "-", "-o", "json"],
        input=built.stdout, capture_output=True, text=True, check=True,
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


def objects(docs):
    return {(d["kind"], d["metadata"]["name"]): d for d in docs}


def container(docs, kind, name):
    return objects(docs)[kind, name]["spec"]["template"]["spec"]["containers"][0]


def bytes_quantity(value):
    value = str(value)
    for unit, multiplier in [("Gi", 1024 ** 3), ("Mi", 1024 ** 2)]:
        if value.endswith(unit):
            return int(value[:-len(unit)]) * multiplier
    return int(value)


class MonitoringManifests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds = {}
        for app in ["MonitoringAgent", "MonitoringMetrics"]:
            for overlay in sorted((APPS / app / "overlay").iterdir()):
                if not overlay.is_dir() or not (overlay / "kustomization.yaml").exists():
                    continue
                if overlay.name != "_SAMPLE" and not os.getenv("MONITORING_PRIVATE_OVERLAYS"):
                    continue
                cls.builds[app, overlay.name] = render(overlay)

    def test_references_and_selectors(self):
        for key, docs in self.builds.items():
            with self.subTest(overlay=key):
                index = objects(docs)
                self.assertEqual(len(index), len(docs))
                for doc in docs:
                    if doc["kind"] not in ("StatefulSet", "Deployment", "DaemonSet"):
                        continue
                    template = doc["spec"]["template"]
                    for label, value in doc["spec"]["selector"]["matchLabels"].items():
                        self.assertEqual(template["metadata"]["labels"][label], value)
                    for c in template["spec"]["containers"]:
                        self.assertNotIn(":0.0.0", c["image"])
                        for ref in c.get("envFrom", []):
                            for field, kind in [("configMapRef", "ConfigMap"), ("secretRef", "Secret")]:
                                if field in ref:
                                    self.assertIn((kind, ref[field]["name"]), index)
                    for volume in template["spec"].get("volumes", []):
                        if "secret" in volume:
                            self.assertIn(("Secret", volume["secret"]["secretName"]), index)
                        sources = volume.get("projected", {}).get("sources", [])
                        if "configMap" in volume:
                            sources = [{"configMap": volume["configMap"]}]
                        for source in sources:
                            cm = source.get("configMap")
                            if cm and not cm.get("optional"):
                                self.assertIn(("ConfigMap", cm["name"]), index)

    def test_agent_runtime_contract(self):
        for (app, overlay), docs in self.builds.items():
            if app != "MonitoringAgent":
                continue
            with self.subTest(overlay=overlay):
                ksm = container(docs, "Deployment", "kube-state-metrics")
                self.assertEqual(ksm["livenessProbe"]["httpGet"], {"path": "/livez", "port": "metrics"})
                self.assertEqual(ksm["readinessProbe"]["httpGet"], {"path": "/readyz", "port": "telemetry"})
                pod = objects(docs)["DaemonSet", "node-exporter"]["spec"]["template"]["spec"]
                self.assertTrue(pod["hostNetwork"])
                self.assertTrue(pod["hostPID"])
                self.assertEqual(pod["dnsPolicy"], "ClusterFirstWithHostNet")
                self.assertIn("--web.listen-address=$(HOST_IP):9100", pod["containers"][0]["args"])
                env = next(d["data"] for d in docs if d["kind"] == "ConfigMap"
                           and "FAST_SCRAPE_INTERVAL" in d.get("data", {}))
                self.assertEqual([env[k] for k in ("FAST_SCRAPE_INTERVAL", "NORMAL_SCRAPE_INTERVAL", "SLOW_SCRAPE_INTERVAL")],
                                 ["15s", "30s", "60s"])
                config = next(d["data"] for d in docs if d["kind"] == "ConfigMap"
                              and "10-infrastructure.alloy" in d.get("data", {}))
                infrastructure = config["10-infrastructure.alloy"]
                infrastructure_filters = config["30-infrastructure-filters.alloy"]
                main = config["00-main.alloy"]
                self.assertIn('"__address__" = "kube-state-metrics:8080"', main)
                self.assertIn('"__address__" = "kube-state-metrics:8081"', main)
                self.assertNotIn("svc.cluster.local", main)
                for job in ("kubernetes-infrastructure", "cloudnativepg-instances", "kube-vip",
                            "metrics-server", "metallb"):
                    self.assertIn(f'job_name        = "{job}"', infrastructure)
                for selector in ("kube-system;;;kube-dns;9153", "longhorn-system;longhorn;longhorn-manager;;9500",
                                 "postgresql;cloudnative-pg;9187", 'replacement   = "$1:2112"',
                                 "kube-system;metrics-server;https",
                                 "metallb-system;metallb;metallb;metricshttps"):
                    self.assertIn(selector, infrastructure)
                self.assertEqual(infrastructure.count("insecure_skip_verify = true"), 2)
                for scrape, destination in (("metrics_server", "metrics_server"), ("metallb", "metallb")):
                    self.assertRegex(
                        infrastructure,
                        rf'prometheus\.scrape "{scrape}" \{{[\s\S]*?forward_to\s*=\s*\[prometheus\.relabel\.{destination}\.receiver\]',
                    )
                for scrape in ("infrastructure_http", "cloudnativepg_instances"):
                    self.assertRegex(
                        infrastructure,
                        rf'prometheus\.scrape "{scrape}" \{{[\s\S]*?forward_to\s*=\s*\[prometheus\.remote_write\.central\.receiver\]',
                    )
                for component in ('prometheus.relabel "metrics_server"', 'prometheus.relabel "metallb"'):
                    self.assertIn(component, infrastructure_filters)
                self.assertIn("controller_runtime_reconcile_time_seconds_bucket", infrastructure_filters)

    def test_network_rules(self):
        for (app, overlay), docs in self.builds.items():
            with self.subTest(app=app, overlay=overlay):
                index = objects(docs)
                dns = index["NetworkPolicy", "allow-dns-egress"]["spec"]["egress"]
                self.assertTrue(all("to" in rule for rule in dns))
                self.assertEqual(dns[0]["to"][0]["podSelector"]["matchLabels"], {"k8s-app": "kube-dns"})
                if app != "MonitoringAgent":
                    continue
                alloy = index["NetworkPolicy", "alloy-internal-egress"]["spec"]["egress"]
                ksm = index["NetworkPolicy", "kube-state-metrics-kubernetes-api-egress"]["spec"]["egress"]
                self.assertIn(6443, [p["port"] for r in ksm for p in r["ports"]])
                self.assertTrue({443, 2112, 2381, 6443, 8000, 8080, 9090, 9100, 9120, 9153, 9187, 9402, 9500, 10250}
                                <= {p["port"] for r in alloy for p in r["ports"]})
                for rule in alloy + ksm:
                    self.assertTrue(rule.get("ports"))
                    for target in rule["to"]:
                        if "ipBlock" in target:
                            self.assertTrue(target["ipBlock"]["cidr"].endswith("/32"))
                applications = next(r for r in alloy if any(
                    t.get("podSelector", {}).get("matchLabels", {}).get("monitoring-metrics-scrape") == "true"
                    for t in r["to"]))
                self.assertEqual(applications["ports"], [{"protocol": "TCP", "port": "metrics"}])
                has_telemetry = any(d["kind"] == "Secret" and d["metadata"]["name"].startswith("monitoring-agent-telemetry-")
                                    for d in docs)
                if has_telemetry:
                    self.assertIn(8443, [p["port"] for r in alloy for p in r["ports"]])

    def test_memory_quota_includes_rollout(self):
        for (app, overlay), docs in self.builds.items():
            with self.subTest(app=app, overlay=overlay):
                quota = next(d["spec"]["hard"] for d in docs if d["kind"] == "ResourceQuota")
                totals = {"limits": 0}
                for d in docs:
                    if d["kind"] not in ("StatefulSet", "Deployment", "DaemonSet"):
                        continue
                    # Three nodes, plus the one extra Deployment Pod allowed during rollout.
                    count = 3 if d["kind"] == "DaemonSet" else d["spec"]["replicas"]
                    if d["kind"] == "Deployment":
                        count += 1
                    for c in d["spec"]["template"]["spec"]["containers"]:
                        self.assertEqual(c["resources"]["requests"], {"cpu": "0", "memory": "0"})
                        for category in totals:
                            totals[category] += count * bytes_quantity(c["resources"][category]["memory"])
                for category in totals:
                    self.assertLessEqual(totals[category], bytes_quantity(quota[category + ".memory"]))
                self.assertNotIn("requests.cpu", quota)
                self.assertNotIn("requests.memory", quota)

    def test_metrics_retention(self):
        for (app, overlay), docs in self.builds.items():
            if app != "MonitoringMetrics":
                continue
            with self.subTest(overlay=overlay):
                workload = next(d for d in docs if d["kind"] == "StatefulSet")
                args = workload["spec"]["template"]["spec"]["containers"][0]["args"]
                self.assertEqual([a for a in args if a.startswith("-retentionPeriod=")], ["-retentionPeriod=90d"])

    def test_infrastructure_dependencies_render(self):
        longhorn = render(ROOT / "Kubernetes" / "61-Longhorn" / "overlay" / "_SAMPLE")
        policy = objects(longhorn)["NetworkPolicy", "monitoring-to-longhorn-manager"]
        self.assertEqual(policy["metadata"]["namespace"], "longhorn-system")
        self.assertEqual(policy["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 9500}])

        snapshots = render(ROOT / "Kubernetes" / "62-CSI-SnapshotController" / "overlay" / "_SAMPLE")
        controller = container(snapshots, "Deployment", "snapshot-controller")
        self.assertIn("--http-endpoint=:8080", controller["args"])
        self.assertIn({"name": "metrics", "containerPort": 8080, "protocol": "TCP"}, controller["ports"])

        postgres = render(ROOT / "Applications" / "PostgreSQL" / "overlay" / "_SAMPLE")
        policy = objects(postgres)["NetworkPolicy", "monitoring-to-database-metrics"]
        self.assertEqual(policy["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 9187}])

    def test_sample_tokens_match_and_are_placeholders(self):
        metrics = self.builds["MonitoringMetrics", "_SAMPLE"]
        agent = self.builds["MonitoringAgent", "_SAMPLE"]
        server = next(d["data"] for d in metrics if d["kind"] == "Secret")
        client = next(d["data"] for d in agent if d["kind"] == "Secret"
                      and d["metadata"]["name"].startswith("monitoring-agent-remote-write-"))
        telemetry = next(d["data"] for d in agent if d["kind"] == "Secret"
                         and d["metadata"]["name"].startswith("monitoring-agent-telemetry-"))
        self.assertEqual(client["token"], server["WRITER_CLUSTER_A_TOKEN"])
        self.assertEqual(telemetry["token"], server["TELEMETRY_TOKEN"])
        for key, value in server.items():
            if key != "GRAFANA_USERNAME":
                self.assertTrue(base64.b64decode(value).decode().startswith("replace-with-"))

    def test_agent_overlay_layouts_match_sample(self):
        base = APPS / "MonitoringAgent" / "overlay"
        paths = {str(p.relative_to(base / "_SAMPLE")) for p in (base / "_SAMPLE").rglob("*") if p.is_file()}
        for app, overlay in self.builds:
            if app == "MonitoringAgent":
                current = {str(p.relative_to(base / overlay)) for p in (base / overlay).rglob("*") if p.is_file()}
                self.assertEqual(paths, current, overlay)

    def test_optional_etcd_collection(self):
        for (app, overlay), docs in self.builds.items():
            if app != "MonitoringAgent":
                continue
            config = next(d["data"] for d in docs if d["kind"] == "ConfigMap"
                          and "10-infrastructure.alloy" in d.get("data", {}))
            if overlay in ("_SAMPLE", "admin01", "apps01", "apps02", "home01"):
                self.assertIn("40-etcd.alloy", config)
                etcd = config["40-etcd.alloy"]
                self.assertIn('label = "node-role.kubernetes.io/etcd=true"', etcd)
                self.assertIn('replacement   = "$1:2381"', etcd)
                self.assertIn('job_name        = "etcd"', etcd)
                self.assertIn('forward_to      = [prometheus.relabel.etcd_metrics.receiver]', etcd)
            else:
                self.assertNotIn("40-etcd.alloy", config)


if __name__ == "__main__":
    unittest.main()
