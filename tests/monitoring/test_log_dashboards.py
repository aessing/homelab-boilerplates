"""Checks for the two provisioned OSS log dashboards and their query contracts."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest
import urllib.parse
import urllib.request

from test_kustomize import APPS, objects, render

APP = APPS / "MonitoringGrafana"
sys.path.insert(0, str(APP / "scripts"))
from build_log_dashboards import dashboards


class LogDashboards(unittest.TestCase):
    def test_canonical_layout_and_query_budgets(self):
        for name, dashboard in dashboards().items():
            self.assertEqual((APP / "components/_dashboards/log-dashboards" / name).read_text(), json.dumps(dashboard, indent=2) + "\n")
            self.assertFalse(dashboard["title"][0].isdigit())
            self.assertEqual(dashboard["refresh"], "30s")
            self.assertFalse(dashboard["editable"])
            self.assertLessEqual(sum(len(p.get("targets", [])) for p in dashboard["panels"]), 24)
            for i, panel in enumerate(dashboard["panels"]):
                pos = panel["gridPos"]
                if panel["type"] in ("logs", "table"):
                    self.assertEqual(pos["w"], 24)
                for other in dashboard["panels"][i+1:]:
                    b = other["gridPos"]
                    self.assertTrue(pos["x"]+pos["w"] <= b["x"] or b["x"]+b["w"] <= pos["x"] or pos["y"]+pos["h"] <= b["y"] or b["y"]+b["h"] <= pos["y"])
                for query in panel.get("targets", []):
                    self.assertNotIn("or vector(0)", query["expr"])
                    self.assertIn(query["datasource"]["uid"], ("monitoring-logs", "monitoring-metrics"))
                    if panel["type"] == "logs":
                        self.assertLessEqual(query["maxLines"], 500)

    def test_folder_mounts_and_reader_datasource(self):
        docs = render(APPS / "Grafana/overlay/_SAMPLE")
        provider = next(d["data"]["monitoring.yaml"] for d in docs if d["kind"] == "ConfigMap" and "monitoring.yaml" in d.get("data", {}))
        self.assertIn("folder: Monitoring Logs", provider)
        self.assertIn("folderUid: monitoring-logs", provider)
        pod = objects(docs)["Deployment", "grafana"]["spec"]["template"]["spec"]
        mount = next(m for c in pod["containers"] if c["name"] == "grafana" for m in c["volumeMounts"] if m["name"] == "monitoring-log-dashboards")
        self.assertTrue(mount["readOnly"])
        self.assertEqual(mount["mountPath"], "/var/lib/grafana/monitoring-log-dashboards")
        datasource = next(d["data"]["monitoring-logs.yaml"] for d in docs if d["kind"] == "ConfigMap" and "monitoring-logs.yaml" in d.get("data", {}))
        self.assertIn("uid: monitoring-logs", datasource)
        self.assertIn("tlsSkipVerify: false", datasource)

    def test_network_status_does_not_hide_failed_members(self):
        d = json.loads((APP / "components/_dashboards/dashboards/50-network.json").read_text())
        panel = next(p for p in d["panels"] if p["title"] == "Ingress and network target health")
        self.assertTrue(panel["targets"][0]["expr"].startswith("min by"))

    @unittest.skipUnless(os.getenv("MONITORING_LOKI_TEST_URL"), "isolated Loki query validation disabled")
    def test_loki_executes_every_explorer_query(self):
        base = os.environ["MONITORING_LOKI_TEST_URL"]
        for panel in dashboards()["log-explorer.json"]["panels"]:
            for target in panel.get("targets", []):
                if target["datasource"]["type"] != "loki":
                    continue
                expr = target["expr"].replace('${search:doublequote}', '""').replace('$__range', '1h').replace('$__auto', '5m')
                for name in ("cluster", "source", "node", "namespace", "workload", "container"):
                    expr = expr.replace('$' + name, '.+' if name in ('cluster', 'source') else '.*')
                params = {"query": expr, "start": str(time.time()-3600), "end": str(time.time()), "step": "60"}
                with self.subTest(panel=panel["title"]):
                    with urllib.request.urlopen(base + '/loki/api/v1/query_range?' + urllib.parse.urlencode(params), timeout=20) as response:
                        self.assertEqual(json.load(response)["status"], "success")

    @unittest.skipUnless(os.getenv("MONITORING_VM_TEST_URL"), "isolated MetricsQL validation disabled")
    def test_metrics_backend_executes_every_pipeline_query(self):
        for panel in dashboards()["log-pipeline-health.json"]["panels"]:
            for target in panel.get("targets", []):
                expr = target["expr"].replace('$cluster', '.*').replace('$__range', '1h').replace('$__rate_interval', '5m')
                with self.subTest(panel=panel["title"]):
                    with urllib.request.urlopen(os.environ['MONITORING_VM_TEST_URL'] + '/api/v1/query?' + urllib.parse.urlencode({'query': expr}), timeout=20) as response:
                        self.assertEqual(json.load(response)["status"], "success")


if __name__ == "__main__":
    unittest.main()
