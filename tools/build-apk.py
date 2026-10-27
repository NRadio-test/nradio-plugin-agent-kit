#!/usr/bin/env python3
"""Build an unsigned APK v2 for the observed ultra 3.0 apk-tools 3.0.5 reader.
Pure scripts/resources only. This is not an APK v3/ADB writer or a compiler.
Production native packages use the matching vendor SDK.
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
import tempfile

BASE = Path(__file__).resolve().parents[1]

def layer(items, cut_eoa=False, file_checksums=False):
    buffer = io.BytesIO()
    end = 0
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.PAX_FORMAT if file_checksums else tarfile.USTAR_FORMAT) as archive:
        for name, data, mode, directory in items:
            item = tarfile.TarInfo(name)
            item.mode, item.uid, item.gid, item.mtime = mode, 0, 0, 0
            item.uname = item.gname = 'root'
            if directory:
                item.type = tarfile.DIRTYPE
                archive.addfile(item)
            else:
                item.size = len(data)
                if file_checksums:
                    item.pax_headers = {'APK-TOOLS.checksum.SHA1': hashlib.sha1(data).hexdigest()}
                archive.addfile(item, io.BytesIO(data))
            end = buffer.tell()
    raw = buffer.getvalue()[:end] if cut_eoa else buffer.getvalue()
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', filename='', mtime=0) as stream:
        stream.write(raw)
    return compressed.getvalue()

def build(project, out):
    project, out = Path(project).resolve(), Path(out).resolve()
    legacy = runpy.run_path(str(Path(__file__).with_name('build.py')))
    cfg = legacy['load_config'](project)
    if cfg['architecture'] != 'all':
        raise ValueError('This APK helper supports pure scripts/resources only; use the vendor SDK for ELF/kmod')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', cfg['version']):
        raise ValueError('This APK helper accepts numeric dotted versions; use SDK for other APK version schemes')
    if any(out.is_relative_to((project / name).resolve()) for name in ('root', 'control')):
        raise ValueError('APK output must stay outside root/ and control/')
    out.mkdir(parents=True, exist_ok=True)
    # Reuse the established path, permissions, shebang and payload validation.
    # The temporary IPK is a validation intermediate, never a claimed ultra artifact.
    with tempfile.TemporaryDirectory(prefix='apk-validation-', dir=out) as temporary:
        legacy['build'](project, Path(temporary))
    entries = []
    for path in sorted((project / 'root').rglob('*')):
        rel = path.relative_to(project / 'root').as_posix()
        directory = path.is_dir()
        data = b'' if directory else path.read_bytes()
        if data.startswith(b'\x7fELF'):
            raise ValueError('ELF requires matching vendor SDK and runtime ABI validation')
        mode = 0o755 if directory or rel in cfg['executable_files'] else 0o644
        entries.append((rel, data, mode, directory))
    payload = layer(entries, file_checksums=True)
    version = cfg['version'] + '-r' + str(cfg['release'])
    info = '\n'.join([
        'pkgname = ' + cfg['package'], 'pkgver = ' + version,
        'pkgdesc = ' + cfg['description'], 'builddate = 0',
        'packager = ' + cfg['maintainer'],
        'size = ' + str(sum(len(data) for _, data, _, _ in entries)),
        'arch = noarch', 'license = ' + cfg['license'],
        *['depend = ' + dependency for dependency in cfg['depends']],
        'datahash = ' + hashlib.sha256(payload).hexdigest(),
    ]) + '\n'
    controls = [('.PKGINFO', info.encode('utf-8'), 0o644, False)]
    mapping = [('preinst', ('pre-install', 'pre-upgrade')),
               ('postinst', ('post-install', 'post-upgrade')),
               ('prerm', ('pre-deinstall',)), ('postrm', ('post-deinstall',))]
    for source, destinations in mapping:
        hook = project / 'control' / source
        if hook.exists():
            for destination in destinations:
                controls.append(('.' + destination, hook.read_bytes(), 0o755, False))
    blob = layer(controls, cut_eoa=True) + payload
    filename = cfg['package'] + '-' + version + '.apk'
    (out / filename).write_bytes(blob)
    manifest = {
        'format': 'unsigned-apkv2-compat', 'package': cfg['package'], 'version': version,
        'architecture': 'noarch', 'depends': cfg['depends'], 'conffiles': cfg['conffiles'],
        'file': filename, 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
        'luci_route': cfg.get('luci_route'), 'signed': False,
        'target_profile': 'ultra-3.0.0.n0.c1-preview-apk-tools-3.0.5',
        'device_validation': 'not_run_for_this_build', 'appcenter_import': 'not_run_for_this_build',
        'observed_appcenter_backend': 'opkg; native APK test rejected with code 14',
        'files': [{'path': name, 'bytes': len(data), 'mode': oct(mode), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data, mode, directory in entries if not directory],
    }
    (out / 'apk-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return cfg, manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=BASE if (BASE / 'plugin.json').exists() else BASE / 'example')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    _, manifest = build(project, args.output or (BASE / 'dist' if project == BASE / 'example' else project / 'dist'))
    print(json.dumps(manifest, ensure_ascii=True))

if __name__ == '__main__':
    main()
