#!/usr/bin/env python3
"""Read-only, bounded host inspection of the observed gzip/tar IPK profile.
No archive extraction or code execution. Links/special files require manual SDK review.
This check does not certify dependency closure, ABI, script semantics, or device operation.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

def members(data, limit):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Expanded archive exceeds configured per-layer limit')
    files, inventory, seen = {}, [], set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        for index, item in enumerate(tar):
            if index >= 10000:
                raise ValueError('Archive member count exceeds helper profile')
            path = item.name
            while path.startswith('./'):
                path = path[2:]
            if path in ('', '.') and item.isdir():
                continue
            if (path.startswith('/') or any(c in path for c in '\\\r\n\0:')
                    or any(p in ('', '.', '..') for p in path.rstrip('/').split('/'))):
                raise ValueError('Unsafe archive path: ' + repr(item.name))
            path = path.rstrip('/')
            if path in seen:
                raise ValueError('Duplicate archive member: ' + path)
            seen.add(path)
            if not (item.isfile() or item.isdir()):
                raise ValueError('Link/special member outside strict helper profile: ' + path)
            if item.mode & 0o6000:
                raise ValueError('Privileged setuid/setgid mode requires separate review: ' + path)
            if item.isfile():
                payload = tar.extractfile(item).read()
                files[path] = payload
                inventory.append({'path': path, 'mode': oct(item.mode), 'bytes': len(payload),
                                  'sha256': hashlib.sha256(payload).hexdigest()})
    # Avoid ambiguous file-as-parent layouts even when an extractor differs.
    for name in seen:
        parts = name.split('/')
        if any('/'.join(parts[:i]) in files for i in range(1, len(parts))):
            raise ValueError('Archive regular file is also a parent directory: ' + name)
    return files, inventory

def control_fields(data):
    text = data.decode('utf-8')
    if '\r' in text or '\0' in text:
        raise ValueError('Control file must use LF and contain no NUL')
    fields, last = {}, None
    for line in text.splitlines():
        if not line:
            continue
        if line[0].isspace() and last:
            fields[last] += '\n' + line
            continue
        match = re.fullmatch(r'([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)', line)
        if not match or match[1] in fields:
            raise ValueError('Malformed or duplicate control field')
        last = match[1]
        fields[last] = match[2]
    for key in ('Package', 'Version', 'Architecture'):
        if not fields.get(key):
            raise ValueError('Missing control field: ' + key)
    if not re.fullmatch(r'[a-z0-9][a-z0-9+._-]*', fields['Package']):
        raise ValueError('Invalid Package field')
    return fields

def inspect(path, limit=128 * 1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError('IPK exceeds configured input size limit')
    blob = path.read_bytes()
    outer, _ = members(blob, limit)
    if set(outer) != {'debian-binary', 'control.tar.gz', 'data.tar.gz'} or outer['debian-binary'] != b'2.0\n':
        raise ValueError('Unsupported outer IPK layout/version')
    control, control_listing = members(outer['control.tar.gz'], limit)
    payload, listing = members(outer['data.tar.gz'], limit)
    if 'control' not in control or not payload:
        raise ValueError('Missing control or empty payload')
    meta = control_fields(control['control'])
    if meta['Architecture'] not in ('all', 'noarch', 'aarch64_cortex-a53'):
        raise ValueError('Architecture is not accepted by observed target profile')
    control_modes = {i['path']: int(i['mode'], 8) for i in control_listing}
    modes = {i['path']: int(i['mode'], 8) for i in listing}
    elf_files = []
    for name, data in payload.items():
        if data.startswith(b'#!'):
            if b'\r' in data.split(b'\n', 1)[0] or not modes[name] & 0o111:
                raise ValueError('Invalid script shebang/execute mode: ' + name)
        if data.startswith(b'\x7fELF'):
            if meta['Architecture'] == 'all':
                raise ValueError('Native ELF is incorrectly labelled all: ' + name)
            if (meta['Architecture'] != 'aarch64_cortex-a53' or len(data) < 20
                    or data[4:6] != b'\x02\x01' or int.from_bytes(data[18:20], 'little') != 183):
                raise ValueError('Native ELF does not match this target profile: ' + name)
            elf_files.append(name)
    for line in control.get('conffiles', b'').decode('utf-8').splitlines():
        if not line.startswith('/') or line[1:] not in payload:
            raise ValueError('Conffile missing from package payload: ' + line)
    for hook in ('preinst', 'postinst', 'prerm', 'postrm'):
        if hook in control and (b'\r' in control[hook] or not control[hook].startswith(b'#!/bin/sh\n')
                                or not control_modes[hook] & 0o111):
            raise ValueError('Hook outside helper shell/LF profile: ' + hook)
    return {'profile': 'nradio-gzip-tar-strict', 'status': 'pass', 'file': path.name,
            'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob), 'control': meta,
            'source_bytes': sum(len(d) for d in payload.values()), 'files': listing,
            'elf_files_require_runtime_abi_check': elf_files,
            'scope': 'Host structure/metadata only; not device validation'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ipk', type=Path)
    parser.add_argument('--max-expanded-mib', type=int, default=128)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    try:
        if args.max_expanded_mib < 1:
            raise ValueError('Limit must be positive')
        result = inspect(args.ipk, args.max_expanded_mib * 1024 * 1024)
    except (ValueError, OSError, tarfile.TarError, EOFError) as exc:
        result = {'status': 'fail', 'profile': 'nradio-gzip-tar-strict', 'error': str(exc)}
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.json_out:
        args.json_out.write_text(text, encoding='utf-8')
    print(text, end='')
    raise SystemExit(0 if result['status'] == 'pass' else 1)

if __name__ == '__main__':
    main()
