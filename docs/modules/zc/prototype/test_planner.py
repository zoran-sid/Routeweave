import unittest
from copy import deepcopy
from math import dist
from planner import assess_segment, clip_segment, edge_info, overlap, plan
from scenarios import bind, cases, fixture, restriction


class GeometryTests(unittest.TestCase):
    def test_interior_crossing_and_tangent(self):
        box = [[4, 4, 4], [6, 6, 6]]
        for a, b in [((0, 5, 5), (10, 5, 5)), ((4.5, 5, 5), (5.5, 5, 5)),
                     ((0, 4, 4), (10, 4, 4)), ((5, 5, 5), (5, 5, 5))]:
            self.assertIsNotNone(clip_segment(a, b, box))
        self.assertIsNone(clip_segment((0, 5, 8), (10, 5, 8), box))

    def test_buffer_and_corner_cut(self):
        box = [[4, 4, 0], [6, 6, 10]]
        self.assertIsNotNone(clip_segment((0, 0, 5), (10, 10, 5), box))
        self.assertIsNone(clip_segment((0, 2, 5), (10, 2, 5), box))
        self.assertIsNotNone(clip_segment((0, 2, 5), (10, 2, 5), box, 2))

    def test_time_half_open_and_future_activation(self):
        window = ["2026-11-04T00:00:00Z", "2026-11-04T00:10:00Z"]
        self.assertFalse(overlap(["2026-11-03T23:00:00Z", window[0]], window))
        self.assertFalse(overlap([window[1], "2026-11-04T01:00:00Z"], window))
        self.assertTrue(overlap(["2026-11-04T00:05:00Z", window[1]], window))


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.s, self.q = fixture()

    def search(self):
        bind(self.s, self.q)
        return plan(self.s, self.q)

    def test_open_analytical_solution(self):
        self.s["scene"]["obstacles"] = []
        self.s["risk_data"]["zones"] = []
        self.s["planner_config"]["lambda_risk"] = 0
        r = self.search()
        self.assertEqual(r["status"], "feasible")
        self.assertAlmostEqual(r["metrics"]["length_m"], 100)
        self.assertAlmostEqual(r["metrics"]["cost"], 1)

    def test_building_forces_vertical_detour(self):
        self.s["risk_data"]["zones"] = []
        r = self.search()
        self.assertEqual(r["status"], "feasible")
        self.assertGreaterEqual(max(p[2] for p in r["path"]), 40)
        self.assertGreater(r["metrics"]["length_m"], 100)

    def test_all_cases_match_dijkstra(self):
        for name, s, q in cases():
            with self.subTest(case=name):
                a, d = plan(s, q), plan(s, q, "dijkstra")
                self.assertEqual(a["status"], d["status"])
                if a["status"] == "feasible":
                    self.assertAlmostEqual(a["metrics"]["cost"], d["metrics"]["cost"], places=9)
                    for segment in a["segments"]:
                        self.assertEqual(segment["state"], "allowed")

    def test_weight_sweep_reduces_proxy(self):
        results = {}
        for weight in (0, 8):
            self.s["planner_config"]["lambda_risk"] = weight
            results[weight] = self.search()["metrics"]
        self.assertGreater(results[8]["length_m"], results[0]["length_m"])
        self.assertLess(results[8]["risk_proxy"], results[0]["risk_proxy"])

    def test_hard_risk_cannot_be_bought_off(self):
        self.s["planner_config"]["lambda_risk"] = 0
        self.s["risk_data"]["zones"][0]["q"] = .95
        r = self.search()
        self.assertEqual(r["status"], "feasible")
        self.assertTrue(all(e["q_max"] < .9 for e in r["segments"]))

    def test_window_active_no_fly_blocks_all_levels(self):
        self.s["airspace"]["restrictions"] = [restriction(start="2026-11-04T00:05:00Z")]
        self.assertEqual(self.search()["status"], "infeasible")

    def test_expired_and_revoked_restrictions(self):
        r = restriction(end="2026-11-04T00:00:00Z", start="2026-11-03T23:00:00Z")
        self.s["airspace"]["restrictions"] = [r]
        self.assertEqual(self.search()["status"], "feasible")
        r["valid"] = list(self.q["window"])
        r["state"] = "revoked"
        self.assertEqual(self.search()["status"], "feasible")

    def test_ceiling_checks_segment_interior(self):
        self.s["airspace"]["restrictions"] = [restriction("height_limit", [[40, 40, 0], [60, 60, 100]])]
        self.s["scene"]["obstacles"] = []
        bind(self.s, self.q)
        self.assertEqual(assess_segment(self.s, self.q, [20, 50, 40], [80, 50, 40])["state"], "forbidden")
        self.assertEqual(assess_segment(self.s, self.q, [20, 50, 28], [80, 50, 28])["state"], "allowed")

    def test_missing_stale_and_mixed_are_unknown(self):
        for component in ("scene", "airspace", "risk_data"):
            s, q = fixture()
            s[component]["complete"] = False
            bind(s, q)
            self.assertEqual(plan(s, q)["status"], "unknown")
        self.s["airspace"]["valid"][1] = "2026-11-04T00:05:00Z"
        self.assertEqual(self.search()["status"], "unknown")
        self.s, self.q = fixture()
        self.s["airspace"]["version"] = "mixed"
        self.assertEqual(plan(self.s, self.q)["status"], "unknown")

    def test_query_version_mismatch(self):
        self.q["versions"]["risk_model"] = "wrong"
        self.assertEqual(plan(self.s, self.q)["reason"], "query_snapshot_mismatch")

    def test_unknown_risk_wall_does_not_prove_infeasible(self):
        _, s, q = next(c for c in cases() if c[0] == "unknown_wall")
        self.assertEqual(plan(s, q)["status"], "unknown")

    def test_known_detour_around_unknown_is_feasible(self):
        self.s["risk_data"]["zones"][0]["q"] = None
        self.assertEqual(self.search()["status"], "feasible")

    def test_search_budget_and_deadline(self):
        self.assertEqual(plan(self.s, self.q, max_expansions=1)["status"], "unknown")
        self.q["window"][1] = "2026-11-04T00:00:01Z"
        self.assertEqual(self.search()["reason"], "selected_route_exceeds_window")

    def test_invalid_and_off_grid_inputs(self):
        for point in ([1, 50, 20], [-10, 50, 20], [float("nan"), 50, 20]):
            self.q["start"] = point
            self.assertEqual(plan(self.s, self.q)["status"], "unknown")
        self.s, self.q = fixture()
        self.s["scene"]["obstacles"][0]["box"][1][2] = None
        self.assertEqual(self.search()["status"], "unknown")

    def test_blocked_and_zero_length_endpoints(self):
        self.q["start"] = [50, 50, 20]
        self.assertEqual(self.search()["status"], "infeasible")
        self.q["start"] = list(self.q["goal"])
        r = self.search()
        self.assertEqual(r["status"], "feasible")
        self.assertEqual(r["metrics"]["length_m"], 0)

    def test_update_invalidates_old_route_and_replans(self):
        old = self.search()
        self.s["airspace"]["restrictions"] = [restriction(box=[[45, 35, 0], [55, 65, 100]])]
        bind(self.s, self.q)
        self.assertTrue(any(assess_segment(self.s, self.q, a, b)["state"] != "allowed"
                            for a, b in zip(old["path"], old["path"][1:])))
        new = plan(self.s, self.q)
        self.assertEqual(new["status"], "feasible")
        self.assertNotEqual(old["versions"]["airspace"], new["versions"]["airspace"])
        self.assertNotEqual(old["path"], new["path"])

    def test_snapshot_not_mutated(self):
        before = deepcopy((self.s, self.q))
        plan(self.s, self.q)
        self.assertEqual(before, (self.s, self.q))

    def test_heuristic_consistency_on_all_allowed_edges(self):
        bind(self.s, self.q)
        from planner import OFFSETS
        from itertools import product
        scale = self.s["planner_config"]["length_scale_m"]
        goal = self.q["goal"]
        for a in product(range(0, 101, 10), range(0, 101, 10), range(10, 71, 10)):
            for delta in OFFSETS:
                b = tuple(v + d * 10 for v, d in zip(a, delta))
                e = edge_info(self.s, self.q, a, b)
                if e["state"] == "allowed":
                    self.assertLessEqual(dist(a, goal) / scale, e["cost"] + dist(b, goal) / scale + 1e-12)


if __name__ == "__main__":
    unittest.main()
