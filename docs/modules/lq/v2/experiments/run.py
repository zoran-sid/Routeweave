"""LQ database governance, operation C, privacy and predecessor review evidence.

python3 -B docs/modules/lq/v2/experiments/run.py --output /tmp/lq-v2.json
"""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import tempfile
import time
import unittest
import governance as gov
from test_governance import GovernanceTest

cat=gov.cat
HERE=Path(__file__).resolve().parent


def execute():
    stream=io.StringIO()
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GovernanceTest))
    if not tests.wasSuccessful(): raise RuntimeError(stream.getvalue())
    records={'tests':{'run':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'log':stream.getvalue()}}
    with tempfile.TemporaryDirectory(prefix='lq-governance-') as tmp:
        path=Path(tmp)/'lq.db';cat.initialize(path);c=cat.connect(path);gov.seed(c)
        payload=cat.fixture()
        gov.request_release(c,payload,'R0',None,'AUTHOR','approved-R0');gov.approve(c,'approved-R0','REVIEWER')
        gov.publish_approved(c,payload,'R0',None,'approved-R0','REVIEWER')
        changed=cat.changed(payload)
        gov.request_release(c,changed,'R1','R0','AUTHOR','approved-R1');gov.approve(c,'approved-R1','REVIEWER')
        gov.publish_approved(c,changed,'R1','R0','approved-R1','REVIEWER')
        started=time.perf_counter_ns();gov.compile_dataset(c,'R0','D0');zones=gov.compile_dataset(c,'R1','D1')
        records['compile']={'two_datasets_elapsed_ms':(time.perf_counter_ns()-started)/1e6,
                           'zones_per_dataset':len(zones),'periods':12,'window':list(cat.WIN),
                           'definition':'single demonstration, not a repeated performance benchmark'}
        gov.lineage(c,'D0');gov.lineage(c,'D1')
        # Explicit temporary consumer contract; no production ZC table is silently added.
        c.executescript('''CREATE TEMP TABLE query_run(query_id TEXT PRIMARY KEY, release_id TEXT NOT NULL,
             actor_id TEXT NOT NULL,window_lo TEXT NOT NULL,window_hi TEXT NOT NULL);
        CREATE TEMP TABLE route_segment_source(query_id TEXT NOT NULL,segment_no INTEGER NOT NULL,
             component_id TEXT NOT NULL,zone_rid INTEGER NOT NULL,dataset_id TEXT NOT NULL,
             PRIMARY KEY(query_id,segment_no,zone_rid));''')
        task=('2026-11-05T08:05:00Z','2026-11-05T08:15:00Z')  # 10-minute task inside the dataset window
        c.execute('INSERT INTO query_run VALUES(?,?,?,?,?)',('Q1','R1','DISPATCH',*task))
        for i,z in enumerate(zones[:2]): c.execute('INSERT INTO route_segment_source VALUES(?,?,?,?,?)',('Q1',i+1,'R0:exposure',z['rid'],'D1'))
        sql=(HERE/'op_c.sql').read_text(encoding="utf-8")
        result=cat.rows(c,sql,{'query_id':'Q1'})
        plan=cat.rows(c,'EXPLAIN QUERY PLAN '+sql,{'query_id':'Q1'})
        assert len(result)==2 and all(r['release_id']=='R1' and r['owner_release_id']=='R0' and r['risk_model_id']=='lq-risk-v1' for r in result)
        c.execute("UPDATE query_run SET window_hi='2027-06-01T00:00:00Z' WHERE query_id='Q1'")  # beyond dataset window
        mismatched=cat.rows(c,sql,{'query_id':'Q1'})
        assert mismatched==[]
        c.execute('UPDATE query_run SET window_hi=? WHERE query_id=?',(task[1],'Q1'))
        records['trace_window_mismatch_filtered']=True
        records['trace_window_rule']={'task_window':list(task),'dataset_window':list(cat.WIN),
            'rule':'dataset window contains task window (LQ-V2-02)','outside_window_rows':0}
        records['operation_C']={'sql':sql,'query_fixture':cat.rows(c,'SELECT * FROM query_run'),
            'segment_fixture':cat.rows(c,'SELECT * FROM route_segment_source'),
            'result':result,'explain_query_plan':plan,'passed':True,
            'boundary':'trusted same-organization internal trace; external callers need actor/org checks before execution'}
        affected_sql="""WITH RECURSIVE affected(kind,id) AS (
          VALUES('source',:source) UNION SELECT l.to_kind,l.to_id FROM lineage_edge l
          JOIN affected a ON l.from_kind=a.kind AND l.from_id=a.id)
          SELECT d.dataset_id,d.release_id,d.component_id,d.risk_model_id
          FROM affected a JOIN risk_dataset d ON a.kind='dataset' AND d.dataset_id=a.id ORDER BY d.dataset_id"""
        affected=cat.rows(c,affected_sql,{'source':'SRC-SYN'})
        assert [r['dataset_id'] for r in affected]==['D0','D1']
        records['invalidation']={'sql':affected_sql,'result':affected,'meaning':'candidate derivations to rebuild/revalidate, not proof an entire route is forbidden'}
        records['access']={}
        for actor in ('DISPATCH','OPER','REVIEWER','SYS','OTHER','OFF'):
            records['access'][actor]={'summary':gov.read_audited(path,actor,'SELECT * FROM v_exposure_summary'),
                                     'detail_rows':len(gov.read_audited(path,actor,'SELECT * FROM v_exposure_detail'))}
        try: gov.read_audited(path,'DISPATCH','SELECT * FROM exposure_zone')
        except sqlite3.DatabaseError as e: records['raw_table_denied']=str(e)
        try:
            gov.request_release(c,payload,'R2','R1','AUTHOR','self');gov.approve(c,'self','AUTHOR')
        except sqlite3.IntegrityError as e: records['self_approval_denied']=str(e)
        periods={'G-0':[{'valid':[cat.WIN[0],'2026-06-01T00:00:00Z'],'E':.5,'C':.4}]}
        gov.compile_dataset(c,'R1','GAP',periods,seal=False)
        try: c.execute("UPDATE risk_dataset SET state='validated' WHERE dataset_id='GAP'")
        except sqlite3.IntegrityError as e:
            cat.insert(c,'quality_check',dict(check_id='gap-failure',dataset_id='GAP',rule='temporal_coverage',result='fail',checked_at=gov.AT,actor_id='REVIEWER',detail=json.dumps({'error':str(e)})))
            records['gap_rejected']={'reason':str(e),'quality':dict(c.execute("SELECT * FROM quality_check WHERE check_id='gap-failure'").fetchone())}
        try: c.execute("UPDATE risk_model SET formula='tampered' WHERE risk_model_id='lq-risk-v1'")
        except sqlite3.IntegrityError as e: records['LQ-V2-01']={'passed':True,'rejection':str(e)}
        reopened=cat.connect(path)
        assert cat.snapshot(reopened,'R0')['layers']==payload
        reopened.close()
        records['audit']=cat.rows(c,'SELECT * FROM audit_event ORDER BY rowid')
        records['integrity']={'check':c.execute('PRAGMA integrity_check').fetchone()[0],
                              'foreign_key_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),
                              'history_reopen_unchanged':True}
        # Privacy illustration: 200m-cell summaries vs raw zone geometry, no anonymity claim.
        records['privacy']={'raw_rows':len(zones),'display_rows_per_release':3,'display_grid_m':200,'min_zones_per_cell':2,
                            'retained_columns':['release_id','cell_x','cell_y','zone_count','display_proxy'],
                            'warning':'display proxy is rounded and must never replace planning inputs; no formal anonymity guarantee'}
        c.close()
    return records


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    evidence=execute()
    paths=[*HERE.glob('*.py'),HERE/'op_c.sql',cat.SCHEMA/'schema.sql',cat.SCHEMA/'test_governance_v2.py',Path(cat.__file__),cat.SCHEMA/'fixtures.py',cat.ROOT/'docs/modules/lq/prototype/risk.py']
    evidence.update(environment={'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=cat.ROOT,text=True).strip(),
        'source_sha256':{str(f.relative_to(cat.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}},
        synthetic=True,parameters={'buildings':25,'terrain_posts':121,'exposure_zones':6,'published_releases':2,
                                   'risk_datasets':2,'temporary_queries':1,'temporary_segments':2})
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2,allow_nan=False)+'\n', encoding="utf-8")
    print(json.dumps({'tests':evidence['tests']['run'],'operation_C_rows':len(evidence['operation_C']['result']),
          'invalidation_datasets':len(evidence['invalidation']['result']),'integrity':evidence['integrity']},ensure_ascii=False))

if __name__=='__main__':main()
