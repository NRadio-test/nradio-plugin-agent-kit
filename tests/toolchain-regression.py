from pathlib import Path
import hashlib
import io
import json
import runpy
import shutil
import subprocess
import sys
import tarfile

import atexit
import tempfile
from datetime import datetime, timezone
kit = Path(__file__).resolve().parents[1]
scratch = (Path.cwd() / 'work').resolve()
scratch.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='nradio-toolchain-', dir=scratch)).resolve()
assert work.is_relative_to(scratch)
def cleanup():
    assert work.resolve().is_relative_to(scratch)
    shutil.rmtree(work)
atexit.register(cleanup)
builder = runpy.run_path(str(kit / 'tools/build.py'))
inspector = runpy.run_path(str(kit / 'tools/inspect-ipk.py'))
build, archive, inspect = builder['build'], builder['archive'], inspector['inspect']
results = []

def record(name):
    results.append({'case': name, 'status': 'pass'})

def fails(name, action):
    try:
        action()
    except (ValueError, OSError, tarfile.TarError, EOFError):
        record(name)
    else:
        raise AssertionError('Expected rejection: ' + name)

def entries(blob):
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as tar:
        return {m.name.removeprefix('./'): tar.extractfile(m).read() for m in tar if m.isfile()}

cfg, meta = build(kit / 'example', work / 'baseline-a')
pkg = work / 'baseline-a' / meta['file']
_, repeat = build(kit / 'example', work / 'baseline-b')
assert meta['sha256'] == repeat['sha256'] == '3f7292861bf27036d9a7e02425c67d64a7f4a991e78af5ef703dcf227f6aeff1'
record('baseline_rebuild_is_byte_identical_to_device_preflight_artifact')
assert inspect(pkg)['status'] == 'pass'
record('baseline_host_inspection')

