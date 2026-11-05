"""Unit tests for the YHT data model, queries, indexes and quality rules."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import export_lq  # noqa: E402
import export_zc  # noqa: E402
import quality  # noqa: E402
import query as q  # noqa: E402
import yht_model as m  # noqa: E402
from cache import QueryCache  # noqa: E402
from store import GridIndex, SQLiteStore  # noqa: E402

WINDOW = {"start": "2026-11-05T08:05:00Z", "end": "2026-11-05T08:15:00Z"}
LATER = {"start": "2026-11-05T12:00:00Z", "end": "2026-11-05T12:10:00Z"}


class GeometryTest(unittest.TestCase):
    def test_flat_terrain(self):
        s = m.seal(m.scene())
        self.assertEqual(len(s["terrain"]["posts"]), 31 * 31)
        self.assertTrue(all(p["z"] == 0 for p in s["terrain"]["posts"]))

    def test_release_versions_and_manifest(self):
        s = m.seal(m.scene())
        self.assertEqual(len(s["versions"]), 5)
        self.assertEqual(m.verify_release(s), [])
        s["buildings"][0]["name"] = "changed without reseal"
        problems = m.verify_release(s)
        self.assertIn("version_mismatch:scene", problems)
        self.assertIn("manifest_content_hash_mismatch", problems)

    def test_polygon_rules(self):
        self.assertFalse(quality.ring_is_closed([[0, 0], [1, 0], [1, 1]]))
        self.assertTrue(quality.ring_is_closed([[0, 0], [1, 0], [1, 1], [0, 0]]))
        self.assertFalse(quality.ring_is_simple(
            [[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]))

    def test_segment_box_distance(self):
        box = [[10, 10, 10], [20, 20, 20]]
        self.assertAlmostEqual(q.segment_box_distance(
            [0, 15, 15], [5, 15, 15], box), 5.0)
        self.assertEqual(q.segment_box_distance(
            [10, 15, 15], [20, 15, 15], box), 0.0)

    def test_segment_hits_building_unknown_top(self):
        b = dict(m.buildings()[0])
        b["top_z"] = None
        self.assertTrue(q.segment_hits_building(
            [30, 30, 50], [40, 40, 50], b))


class QueryTest(unittest.TestCase):
    def setUp(self):
        self.s = m.seal(m.scene())

    def test_q2_allowed(self):
        r = q.query_segment(self.s, [20, 260, 80], [90, 260, 80],
                            WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "allowed", r["reasons"])
        self.assertEqual(r["blocked_by"], [])

    def test_q2_building(self):
        r = q.query_segment(self.s, [240, 40, 20], [300, 40, 20],
                            WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "forbidden")
        self.assertIn("building:B-010", r["blocked_by"])

    def test_q2_hospital_ceiling(self):
        r = q.query_segment(self.s, [325, 105, 65], [335, 105, 65],
                            WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "forbidden")
        self.assertIn("ceiling:HL-001", r["blocked_by"])

    def test_q2_below_ceiling_is_allowed(self):
        r = q.query_segment(self.s, [325, 105, 45], [335, 105, 45],
                            WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "allowed", r["reasons"] + r["blocked_by"])

    def test_q2_no_fly_activation(self):
        inside = ([140, 150, 80], [160, 150, 80])
        active = q.query_segment(self.s, *inside, WINDOW, self.s["versions"])
        self.assertIn("airspace:NF-002", active["blocked_by"])
        later = quality._reseal(self.s, lambda s: s["airspace"][1].update(
            {"valid": ["2026-11-05T08:30:00Z", "2026-11-05T09:00:00Z"]}))
        closed = q.query_segment(later, *inside, WINDOW, later["versions"])
        self.assertEqual(closed["status"], "allowed", closed["reasons"])

    def test_q2_version_mismatch(self):
        r = q.query_segment(
            self.s, [280, 120, 70], [370, 120, 70], WINDOW,
            dict(self.s["versions"], scene="mock-yht-scene-deadbeef"))
        self.assertEqual(r["status"], "unknown")
        self.assertTrue(any(x.startswith("version_mismatch") for x in r["reasons"]))

    def test_q1_clear(self):
        r = q.query_corridor(self.s, [20, 20, 140], [240, 220, 140], 15.0,
                             WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "clear", r["reasons"] + r["blocked_by"])

    def test_q1_blocked(self):
        r = q.query_corridor(self.s, [20, 20, 80], [240, 220, 80], 20.0,
                             WINDOW, self.s["versions"])
        self.assertEqual(r["status"], "blocked")
        self.assertTrue(r["blocked_by"])

    def test_q1_vertical_clearance(self):
        # Above B-010 (40 m) but the corridor's vertical radius still reaches it.
        low = q.query_corridor(self.s, [270, 40, 45], [330, 40, 45], 10.0,
                               WINDOW, self.s["versions"])
        high = q.query_corridor(self.s, [270, 40, 70], [330, 40, 70], 10.0,
                                WINDOW, self.s["versions"])
        self.assertIn("building:B-010", low["blocked_by"])
        self.assertNotIn("building:B-010", high["blocked_by"])

    def test_q1_height_limit_counts_vertical_buffer(self):
        # HL-001 caps this area at 60 m; the 5 m corridor radius is part of
        # the clearance, and contact at exactly 60 m remains clear.
        s = m.scene()
        s["buildings"] = []  # isolate the height cap from B-013
        s = m.seal(s)
        for z, expected in ((54.0, "clear"), (55.0, "clear"),
                            (55.1, "blocked")):
            r = q.query_corridor(s, [350, 120, z], [400, 120, z], 5.0,
                                 WINDOW, s["versions"])
            self.assertEqual(r["status"], expected, (z, r["blocked_by"]))
            if expected == "blocked":
                self.assertIn("airspace:HL-001", r["blocked_by"])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.s = m.seal(m.scene())
        self.store = SQLiteStore(self.s, ":memory:", fast=True)
        self.store.build()

    def tearDown(self):
        self.store.close()

    def test_stats_and_rtree(self):
        st = self.store.stats()
        self.assertEqual(st["buildings"], 25)
        self.assertEqual(st["coverage_tiles"], 36)
        rows = self.store.conn.execute(
            "EXPLAIN QUERY PLAN SELECT rid FROM rtree_building "
            "WHERE maxx>=? AND minx<=? AND maxy>=? AND miny<=? "
            "AND maxz>=? AND minz<=?",
            (0, 100, 0, 100, 0, 100)).fetchall()
        self.assertIn("VIRTUAL TABLE INDEX", " ".join(str(tuple(r)) for r in rows))

    def test_segment_parity_with_bruteforce(self):
        a, b = [280, 120, 70], [370, 120, 70]
        full = q.query_segment(self.s, a, b, WINDOW, self.s["versions"])
        indexed = self.store.segment_query(a, b, WINDOW, self.s["versions"])
        self.assertEqual(indexed["status"], full["status"])
        self.assertEqual(indexed["blocked_by"], full["blocked_by"])
        self.assertLess(indexed["candidates"], full["candidates"])

    def test_corridor_parity_with_bruteforce(self):
        a, b = [20, 20, 140], [240, 220, 140]
        full = q.query_corridor(self.s, a, b, 15.0, WINDOW, self.s["versions"])
        indexed = self.store.corridor_query(a, b, 15.0, WINDOW, self.s["versions"])
        self.assertEqual(indexed["status"], full["status"])
        self.assertEqual(indexed["blocked_by"], full["blocked_by"])

    def test_2d_index_is_conservative(self):
        a, b = [20, 190, 100], [50, 190, 100]  # above B-005 (18 m)
        full = self.store.segment_query(a, b, WINDOW, self.s["versions"], "3d")
        flat = self.store.segment_query(a, b, WINDOW, self.s["versions"], "2d")
        self.assertEqual(flat["status"], full["status"])
        self.assertGreaterEqual(flat["candidates"], full["candidates"])
        self.assertIn("B-005", [c["id"] for c in self.store.candidates_2d_z(
            (0, 180, 0), (60, 240, 160))])

    def test_wal_reader_during_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "store.sqlite")
            st = SQLiteStore(self.s, path, fast=False)
            st.build()
            st.conn.execute("PRAGMA journal_mode=WAL")
            reader = sqlite3.connect(path)
            writer = sqlite3.connect(path)
            try:
                writer.isolation_level = None
                writer.execute("BEGIN IMMEDIATE")
                writer.execute("UPDATE meta SET value=value WHERE key='scene_id'")
                count = reader.execute("SELECT COUNT(*) FROM building").fetchone()[0]
                self.assertEqual(count, 25)
                writer.commit()
                count = reader.execute("SELECT COUNT(*) FROM building").fetchone()[0]
                self.assertEqual(count, 25)
            finally:
                reader.close()
                writer.close()
                st.close()


class QualityTest(unittest.TestCase):
    def setUp(self):
        self.s = m.seal(m.scene())

    def test_baseline_is_clean(self):
        report = quality.check_scene(self.s)
        self.assertTrue(report["ok"], report["errors"][:3])
        self.assertEqual(report["counts"]["errors"], 0)

    def test_fault_injection(self):
        rows = quality.run_fault_injection()
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(r["detected"] for r in rows), rows)
        bad = quality._reseal(self.s, lambda s: s["ground_zones"][0].update(
            {"q": 0.01}))
        report = quality.check_scene(bad)
        self.assertTrue(any(e["rule"] == "ATTR-003" for e in report["errors"]),
                        report["errors"][:3])

    def test_unknown_height_blocks_clearance(self):
        faulty = quality._reseal(self.s, lambda s: s["buildings"][5].update(
            {"height_m": None, "top_z": None, "quality": "unknown"}))
        r = q.query_segment(faulty, [70, 200, 20], [150, 200, 20],
                            WINDOW, faulty["versions"])
        self.assertEqual(r["status"], "unknown")
        self.assertIn("unknown_height:B-006", r["reasons"])

    def test_incomplete_coverage_is_unknown(self):
        faulty = quality._reseal(self.s, lambda s: s["coverage"][14].update(
            {"complete": False}))
        r = q.query_segment(faulty, [250, 250, 20], [290, 250, 20],
                            WINDOW, faulty["versions"])
        self.assertEqual(r["status"], "unknown")
        self.assertIn("incomplete_coverage", r["reasons"])

    def test_mutation_queries(self):
        rows = quality.query_after_mutation()
        self.assertEqual(rows["missing_height"]["status"], "unknown")
        self.assertEqual(rows["incomplete_coverage"]["status"], "unknown")


class ExportTest(unittest.TestCase):
    def test_zc_export_rejects_unknown_risk(self):
        s = m.scene()
        s["ground_zones"][0].update(q=None, exposure_e=None, consequence_c=None)
        s = m.seal(s)
        with self.assertRaisesRegex(ValueError,
                                    "unknown_or_invalid_exposure:G-001"):
            export_zc.export_snapshot(
                s, WINDOW, ((0, 0, 10), (450, 450, 120)),
                (20, 20, 70), (420, 420, 70))

    def test_lq_profiles_reject_unknown_risk(self):
        s = m.scene()
        s["ground_zones"][0].update(q=None, exposure_e=None, consequence_c=None)
        s = m.seal(s)
        with self.assertRaisesRegex(ValueError,
                                    "unknown_or_invalid_exposure:G-001"):
            export_lq.profiles_from_scene(s)

    def test_zc_export_rejects_incomplete_coverage(self):
        s = m.scene()
        s["coverage"][0]["complete"] = False
        s = m.seal(s)
        with self.assertRaisesRegex(ValueError, "incomplete_coverage:T-00-00"):
            export_zc.export_snapshot(
                s, WINDOW, ((0, 0, 10), (450, 450, 120)),
                (20, 20, 70), (420, 420, 70))

    def test_zc_export_rejects_nonflat_terrain(self):
        s = m.scene()
        s["terrain"]["flat"] = False
        s["terrain"]["z"] = 20.0
        for post in s["terrain"]["posts"]:
            post["z"] = 20.0
        s = m.seal(s)
        with self.assertRaisesRegex(ValueError,
                                    "unsupported_terrain:only_flat_supported"):
            export_zc.export_snapshot(
                s, WINDOW, ((0, 0, 10), (450, 450, 120)),
                (20, 20, 70), (420, 420, 70))

    def test_zc_export_rejects_nonzero_flat_base(self):
        s = m.scene()
        s["terrain"]["z"] = 20.0
        for post in s["terrain"]["posts"]:
            post["z"] = 20.0
        s = m.seal(s)
        with self.assertRaisesRegex(ValueError,
                                    "unsupported_terrain:zero_base_required"):
            export_zc.export_snapshot(
                s, WINDOW, ((0, 0, 10), (450, 450, 120)),
                (20, 20, 70), (420, 420, 70))

    def test_export_binds_with_zc(self):
        s = m.seal(m.scene())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zc-export.json"
            payload = export_zc.write_export(
                s, WINDOW, ((0, 0, 10), (450, 450, 120)),
                (20, 20, 70), (420, 420, 70), path,
                repo_root=str(HERE.parents[3]))
            self.assertIsNone(payload["zc_report"]["preflight"])
            self.assertIsNotNone(payload["zc_report"]["plan"])
            self.assertEqual(
                payload["zc_report"]["plan"]["status"], "feasible")
            self.assertGreater(len(payload["snapshot"]["scene"]["obstacles"]), 0)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["snapshot"]["versions"],
                             payload["snapshot"]["versions"])

    def test_lq_profiles_keep_q_equal_e_times_c(self):
        s = m.seal(m.scene())
        profiles = export_lq.profiles_from_scene(s)
        self.assertEqual(len(profiles), len(s["ground_zones"]))
        by_id = {z["id"]: z for z in s["ground_zones"]}
        for profile in profiles:
            zone = by_id[profile["id"]]
            self.assertAlmostEqual(zone["q"],
                                   zone["exposure_e"] * zone["consequence_c"])
            self.assertEqual(profile["periods"][0]["valid"], list(s["valid"]))
            self.assertEqual(profile["source"], zone["source_id"])

    def test_lq_adapter_plans_on_exported_profiles(self):
        s = m.seal(m.scene())
        with tempfile.TemporaryDirectory() as tmp:
            payload = export_lq.write_export(Path(tmp) / "lq-export.json")
        report = payload["report"]
        self.assertIsNone(report["preflight"])
        self.assertEqual(report["plan"]["status"], "feasible")
        self.assertIsNotNone(report["plan"]["metrics"]["risk_proxy"])
        self.assertEqual(report["q2_assess"]["state"], "forbidden")


class CacheTest(unittest.TestCase):
    def test_hit_returns_a_copy(self):
        cache = QueryCache(capacity=4)
        calls = {"n": 0}

        def compute():
            calls["n"] += 1
            return {"status": "allowed", "nested": {"candidates": 1}}

        first = cache.get_or_compute("k", {"scene": "v1"}, compute)
        first["status"] = "tampered"
        second = cache.get_or_compute("k", {"scene": "v1"}, compute)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(second["status"], "allowed")
        self.assertEqual(cache.stats()["hits"], 1)

    def test_version_change_invalidates(self):
        cache = QueryCache(capacity=4)
        cache.get_or_compute("k", {"scene": "v1"}, lambda: {"ok": 1})
        cache.get_or_compute("k", {"scene": "v2"}, lambda: {"ok": 2})
        self.assertEqual(cache.stats()["invalidations"], 1)
        self.assertEqual(cache.stats()["misses"], 2)

    def test_lru_eviction(self):
        cache = QueryCache(capacity=2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.stats()["evictions"], 1)


class GridTest(unittest.TestCase):
    def test_grid_matches_bruteforce(self):
        s = m.seal(m.scene())
        grid = GridIndex(s)
        a, b = [20, 20, 80], [240, 220, 80]
        full = q.query_corridor(s, a, b, 15.0, WINDOW, s["versions"])
        fast = grid.corridor_query(a, b, 15.0, WINDOW, s["versions"])
        self.assertEqual(fast["status"], full["status"])
        self.assertEqual(fast["blocked_by"], full["blocked_by"])


if __name__ == "__main__":
    unittest.main()
