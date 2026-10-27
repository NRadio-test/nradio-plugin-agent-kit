#!/usr/bin/env python3
"""Create a NEW project from the local example; never overwrites an existing path."""
import argparse
import json
from pathlib import Path
import re
import runpy
import shutil

KIT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True, help='Lowercase slug, for example link-monitor')
    parser.add_argument('--name', required=True)
    parser.add_argument('--version', default='0.1.0')
    parser.add_argument('--maintainer', default='Project maintainer')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', args.id) or len(args.id) > 40:
        raise ValueError('id must be a lowercase hyphenated slug of at most 40 characters')
    if not args.name or len(args.name) > 80 or any(ord(c) < 32 for c in args.name):
        raise ValueError('Invalid display name')
    if any(c in args.name for c in '$#'):
        raise ValueError('This SDK scaffold profile does not accept Make expression/comment characters in display name')
    target = args.output.resolve()
    if target.exists():
        raise FileExistsError('Target already exists; not overwritten: ' + str(target))
    template = KIT / 'example'
    cfg = json.loads((template / 'plugin.json').read_text(encoding='utf-8'))
    slug, lua_id = args.id, args.id.replace('-', '_')
    cfg.update({'package': 'luci-app-' + slug, 'version': args.version, 'release': 1,
                'title': args.name, 'maintainer': args.maintainer,
                'description': args.name + ' plugin', 'uci_name': lua_id, 'service_name': slug,
                'luci_route': 'nradioadv/system/' + lua_id,
                'conffiles': ['/etc/config/' + lua_id],
                'executable_files': ['etc/init.d/' + slug, 'usr/libexec/' + slug + '/worker.sh']})
    # Validate metadata in memory before creating project files.
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+~_-]*', args.version):
        raise ValueError('Invalid version')
    if not args.maintainer or any(ord(c) < 32 for c in args.maintainer):
        raise ValueError('Invalid maintainer')
    target.mkdir(parents=True)
    for tree in ('root', 'control'):
        for source in sorted((template / tree).rglob('*')):
            if source.is_symlink():
                raise ValueError('Unexpected symlink in trusted template')
            if not source.is_file():
                continue
            rel = source.relative_to(template).as_posix().replace('nradio_demo', lua_id).replace('nradio-demo', slug)
            data = source.read_bytes()
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                text = None
            if text is not None and '\0' not in text:
                text = text.replace('nradio_demo', lua_id).replace('nradio-demo', slug)
                text = text.replace('"NRadio Demo"', json.dumps(args.name, ensure_ascii=False))
                data = text.encode('utf-8')
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    (target / 'plugin.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (target / 'tools').mkdir()
    for name in ('build.py', 'inspect-ipk.py', 'device-dry-run.sh', 'syntax-check.lua', 'preflight.sh',
                 'build-apk.py', 'inspect-apk.py', 'device-dry-run-apk.sh'):
        shutil.copy2(KIT / 'tools' / name, target / 'tools' / name)
    shutil.copy2(KIT / 'LICENSE', target / 'LICENSE')
    shutil.copy2(KIT / 'AGENTS.md', target / 'AGENTS.md')
    builder = runpy.run_path(str(KIT / 'tools/build.py'))
    config = builder['load_config'](target)
    (target / 'Makefile').write_text(builder['sdk_text'](target, config), encoding='utf-8')
    print(json.dumps({'project': str(target), 'package': cfg['package'], 'route': cfg['luci_route'],
                      'next': 'ultra 3.0: implement root/, then python tools/build-apk.py and inspect-apk.py; legacy IPK is not a compatible default',
                      'template_policy': 'Minimal example only; complete product lifecycle before release'}, ensure_ascii=True))

if __name__ == '__main__':
    main()
