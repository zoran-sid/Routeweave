"""Transaction failures, concurrent connections, and real LQ/ZC integration."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from publication import Catalog, prepare_risk, consume_notification, bind, validate
from scenarios import fixture, restriction
from risk import compile_profiles


def integrated():
    s,q=fixture()
    profiles=[{'id':'LQ-hotspot','box':[[30,35,0],[70,65,0]],'source':'synthetic-zqo-lq',
               'periods':[{'valid':q['window'],'E':0.875,'C':0.8}]}]
    return prepare_risk(s,q,profiles)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Catalog(Path(self.tmp.name)/'catalog.sqlite')
        self.s,self.q=integrated()
        self.v1=self.db.publish(self.s,self.q,expected=None,request_id='first')

    def changed(self, revoked=False):
        s,q=deepcopy(self.s),deepcopy(self.q)
        r=restriction(box=[[45,35,0],[55,65,100]])
        if revoked:r['state']='revoked'
        s['airspace']['restrictions']=[r]
        return bind(s,q)

    def test_real_lq_zc_query_and_q2(self):
        r=self.db.query(self.q)
        self.assertEqual(r['status'],'feasible')
        self.assertEqual(r['versions'],self.s['versions'])
        self.assertEqual(r['freshness'],'current_at_check')
        e=r['segments'][0]
        state=self.db.status(self.q,e['from'],e['to'])
        self.assertEqual(state['state'],'allowed')
        self.assertEqual(state['release_id'],self.v1)

    def test_q2_normal_keeps_snapshot_provenance(self):
        r = self.db.status(self.q, self.q['start'], self.q['start'], self.v1)
        self.assertEqual(r['state'], 'allowed')
        self.assertEqual(r['versions'], self.s['versions'])
        self.assertEqual(r['provenance_state'], 'available')
        self.assertEqual(r['component_sources']['risk_data'], self.s['risk_data']['source'])
        self.assertEqual(r['compiled_window'], self.q['window'])
        self.assertTrue(r['published_at'])

    def test_q2_window_failure_keeps_old_release_versions(self):
        s, q = self.changed()
        self.db.publish(s, q, expected=self.v1, request_id='second')
        wrong = deepcopy(self.q); wrong['window'][1] = '2026-11-04T00:20:00Z'
        r = self.db.status(wrong, wrong['start'], wrong['goal'], self.v1)
        self.assertEqual((r['state'], r['reason']), ('unknown', 'risk_window_mismatch'))
        self.assertEqual(r['versions'], self.s['versions'])
        self.assertNotEqual(r['versions'], s['versions'])
        self.assertEqual(r['release_id'], self.v1)
        self.assertEqual(r['compiled_window'], self.q['window'])
        self.assertEqual(r['restrictions'], self.s['airspace']['restrictions'])
        self.assertEqual(r['component_sources']['scene'], self.s['scene']['source'])

    def test_q2_missing_release_marks_provenance_unavailable(self):
        r = self.db.status(self.q, self.q['start'], self.q['goal'], 999)
        self.assertEqual(r['reason'], 'release_unavailable')
        self.assertEqual(r['release_id'], 999)
        self.assertEqual(r['versions'], {})
        self.assertEqual(r['provenance_state'], 'unavailable')
        self.assertIsNone(r['source_release'])
        self.assertIsNone(r['published_at'])
        self.assertEqual(r['component_sources'], {})

    def test_failed_attempt_audit_survives_rollback_and_reopen(self):
        s, q = self.changed(); before = self.db.counts()
        with self.assertRaisesRegex(RuntimeError, 'injected_before_commit'):
            self.db.publish(s, q, expected=self.v1, request_id='failed', fail_at='before_commit')
        reopened = Catalog(self.db.path)
        self.assertEqual(reopened.counts(), before)
        self.assertEqual(reopened.current(), self.v1)
        failure = reopened.failures()[0]
        self.assertEqual(failure['request_id'], 'failed')
        self.assertEqual(failure['expected_parent'], self.v1)
        self.assertEqual(failure['error'], 'injected_before_commit')
        self.assertTrue(failure['snapshot_sha'])
        c = reopened.connect()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('DELETE FROM failed_attempts')
        finally:
            c.close()

    def test_failure_audit_unavailable_is_explicit(self):
        c = self.db.connect()
        c.execute("CREATE TRIGGER fail_failure_audit BEFORE INSERT ON failed_attempts BEGIN SELECT RAISE(ABORT,'sink_down'); END")
        c.close(); s, q = self.changed()
        with self.assertRaisesRegex(RuntimeError, 'failure_audit_unavailable.*injected.*sink_down'):
            self.db.publish(s, q, expected=self.v1, request_id='failed', fail_at='before_commit')
        self.assertEqual(self.db.current(), self.v1)

    def test_reader_pins_old_release_across_commit(self):
        pin=self.db.pin(); s,q=self.changed()
        v2=self.db.publish(s,q,expected=self.v1,request_id='second')
        old=self.db.query(self.q,pin); new=self.db.query(q)
        self.assertEqual(old['release_id'],self.v1)
        self.assertEqual(old['freshness'],'stale')
        self.assertEqual(new['release_id'],v2)
        self.assertNotEqual(old['versions']['airspace'],new['versions']['airspace'])

    def test_uncommitted_head_not_visible_to_other_connection(self):
        ready,release=threading.Event(),threading.Event(); errors=[]
        s,q=self.changed()
        def hook(rid):
            ready.set()
            if not release.wait(5):raise TimeoutError('test_barrier')
        def writer():
            try:self.db.publish(s,q,expected=self.v1,request_id='second',hook=hook)
            except BaseException as e:errors.append(e)
        t=threading.Thread(target=writer);t.start()
        try:
            self.assertTrue(ready.wait(5))
            self.assertEqual(self.db.pin()['release_id'],self.v1)
        finally:release.set();t.join(5)
        self.assertFalse(t.is_alive());self.assertFalse(errors)
        self.assertNotEqual(self.db.current(),self.v1)

    def test_each_failure_rolls_back_release_audit_outbox_and_head(self):
        counts=self.db.counts();s,q=self.changed()
        for point in ('after_objects','after_audit','before_commit'):
            with self.subTest(point=point),self.assertRaises(RuntimeError):
                self.db.publish(s,q,expected=self.v1,request_id=point,fail_at=point)
            self.assertEqual(self.db.current(),self.v1)
            self.assertEqual(self.db.counts(),counts)

    def test_actual_audit_write_error_aborts_publication(self):
        c=self.db.connect()
        c.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON audit BEGIN SELECT RAISE(ABORT,'audit_unavailable'); END")
        c.close();s,q=self.changed();counts=self.db.counts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.publish(s,q,expected=self.v1,request_id='audit-fail')
        self.assertEqual(self.db.counts(),counts)
        self.assertEqual(self.db.current(),self.v1)

    def test_concurrent_publishers_only_one_parent_wins(self):
        barrier=threading.Barrier(2);out=[]
        def writer(name):
            s,q=self.changed();barrier.wait(5)
            try:out.append(('ok',self.db.publish(s,q,expected=self.v1,request_id=name)))
            except ValueError as e:out.append(('error',str(e)))
        ts=[threading.Thread(target=writer,args=(str(i),)) for i in range(2)]
        for t in ts:t.start()
        for t in ts:t.join(6)
        self.assertEqual(sum(x[0]=='ok' for x in out),1)
        self.assertIn(('error','stale_parent'),out)
        self.assertEqual(self.db.counts()['releases'],2)

    def test_idempotent_retry_returns_original_after_later_publish(self):
        s,q=self.changed();self.db.publish(s,q,expected=self.v1,request_id='second')
        head=self.db.current();counts=self.db.counts()
        self.assertEqual(self.db.publish(self.s,self.q,expected=None,request_id='first'),self.v1)
        self.assertEqual(self.db.current(),head);self.assertEqual(self.db.counts(),counts)

    def test_same_request_id_different_payload_rejected(self):
        s,q=self.changed()
        with self.assertRaisesRegex(ValueError,'idempotency'):
            self.db.publish(s,q,expected=self.v1,request_id='first')

    def test_same_component_version_cannot_change_content(self):
        s=deepcopy(self.s);s['scene']['source']='silently-mutated'
        with self.assertRaisesRegex(ValueError,'version_content_changed'):
            self.db.publish(s,self.q,expected=self.v1,request_id='bad')

    def test_mixed_versions_rejected(self):
        s=deepcopy(self.s);s['airspace']['version']='wrong'
        with self.assertRaisesRegex(ValueError,'version_mismatch'):
            self.db.publish(s,self.q,expected=self.v1,request_id='bad')

    def test_missing_data_does_not_publish(self):
        s=deepcopy(self.s);s['risk_data']['complete']=False
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.db.publish(s,self.q,expected=self.v1,request_id='bad')

    def test_reviewer_policy(self):
        for kwargs in ({'actor':'author-demo'},{'role':'dispatcher'}):
            with self.assertRaises(PermissionError):
                self.db.publish(self.s,self.q,expected=self.v1,request_id='bad',**kwargs)

    def test_release_and_components_immutable(self):
        c=self.db.connect()
        try:
            for sql in ('UPDATE releases SET reason=\'changed\'','DELETE FROM releases',
                        'UPDATE components SET body=\'{}\'','DELETE FROM components'):
                with self.assertRaises(sqlite3.IntegrityError):c.execute(sql)
        finally:c.close()

    def test_history_reopens_after_restart(self):
        s,q=self.changed();self.db.publish(s,q,expected=self.v1,request_id='second')
        reopened=Catalog(self.db.path)
        self.assertEqual(reopened.pin(self.v1)['snapshot'],self.s)
        self.assertEqual(reopened.counts()['outbox'],2)

    def test_republish_rollback_has_new_release_identity(self):
        s,q=self.changed();v2=self.db.publish(s,q,expected=self.v1,request_id='second')
        v3=self.db.publish(self.s,self.q,expected=v2,request_id='rollback',reason='reviewed recovery')
        self.assertGreater(v3,v2)
        self.assertEqual(self.db.pin()['snapshot']['versions'],self.s['versions'])
        self.assertEqual(self.db.pin(v2)['snapshot'],s)

    def test_notifications_reconcile_duplicates_reordering_and_loss(self):
        s,q=self.changed();v2=self.db.publish(s,q,expected=self.v1,request_id='second')
        for hint in (v2,v2,self.v1,None):
            self.assertEqual(consume_notification(self.db,self.v1,hint),v2)

    def test_risk_compiled_window_cannot_be_reused(self):
        q=deepcopy(self.q);q['window'][1]='2026-11-04T00:20:00Z'
        self.assertEqual(self.db.query(q)['reason'],'risk_window_mismatch')
        s=deepcopy(self.s);del s['risk_data']['compiled_window']
        s,q=bind(s,self.q)
        with self.assertRaisesRegex(ValueError,'risk_window_mismatch'):validate(s,q)

    def test_revoke_and_expiry_are_distinct_from_publish_time(self):
        s,q=self.changed();v2=self.db.publish(s,q,expected=self.v1,request_id='restricted')
        before=self.db.query(q)
        s,q=self.changed(revoked=True)
        self.db.publish(s,q,expected=v2,request_id='revoked')
        after=self.db.query(q)
        self.assertLess(after['metrics']['length_m'],before['metrics']['length_m'])
        # Uncompiled ZC input permits another covered task window.
        s,q=fixture();s['airspace']['restrictions']=[restriction(start='2026-11-03T23:50:00Z',end=q['departure'])]
        s,q=bind(s,q)
        self.db.publish(s,q,expected=self.db.current(),request_id='expired')
        self.assertEqual(self.db.query(q)['status'],'feasible')

    def test_unknown_when_no_release_or_uncovered_time(self):
        empty=Catalog(Path(self.tmp.name)/'empty.sqlite')
        self.assertEqual(empty.query(self.q)['status'],'unknown')
        self.assertEqual(empty.status(self.q,self.q['start'],self.q['goal'])['state'],'unknown')
        q=deepcopy(self.q);q['window'][1]='2026-11-04T02:00:00Z'
        self.assertEqual(self.db.query(q)['status'],'unknown')
        self.assertEqual(self.db.query(q)['versions'],self.s['versions'])

    def test_notification_absence_does_not_hide_new_head(self):
        s,q=self.changed();v2=self.db.publish(s,q,expected=self.v1,request_id='second')
        self.assertEqual(self.db.query(q)['release_id'],v2)
        self.assertEqual(self.db.counts()['outbox'],2)


if __name__=='__main__':unittest.main()