target = work / 'link-monitor'
if not target.exists():
    run = subprocess.run([sys.executable, str(kit / 'tools/new-plugin.py'), '--id', 'link-monitor',
                          '--name', '链路 "监测"', '--version', '0.2.0', '--output', str(target)],
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    assert run.returncode == 0, run.stderr
new_cfg = json.loads((target / 'plugin.json').read_text(encoding='utf-8'))
assert new_cfg['package'] == 'luci-app-link-monitor'
assert new_cfg['luci_route'] == 'nradioadv/system/link_monitor'
for folder in ('root', 'control'):
    for f in (target / folder).rglob('*'):
        if f.is_file():
            assert 'nradio_demo' not in f.as_posix() and 'nradio-demo' not in f.as_posix()
            assert b'nradio_demo' not in f.read_bytes() and b'nradio-demo' not in f.read_bytes()
controller = target / 'root/usr/lib/lua/luci/controller/nradio_adv/link_monitor.lua'
assert json.dumps('链路 "监测"', ensure_ascii=False) in controller.read_text(encoding='utf-8')
assert '$$IPKG_INSTROOT' in (target / 'Makefile').read_text(encoding='utf-8')
record('new_project_identity_paths_unicode_title_and_sdk_hook_dollars')
prior = (target / 'plugin.json').read_bytes()
run = subprocess.run([sys.executable, str(kit / 'tools/new-plugin.py'), '--id', 'link-monitor', '--name', 'Other',
                      '--output', str(target)], capture_output=True)
assert run.returncode != 0 and (target / 'plugin.json').read_bytes() == prior
record('generator_refuses_existing_project')
_, generated = build(target, target / 'dist')
assert inspect(target / 'dist' / generated['file'])['control']['Package'] == 'luci-app-link-monitor'
record('generated_project_build_and_host_inspection')

png = b'\x89PNG\r\n\x1a\n\x00\x00BINARY\r\nRESOURCE\x00'
asset = target / 'root/www/luci-static/link-monitor/icon.png'
asset.parent.mkdir(parents=True, exist_ok=True)
asset.write_bytes(png)
_, with_asset = build(target, target / 'dist')
outer = entries((target / 'dist' / with_asset['file']).read_bytes())
assert entries(outer['data.tar.gz'])['www/luci-static/link-monitor/icon.png'] == png
record('binary_png_crlf_and_nul_bytes_preserved_exactly')

def project_variant(label, mutate):
    destination = work / label
    if not destination.exists():
        shutil.copytree(kit / 'example', destination)
    cfg = json.loads((destination / 'plugin.json').read_text(encoding='utf-8'))
    mutate(destination, cfg)
    (destination / 'plugin.json').write_text(json.dumps(cfg), encoding='utf-8')
    return destination

crlf = project_variant('crlf', lambda p,c: (p/'root/usr/libexec/nradio-demo/worker.sh').write_bytes(b'#!/bin/sh\r\nexit 0\r\n'))
fails('builder_rejects_crlf_shebang_without_silent_conversion', lambda: build(crlf, crlf/'dist'))
elf = b'\x7fELF' + b'\x02\x01' + b'\x00'*12 + (183).to_bytes(2,'little')
native = project_variant('native-all', lambda p,c: (p/'root/usr/libexec/nradio-demo/program').write_bytes(elf))
fails('builder_rejects_native_elf_labelled_all', lambda: build(native, native/'dist'))
missing = project_variant('missing-config', lambda p,c: c.update(conffiles=['/etc/config/does_not_exist']))
fails('builder_rejects_missing_conffile', lambda: build(missing, missing/'dist'))
malformed = project_variant('metadata-newline', lambda p,c: c.update(maintainer='name\nPackage: wrong'))
fails('builder_rejects_control_field_injection', lambda: build(malformed, malformed/'dist'))
fails('builder_rejects_output_inside_payload', lambda: build(kit/'example', kit/'example/root/dist'))
no_conffiles = project_variant('no-conffiles', lambda p,c: c.update(conffiles=[]))
_, empty_cfg_meta = build(no_conffiles, no_conffiles/'dist')
assert inspect(no_conffiles/'dist'/empty_cfg_meta['file'])['status'] == 'pass'
record('empty_conffiles_list_builds_and_inspects')
extra_control = project_variant('extra-control', lambda p,c: (p/'control/control').write_text('Package: wrong\n'))
fails('builder_rejects_silently_ignored_control_metadata', lambda: build(extra_control, extra_control/'dist'))
def wrong_elf(p,c):
    c['architecture'] = 'aarch64_cortex-a53'
    (p/'root/usr/libexec/nradio-demo/program').write_bytes(elf[:18] + (62).to_bytes(2,'little'))
wrong_native = project_variant('native-wrong-machine', wrong_elf)
fails('builder_rejects_x86_elf_under_aarch64_metadata', lambda: build(wrong_native, wrong_native/'dist'))

base_outer = entries(pkg.read_bytes())
base_controls = entries(base_outer['control.tar.gz'])
def evil_package(label, data_entries=None, control_entries=None, raw_data=None):
    control = control_entries or [(n,b,0o755 if n in ('preinst','postinst','prerm','postrm') else 0o644)
                                  for n,b in base_controls.items()]
    blob = archive([('debian-binary',b'2.0\n',0o644),('control.tar.gz',archive(control),0o644),
                    ('data.tar.gz', raw_data if raw_data is not None else archive(data_entries),0o644)])
    path = work / (label + '.ipk')
    path.write_bytes(blob)
    return path

for label, name in [('parent-traversal','../escape'), ('absolute-path','/tmp/escape'),
                    ('backslash-path','etc\\escape')]:
    p = evil_package(label, [(name,b'x',0o644)])
    fails('inspector_rejects_' + label, lambda p=p: inspect(p))
p = evil_package('duplicates', [('etc/config/nradio_demo',b'x',0o644),('etc/config/nradio_demo',b'y',0o644)])
fails('inspector_rejects_duplicate_members', lambda: inspect(p))
stream = io.BytesIO()
with tarfile.open(fileobj=stream,mode='w:gz') as tf:
    link = tarfile.TarInfo('./link'); link.type=tarfile.SYMTYPE; link.linkname='/etc/shadow'; tf.addfile(link)
p = evil_package('symlink',raw_data=stream.getvalue())
fails('inspector_rejects_links_without_extraction', lambda: inspect(p))
bad_control = [(n,(b + b'Package: injected\n') if n=='control' else b,0o755 if n in ('postinst','prerm','postrm') else 0o644)
               for n,b in base_controls.items()]
p = evil_package('duplicate-control', [('etc/config/nradio_demo',b'x',0o644)], bad_control)
fails('inspector_rejects_duplicate_control_fields',lambda: inspect(p))
p = evil_package('missing-conffile', [('somewhere',b'x',0o644)])
fails('inspector_rejects_missing_conffile',lambda: inspect(p))
p = evil_package('mode', [('etc/config/nradio_demo',b'x',0o644),('usr/bin/run',b'#!/bin/sh\nexit 0\n',0o644)])
fails('inspector_rejects_non_executable_shebang',lambda: inspect(p))
p = evil_package('elf-all', [('etc/config/nradio_demo',b'x',0o644),('usr/bin/run',elf,0o755)])
fails('inspector_rejects_native_elf_labelled_all',lambda: inspect(p))
p = evil_package('expanded-limit', [('etc/config/nradio_demo',b'A'*32768,0o644)])
fails('inspector_enforces_expanded_size_limit',lambda: inspect(p,8192))

report = {'observed_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Local Python tooling and archive regression; no device install performed',
          'cases':results,'tool_sha256':{name:hashlib.sha256((kit/'tools'/name).read_bytes()).hexdigest()
                                       for name in ('build.py','new-plugin.py','inspect-ipk.py')},
          'device_preflight_sample_unchanged':True,
          'sample_sha256':meta['sha256']}
(kit/'construction-tool-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'PASS {len(results)} construction/inspection regressions; sample bytes unchanged; no new device installation claimed')
