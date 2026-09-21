"""Regression coverage for the exporter's Unix datagram reply socket."""
import unittest
from pathlib import Path

from test_grafana_dashboards import render

ROOT = Path(__file__).resolve().parents[2]


class ChronyExporter(unittest.TestCase):
    def test_shared_socket_directory_is_writable_without_root(self):
        docs = render(ROOT / 'Applications/Timeserver/overlay/_SAMPLE')
        pod = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']
        exporter = next(c for c in pod['containers'] if c['name'] == 'chrony-metrics')
        mount = next(v for v in exporter['volumeMounts'] if v['name'] == 'chrony-run')
        self.assertFalse(mount['readOnly'])
        self.assertIn('--chrony.address=unix:///var/run/chrony/chronyd.sock', exporter['args'])
        self.assertEqual(mount['mountPath'], '/var/run/chrony')
        self.assertEqual(exporter['securityContext']['runAsUser'], 100)
        self.assertTrue(exporter['securityContext']['runAsNonRoot'])
        self.assertTrue(exporter['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(exporter['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(exporter['securityContext']['capabilities']['drop'], ['ALL'])


if __name__ == '__main__':
    unittest.main()
