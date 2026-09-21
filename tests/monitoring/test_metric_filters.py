"""Exercise the deployed Alloy relabel rules against representative samples."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "Applications/MonitoringAgent/components/_alloy/configs/20-metric-filters.alloy"
INFRA_CONFIG = ROOT / "Applications/MonitoringAgent/components/_alloy/configs/30-infrastructure-filters.alloy"
ETCD_CONFIG = ROOT / "Applications/MonitoringAgent/components/_etcd/configs/40-etcd.alloy"


def relabel(labels):
    labels = dict(labels)
    # This deliberately supports only the relabel actions used in this config.
    for block in re.findall(r"rule\s*\{([^}]+)\}", CONFIG.read_text()):
        rule = {}
        for key, value in re.findall(r"^\s*(\w+)\s*=\s*(.+)$", block, re.M):
            rule[key] = json.loads(value)
        action = rule.get("action", "replace")
        expression = rule["regex"]
        if action == "labeldrop":
            labels = {k: v for k, v in labels.items() if not re.fullmatch(expression, k)}
            continue
        value = ";".join(labels.get(k, "") for k in rule["source_labels"])
        matched = re.fullmatch(expression, value)
        if action == "keep":
            if not matched:
                return None
            continue
        if not matched:
            continue
        if action == "drop":
            return None
        if action != "replace":
            raise AssertionError(f"unsupported action: {action}")
        labels[rule["target_label"]] = rule["replacement"]
    return labels


def component_body(path, label):
    text = path.read_text()
    start = text.index(f'prometheus.relabel "{label}"')
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    raise AssertionError(f"unterminated prometheus.relabel component: {label}")


def relabel_component(path, label, labels):
    labels = dict(labels)
    for block in re.findall(r"rule\s*\{([^}]+)\}", component_body(path, label)):
        rule = {}
        for key, value in re.findall(r"^\s*(\w+)\s*=\s*(.+)$", block, re.M):
            rule[key] = json.loads(value)
        action = rule.get("action", "replace")
        expression = rule["regex"]
        if action == "labeldrop":
            labels = {key: value for key, value in labels.items()
                      if not re.fullmatch(expression, key)}
            continue
        value = ";".join(labels.get(key, "") for key in rule["source_labels"])
        matched = re.fullmatch(expression, value)
        if action == "keep":
            if not matched:
                return None
            continue
        if not matched:
            continue
        if action == "drop":
            return None
        labels[rule["target_label"]] = rule["replacement"]
    return labels


class K3sMetricFilters(unittest.TestCase):
    def test_preserves_node_identity_and_essential_metrics(self):
        for name in ["up", "kubelet_running_pods", "apiserver_request_total",
                     "scheduler_schedule_attempts_total", "workqueue_depth",
                     "apiserver_request_duration_seconds_sum",
                     "apiserver_request_duration_seconds_count",
                     "apiserver_response_sizes_sum", "etcd_request_errors_total"]:
            labels = {"__name__": name, "node": "node-a", "instance": "192.0.2.11:10250"}
            self.assertEqual(relabel(labels), labels)

    def test_retains_selected_buckets_and_infinity(self):
        for family in ["apiserver_request_duration_seconds", "etcd_request_duration_seconds"]:
            for boundary in ["0.1", "0.4", "1", "1.0", "5", "5.0", "+Inf"]:
                labels = {"__name__": family + "_bucket", "le": boundary}
                self.assertEqual(relabel(labels), labels)
            for boundary in ["0.005", "0.025", "0.05", "0.2", "0.6", "2", "60"]:
                self.assertIsNone(relabel({"__name__": family + "_bucket", "le": boundary}))

    def test_drops_only_selected_detail_histograms(self):
        for family in ["request_body_size_bytes", "response_sizes", "watch_events_sizes",
                       "watch_list_duration_seconds", "watch_cache_read_wait_seconds",
                       "request_sli_duration_seconds"]:
            for boundary in ["1", "+Inf"]:
                self.assertIsNone(relabel({"__name__": "apiserver_" + family + "_bucket", "le": boundary}))
        labels = {"__name__": "kubelet_pod_start_duration_seconds_bucket", "le": "0.005"}
        self.assertEqual(relabel(labels), labels)


class InfrastructureMetricFilters(unittest.TestCase):
    def test_metrics_server_drops_generic_buckets(self):
        for name in ["apiserver_request_duration_seconds_bucket",
                     "authorization_duration_seconds_bucket",
                     "authentication_duration_seconds_bucket",
                     "field_validation_request_duration_seconds_bucket",
                     "rest_client_request_duration_seconds_bucket",
                     "workqueue_work_duration_seconds_bucket",
                     "go_sched_latencies_seconds_bucket",
                     "metrics_server_manager_tick_duration_seconds_bucket"]:
            self.assertIsNone(relabel_component(INFRA_CONFIG, "metrics_server", {"__name__": name}))

    def test_metrics_server_preserves_component_metrics(self):
        for name in ["metrics_server_kubelet_request_duration_seconds_bucket",
                     "metrics_server_api_metric_freshness_seconds_bucket",
                     "apiserver_request_duration_seconds_sum",
                     "apiserver_request_duration_seconds_count"]:
            labels = {"__name__": name, "le": "1.0"}
            self.assertEqual(relabel_component(INFRA_CONFIG, "metrics_server", labels), labels)

    def test_metallb_reduces_reconcile_histogram(self):
        for boundary in ["0.1", "1", "1.0", "5", "5.0", "+Inf"]:
            labels = {"__name__": "controller_runtime_reconcile_time_seconds_bucket", "le": boundary}
            self.assertEqual(relabel_component(INFRA_CONFIG, "metallb", labels), labels)
        for boundary in ["0.005", "0.5", "2.5", "10.0", "60.0"]:
            labels = {"__name__": "controller_runtime_reconcile_time_seconds_bucket", "le": boundary}
            self.assertIsNone(relabel_component(INFRA_CONFIG, "metallb", labels))
        for name in ["workqueue_queue_duration_seconds_bucket", "go_gc_pauses_seconds_bucket"]:
            self.assertIsNone(relabel_component(INFRA_CONFIG, "metallb", {"__name__": name}))
        labels = {"__name__": "controller_runtime_reconcile_errors_total"}
        self.assertEqual(relabel_component(INFRA_CONFIG, "metallb", labels), labels)


class EtcdMetricFilters(unittest.TestCase):
    def test_keeps_only_native_etcd_and_scrape_health(self):
        for name in ["up", "scrape_duration_seconds", "etcd_server_has_leader",
                     "etcd_server_proposals_failed_total"]:
            labels = {"__name__": name}
            self.assertEqual(relabel_component(ETCD_CONFIG, "etcd_metrics", labels), labels)
        for name in ["grpc_server_handled_total", "kubelet_running_pods",
                     "aggregator_unavailable_apiservice"]:
            self.assertIsNone(relabel_component(ETCD_CONFIG, "etcd_metrics", {"__name__": name}))

    def test_keeps_coarse_essential_latency_buckets(self):
        for family in ["etcd_server_apply_duration_seconds", "etcd_network_peer_round_trip_time_seconds"]:
            for boundary in ["0.0128", "0.0512", "0.2048", "0.8192", "+Inf"]:
                labels = {"__name__": family + "_bucket", "le": boundary}
                self.assertEqual(relabel_component(ETCD_CONFIG, "etcd_metrics", labels), labels)
            self.assertIsNone(relabel_component(
                ETCD_CONFIG, "etcd_metrics", {"__name__": family + "_bucket", "le": "0.0016"}))

        for family in ["etcd_disk_backend_commit_duration_seconds", "etcd_disk_wal_fsync_duration_seconds",
                       "etcd_disk_wal_write_duration_seconds"]:
            for boundary in ["0.008", "0.032", "0.128", "0.512", "2.048", "+Inf"]:
                labels = {"__name__": family + "_bucket", "le": boundary}
                self.assertEqual(relabel_component(ETCD_CONFIG, "etcd_metrics", labels), labels)
            self.assertIsNone(relabel_component(
                ETCD_CONFIG, "etcd_metrics", {"__name__": family + "_bucket", "le": "0.004"}))

    def test_drops_other_buckets_but_keeps_sum_and_count(self):
        self.assertIsNone(relabel_component(
            ETCD_CONFIG, "etcd_metrics", {"__name__": "etcd_debugging_lease_ttl_total_bucket", "le": "1"}))
        for suffix in ["sum", "count"]:
            labels = {"__name__": "etcd_debugging_lease_ttl_total_" + suffix}
            self.assertEqual(relabel_component(ETCD_CONFIG, "etcd_metrics", labels), labels)


if __name__ == "__main__":
    unittest.main()
