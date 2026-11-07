import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
import governance as gov

cat=gov.cat


class GovernanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'governance.db'
        cat.initialize(self.path)
        self.c=cat.connect(self.path)
        gov.seed(self.c)
        self.p=cat.fixture(buildings=3,grid=3)
        cat.publish(self.c,self.p,release_id='r0',expected=None,request_id='seed',provenance=cat.provenance())

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def test_referenced_model_immutable_new_version_preserves_history(self):
        original=cat.snapshot(self.c,'r0')['layers']['exposure']
        for sql in ("UPDATE risk_model SET formula='changed' WHERE risk_model_id='lq-risk-v1'",
                    "UPDATE risk_model SET risk_model_id='replacement' WHERE risk_model_id='lq-risk-v1'",
                    "UPDATE risk_model SET status='retired' WHERE risk_model_id='lq-risk-v1'",
                    "DELETE FROM risk_model WHERE risk_model_id='lq-risk-v1'"):
            with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError): self.c.execute(sql)
        model=dict(self.c.execute('SELECT * FROM risk_model').fetchone())
        model.update(risk_model_id='lq-risk-v2',model_version='2.0.0',formula='q = E * C; clarified assumption')
        cat.insert(self.c,'risk_model',model)
        p=copy.deepcopy(self.p);p['exposure']['risk_model']=[model]
        for e in p['exposure']['exposure_zone']: e['risk_model_id']='lq-risk-v2'
        cat.publish(self.c,p,release_id='r1',expected='r0',request_id='model-v2',provenance={**cat.provenance(),'risk_model_id':'lq-risk-v2'})
        self.assertEqual(cat.snapshot(self.c,'r0')['layers']['exposure'],original)
        self.assertEqual(cat.snapshot(self.c,'r1')['layers']['exposure']['risk_model'][0]['model_version'],'2.0.0')
        reopened=cat.connect(self.path)
        self.assertEqual(cat.snapshot(reopened,'r0')['layers']['exposure'],original);reopened.close()

    def test_disabled_model_control_is_separate_and_audited(self):
        before=cat.snapshot(self.c,'r0')
        cat.insert(self.c,'risk_model_control',dict(risk_model_id='lq-risk-v1',enabled=0,changed_by='REVIEWER',at=gov.AT,reason='synthetic policy'))
        self.assertEqual(cat.snapshot(self.c,'r0')['layers'],before['layers'])
        self.assertEqual(self.c.execute("SELECT count(*) FROM audit_event WHERE action='model_control'").fetchone()[0],1)
        gov.request_release(self.c,self.p,'r1','r0','AUTHOR','request')
        gov.approve(self.c,'request','REVIEWER')
        with self.assertRaisesRegex(PermissionError,'disabled'): gov.publish_approved(self.c,self.p,'r1','r0','request','REVIEWER')

    def test_native_missing_E_C_rolls_back(self):
        for key in ('E','C'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gov.compile_dataset(self.c,'r0','missing-'+key,{'G-0':[{'valid':list(cat.WIN),'E':None if key=='E' else .5,'C':None if key=='C' else .4}]})
        self.assertEqual(self.c.execute('SELECT count(*) FROM risk_dataset').fetchone()[0],0)

    def test_database_NULL_and_inconsistent_q_rejected(self):
        # Independent database checks: no use of Python's score() for these inputs.
        cat.fx.create_release(self.c,'draft')
        for i,(e,c,q) in enumerate(((None,.4,.2),(.5,None,.2),(.5,.4,.3))):
            rid=1000+i
            cat.fx.add_feature(self.c,rid,'draft','bad-'+str(i),'exposure')
            row=copy.deepcopy(self.p['exposure']['exposure_zone'][0]);row.pop('feature_id');row.update(rid=rid,zone_id='bad-'+str(i),exposure_e=e,consequence_c=c,q=q)
            with self.subTest(i=i),self.assertRaises(sqlite3.IntegrityError): cat.insert(self.c,'exposure_zone',row)

    def test_unknown_quality_does_not_become_validated_risk(self):
        p=copy.deepcopy(self.p);p['exposure']['exposure_zone'][0]['quality']='unknown'
        cat.publish(self.c,p,release_id='r1',expected='r0',request_id='unknown-quality',provenance=cat.provenance())
        with self.assertRaises(sqlite3.IntegrityError): gov.compile_dataset(self.c,'r1','unknown')
        self.assertEqual(self.c.execute('SELECT count(*) FROM risk_dataset').fetchone()[0],0)

    def test_complete_native_periods_compiled_and_frozen(self):
        zones=gov.compile_dataset(self.c,'r0','D')
        self.assertEqual(self.c.execute("SELECT state FROM risk_dataset WHERE dataset_id='D'").fetchone()[0],'validated')
        self.assertAlmostEqual(self.c.execute("SELECT q_max FROM derived_risk WHERE dataset_id='D' LIMIT 1").fetchone()[0],.2)
        for sql in ("UPDATE derived_risk SET q_max=.1", "DELETE FROM risk_input_period", "UPDATE risk_dataset SET compiler_version='changed'"):
            with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError): self.c.execute(sql)
        self.assertEqual(len(zones),6)

    def test_gap_cannot_be_validated_even_with_pass_label(self):
        profile={'G-0':[{'valid':[cat.WIN[0],'2026-06-01T00:00:00Z'],'E':.5,'C':.4}]}
        gov.compile_dataset(self.c,'r0','gap',profile,seal=False)
        with self.assertRaisesRegex(sqlite3.IntegrityError,'gap'):
            self.c.execute("UPDATE risk_dataset SET state='validated' WHERE dataset_id='gap'")
        cat.insert(self.c,'quality_check',dict(check_id='gap-failed',dataset_id='gap',rule='temporal_coverage',result='fail',checked_at=gov.AT,actor_id='REVIEWER',detail='{"reason":"missing tail"}'))
        self.assertEqual(self.c.execute("SELECT state FROM risk_dataset WHERE dataset_id='gap'").fetchone()[0],'draft')
        self.assertEqual(self.c.execute("SELECT result FROM quality_check WHERE check_id='gap-failed'").fetchone()[0],'fail')

    def test_period_overlap_rejected(self):
        periods=[{'valid':list(cat.WIN),'E':.5,'C':.4},{'valid':list(cat.WIN),'E':.5,'C':.4}]
        with self.assertRaises(sqlite3.IntegrityError): gov.compile_dataset(self.c,'r0','overlap',{'G-0':periods})

    def test_dataset_window_component_and_model_gate(self):
        for key,value in [('window_hi','2026-12-01T00:00:00Z'),('component_id','r0:scene'),('state','validated')]:
            row=dict(dataset_id='bad',release_id='r0',component_id='r0:exposure',risk_model_id='lq-risk-v1',window_lo=cat.WIN[0],window_hi=cat.WIN[1],compiler_version='lq-sql-1',created_by='AUTHOR',created_at=gov.AT,state='draft')
            row[key]=value
            with self.subTest(key=key),self.assertRaises(sqlite3.IntegrityError): cat.insert(self.c,'risk_dataset',row)

    def test_reader_filters_org_role_active_and_hides_columns(self):
        for actor in ('DISPATCH','OPER','REVIEWER'):
            rows=gov.read_audited(self.path,actor,'SELECT * FROM v_exposure_summary')
            self.assertEqual(len(rows),3)
            self.assertEqual(set(rows[0]),{'release_id','cell_x','cell_y','zone_count','display_proxy'})
        for actor in ('OTHER','OFF','SYS'):
            self.assertEqual(gov.read_audited(self.path,actor,'SELECT * FROM v_exposure_summary'),[])
        self.assertEqual(len(gov.read_audited(self.path,'REVIEWER','SELECT * FROM v_exposure_detail')),6)
        self.assertEqual(gov.read_audited(self.path,'DISPATCH','SELECT * FROM v_exposure_detail'),[])

    def test_sql_bypass_and_dml_are_rejected_and_denials_audited(self):
        for sql in ('SELECT * FROM exposure_zone', 'SELECT * FROM resolved_feature',
                    'WITH v_exposure_summary AS (SELECT * FROM exposure_zone) SELECT * FROM v_exposure_summary',
                    'SELECT * FROM v_exposure_summary UNION ALL SELECT * FROM v_exposure_summary',
                    'PRAGMA writable_schema=ON', 'UPDATE risk_model SET formula=\'x\''):
            with self.subTest(sql=sql),self.assertRaises(sqlite3.DatabaseError): gov.read_audited(self.path,'DISPATCH',sql)
        c=gov.reader(self.path,'DISPATCH')
        with self.assertRaises(sqlite3.DatabaseError): c.execute('SELECT * FROM exposure_zone')
        with self.assertRaises(sqlite3.DatabaseError): c.execute("UPDATE actor SET role='airspace_admin'")
        c.close()
        self.assertEqual(self.c.execute("SELECT count(*) FROM audit_event WHERE action='deny'").fetchone()[0],6)

    def test_policy_sensitivity_cap_is_enforced(self):
        self.c.execute("UPDATE access_policy SET max_sensitivity='public' WHERE policy_id='detail-admin'")
        self.assertEqual(gov.read_audited(self.path,'REVIEWER','SELECT * FROM v_exposure_detail'),[])

    def test_sensitive_source_is_filtered_without_mutating_old_release(self):
        source=copy.deepcopy(self.p['sources']['source'][0])
        source.update(source_id='SRC-SENSITIVE',sensitivity='sensitive')
        cat.insert(self.c,'source',source)
        p=copy.deepcopy(self.p);p['sources']['source'].append(source)
        p['exposure']['exposure_zone'][0]['source_id']='SRC-SENSITIVE'
        cat.publish(self.c,p,release_id='r1',expected='r0',request_id='sensitive',provenance=cat.provenance())
        rows=gov.read_audited(self.path,'DISPATCH','SELECT * FROM v_exposure_summary')
        # The first 200m cell in r1 now has only one eligible zone and is suppressed.
        self.assertEqual(len([r for r in rows if r['release_id']=='r0']),3)
        self.assertEqual(len([r for r in rows if r['release_id']=='r1']),2)

    def test_author_cannot_approve_and_operator_cannot_approve(self):
        gov.request_release(self.c,self.p,'r1','r0','AUTHOR','req')
        for reviewer in ('AUTHOR','OPER','OFF','OTHER'):
            with self.subTest(reviewer=reviewer),self.assertRaises(sqlite3.IntegrityError): gov.approve(self.c,'req',reviewer)
        gov.approve(self.c,'req','REVIEWER')
        gov.publish_approved(self.c,self.p,'r1','r0','req','REVIEWER')
        self.assertEqual(cat.head(self.c),'r1')
        self.assertEqual(self.c.execute("SELECT actor_id FROM audit_event WHERE event_id='audit:r1'").fetchone()[0],'REVIEWER')

    def test_dispatcher_cannot_author_release_request(self):
        with self.assertRaises(sqlite3.IntegrityError):
            gov.request_release(self.c,self.p,'r1','r0','DISPATCH','denied-author')

    def test_approval_binds_payload_and_is_immutable(self):
        gov.request_release(self.c,self.p,'r1','r0','AUTHOR','req');gov.approve(self.c,'req','REVIEWER')
        with self.assertRaises(PermissionError): gov.publish_approved(self.c,cat.changed(self.p),'r1','r0','req','REVIEWER')
        with self.assertRaises(sqlite3.IntegrityError): self.c.execute("UPDATE governance_approval SET reviewer_id='AUTHOR'")
        self.assertEqual(cat.head(self.c),'r0')

    def test_lineage_and_reverse_invalidation_query(self):
        gov.compile_dataset(self.c,'r0','D');gov.lineage(self.c,'D')
        rows=self.c.execute("WITH RECURSIVE affected(kind,id) AS (VALUES('source','SRC-SYN') UNION SELECT l.to_kind,l.to_id FROM lineage_edge l JOIN affected a ON l.from_kind=a.kind AND l.from_id=a.id) SELECT id FROM affected WHERE kind='dataset'").fetchall()
        self.assertEqual([r[0] for r in rows],['D'])
        with self.assertRaises(sqlite3.IntegrityError): self.c.execute("UPDATE lineage_edge SET tool_version='other'")
        with self.assertRaises(sqlite3.IntegrityError):
            cat.insert(self.c,'lineage_edge',dict(edge_id='bad',from_kind='source',from_id='MISSING',to_kind='dataset',to_id='D',activity='compiled_from',tool_version='x',at=gov.AT))

    def test_audit_and_quality_are_append_only(self):
        gov.compile_dataset(self.c,'r0','D')
        for table in ('audit_event','quality_check'):
            with self.subTest(table=table),self.assertRaises(sqlite3.IntegrityError): self.c.execute('DELETE FROM '+table)

if __name__=='__main__': unittest.main()
