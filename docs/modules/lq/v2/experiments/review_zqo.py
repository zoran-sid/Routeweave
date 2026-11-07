"""Read-only predecessor probes. Exit 1 while provenance validation is incomplete."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import tempfile
import governance as gov
cat=gov.cat


def run():
    observed=[]
    for name in ('empty_upstream_versions','empty_compiler_version'):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'probe.db';cat.initialize(path);c=cat.connect(path)
            prov=cat.provenance()
            if name=='empty_upstream_versions': prov['source_versions']={k:'' for k in cat.LAYERS}
            else: prov['compiler_version']=''
            try:
                cat.publish(c,cat.fixture(),release_id='probe',expected=None,request_id=name,provenance=prov)
                r={'case':name,'expected':'reject invalid provenance','actual':'accepted',
                   'provenance':cat.snapshot(c)['manifest']['provenance'],'passed':False}
            except (ValueError,sqlite3.IntegrityError) as e:
                r={'case':name,'actual':'rejected','reason':str(e),'passed':True}
            observed.append(r);c.close()
    return observed


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    cases=run()
    paths=[Path(__file__),Path(cat.__file__),cat.SCHEMA/'schema.sql']
    result={'issue':'ZQO-V2-01','cases':cases,'synthetic':True,
       'environment':{'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),
       'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=cat.ROOT,text=True).strip(),
       'source_sha256':{str(p.relative_to(cat.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for c in cases: print(c['case'],c['actual'])
    raise SystemExit(any(not c['passed'] for c in cases))
