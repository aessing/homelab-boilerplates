"""Battery contracts and optional read-only MetricsQL evaluation with fixtures."""

import json
import os
from pathlib import Path
import re
import sys
import unittest
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Applications/MonitoringGrafana/scripts"))
from build_battery_dashboard import battery_dashboard


class BatteryDashboardTests(unittest.TestCase):
    def test_canonical_json_matches_generator(self):
        path = ROOT / "Applications/MonitoringGrafana/components/_dashboards/application-dashboards/device-batteries.json"
        self.assertEqual(json.loads(path.read_text()), battery_dashboard())

    def test_kpis_are_first_and_fit_one_row(self):
        panels = battery_dashboard()["panels"][1:7]
        self.assertEqual([p["type"] for p in panels], ["stat"] * 6)
        self.assertEqual(sum(p["gridPos"]["w"] for p in panels), 24)
        self.assertEqual(len({p["gridPos"]["y"] for p in panels}), 1)

    def test_queries_fit_backend_limit(self):
        for p in battery_dashboard()["panels"]:
            for t in p.get("targets", []):
                self.assertLess(len(t["expr"].encode()), 16384, p["title"])


@unittest.skipUnless(os.environ.get("BATTERY_QUERY_URL"), "Set BATTERY_QUERY_URL to a read-only VictoriaMetrics endpoint")
class BatteryQueryTests(unittest.TestCase):
    # Same entity in two clusters, fractional boundaries, missing data and stale
    # data expose errors that a simple happy-path query would not detect.
    CASES = [
        ("one", "zero", 0, 1, 0, "Critical"),
        ("two", "zero", 0, 1, 0, "Critical"),
        ("one", "ten", 10, 1, 0, "Critical"),
        ("one", "fractional", 10.5, 1, 0, "Warning"),
        ("one", "twenty", 20, 1, 0, "Warning"),
        ("one", "healthy", 20.5, 1, 0, "Healthy"),
        ("one", "full", 100, 1, 0, "Healthy"),
        ("one", "invalid", 101, 1, 0, "Unknown"),
        ("one", "negative", -5, 1, 0, "Unknown"),
        ("one", "unavailable", 50, 0, 0, "Unknown"),
        ("one", "missing", None, 1, 0, "Unknown"),
        ("one", "stale", 50, 1, 180, "Unknown"),
    ]

    def fixture(self, kind):
        items = []
        for cluster, entity, value, available, age, _ in self.CASES:
            if kind == "current" and value is None:
                continue
            if kind == "info" and entity == "missing":
                continue
            scalar = {"current": value, "inventory": 50, "availability": available,
                      "info": 1, "timestamp": f"time() - {age}"}[kind]
            labels = {"cluster": cluster, "entity": "sensor." + entity}
            if kind in {"current", "availability", "timestamp"}:
                labels["friendly_name"] = entity
            if kind == "info":
                labels["area"] = "room"
            args = ", ".join(json.dumps(item) for pair in labels.items() for item in pair)
            items.append(f'label_set(vector({scalar}), {args})')
        return "(" + " or ".join(items) + ")"

    def evaluate(self, panel_title, down=False, empty=False, no_availability=False):
        p = next(p for p in battery_dashboard()["panels"] if p["title"] == panel_title)
        expr = p["targets"][0]["expr"]
        sensor = r'homeassistant_sensor_battery_percent\{[^}]+\}'
        expr = re.sub(r'last_over_time\(' + sensor + r'\[30d\]\)', 'fixture_inventory', expr)
        expr = re.sub(r'timestamp\(' + sensor + r'\)', 'fixture_timestamp', expr)
        expr = re.sub(sensor, 'fixture_current', expr)
        expr = re.sub(r'homeassistant_entity_available\{[^}]+\}', 'fixture_availability', expr)
        expr = re.sub(r'homeassistant_entity_info\{[^}]+\}', 'fixture_info', expr)
        up = f'(label_set(vector({0 if down else 1}), "cluster", "one") or label_set(vector({0 if down else 1}), "cluster", "two"))'
        expr = re.sub(r'up\{[^}]+\}', up, expr)
        fixtures = {kind: '(vector(1) > 2)' if empty else self.fixture(kind)
                    for kind in ['inventory', 'timestamp', 'current', 'availability', 'info']}
        if no_availability:
            fixtures['availability'] = '(vector(1) > 2)'
        expr = 'WITH (' + ', '.join(f'fixture_{kind} = {value}' for kind, value in fixtures.items()) + ') ' + expr
        request = urllib.request.Request(os.environ["BATTERY_QUERY_URL"].rstrip("/") + "/api/v1/query",
                                         data=urllib.parse.urlencode({"query": expr}).encode())
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        self.assertEqual(data["status"], "success")
        return data["data"]["result"]

    def test_boundary_counts_partition_inventory(self):
        expected = {"Observed batteries": 12, "Healthy (>20%)": 2,
                    "Warning (10–20%)": 2, "Almost empty (≤10%)": 3,
                    "Unknown / unavailable": 5, "Lowest battery": 0}
        for title, value in expected.items():
            with self.subTest(title=title):
                self.assertEqual(float(self.evaluate(title)[0]["value"][1]), value)

    def test_table_has_one_row_per_entity_and_cluster(self):
        rows = self.evaluate("All device batteries")
        actual = {(r["metric"]["cluster"], r["metric"]["entity"]):
                  (r["metric"]["status"], float(r["value"][1])) for r in rows}
        self.assertEqual(len(rows), len(self.CASES))
        for cluster, entity, value, _, _, status in self.CASES:
            self.assertEqual(actual[(cluster, "sensor." + entity)],
                             (status, -1 if status == "Unknown" else value))

    def test_attention_list_excludes_healthy(self):
        rows = self.evaluate("Batteries needing attention")
        self.assertEqual(len(rows), 10)
        self.assertNotIn("Healthy", {r["metric"]["status"] for r in rows})

    def test_failed_scrape_never_shows_healthy_charge(self):
        self.assertEqual(float(self.evaluate("Unknown / unavailable", down=True)[0]["value"][1]), 12)
        self.assertEqual(float(self.evaluate("Almost empty (≤10%)", down=True)[0]["value"][1]), 0)
        self.assertEqual(self.evaluate("Lowest battery", down=True), [])

    def test_empty_inventory_does_not_become_healthy_zero(self):
        for title in ["Observed batteries", "Healthy (>20%)", "Warning (10–20%)",
                      "Almost empty (≤10%)", "Unknown / unavailable", "Lowest battery"]:
            with self.subTest(title=title):
                self.assertEqual(self.evaluate(title, empty=True), [])

    def test_disappeared_metadata_has_explicit_telemetry_loss_state(self):
        dashboard = battery_dashboard()
        for title in ["Observed batteries", "Healthy (>20%)", "Warning (10–20%)",
                      "Almost empty (≤10%)", "Unknown / unavailable"]:
            with self.subTest(title=title):
                self.assertEqual(self.evaluate(title, no_availability=True), [])
                p = next(p for p in dashboard['panels'] if p['title'] == title)
                self.assertEqual(p['fieldConfig']['defaults']['noValue'], 'No battery telemetry')
        self.assertEqual(self.evaluate('All device batteries', no_availability=True), [])


if __name__ == "__main__":
    unittest.main()
