"""Focused policy and file-replacement checks, without host AppArmor access."""
import hashlib
import os
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / '22-repair-ubuntu-pro-apparmor.sh'
SOURCE = SCRIPT.read_text().split("<<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]
HELPER = types.ModuleType('ubuntu_pro_repair')
exec(compile(SOURCE, str(SCRIPT), 'exec'), HELPER.__dict__)

CURRENT = '''# Site policy keeps its existing custom permissions.
profile ubuntu_pro_esm_cache flags=(attach_disconnected) {
  include <abstractions/base>
  /opt/site/{one,two}/** r,
  @{PROC}/sys/kernel/osrelease r,
  profile unrelated flags=(attach_disconnected) {
    /opt/other/** r,
  }
  #include <local/ubuntu_pro_esm_cache>
}
profile ubuntu_pro_esm_cache_systemd_detect_virt flags=(attach_disconnected) {
    @{PROC}/sys/kernel/osrelease r,
    /opt/site/virt-cache r,
  }
'''
VENDOR = CURRENT.replace(
    '  @{PROC}/sys/kernel/osrelease r,\n',
    '  @{PROC}/sys/kernel/osrelease r,\n  /sys/firmware/devicetree/base/model r,\n', 1
).replace(
    '    @{PROC}/sys/kernel/osrelease r,\n',
    '    @{PROC}/sys/kernel/osrelease r,\n    /sys/firmware/dmi/entries/0-0/raw r,\n', 1
)


class PolicyRepairTests(unittest.TestCase):
    def test_adds_only_official_read_rules_and_preserves_customizations(self):
        candidate, additions = HELPER.repair_profile(CURRENT, VENDOR)
        self.assertEqual(additions, 2)
        self.assertEqual(
            [line for line in candidate.splitlines() if line.strip()],
            [line for line in VENDOR.replace(
                '  /sys/firmware/devicetree/base/model r,',
                '  # LP: #2131292\n  /sys/firmware/devicetree/base/model r,'
            ).replace(
                '    /sys/firmware/dmi/entries/0-0/raw r,',
                '    # LP: #2131292\n    /sys/firmware/dmi/entries/0-0/raw r,'
            ).splitlines() if line.strip()])

    def test_second_run_is_byte_identical(self):
        candidate, _ = HELPER.repair_profile(CURRENT, VENDOR)
        repeated, additions = HELPER.repair_profile(candidate, VENDOR)
        self.assertEqual(repeated, candidate)
        self.assertEqual(additions, 0)

    def test_valid_vendor_format_without_end_newline_is_preserved(self):
        candidate, additions = HELPER.repair_profile(CURRENT.rstrip('\n'), VENDOR.rstrip('\n'))
        self.assertEqual(additions, 2)
        self.assertFalse(candidate.endswith('\n'))
        self.assertEqual(HELPER.repair_profile(candidate, VENDOR.rstrip('\n')), (candidate, 0))

    def test_only_missing_rule_is_added(self):
        current = CURRENT.replace(
            '  @{PROC}/sys/kernel/osrelease r,\n',
            '  @{PROC}/sys/kernel/osrelease r,\n  /sys/firmware/devicetree/base/model r,\n', 1)
        candidate, additions = HELPER.repair_profile(current, VENDOR)
        self.assertEqual(additions, 1)
        self.assertEqual(candidate.count('/sys/firmware/devicetree/base/model r,'), 1)

    def test_rule_in_wrong_subprofile_does_not_satisfy_vendor_requirement(self):
        wrong_vendor = VENDOR.replace(
            '  /sys/firmware/devicetree/base/model r,\n', '').replace(
            '    /opt/other/** r,\n',
            '    /opt/other/** r,\n    /sys/firmware/devicetree/base/model r,\n')
        with self.assertRaisesRegex(ValueError, 'vendor policy lacks'):
            HELPER.repair_profile(CURRENT, wrong_vendor)

    def test_unknown_or_ambiguous_schema_fails_closed(self):
        cases = [
            CURRENT.replace('flags=(attach_disconnected)', 'flags=(complain)', 1),
            CURRENT.replace('  @{PROC}/sys/kernel/osrelease r,\n', '', 1),
            CURRENT.replace('  @{PROC}/sys/kernel/osrelease r,\n',
                            '  @{PROC}/sys/kernel/osrelease r,\n' * 2, 1),
            CURRENT + CURRENT,
            CURRENT[:-2],
            CURRENT.replace('\n', '\r\n'),
        ]
        for current in cases:
            with self.subTest(current=current), self.assertRaises(ValueError):
                HELPER.repair_profile(current, VENDOR)

    def test_duplicate_target_rule_fails_closed(self):
        duplicated = VENDOR.replace('  /sys/firmware/devicetree/base/model r,\n',
                                    '  /sys/firmware/devicetree/base/model r,\n' * 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate target rule'):
            HELPER.repair_profile(duplicated, VENDOR)


class FileReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.policy_dir = self.base / 'apparmor.d'
        self.policy_dir.mkdir(mode=0o700)
        self.profile = self.policy_dir / 'ubuntu_pro_esm_cache'
        self.vendor = self.policy_dir / 'ubuntu_pro_esm_cache.dpkg-dist'
        self.profile.write_text(CURRENT)
        self.profile.chmod(0o640)
        self.vendor.write_text(VENDOR)
        self.vendor.chmod(0o640)
        self.candidate_dir = self.policy_dir / '.candidate'
        self.candidate_dir.mkdir(mode=0o700)
        self.original_lstat = Path.lstat
        self.original_fstat = os.fstat

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def root_metadata(metadata):
        fields = list(metadata)
        fields[4] = 0
        return os.stat_result(fields)

    def root_lstat(self, path, *args, **kwargs):
        return self.root_metadata(self.original_lstat(path, *args, **kwargs))

    def root_fstat(self, fd):
        return self.root_metadata(self.original_fstat(fd))

    def run_helper(self, mode, parser_action=None):
        with (
            patch.object(HELPER, 'PROFILE', self.profile),
            patch.object(HELPER, 'VENDOR', self.vendor),
            patch.object(HELPER, 'installed_md5', return_value=hashlib.md5(VENDOR.encode()).hexdigest()),
            patch.object(HELPER.os, 'geteuid', return_value=0),
            patch.object(Path, 'lstat', lambda path, *args, **kwargs: self.root_lstat(path, *args, **kwargs)),
            patch.object(HELPER.os, 'fstat', self.root_fstat),
            patch.object(HELPER.os, 'fchown'),
            patch.object(HELPER, 'run_parser', side_effect=parser_action) as parser,
        ):
            HELPER.main(mode, self.candidate_dir)
            return parser.call_args_list

    def test_check_keeps_original_bytes_inode_and_permissions(self):
        before = self.profile.stat()
        calls = self.run_helper('--check')
        self.assertEqual(self.profile.read_text(), CURRENT)
        self.assertEqual(self.profile.stat().st_ino, before.st_ino)
        self.assertEqual(self.profile.stat().st_mode, before.st_mode)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('apply', calls[0].kwargs)

    def test_apply_replaces_only_after_validation_and_preserves_permissions(self):
        before = self.profile.stat()

        def inspect(path, apply=False):
            if not apply:
                self.assertEqual(self.profile.read_text(), CURRENT)
            else:
                self.assertEqual(path, self.profile)
                self.assertIn('/sys/firmware/devicetree/base/model r,', path.read_text())

        calls = self.run_helper('--apply', inspect)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1].kwargs, {'apply': True})
        self.assertEqual(self.profile.stat().st_mode, before.st_mode)
        self.assertNotEqual(self.profile.stat().st_ino, before.st_ino)
        self.assertEqual(self.vendor.read_text(), VENDOR)

    def test_parser_failure_keeps_original(self):
        def fail(path, apply=False):
            raise subprocess.CalledProcessError(1, ['apparmor_parser'])

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_helper('--apply', fail)
        self.assertEqual(self.profile.read_text(), CURRENT)

    def test_changed_source_during_validation_is_not_overwritten(self):
        changed = CURRENT + '# Administrator changed policy during validation.\n'

        def change(path, apply=False):
            self.profile.write_text(changed)

        with self.assertRaisesRegex(ValueError, 'changed during validation'):
            self.run_helper('--apply', change)
        self.assertEqual(self.profile.read_text(), changed)

    def test_wrong_package_hash_is_rejected_before_parser_or_replace(self):
        self.vendor.write_text(VENDOR + '# Unverified vendor change.\n')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.run_helper('--apply')
        self.assertEqual(self.profile.read_text(), CURRENT)

    def test_changed_permissions_during_validation_are_not_overwritten(self):
        def change(path, apply=False):
            self.profile.chmod(0o600)

        with self.assertRaisesRegex(ValueError, 'changed during validation'):
            self.run_helper('--apply', change)
        self.assertEqual(self.profile.read_text(), CURRENT)
        self.assertEqual(self.profile.stat().st_mode & 0o777, 0o600)

    def test_reload_failure_reports_on_disk_and_loaded_state_separately(self):
        def fail_reload(path, apply=False):
            if apply:
                raise subprocess.CalledProcessError(1, ['apparmor_parser'])

        with self.assertRaisesRegex(RuntimeError, 'on-disk policy is repaired'):
            self.run_helper('--apply', fail_reload)
        self.assertIn('/sys/firmware/devicetree/base/model r,', self.profile.read_text())

    def test_apply_already_repaired_policy_keeps_file_inode(self):
        repaired, _ = HELPER.repair_profile(CURRENT, VENDOR)
        self.profile.write_text(repaired)
        before = self.profile.stat()
        calls = self.run_helper('--apply')
        self.assertEqual(self.profile.read_text(), repaired)
        self.assertEqual(self.profile.stat().st_ino, before.st_ino)
        self.assertEqual(calls[-1].kwargs, {'apply': True})


class CommandTests(unittest.TestCase):
    def test_help_and_invalid_arguments_need_no_host_access(self):
        help_result = subprocess.run(['bash', str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        bad_result = subprocess.run(['bash', str(SCRIPT), '--apply', '--check'], capture_output=True, text=True)
        self.assertEqual(bad_result.returncode, 2)

    def test_parser_commands_disable_cache_and_limit_parallelism(self):
        with patch.object(HELPER.subprocess, 'run') as run:
            HELPER.run_parser(Path('/candidate'))
            self.assertEqual(run.call_args.args[0],
                             ['/usr/sbin/apparmor_parser', '-Q', '-K', '--jobs=1', '-b', '/etc/apparmor.d', '/candidate'])
            HELPER.run_parser(Path('/policy'), apply=True)
            self.assertEqual(run.call_args.args[0],
                             ['/usr/sbin/apparmor_parser', '-r', '-K', '--jobs=1', '-b', '/etc/apparmor.d', '/policy'])


if __name__ == '__main__':
    unittest.main()
