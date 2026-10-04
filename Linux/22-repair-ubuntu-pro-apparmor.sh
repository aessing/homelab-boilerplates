#!/usr/bin/env bash

# Restore two Ubuntu Pro firmware read rules without replacing local policy.
set -euo pipefail
export PATH='/usr/sbin:/usr/bin:/sbin:/bin'
export LC_ALL=C LANG=C

mode='--check'
if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi
case "${1:---check}" in
  --check|--apply) mode="${1:---check}" ;;
  --help|-h)
    echo "Usage: $0 [--check|--apply]"
    echo 'Check is the default. Apply repairs and reloads only ubuntu_pro_esm_cache.'
    exit 0
    ;;
  *) echo "Usage: $0 [--check|--apply]" >&2; exit 2 ;;
esac
if [ "$EUID" -ne 0 ]; then
  echo 'Run as root. No sudo password is read or stored by this helper.' >&2
  exit 1
fi
for program in /usr/bin/python3 /usr/bin/dpkg-query /usr/sbin/apparmor_parser; do
  if [ ! -x "$program" ]; then
    echo "Required program missing: $program" >&2
    exit 1
  fi
done

umask 077
repair_dir="$(mktemp -d /etc/apparmor.d/.ubuntu-pro-repair.XXXXXX)"
# The directory contains only the new candidate, never an original/backup copy.
trap 'rm -rf -- "$repair_dir"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

/usr/bin/python3 -I - "$mode" "$repair_dir" <<'PYTHON'
import hashlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


PROFILE = Path('/etc/apparmor.d/ubuntu_pro_esm_cache')
VENDOR = Path('/etc/apparmor.d/ubuntu_pro_esm_cache.dpkg-dist')
PARSER = '/usr/sbin/apparmor_parser'
ANCHOR = '@{PROC}/sys/kernel/osrelease r,'
RULES = {
    'ubuntu_pro_esm_cache': '/sys/firmware/devicetree/base/model r,',
    'ubuntu_pro_esm_cache_systemd_detect_virt': '/sys/firmware/dmi/entries/0-0/raw r,',
}


def scoped_lines(text):
    """Accept the known profile structure, including unchanged custom rules."""
    if '\r' in text:
        raise ValueError('Unsupported profile line endings')
    lines = text.splitlines(keepends=True)
    depth = 0
    sections = {}
    active = []
    for index, line in enumerate(lines):
        code = line.split('#', 1)[0].strip()
        declaration = re.fullmatch(
            r'profile\s+(ubuntu_pro_esm_cache(?:_systemd_detect_virt)?)'
            r'\s+flags=\(attach_disconnected\)\s*\{', code)
        if declaration:
            name = declaration.group(1)
            # The vendor moved detect_virt to top level to avoid a kernel bug.
            if name in sections or depth != 0:
                raise ValueError('Duplicate or misplaced target profile: ' + name)
            sections[name] = []
            active.append((name, depth))
        for name, start_depth in active:
            if depth == start_depth + 1:
                sections[name].append(index)
        # Inline AppArmor path/variable braces are balanced within their line.
        depth += code.count('{') - code.count('}')
        if depth < 0:
            raise ValueError('Unbalanced profile braces')
        active = [(name, start) for name, start in active if depth > start]
    if depth or set(sections) != set(RULES):
        raise ValueError('Missing target profile or unsupported brace structure')
    return lines, sections


