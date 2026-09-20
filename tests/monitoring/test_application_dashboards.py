"""Application dashboard semantics, reproducibility and provisioning contracts."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "Applications/MonitoringGrafana"
sys.path.insert(0, str(APP / "scripts"))
from build_application_dashboards import dashboards, operations_center, OUTPUT, ROOT_OUTPUT
from test_grafana_dashboards import render


class ApplicationDashboards(unittest.TestCase):
    def test_generated_layout_and_budget(self):
        generated = dashboards()
        self.assertEqual(len(generated), 11)
        self.assertEqual(len({d['uid'] for d in generated.values()}), 11)
        for name, d in generated.items():
            with self.subTest(name=name):
                self.assertEqual((OUTPUT / name).read_text(), json.dumps(d, indent=2) + '\n')
                self.assertFalse(d['title'][0].isdigit())
                self.assertEqual(d['refresh'], '1m')
                self.assertEqual(d['time'], {'from': 'now-1h', 'to': 'now'})
                self.assertEqual([link['title'] for link in d['links']], ['Monitoring dashboards', 'Application reports'])
                self.assertEqual(d['links'][1]['tags'], ['applications'])
                budget = 32 if name == 'postgresql.json' else 24
                self.assertLessEqual(sum(len(p.get('targets', [])) for p in d['panels']), budget)
                ids = [p['id'] for p in d['panels']]
                self.assertEqual(len(ids), len(set(ids)))
                for index, p in enumerate(d['panels']):
                    a = p['gridPos']
                    if p['type'] in ('logs', 'table'):
                        self.assertEqual(a['w'], 24)
                    for q in d['panels'][index + 1:]:
                        b = q['gridPos']
                        self.assertFalse(a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h'])
                    for target in p.get('targets', []):
                        self.assertIn('cluster=~"$cluster"', target['expr'])
                        self.assertNotIn('or vector(0)', target['expr'])
                        self.assertIn(target['datasource']['uid'], ('monitoring-metrics', 'monitoring-logs'))

    def test_monitor_state_and_backend_semantics(self):
        ds = dashboards()
        state = next(p for p in ds['uptime-kuma-monitors.json']['panels'] if p['title'] == 'Monitor status')
        mapping = state['fieldConfig']['defaults']['mappings'][0]['options']
        self.assertEqual(mapping['0']['color'], 'red')
        self.assertEqual(mapping['1']['color'], 'green')
        self.assertEqual(mapping['3']['color'], 'orange')
        expressions = [t['expr'] for name in ('homecdn.json', 'timeserver.json') for p in ds[name]['panels'] for t in p.get('targets', [])]
        self.assertTrue(any('chrony_up{' in q for q in expressions))
        self.assertTrue(any('nginx_up{' in q for q in expressions))
        self.assertTrue(any('chrony_tracking_last_offset_seconds' in q for q in expressions))
        source = (APP / 'scripts/build_dashboards.py').read_text()
        self.assertNotIn('max(vm_data_size_bytes)', source)
        self.assertIn('vm_data_size_bytes{job="victoriametrics"}', source)

    def test_provisioned_folder_and_payload(self):
        docs = render(ROOT / 'Applications/Grafana/overlay/_SAMPLE')
        cms = [d for d in docs if d['kind'] == 'ConfigMap' and d['metadata']['name'].startswith('grafana-monitoring-dashboards-applications-')]
        self.assertEqual(len(cms), 4)
        self.assertEqual({name for cm in cms for name in cm['data']}, set(dashboards()))
        for cm in cms:
            # Client-side apply stores an escaped JSON copy in an annotation.
            self.assertLess(len(json.dumps(cm).encode()), 250 * 1024)
        deployment = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'grafana')
        volumes = deployment['spec']['template']['spec']['volumes']
        sources = next(v for v in volumes if v['name'] == 'monitoring-application-dashboards')['projected']['sources']
        self.assertEqual({v['configMap']['name'] for v in sources}, {cm['metadata']['name'] for cm in cms})
        self.assertIn('folder: Monitoring Applications', (APP / 'components/_dashboards/configs/providers.yaml').read_text())

    def test_missing_limits_and_homeassistant_semantics(self):
        ds = dashboards()
        self.assertEqual(ds['postgresql.json']['templating']['list'][1]['allValue'], '')
        memory = next(p for p in ds['authentik.json']['panels'] if p['title'] == 'Memory limit utilization')
        self.assertIn('unless on', memory['targets'][0]['expr'])
        self.assertEqual(memory['fieldConfig']['defaults']['mappings'][0]['options']['-1']['text'], 'No limit configured')
        ha = next(p for p in ds['home-assistant.json']['panels'] if p['type'] == 'stat' and 'entities' in p['title'])
        self.assertIn('unknown', ha['title'])
        self.assertIn('BOTH', ha['description'])
        self.assertEqual(ds['uptime-kuma.json']['time']['from'], 'now-1h')
        self.assertFalse(any('monitor_status' in t['expr'] for p in ds['uptime-kuma.json']['panels'] for t in p.get('targets', [])))
        monitors = ds['uptime-kuma-monitors.json']
        histories = [p for p in monitors['panels'] if p['type'] == 'status-history']
        self.assertEqual(len(histories), 2)
        for p in histories:
            self.assertEqual(p['options']['perPage'], 20)
            self.assertEqual(p['maxDataPoints'], 120)
            self.assertIn('monitor_type=~"$monitor_type"', p['targets'][0]['expr'])
            self.assertIn('sort_by_label(', p['targets'][0]['expr'])

    def test_root_operations_center(self):
        d = operations_center()
        self.assertEqual((ROOT_OUTPUT / 'operations-center.json').read_text(), json.dumps(d, indent=2) + '\n')
        self.assertEqual(d['uid'], 'mon-operations-center')
        self.assertEqual(d['time'], {'from': 'now-1h', 'to': 'now'})
        self.assertEqual(d['refresh'], '1m')
        self.assertEqual([link['title'] for link in d['links'][:2]], ['Monitoring dashboards', 'Operations reports'])
        self.assertEqual(d['links'][1]['tags'], ['operations'])
        self.assertLessEqual(sum(len(p.get('targets', [])) for p in d['panels']), 26)
        docs = render(ROOT / 'Applications/Grafana/overlay/_SAMPLE')
        cm = next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name'].startswith('grafana-monitoring-dashboards-root-'))
        self.assertEqual(set(cm['data']), {'operations-center.json'})
        provider = (APP / 'components/_dashboards/configs/providers.yaml').read_text()
        root_provider = provider.split('  - name: monitoring-applications')[0]
        self.assertIn("folder: ''", root_provider)
        self.assertNotIn('folderUid:', root_provider)
        tables = [p for p in d['panels'] if p['type'] == 'table']
        self.assertEqual([p['title'] for p in tables], ['Active monitor incident details'])
        self.assertGreaterEqual(sum(p['type'] in ('bargauge', 'status-history', 'timeseries') for p in d['panels']), 9)
        self.assertTrue(all(p['options']['displayMode'] == 'basic' for p in d['panels'] if p['type'] == 'bargauge'))

    def test_homecdn_kpis_precede_visuals(self):
        d = dashboards()['homecdn.json']
        kpis = [next(p for p in d['panels'] if p['title'] == title) for title in ('NGINX reachable', 'Active connections')]
        visuals = [next(p for p in d['panels'] if p['title'] == title) for title in ('Requests', 'Waiting connections', 'Reading connections', 'Writing connections')]
        self.assertEqual({p['gridPos']['w'] for p in kpis}, {12})
        self.assertEqual({p['gridPos']['h'] for p in kpis}, {4})
        self.assertEqual(len({p['gridPos']['y'] for p in kpis}), 1)
        self.assertGreater(min(p['gridPos']['y'] for p in visuals), max(p['gridPos']['y'] for p in kpis))


if __name__ == '__main__':
    unittest.main()
