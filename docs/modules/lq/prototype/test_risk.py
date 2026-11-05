import unittest
from copy import deepcopy
from risk import score, compile_profiles, evaluate, can_publish, fixture, plan, assess_segment

T0='2026-11-04T00:00:00Z'
T5='2026-11-04T00:05:00Z'
T10='2026-11-04T00:10:00Z'

def region(E=.875, C=.8):
    return [{'id':'commercial','box':[[30,35,0],[70,65,100]],'source':'synthetic-lq-v1',
             'periods':[{'valid':[T0,T10],'E':E,'C':C}]}]

class RiskTests(unittest.TestCase):
    def setUp(self):
        self.s, self.q = fixture()
        self.s['scene']['obstacles'] = []
        from risk import bind
        self.s, self.q = bind(self.s, self.q)
    def assess(self, profiles, a=(30,50,20), b=(70,50,20)):
        return evaluate(self.s,self.q,profiles,a,b)
    def test_product(self): self.assertAlmostEqual(score(.875,.8),.7)
    def test_equal_population_different_consequence(self):
        self.assertGreater(score(.8,.9),score(.8,.2))
    def test_invalid_numeric_inputs(self):
        for x in [-.1,1.1,float('nan'),float('inf'),True,'0.8']:
            with self.subTest(x=x): self.assertEqual(self.assess(region(x))['state'],'unknown')
    def test_unknown(self): self.assertEqual(self.assess(region(None))['state'],'unknown')
    def test_missing_profiles(self): self.assertEqual(self.assess([])['state'],'unknown')
    def test_hard_threshold_inclusive(self):
        self.assertEqual(self.assess(region(.9,1))['state'],'forbidden')
    def test_below_threshold(self): self.assertEqual(self.assess(region(.899,1))['state'],'allowed')
    def test_flying_higher_does_not_remove_ground_risk(self):
        self.assertAlmostEqual(self.assess(region(),(30,50,70),(70,50,70))['q_max'],.7)
    def test_buffer_contact(self):
        self.assertAlmostEqual(self.assess(region(),(20,30,20),(80,30,20))['q_max'],.7)
    def test_outside_footprint(self):
        self.assertEqual(self.assess(region(),(20,29,20),(80,29,20))['q_max'],.05)
    def test_gap_unknown(self):
        p=region(); p[0]['periods'][0]['valid']=[T0,T5]
        self.assertEqual(self.assess(p)['state'],'unknown')
    def test_future_peak(self):
        p=region(.1,1); p[0]['periods']=[{'valid':[T0,T5],'E':.1,'C':1},
                                                    {'valid':[T5,T10],'E':.95,'C':1}]
        self.assertEqual(self.assess(p)['state'],'forbidden')
    def test_half_open_end(self):
        p=region(); p[0]['periods'].append({'valid':[T10,'2026-11-04T00:20:00Z'],'E':1,'C':1})
        self.assertEqual(self.assess(p)['state'],'allowed')
    def test_known_hazard_overrides_gap(self):
        p=region(.95,1); p[0]['periods'][0]['valid']=[T0,T5]
        self.assertEqual(self.assess(p)['state'],'forbidden')
    def test_background_outside_unknown_region(self):
        self.assertEqual(self.assess(region(None),(0,0,20),(10,0,20))['state'],'allowed')
    def test_model_and_data_rebound_without_mutation(self):
        before=deepcopy(self.s); s,q=compile_profiles(self.s,self.q,region())
        self.assertEqual(self.s,before)
        self.assertNotEqual(s['versions']['risk_data'],self.s['versions']['risk_data'])
        self.assertNotEqual(s['versions']['risk_model'],self.s['versions']['risk_model'])
        self.assertEqual(s['versions'],q['versions'])
    def test_version_mismatch_rejected(self):
        s,q=compile_profiles(self.s,self.q,region()); q['versions']['risk_data']='old'
        self.assertEqual(assess_segment(s,q,(0,0,20),(10,0,20))['state'],'unknown')
    def test_nonnegative_additive_and_search_agreement(self):
        s,q=compile_profiles(self.s,self.q,region()); s['planner_config']['lambda_risk']=8
        from risk import bind
        s,q=bind(s,q)
        a,d=plan(s,q),plan(s,q,'dijkstra')
        self.assertEqual(a['status'],'feasible')
        self.assertAlmostEqual(a['metrics']['cost'],d['metrics']['cost'])
        self.assertAlmostEqual(a['metrics']['risk_proxy'],sum(e['risk_proxy'] for e in a['segments']))
        self.assertTrue(all(e['risk_proxy']>=0 for e in a['segments']))
    def test_publication_separation(self):
        self.assertFalse(can_publish('lq','lq','safety_reviewer'))
        self.assertFalse(can_publish('reviewer','lq','dispatcher'))
        self.assertTrue(can_publish('reviewer','lq','safety_reviewer'))

if __name__=='__main__': unittest.main()
