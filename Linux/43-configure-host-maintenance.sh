#!/usr/bin/env bash
# Make safe SSH policy visible to older rkhunter and skip unused Pi 5 flashrom.
set -euo pipefail
export PATH='/usr/sbin:/usr/bin:/sbin:/bin'
export LC_ALL=C LANG=C
mode='--check'
flashrom='no'
for arg in "$@"; do
  case "$arg" in
    --check|--apply) mode="$arg" ;;
    --disable-flashrom) flashrom='yes' ;;
    --help|-h)
      echo "Usage: $0 [--check|--apply] [--disable-flashrom]"
      echo 'Flashrom opt-out requires Raspberry Pi 5. No backups or service restarts.'
      exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done
if [ "$EUID" -ne 0 ]; then
  echo 'Run as root. This helper does not handle sudo credentials.' >&2
  exit 1
fi
/usr/bin/python3 -I - "$mode" "$flashrom" <<'PYTHON'
import configparser
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SSH = Path('/etc/ssh/sshd_config')
FWUPD = [Path('/etc/fwupd/fwupd.conf'), Path('/var/lib/fwupd/fwupd.conf')]
RKHUNTER_DEFAULTS = Path('/etc/default/rkhunter')
RKHUNTER_CONFIGS = [Path('/etc/rkhunter.conf'), Path('/etc/rkhunter.conf.local')]
SYSTEMD_MARKER = Path('/etc/.updated')


def run(args):
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=30)
    return result.stdout


def read_config(path, optional=False):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if optional:
            return None, None
        raise
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Unsafe config ownership/type/mode: ' + str(path))
        data = handle.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('Oversized config: ' + str(path))
    data.decode('utf-8')
    return data, info


def ssh_candidate(text):
    if '\r' in text:
        raise ValueError('Unsupported SSH line endings')
    settings = re.findall(r'^\s*PermitRootLogin\s+(\S+)', text, re.M | re.I)
    if settings:
        if any(value.lower() != 'no' for value in settings):
            raise ValueError('Existing explicit root-login policy needs manual review')
        return text
    return '# Expose existing safe policy to rkhunter 1.4.6 without changing Includes.\nPermitRootLogin no\n' + text


def rkhunter_candidate(text):
    if '\r' in text:
        raise ValueError('Unsupported rkhunter defaults line endings')
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if re.match(r'^\s*(?:export\s+)?APT_AUTOGEN\s*=', line)]
    if len(matches) > 1:
        raise ValueError('Ambiguous duplicate APT_AUTOGEN settings')
    if matches:
        index = matches[0]
        match = re.fullmatch(r'(\s*)APT_AUTOGEN\s*=\s*(?:"(yes|no)"|\'(yes|no)\'|(yes|no))(\s*(?:#[^\n]*)?)(\n?)', lines[index])
        if match is None:
            raise ValueError('Unreviewed APT_AUTOGEN shell syntax')
        if next(value for value in match.group(2, 3, 4) if value is not None) == 'no':
            return text
        lines[index] = match.group(1) + 'APT_AUTOGEN="no"' + match.group(5) + match.group(6)
    else:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.extend(['# Package changes must not overwrite the known rkhunter file baseline.\n', 'APT_AUTOGEN="no"\n'])
    return ''.join(lines)


def rkhunter_web_candidate(text):
    if '\r' in text:
        raise ValueError('Unsupported rkhunter config line endings')
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if re.match(r'^[ \t]*WEB_CMD[ \t]*=', line)]
    if len(matches) > 1:
        raise ValueError('Ambiguous duplicate WEB_CMD settings')
    if not matches:
        return text
    index = matches[0]
    match = re.fullmatch(r'([ \t]*WEB_CMD[ \t]*=[ \t]*)("/bin/false"|\'/bin/false\'|/bin/false)([ \t]*(?:#[^\n]*)?)(\n?)', lines[index])
    if match is None:
        # This repair does not replace another configured network command.
        return text
    if match.group(2) == '/bin/false':
        return text
    lines[index] = match.group(1) + '/bin/false' + match.group(3) + match.group(4)
    return ''.join(lines)


