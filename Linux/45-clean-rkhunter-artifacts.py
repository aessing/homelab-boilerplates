#!/usr/bin/env python3
"""Remove only verified, unused rkhunter artifacts. No backups or restarts."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET


RESOLVER_HASH = 'e50a919ff545909f091971e77c857b43718f68611642bdd09c7492e0e0892fec'
SHM_NAME = re.compile(r'qb-([1-9][0-9]*)-([1-9][0-9]*)-([0-9]+)-[A-Za-z0-9]{6}\Z')
SHM_FILES = frozenset('qb-' + channel + '-usbguard-' + part
                      for channel in ('request', 'response', 'event')
                      for part in ('data', 'header'))
NOFOLLOW = os.O_NOFOLLOW
CACHE_LIMIT = 65536
CACHE_ATTRIBUTES = frozenset(('DATE', 'TIME', 'DEVNO', 'UUID', 'TYPE', 'BLOCK_SIZE'))
DEVICE_PATH = re.compile(r'/dev/[a-zA-Z0-9._/-]+\Z')


class UnsafeArtifact(Exception):
    pass


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def validate_stat(info, mode, directory=False):
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != mode:
        raise UnsafeArtifact('unexpected_type_owner_or_mode')
    if not directory and info.st_nlink != 1:
        raise UnsafeArtifact('unexpected_hardlink')


def pid_exists(pid, proc_root):
    # Presence, including zombies and recycled PIDs, conservatively blocks cleanup.
    return (proc_root / str(pid)).exists()


def referenced(targets, proc_root):
    """Inspect the host PID namespace, including mappings whose FDs are closed."""
    found = False
    try:
        processes = list(proc_root.iterdir())
    except OSError as exc:
        raise UnsafeArtifact('proc_inspection_failed') from exc
    for process in processes:
        if not process.name.isdecimal():
            continue
        try:
            with (process / 'maps').open() as stream:
                for line in stream:
                    fields = line.split(None, 5)
                    if len(fields) < 5:
                        raise UnsafeArtifact('proc_inspection_failed')
                    major, minor = (int(value, 16) for value in fields[3].split(':'))
                    if (os.makedev(major, minor), int(fields[4])) in targets:
                        found = True
            for descriptor in (process / 'fd').iterdir():
                try:
                    info = descriptor.stat()
                except FileNotFoundError:
                    # An FD may close during enumeration. Existing mappings were checked above.
                    continue
                if (info.st_dev, info.st_ino) in targets:
                    found = True
        except FileNotFoundError as exc:
            if not process.exists():
                continue
            raise UnsafeArtifact('proc_inspection_failed') from exc
        except (OSError, ValueError) as exc:
            raise UnsafeArtifact('proc_inspection_failed') from exc
    return found


def shm_snapshot(path):
    directory = path.lstat()
    validate_stat(directory, 0o770, directory=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(directory):
            raise UnsafeArtifact('artifact_changed')
        if set(os.listdir(fd)) != SHM_FILES:
            raise UnsafeArtifact('unexpected_children')
        files = {}
        for name in SHM_FILES:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            validate_stat(info, 0o660)
            files[name] = identity(info)
        return identity(directory), files
    finally:
        os.close(fd)


def shm_eligible(path, proc_root):
    match = SHM_NAME.fullmatch(path.name)
    if not match:
        raise UnsafeArtifact('unexpected_directory_name')
    snapshot = shm_snapshot(path)
    if any(pid_exists(int(pid), proc_root) for pid in match.groups()[:2]):
        raise UnsafeArtifact('named_process_exists')
    targets = {(info[0], info[1]) for info in snapshot[1].values()}
    targets.add(snapshot[0][:2])
    if referenced(targets, proc_root):
        raise UnsafeArtifact('in_use')
    if shm_snapshot(path) != snapshot:
        raise UnsafeArtifact('artifact_changed')
    if any(pid_exists(int(pid), proc_root) for pid in match.groups()[:2]):
        raise UnsafeArtifact('named_process_exists')
    return snapshot


def remove_shm(path, expected, proc_root):
    # Recheck globally immediately before unlink. Never recursively follow or remove children.
    if shm_eligible(path, proc_root) != expected:
        raise UnsafeArtifact('artifact_changed')
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    directory_fd = None
    try:
        directory_fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW, dir_fd=parent_fd)
        if identity(os.fstat(directory_fd)) != expected[0]:
            raise UnsafeArtifact('artifact_changed')
        if set(os.listdir(directory_fd)) != SHM_FILES:
            raise UnsafeArtifact('unexpected_children')
        for name in SHM_FILES:
            if identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != expected[1][name]:
                raise UnsafeArtifact('artifact_changed')
        for name in sorted(SHM_FILES):
            if identity(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)) != expected[1][name]:
                raise UnsafeArtifact('artifact_changed')
            os.unlink(name, dir_fd=directory_fd)
        current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != expected[0][:2]:
            raise UnsafeArtifact('artifact_changed')
        os.rmdir(path.name, dir_fd=parent_fd)
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
        os.close(parent_fd)


def service_active():
    try:
        result = subprocess.run(['systemctl', 'is-active', '--quiet', 'systemd-resolved.service'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolver_snapshot(path, resolv_conf, resolved_active):
    info = path.lstat()
    validate_stat(info, 0o644)
    if info.st_size != 789:
        raise UnsafeArtifact('unexpected_resolver_content')
    fd = os.open(path, os.O_RDONLY | NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(info):
            raise UnsafeArtifact('artifact_changed')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            digest = hashlib.sha256(stream.read(790)).hexdigest()
        if digest != RESOLVER_HASH:
            raise UnsafeArtifact('unexpected_resolver_content')
        if identity(os.fstat(fd)) != identity(info):
            raise UnsafeArtifact('artifact_changed')
    finally:
        os.close(fd)
    link = resolv_conf.lstat()
    if not stat.S_ISLNK(link.st_mode) or link.st_uid != 0 or link.st_gid != 0:
        raise UnsafeArtifact('resolver_not_stub_symlink')
    if os.readlink(resolv_conf) not in ('../run/systemd/resolve/stub-resolv.conf',
                                       '/run/systemd/resolve/stub-resolv.conf'):
        raise UnsafeArtifact('resolver_not_stub_symlink')
    if not resolv_conf.is_file():
        raise UnsafeArtifact('resolver_stub_missing')
    if not resolved_active():
        raise UnsafeArtifact('resolved_not_active')
    return identity(info), identity(link)


def resolver_eligible(path, resolv_conf, proc_root, resolved_active):
    snapshot = resolver_snapshot(path, resolv_conf, resolved_active)
    if referenced({snapshot[0][:2]}, proc_root):
        raise UnsafeArtifact('in_use')
    if resolver_snapshot(path, resolv_conf, resolved_active) != snapshot:
        raise UnsafeArtifact('artifact_changed')
    return snapshot


def remove_resolver(path, expected, resolv_conf, proc_root, resolved_active):
    if resolver_eligible(path, resolv_conf, proc_root, resolved_active) != expected:
        raise UnsafeArtifact('artifact_changed')
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    try:
        if identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)) != expected[0]:
            raise UnsafeArtifact('artifact_changed')
        os.unlink(path.name, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def read_cache_file(path):
    info = path.lstat()
    validate_stat(info, 0o644)
    if not 0 < info.st_size <= CACHE_LIMIT:
        raise UnsafeArtifact('unexpected_cache_size')
    fd = os.open(path, os.O_RDONLY | NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(info):
            raise UnsafeArtifact('artifact_changed')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(CACHE_LIMIT + 1)
        if len(data) != info.st_size or identity(os.fstat(fd)) != identity(info):
            raise UnsafeArtifact('artifact_changed')
        return identity(info), data
    finally:
        os.close(fd)


def cache_entries(data):
    # libblkid stores separate device elements without an enclosing document root.
    if b'<!' in data or b'<?' in data:
        raise UnsafeArtifact('unexpected_cache_xml')
    try:
        document = ET.fromstring(b'<cache>' + data + b'</cache>')
    except ET.ParseError as exc:
        raise UnsafeArtifact('unexpected_cache_xml') from exc
    if (document.text or '').strip() or not 1 <= len(document) <= 128:
        raise UnsafeArtifact('unexpected_cache_xml')
    entries = []
    seen = set()
    for entry in document:
        if (entry.tag != 'device' or len(entry) or (entry.tail or '').strip()
                or not set(entry.attrib) <= CACHE_ATTRIBUTES
                or not {'UUID', 'TYPE'} <= set(entry.attrib)):
            raise UnsafeArtifact('unexpected_cache_xml')
        device = (entry.text or '').strip()
        if (not DEVICE_PATH.fullmatch(device) or any(part in ('', '.', '..') for part in device.split('/')[2:])
                or device in seen):
            raise UnsafeArtifact('unexpected_cache_device')
        if not re.fullmatch(r'[A-Fa-f0-9-]{4,128}', entry.attrib['UUID']):
            raise UnsafeArtifact('unexpected_cache_metadata')
        if not re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}', entry.attrib['TYPE']):
            raise UnsafeArtifact('unexpected_cache_metadata')
        for key in ('TIME', 'DATE'):
            if key in entry.attrib and not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', entry.attrib[key]):
                raise UnsafeArtifact('unexpected_cache_metadata')
        if 'BLOCK_SIZE' in entry.attrib and not re.fullmatch(r'[1-9][0-9]*', entry.attrib['BLOCK_SIZE']):
            raise UnsafeArtifact('unexpected_cache_metadata')
        if 'DEVNO' in entry.attrib and not re.fullmatch(r'0x[0-9a-fA-F]+', entry.attrib['DEVNO']):
            raise UnsafeArtifact('unexpected_cache_metadata')
        seen.add(device)
        entries.append((device, entry.attrib))
    return entries


def cache_config_snapshot(config_path):
    if 'BLKID_FILE' in os.environ or 'BLKID_CONF' in os.environ:
        raise UnsafeArtifact('blkid_environment_override')
    try:
        snapshot, data = read_cache_file(config_path)
    except FileNotFoundError:
        return None
    try:
        lines = data.decode('utf-8').splitlines()
    except UnicodeDecodeError as exc:
        raise UnsafeArtifact('unexpected_blkid_config') from exc
    for line in lines:
        text = line.split('#', 1)[0].strip()
        if not text:
            continue
        match = re.fullmatch(r'(CACHE_FILE|EVALUATE|SEND_UEVENT)\s*=\s*[^\r\n]+', text)
        if not match:
            raise UnsafeArtifact('unexpected_blkid_config')
        if match.group(1) == 'CACHE_FILE':
            raise UnsafeArtifact('blkid_config_override')
    return snapshot


def probe_device(device):
    try:
        before = os.stat(device)
    except FileNotFoundError:
        return None, None
    if not stat.S_ISBLK(before.st_mode):
        raise UnsafeArtifact('cache_device_not_block')
    try:
        result = subprocess.run(['blkid', '-p', '-c', '/dev/null', '-o', 'export', device],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnsafeArtifact('blkid_probe_failed') from exc
    if result.returncode != 0 or len(result.stdout) > CACHE_LIMIT:
        raise UnsafeArtifact('blkid_probe_failed')
    try:
        values = {}
        for line in result.stdout.decode('utf-8').splitlines():
            key, value = line.split('=', 1)
            if key in values:
                raise ValueError('duplicate key')
            values[key] = value
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsafeArtifact('blkid_probe_failed') from exc
    if not values.get('UUID') or not values.get('TYPE'):
        raise UnsafeArtifact('blkid_probe_failed')
    after = os.stat(device)
    if (before.st_dev, before.st_ino, before.st_rdev, before.st_mode) != (
            after.st_dev, after.st_ino, after.st_rdev, after.st_mode):
        raise UnsafeArtifact('cache_device_changed')
    return values, before.st_rdev


def blkid_eligible(path, modern_cache, config_path, proc_root):
    snapshot, data = read_cache_file(path)
    if path == modern_cache:
        raise UnsafeArtifact('cache_paths_overlap')
    modern_snapshot, _ = read_cache_file(modern_cache)
    config_snapshot = cache_config_snapshot(config_path)
    states = []
    for device, attributes in cache_entries(data):
        current, device_number = probe_device(device)
        if current is None:
            states.append((device, 'absent'))
            continue
        states.append((device, 'present'))
        if any(attributes[key] != current[key] for key in ('UUID', 'TYPE')):
            raise UnsafeArtifact('cache_metadata_mismatch')
        if 'DEVNO' in attributes and int(attributes['DEVNO'], 16) != device_number:
            raise UnsafeArtifact('cache_device_number_mismatch')
    if referenced({snapshot[:2]}, proc_root):
        raise UnsafeArtifact('in_use')
    recheck_absent_devices(states)
    if (read_cache_file(path)[0] != snapshot or read_cache_file(modern_cache)[0] != modern_snapshot
            or cache_config_snapshot(config_path) != config_snapshot):
        raise UnsafeArtifact('artifact_changed')
    return snapshot, modern_snapshot, config_snapshot, tuple(states)


def recheck_absent_devices(states):
    for device, state in states:
        if state != 'absent':
            continue
        try:
            os.stat(device)
        except FileNotFoundError:
            continue
        raise UnsafeArtifact('cache_device_changed')


def remove_blkid(path, expected, modern_cache, config_path, proc_root):
    if blkid_eligible(path, modern_cache, config_path, proc_root) != expected:
        raise UnsafeArtifact('artifact_changed')
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW)
    try:
        if identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)) != expected[0]:
            raise UnsafeArtifact('artifact_changed')
        recheck_absent_devices(expected[3])
        os.unlink(path.name, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


def audit(apply=False, shm_root=Path('/dev/shm'), resolver_backup=Path('/etc/.resolv.conf.systemd-resolved.bak'),
          resolv_conf=Path('/etc/resolv.conf'), proc_root=Path('/proc'),
          blkid_paths=(Path('/dev/.blkid.tab'), Path('/dev/.blkid.tab.old')), resolved_active=service_active,
          modern_cache=Path('/run/blkid/blkid.tab'), blkid_config=Path('/etc/blkid.conf')):
    results = []
    try:
        shm_paths = sorted(path for path in shm_root.iterdir() if path.name.startswith('qb-'))
    except OSError:
        shm_paths = []
        results.append({'path': str(shm_root), 'status': 'blocked', 'reason': 'shm_inspection_failed'})
    for path in shm_paths:
        try:
            expected = shm_eligible(path, proc_root)
            if apply:
                remove_shm(path, expected, proc_root)
            results.append({'path': str(path), 'status': 'removed' if apply else 'eligible'})
        except UnsafeArtifact as exc:
            reason = str(exc)
            results.append({'path': str(path), 'status': 'retained' if reason in ('in_use', 'named_process_exists') else 'blocked',
                            'reason': reason})
        except OSError:
            results.append({'path': str(path), 'status': 'blocked', 'reason': 'artifact_io_failed'})
    try:
        expected = resolver_eligible(resolver_backup, resolv_conf, proc_root, resolved_active)
        if apply:
            remove_resolver(resolver_backup, expected, resolv_conf, proc_root, resolved_active)
        results.append({'path': str(resolver_backup), 'status': 'removed' if apply else 'eligible'})
    except FileNotFoundError:
        # Only an absent backup is a successful no-op, missing resolver prerequisites block removal.
        results.append({'path': str(resolver_backup), 'status': 'absent' if not os.path.lexists(resolver_backup) else 'blocked',
                        'reason': 'missing_path'})
    except UnsafeArtifact as exc:
        results.append({'path': str(resolver_backup), 'status': 'retained' if str(exc) == 'in_use' else 'blocked', 'reason': str(exc)})
    except OSError:
        results.append({'path': str(resolver_backup), 'status': 'blocked', 'reason': 'artifact_io_failed'})
    for path in blkid_paths:
        try:
            expected = blkid_eligible(path, modern_cache, blkid_config, proc_root)
            if apply:
                remove_blkid(path, expected, modern_cache, blkid_config, proc_root)
            results.append({'path': str(path), 'status': 'removed' if apply else 'eligible'})
        except FileNotFoundError:
            results.append({'path': str(path), 'status': 'absent' if not os.path.lexists(path) else 'blocked',
                            'reason': 'missing_cache_prerequisite'})
        except UnsafeArtifact as exc:
            results.append({'path': str(path), 'status': 'retained' if str(exc) == 'in_use' else 'blocked',
                            'reason': str(exc)})
        except OSError:
            results.append({'path': str(path), 'status': 'blocked', 'reason': 'artifact_io_failed'})
    return {'mode': 'apply' if apply else 'check', 'artifacts': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print(json.dumps({'status': 'blocked', 'reason': 'root_required'}))
        return 1
    report = audit(apply=args.apply)
    print(json.dumps(report, sort_keys=True))
    return 1 if any(item['status'] == 'blocked' for item in report['artifacts']) else 0


if __name__ == '__main__':
    sys.exit(main())
