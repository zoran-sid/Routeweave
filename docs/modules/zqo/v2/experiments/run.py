"""Reproduce operation B evidence and paired 10/100/1000 release storage experiments.

python3 -B docs/modules/zqo/v2/experiments/run.py --output /tmp/zqo-v2.json
Default workload: 25 buildings, 121 terrain posts, 3 restrictions, 6 exposure zones.
Every new release changes one restriction's height; all other layers are unchanged.
"""
import argparse
import hashlib
import io
import json
import platform
import sqlite3
import statistics
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import catalog as cat
from test_catalog import CatalogTest


def environment():
    paths = [Path(__file__), Path(__file__).with_name('catalog.py'), Path(__file__).with_name('test_catalog.py'),
             cat.SCHEMA/'schema.sql', cat.SCHEMA/'fixtures.py']
    return {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version, 'platform': platform.platform(),
            'git_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=cat.ROOT,text=True).strip(),
            'working_tree_source_sha256': {str(p.relative_to(cat.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def benchmark(mode, counts):
    payload = cat.fixture()
    results = []; semantic_digests = {}
    with tempfile.TemporaryDirectory(prefix='zqo-storage-') as tmp:
        path = Path(tmp)/'catalog.db'; cat.initialize(path); c = cat.connect(path)
        previous = None; start = time.perf_counter()
        for i in range(max(counts)):
            rid = f'r{i:04d}'
            data = payload if i == 0 else cat.changed(payload, i)
            cat.publish(c,data,request_id='q'+str(i),release_id=rid,expected=previous,
                        provenance=cat.provenance(),mode=mode,timestamp='2026-11-06T10:00:00Z')
            previous=rid
            if i+1 not in counts: continue
            write_seconds = time.perf_counter()-start
            checkpoint = tuple(c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
            assert checkpoint[0]==0
            # Reopen the connection; OS page cache is not flushed. One warmup, then 30 reads.
            c.close(); c=cat.connect(path)
            ids = ['r0000', f'r{i//2:04d}', rid]
            cat.snapshot(c,ids[0])
            latencies=[]; sizes=[]
            for j in range(30):
                target = ids[j%3]
                t=time.perf_counter_ns(); snap=cat.snapshot(c,target)
                serialized=cat.canonical(snap['layers'])
                latencies.append((time.perf_counter_ns()-t)/1000)
                sizes.append(len(serialized.encode()))
                h=cat.digest(snap['layers'])
                assert semantic_digests.setdefault(target,h)==h
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            wal=Path(str(path)+'-wal')
            result={'mode':mode,'releases':i+1,'db_bytes':path.stat().st_size,
                    'wal_bytes_after_checkpoint':wal.stat().st_size if wal.exists() else 0,
                    'components':c.execute('SELECT count(*) FROM layer_component').fetchone()[0],
                    'feature_rows':c.execute('SELECT count(*) FROM feature').fetchone()[0],
                    'terrain_posts':c.execute('SELECT count(*) FROM terrain_post').fetchone()[0],
                    'publish_elapsed_seconds':round(write_seconds,4),'read_samples':30,'historical_release_ids':ids,
                    'history_export_median_us':round(statistics.median(latencies),2),
                    'history_export_p95_us':round(sorted(latencies)[28],2),
                    'export_bytes_mean':round(statistics.mean(sizes)),
                    'integrity_check':'ok','foreign_key_violations':0}
            results.append(result); print(json.dumps(result),flush=True)
            # Exclude the benchmark reads/checks from subsequent cumulative write timings.
            start = time.perf_counter()-write_seconds
        c.close()
    return results, semantic_digests


def review_yht():
    """Known SQL bypasses: report real outcomes, do not patch YHT-owned tables."""
    c=cat.fx.connect(); c.row_factory=sqlite3.Row; cat.fx.base(c)
    cat.fx.create_release(c,'published'); cat.fx.add_layers(c,'published')
    cat.fx.add_feature(c,1,'published','B-header','building')
    cat.fx.publish(c,'published')
    cat.fx.create_release(c,'draft'); cat.fx.add_building(c,2,'draft','B-move',(0.,0.,5.,5.),0.,10.)
    probes=[('YHT-V2-05','draft feature can move to published owner',
             "UPDATE feature SET release_id='published' WHERE rid=2"),
            ('YHT-V2-05','subtype inserted after publication',
             "INSERT INTO building (rid,footprint_wkt,solid_wkt,bbox_min_x,bbox_min_y,bbox_max_x,bbox_max_y,base_z,top_z,height_m,footprint_source,height_source,height_method,is_landmark) VALUES(1,'p','s',0,0,1,1,0,10,10,'SRC-SYN','SRC-SYN','assumed',0)"),
            ('YHT-V2-05','terrain inserted after publication',
             "INSERT INTO terrain_surface (release_id,terrain_id,surface_type,bounds_wkt,post_spacing_m,vertical_datum,flat,min_z,max_z,source_id,quality,valid_lo,valid_hi,checksum) VALUES('published','late','grid','p',1,'local-z0',1,0,0,'SRC-SYN','assumed','2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','"+'0'*64+"')"),
            ('YHT-V2-06','source metadata update accepted',"UPDATE source SET license='changed' WHERE source_id='SRC-SYN'"),
            ('LQ-V2-01','risk model formula update accepted',"UPDATE risk_model SET formula='different' WHERE risk_model_id='lq-risk-v1'")]
    evidence=[]
    for issue,label,sql in probes:
        c.execute('SAVEPOINT probe')
        try:
            c.execute(sql); outcome='accepted'
        except sqlite3.IntegrityError as e:
            outcome='rejected: '+str(e)
        finally:
            c.execute('ROLLBACK TO probe');c.execute('RELEASE probe')
        evidence.append({'issue':issue,'case':label,'sql':sql,'expected':'rejected','actual':outcome,'pass':outcome.startswith('rejected')})
    c.close()
    return evidence


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path(__file__).parent/'results/transactions-storage.json')
    ap.add_argument('--counts',type=int,nargs='+',default=[10,100,1000]);args=ap.parse_args()
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CatalogTest))
    if not result.wasSuccessful():
        raise RuntimeError(stream.getvalue())
    shared,sd=benchmark('shared',args.counts);full,fd=benchmark('full',args.counts)
    assert sd==fd, 'shared/full logical historical exports differ'
    evidence={'experiment':'unified operation B and historical storage','recorded_at':cat.now(),'synthetic':True,'environment':environment(),
        'parameters':{'release_counts':args.counts,'buildings':25,'terrain_grid':[11,11],'restrictions':3,'exposure_zones':6,
                      'change':'one airspace ceiling per release','journal_mode':'WAL','synchronous':'FULL',
                      'history_latency':'reopened connection; warm OS cache; SQL + digest validation + full JSON serialization; 30 reads alternating oldest/middle/latest',
                      'storage':'main DB after successful TRUNCATE checkpoint; indexes, audit and outbox included'},
        'regressions':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'log':stream.getvalue()},
        'storage':shared+full,'paired_semantic_hashes_equal':sd==fd,'sampled_semantic_hashes':sd,
        'known_other_owner_defects':review_yht()}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print('wrote',args.output)


if __name__=='__main__': main()
