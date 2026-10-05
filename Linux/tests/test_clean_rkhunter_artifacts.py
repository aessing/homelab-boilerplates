import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / '45-clean-rkhunter-artifacts.py'
HELPER = types.ModuleType('clean_rkhunter_artifacts')
exec(compile(SCRIPT.read_text(), str(SCRIPT), 'exec'), HELPER.__dict__)


class ArtifactCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shm = self.root / 'shm'
        self.proc = self.root / 'proc'
        self.etc = self.root / 'etc'
        for path in (self.shm, self.proc, self.etc):
            path.mkdir()
        self.backup = self.etc / '.resolv.conf.systemd-resolved.bak'
        self.resolv = self.etc / 'resolv.conf'
        self.stub = self.root / 'run/systemd/resolve/stub-resolv.conf'
        self.stub.parent.mkdir(parents=True)
        self.stub.write_text('nameserver 127.0.0.53\n')
        self.resolv.symlink_to('../run/systemd/resolve/stub-resolv.conf')
        # Fixtures are owned by the non-root developer on macOS. Root ownership itself
        # is tested separately against the unmodified production validator.
        original = HELPER.validate_stat
        def fixture_validator(info, mode, directory=False):
            owner = types.SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_gid=0, st_nlink=info.st_nlink)
            return original(owner, mode, directory)
        self.owner_patch = mock.patch.object(HELPER, 'validate_stat', side_effect=fixture_validator)
        self.owner_patch.start()
        self.addCleanup(self.owner_patch.stop)

    def directory(self):
        path = self.shm / 'qb-900001-900002-14-Ab12Cd'
        path.mkdir(mode=0o770)
        path.chmod(0o770)
        for name in HELPER.SHM_FILES:
            child = path / name
            child.write_bytes(b'fixture')
            child.chmod(0o660)
        return path

    def resolver(self):
        data = b'#' + b'x' * 787 + b'\n'
        self.backup.write_bytes(data)
        self.backup.chmod(0o644)
        digest_patch = mock.patch.object(HELPER, 'RESOLVER_HASH', hashlib.sha256(data).hexdigest())
        digest_patch.start()
        self.addCleanup(digest_patch.stop)

    def process(self, pid=321, maps=''):
        process = self.proc / str(pid)
        process.mkdir()
        (process / 'maps').write_text(maps)
        (process / 'fd').mkdir()
        return process

    def map_line(self, path):
        info = path.stat()
        return ('1000-2000 rw-s 00000000 %x:%x %d %s\n' %
                (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino, path))

    def audit(self, apply=False, active=True):
        with mock.patch.object(HELPER.os, 'readlink', wraps=os.readlink) as readlink:
            # Snapshot UID checking for this symlink is independent of file validation.
            actual_lstat = Path.lstat
            def fixture_lstat(path):
                info = actual_lstat(path)
                if path == self.resolv:
                    fields = {name: getattr(info, name) for name in (
                        'st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink')}
                    return types.SimpleNamespace(st_uid=0, st_gid=0, **fields)
                return info
            with mock.patch.object(Path, 'lstat', fixture_lstat):
                return HELPER.audit(apply=apply, shm_root=self.shm, resolver_backup=self.backup,
                                    resolv_conf=self.resolv, proc_root=self.proc, blkid_paths=(),
                                    resolved_active=lambda: active)

    def status(self, report, path):
        return next(item for item in report['artifacts'] if item['path'] == str(path))

    def test_check_is_read_only_and_apply_is_idempotent(self):
        path = self.directory()
        self.resolver()
        before = {item.name: item.read_bytes() for item in path.iterdir()}
        report = self.audit()
        self.assertEqual(self.status(report, path)['status'], 'eligible')
        self.assertEqual(self.status(report, self.backup)['status'], 'eligible')
        self.assertEqual(before, {item.name: item.read_bytes() for item in path.iterdir()})
        self.assertTrue(self.backup.exists())
        report = self.audit(apply=True)
        self.assertEqual(self.status(report, path)['status'], 'removed')
        self.assertEqual(self.status(report, self.backup)['status'], 'removed')
        self.assertFalse(path.exists())
        self.assertTrue(self.resolv.is_symlink())
        self.assertEqual(self.status(self.audit(apply=True), self.backup)['status'], 'absent')

    def test_mapping_blocks_cleanup_even_without_open_fd(self):
        path = self.directory()
        child = path / next(iter(HELPER.SHM_FILES))
        self.process(maps=self.map_line(child))
        report = self.audit(apply=True)
        self.assertEqual(self.status(report, path)['reason'], 'in_use')
        self.assertEqual(set(item.name for item in path.iterdir()), HELPER.SHM_FILES)

    def test_fd_inode_blocks_cleanup_via_other_pathname(self):
        path = self.directory()
        child = path / next(iter(HELPER.SHM_FILES))
        process = self.process()
        (process / 'fd/3').symlink_to(child)
        self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'in_use')

    def test_both_named_pids_are_checked(self):
        for pid in (900001, 900002):
            with self.subTest(pid=pid):
                path = self.directory()
                process = self.process(pid)
                self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'named_process_exists')
                for child in process.iterdir():
                    child.rmdir() if child.is_dir() else child.unlink()
                process.rmdir()
                for child in path.iterdir():
                    child.unlink()
                path.rmdir()

    def test_proc_read_error_fails_closed(self):
        path = self.directory()
        (self.proc / '321').mkdir()
        self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'proc_inspection_failed')
        self.assertTrue(path.exists())

    def test_permission_error_fails_closed(self):
        path = self.directory()
        self.process()
        with mock.patch.object(Path, 'open', side_effect=PermissionError):
            self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'proc_inspection_failed')
        self.assertTrue(path.exists())

    def test_unexpected_children_and_symlinks_are_retained(self):
        path = self.directory()
        extra = path / 'unexpected'
        extra.write_bytes(b'x')
        self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'unexpected_children')
        extra.unlink()
        child = path / next(iter(HELPER.SHM_FILES))
        child.unlink()
        child.symlink_to(self.stub)
        self.assertEqual(self.status(self.audit(apply=True), path)['reason'], 'unexpected_type_owner_or_mode')
        self.assertTrue(self.stub.exists())

    def test_directory_symlink_is_not_followed(self):
        target = self.directory()
        alias = self.shm / 'qb-800001-800002-14-Ab12Cd'
        alias.symlink_to(target, target_is_directory=True)
        report = self.audit()
        self.assertEqual(self.status(report, alias)['status'], 'blocked')
        self.assertEqual(set(item.name for item in target.iterdir()), HELPER.SHM_FILES)

    def test_changed_inode_between_audit_and_apply_blocks_all_unlinks(self):
        path = self.directory()
        expected = HELPER.shm_eligible(path, self.proc)
        child = path / next(iter(HELPER.SHM_FILES))
        child.unlink()
        child.write_bytes(b'replacement')
        child.chmod(0o660)
        with self.assertRaises(HELPER.UnsafeArtifact):
            HELPER.remove_shm(path, expected, self.proc)
        self.assertEqual(len(list(path.iterdir())), 6)

    def test_changed_resolver_content_wrong_link_or_inactive_service_blocks(self):
        self.resolver()
        self.backup.write_bytes(b'x' * 789)
        self.assertEqual(self.status(self.audit(apply=True), self.backup)['reason'], 'unexpected_resolver_content')
        self.resolver()
        self.assertEqual(self.status(self.audit(apply=True, active=False), self.backup)['reason'], 'resolved_not_active')
        self.resolv.unlink()
        self.resolv.symlink_to(self.stub)
        self.assertEqual(self.status(self.audit(apply=True), self.backup)['reason'], 'resolver_not_stub_symlink')
        self.assertTrue(self.backup.exists())

    def test_used_resolver_backup_is_retained(self):
        self.resolver()
        self.process(maps=self.map_line(self.backup))
        self.assertEqual(self.status(self.audit(apply=True), self.backup)['reason'], 'in_use')

    def test_blkid_missing_modern_cache_blocks_cleanup(self):
        cache = self.root / '.blkid.tab'
        cache.write_bytes(b'cache')
        report = HELPER.audit(apply=True, shm_root=self.shm, resolver_backup=self.backup,
                              proc_root=self.proc, blkid_paths=(cache,))
        self.assertEqual(self.status(report, cache)['status'], 'blocked')
        self.assertEqual(cache.read_bytes(), b'cache')

    def test_real_cli_requires_mode_and_root(self):
        result = subprocess.run(['python3', str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        with mock.patch.object(HELPER.os, 'geteuid', return_value=501), mock.patch('builtins.print') as output:
            self.assertEqual(HELPER.main(['--check']), 1)
            self.assertIn('root_required', output.call_args.args[0])


class OwnershipTests(unittest.TestCase):
    def test_production_validator_rejects_nonroot_wrong_gid_modes_and_hardlinks(self):
        for uid, gid, mode, links in ((501, 0, 0o660, 1), (0, 501, 0o660, 1),
                                      (0, 0, 0o666, 1), (0, 0, 0o660, 2)):
            info = types.SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=stat.S_IFREG | mode, st_nlink=links)
            with self.subTest(uid=uid, gid=gid, mode=mode, links=links), self.assertRaises(HELPER.UnsafeArtifact):
                HELPER.validate_stat(info, 0o660)
        info = types.SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFREG | 0o660, st_nlink=1)
        HELPER.validate_stat(info, 0o660)

    def test_manufacturer_hash_is_fixed(self):
        self.assertEqual(HELPER.RESOLVER_HASH,
                         'e50a919ff545909f091971e77c857b43718f68611642bdd09c7492e0e0892fec')


