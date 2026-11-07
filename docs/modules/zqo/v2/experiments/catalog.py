"""Operation B on the unified SQLite schema. JSON is an export, never a second store.

Payloads contain normalized YHT table rows, with feature_id replacing physical rid.
Only the publishing service owns writes; SQL consumers pin one release/read transaction.
"""
import copy
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCHEMA = ROOT / 'docs/v2/schema'
sys.path.insert(0, str(SCHEMA))
import fixtures as fx

LAYERS = fx.LAYERS
TYPES = {'scene': 'building', 'airspace': 'airspace_restriction', 'exposure': 'exposure_zone'}
TABLES = {'scene': ('feature', 'building', 'coverage_tile'),
          'airspace': ('feature', 'airspace_restriction', 'coverage_tile'),
          'exposure': ('feature', 'exposure_zone', 'coverage_tile', 'risk_model'),
          'terrain': ('terrain_surface', 'terrain_post', 'coverage_tile'),
          'sources': ('source',)}
WIN = ('2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def connect(path):
    c = sqlite3.connect(path, isolation_level=None, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=10000')
    c.execute('PRAGMA synchronous=FULL')
    return c


def initialize(path):
    c = connect(path)
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript((SCHEMA / 'schema.sql').read_text(encoding='utf-8'))
    with c:
        fx.base(c)
    c.close()


def rows(c, sql, params=()):
    return [dict(r) for r in c.execute(sql, params)]


def normalized(items):
    return sorted(items, key=canonical)


def read_layer(c, owner, layer, component_id=None):
    """Canonical semantic rows; physical owner/rid do not change the content hash."""
    out = {table: [] for table in TABLES[layer]}
    if layer in TYPES:
        features = rows(c, 'SELECT * FROM feature WHERE release_id=? AND layer=?', (owner, layer))
        table = TYPES[layer]
        children = rows(c, f'SELECT t.*, f.feature_id FROM {table} t JOIN feature f USING(rid) '
                          'WHERE f.release_id=? AND f.layer=?', (owner, layer))
        for f in features:
            f.pop('rid'); f.pop('release_id')
        for child in children:
            child.pop('rid')
            child.pop('forbid_lo_z', None); child.pop('forbid_hi_z', None)
        out['feature'], out[table] = features, children
        if layer == 'exposure':
            ids = sorted({r['risk_model_id'] for r in children})
            out['risk_model'] = [dict(c.execute('SELECT * FROM risk_model WHERE risk_model_id=?', (i,)).fetchone()) for i in ids]
    if layer == 'terrain':
        for table in ('terrain_surface', 'terrain_post'):
            out[table] = rows(c, f'SELECT * FROM {table} WHERE release_id=?', (owner,))
            for r in out[table]:
                r.pop('release_id')
    if layer != 'sources':
        out['coverage_tile'] = rows(c, 'SELECT * FROM coverage_tile WHERE release_id=? AND layer=?', (owner, layer))
        for r in out['coverage_tile']:
            r.pop('release_id')
    else:
        out['source'] = rows(c, 'SELECT s.* FROM source s JOIN component_source cs USING(source_id) '
                               'WHERE cs.component_id=?', (component_id,))
    return {k: normalized(v) for k, v in out.items()}


def insert(c, table, row):
    # table and column names come from schema-controlled code/payload validation below.
    cols = {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
    if not set(row) <= cols:
        raise ValueError(f'unknown columns: {table}')
    names = ','.join('"' + k + '"' for k in row)
    return c.execute(f'INSERT INTO {table} ({names}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))


def write_layer(c, release_id, layer, payload, component_id):
    rid_map = {}
    for table in TABLES[layer]:
        for original in payload[table]:
            r = dict(original)
            if table in ('source', 'risk_model'):
                key = 'source_id' if table == 'source' else 'risk_model_id'
                actual = c.execute(f'SELECT * FROM {table} WHERE {key}=?', (r[key],)).fetchone()
                if actual is None or dict(actual) != r:
                    raise ValueError(f'reference metadata mismatch: {table}:{r[key]}')
                if table == 'source':
                    insert(c, 'component_source', {'component_id': component_id, 'source_id': r[key]})
            elif table == 'feature':
                r['release_id'] = release_id
                rid_map[r['feature_id']] = insert(c, table, r).lastrowid
            elif table in TYPES.values():
                r['rid'] = rid_map[r.pop('feature_id')]
                insert(c, table, r)
            else:
                r['release_id'] = release_id
                insert(c, table, r)


def validate(payload, window):
    if set(payload) != set(LAYERS) or window[0] >= window[1]:
        raise ValueError('five layers and a nonempty window required')
    for t in window:
        if datetime.strptime(t, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H:%M:%SZ') != t:
            raise ValueError('UTC format')
    source_ids = {r['source_id'] for r in payload['sources']['source']}
    if not source_ids:
        raise ValueError('source manifest is empty')
    for layer in LAYERS:
        if set(payload[layer]) != set(TABLES[layer]):
            raise ValueError(f'layer tables: {layer}')
        for table, records in payload[layer].items():
            for row in records:
                for field in ('source_id', 'footprint_source', 'height_source'):
                    if field in row and row[field] not in source_ids:
                        raise ValueError('source omitted from manifest')
                if row.get('valid_lo') is not None and not (row['valid_lo'] <= window[0] < window[1] <= row['valid_hi']):
                    raise ValueError(f'valid window mismatch: {table}')
                if table == 'coverage_tile' and (row['layer'] != layer or row['complete'] != 1):
                    raise ValueError('incomplete/mismatched coverage')
                if table == 'feature' and row['layer'] != layer:
                    raise ValueError('feature layer mismatch')
        if layer in TYPES:
            ids = [r['feature_id'] for r in payload[layer]['feature']]
            sub_ids = [r['feature_id'] for r in payload[layer][TYPES[layer]]]
            if sorted(ids) != sorted(sub_ids) or len(set(ids)) != len(ids):
                raise ValueError('feature/subtype mismatch')
        if layer != 'sources' and not payload[layer]['coverage_tile']:
            raise ValueError(f'coverage absent: {layer}')


def head(c, scene='syn-district'):
    r = c.execute('SELECT release_id FROM current_release WHERE scene_id=?', (scene,)).fetchone()
    return r[0] if r else None


def snapshot(c, release_id=None, scene='syn-district'):
    """One read transaction includes head, all layers and verification; safe for WAL readers."""
    own = not c.in_transaction
    if own:
        c.execute('BEGIN')
    try:
        observed = head(c, scene)
        rid = observed if release_id is None else release_id
        release = c.execute('SELECT * FROM release WHERE release_id=? AND scene_id=? AND status<>\'draft\'', (rid, scene)).fetchone()
        if release is None:
            raise LookupError(f'unknown published release: {rid}')
        mappings = rows(c, 'SELECT rc.layer, rc.component_id, lc.owner_release_id, rl.layer_version, '
                          'rl.content_hash FROM release_component rc JOIN layer_component lc USING(component_id) '
                          'JOIN release_layer rl ON rl.release_id=rc.release_id AND rl.layer=rc.layer '
                          'WHERE rc.release_id=? ORDER BY rc.layer', (rid,))
        if len(mappings) != 5:
            raise ValueError('unmapped release; import legacy fixture explicitly')
        data = {}
        for m in mappings:
            data[m['layer']] = read_layer(c, m['owner_release_id'], m['layer'], m['component_id'])
            if digest(data[m['layer']]) != m['content_hash']:
                raise ValueError(f'component drift: {m["layer"]}')
        hashes = {m['layer']: m['content_hash'] for m in mappings}
        manifest = json.loads(release['manifest'])
        if digest({'hashes': hashes, 'window': [release['valid_lo'], release['valid_hi']],
                   'scene': scene, 'provenance': manifest['provenance']}) != release['content_hash']:
            raise ValueError('release manifest drift')
        return {'release_id': rid, 'observed_head': observed, 'freshness': 'current' if rid == observed else 'historical',
                'mappings': mappings, 'manifest': manifest, 'layers': data, 'content_hash': release['content_hash']}
    finally:
        if own:
            c.execute('ROLLBACK')


class Conflict(ValueError):
    pass


def publish(c, payload, *, request_id, release_id, expected, scene='syn-district',
            actor='A-ADMIN', window=WIN, provenance=None, mode='shared', timestamp=None,
            failpoint=None, hook=None):
    """BEGIN IMMEDIATE + expected-head CAS. Caller must not already be in a transaction.

    Hook is a test-only callback at failpoints. Retry the SAME request after a lost reply.
    Failure audit is committed in a separate transaction after rollback; process death before
    that second commit requires an upstream durable request log (LJ handoff).
    """
    if c.in_transaction:
        raise ValueError('publish requires its own transaction')
    if mode not in ('shared', 'full'):
        raise ValueError('unknown storage mode')
    timestamp = timestamp or now()
    provenance = copy.deepcopy(provenance or {})
    payload = {k: {t: normalized(v) for t, v in p.items()} for k, p in copy.deepcopy(payload).items()}
    request_hash = digest({'payload': payload, 'release_id': release_id, 'expected': expected,
                           'scene': scene, 'actor': actor, 'window': list(window), 'provenance': provenance, 'mode': mode})
    observed = None

    def stage(name):
        if hook:
            hook(name)
        if name == failpoint:
            raise RuntimeError('injected:' + name)

    try:
        c.execute('BEGIN IMMEDIATE')
        previous = c.execute('SELECT * FROM publish_request WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if previous['request_hash'] != request_hash:
                raise Conflict('idempotency key payload mismatch')
            snapshot(c, previous['release_id'], scene)  # replay must not bless drifted data
            c.execute('COMMIT')
            return {'release_id': previous['release_id'], 'replayed': True}
        observed = head(c, scene)
        if observed != expected:
            raise Conflict(f'head conflict: expected={expected}, observed={observed}')
        role = c.execute('SELECT role,active FROM actor WHERE actor_id=?', (actor,)).fetchone()
        if not role or not role['active'] or role['role'] not in ('airspace_admin', 'system_admin'):
            raise PermissionError('publisher role denied')
        validate(payload, window)
        if set(provenance) != {'source_versions', 'risk_window', 'risk_model_id', 'compiler_version'}:
            raise ValueError('explicit provenance required')
        if set(provenance['source_versions']) != set(LAYERS):
            raise ValueError('five upstream versions required')
        if provenance['risk_window'] != list(window):
            raise ValueError('risk compilation window mismatch')
        models = {r['risk_model_id'] for r in payload['exposure']['risk_model']}
        if models != {provenance['risk_model_id']}:
            raise ValueError('risk model provenance mismatch')
        old = snapshot(c, expected, scene) if expected else None
        hashes = {layer: digest(payload[layer]) for layer in LAYERS}
        manifest = {'provenance': provenance, 'source_ids': sorted(r['source_id'] for r in payload['sources']['source']),
                    'layer_hashes': hashes, 'storage': mode}
        content_hash = digest({'hashes': hashes, 'window': list(window), 'scene': scene, 'provenance': provenance})
        insert(c, 'release', dict(release_id=release_id, scene_id=scene, schema_version='v2-schema-0.2',
               baseline='starter-v0', status='draft', base_release_id=expected, valid_lo=window[0],
               valid_hi=window[1], created_at=timestamp, actor_id=actor, content_hash=content_hash, manifest=canonical(manifest)))
        stage('after_draft')
        for layer in LAYERS:
            candidate = None
            if mode == 'shared' and (layer != 'airspace' or (old and digest(old['layers'][layer]) == hashes[layer])):
                candidate = c.execute('SELECT lc.* FROM layer_component lc JOIN release r ON r.release_id=lc.owner_release_id '
                    'WHERE lc.layer=? AND lc.content_hash=? AND r.scene_id=? AND r.status<>\'draft\' ORDER BY lc.component_id LIMIT 1',
                    (layer, hashes[layer], scene)).fetchone()
            if candidate:
                cid = candidate['component_id']
                if digest(read_layer(c, candidate['owner_release_id'], layer, cid)) != hashes[layer]:
                    raise ValueError('shared component drift')
            else:
                cid = release_id + ':' + layer
                count = len(payload[layer].get('feature', payload[layer].get('terrain_post', payload[layer].get('source', []))))
                insert(c, 'layer_component', dict(component_id=cid, layer=layer, owner_release_id=release_id,
                                                 content_hash=hashes[layer], feature_count=count))
                write_layer(c, release_id, layer, payload[layer], cid)
                if digest(read_layer(c, release_id, layer, cid)) != hashes[layer]:
                    raise ValueError('roundtrip mismatch: ' + layer)
            count = c.execute('SELECT feature_count FROM layer_component WHERE component_id=?', (cid,)).fetchone()[0]
            insert(c, 'release_layer', dict(release_id=release_id, layer=layer, layer_version=hashes[layer],
                    content_hash=hashes[layer], feature_count=count, generated_at=timestamp, complete=1))
            insert(c, 'release_component', dict(release_id=release_id, layer=layer, component_id=cid))
        stage('after_components')
        old_air = {r['restriction_id']: r for r in old['layers']['airspace']['airspace_restriction']} if old else {}
        new_air = {r['restriction_id']: r for r in payload['airspace']['airspace_restriction']}
        if set(old_air) - set(new_air):
            raise ValueError('restrictions must be revoked explicitly, not dropped')
        actions = []
        for restriction, row in new_air.items():
            if old_air.get(restriction) == row:
                continue
            action = ('revoke' if row['state'] == 'revoked' else 'expire' if row['state'] == 'expired'
                      else 'update' if restriction in old_air else 'publish')
            prior = c.execute('SELECT e.event_id FROM airspace_event e JOIN release r USING(release_id) '
                              'WHERE e.restriction_id=? AND r.scene_id=? ORDER BY e.rowid DESC LIMIT 1', (restriction, scene)).fetchone()
            insert(c, 'airspace_event', dict(event_id=release_id + ':' + restriction, release_id=release_id,
                restriction_id=restriction, action=action, occurred_at=timestamp, effective_at=row['revoked_at'] or row['effective_lo'],
                actor_id=actor, source_id=row['source_id'], payload_hash=digest(row), reason='operation B: ' + release_id,
                previous_event_id=prior[0] if prior else None))
            actions.append(action)
        stage('after_events')
        c.execute("UPDATE release SET status='published',published_at=? WHERE release_id=?", (timestamp, release_id))
        if expected:
            n = c.execute('UPDATE current_release SET release_id=? WHERE scene_id=? AND release_id=?', (release_id, scene, expected)).rowcount
            if n != 1:
                raise Conflict('head compare-and-swap failed')
            c.execute("UPDATE release SET status='superseded' WHERE release_id=?", (expected,))
        else:
            insert(c, 'current_release', dict(scene_id=scene, release_id=release_id))
        stage('after_head')
        action = 'revoke' if 'revoke' in actions else 'publish'
        eid = 'audit:' + release_id
        insert(c, 'audit_event', dict(event_id=eid, at=timestamp, actor_id=actor, action=action,
               object_kind='release', object_id=release_id, release_id=release_id, result='success',
               request_id=request_id, detail=canonical({'hashes': hashes, 'provenance': provenance})))
        insert(c, 'outbox', dict(event_id=eid, release_id=release_id, kind=action, created_at=timestamp))
        insert(c, 'publish_request', dict(request_id=request_id, request_hash=request_hash, release_id=release_id))
        stage('before_commit')
        c.execute('COMMIT')
    except Exception as error:
        if c.in_transaction:
            c.execute('ROLLBACK')
        # Separate durable failure row. A failure here is reported, never silently swallowed.
        c.execute('BEGIN IMMEDIATE')
        try:
            insert(c, 'failed_attempt', dict(attempt_id=str(uuid.uuid4()), request_id=request_id,
                candidate_hash=request_hash, candidate_release_id=release_id, expected_release_id=expected,
                observed_release_id=observed, actor_ref=actor, at=timestamp, reason=f'{type(error).__name__}: {error}'))
            c.execute('COMMIT')
        except Exception as audit_error:
            c.execute('ROLLBACK')
            raise RuntimeError(f'publication failed ({error}); failure audit also failed ({audit_error})') from audit_error
        raise
    stage('after_commit')  # lost response: durable success, not a failed transaction
    return {'release_id': release_id, 'replayed': False}


def provenance(window=WIN):
    return {'source_versions': {layer: 'synthetic-v2-1' for layer in LAYERS}, 'risk_window': list(window),
            'risk_model_id': 'lq-risk-v1', 'compiler_version': 'synthetic-fixture-1'}


def fixture(buildings=25, grid=11):
    """Synthetic relational workload, not a v1 geometry/risk-compiler adapter."""
    c = fx.connect(); c.row_factory = sqlite3.Row; fx.base(c); fx.create_release(c, 'seed')
    rid = 1
    for i in range(buildings):
        fx.add_building(c, rid, 'seed', f'B-{i:04}', (float(i*20), 0., float(i*20+10), 10.), 0., 60.); rid += 1
    for i in range(3):
        fx.add_airspace(c, rid, 'seed', f'NF-{i}', (100.+i*50, 90., 120.+i*50, 150.),
                       ('2026-11-05T08:00:00Z', '2026-11-05T09:00:00Z')); rid += 1
    for i in range(6):
        fx.add_exposure(c, rid, 'seed', f'G-{i}', (float(i*100), 0., float(i*100+100), 600.), .5, .4); rid += 1
    insert(c, 'terrain_surface', dict(release_id='seed', terrain_id='TER-1', surface_type='grid', bounds_wkt=fx.box_wkt(0,0,600,600),
        post_spacing_m=600./(grid-1), vertical_datum='local-z0', flat=1, min_z=0., max_z=0., source_id='SRC-SYN',
        quality='assumed', valid_lo=WIN[0], valid_hi=WIN[1], checksum=digest('flat')))
    for ix in range(grid):
        for iy in range(grid):
            insert(c, 'terrain_post', dict(release_id='seed', terrain_id='TER-1', ix=ix, iy=iy,
                x=ix*600./(grid-1), y=iy*600./(grid-1), z=0., quality='assumed', source_id='SRC-SYN'))
    for layer in LAYERS[:-1]:
        insert(c, 'coverage_tile', dict(release_id='seed', layer=layer, tile_id='T-0', tile_x=0, tile_y=0,
            bounds_wkt=fx.box_wkt(0,0,600,600), complete=1, quality='assumed', source_id='SRC-SYN',
            valid_lo=WIN[0], valid_hi=WIN[1], checksum=digest(layer)))
    payload = {layer: read_layer(c, 'seed', layer) for layer in LAYERS if layer != 'sources'}
    payload['sources'] = {'source': rows(c, 'SELECT * FROM source')}
    c.close()
    return payload


def changed(payload, number=1, revoke=False):
    result = copy.deepcopy(payload)
    row = result['airspace']['airspace_restriction'][0]
    if revoke:
        row['state'], row['revoked_at'] = 'revoked', '2026-11-05T08:10:00Z'
    else:
        row['ceiling_m'] = float(100 + number)
    return result
