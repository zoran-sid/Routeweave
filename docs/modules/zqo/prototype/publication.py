"""ZQO transactional publication prototype. SQLite, synthetic trusted identities.
Production PostgreSQL mapping and operational boundaries are in ../design.md.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

MODULES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULES / 'zc' / 'prototype'))
sys.path.insert(0, str(MODULES / 'lq' / 'prototype'))
from planner import VERSION_KEYS, preflight, plan, assess_segment, instant
from scenarios import bind
from risk import compile_profiles, can_publish


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def prepare_risk(snapshot, query, profiles):
    s, q = compile_profiles(snapshot, query, profiles)
    s['risk_data']['compiled_window'] = list(q['window'])
    return bind(s, q)


def validate(s, q):
    error = preflight(s, q)
    if error:
        raise ValueError(error)
    if 'profile_inputs' in s['risk_data']:
        window = s['risk_data'].get('compiled_window')
        if not window or list(map(instant, window)) != list(map(instant, q['window'])):
            raise ValueError('risk_window_mismatch')


class Catalog:
    def __init__(self, path):
        self.path = str(path)
        c = self.connect()
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS components(kind TEXT, version TEXT, body TEXT NOT NULL,
            PRIMARY KEY(kind,version));
        CREATE TABLE IF NOT EXISTS releases(id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
            snapshot TEXT NOT NULL, sha TEXT NOT NULL, parent INTEGER,
            published_at TEXT NOT NULL, received_at TEXT NOT NULL, actor TEXT NOT NULL,
            author TEXT NOT NULL, reason TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS head(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            release_id INTEGER REFERENCES releases(id));
        INSERT OR IGNORE INTO head VALUES(1,NULL);
        CREATE TABLE IF NOT EXISTS audit(release_id INTEGER PRIMARY KEY REFERENCES releases(id),
            actor TEXT NOT NULL, action TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(release_id INTEGER PRIMARY KEY REFERENCES releases(id),
            delivered INTEGER NOT NULL DEFAULT 0);
        CREATE TRIGGER IF NOT EXISTS releases_no_update BEFORE UPDATE ON releases
            BEGIN SELECT RAISE(ABORT,'immutable_release'); END;
        CREATE TRIGGER IF NOT EXISTS releases_no_delete BEFORE DELETE ON releases
            BEGIN SELECT RAISE(ABORT,'retained_release'); END;
        CREATE TRIGGER IF NOT EXISTS components_no_update BEFORE UPDATE ON components
            BEGIN SELECT RAISE(ABORT,'immutable_component'); END;
        CREATE TRIGGER IF NOT EXISTS components_no_delete BEFORE DELETE ON components
            BEGIN SELECT RAISE(ABORT,'retained_component'); END;
        ''')
        c.close()

    def connect(self):
        c = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA synchronous=FULL')
        return c

    def current(self):
        c = self.connect()
        try:
            return c.execute('SELECT release_id FROM head WHERE singleton=1').fetchone()[0]
        finally:
            c.close()

    def publish(self, snapshot, query, *, expected, request_id,
                actor='reviewer-demo', author='author-demo', role='safety_reviewer',
                received_at='2026-11-04T00:00:00Z', reason='synthetic publication',
                fail_at=None, hook=None):
        s, q = deepcopy(snapshot), deepcopy(query)
        if not can_publish(actor, author, role):
            raise PermissionError('independent_reviewer_required')
        if not request_id or not reason or not actor or not author:
            raise ValueError('missing_publication_metadata')
        instant(received_at)
        validate(s, q)
        payload = canonical(s)
        request_hash = digest([s, q, expected, actor, author, role, received_at, reason])
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT id,request_hash FROM releases WHERE request_id=?',
                                 (request_id,)).fetchone()
            if existing:
                if existing[1] != request_hash:
                    raise ValueError('idempotency_key_reused')
                c.rollback()
                return existing[0]
            current = c.execute('SELECT release_id FROM head WHERE singleton=1').fetchone()[0]
            if current != expected:
                raise ValueError('stale_parent')
            for key in VERSION_KEYS:
                version, body = s['versions'][key], canonical(s[key])
                old = c.execute('SELECT body FROM components WHERE kind=? AND version=?',
                                (key, version)).fetchone()
                if old and old[0] != body:
                    raise ValueError('version_content_changed:' + key)
                c.execute('INSERT OR IGNORE INTO components VALUES(?,?,?)', (key,version,body))
            now = datetime.now(timezone.utc).isoformat()
            rid = c.execute('''INSERT INTO releases(request_id,request_hash,snapshot,sha,parent,
                published_at,received_at,actor,author,reason) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (request_id,request_hash,payload,sha256(payload.encode()).hexdigest(),expected,
                 now,received_at,actor,author,reason)).lastrowid
            if fail_at == 'after_objects':
                raise RuntimeError('injected_after_objects')
            c.execute('INSERT INTO audit VALUES(?,?,?)', (rid,actor,'publish'))
            if fail_at == 'after_audit':
                raise RuntimeError('injected_after_audit')
            c.execute('INSERT INTO outbox(release_id) VALUES(?)', (rid,))
            c.execute('UPDATE head SET release_id=? WHERE singleton=1', (rid,))
            if hook:
                hook(rid)  # test barrier before commit, no external network side effect
            if fail_at == 'before_commit':
                raise RuntimeError('injected_before_commit')
            c.commit()
            return rid
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def pin(self, release_id=None):
        c = self.connect()
        try:
            c.execute('BEGIN')
            rid = release_id if release_id is not None else c.execute(
                'SELECT release_id FROM head WHERE singleton=1').fetchone()[0]
            row = c.execute('SELECT snapshot,sha,published_at,received_at FROM releases WHERE id=?',
                            (rid,)).fetchone()
            if not row:
                raise ValueError('release_unavailable')
            payload, expected_hash, published, received = row
            if sha256(payload.encode()).hexdigest() != expected_hash:
                raise ValueError('release_digest_mismatch')
            s = json.loads(payload)
            for key in VERSION_KEYS:
                obj = c.execute('SELECT body FROM components WHERE kind=? AND version=?',
                                (key,s['versions'][key])).fetchone()
                if not obj or obj[0] != canonical(s[key]):
                    raise ValueError('component_integrity_mismatch')
            c.commit()
            return {'release_id':rid, 'snapshot':s, 'published_at':published, 'received_at':received}
        finally:
            c.close()

    def query(self, query, pinned=None):
        p = None
        try:
            p = pinned or self.pin()
            q = deepcopy(query)
            q['versions'] = dict(p['snapshot']['versions'])
            validate(p['snapshot'], q)
            result = plan(p['snapshot'], q)
            observed = self.current()  # fresh read after search, not the pinned transaction
            result.update(release_id=p['release_id'], observed_head=observed,
                          freshness='current_at_check' if observed == p['release_id'] else 'stale',
                          checked_at=datetime.now(timezone.utc).isoformat())
            return result
        except ValueError as exc:
            return {'query_id':query.get('id'), 'status':'unknown', 'reason':str(exc),
                    'metrics':None, 'freshness':'unavailable',
                    'release_id':p['release_id'] if p else None,
                    'versions':p['snapshot']['versions'] if p else {}}

    def status(self, query, a, b, release_id=None):
        try:
            p = self.pin(release_id)
        except ValueError as exc:
            return {'state':'unknown','reason':str(exc),'release_id':release_id,'versions':{}}
        q = deepcopy(query); q['versions'] = dict(p['snapshot']['versions'])
        try:
            validate(p['snapshot'], q)
        except ValueError as exc:
            return {'state':'unknown','reason':str(exc),'release_id':p['release_id']}
        r = assess_segment(p['snapshot'], q, a, b)
        r.update(release_id=p['release_id'], published_at=p['published_at'],
                 received_at=p['received_at'], restrictions=p['snapshot']['airspace']['restrictions'])
        return r

    def counts(self):
        c=self.connect()
        try:
            return {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
                    for t in ('components','releases','audit','outbox')}
        finally:
            c.close()


def consume_notification(catalog, last_seen, notification_id):
    """Notification is a hint; reconcile authoritative head, including missed events."""
    head = catalog.current()
    if head is None:
        return last_seen
    return max(last_seen or 0, head)
