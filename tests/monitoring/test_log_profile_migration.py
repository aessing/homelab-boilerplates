"""Render contracts for the shared-state log collector handover."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
OVERLAYS = ROOT / "Applications/MonitoringAgent/overlay"
SAMPLE = OVERLAYS / "_SAMPLE"
COMPONENT_LABEL = "app.kubernetes.io/component"


def render(overlay):
    manifest = subprocess.run(
        ["kustomize", "build", str(overlay)],
        check=True, capture_output=True, text=True,
    ).stdout
    parsed = subprocess.run(
        ["ruby", "--disable-gems", "-ryaml", "-rjson", "-e",
         "puts YAML.load_stream(STDIN.read).compact.to_json"],
        input=manifest, check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(parsed)


def collectors(objects):
    return {
        obj["spec"]["template"]["metadata"]["labels"][COMPONENT_LABEL]: obj
        for obj in objects
        if obj.get("kind") == "DaemonSet"
        and obj["spec"]["template"]["metadata"]["labels"].get(COMPONENT_LABEL)
        in {"alloy-logs", "alloy-logs-high-memory"}
    }


class LogProfileMigrationTests(unittest.TestCase):
    def assert_handover_guard(self, objects):
        workloads = collectors(objects)
        standard = workloads["alloy-logs"]
        high = workloads["alloy-logs-high-memory"]
        self.assertEqual(standard["metadata"]["namespace"], high["metadata"]["namespace"])
        self.assertEqual(standard["spec"]["selector"]["matchLabels"][COMPONENT_LABEL],
                         "alloy-logs")
        self.assertEqual(high["spec"]["selector"]["matchLabels"][COMPONENT_LABEL],
                         "alloy-logs-high-memory")

        standard_spec = standard["spec"]["template"]["spec"]
        high_spec = high["spec"]["template"]["spec"]
        guard = high_spec["affinity"]["podAntiAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"
        ]
        self.assertEqual(guard, [{
            "labelSelector": {"matchLabels": {COMPONENT_LABEL: "alloy-logs"}},
            "topologyKey": "kubernetes.io/hostname",
        }])

        # The sample patches depend on the original node-affinity list positions.
        def node_term(spec):
            return spec["affinity"]["nodeAffinity"][
                "requiredDuringSchedulingIgnoredDuringExecution"
            ]["nodeSelectorTerms"][0]["matchExpressions"][0]

        standard_term = node_term(standard_spec)
        high_term = node_term(high_spec)
        self.assertEqual(standard_term["key"], "kubernetes.io/hostname")
        self.assertEqual(high_term["key"], "kubernetes.io/hostname")
        self.assertEqual(standard_term["operator"], "NotIn")
        self.assertEqual(high_term["operator"], "In")
        self.assertEqual(standard_term["values"], high_term["values"])
        for spec in (standard_spec, high_spec):
            state = next(volume for volume in spec["volumes"] if volume["name"] == "state")
            self.assertEqual(state["hostPath"]["path"], "/var/lib/alloy-logs")
        self.assertEqual(high["spec"]["updateStrategy"]["rollingUpdate"].get("maxSurge", 0), 0)

    def test_default_sample_keeps_standard_collector(self):
        workloads = collectors(render(SAMPLE))
        self.assertEqual(set(workloads), {"alloy-logs"})
        standard_spec = workloads["alloy-logs"]["spec"]["template"]["spec"]
        self.assertEqual(standard_spec["containers"][0]["resources"]["limits"]["memory"],
                         "384Mi")
        self.assertNotIn("podAntiAffinity", standard_spec.get("affinity", {}))

    def test_enabled_sample_blocks_shared_state_overlap(self):
        # Keep the overlay depth so default Kustomize load restrictions still apply.
        with tempfile.TemporaryDirectory(prefix="_TEST_log_migration_", dir=OVERLAYS) as directory:
            overlay = Path(directory)
            shutil.copytree(SAMPLE, overlay, dirs_exist_ok=True)
            path = overlay / "kustomization.yaml"
            content = path.read_text()
            optional_component = "  # - ../../components/_logs-high-memory"
            self.assertIn(optional_component, content)
            content = content.replace(optional_component, optional_component.replace("# ", "", 1))
            for profile, component in (("standard", "alloy-logs"),
                                       ("high-memory", "alloy-logs-high-memory")):
                block = (
                    f"  # - path: ./patches/alloy-logs-{profile}-nodes.yaml\n"
                    "  #   target:\n"
                    "  #     group: apps\n"
                    "  #     version: v1\n"
                    "  #     kind: DaemonSet\n"
                    f"  #     labelSelector: {COMPONENT_LABEL}={component}"
                )
                self.assertIn(block, content)
                content = content.replace(block, block.replace("  # ", "  "))
                patch = overlay / f"patches/alloy-logs-{profile}-nodes.yaml"
                patch.write_text(patch.read_text().replace("example-high-memory-node", "migration-fixture-node"))
            path.write_text(content)
            objects = render(overlay)
            self.assert_handover_guard(objects)
            high_spec = collectors(objects)["alloy-logs-high-memory"]["spec"]["template"]["spec"]
            self.assertEqual(high_spec["containers"][0]["resources"]["limits"]["memory"], "768Mi")
            term = high_spec["affinity"]["nodeAffinity"][
                "requiredDuringSchedulingIgnoredDuringExecution"
            ]["nodeSelectorTerms"][0]["matchExpressions"][0]
            self.assertEqual(term["values"], ["migration-fixture-node"])

    @unittest.skipUnless(os.environ.get("MONITORING_PRIVATE_OVERLAYS") == "1",
                         "Set MONITORING_PRIVATE_OVERLAYS=1 to render the local admin01 overlay")
    def test_private_admin_overlay_keeps_handover_guard(self):
        overlay = OVERLAYS / "admin01"
        if not overlay.exists():
            self.skipTest("Local admin01 overlay is unavailable")
        self.assert_handover_guard(render(overlay))


if __name__ == "__main__":
    unittest.main()