def rkhunter_hidden_candidate(text, marker_data, marker_info):
    if marker_data is None:
        return text
    if (marker_info is None or not stat.S_ISREG(marker_info.st_mode)
            or marker_info.st_uid != 0 or stat.S_IMODE(marker_info.st_mode) != 0o644):
        raise ValueError('Unexpected systemd marker ownership/type/mode')
    message = (b'# This file was created by systemd-update-done. Its only \n'
               b'# purpose is to hold a timestamp of the time this directory\n'
               b'# was updated. See man:systemd-update-done.service(8).\n')
    if re.fullmatch(re.escape(message) + rb'TIMESTAMP_NSEC=[0-9]+\n', marker_data) is None:
        raise ValueError('Unexpected systemd marker content')
    if '\r' in text:
        raise ValueError('Unsupported rkhunter config line endings')
    # This repeatable key is scoped to the one verified marker, never a glob.
    if re.search(r'^[ \t]*ALLOWHIDDENFILE[ \t]*=[ \t]*/etc/\.updated[ \t]*(?:#[^\n]*)?$', text, re.M):
        return text
    if re.search(r'^[ \t]*ALLOWHIDDENFILE[ \t]*=[^\n]*/etc/\.updated', text, re.M):
        raise ValueError('Unreviewed existing marker exception syntax')
    if text and not text.endswith('\n'):
        text += '\n'
    return text + '# Verified systemd-update-done timestamp marker.\nALLOWHIDDENFILE=/etc/.updated\n'


def disabled_plugins(text):
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=('=',),
                                       comment_prefixes=('#',), empty_lines_in_values=False)
    parser.optionxform = str
    parser.read_string(text)
    raw = parser.get('fwupd', 'DisabledPlugins', fallback=None)
    if raw is None:
        return None
    tokens = [token.strip() for token in raw.split(';') if token.strip()]
    if any(not re.fullmatch(r'[a-zA-Z0-9_?*-]+', token) for token in tokens):
        raise ValueError('Unsupported DisabledPlugins list syntax')
    return tokens


def fwupd_candidate(text):
    if '\r' in text:
        raise ValueError('Unsupported fwupd line endings')
    tokens = disabled_plugins(text)
    if tokens is not None and 'flashrom' in tokens:
        return text
    lines = text.splitlines(keepends=True)
    section = None
    section_start = None
    key_index = None
    for index, line in enumerate(lines):
        match = re.fullmatch(r'\s*\[([^\]]+)\]\s*\n?', line)
        if match:
            section = match.group(1)
            if section == 'fwupd':
                section_start = index
        elif section == 'fwupd' and re.match(r'^\s*DisabledPlugins\s*=', line):
            key_index = index
    value = ';'.join((tokens or []) + ['flashrom'])
    if key_index is not None:
        prefix = lines[key_index].split('=', 1)[0]
        lines[key_index] = prefix + '=' + value + '\n'
    elif section_start is not None:
        if not lines[section_start].endswith('\n'):
            lines[section_start] += '\n'
        lines.insert(section_start + 1, 'DisabledPlugins=' + value + '\n')
    else:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.extend(['\n[fwupd]\n', 'DisabledPlugins=' + value + '\n'])
    candidate = ''.join(lines)
    expected = (tokens or []) + ['flashrom']
    if disabled_plugins(candidate) != expected:
        raise ValueError('fwupd candidate verification failed')
    return candidate


def secure_parent(path):
    for directory in [path.parent, *path.parent.parents]:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Unsafe config parent: ' + str(directory))