def repair_profile(current, vendor):
    lines, sections = scoped_lines(current)
    vendor_lines, vendor_sections = scoped_lines(vendor)
    additions = []
    for name, rule in RULES.items():
        if sum(vendor_lines[i].strip() == rule for i in vendor_sections[name]) != 1:
            raise ValueError('Installed vendor policy lacks the exact rule: ' + rule)
        matches = [i for i in sections[name] if lines[i].strip() == rule]
        if len(matches) > 1:
            raise ValueError('Duplicate target rule: ' + rule)
        if matches:
            continue
        anchors = [i for i in sections[name] if lines[i].strip() == ANCHOR]
        if len(anchors) != 1:
            raise ValueError('Missing or ambiguous insertion anchor: ' + name)
        index = anchors[0]
        indent = lines[index][:len(lines[index]) - len(lines[index].lstrip())]
        additions.append((index + 1, '\n' + indent + '# LP: #2131292\n' + indent + rule + '\n'))
    for index, addition in sorted(additions, reverse=True):
        lines.insert(index, addition)
    candidate = ''.join(lines)
    # Recheck scopes after insertion, including the already repaired case.
    candidate_lines, candidate_sections = scoped_lines(candidate)
    for name, rule in RULES.items():
        if sum(candidate_lines[i].strip() == rule for i in candidate_sections[name]) != 1:
            raise ValueError('Candidate rule verification failed')
    return candidate, len(additions)


def read_root_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError('Expected a root-owned regular policy file without group/world write: ' + str(path))
        content = handle.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError('Policy file exceeds the supported size')
    return content, metadata


def installed_md5():
    result = subprocess.run(
        ['/usr/bin/dpkg-query', '-W', '-f=${db:Status-Status}\n${Conffiles}', 'ubuntu-pro-client'],
        check=True, text=True, capture_output=True, timeout=15)
    lines = result.stdout.splitlines()
    if not lines or lines[0] != 'installed':
        raise ValueError('ubuntu-pro-client is not installed')
    matches = [re.fullmatch(r'\s*' + re.escape(str(PROFILE)) + r' ([0-9a-f]{32})', line)
               for line in lines[1:]]
    hashes = [match.group(1) for match in matches if match]
    if len(hashes) != 1:
        raise ValueError('Missing or ambiguous installed conffile hash')
    return hashes[0]


def run_parser(path, apply=False):
    subprocess.run(
        [PARSER, '-r' if apply else '-Q', '-K', '--jobs=1', '-b', str(PROFILE.parent), str(path)],
        check=True, timeout=120)


def main(mode, repair_dir):
    if os.geteuid() != 0:
        raise ValueError('Root is required')
    for directory in (PROFILE.parent.parent, PROFILE.parent, repair_dir):
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise ValueError('Unsafe policy/candidate directory: ' + str(directory))
    if repair_dir.parent != PROFILE.parent or repair_dir.stat().st_mode & 0o077:
        raise ValueError('Candidate directory must be private and next to the policy')
    original, metadata = read_root_file(PROFILE)
    expected_md5 = installed_md5()
    try:
        vendor, _ = read_root_file(VENDOR)
    except FileNotFoundError:
        # A fresh package installation may already contain the official policy.
        vendor = original
    if hashlib.md5(vendor, usedforsecurity=False).hexdigest() != expected_md5:
        raise ValueError('Vendor policy does not match the installed package conffile hash')
    candidate_text, additions = repair_profile(original.decode('utf-8'), vendor.decode('utf-8'))
    candidate = repair_dir / PROFILE.name
    fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(candidate_text.encode('utf-8'))
        handle.flush()
        os.fchown(handle.fileno(), metadata.st_uid, metadata.st_gid)
        os.fchmod(handle.fileno(), stat.S_IMODE(metadata.st_mode))
        os.fsync(handle.fileno())
    run_parser(candidate)
    print(f'Validated policy, missing official rules: {additions}')
    if mode == '--check':
        print('Check complete. No policy file or loaded profile was changed.')
        return
    latest, latest_metadata = read_root_file(PROFILE)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_gid)
    if latest != original or identity(latest_metadata) != identity(metadata):
        raise ValueError('Policy changed during validation, refusing replacement')
    if additions:
        os.replace(candidate, PROFILE)
        directory_fd = os.open(PROFILE.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    try:
        run_parser(PROFILE, apply=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError('The on-disk policy is repaired but its targeted reload failed. '
                           'The loaded policy is not verified. Review the parser error and '
                           'rerun --apply after resolving it.') from error
    print('Applied and reloaded only profiles declared in ubuntu_pro_esm_cache.')


if __name__ == '__main__':
    try:
        main(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Repair failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
PYTHON
