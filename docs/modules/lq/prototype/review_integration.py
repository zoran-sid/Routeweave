"""LQ read-only integration probes. Exit 1 for an outstanding owner finding.

Uses current member implementations; all writes are explicit evidence outputs or
SQLite databases in temporary directories. Does not rewrite historical results.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
for member in ('yht', 'lq', 'zc', 'zqo'):
    sys.path.insert(0, str(ROOT / 'docs/modules' / member / 'prototype'))
from yht_model import scene, seal
from export_zc import export_snapshot
from export_lq import profiles_from_scene
from source_adapter import prepare_source, SourceRejected
from publication import Catalog, prepare_risk, digest
from risk import compile_profiles
from planner import assess_segment
from scenarios import bind

WINDOW = {'start': '2026-11-05T08:05:00Z', 'end': '2026-11-05T08:15:00Z'}
BOUNDS = [[0, 0, 10], [450, 450, 120]]
A, B = [20, 20, 70], [40, 20, 70]
START, GOAL = [20, 20, 70], [420, 420, 70]


def exported(source):
    return bind(*export_snapshot(source, WINDOW, BOUNDS, START, GOAL))


def run():
    cases = []
    def record(name, owner, passed, observed):
        cases.append({'id': name, 'owner': owner, 'passed': bool(passed), 'observed': observed})

    source = scene()
    source['buildings'] = []
    source['airspace'] = []
    source = seal(source)
    known_s, known_q = exported(source)
    for name, fields in [('all', ('q', 'exposure_e', 'consequence_c')),
                         ('q', ('q',)), ('E', ('exposure_e',)), ('C', ('consequence_c',))]:
        bad = deepcopy(source)
        for field in fields:
            bad['ground_zones'][0][field] = None
        bad = seal(bad)
        zone = bad['ground_zones'][0]
        for route in ('export_zc', 'export_lq', 'prepare_source'):
            before = deepcopy(bad)
            obs = {'region_id': zone['id'], 'polygon': zone['polygon'], 'source_id': zone['source_id'],
                   'source_versions': bad['versions'], 'missing_fields': fields}
            try:
                if route == 'export_zc':
                    s, q = exported(bad)
                elif route == 'export_lq':
                    # Independent entry: do not let export_zc's gate mask it.
                    s, q = compile_profiles(known_s, known_q, profiles_from_scene(bad))
                else:
                    s, q = prepare_source(bad, WINDOW, BOUNDS, START, GOAL)
                response = assess_segment(s, q, A, B)
                obs.update(response=response, rejected=False)
                passed = response['state'] == 'unknown'
            except ValueError as exc:
                obs.update(rejected=True, reason=str(exc), stage=getattr(exc, 'stage', 'export'))
                passed = True
            obs['input_unchanged'] = bad == before
            record('unknown_' + name + '_' + route, 'YHT' if route != 'prepare_source' else 'ZQO',
                   passed and obs['input_unchanged'], obs)

    # LQ accepts native unknown E/C profiles, preserving box/source and versioned inputs.
    original_profiles = profiles_from_scene(source)
    for missing in ('E', 'C', 'gap'):
        profiles = deepcopy(original_profiles)
        period = profiles[0]['periods'][0]
        if missing == 'gap':
            period['valid'][1] = '2026-11-05T08:10:00Z'
        else:
            period[missing] = None
        s, q = prepare_risk(known_s, known_q, profiles)
        unknown = next(z for z in s['risk_data']['zones'] if z['id'] == profiles[0]['id'] + ':unknown')
        response = assess_segment(s, q, A, B)
        record('compiled_unknown_' + missing, 'LQ', response['state'] == 'unknown'
               and profiles[0]['id'] + ':unknown' in response['sources']
               and unknown['box'] == profiles[0]['box'] and unknown['source'] == profiles[0]['source']
               and s['risk_data']['profile_inputs'] == profiles,
               {'response': response, 'unknown_zone': unknown, 'profile': profiles[0],
                'compiled_window': s['risk_data']['compiled_window']})

    # Native q=None is retained by ZC even though strict YHT exporters refuse it.
    s, q = deepcopy(known_s), deepcopy(known_q)
    s['risk_data']['zones'][0]['q'] = None
    s, q = bind(s, q)
    r = assess_segment(s, q, A, B)
    record('native_unknown_q', 'ZC', r['state'] == 'unknown'
           and s['risk_data']['zones'][0]['id'] in r['sources'], r)

    # Check unchanged hard/soft definitions on an unobstructed source segment.
    for weight in (0, 8):
        s, q = deepcopy(known_s), deepcopy(known_q)
        s['planner_config']['lambda_risk'] = weight
        for e in (.7, .9):
            profiles = deepcopy(original_profiles)
            profiles[0]['periods'][0].update(E=e, C=1)
            bound, query = prepare_risk(s, q, profiles)
            r = assess_segment(bound, query, A, B)
            if e == .9:
                ok = r['state'] == 'forbidden' and r['reason'] == 'risk_threshold'
            else:
                expected = 20 / bound['planner_config']['length_scale_m'] * r['q_max']
                ok = r['state'] == 'allowed' and abs(r['risk_proxy'] - expected) < 1e-12
                ok &= abs(r['cost'] - (20/100 + weight*expected)) < 1e-12
            record('hard_soft_' + str(weight) + '_' + str(e), 'LQ', ok, r)

    # Actual source adapter, publication, source mapping, window gate, and DB reopen.
    actual = seal(scene())
    s, q = prepare_source(actual, WINDOW, BOUNDS, START, GOAL)
    with tempfile.TemporaryDirectory() as tmp:
        file = Path(tmp) / 'lq-review.sqlite'
        db = Catalog(file)
        rid = db.publish(s, q, expected=None, request_id='lq-risk-review')
        db = Catalog(file)
        pinned = db.pin(rid)['snapshot']
        lineage = pinned['lineage']
        records = {x['id']: x for x in actual['ground_zones']}
        profiles = pinned['risk_data']['profile_inputs']
        mapping_ok = all(p['source'] == records[p['id']]['source_id']
                         and p['periods'][0]['E'] == records[p['id']]['exposure_e']
                         and p['periods'][0]['C'] == records[p['id']]['consequence_c'] for p in profiles)
        normal = db.status(q, A, B, rid)
        record('source_mapping_and_reopen', 'ZQO', mapping_ok
               and lineage['source_sha256'] == digest(actual)
               and lineage['source_snapshot'] == actual
               and lineage['source_release']['versions'] == actual['versions']
               and lineage['query_versions'] == pinned['versions']
               and normal['versions'] == pinned['versions']
               and normal['source_release'] == lineage['source_release'],
               {'profiles': profiles, 'lineage': lineage, 'response': normal})
        for name, window in [('matching', q['window']),
                             ('extended', [q['window'][0], '2026-11-05T08:20:00Z']),
                             ('shifted', ['2026-11-05T08:10:00Z', '2026-11-05T08:20:00Z']),
                             ('subset', [q['window'][0], '2026-11-05T08:10:00Z'])]:
            probe = deepcopy(q); probe['window'] = window; probe['departure'] = window[0]
            r = db.status(probe, A, B, rid)
            ok = r['state'] == 'allowed' if name == 'matching' else (
                r['state'] == 'unknown' and r['reason'] == 'risk_window_mismatch')
            record('published_window_' + name, 'ZQO', ok and r['versions'] == pinned['versions']
                   and r['compiled_window'] == q['window']
                   and r['source_release'] == lineage['source_release'], r)
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = run()
    files = [Path(__file__), *sorted((ROOT/'docs/modules').rglob('*.py'))]
    report = {'baseline': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
              'executed_at': datetime.now(timezone.utc).isoformat(), 'cases': cases,
              'failed_cases': sum(not x['passed'] for x in cases),
              'source_sha256': {str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in files}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding="utf-8")
    for c in cases:
        print(c['id'], 'PASS' if c['passed'] else 'FAIL', c['owner'])
    print('total:', len(cases), 'failed:', report['failed_cases'])
    raise SystemExit(bool(report['failed_cases']))

if __name__ == '__main__': main()