def staged_file(path, data, info):
    secure_parent(path)
    fd, name = tempfile.mkstemp(prefix='.host-maintenance-candidate-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchown(handle.fileno(), info.st_uid, info.st_gid)
            os.fchmod(handle.fileno(), stat.S_IMODE(info.st_mode))
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(name)
        raise
    return Path(name)


def ssh_effective(path):
    base = ['/usr/sbin/sshd', '-T', '-f', str(path)]
    return (run(base), run(base + ['-C', 'user=root,host=localhost,addr=127.0.0.1']))


def main(mode, flashrom):
    if os.geteuid() != 0:
        raise ValueError('Root required')
    original, metadata = read_config(SSH)
    before = ssh_effective(SSH)
    if any('permitrootlogin no\n' not in output for output in before):
        raise ValueError('Effective root-login policy is not already no')
    changes = []
    defaults, defaults_info = read_config(RKHUNTER_DEFAULTS, optional=True)
    if defaults is not None:
        status = run(['/usr/bin/dpkg-query', '-W', '-f=${db:Status-Status}', 'rkhunter'])
        if status.strip() == 'installed':
            changes.append((RKHUNTER_DEFAULTS, defaults, defaults_info, rkhunter_candidate(defaults.decode()).encode()))
            marker, marker_info = read_config(SYSTEMD_MARKER, optional=True)
            existing_marker_exception = False
            configs = []
            for path in RKHUNTER_CONFIGS:
                current, info = read_config(path, optional=True)
                if current is not None:
                    text = current.decode()
                    # Check either file before adding a repeatable main-config key.
                    validated = rkhunter_hidden_candidate(text, marker, marker_info)
                    existing_marker_exception |= validated == text and marker is not None
                    configs.append((path, current, info, text))
            for path, current, info, text in configs:
                candidate = rkhunter_web_candidate(text)
                if path == RKHUNTER_CONFIGS[0] and not existing_marker_exception:
                    candidate = rkhunter_hidden_candidate(candidate, marker, marker_info)
                changes.append((path, current, info, candidate.encode()))
    changes.append((SSH, original, metadata, ssh_candidate(original.decode()).encode()))
    if flashrom == 'yes':
        model = Path('/sys/firmware/devicetree/base/model').read_text().rstrip('\0\n')
        if not model.startswith('Raspberry Pi 5 '):
            raise ValueError('Flashrom opt-out is scoped to Raspberry Pi 5')
        version = run(['/usr/bin/dpkg-query', '-W', '-f=${Version}', 'fwupd'])
        if not version.startswith('2.0.20-'):
            raise ValueError('Recheck supported fwupd configuration for this package version')
        for path in FWUPD:
            if path.with_name('daemon.conf').exists():
                raise ValueError('Legacy fwupd daemon.conf requires explicit migration review')
            current, info = read_config(path, optional=True)
            if current is None:
                if path == FWUPD[0]:
                    raise ValueError('Expected installed /etc/fwupd/fwupd.conf missing')
                continue
            # The mutable file overrides /etc, so preserve and extend either list.
            if path == FWUPD[0] or disabled_plugins(current.decode()) is not None:
                changes.append((path, current, info, fwupd_candidate(current.decode()).encode()))
    candidates = []
    applied = []
    try:
        for path, old, info, new in changes:
            if old == new:
                print(str(path) + ': already configured')
                continue
            candidate = staged_file(path, new, info)
            candidates.append((path, old, info, candidate))
            if path == SSH:
                run(['/usr/sbin/sshd', '-t', '-f', str(candidate)])
                if ssh_effective(candidate) != before:
                    raise ValueError('Candidate changes effective SSH policy')
            print(str(path) + ': validated targeted change')
        if mode == '--check':
            print('Check passed. No installed config changed.')
            return
        for path, old, info, candidate in candidates:
            current, current_info = read_config(path)
            identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_uid, x.st_gid)
            if current != old or identity(current_info) != identity(info):
                raise ValueError('Config changed during validation: ' + str(path))
            os.replace(candidate, path)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            applied.append(str(path))
        run(['/usr/sbin/sshd', '-t'])
        if ssh_effective(SSH) != before:
            raise ValueError('Post-write effective SSH settings changed')
        print('Apply passed. Effective SSH policy preserved. No daemon restart or scanner baseline update.')
        if flashrom == 'yes':
            print('fwupd runtime plugin/device verification is required separately.')
    except BaseException:
        if applied:
            print('Already updated files: ' + ', '.join(applied) + '. Resolve the reported failure before continuing.', file=sys.stderr)
        raise
    finally:
        for _, _, _, candidate in candidates:
            candidate.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, configparser.Error, subprocess.SubprocessError) as error:
        print('Maintenance failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
PYTHON

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
/usr/bin/python3 -I "$SCRIPT_DIR/45-clean-rkhunter-artifacts.py" "$mode"
/usr/bin/python3 -I "$SCRIPT_DIR/46-configure-rkhunter-usbguard.py" "$mode"
