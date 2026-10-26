#!/usr/bin/env python3
"""Package a reviewed payload, without compiling code. Python 3.10+, stdlib.
Metadata comes from plugin.json. Payload bytes are NEVER rewritten.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

BASE = Path(__file__).resolve().parents[1]

def relative_path(value):
    if not isinstance(value, str) or not value or any(c in value for c in '\\\r\n\0:'):
        raise ValueError('Invalid relative payload path: ' + repr(value))
    if value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Non-canonical payload path: ' + value)
    return value

def load_config(project):
    cfg = json.loads((project / 'plugin.json').read_text(encoding='utf-8'))
    for key in ('package', 'version', 'architecture', 'title', 'description', 'maintainer', 'section', 'license'):
        value = cfg.get(key)
        if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
            raise ValueError('Missing/invalid text field: ' + key)
    if not re.fullmatch(r'[a-z0-9][a-z0-9+._-]*', cfg['package']):
        raise ValueError('Invalid Package')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+~_-]*', cfg['version']):
        raise ValueError('Invalid Version for this helper profile')
    release = cfg.get('release')
    if type(release) is not int or release < 1:
        raise ValueError('release must be a positive integer')
    if cfg['architecture'] not in ('all', 'aarch64_cortex-a53'):
        raise ValueError('Helper supports all or aarch64_cortex-a53 only')
    for field in ('depends', 'conffiles', 'executable_files'):
        values = cfg.get(field)
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values) or len(set(values)) != len(values):
            raise ValueError('Invalid list: ' + field)
    for dep in cfg['depends']:
        if not re.fullmatch(r'[a-z0-9][a-z0-9+._-]*', dep):
            raise ValueError('Use SDK for complex dependency expressions: ' + dep)
    for name in cfg['executable_files']:
        relative_path(name)
    for name in cfg['conffiles']:
        if not name.startswith('/'):
            raise ValueError('Conffiles must be absolute target paths')
        relative_path(name[1:])
    cfg['full_version'] = cfg['version'] + '-' + str(release)
    return cfg

def archive(entries):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', mtime=0, filename='') as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tf:
            for path, data, mode in sorted(entries):
                info = tarfile.TarInfo('./' + path)
                info.size, info.mode = len(data), mode
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()

def sdk_text(project, cfg):
    name = cfg['package']
    for value in cfg['executable_files'] + cfg['conffiles']:
        if not re.fullmatch(r'[A-Za-z0-9_./+-]+', value):
            raise ValueError('Use a manually reviewed SDK recipe for this complex path: ' + value)
    for key in ('title', 'section', 'license'):
        if '$' in cfg[key] or '#' in cfg[key]:
            raise ValueError('Make expression/comment characters not supported in SDK field: ' + key)
    lines = ['include $(TOPDIR)/rules.mk', '',
             'PKG_NAME:=' + name, 'PKG_VERSION:=' + cfg['version'],
             'PKG_RELEASE:=' + str(cfg['release']), 'PKG_LICENSE:=' + cfg['license'], '',
             'include $(INCLUDE_DIR)/package.mk', '', 'define Package/' + name,
             '  SECTION:=' + cfg['section'], '  CATEGORY:=LuCI', '  SUBMENU:=3. Applications',
             '  TITLE:=' + cfg['title'].replace('$', '$$').replace('#', '\\#'),
             '  DEPENDS:=' + ' '.join('+' + d for d in cfg['depends']),
             '  PKGARCH:=' + cfg['architecture'], 'endef', '',
             'define Package/' + name + '/conffiles', *cfg['conffiles'], 'endef', '',
             'define Build/Compile', 'endef', '', 'define Package/' + name + '/install',
             '\t$(CP) ./root/* $(1)/']
    for filename in cfg['executable_files']:
        lines.append('\tchmod 0755 $(1)/' + filename)
    lines += ['endef', '']
    for hook in ('preinst', 'postinst', 'prerm', 'postrm'):
        source = project / 'control' / hook
        if source.exists():
            lines += ['define Package/' + name + '/' + hook,
                      source.read_text(encoding='utf-8').replace('$', '$$').rstrip('\n'), 'endef', '']
    lines.append('$(eval $(call BuildPackage,' + name + '))')
    return '\n'.join(lines) + '\n'

def build(project, out):
    cfg = load_config(project)
    if any(out.resolve().is_relative_to((project / folder).resolve()) for folder in ('root', 'control')):
        raise ValueError('Build output must stay outside payload and maintenance directories')
    if (project / 'root').is_symlink() or not (project / 'root').is_dir():
        raise ValueError('root/ must be a real payload directory')
    if (project / 'control').is_symlink():
        raise ValueError('control/ must not be a symlink')
    if (project / 'control').exists():
        for entry in (project / 'control').iterdir():
            if entry.name not in ('preinst', 'postinst', 'prerm', 'postrm'):
                raise ValueError('Helper control/ accepts maintenance hooks only; use plugin.json for metadata: ' + entry.name)
    files = []
    for src in sorted((project / 'root').rglob('*')):
        if src.is_symlink():
            raise ValueError('Symlinks require separate reviewed SDK packaging: ' + str(src))
        if src.is_dir():
            continue
        if not src.is_file():
            raise ValueError('Unsupported payload type: ' + str(src))
        rel = relative_path(src.relative_to(project / 'root').as_posix())
        data = src.read_bytes()
        if data.startswith(b'#!') and b'\r' in data.split(b'\n', 1)[0]:
            raise ValueError('Fix CRLF shebang in source; payload is not auto-converted: ' + rel)
        if data.startswith(b'\x7fELF'):
            if cfg['architecture'] == 'all':
                raise ValueError('ELF is not Architecture all: ' + rel)
            if len(data) < 20 or data[4:6] != b'\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
                raise ValueError('ELF is not little-endian ELF64 AArch64: ' + rel)
        files.append((rel, data, 0o755 if rel in cfg['executable_files'] else 0o644))
    if not files:
        raise ValueError('Empty payload')
    names = {p for p, _, _ in files}
    for path in cfg['executable_files'] + [p[1:] for p in cfg['conffiles']]:
        if path not in names:
            raise ValueError('Declared payload file is missing: ' + path)
    installed = sum(len(data) for _, data, _ in files)
    control = (f"Package: {cfg['package']}\nVersion: {cfg['full_version']}\nArchitecture: {cfg['architecture']}\n"
               f"Maintainer: {cfg['maintainer']}\nSection: {cfg['section']}\nPriority: optional\n"
               f"Depends: {', '.join(cfg['depends'])}\nLicense: {cfg['license']}\n"
               f"Installed-Size: {installed}\nDescription: {cfg['description']}\n").encode('utf-8')
    conffiles = ('\n'.join(cfg['conffiles']) + ('\n' if cfg['conffiles'] else '')).encode()
    controls = [('control', control, 0o644), ('conffiles', conffiles, 0o644)]
    for hook in ('preinst', 'postinst', 'prerm', 'postrm'):
        src = project / 'control' / hook
        if src.is_symlink():
            raise ValueError('Symlink maintenance hook')
        if src.exists():
            data = src.read_bytes()
            if b'\r' in data or not data.startswith(b'#!/bin/sh\n'):
                raise ValueError('Hook must use LF and #!/bin/sh: ' + hook)
            controls.append((hook, data, 0o755))
    ipk = archive([('debian-binary', b'2.0\n', 0o644),
                   ('control.tar.gz', archive(controls), 0o644),
                   ('data.tar.gz', archive(files), 0o644)])
    out.mkdir(parents=True, exist_ok=True)
    filename = f"{cfg['package']}_{cfg['full_version']}_{cfg['architecture']}.ipk"
    (out / filename).write_bytes(ipk)
    manifest = {'purpose': 'Local plugin build record; no cloud publishing',
        'package': cfg['package'], 'version': cfg['full_version'], 'architecture': cfg['architecture'],
        'depends': cfg['depends'], 'conffiles': cfg['conffiles'],
        'luci_route': cfg.get('luci_route'), 'file': filename, 'size': len(ipk),
        'source_bytes': installed, 'md5': hashlib.md5(ipk).hexdigest(),
        'sha256': hashlib.sha256(ipk).hexdigest(),
        'files': [{'path': p, 'bytes': len(d), 'mode': oct(m), 'sha256': hashlib.sha256(d).hexdigest()}
                  for p, d, m in files], 'device_validation': 'not_run_for_this_build'}
    if cfg.get('local_bundle', False):
        bundle = cfg['package'] + '_' + cfg['full_version'] + '_local.tar.gz'
        (out / bundle).write_bytes(archive([(filename, ipk, 0o644)]))
        manifest['local_import_candidate'] = bundle
    (out / 'package-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return cfg, manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = BASE if (BASE / 'plugin.json').exists() else BASE / 'example'
    parser.add_argument('--project', type=Path, default=default)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sdk-makefile', type=Path, help='Write a script/prebuilt-payload SDK recipe to a new path')
    args = parser.parse_args()
    project = args.project.resolve()
    out = (args.output or (BASE / 'dist' if project == BASE / 'example' else project / 'dist')).resolve()
    cfg, manifest = build(project, out)
    if args.sdk_makefile:
        text = sdk_text(project, cfg)
        target = args.sdk_makefile.resolve()
        if target.exists() and target.read_text(encoding='utf-8') != text:
            raise ValueError('Refusing to overwrite a different SDK recipe: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    print(json.dumps({'artifact': str(out / manifest['file']), 'bytes': manifest['size'],
                      'sha256': manifest['sha256']}, ensure_ascii=True))

if __name__ == '__main__':
    main()
