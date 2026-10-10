#!/usr/bin/env python3
"""Offline regression fixtures for one-sided LTE channel observations."""
import json
import unittest

from build_application_dashboards import UNIFI_OUTPUT, unifi_dashboards


class LTEChannelTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = unifi_dashboards()["unifi-gateway.json"]
        self.panel = next(p for p in self.dashboard["panels"] if p["id"] == 30)
        self.options = next(t["options"] for t in self.panel["transformations"] if t["id"] == "organize")

    def visible_row(self, row):
        return {
            self.options["renameByName"].get(name, name): value
            for name, value in row.items()
            if not self.options["excludeByName"].get(name)
        }

    def test_one_sided_and_paired_rows_retain_identity(self):
        # Fixtures match Grafana 13.2.3's outer join: A labels are empty for B-only rows.
        for cluster, rx, tx in [("ADMIN01", 100, None), ("APPS01", None, 300), ("HOME01", 200, 400)]:
            with self.subTest(rx=rx, tx=tx):
                identity = f"{cluster} / House / Main / LTE"
                row = {
                    "modem": identity,
                    "cluster": cluster if rx is not None else None,
                    "location": "House" if rx is not None else None,
                    "site_name": "Main" if rx is not None else None,
                    "name": "LTE" if rx is not None else None,
                    "Value #A": rx,
                    "cluster 1": cluster if tx is not None else None,
                    "location 1": "House" if tx is not None else None,
                    "site_name 1": "Main" if tx is not None else None,
                    "name 1": "LTE" if tx is not None else None,
                    "Value #B": tx,
                }
                visible = self.visible_row(row)
                labels = tuple(visible.get(name) for name in ["Cluster", "Location", "Site", "Modem"])
                self.assertTrue(identity in visible.values() or labels == (cluster, "House", "Main", "LTE"))
                self.assertEqual(visible["Receive channel"], rx)
                self.assertEqual(visible["Transmit channel"], tx)

    def test_queries_join_by_full_identity(self):
        join = self.panel["transformations"][0]
        self.assertEqual(join, {"id": "joinByField", "options": {"byField": "modem", "mode": "outer"}})
        self.assertEqual([t["refId"] for t in self.panel["targets"]], ["A", "B"])
        for target in self.panel["targets"]:
            self.assertIn('"modem", " / ", "cluster", "location", "site_name", "name"', target["expr"])

    def test_generated_dashboard_matches_committed_json(self):
        stored = json.loads((UNIFI_OUTPUT / "unifi-gateway.json").read_text())
        self.assertEqual(self.dashboard, stored)


if __name__ == "__main__":
    unittest.main()
