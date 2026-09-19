"""Log rollout regressions and opt-in execution of the real Alloy pipeline.

MONITORING_ALLOY_RUNTIME=1 executes synthetic fixtures in the pinned local image.
No cluster resources or real credentials are used by these tests.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

from test_kustomize import APPS, objects, render

CONFIG = APPS / "MonitoringAgent/components/_logs/configs/00-logs.alloy"


class LogsManifests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = render(APPS / "MonitoringAgent/overlay/_SAMPLE")
        cls.logs = render(APPS / "MonitoringLogs/overlay/_SAMPLE")

    def test_single_named_metrics_container_with_all_secrets(self):
        pod = objects(self.agent)["StatefulSet", "alloy-metrics"]["spec"]["template"]["spec"]
        self.assertEqual([c["name"] for c in pod["containers"]], ["alloy-metrics"])
        c = pod["containers"][0]
        self.assertIn("--stability.level=public-preview", c["args"])
        paths = {m["mountPath"] for m in c["volumeMounts"]}
        for name in ("telemetry", "logs", "logs-telemetry"):
            self.assertIn("/var/run/secrets/monitoring-agent-" + name, paths)
        self.assertEqual({v["name"] for v in c["env"]}, {"LOKI_WRITE_URL", "LOKI_TELEMETRY_HOST"})

    def test_log_url_and_bounded_wal(self):
        pod = objects(self.agent)["DaemonSet", "alloy-logs"]["spec"]["template"]["spec"]
        c = pod["containers"][0]
        cms = {d["metadata"]["name"]: d["data"] for d in self.agent if d["kind"] == "ConfigMap"}
        values = {}
        for ref in c["envFrom"]:
            values.update(cms[ref["configMapRef"]["name"]])
        self.assertEqual(values["LOKI_WRITE_URL"], "https://logs.example.com/loki/api/v1/push")
        wal = next(v for v in pod["volumes"] if v["name"] == "wal")
        self.assertEqual(wal["emptyDir"]["sizeLimit"], "512Mi")
        mount = next(v for v in c["volumeMounts"] if v["name"] == "wal")
        self.assertEqual(mount["mountPath"], "/var/lib/alloy/data/loki.write.central")
        self.assertEqual(c["resources"]["requests"]["ephemeral-storage"], "0")
        self.assertNotIn("hostNetwork", pod)
        self.assertNotIn("hostPID", pod)

    def test_network_paths_and_no_direct_backend_bypass(self):
        rules = objects(self.agent)["NetworkPolicy", "alloy-logs-egress"]["spec"]["egress"]
        self.assertTrue({443, 6443, 8443, 53} <= {p["port"] for r in rules for p in r["ports"]})
        backend = objects(self.logs)
        self.assertNotIn(("NetworkPolicy", "monitoring-agent-to-loki"), backend)
        self.assertNotIn(("NetworkPolicy", "monitoring-agent-to-vmauth"), backend)

    def test_retention_and_fresh_install_quota(self):
        config = next(d["data"]["loki.yaml"] for d in self.logs
                      if d["kind"] == "ConfigMap" and "loki.yaml" in d.get("data", {}))
        self.assertIn("retention_period: 2160h", config)
        self.assertIn("retention_enabled: true", config)
        quota = objects(self.agent)["ResourceQuota", "monitoring-agent"]["spec"]["hard"]
        self.assertGreaterEqual(int(quota["persistentvolumeclaims"]), 2)

    def test_short_lived_logs_and_cardinality(self):
        config = CONFIG.read_text()
        self.assertNotIn("tail_from_end = true", config)
        self.assertIn('values = ["filename", "database"]', config)
        self.assertIn('field = "spec.nodeName="', config)


@unittest.skipUnless(os.getenv("MONITORING_ALLOY_RUNTIME"), "local Alloy runtime fixtures disabled")
class LogsRuntime(unittest.TestCase):
    def test_rotation_and_persistent_positions(self):
        name = "monitoring-log-rotation-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory(prefix="monitoring-log-rotation-") as directory:
            temp = Path(directory)
            log = temp / "active.log"
            log.write_text("initial-marker\n")
            (temp / "test.alloy").write_text('''logging { level = "info" }
loki.echo "test" {}
loki.source.file "fixture" {
  targets = [{"__path__" = "/fixtures/active.log", "source" = "fixture"}]
  forward_to = [loki.echo.test.receiver]
  tail_from_end = false
}
''')
            command = ["podman", "run", "--rm", "--name", name, "--network=none", "-v", directory + ":/fixtures",
                       "docker.io/grafana/alloy:v1.19.2", "run", "--storage.path=/fixtures/state", "/fixtures/test.alloy"]
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                time.sleep(3)
                log.rename(temp / "rotated.log")
                log.write_text("rotated-marker\n")
                time.sleep(3)
            finally:
                subprocess.run(["podman", "stop", "--time", "3", name], capture_output=True)
                output, _ = proc.communicate(timeout=15)
            self.assertIn("initial-marker", output)
            self.assertIn("rotated-marker", output)
            with log.open("a") as target:
                target.write("after-restart-marker\n")
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                time.sleep(3)
            finally:
                subprocess.run(["podman", "stop", "--time", "3", name], capture_output=True)
                output, _ = proc.communicate(timeout=15)
            self.assertIn("after-restart-marker", output)
            self.assertNotIn("rotated-marker", output)

    def test_real_cri_redaction_sql_exclusion_and_startup_logs(self):
        source = CONFIG.read_text()
        pipeline = source[source.index('loki.process "pod_logs"'):source.index('loki.source.file "pod_logs"')]
        fixtures = {
            "ordinary": ('startup-marker\n', {}),
            "credentials": ('connected token=synthetic-secret-value\n', {}),
            "payload": ('{"payload":"synthetic-customer-content"}\n', {}),
            "sql": ('SELECT sensitive_field FROM customers\n', {}),
            "access": ('192.0.2.1 - - [01/Jan/2026:00:00:00 +0000] "GET /private-access-marker HTTP/1.1" 200 42\n', {}),
            "database": ('{"level":"error","logger":"postgres","record":{"error_severity":"ERROR","sql_state_code":"23505","statement":"INSERT INTO private_table VALUES (1)","message":"private-customer-name","detail":"private-detail"}}\n', {"database": "postgresql"}),
            "partial": ('partial-marker-end\n', {}),
        }
        name = "monitoring-log-fixture-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory(prefix="monitoring-log-fixtures-") as directory:
            temp = Path(directory)
            targets = []
            for key, (content, labels) in fixtures.items():
                if key == "partial":
                    text = "2026-01-01T00:00:00Z stdout P partial-marker-\n2026-01-01T00:00:00Z stdout F end\n"
                else:
                    text = "2026-01-01T00:00:00Z stdout F " + content
                (temp / (key + ".log")).write_text(text)
                labels.update({"__path__": "/fixtures/" + key + ".log", "source": "pod", "namespace": "fixture", "pod": "test-pod", "pod_uid": "test-uid"})
                targets.append("{" + ", ".join(json.dumps(k) + " = " + json.dumps(v) for k, v in labels.items()) + "}")
            config = ('logging { level = "info" }\nloki.echo "test" {}\n'
                      'loki.secretfilter "redact" {\n forward_to = [loki.echo.test.receiver]\n redact_with = "[REDACTED]"\n}\n'
                      + pipeline + '\nloki.source.file "fixture" {\n targets = [' + ",\n".join(targets) + ',]\n forward_to = [loki.process.pod_logs.receiver]\n tail_from_end = false\n}\n')
            (temp / "test.alloy").write_text(config)
            command = ["podman", "run", "--rm", "--name", name, "--network=none", "-v", directory + ":/fixtures:ro",
                       "docker.io/grafana/alloy:v1.19.2", "run", "--stability.level=experimental", "--storage.path=/tmp/alloy-test", "/fixtures/test.alloy"]
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                time.sleep(6)
            finally:
                subprocess.run(["podman", "stop", "--time", "2", name], capture_output=True)
                output, _ = proc.communicate(timeout=15)
            self.assertIn("startup-marker", output, output)
            self.assertIn("partial-marker-end", output, output)
            self.assertIn("[REDACTED]", output, output)
            self.assertIn("23505", output, output)
            for excluded in ("synthetic-secret-value", "synthetic-customer-content", "private-customer-name", "private-detail", "private_table", "sensitive_field", "private-access-marker"):
                self.assertNotIn(excluded, output, output)
            self.assertNotIn('filename=', output)


if __name__ == "__main__":
    unittest.main()
