"""Governance service over the unified schema. Server owns identity and DB handle.

SQLite has no GRANT/RLS. Authorizer + restricted views demonstrate SQL-boundary
controls; a caller with the database file or Python connection is privileged.
"""
from copy import deepcopy
import json
import re
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'docs/modules/zqo/v2/experiments'))
import catalog as cat

VIEWS = {'v_exposure_summary','v_exposure_detail'}
AT = '2026-11-07T00:00:00Z'


def seed(c):
    for name,role,org,active in [('AUTHOR','airspace_admin','SYN',1),('REVIEWER','airspace_admin','SYN',1),
                               ('DISPATCH','dispatcher','SYN',1),('OPER','operator','SYN',1),
                               ('SYS','system_admin','SYN',1),('OTHER','dispatcher','OTHER',1),
                               ('OFF','dispatcher','SYN',0)]:
        c.execute('INSERT INTO actor VALUES(?,?,?,?,?)',(name,role,org,active,AT))
    for role in ('dispatcher','operator','airspace_admin'):
        c.execute('INSERT INTO access_policy VALUES(?,?,?,?,?,?,?)',
                  ('summary-'+role,role,'v_exposure_summary','read','restricted',None,'active'))
    c.execute('INSERT INTO access_policy VALUES(?,?,?,?,?,?,?)',
              ('detail-admin','airspace_admin','v_exposure_detail','read','restricted',None,'active'))


def reader(path, actor):
    c=cat.connect(path)
    # Authenticate before exposing the query connection; identity is not in SQL input.
    if c.execute('SELECT active FROM actor WHERE actor_id=?',(actor,)).fetchone() is None:
        c.close(); raise PermissionError('unknown actor')
    c.create_function('current_actor',0,lambda:actor)
    def authorize(action, table, column, database, origin):
        if action == sqlite3.SQLITE_SELECT: return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_DENY if column in ('load_extension','writefile','readfile') else sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if table in VIEWS or origin in VIEWS or origin in ('resolved_feature',):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    c.set_authorizer(authorize)
    return c


def read_audited(path, actor, sql):
    c=reader(path,actor)
    try:
        if not re.fullmatch(r'\s*SELECT\s+\*\s+FROM\s+(v_exposure_summary|v_exposure_detail)\s*;?\s*',sql,re.IGNORECASE):
            raise sqlite3.DatabaseError('restricted endpoint accepts fixed view queries only')
        result=cat.rows(c,sql); status='success'; reason='restricted view'
        return result
    except sqlite3.DatabaseError as exc:
        status='denied'; reason=str(exc); raise
    finally:
        c.close()
        audit=cat.connect(path)
        cat.insert(audit,'audit_event',dict(event_id='read:'+__import__('uuid').uuid4().hex,at=AT,
            actor_id=actor,action='query' if status=='success' else 'deny',object_kind='view',
            object_id='restricted-query',result=status,reason=reason,detail=json.dumps({'role_snapshot':audit.execute('SELECT role FROM actor WHERE actor_id=?',(actor,)).fetchone()[0]})))
        audit.close()


def request_release(c, payload, release_id, expected, author, request_id, provenance=None):
    provenance=deepcopy(provenance or cat.provenance())
    digest=cat.digest({'payload':payload,'release_id':release_id,'expected':expected,'provenance':provenance})
    cat.insert(c,'governance_request',dict(request_id=request_id,object_kind='release',object_id=release_id,
                                         author_id=author,payload_hash=digest,created_at=AT))
    return digest


def approve(c, request_id, reviewer):
    try:
        cat.insert(c,'governance_approval',dict(request_id=request_id,reviewer_id=reviewer,decision='approved',at=AT,reason='synthetic review'))
    except sqlite3.IntegrityError as exc:
        if c.execute('SELECT 1 FROM actor WHERE actor_id=?',(reviewer,)).fetchone():
            cat.insert(c,'audit_event',dict(event_id='denied-approval:'+__import__('uuid').uuid4().hex,
                at=AT,actor_id=reviewer,action='deny',object_kind='governance_request',object_id=request_id,
                result='denied',reason=str(exc),request_id=request_id))
        raise


