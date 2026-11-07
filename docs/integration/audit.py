"""Read-only cross-module regressions. Exit 1 while a checked defect persists.

Use --owner YHT/LJ/ZQO to focus a handoff. SQLite files live in temporary folders.
Only --output explicitly writes a JSON result; member artifacts are never changed.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
for member in ('yht','lq','zc','zqo','lj'):
    sys.path.insert(0,str(ROOT/'docs/modules'/member/'prototype'))
from scenarios import fixture,bind
from planner import assess_segment,preflight,plan
from acceptance import validate_result
from publication import Catalog,prepare_risk
from yht_model import scene,seal
from export_zc import export_snapshot
from export_lq import profiles_from_scene
from risk import compile_profiles
from query import query_corridor

WINDOW={'start':'2026-11-05T08:05:00Z','end':'2026-11-05T08:15:00Z'}
BOUNDS=[[0,0,10],[450,450,120]]


def export(source):
    return bind(*export_snapshot(source,WINDOW,BOUNDS,[20,20,70],[420,420,70]))


def rejected_or_unknown(call):
    try:
        s,q=call()
        error=preflight(s,q)
        return bool(error),{'preflight':error,'complete':s['scene']['complete'],
                            'terrain_z':s['scene']['terrain_z']}
    except ValueError as exc:
        return True,{'rejected':type(exc).__name__,'reason':str(exc)}


def missing_risk():
    src=scene();src['buildings']=[];src['airspace']=[]
    src['ground_zones'][0].update(q=None,exposure_e=None,consequence_c=None)
    src=seal(src);observed={};passed=True
    for name in ('export_zc','export_lq'):
        try:
            if name=='export_zc':
                s,q=export(src)
            else:
                # Isolate the profile adapter: a guard added to export_zc must
                # not hide dropped profiles in export_lq.
                known=scene();known['buildings']=[];known['airspace']=[]
                s,q=export(seal(known))
                s,q=compile_profiles(s,q,profiles_from_scene(src))
            r=assess_segment(s,q,[20,20,70],[40,20,70])
            observed[name]={k:r.get(k) for k in ('state','reason','q_max','sources')}
            passed &= r['state']=='unknown'
        except ValueError as exc:
            observed[name]={'rejected':type(exc).__name__,'reason':str(exc)}
    return passed,observed


def incomplete_or_nonflat():
    observations={};passed=True
    for name in ('incomplete_coverage','nonflat_terrain'):
        src=scene()
        if name=='incomplete_coverage':src['coverage'][0]['complete']=False
        else:
            src['terrain']['flat']=False;src['terrain']['z']=20
            for p in src['terrain']['posts']:p['z']=20
        ok,obs=rejected_or_unknown(lambda:export(seal(src)))
        observations[name]=obs;passed &= ok
    return passed,observations


def ceiling_buffer():
    src=scene();src['buildings']=[];src=seal(src)
    a,b=[350,120,58],[400,120,58]
    r=query_corridor(src,a,b,5,WINDOW,src['versions'])
    s,q=export(src);other=assess_segment(s,q,a,b)
    return r['status']=='blocked',{'yht_status':r['status'],'zc_state':other['state'],
                                   'altitude_m':58,'radius_m':5,'ceiling_m':60}


def missing_versions():
    s,q=fixture();r=plan(s,q);r['versions']={}
    checked=validate_result(r,{})
    return checked['status']=='fail',checked


def stale_same_versions():
    s,q=fixture()
    with tempfile.TemporaryDirectory() as tmp:
        c=Catalog(Path(tmp)/'catalog.sqlite')
        first=c.publish(s,q,expected=None,request_id='first');pinned=c.pin()
        current=c.publish(s,q,expected=first,request_id='second')
        r=c.query(q,pinned);checked=validate_result(r,s['versions'])
    return checked['status']=='fail',{'freshness':r['freshness'],'release_id':first,
                                      'observed_head':current,'same_versions':r['versions']==s['versions'],
                                      'acceptance':checked}


def invalid_numbers():
    s,q=fixture();base=plan(s,q);observed={};passed=True
    for name,value in [('nan',float('nan')),('inf',float('inf')),('boolean',True)]:
        r=deepcopy(base);r['metrics']['risk_proxy']=value
        checked=validate_result(r,s['versions']);observed['risk_'+name]=checked
        passed &= checked['status']=='fail'
    r=deepcopy(base);r['elapsed_ms']=float('nan')
    checked=validate_result(r,s['versions']);observed['elapsed_nan']=checked
    passed &= checked['status']=='fail'
    return passed,observed


def q2_failure_versions():
    s,q=fixture()
    profiles=[{'id':'audit-risk','box':[[0,0,0],[100,100,100]],'source':'synthetic-audit',
               'periods':[{'valid':q['window'],'E':.2,'C':.2}]}]
    s,q=prepare_risk(s,q,profiles)
    with tempfile.TemporaryDirectory() as tmp:
        c=Catalog(Path(tmp)/'catalog.sqlite');c.publish(s,q,expected=None,request_id='first')
        q['window'][1]='2026-11-04T00:20:00Z'
        r=c.status(q,[0,0,20],[10,0,20])
    return r.get('versions')==s['versions'] and r.get('state')=='unknown',r


CASES=[
 ('YHT-01','YHT','未知风险须保持 unknown 或显式拒绝导出',missing_risk),
 ('YHT-02','YHT','覆盖不完整或不支持的非平地须拒绝或返回 unknown',incomplete_or_nonflat),
 ('YHT-03','YHT','高度58米加缓冲5米超过限高60米须 blocked',ceiling_buffer),
 ('LJ-01','LJ','双方缺少五类版本时验收必须 fail',missing_versions),
 ('LJ-02','LJ','旧发布即使组件版本相同也不能作为当前推荐验收通过',stale_same_versions),
 ('LJ-03','LJ','NaN/Infinity/布尔指标及非有限耗时必须 fail',invalid_numbers),
 ('ZQO-01','ZQO','已知发布的Q2失败结果保留五类版本',q2_failure_versions),
]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--owner',choices=['YHT','LJ','ZQO'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--baseline',default=None)
    args=parser.parse_args();records=[]
    for code,owner,expected,check in CASES:
        if args.owner and owner!=args.owner:continue
        try:passed,observed=check()
        except Exception as exc:passed,observed=False,{'unexpected_exception':type(exc).__name__,'reason':str(exc)}
        records.append({'id':code,'owner':owner,'passed':bool(passed),'expected':expected,'observed':observed})
    baseline=args.baseline
    if not baseline:
        proc=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
        baseline=proc.stdout.strip() if proc.returncode==0 else 'uncommitted-copy'
    output={'baseline':baseline,'cases':records,
            'failed_cases':sum(not r['passed'] for r in records),
            'source_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT/'docs/modules').rglob('*.py'))}}
    text=json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text, encoding="utf-8")
    for r in records:
        print(r['id'], 'PASS' if r['passed'] else 'FAIL', json.dumps(r['observed'],ensure_ascii=False))
    raise SystemExit(1 if output['failed_cases'] else 0)


if __name__=='__main__':main()
