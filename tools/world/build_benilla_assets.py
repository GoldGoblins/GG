"""Build Benilla's original format readers, without Bevy or a system install."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from build_benilla_ui import environment,TOOLS,ENGINE,PROJECT
SOURCE=PROJECT/'native/benilla-assets'
TARGET=ENGINE/'benilla-assets-build'
def source_digest():
    digest=hashlib.sha256()
    for path in sorted(SOURCE.rglob('*')):
        if path.is_file() and path.suffix in ('.rs','.h','.toml','.lock'):
            digest.update(path.relative_to(SOURCE).as_posix().encode());digest.update(path.read_bytes())
    return digest.hexdigest()
def run(args,**kwargs):
    env=environment();env['CARGO_TARGET_DIR']=str(TARGET)
    return subprocess.run([str(TOOLS/'cargo/bin/cargo'),*args],cwd=SOURCE,env=env,check=True,**kwargs)
def build():
    run(['build','--release','--locked','-p','gg-benilla-assets'])
    binary=TARGET/'release/libgg_benilla_assets.so';output=PROJECT/'backend/native/linux-x86_64';output.mkdir(parents=True,exist_ok=True)
    receipt={'schema':'gg.benilla-assets-build.v1','abi':1,'source_sha256':source_digest(),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'binary_bytes':binary.stat().st_size}
    with tempfile.TemporaryDirectory(prefix='.gg-benilla-assets-',dir=output) as directory:
        temporary=Path(directory);shutil.copy2(binary,temporary/binary.name)
        (temporary/'benilla-assets-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
        for name in (binary.name,'benilla-assets-build.json'):os.replace(temporary/name,output/name)
    print(json.dumps({'status':'PASS','binary_bytes':receipt['binary_bytes']}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-lock',action='store_true');parser.add_argument('--tests',action='store_true');args=parser.parse_args()
    if args.prepare_lock:run(['generate-lockfile'])
    elif args.tests:run(['test','--locked','--workspace'])
    else:build()
