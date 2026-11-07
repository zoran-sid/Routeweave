"""Rebuild auditable synthetic results from repository root."""
import csv, json
from datetime import datetime, timezone
from pathlib import Path
from risk import fixture, compile_profiles, bind, plan, evaluate, can_publish
from test_risk import region, T0, T5

out=Path(__file__).resolve().parents[1]/'results'
out.mkdir(exist_ok=True)
rows=[]; results=[]
for weight in (0,2,8):
    s,q=fixture(); s,q=compile_profiles(s,q,region())
    s['planner_config']['lambda_risk']=weight; s,q=bind(s,q)
    a,d=plan(s,q),plan(s,q,'dijkstra')
    assert a['status']==d['status']=='feasible'
    assert abs(a['metrics']['cost']-d['metrics']['cost'])<1e-9
    rows.append({'lambda':weight,**a['metrics']})
    results.append({'lambda':weight,'astar':a,'dijkstra':d})
s,q=fixture()
checks={}
for name,p in [('commercial',region()),('hard',region(.95,1)),('unknown',region(None)),('missing',[])]:
    checks[name]=evaluate(s,q,p,(30,50,70),(70,50,70))
p=region(); p[0]['periods'][0]['valid']=[T0,T5]
checks['time_gap']=evaluate(s,q,p,(30,50,70),(70,50,70))
# A complete high-risk wall makes the finite domain infeasible, for any lambda.
p=region(1,1); p[0]['box']=[[45,0,0],[55,100,100]]
s,q=compile_profiles(s,q,p); checks['hard_wall']=plan(s,q)
assert checks['hard_wall']['status']=='infeasible'
payload={'executed_at':datetime.now(timezone.utc).isoformat(),'scenario':'synthetic-lq-v1',
         'baseline':'starter-v0','comparisons':results,'segment_checks':checks,
         'governance_policy_simulation':{'self_publish_denied':not can_publish('lq','lq','safety_reviewer'),
                                       'dispatcher_publish_denied':not can_publish('dispatcher','lq','dispatcher'),
                                       'independent_review_allowed':can_publish('reviewer','lq','safety_reviewer')}}
(out/'evaluation.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
with (out/'tradeoffs.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n"); w.writeheader(); w.writerows(rows)
print(json.dumps({'tradeoffs':rows,'states':{k:v.get('state',v.get('status')) for k,v in checks.items()}},indent=2))
