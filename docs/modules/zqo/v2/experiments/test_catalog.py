"""Concurrent connections, real commit/rollback and reconstructed historical rows."""
import copy
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
import catalog as cat


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'catalog.db'
        cat.initialize(self.path)
        self.c = cat.connect(self.path)
        self.payload = cat.fixture(buildings=3, grid=3)
        self.pub(self.payload, 'r0', None)

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def pub(self, payload, rid, expected, **kw):
        return cat.publish(self.c, payload, request_id='req-'+rid, release_id=rid,
                           expected=expected, provenance=cat.provenance(), **kw)

    def count(self, table):
        return self.c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def test_shared_layers_and_history_reopen(self):
        before = cat.snapshot(self.c, 'r0')
        self.pub(cat.changed(self.payload), 'r1', 'r0')
        self.assertEqual(self.count('layer_component'), 6)
        self.assertEqual(self.count('building'), 3)
        self.c.close(); self.c = cat.connect(self.path)
        old = cat.snapshot(self.c, 'r0')
        self.assertEqual(before['layers'], old['layers'])
        self.assertEqual(old['freshness'], 'historical')
        self.assertEqual(cat.snapshot(self.c)['release_id'], 'r1')
        self.assertEqual(self.c.execute("SELECT count(*) FROM resolved_feature WHERE query_release_id='r1'").fetchone()[0], 12)
        self.assertEqual(self.c.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_failpoints_are_atomic_and_audited(self):
        names = ('release','release_layer','layer_component','release_component','feature','building',
                 'terrain_post','airspace_restriction','airspace_event','audit_event','outbox','publish_request')
        before = {t:self.count(t) for t in names}
        for point in ('after_draft','after_components','after_events','after_head','before_commit'):
            with self.subTest(point=point):
                with self.assertRaisesRegex(RuntimeError, 'injected:'):
                    self.pub(cat.changed(self.payload), 'fail-'+point, 'r0', failpoint=point)
                self.assertEqual(before, {t:self.count(t) for t in names})
                self.assertEqual(cat.head(self.c), 'r0')
        self.assertEqual(self.count('failed_attempt'), 5)
        self.assertEqual(self.c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_two_publishers_one_winner(self):
        barrier = threading.Barrier(2)
        outcomes = []; errors = []
        def worker(i):
            c = cat.connect(self.path)
            try:
                barrier.wait(timeout=5)
                cat.publish(c, cat.changed(self.payload, i), request_id=f'parallel-{i}', release_id=f'r{i}',
                            expected='r0', provenance=cat.provenance())
                outcomes.append('success')
            except cat.Conflict:
                outcomes.append('conflict')
            except Exception as e:
                errors.append(repr(e))
            finally:
                c.close()
        threads = [threading.Thread(target=worker,args=(i,)) for i in (1,2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(outcomes, ['success','conflict'])
        self.assertEqual(self.count('release'), 2)
        self.assertEqual(self.count('failed_attempt'), 1)
        failure = dict(self.c.execute('SELECT * FROM failed_attempt').fetchone())
        self.assertEqual(failure['observed_release_id'], cat.head(self.c))

    def test_wal_reader_and_new_reader_visibility(self):
        reader = cat.connect(self.path)
        reader.execute('BEGIN')
        first = cat.snapshot(reader)
        observations = []
        def hook(stage):
            if stage == 'after_head':
                other = cat.connect(self.path)
                observations.append(cat.snapshot(other)['release_id']); other.close()
        self.pub(cat.changed(self.payload), 'r1', 'r0', hook=hook)
        self.assertEqual(observations, ['r0'])
        self.assertEqual(cat.snapshot(reader)['layers'], first['layers'])
        self.assertEqual(cat.snapshot(reader)['observed_head'], 'r0')
        reader.execute('COMMIT')
        self.assertEqual(cat.snapshot(reader)['release_id'], 'r1')
        reader.close()

    def test_lost_reply_idempotency_and_key_reuse(self):
        payload = cat.changed(self.payload)
        with self.assertRaisesRegex(RuntimeError, 'after_commit'):
            self.pub(payload,'r1','r0',failpoint='after_commit')
        self.assertEqual(self.count('failed_attempt'), 0)
        self.assertTrue(self.pub(payload,'r1','r0')['replayed'])
        self.assertEqual(self.count('outbox'), 2)
        with self.assertRaisesRegex(cat.Conflict, 'idempotency'):
            self.pub(cat.changed(self.payload,2),'r1','r0')
        self.assertEqual(self.count('release'), 2)

    def test_revoke_is_new_version_and_event(self):
        self.pub(cat.changed(self.payload, revoke=True), 'r1', 'r0')
        self.assertEqual(cat.snapshot(self.c,'r0')['layers']['airspace']['airspace_restriction'][0]['state'], 'published')
        self.assertEqual(cat.snapshot(self.c,'r1')['layers']['airspace']['airspace_restriction'][0]['state'], 'revoked')
        row = self.c.execute("SELECT * FROM airspace_event WHERE action='revoke'").fetchone()
        self.assertEqual(row['release_id'], 'r1')
        self.assertIsNotNone(row['previous_event_id'])
        # Reinstatement creates a new physical airspace owner so the event points at this publication.
        self.pub(self.payload, 'r2', 'r1')
        self.assertEqual(self.c.execute("SELECT release_id FROM airspace_event WHERE event_id='r2:NF-0'").fetchone()[0], 'r2')
        self.assertEqual(self.c.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_provenance_window_missing_release_and_no_safe_default(self):
        bad = cat.provenance(); bad['risk_window'][1]='2026-12-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'compilation window'):
            cat.publish(self.c,self.payload,request_id='bad',release_id='bad',expected='r0',provenance=bad)
        with self.assertRaises(LookupError): cat.snapshot(self.c,'missing')
        self.assertEqual(self.count('release'),1)
        self.assertEqual(cat.snapshot(self.c)['manifest']['provenance'],cat.provenance())

    def test_invalid_rows_rollback_and_source_coverage(self):
        bad = copy.deepcopy(self.payload)
        bad['exposure']['exposure_zone'][0]['q']=0.9
        with self.assertRaises(sqlite3.IntegrityError): self.pub(bad,'bad','r0')
        bad = copy.deepcopy(self.payload); bad['sources']['source']=[]
        with self.assertRaisesRegex(ValueError,'manifest'): self.pub(bad,'bad2','r0')
        self.assertEqual(cat.head(self.c),'r0')
        self.assertEqual(self.count('failed_attempt'),2)

    def test_reference_metadata_drift_is_visible_failure(self):
        self.c.execute("UPDATE source SET license='changed' WHERE source_id='SRC-SYN'")
        with self.assertRaisesRegex(ValueError,'component drift: sources'):
            cat.snapshot(self.c,'r0')
        with self.assertRaisesRegex(ValueError,'component drift: sources'):
            self.pub(cat.changed(self.payload),'r1','r0')
        self.assertEqual(cat.head(self.c),'r0')

    def test_publish_role_denied_without_mutation(self):
        with self.assertRaises(PermissionError): self.pub(self.payload,'denied','r0',actor='UNKNOWN')
        self.assertEqual(self.count('failed_attempt'),1)
        self.assertEqual(self.count('release'),1)

    def test_own_sql_guards(self):
        statements = ["UPDATE release_component SET component_id='bad'",
            "DELETE FROM layer_component", "UPDATE publish_request SET request_hash='bad'",
            "DELETE FROM current_release", "DELETE FROM outbox", "DELETE FROM component_source",
            "UPDATE release_layer SET layer_version='other'", "UPDATE outbox SET release_id='other'"]
        for sql in statements:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError): self.c.execute(sql)
        self.c.execute("UPDATE outbox SET attempts=1,delivered_at='2026-11-06T10:00:00Z'")
        self.assertEqual(self.c.execute('SELECT attempts FROM outbox').fetchone()[0],1)

    def test_shared_airspace_operation_a_resolves_owner(self):
        p = copy.deepcopy(self.payload)
        p['exposure']['exposure_zone'][0]['exposure_e'] = .6
        p['exposure']['exposure_zone'][0]['q'] = .24
        self.pub(p, 'r1', 'r0')
        self.c.execute('BEGIN')
        snap = cat.snapshot(self.c, 'r1')
        owner = next(m['owner_release_id'] for m in snap['mappings'] if m['layer']=='airspace')
        self.assertEqual(owner, 'r0')
        params = dict(release_id=owner, win_lo='2026-11-05T08:05:00Z', win_hi='2026-11-05T08:15:00Z',
                      x0=100., x1=300., y0=100., y1=140., z0=40., z1=90.)
        self.assertEqual(len(self.c.execute(cat.fx.op_a_sql(), params).fetchall()), 3)
        self.c.execute('COMMIT')
        self.assertTrue(self.pub(self.payload, 'r0', None)['replayed'])
        self.assertEqual(cat.head(self.c), 'r1')

    def test_release_insert_and_completeness_guards(self):
        self.c.execute('BEGIN')
        try:
            row = dict(self.c.execute("SELECT * FROM release WHERE release_id='r0'").fetchone())
            row['release_id'] = 'illegal'
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'insert as draft'):
                cat.insert(self.c, 'release', row)
            cat.fx.create_release(self.c, 'incomplete')
            cat.fx.add_layers(self.c, 'incomplete', complete=False)
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'incomplete layer'):
                cat.fx.publish(self.c, 'incomplete')
            with self.assertRaises(sqlite3.IntegrityError):
                self.c.execute("UPDATE current_release SET release_id='incomplete'")
        finally:
            self.c.execute('ROLLBACK')

    def test_full_copy_exports_equal_shared(self):
        other_path = Path(self.tmp.name)/'full.db'; cat.initialize(other_path); other = cat.connect(other_path)
        for i in range(3):
            p = self.payload if i == 0 else cat.changed(self.payload,i)
            cat.publish(other,p,request_id=f'q{i}',release_id=f'r{i}',expected=None if i==0 else f'r{i-1}',
                        mode='full',provenance=cat.provenance())
            if i: self.pub(p,f'r{i}',f'r{i-1}')
            self.assertEqual(cat.snapshot(other,f'r{i}')['layers'],cat.snapshot(self.c,f'r{i}')['layers'])
        self.assertEqual(other.execute('SELECT count(*) FROM building').fetchone()[0],9)
        other.close()


if __name__ == '__main__':
    unittest.main()