class BlkidCleanupTests(unittest.TestCase):
    setUp = ArtifactCleanupTests.setUp
    process = ArtifactCleanupTests.process
    map_line = ArtifactCleanupTests.map_line
    status = ArtifactCleanupTests.status

    def cache_fixture(self):
        self.cache = self.root / '.blkid.tab'
        self.modern = self.root / 'modern-cache'
        self.config = self.root / 'blkid.conf'
        self.xml = (b'<device BLOCK_SIZE="4096" DEVNO="0xb302" TIME="1234567890.123456" '
                    b'UUID="12345678-1234-abcd-1234-123456789abc" TYPE="ext4">/dev/mmcblk0p2</device>\n')
        for path in (self.cache, self.modern):
            path.write_bytes(self.xml)
            path.chmod(0o644)
        self.current = {'UUID': '12345678-1234-abcd-1234-123456789abc', 'TYPE': 'ext4'}

    def cache_audit(self, apply=False):
        with mock.patch.dict(HELPER.os.environ, {}, clear=True), \
                mock.patch.object(HELPER, 'probe_device', return_value=(self.current, 0xb302)):
            return HELPER.audit(apply=apply, shm_root=self.shm, resolver_backup=self.backup,
                                proc_root=self.proc, blkid_paths=(self.cache,), modern_cache=self.modern,
                                blkid_config=self.config)

    def test_matching_cache_removal_keeps_modern_cache_and_is_idempotent(self):
        self.cache_fixture()
        before = self.modern.read_bytes()
        self.assertEqual(self.status(self.cache_audit(), self.cache)['status'], 'eligible')
        self.assertTrue(self.cache.exists())
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['status'], 'removed')
        self.assertEqual(self.modern.read_bytes(), before)
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['status'], 'absent')

    def test_uuid_type_and_device_number_mismatch_block(self):
        for key, value, reason in (('UUID', 'abcdef12', 'cache_metadata_mismatch'),
                                  ('TYPE', 'xfs', 'cache_metadata_mismatch'),
                                  ('DEVNO', '0xb301', 'cache_device_number_mismatch')):
            with self.subTest(key=key):
                self.cache_fixture()
                self.cache.write_bytes(self.xml.replace((key + '="' +
                    ('0xb302' if key == 'DEVNO' else self.current[key]) + '"').encode(),
                    (key + '="' + value + '"').encode()))
                self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['reason'], reason)
                self.assertTrue(self.cache.exists())

    def test_active_mapping_retains_cache(self):
        self.cache_fixture()
        self.process(maps=self.map_line(self.cache))
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['reason'], 'in_use')
        self.assertTrue(self.cache.exists())

    def test_environment_and_config_overrides_block(self):
        self.cache_fixture()
        for key in ('BLKID_FILE', 'BLKID_CONF'):
            with self.subTest(key=key), mock.patch.dict(HELPER.os.environ, {key: ''}, clear=True):
                with self.assertRaisesRegex(HELPER.UnsafeArtifact, 'blkid_environment_override'):
                    HELPER.blkid_eligible(self.cache, self.modern, self.config, self.proc)
        self.config.write_text('CACHE_FILE=/dev/.blkid.tab\n')
        self.config.chmod(0o644)
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['reason'], 'blkid_config_override')
        self.assertTrue(self.cache.exists())

    def test_missing_or_symlink_modern_cache_blocks(self):
        self.cache_fixture()
        self.modern.unlink()
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['status'], 'blocked')
        self.modern.symlink_to(self.cache)
        self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['reason'],
                         'unexpected_type_owner_or_mode')
        self.assertTrue(self.cache.exists())

    def test_unknown_xml_missing_identifiers_entities_and_traversal_block(self):
        self.cache_fixture()
        cases = (b'<unknown />', b'<device TYPE="ext4">/dev/mmcblk0p2</device>',
                 self.xml.replace(b'TYPE="ext4"', b'TYPE="ext4" LABEL="test"'),
                 b'<!DOCTYPE x [<!ENTITY e "test">]>' + self.xml,
                 self.xml.replace(b'/dev/mmcblk0p2', b'/dev/../etc/passwd'),
                 self.xml.replace(b'/dev/mmcblk0p2', b'/dev//mmcblk0p2'),
                 self.xml + self.xml)
        for data in cases:
            with self.subTest(data=data):
                self.cache.write_bytes(data)
                self.assertEqual(self.status(self.cache_audit(apply=True), self.cache)['status'], 'blocked')
                self.assertTrue(self.cache.exists())

    def test_changed_legacy_inode_before_unlink_blocks(self):
        self.cache_fixture()
        with mock.patch.dict(HELPER.os.environ, {}, clear=True), \
                mock.patch.object(HELPER, 'probe_device', return_value=(self.current, 0xb302)):
            expected = HELPER.blkid_eligible(self.cache, self.modern, self.config, self.proc)
            self.cache.unlink()
            self.cache.write_bytes(self.xml)
            self.cache.chmod(0o644)
            with self.assertRaisesRegex(HELPER.UnsafeArtifact, 'artifact_changed'):
                HELPER.remove_blkid(self.cache, expected, self.modern, self.config, self.proc)
        self.assertTrue(self.cache.exists())

    def test_changed_modern_cache_before_unlink_blocks(self):
        self.cache_fixture()
        with mock.patch.dict(HELPER.os.environ, {}, clear=True), \
                mock.patch.object(HELPER, 'probe_device', return_value=(self.current, 0xb302)):
            expected = HELPER.blkid_eligible(self.cache, self.modern, self.config, self.proc)
            self.modern.write_bytes(self.xml + b'\n')
            with self.assertRaisesRegex(HELPER.UnsafeArtifact, 'artifact_changed'):
                HELPER.remove_blkid(self.cache, expected, self.modern, self.config, self.proc)
        self.assertTrue(self.cache.exists())

    def test_absent_device_cleanup_is_rechecked_and_never_probes(self):
        self.cache_fixture()
        actual_stat = HELPER.os.stat
        checked = []
        def absent_device(path, *args, **kwargs):
            if str(path) == '/dev/mmcblk0p2':
                checked.append(path)
                raise FileNotFoundError
            return actual_stat(path, *args, **kwargs)
        with mock.patch.dict(HELPER.os.environ, {}, clear=True), \
                mock.patch.object(HELPER.os, 'stat', side_effect=absent_device), \
                mock.patch.object(HELPER.subprocess, 'run') as probe:
            report = HELPER.audit(apply=True, shm_root=self.shm, resolver_backup=self.backup,
                                  proc_root=self.proc, blkid_paths=(self.cache,), modern_cache=self.modern,
                                  blkid_config=self.config)
        self.assertEqual(self.status(report, self.cache)['status'], 'removed')
        self.assertGreaterEqual(len(checked), 5)
        probe.assert_not_called()
        self.assertTrue(self.modern.exists())

    def test_absent_device_reappearing_before_apply_blocks(self):
        self.cache_fixture()
        actual_stat = HELPER.os.stat
        present = False
        def device_stat(path, *args, **kwargs):
            if str(path) == '/dev/mmcblk0p2':
                if present:
                    return types.SimpleNamespace(st_mode=stat.S_IFBLK)
                raise FileNotFoundError
            return actual_stat(path, *args, **kwargs)
        with mock.patch.dict(HELPER.os.environ, {}, clear=True), \
                mock.patch.object(HELPER.os, 'stat', side_effect=device_stat), \
                mock.patch.object(HELPER, 'probe_device', return_value=(None, None)):
            expected = HELPER.blkid_eligible(self.cache, self.modern, self.config, self.proc)
            present = True
            with self.assertRaisesRegex(HELPER.UnsafeArtifact, 'cache_device_changed'):
                HELPER.remove_blkid(self.cache, expected, self.modern, self.config, self.proc)
        self.assertTrue(self.cache.exists())

    def test_absent_device_permission_error_is_not_treated_as_absence(self):
        self.cache_fixture()
        with mock.patch.object(HELPER.os, 'stat', side_effect=PermissionError), \
                mock.patch.object(HELPER.subprocess, 'run') as probe, self.assertRaises(PermissionError):
            HELPER.probe_device('/dev/mmcblk0p2')
        probe.assert_not_called()

    def test_actual_probe_command_is_read_only_and_sanitizes_environment(self):
        block = types.SimpleNamespace(st_dev=1, st_ino=2, st_rdev=0xb302, st_mode=stat.S_IFBLK | 0o660)
        result = types.SimpleNamespace(returncode=0, stdout=b'UUID=12345678\nTYPE=ext4\n')
        with mock.patch.object(HELPER.os, 'stat', return_value=block), \
                mock.patch.object(HELPER.subprocess, 'run', return_value=result) as command:
            values, number = HELPER.probe_device('/dev/mmcblk0p2')
        self.assertEqual(values, {'UUID': '12345678', 'TYPE': 'ext4'})
        self.assertEqual(number, 0xb302)
        self.assertEqual(command.call_args.args[0],
                         ['blkid', '-p', '-c', '/dev/null', '-o', 'export', '/dev/mmcblk0p2'])
        self.assertEqual(command.call_args.kwargs['env'],
                         {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        self.assertNotIn('shell', command.call_args.kwargs)

    def test_probe_rejects_regular_device_missing_metadata_and_nonzero_exit(self):
        regular = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o644)
        with mock.patch.object(HELPER.os, 'stat', return_value=regular), self.assertRaises(HELPER.UnsafeArtifact):
            HELPER.probe_device('/dev/mmcblk0p2')
        block = types.SimpleNamespace(st_dev=1, st_ino=2, st_rdev=1, st_mode=stat.S_IFBLK | 0o660)
        for code, output in ((2, b''), (0, b'TYPE=ext4\n'), (0, b'UUID=1234\nTYPE=ext4\nTYPE=xfs\n')):
            with self.subTest(code=code, output=output), \
                    mock.patch.object(HELPER.os, 'stat', return_value=block), \
                    mock.patch.object(HELPER.subprocess, 'run',
                                      return_value=types.SimpleNamespace(returncode=code, stdout=output)), \
                    self.assertRaises(HELPER.UnsafeArtifact):
                HELPER.probe_device('/dev/mmcblk0p2')


if __name__ == '__main__':
    unittest.main()
