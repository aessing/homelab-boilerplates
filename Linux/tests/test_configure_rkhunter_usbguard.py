import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / '46-configure-rkhunter-usbguard.py'
HELPER = types.ModuleType('configure_rkhunter_usbguard')
HELPER.__file__ = str(SCRIPT)
exec(compile(SCRIPT.read_text(), str(SCRIPT), 'exec'), HELPER.__dict__)


class USBGuardPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shm = self.root / 'shm'
        self.shm.mkdir()
        original = HELPER.validate_stat
        self.original_validator = original
        def fixture_validator(info, mode, directory=False):
            return original(types.SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_gid=0,
                                                  st_nlink=info.st_nlink), mode, directory)
        self.patch = mock.patch.object(HELPER, 'validate_stat', side_effect=fixture_validator)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def directory(self):
        path = self.shm / 'qb-123-123-9-Ab12Cd'
        path.mkdir()
        path.chmod(0o770)
        for name in HELPER.SHM_FILES:
            child = path / name
            child.write_bytes(b'fixture')
            child.chmod(0o660)
        return path

    def collect(self, path, missing=(), snapshot_changes=False):
        targets = {(child.stat().st_dev, child.stat().st_ino) for child in path.iterdir()
                   if child.name not in missing}
        process = mock.patch.object(HELPER, 'process_snapshot',
                                    side_effect=[(123, '1', 'binary'),
                                                 (123, '2' if snapshot_changes else '1', 'binary')])
        with process, mock.patch.object(HELPER, 'mapped_inodes', return_value=targets):
            return HELPER.collect_policy(shm_root=self.shm, state=lambda: (123, 'active'))

    def test_valid_active_exact_six_paths_without_mutating_artifacts(self):
        path = self.directory()
        before = HELPER.shm_snapshot(path)
        paths, warnings, status = self.collect(path)
        self.assertEqual(len(paths), 6)
        self.assertEqual(warnings, [])
        self.assertEqual(status, 'active')
        self.assertEqual(HELPER.shm_snapshot(path), before)
        self.assertEqual(set(paths), {str(path / name) for name in HELPER.SHM_FILES})

    def test_missing_mapping_is_not_allowed(self):
        path = self.directory()
        paths, warnings, _ = self.collect(path, missing=(next(iter(HELPER.SHM_FILES)),))
        self.assertEqual(paths, [])
        self.assertIn('not_all_files_mapped', warnings[0])

    def test_changed_start_time_fails_closed(self):
        with self.assertRaisesRegex(HELPER.UnsafePolicy, 'daemon_changed'):
            self.collect(self.directory(), snapshot_changes=True)

    def test_unknown_child_wrong_mode_and_symlink_are_not_allowed(self):
        path = self.directory()
        extra = path / 'unknown'
        extra.write_text('x')
        self.assertEqual(self.collect(path)[0], [])
        extra.unlink()
        path.chmod(0o777)
        self.assertEqual(self.collect(path)[0], [])
        path.chmod(0o770)
        child = path / next(iter(HELPER.SHM_FILES))
        child.unlink()
        child.symlink_to(self.root / 'outside')
        with mock.patch.object(HELPER, 'process_snapshot', return_value=(123, '1', 'binary')), \
                mock.patch.object(HELPER, 'mapped_inodes', return_value=set()):
            self.assertEqual(HELPER.collect_policy(shm_root=self.shm,
                             state=lambda: (123, 'active'))[0], [])

    def test_unknown_qb_name_warns_without_trust(self):
        (self.shm / 'qb-unknown').mkdir()
        with mock.patch.object(HELPER, 'process_snapshot', return_value=(123, '1', 'binary')), \
                mock.patch.object(HELPER, 'mapped_inodes', return_value=set()):
            paths, warnings, _ = HELPER.collect_policy(shm_root=self.shm,
                                                      state=lambda: (123, 'active'))
        self.assertEqual(paths, [])
        self.assertIn('unexpected_directory_name', warnings[0])

    def test_absent_service_empty_and_inactive_service_warns(self):
        self.assertEqual(HELPER.collect_policy(shm_root=self.shm,
                        state=lambda: (None, 'absent')), ([], [], None))
        self.assertIn('installed_usbguard_inactive', HELPER.collect_policy(shm_root=self.shm,
                      state=lambda: (None, 'inactive'))[1])
        self.directory()
        self.assertIn('usbguard_not_active', HELPER.collect_policy(shm_root=self.shm,
                      state=lambda: (None, 'absent'))[1][0])

    def test_original_validator_rejects_nonroot_and_hardlink(self):
        original = self.original_validator
        for uid, gid, links in ((1000, 0, 1), (0, 1000, 1), (0, 0, 2)):
            info = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o660, st_uid=uid,
                                         st_gid=gid, st_nlink=links)
            with self.assertRaises(HELPER.UnsafePolicy):
                original(info, 0o660)

    def test_cron_keeps_all_original_content_and_is_idempotent(self):
        original = ('#!/bin/sh\nMAIL=false\n' + HELPER.ANCHOR + 'echo existing\n').encode()
        candidate = HELPER.cron_candidate(original)
        self.assertEqual(candidate.replace(HELPER.HOOK.encode(), b''), original)
        self.assertEqual(HELPER.cron_candidate(candidate), candidate)
        self.assertIn(b'--appendlog > $OUTFILE', candidate)
        self.assertIn(b'--refresh >/dev/null || /usr/bin/logger', candidate)

    def test_cron_unknown_duplicate_or_modified_hook_fails(self):
        for text in ('#!/bin/sh\n', HELPER.ANCHOR * 2,
                     '# homelab-rkhunter-usbguard\n' + HELPER.ANCHOR):
            with self.subTest(text=text), self.assertRaises(HELPER.UnsafePolicy):
                HELPER.cron_candidate(text.encode())

    def test_generated_policy_rejects_globs_or_injected_lines(self):
        path = '/dev/shm/qb-123-123-9-Ab12Cd/qb-request-usbguard-data'
        self.assertEqual(HELPER.config_data([path]), (HELPER.HEADER + 'ALLOWDEVFILE=' + path + '\n').encode())
        for invalid in ('/dev/shm/qb-*/*', path + '\nDISABLE_TESTS=all', '/tmp/x'):
            with self.assertRaises(HELPER.UnsafePolicy):
                HELPER.config_data([invalid])

    def test_foreign_managed_config_is_never_overwritten(self):
        config = self.root / 'foreign.conf'
        config.write_text('ALLOWDEVFILE=/dev/shm/*\n')
        with mock.patch.object(HELPER, 'read_file', return_value=(config.read_bytes(), config.stat())):
            with self.assertRaisesRegex(HELPER.UnsafePolicy, 'foreign_or_invalid'):
                HELPER.managed_config(config)
        self.assertEqual(config.read_text(), 'ALLOWDEVFILE=/dev/shm/*\n')

    def test_refresh_failure_clears_own_exceptions_and_retains_scan_failure_signal(self):
        info = types.SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                st_uid=0, st_gid=0, st_size=10, st_mtime_ns=1, st_ctime_ns=1, st_nlink=1)
        with mock.patch.object(HELPER, 'ensure_directory'), \
                mock.patch.object(HELPER, 'managed_config', return_value=info), \
                mock.patch.object(HELPER, 'collect_policy', side_effect=HELPER.UnsafePolicy('changed')), \
                mock.patch.object(HELPER, 'atomic_write') as write, \
                mock.patch.object(HELPER, 'config_check'), mock.patch.object(HELPER, 'warn'):
            report = HELPER.refresh()
        self.assertEqual(write.call_args.args[1], HELPER.HEADER.encode())
        self.assertTrue(report['verification_failed'])
        self.assertEqual(report['allowed_paths'], 0)

    def test_config_check_failure_clears_own_policy(self):
        info = types.SimpleNamespace(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600,
                st_uid=0, st_gid=0, st_size=10, st_mtime_ns=1, st_ctime_ns=1, st_nlink=1)
        path = '/dev/shm/qb-123-123-9-Ab12Cd/qb-request-usbguard-data'
        with mock.patch.object(HELPER, 'ensure_directory'), \
                mock.patch.object(HELPER, 'managed_config', return_value=info), \
                mock.patch.object(HELPER, 'collect_policy', return_value=([path], [], 'active')), \
                mock.patch.object(HELPER, 'atomic_write') as write, \
                mock.patch.object(HELPER, 'config_check', side_effect=HELPER.UnsafePolicy('invalid')):
            with self.assertRaises(HELPER.UnsafePolicy):
                HELPER.refresh()
        self.assertEqual(write.call_count, 2)
        self.assertEqual(write.call_args.args[1], HELPER.HEADER.encode())

    def test_check_is_read_only(self):
        source = self.root / 'source.py'
        source.write_bytes(SCRIPT.read_bytes())
        info = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o755)
        def read(path, optional=False):
            return (HELPER.ANCHOR.encode(), info) if path == HELPER.CRON else (None, None)
        with mock.patch.object(HELPER, 'read_file', side_effect=read), \
                mock.patch.object(HELPER, 'managed_config'), \
                mock.patch.object(HELPER, 'collect_policy', return_value=([], [], None)), \
                mock.patch.object(HELPER, 'atomic_write') as write, \
                mock.patch.object(HELPER, 'ensure_directory') as mkdir:
            report = HELPER.install(source=source)
        write.assert_not_called()
        mkdir.assert_not_called()
        self.assertTrue(report['cron_change'])

    def test_package_checksum_match_and_mismatch(self):
        binary = self.root / 'usbguard-daemon'
        binary.write_bytes(b'verified package binary')
        digest = hashlib.md5(binary.read_bytes(), usedforsecurity=False).hexdigest()
        manifest = (digest + '  ' + str(binary).lstrip('/') + '\n').encode()
        with mock.patch.object(HELPER, 'read_file', return_value=(manifest, None)):
            HELPER.verify_package_binary(binary, binary.stat())
            binary.write_bytes(b'changed')
            with self.assertRaisesRegex(HELPER.UnsafePolicy, 'checksum_mismatch'):
                HELPER.verify_package_binary(binary, binary.stat())

    def test_mapping_disappearing_on_recheck_fails_closed(self):
        path = self.directory()
        targets = {(child.stat().st_dev, child.stat().st_ino) for child in path.iterdir()}
        with mock.patch.object(HELPER, 'process_snapshot', return_value=(123, '1', 'binary')), \
                mock.patch.object(HELPER, 'mapped_inodes', side_effect=[targets, set()]):
            with self.assertRaisesRegex(HELPER.UnsafePolicy, 'shm_changed'):
                HELPER.collect_policy(shm_root=self.shm, state=lambda: (123, 'active'))

    def test_config_validation_keeps_logging_untouched_and_checks_disabled_options(self):
        with mock.patch.object(HELPER.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)) as run:
            HELPER.config_check()
        args = run.call_args.args[0]
        self.assertIn('--nolog', args)
        self.assertIn('--nocf', args)
        self.assertEqual(args[args.index('--disable') + 1], 'none')

    def test_cli_rejects_nonroot_before_inspection(self):
        driver = ('import os,runpy,sys; os.geteuid=lambda:1000; '
                  'sys.argv=[sys.argv[1],"--check"]; runpy.run_path(sys.argv[0],run_name="__main__")')
        result = subprocess.run(['python3', '-c', driver, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Run as root', result.stderr)

    def test_help_cli_runs(self):
        result = subprocess.run(['python3', str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--refresh', result.stdout)

    def test_apply_reports_nested_policy_verification_failure(self):
        with mock.patch.object(HELPER.os, 'geteuid', return_value=0), \
                mock.patch.object(HELPER.sys, 'argv', ['helper', '--apply']), \
                mock.patch.object(HELPER, 'install', return_value={'policy': {'verification_failed': True}}):
            self.assertEqual(HELPER.main(), 1)


if __name__ == '__main__':
    unittest.main()
