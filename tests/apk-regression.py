"""Strict APK format regression; no network, device changes or script execution."""
from pathlib import Path
import hashlib
import io
import json
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

kit = Path(__file__).resolve().parents[1]
scratch = kit / 'work'
scratch.mkdir(exist_ok=True)
builder = runpy.run_path(str(kit/'tools/build-apk.py'))
reader = runpy.run_path(str(kit/'tools/inspect-apk.py'))
members = runpy.run_path(str(kit/'tools/inspect-ipk.py'))['members']
cases = []
def passed(name): cases.append({'case': name, 'status': 'pass'})
def reject(name, fn):
    try: fn()
    except (ValueError, OSError, tarfile.TarError, EOFError): passed(name)
    else: raise AssertionError('Expected rejection: '+name)

with tempfile.TemporaryDirectory(prefix='apk-regression-', dir=scratch) as temporary:
    work = Path(temporary)
    project = work/'project'
    shutil.copytree(kit/'example', project)
    cfg, manifest = builder['build'](project, work/'first')
    _, repeated = builder['build'](project, work/'repeat')
    assert manifest['sha256'] == repeated['sha256']
    passed('byte_reproducible_build')
    package = work/'first'/manifest['file']
    result = reader['inspect'](package)
    assert result['metadata']['arch'] == 'noarch' and result['metadata']['pkgver'] == '1.0.0-r1'
    assert result['depends'] == ['libc','luci-base']
    passed('native_metadata_architecture_version_and_dependencies')
    assert result['hooks'] == ['.post-deinstall','.post-install','.post-upgrade','.pre-deinstall']
    passed('apk_lifecycle_hook_mapping')
    control, data = reader['split_streams'](package.read_bytes(), 1048576)
    controls, _ = members(control,1048576)
    payload, inventory = members(data,1048576)
    original_info = controls['.PKGINFO'].decode()
    def forged(name, entries=None, control_text=None, checksum=True, suffix=b''):
        payload_blob = builder['layer'](entries or [(path,value,0o755 if value.startswith(b'#!') else 0o644,False) for path,value in payload.items()], file_checksums=checksum)
        text = control_text if control_text is not None else original_info
        text = '\n'.join('datahash = '+hashlib.sha256(payload_blob).hexdigest() if line.startswith('datahash = ') else line for line in text.splitlines())+'\n'
        out = work/(name+'.apk')
        out.write_bytes(builder['layer']([('.PKGINFO',text.encode(),0o644,False)],cut_eoa=True)+payload_blob+suffix)
        return out
    p = forged('missing-file-checksums', checksum=False)
    reject('reject_missing_embedded_per_file_checksum_despite_valid_datahash',lambda:reader['inspect'](p))
    p = forged('traversal',[('../escape',b'x',0o644,False)])
    reject('reject_parent_traversal_without_extraction',lambda:reader['inspect'](p))
    p = forged('absolute',[('/etc/escape',b'x',0o644,False)])
    reject('reject_absolute_payload_path',lambda:reader['inspect'](p))
    p = forged('duplicate',[('same',b'x',0o644,False),('same',b'y',0o644,False)])
    reject('reject_duplicate_payload_members',lambda:reader['inspect'](p))
    p = forged('duplicate-metadata',control_text=original_info+'pkgname = second\n')
    reject('reject_duplicate_metadata_key',lambda:reader['inspect'](p))
    p = forged('duplicate-dependency',control_text=original_info+'depend = libc\n')
    reject('reject_duplicate_dependency',lambda:reader['inspect'](p))
    p = forged('unknown-arch',control_text=original_info.replace('arch = noarch','arch = x86_64'))
    reject('reject_unverified_native_architecture',lambda:reader['inspect'](p))
    p = forged('bad-mode',[('worker',b'#!/bin/sh\nexit 0\n',0o644,False)])
    reject('reject_nonexecutable_shebang',lambda:reader['inspect'](p))
    p = forged('native',[('program',b'\x7fELF'+b'\0'*40,0o755,False)])
    reject('reject_ELF_in_noarch_helper',lambda:reader['inspect'](p))
    p = forged('trailing',suffix=b'trailing')
    reject('reject_trailing_data',lambda:reader['inspect'](p))
    p = work/'truncated.apk';p.write_bytes(package.read_bytes()[:-8])
    reject('reject_truncated_gzip',lambda:reader['inspect'](p))
    reject('enforce_expansion_limit',lambda:reader['inspect'](package,512))
    p = work/'apkv3.apk';p.write_bytes(b'ADB.'+b'\0'*50)
    reject('reject_APKv3_instead_of_misidentifying_as_APKv2',lambda:reader['inspect'](p))
    raw = package.read_bytes();p=work/'wrong-datahash.apk';p.write_bytes(builder['layer']([('.PKGINFO',original_info.replace('datahash = ','datahash = 0').encode(),0o644,False)],cut_eoa=True)+data)
    reject('reject_payload_digest_mismatch',lambda:reader['inspect'](p))
    asset=project/'root/www/test.png';asset.parent.mkdir(parents=True);asset.write_bytes(b'\x89PNG\r\n\0DATA\r\n')
    _, extra=builder['build'](project,work/'asset')
    _, asset_data=reader['split_streams']((work/'asset'/extra['file']).read_bytes(),1048576)
    assert members(asset_data,1048576)[0]['www/test.png']==asset.read_bytes()
    passed('binary_resource_bytes_preserved')
    config=json.loads((project/'plugin.json').read_text(encoding='utf-8'));config['architecture']='aarch64_cortex-a53';(project/'plugin.json').write_text(json.dumps(config),encoding='utf-8')
    reject('builder_requires_SDK_for_native_payloads',lambda:builder['build'](project,work/'native'))
    for version,expected in [('0.1.0','7ea7acb3c4262fba85f5af59ff6bc7cf6e6f605ee90d7459d32c73c0f887b8ff'),('0.2.0','cec8e8d6e741b6bd80f1146a7e0e4073064e88bf0bda76c7deb5defaf3029cf0')]:
        fixture=work/('fixture-'+version)
        shutil.copytree(kit/'validation/probe-source',fixture)
        metadata=json.loads((fixture/'plugin.json').read_text(encoding='utf-8'));metadata['version']=version
        (fixture/'plugin.json').write_text(json.dumps(metadata),encoding='utf-8')
        if version=='0.1.0':
            conf=fixture/'root/etc/config/nradio_compatprobe'
            conf.write_bytes(conf.read_bytes().replace(b" option interval '600'",b"\toption interval '300'"))
        _, rebuilt=builder['build'](fixture,work/('fixture-out-'+version))
        assert rebuilt['sha256']==expected, (version,rebuilt['sha256'],expected)
        passed('rebuild_exact_device_tested_artifact_'+version)
    generated=work/'generated'
    subprocess.run([sys.executable,str(kit/'tools/new-plugin.py'),'--id','native-demo','--name','Native Demo','--output',str(generated)],check=True,capture_output=True)
    subprocess.run([sys.executable,str(generated/'tools/build-apk.py')],cwd=generated,check=True,capture_output=True)
    subprocess.run([sys.executable,str(generated/'tools/inspect-apk.py'),str(generated/'dist/luci-app-native-demo-0.1.0-r1.apk')],cwd=generated,check=True,capture_output=True)
    assert (generated/'AGENTS.md').exists()
    passed('generated_project_self_contained_apk_cli_and_agent_guide')

report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Local APK v2 helper regression only; no device install','cases':cases,
        'tool_sha256':{name:hashlib.sha256((kit/'tools'/name).read_bytes()).hexdigest() for name in ('build-apk.py','inspect-apk.py','device-dry-run-apk.sh')}}
(kit/'apk-tool-validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS',len(cases),'APK regressions; no device operation performed')
