"""Run assertions and save a joint LQ/ZC/ZQO publication trace without touching their results."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sqlite3
import tempfile
import unittest
from publication import Catalog, bind, consume_notification
from test_publication import integrated
from scenarios import restriction

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'results'
ROOT=HERE.parents[3]


def run():
    checks=[]
    for member in ('zqo','lq','zc'):
        suite=unittest.TestLoader().discover(str(HERE.parents[1]/member/'prototype'),
                                           pattern='test_*.py',top_level_dir=str(HERE.parents[1]/member/'prototype'))
        stream=io.StringIO(); result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        checks.append({'module':member,'tests':result.testsRun,'success':result.wasSuccessful(),
                       'errors':len(result.errors),'failures':len(result.failures),'log':stream.getvalue()})
    if not all(x['success'] for x in checks):
        raise AssertionError(checks)
    with tempfile.TemporaryDirectory() as d:
        db=Catalog(Path(d)/'catalog.sqlite');s,q=integrated()
        v1=db.publish(s,q,expected=None,request_id='initial');p1=db.pin()
        first=db.query(q,p1)
        s2,q2=deepcopy(s),deepcopy(q)
        s2['airspace']['restrictions']=[restriction(box=[[45,35,0],[55,65,100]])]
        bind(s2,q2)
        v2=db.publish(s2,q2,expected=v1,request_id='no-fly')
        old=db.query(q,p1);new=db.query(q2)
        rechecks=[db.status(q2,e['from'],e['to']) for e in first['segments']]
        counts=db.counts()
        try:db.publish(s,q,expected=v2,request_id='failed-recovery',fail_at='before_commit')
        except RuntimeError:pass
        assert counts==db.counts() and db.current()==v2
        s3,q3=deepcopy(s2),deepcopy(q2)
        s3['airspace']['restrictions'][0]['state']='revoked';bind(s3,q3)
        v3=db.publish(s3,q3,expected=v2,request_id='revocation')
        revoked=db.query(q3)
        trace={'initial':first,'old_query_after_publication':old,'new_query':new,
               'old_segments_in_new_release':rechecks,'after_failed_publish_head':v2,
               'revoked_query':revoked,'outbox_counts':db.counts(),
               'late_notification_reconciled_to':consume_notification(db,v1,v1),
               'replayed_old_versions':db.pin(v1)['snapshot']['versions']}
        assert any(e['state']=='forbidden' for e in rechecks)
        assert old['freshness']=='stale' and new['freshness']=='current_at_check'
        assert revoked['metrics']['length_m']<new['metrics']['length_m']
    data={'executed_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
          'sqlite':sqlite3.sqlite_version,'platform':platform.system()+' '+platform.machine(),
          'baseline':'de2033a0b13296dcadd991e101a3bee3c1df4596',
          'scenario':'ZC synthetic geometry plus LQ compiled risk; UTC window 2026-11-04 00:00 to 00:10',
          'tests':checks,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [HERE/'publication.py',HERE/'test_publication.py',HERE/'evaluate.py',
                        HERE.parents[1]/'zc/prototype/planner.py',HERE.parents[1]/'lq/prototype/risk.py']},
          'trace':trace}
    OUT.mkdir(exist_ok=True)
    (OUT/'evaluation.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'tests':[{k:v for k,v in x.items() if k!='log'} for x in checks],
          'lengths_m':{k:trace[k]['metrics']['length_m'] for k in ('initial','new_query','revoked_query')},
          'old_route_forbidden_segments':sum(e['state']=='forbidden' for e in rechecks)},ensure_ascii=False))

if __name__=='__main__':run()
