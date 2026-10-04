import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / '44-update-host-packages.sh'


class PackagePlanReviewTests(unittest.TestCase):
    def invoke(self, mode='--check', upgrade='', autoremove='', audit='', fail_update=False):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            log = directory / 'calls.jsonl'
            mock = directory / 'mock'
            mock.write_text('#!' + sys.executable + '\n' + '''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'nice': os.execvp(args[2], args[2:])
if name == 'ionice': os.execvp(args[4], args[4:])
with open(os.environ['MOCK_CALLS'], 'a') as f: f.write(json.dumps([name, args]) + '\\n')
if name == 'uname': print('6.8.0-test')
if name == 'dpkg': print(os.environ.get('MOCK_AUDIT', ''), end='')
if name == 'apt-get':
    if 'update' in args and os.environ.get('MOCK_FAIL_UPDATE') == 'yes': sys.exit(100)
    if '-s' in args:
        print(os.environ['MOCK_AUTOREMOVE' if 'autoremove' in args else 'MOCK_UPGRADE'])
''')
            mock.chmod(0o700)
            for name in ('apt-get', 'dpkg', 'dpkg-query', 'uname', 'flock', 'nice', 'ionice'):
                (directory / name).symlink_to(mock)
            source = SCRIPT.read_text()
            # Test only: bypass root and redirect the lock into this isolated directory.
            source = source.replace('if [ "$EUID" -ne 0 ]; then', 'if false; then')
            source = source.replace('/run/lock/homelab-package-maintenance.lock', str(directory / 'lock'))
            tested = directory / 'helper.sh'
            tested.write_text(source)
            env = dict(os.environ, PATH=str(directory) + ':/usr/bin:/bin', MOCK_CALLS=str(log),
                       MOCK_UPGRADE=upgrade, MOCK_AUTOREMOVE=autoremove, MOCK_AUDIT=audit,
                       MOCK_FAIL_UPDATE='yes' if fail_update else 'no')
            result = subprocess.run(['/bin/bash', str(tested), mode], env=env,
                                    text=True, capture_output=True, timeout=10)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, [args for name, args in calls if name == 'apt-get']

    def test_check_only_uses_simulations(self):
        result, calls = self.invoke(autoremove='Remv obsolete-library [1.0]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all('-s' in args for args in calls))
        self.assertEqual(len(calls), 2)

    def test_upgrade_removal_is_rejected(self):
        result, calls = self.invoke(upgrade='Remv example [1.0]')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)

    def test_running_kernel_and_storage_removal_are_rejected(self):
        for package in ('linux-image-6.8.0-test', 'linux-modules-6.8.0-test',
                        'openssh-server:arm64', 'open-iscsi', 'udev', 'systemd', 'nfs-common'):
            with self.subTest(package=package):
                result, _ = self.invoke(autoremove='Remv ' + package + ' [1.0]')
                self.assertNotEqual(result.returncode, 0)

    def test_broken_dpkg_state_prevents_apt(self):
        result, calls = self.invoke(audit='package pending configuration\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_metadata_failure_stops_apply(self):
        result, calls = self.invoke(mode='--apply', fail_update=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn('update', calls[0])

    def test_apply_sequence_is_bounded_and_uses_no_remove_upgrade(self):
        result, calls = self.invoke(mode='--apply', upgrade='Inst example [1.0] (1.1 archive)',
                                    autoremove='Remv obsolete-library [1.0]')
        self.assertEqual(result.returncode, 0, result.stderr)
        sequence = [next(word for word in args if word in ('update', 'upgrade', 'autoremove', 'autoclean', 'check'))
                    for args in calls]
        self.assertEqual(sequence, ['update', 'upgrade', 'upgrade', 'autoremove', 'autoremove', 'autoclean', 'check'])
        self.assertTrue(all('--no-remove' in args for args in calls if 'upgrade' in args))


if __name__ == '__main__':
    unittest.main()
