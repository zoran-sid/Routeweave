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
    lineage = s.get("lineage")
    if lineage is not None:
        if lineage["query_versions"] != s["versions"]:
            raise ValueError("lineage_version_mismatch")
        if lineage["compiled_window"] != s["risk_data"].get("compiled_window"):
            raise ValueError("lineage_window_mismatch")
        if digest(lineage["source_snapshot"]) != lineage["source_sha256"]:
            raise ValueError("lineage_source_digest_mismatch")
        source = lineage['source_snapshot']
        if lineage['source_release'] != {'versions': source['versions'], 'manifest': source['manifest']}:
            raise ValueError('lineage_source_release_mismatch')
        mapping = lineage['version_mapping']
        if set(mapping) != set(VERSION_KEYS) or any(
                mapping[k]['query_version'] != s['versions'][k]
                or any(source['versions'].get(dep) != value
                       for dep, value in mapping[k]['source_versions'].items())
                for k in VERSION_KEYS):
            raise ValueError('lineage_mapping_mismatch')
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
        CREATE TABLE IF NOT EXISTS failed_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT, expected_parent INTEGER, actor TEXT, attempted_at TEXT NOT NULL,
            snapshot_sha TEXT, error_type TEXT NOT NULL, error TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS failed_attempts_no_update BEFORE UPDATE ON failed_attempts
            BEGIN SELECT RAISE(ABORT,'immutable_failure_audit'); END;
        CREATE TRIGGER IF NOT EXISTS failed_attempts_no_delete BEFORE DELETE ON failed_attempts
            BEGIN SELECT RAISE(ABORT,'retained_failure_audit'); END;
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

    def publish(self, snapshot, query, *, expected, request_id, **options):
        """Commit a release or persist its failed attempt after rollback.

        A failed-attempt row is not a committed release/audit/outbox row. If this
        independent write also fails, expose both failures to the caller.
        """
        try:
            return self._publish(snapshot, query, expected=expected,
                                 request_id=request_id, **options)
        except Exception as exc:
            try:
                self._record_failure(snapshot, expected, request_id,
                                     options.get('actor', 'reviewer-demo'), exc)
            except Exception as audit_error:
                raise RuntimeError('publication_failed_and_failure_audit_unavailable:'
                                   + str(exc) + '; audit:' + str(audit_error)) from exc
            raise

    def _record_failure(self, snapshot, expected, request_id, actor, error):
        try:
            snapshot_sha = digest(snapshot)
        except (TypeError, ValueError):
            snapshot_sha = None  # Invalid JSON has no canonical payload digest.
        c = self.connect()
        try:
            c.execute("""INSERT INTO failed_attempts(request_id,expected_parent,actor,
                attempted_at,snapshot_sha,error_type,error) VALUES(?,?,?,?,?,?,?)""",
                (request_id, expected, actor, datetime.now(timezone.utc).isoformat(),
                 snapshot_sha, type(error).__name__, str(error)))
        finally:
            c.close()

    def failures(self):
        c = self.connect()
        c.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in c.execute('SELECT * FROM failed_attempts ORDER BY id')]
        finally:
            c.close()

    def _publish(self, snapshot, query, *, expected, request_id,
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

    @staticmethod
    def trace(p):
        """Snapshot provenance is available even when the task is invalid."""
        if p is None:
            return {'versions': {}, 'provenance_state': 'unavailable',
                    'component_sources': {}, 'source_release': None,
                    'version_mapping': None, 'compiled_window': None,
                    'source_sha256': None, 'published_at': None, 'received_at': None}
        s = p['snapshot']; lineage = s.get('lineage', {})
        return deepcopy({'versions': s['versions'], 'provenance_state': 'available',
                         'published_at': p['published_at'], 'received_at': p['received_at'],
                         'component_sources': {k: s[k].get('source') for k in VERSION_KEYS},
                         'source_release': lineage.get('source_release'),
                         'version_mapping': lineage.get('version_mapping'),
                         'source_sha256': lineage.get('source_sha256'),
                         'compiled_window': s['risk_data'].get('compiled_window')})

    def query(self, query, pinned=None):
        p = None
        try:
            p = pinned or self.pin()
            q = deepcopy(query)
            q['versions'] = dict(p['snapshot']['versions'])
            validate(p['snapshot'], q)
            result = plan(p['snapshot'], q)
            observed = self.current()  # fresh read after search, not the pinned transaction
            result.update(self.trace(p))
            result.update(release_id=p['release_id'], observed_head=observed,
                          freshness='current_at_check' if observed == p['release_id'] else 'stale',
                          checked_at=datetime.now(timezone.utc).isoformat())
            return result
        except ValueError as exc:
            return {'query_id':query.get('id'), 'status':'unknown', 'reason':str(exc),
                    'metrics':None, 'freshness':'unavailable',
                    'release_id':p['release_id'] if p else None,
                    **self.trace(p)}

    def status(self, query, a, b, release_id=None):
        try:
            p = self.pin(release_id)
        except ValueError as exc:
            return {'state':'unknown','reason':str(exc),'release_id':release_id, **self.trace(None)}
        q = deepcopy(query); q['versions'] = dict(p['snapshot']['versions'])
        try:
            validate(p['snapshot'], q)
        except ValueError as exc:
            return {'state':'unknown','reason':str(exc),'release_id':p['release_id'], **self.trace(p),
                    'restrictions':deepcopy(p['snapshot']['airspace']['restrictions'])}
        r = assess_segment(p['snapshot'], q, a, b)
        r.update(self.trace(p))
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
