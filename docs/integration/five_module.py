"""Execute the five actual modules; retain complete evidence, including failures.

No member implementation or historical result is changed. --output saves a new
JSON evidence file. Exit 1 if any acceptance condition fails.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
for member in ('yht', 'lq', 'zc', 'zqo', 'lj'):
    sys.path.insert(0, str(ROOT / 'docs/modules' / member / 'prototype'))
from yht_model import scene, seal
from source_adapter import prepare_source, SourceRejected
from publication import Catalog, digest
from acceptance import validate_result

WINDOW = {'start': '2026-11-05T08:05:00Z', 'end': '2026-11-05T08:15:00Z'}
BOUNDS = [[0, 0, 10], [450, 450, 120]]
START, GOAL = [20, 20, 70], [420, 420, 70]


def prepare(source):
    return prepare_source(source, WINDOW, BOUNDS, START, GOAL)


def inspect(catalog, query, pinned=None):
    result = catalog.query(query, pinned)
    current = catalog.pin()['snapshot']['versions']
    path = result['path'] if result['status'] == 'feasible' else []
    segments = [catalog.status(query, a, b, result['release_id'])
                for a, b in zip(path, path[1:])]
    return {'q1': result, 'q2': segments,
            'lj_current': validate_result(result, current),
            'lj_history': validate_result(result, current, purpose='history')}


def release_metadata(pinned):
    return {**{k:v for k,v in pinned.items() if k != 'snapshot'},
            'snapshot_sha256': digest(pinned['snapshot'])}


def run():
    records, evidence = [], {}

    def check(name, passed, observed):
        records.append({'id': name, 'passed': bool(passed), 'observed': observed})

    source = seal(scene())
    s1, q1 = prepare(source)
    with tempfile.TemporaryDirectory() as tmp:
        db = Catalog(Path(tmp) / 'five.sqlite')
        r1 = db.publish(s1, q1, expected=None, request_id='normal', received_at=source['manifest']['created_at'])
        pinned1 = db.pin(r1)
        normal = inspect(db, q1)
        evidence['normal'] = {'snapshot': s1, 'query': q1,
                              'release': release_metadata(pinned1), 'result': normal}
        check('normal', normal['q1']['status'] == 'feasible'
              and normal['lj_current']['status'] == 'pass'
              and bool(normal['q2']) and all(x['state'] == 'allowed' for x in normal['q2']),
              {'release_id': r1, 'acceptance': normal['lj_current'],
               'metrics': normal['q1'].get('metrics')})
        if normal['q1']['status'] != 'feasible':
            return records, evidence

        # Deterministically place a full-height restriction around the middle
        # of the actual old route; preserve the YHT source model and reseal it.
        path = normal['q1']['path']; middle = len(path) // 2
        x = (path[middle-1][0] + path[middle][0]) / 2
        y = (path[middle-1][1] + path[middle][1]) / 2
        changed = deepcopy(source)
        changed['airspace'].append({
            'id': 'NF-INTEGRATION', 'kind': 'no_fly', 'state': 'published',
            'footprint': [[x-25,y-25],[x+25,y-25],[x+25,y+25],[x-25,y+25],[x-25,y-25]],
            'floor_z': 0, 'ceiling_z': 160, 'ceiling_m': None,
            'valid': list(q1['window']), 'source_id': source['airspace'][0]['source_id']})
        changed = seal(changed)
        s2, q2 = prepare(changed)
        before = db.counts()
        try:
            db.publish(s2, q2, expected=r1, request_id='failed-update', received_at=changed['manifest']['created_at'], fail_at='before_commit')
            failure = {'unexpected_success': True}
        except RuntimeError as exc:
            failure = {'exception': type(exc).__name__, 'reason': str(exc)}
        failure.update(head=db.current(), counts=db.counts(), audit=db.failures())
        evidence['failed_publication'] = failure
        check('failed_publication', failure.get('reason') == 'injected_before_commit'
              and db.current() == r1 and db.counts() == before
              and len(db.failures()) == 1
              and db.failures()[0]['snapshot_sha'] == digest(s2), failure)

        r2 = db.publish(s2, q2, expected=r1, request_id='update', received_at=changed['manifest']['created_at'])
        updated = inspect(db, q2)
        old_segments = [db.status(q2, a, b, r2) for a,b in zip(path,path[1:])]
        stale = inspect(db, q1, pinned1)
        evidence['updated'] = {'snapshot': s2, 'query': q2,
                               'release': release_metadata(db.pin(r2)), 'result': updated,
                               'old_route_under_new_release': old_segments, 'stale': stale}
        blocked = sum(x['state'] == 'forbidden' for x in old_segments)
        check('updated_route', blocked > 0 and updated['q1']['status'] == 'feasible'
              and updated['q1']['path'] != path and updated['lj_current']['status'] == 'pass'
              and all(x['state'] == 'allowed' for x in updated['q2']),
              {'old_blocked_segments': blocked, 'metrics': updated['q1'].get('metrics'),
               'acceptance': updated['lj_current']})
        check('stale_rejected', stale['q1']['freshness'] == 'stale'
              and stale['lj_current']['status'] == 'fail' and stale['lj_history']['status'] == 'pass',
              {'current': stale['lj_current'], 'history': stale['lj_history']})

        revoked = deepcopy(changed); revoked['airspace'][-1]['state'] = 'revoked'
        revoked = seal(revoked); s3, q3 = prepare(revoked)
        r3 = db.publish(s3, q3, expected=r2, request_id='revoke', received_at=revoked['manifest']['created_at'])
        restored = inspect(db, q3)
        evidence['revoked'] = {'snapshot': s3, 'query': q3,
                               'release': release_metadata(db.pin(r3)), 'result': restored}
        check('revoked_route', restored['q1']['status'] == 'feasible'
              and restored['q1']['path'] == path and restored['lj_current']['status'] == 'pass'
              and all(x['state'] == 'allowed' for x in restored['q2']),
              {'release_id': r3, 'metrics': restored['q1'].get('metrics'),
               'same_query_versions_as_normal': s3['versions'] == s1['versions'],
               'different_source_airspace': revoked['versions']['airspace'] != source['versions']['airspace']})
        same_versions_old = inspect(db, q1, pinned1)
        evidence['same_versions_stale'] = same_versions_old
        check('same_versions_stale_rejected', s3['versions'] == s1['versions']
              and same_versions_old['q1']['freshness'] == 'stale'
              and same_versions_old['lj_current']['status'] == 'fail', same_versions_old['lj_current'])

        bad_query = deepcopy(q1); bad_query['window'][1] = '2026-11-05T08:20:00Z'
        mismatch = db.status(bad_query, START, GOAL, r1)
        missing = db.status(q1, START, GOAL, 999)
        evidence['window_mismatch'], evidence['missing_release'] = mismatch, missing
        check('window_trace', mismatch['reason'] == 'risk_window_mismatch'
              and mismatch['versions'] == s1['versions']
              and mismatch['source_release'] == s1['lineage']['source_release']
              and mismatch['compiled_window'] == q1['window'], mismatch)
        check('missing_release', missing['reason'] == 'release_unavailable'
              and missing['versions'] == {} and missing['provenance_state'] == 'unavailable', missing)

        faults = {}
        for name in ('unknown_exposure', 'incomplete_coverage', 'nonflat_terrain', 'unsealed_change'):
            bad = deepcopy(source)
            if name == 'unknown_exposure':
                bad['ground_zones'][0].update(q=None, exposure_e=None, consequence_c=None)
            elif name == 'incomplete_coverage':
                bad['coverage'][0]['complete'] = False
            elif name == 'nonflat_terrain':
                bad['terrain']['flat'] = False
            else:
                bad['buildings'][0]['name'] = 'tampered without reseal'
            if name != 'unsealed_change': bad = seal(bad)
            try:
                prepare(bad)
                faults[name] = {'rejected': False}
            except SourceRejected as exc:
                faults[name] = {'rejected': True, 'stage': exc.stage,
                                'reason': str(exc), 'quality': exc.quality}
            faults[name]['source'] = bad
        evidence['quality_faults'] = faults
        check('quality_gates', all(x['rejected'] for x in faults.values()) and db.current() == r3,
              {k: {a:b for a,b in v.items() if a != 'source'} for k,v in faults.items()})

        reopened = Catalog(db.path)
        historical = [reopened.pin(r) for r in (r1,r2,r3)]
        replay = inspect(reopened, q1, historical[0])
        evidence['reopened'] = {'releases': [release_metadata(p) for p in historical], 'old_result': replay,
                                'failed_attempts': reopened.failures(), 'head': reopened.current()}
        check('history_reopened', [p['snapshot'] for p in historical] == [s1,s2,s3]
              and reopened.current() == r3 and reopened.failures() == db.failures()
              and replay['lj_history']['status'] == 'pass'
              and replay['lj_current']['status'] == 'fail',
              {'release_ids': [p['release_id'] for p in historical],
               'head': reopened.current(), 'history_acceptance': replay['lj_history']})
        mapping_ok = all(
            p['snapshot']['lineage']['source_sha256'] == digest(src)
            and p['snapshot']['lineage']['source_release']['versions'] == src['versions']
            and p['snapshot']['lineage']['source_release']['manifest'] == src['manifest']
            and p['snapshot']['lineage']['query_versions'] == p['snapshot']['versions']
            and all(m['query_version'] == p['snapshot']['versions'][k]
                    for k,m in p['snapshot']['lineage']['version_mapping'].items())
            for p,src in zip(historical,(source,changed,revoked)))
        check('source_mapping', mapping_ok,
              {'normal_source_versions': source['versions'], 'normal_query_versions': s1['versions'],
               'mapping': s1['lineage']['version_mapping'], 'compiled_window': q1['window']})
    return records, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        records, evidence = run()
    except Exception as exc:
        records = [{'id': 'execution_error', 'passed': False,
                    'observed': {'type': type(exc).__name__, 'reason': str(exc)}}]
        evidence = {'traceback': traceback.format_exc()}
    baseline = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    paths = sorted((ROOT/'docs/modules').rglob('*.py')) + [Path(__file__).resolve()]
    result = {'baseline': baseline, 'cases': records, 'failed_cases': sum(not x['passed'] for x in records),
              'evidence': evidence, 'source_sha256': {
                  str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in paths}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    for x in records: print(x['id'], 'PASS' if x['passed'] else 'FAIL')
    raise SystemExit(bool(result['failed_cases']))


if __name__ == '__main__': main()
