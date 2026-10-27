#!/usr/bin/env python3
"""Bounded read-only inspection of this kit's two-stream unsigned APK v2 profile.
Does not extract, execute, validate signatures, or parse APK v3/ADB packages.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import tarfile
import zlib

def split_streams(blob, limit):
    parts = []
    while blob:
        if len(parts) == 2:
            raise ValueError('Expected exactly two gzip streams; signature blocks need separate review')
        decoder = zlib.decompressobj(31)
        try:
            raw = decoder.decompress(blob, limit + 1)
        except zlib.error as error:
            raise ValueError('Unsupported/corrupt gzip stream; APK v3 is outside this helper') from error
        if len(raw) > limit or not decoder.eof:
            raise ValueError('Truncated stream or expanded size limit exceeded')
        consumed = len(blob) - len(decoder.unused_data)
        if consumed <= 0:
            raise ValueError('Invalid gzip boundary')
        parts.append(blob[:consumed])
        blob = decoder.unused_data
    if len(parts) != 2:
        raise ValueError('Expected unsigned control stream followed by payload stream')
    return parts

def inspect(path, limit=128 * 1024 * 1024):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError('APK input exceeds configured size limit')
    blob = path.read_bytes()
    control_blob, payload_blob = split_streams(blob, limit)
    member_reader = runpy.run_path(str(Path(__file__).with_name('inspect-ipk.py')))['members']
    controls, control_listing = member_reader(control_blob, limit)
    payload, listing = member_reader(payload_blob, limit)
    with gzip.GzipFile(fileobj=io.BytesIO(payload_blob)) as stream:
        raw_payload = stream.read(limit + 1)
    if len(raw_payload) > limit:
        raise ValueError('Expanded APK payload limit exceeded')
    with tarfile.open(fileobj=io.BytesIO(raw_payload), mode='r:') as archive:
        for item in archive:
            if set(item.pax_headers) - {'APK-TOOLS.checksum.SHA1', 'path'}:
                raise ValueError('Unreviewed APK PAX metadata')
            if item.isfile():
                data = archive.extractfile(item).read()
                if item.pax_headers.get('APK-TOOLS.checksum.SHA1') != hashlib.sha1(data).hexdigest():
                    raise ValueError('Missing/incorrect embedded APK per-file checksum: ' + item.name)
    hooks = {'.pre-install', '.post-install', '.pre-upgrade', '.post-upgrade', '.pre-deinstall', '.post-deinstall'}
    if '.PKGINFO' not in controls or set(controls) - hooks - {'.PKGINFO'} or not payload:
        raise ValueError('Invalid control members or empty payload')
    metadata, depends = {}, []
    text = controls['.PKGINFO'].decode('utf-8')
    if '\r' in text or '\0' in text:
        raise ValueError('APK metadata must use LF and contain no NUL')
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition(' = ')
        if not separator or not key or not value:
            raise ValueError('Malformed .PKGINFO line')
        if key == 'depend':
            if value in depends or not re.fullmatch(r'[a-z0-9][a-z0-9+._-]*', value):
                raise ValueError('Duplicate/complex dependency outside strict helper profile')
            depends.append(value)
        elif key in metadata:
            raise ValueError('Duplicate .PKGINFO key: ' + key)
        else:
            metadata[key] = value
    if not re.fullmatch(r'[a-z0-9][a-z0-9+._-]*', metadata.get('pkgname', '')):
        raise ValueError('Invalid APK package name')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*-r[1-9][0-9]*', metadata.get('pkgver', '')):
        raise ValueError('Unsupported APK version')
    if metadata.get('arch') != 'noarch':
        raise ValueError('This helper inspects pure script/resource noarch APKs only')
    if metadata.get('datahash') != hashlib.sha256(payload_blob).hexdigest():
        raise ValueError('APK datahash mismatch')
    modes = {item['path']: int(item['mode'], 8) for item in listing}
    hook_modes = {item['path']: int(item['mode'], 8) for item in control_listing}
    for name in hooks & controls.keys():
        if b'\r' in controls[name] or not controls[name].startswith(b'#!/bin/sh\n') or not hook_modes[name] & 0o111:
            raise ValueError('Invalid APK lifecycle script: ' + name)
    for name, data in payload.items():
        if data.startswith(b'\x7fELF'):
            raise ValueError('ELF requires SDK and separate ABI review')
        if data.startswith(b'#!') and (b'\r' in data.split(b'\n', 1)[0] or not modes[name] & 0o111):
            raise ValueError('Invalid shebang/execute mode: ' + name)
    return {'profile': 'unsigned-apkv2-compat-strict', 'status': 'pass', 'file': path.name,
            'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob), 'metadata': metadata,
            'depends': depends, 'hooks': sorted(hooks & controls.keys()), 'files': listing,
            'scope': 'Structure and datahash only; unsigned; no install, ABI or appcenter certification'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    result = inspect(args.package)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))

if __name__ == '__main__':
    main()
