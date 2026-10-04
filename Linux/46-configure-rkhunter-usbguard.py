#!/usr/bin/env python3
"""Allow only verified active USBGuard SHM paths before the existing daily scan."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


INSTALLED = Path('/usr/local/libexec/homelab-rkhunter-usbguard.py')
CRON = Path('/etc/cron.daily/rkhunter')
CONFIG = Path('/etc/rkhunter.d/99-homelab-usbguard-shm.conf')
EXECUTABLE = Path('/usr/sbin/usbguard-daemon')
PACKAGE_SUMS = Path('/var/lib/dpkg/info/usbguard.md5sums')
HEADER = '# Managed by homelab-rkhunter-usbguard. Exact verified active paths only.\n'
ANCHOR = '        /usr/bin/nice -n $NICE $RKHUNTER --cronjob --report-warnings-only --appendlog > $OUTFILE\n'
HOOK = ('        # homelab: refresh verified USBGuard SHM exceptions before this scan\n'
        '        /usr/bin/python3 -I /usr/local/libexec/homelab-rkhunter-usbguard.py --refresh >/dev/null || '
        '/usr/bin/logger -p authpriv.warning -t homelab-rkhunter "USBGuard policy refresh failed"\n')
SHM_NAME = re.compile(r'qb-([1-9][0-9]*)-([1-9][0-9]*)-([0-9]+)-[A-Za-z0-9]{6}\Z')
SHM_FILES = frozenset('qb-' + channel + '-usbguard-' + part
                      for channel in ('request', 'response', 'event')
                      for part in ('data', 'header'))
LINE = re.compile(r'ALLOWDEVFILE=/dev/shm/qb-[1-9][0-9]*-[1-9][0-9]*-[0-9]+-[A-Za-z0-9]{6}/'
                  r'qb-(?:request|response|event)-usbguard-(?:data|header)\Z')


class UnsafePolicy(Exception):
    pass


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def validate_stat(info, mode, directory=False):
    expected_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (not expected_type or info.st_uid != 0 or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != mode
            or (not directory and info.st_nlink != 1)):
        raise UnsafePolicy('unexpected_type_owner_mode_or_links')


def secure_parent(path):
    for directory in (path.parent, *path.parent.parents):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise UnsafePolicy('unsafe_parent: ' + str(directory))


def read_file(path, optional=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if optional:
            return None, None
        raise
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                or info.st_mode & 0o022 or info.st_nlink != 1):
            raise UnsafePolicy('unsafe_file: ' + str(path))
        data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise UnsafePolicy('oversized_file')
        if identity(os.fstat(stream.fileno())) != identity(info):
            raise UnsafePolicy('file_changed')
    return data, info


def atomic_write(path, data, expected, mode):
    secure_parent(path)
    current, current_info = read_file(path, optional=True)
    if (identity(current_info) if current_info is not None else None) != expected:
        raise UnsafePolicy('file_changed: ' + str(path))
    if current == data and current_info is not None and stat.S_IMODE(current_info.st_mode) == mode:
        return False
    fd, temporary = tempfile.mkstemp(prefix='.homelab-policy-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchown(stream.fileno(), 0, 0)
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _, now = read_file(path, optional=True)
        if (identity(now) if now is not None else None) != expected:
            raise UnsafePolicy('file_changed: ' + str(path))
        secure_parent(path)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    return True


def cron_candidate(data):
    text = data.decode('utf-8')
    if '\r' in text or text.count(ANCHOR) != 1:
        raise UnsafePolicy('unknown_or_ambiguous_daily_cron')
    if HOOK + ANCHOR in text:
        if text.count('homelab-rkhunter-usbguard.py') != 1:
            raise UnsafePolicy('ambiguous_managed_hook')
        return data
    if 'homelab-rkhunter-usbguard' in text or 'homelab: refresh verified USBGuard' in text:
        raise UnsafePolicy('unknown_managed_hook')
    return text.replace(ANCHOR, HOOK + ANCHOR, 1).encode('utf-8')


def managed_config(path):
    data, info = read_file(path, optional=True)
    if data is not None:
        text = data.decode('utf-8')
        if not text.startswith(HEADER) or any(not LINE.fullmatch(line)
                                             for line in text[len(HEADER):].splitlines()):
            raise UnsafePolicy('foreign_or_invalid_managed_config')
    return info


def ensure_directory(path):
    if not os.path.lexists(path):
        secure_parent(path)
        path.mkdir(mode=0o755)
        os.chown(path, 0, 0)
        path.chmod(0o755)
    validate_stat(path.lstat(), 0o755, directory=True)
    secure_parent(path / 'placeholder')


def service_state():
    result = subprocess.run(['/usr/bin/systemctl', 'show', 'usbguard.service',
                             '--property=LoadState,ActiveState,MainPID'],
                            capture_output=True, text=True, timeout=10, check=True)
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if values.get('LoadState') == 'not-found':
        return None, 'absent'
    if values.get('LoadState') != 'loaded':
        raise UnsafePolicy('unknown_service_state')
    if values.get('ActiveState') != 'active':
        return None, 'inactive'
    pid = values.get('MainPID', '')
    if not re.fullmatch(r'[1-9][0-9]*', pid):
        raise UnsafePolicy('invalid_main_pid')
    return int(pid), 'active'


def verify_package_binary(executable, expected_info, manifest=PACKAGE_SUMS):
    data, _ = read_file(manifest)
    entries = []
    for line in data.decode('ascii').splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == str(executable).lstrip('/'):
            entries.append(fields[0])
    if len(entries) != 1 or not re.fullmatch(r'[0-9a-f]{32}', entries[0]):
        raise UnsafePolicy('missing_or_ambiguous_package_checksum')
    fd = os.open(executable, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if identity(os.fstat(stream.fileno())) != identity(expected_info):
            raise UnsafePolicy('daemon_executable_changed')
        digest = hashlib.md5(usedforsecurity=False)
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
        if identity(os.fstat(stream.fileno())) != identity(expected_info):
            raise UnsafePolicy('daemon_executable_changed')
    if digest.hexdigest() != entries[0]:
        raise UnsafePolicy('daemon_package_checksum_mismatch')


def process_snapshot(pid, proc_root=Path('/proc'), executable=EXECUTABLE):
    process = proc_root / str(pid)
    status = (process / 'status').read_text()
    match = re.search(r'^Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s*$', status, re.M)
    if match is None or any(int(value) != 0 for value in match.groups()):
        raise UnsafePolicy('daemon_not_root')
    if os.readlink(process / 'exe') != str(executable):
        raise UnsafePolicy('unexpected_daemon_executable')
    binary = executable.lstat()
    if (not stat.S_ISREG(binary.st_mode) or binary.st_uid != 0 or binary.st_gid != 0
            or binary.st_mode & 0o022):
        raise UnsafePolicy('unsafe_daemon_executable')
    verify_package_binary(executable, binary)
    running = (process / 'exe').stat()
    if (running.st_dev, running.st_ino) != (binary.st_dev, binary.st_ino):
        raise UnsafePolicy('daemon_executable_changed')
    raw = (process / 'stat').read_text()
    # A process name may contain spaces or ')' characters. Field 22 follows the last ')'.
    fields = raw[raw.rfind(')') + 2:].split()
    if len(fields) < 20 or not fields[19].isdecimal():
        raise UnsafePolicy('invalid_process_stat')
    return pid, fields[19], identity(binary)


def mapped_inodes(pid, proc_root=Path('/proc')):
    targets = set()
    for line in (proc_root / str(pid) / 'maps').read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) < 5:
            raise UnsafePolicy('invalid_process_maps')
        major, minor = (int(value, 16) for value in fields[3].split(':'))
        targets.add((os.makedev(major, minor), int(fields[4])))
    return targets


def shm_snapshot(path):
    if not SHM_NAME.fullmatch(path.name):
        raise UnsafePolicy('unexpected_directory_name')
    info = path.lstat()
    validate_stat(info, 0o770, directory=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(info) or set(os.listdir(fd)) != SHM_FILES:
            raise UnsafePolicy('changed_directory_or_unexpected_children')
        files = {}
        for name in SHM_FILES:
            child = os.stat(name, dir_fd=fd, follow_symlinks=False)
            validate_stat(child, 0o660)
            files[name] = identity(child)
        return identity(info), files
    finally:
        os.close(fd)


def collect_policy(shm_root=Path('/dev/shm'), proc_root=Path('/proc'),
                   executable=EXECUTABLE, state=service_state):
    warnings = []
    candidates = sorted(path for path in shm_root.iterdir() if path.name.startswith('qb-'))
    pid, status = state()
    if pid is None:
        warnings.extend(path.name + ': usbguard_not_active' for path in candidates)
        if status == 'inactive':
            warnings.append('installed_usbguard_inactive')
        return [], warnings, None
    expected = process_snapshot(pid, proc_root, executable)
    mappings = mapped_inodes(pid, proc_root)
    accepted = {}
    for path in candidates:
        try:
            snapshot = shm_snapshot(path)
            if not {value[:2] for value in snapshot[1].values()}.issubset(mappings):
                raise UnsafePolicy('not_all_files_mapped_by_usbguard')
            accepted[path] = snapshot
        except (OSError, ValueError, UnsafePolicy) as exc:
            warnings.append(path.name + ': ' + str(exc))
    # Recheck all process and SHM identities at the end, including newly replaced mappings.
    if state() != (pid, 'active') or process_snapshot(pid, proc_root, executable) != expected:
        raise UnsafePolicy('daemon_changed_during_refresh')
    fresh_mappings = mapped_inodes(pid, proc_root)
    for path, snapshot in accepted.items():
        if (shm_snapshot(path) != snapshot
                or not {value[:2] for value in snapshot[1].values()}.issubset(fresh_mappings)):
            raise UnsafePolicy('shm_changed_during_refresh')
    paths = [str(path / name) for path in sorted(accepted) for name in sorted(SHM_FILES)]
    return paths, warnings, status


def config_data(paths):
    lines = ['ALLOWDEVFILE=' + path for path in paths]
    if any(not LINE.fullmatch(line) for line in lines):
        raise UnsafePolicy('invalid_exact_policy_path')
    return (HEADER + ''.join(line + '\n' for line in lines)).encode('utf-8')


def config_check():
    result = subprocess.run(['/usr/bin/rkhunter', '--config-check', '--enable', 'all',
                             '--disable', 'none', '--nocf', '--nolog'], capture_output=True, text=True,
                            timeout=120)
    if result.returncode:
        raise UnsafePolicy('rkhunter_config_check_failed: ' + result.stderr.strip())


def warn(message):
    print('Warning: ' + message, file=sys.stderr)
    subprocess.run(['/usr/bin/logger', '-p', 'authpriv.warning', '-t', 'homelab-rkhunter',
                    '--', message], check=False, timeout=10)


def refresh(config=CONFIG):
    ensure_directory(config.parent)
    info = managed_config(config)
    failed = None
    try:
        paths, warnings, _ = collect_policy()
    except (OSError, ValueError, subprocess.SubprocessError, UnsafePolicy) as exc:
        paths, warnings = [], ['policy_verification_failed: ' + str(exc)]
        failed = exc
    atomic_write(config, config_data(paths), identity(info) if info else None, 0o600)
    try:
        config_check()
    except (OSError, subprocess.SubprocessError, UnsafePolicy):
        current = managed_config(config)
        atomic_write(config, config_data([]), identity(current) if current else None, 0o600)
        raise
    for warning in warnings:
        warn(warning)
    return {'allowed_paths': len(paths), 'warnings': warnings, 'verification_failed': failed is not None}


def install(apply=False, source=None, installed=INSTALLED, cron=CRON, config=CONFIG):
    source = Path(__file__) if source is None else source
    data = source.read_bytes()
    cron_data, cron_info = read_file(cron)
    candidate = cron_candidate(cron_data)
    installed_data, installed_info = read_file(installed, optional=True)
    managed_config(config)
    # Inspection must not create the directory, policy, installation or cron hook.
    report = {'helper_change': installed_data != data or (installed_info is not None and
              stat.S_IMODE(installed_info.st_mode) != 0o755), 'cron_change': candidate != cron_data}
    if not apply:
        paths, warnings, _ = collect_policy()
        report.update(allowed_paths=len(paths), warnings=warnings)
    if apply:
        ensure_directory(installed.parent)
        ensure_directory(config.parent)
        atomic_write(installed, data, identity(installed_info) if installed_info else None, 0o755)
        report['policy'] = refresh(config)
        atomic_write(cron, candidate, identity(cron_info), stat.S_IMODE(cron_info.st_mode))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root. This helper does not handle sudo credentials.')
    try:
        result = refresh() if args.refresh else install(apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        failed = result.get('verification_failed') or result.get('policy', {}).get('verification_failed')
        return 1 if failed else 0
    except (OSError, ValueError, subprocess.SubprocessError, UnsafePolicy) as exc:
        print('USBGuard policy error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
