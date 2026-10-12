"""Build the original protocol/SRP client beside the existing asset bridge."""
import hashlib,json,os,shutil,tempfile
from pathlib import Path
from build_benilla_assets import run,source_digest,TARGET,PROJECT

def build():
    run(['build','--release','--locked','-p','gg-benilla-client'])
    source=TARGET/'release/libgg_benilla_client.so';output=PROJECT/'backend/native/linux-x86_64'
    receipt={'schema':'gg.benilla-client-build.v1','abi':1,'source_sha256':source_digest(),
             'binary_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_bytes':source.stat().st_size}
    with tempfile.TemporaryDirectory(prefix='.gg-benilla-client-',dir=output) as directory:
        temporary=Path(directory);shutil.copy2(source,temporary/source.name)
        (temporary/'benilla-client-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
        for name in (source.name,'benilla-client-build.json'):os.replace(temporary/name,output/name)
    print(json.dumps({'status':'PASS','binary_bytes':receipt['binary_bytes']}))

if __name__=='__main__':build()