def publish_approved(c,payload,release_id,expected,request_id,reviewer,provenance=None):
    provenance=deepcopy(provenance or cat.provenance())
    r=c.execute('SELECT r.*,a.reviewer_id,a.decision FROM governance_request r JOIN governance_approval a USING(request_id) WHERE request_id=?',(request_id,)).fetchone()
    expected_hash=cat.digest({'payload':payload,'release_id':release_id,'expected':expected,'provenance':provenance})
    if not r or r['decision']!='approved' or r['reviewer_id']!=reviewer or r['author_id']==reviewer or r['payload_hash']!=expected_hash or r['object_id']!=release_id or r['object_kind']!='release':
        raise PermissionError('independent matching approval required')
    for model in payload['exposure']['risk_model']:
        if c.execute('SELECT 1 FROM risk_model_control WHERE risk_model_id=? AND enabled=0',(model['risk_model_id'],)).fetchone():
            raise PermissionError('risk model disabled for new publication')
    return cat.publish(c,payload,release_id=release_id,expected=expected,request_id=request_id,
                       actor=reviewer,provenance=provenance,timestamp=AT)


def compile_dataset(c,release_id,dataset_id,profiles=None,seal=True):
    """Compile windowed native LQ profiles into SQL periods and whole-window maxima.

    profiles map stable zone_id to LQ periods. Input E/C validation reuses v1 score.
    Publication/legacy fixture dates may be longer than an actual task window.
    """
    sys.path.insert(0,str(ROOT/'docs/modules/lq/prototype'))
    from risk import score
    snap=cat.snapshot(c,release_id)
    rc=next(x for x in snap['mappings'] if x['layer']=='exposure')
    r=c.execute('SELECT valid_lo,valid_hi FROM release WHERE release_id=?',(release_id,)).fetchone()
    window=(r['valid_lo'],r['valid_hi'])
    zones=cat.rows(c,'SELECT e.* FROM feature f JOIN exposure_zone e USING(rid) WHERE f.release_id=?',(rc['owner_release_id'],))
    c.execute('BEGIN IMMEDIATE')
    try:
        cat.insert(c,'risk_dataset',dict(dataset_id=dataset_id,release_id=release_id,component_id=rc['component_id'],
            risk_model_id=zones[0]['risk_model_id'],window_lo=window[0],window_hi=window[1],compiler_version='lq-sql-1',created_by='AUTHOR',created_at=AT))
        for zone in zones:
            periods=(profiles or {}).get(zone['zone_id'],[{'valid':list(window),'E':zone['exposure_e'],'C':zone['consequence_c']}])
            values=[]
            for p in periods:
                value=score(p['E'],p['C'])
                if value is None: raise ValueError('unknown E/C; reject validated SQL dataset')
                lo,hi=max(p['valid'][0],window[0]),min(p['valid'][1],window[1])
                if lo>=hi: continue
                cat.insert(c,'risk_input_period',dict(dataset_id=dataset_id,zone_rid=zone['rid'],valid_lo=lo,valid_hi=hi,
                           exposure_e=p['E'],consequence_c=p['C']))
                values.append(value)
            cat.insert(c,'derived_risk',dict(dataset_id=dataset_id,zone_rid=zone['rid'],q_max=max(values,default=0),source_id=zone['source_id']))
        cat.insert(c,'quality_check',dict(check_id='quality:'+dataset_id,dataset_id=dataset_id,rule='coverage_and_max',
                   result='pass',checked_at=AT,actor_id='REVIEWER',detail=json.dumps({'stage':'computed; database gate independently verifies'})))
        if seal: c.execute("UPDATE risk_dataset SET state='validated' WHERE dataset_id=?",(dataset_id,))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK'); raise
    return zones


def lineage(c,dataset_id):
    d=c.execute('SELECT * FROM risk_dataset WHERE dataset_id=?',(dataset_id,)).fetchone()
    rows=[('component',d['component_id']),('model',d['risk_model_id'])]
    rows += [('source',r[0]) for r in c.execute('SELECT DISTINCT source_id FROM derived_risk WHERE dataset_id=?',(dataset_id,))]
    for n,(kind,key) in enumerate(rows):
        cat.insert(c,'lineage_edge',dict(edge_id=dataset_id+':'+str(n),from_kind=kind,from_id=key,to_kind='dataset',to_id=dataset_id,
                   activity='compiled_from',tool_version='lq-sql-1',at=AT,release_id=d['release_id']))
