"""ZC v2 regression: query/result/trace/cache tables and the planner's data-access paths.

python3 -B -m unittest discover -s docs/modules/zc/v2/experiments -v
"""
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planner_io as io  # noqa: E402
import city  # noqa: E402
import invalidation as inv  # noqa: E402

cat = io.cat
TASK_WIN = ("2026-11-05T08:05:00Z", "2026-11-05T08:15:00Z")


class QueryTablesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="zc-test-")
        cls.pl, cls.boxes, _ = city.payload("S", seed=5)
        cls.c = city.database(str(Path(cls.tmp) / "t.db"), cls.pl)
        cls.tasks = city.tasks(3, cls.boxes, seed=9)

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        shutil.rmtree(cls.tmp)

    def pinned(self, release="R0", window=TASK_WIN):
        self.c.execute("BEGIN")
        try:
            return io.pin(self.c, release, window)
        finally:
            self.c.execute("COMMIT")

    def query_row(self, **over):
        row = dict(query_id="q-test-" + str(len(over)) + str(sorted(over.items()))[:20].replace(" ", ""),
                   release_id="R0", actor_id="DISPATCH", requested_at="2026-11-07T00:00:00Z",
                   window_lo=TASK_WIN[0], window_hi=TASK_WIN[1], start_x=0, start_y=0, start_z=100,
                   goal_x=40, goal_y=0, goal_z=100, planner_config="{}", config_hash=io.CONFIG_HASH,
                   algorithm="astar", access_path="sql_rtree", status="infeasible", reason="test",
                   freshness="current", graph_id=None)
        row.update(over)
        return row

    def assertRejected(self, table, row, message):
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            cat.insert(self.c, table, row)
        self.assertIn(message, str(ctx.exception))

    # --- query_run --------------------------------------------------------
    def test_query_requires_published_release_and_window(self):
        self.assertRejected("query_run", self.query_row(release_id="nope"), "covering the window")
        self.assertRejected("query_run", self.query_row(window_lo="2027-06-01T00:00:00Z",
                                                        window_hi="2027-06-01T00:10:00Z"), "covering the window")

    def test_query_requires_business_actor(self):
        self.assertRejected("query_run", self.query_row(actor_id="SYS"), "business actor")
        self.assertRejected("query_run", self.query_row(actor_id="OFF"), "business actor")

    def test_freshness_is_checked_against_head(self):
        self.assertRejected("query_run", self.query_row(freshness="historical"), "freshness")

    def test_query_and_results_are_append_only(self):
        cat.insert(self.c, "query_run", self.query_row(query_id="q-append"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE query_run SET status='feasible' WHERE query_id='q-append'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("DELETE FROM query_run WHERE query_id='q-append'")
        self.assertRejected("route_result", dict(query_id="q-append", length_m=1, time_s=1, risk_proxy=0, cost=1,
                                                 waypoints="[[0,0,100],[20,0,100]]"), "only feasible")

    # --- route_segment_source -------------------------------------------
    def test_segment_sources_must_match_release_window_and_dataset(self):
        p = self.pinned()
        zone = self.c.execute("SELECT rid, feature_id FROM feature WHERE release_id=? AND layer='exposure' LIMIT 1",
                              (p["owners"]["exposure"][1],)).fetchone()
        result = {"status": "feasible", "reason": "t", "length_m": 40, "time_s": 4, "risk_proxy": 0.1, "cost": 0.5,
                  "path": [[0, 0, 100], [20, 0, 100], [40, 0, 100]], "segment_sources": [[zone[1]], []]}
        qid = io.record_query(self.c, p, "DISPATCH", TASK_WIN, (0, 0, 100), (40, 0, 100), result, "sql_rtree",
                              {zone[1]: zone[0]})
        good = dict(query_id=qid, segment_no=2, component_id=p["owners"]["exposure"][0], zone_rid=zone[0],
                    dataset_id=p["dataset_id"])
        self.assertRejected("route_segment_source", {**good, "component_id": p["owners"]["scene"][0]},
                            "must match")
        self.assertRejected("route_segment_source", {**good, "segment_no": 3}, "beyond route")
        other = self.c.execute("SELECT rid FROM feature WHERE release_id=? AND layer='scene' LIMIT 1",
                               (p["owners"]["scene"][1],)).fetchone()[0]
        self.assertRejected("route_segment_source", {**good, "zone_rid": other}, "must match")
        cat.insert(self.c, "route_segment_source", good)
        rows = io.trace(self.c, qid)
        self.assertEqual(sorted({r["segment_no"] for r in rows}), [1, 2])
        self.assertTrue(all(r["dataset_window_lo"] <= r["task_window_lo"] for r in rows))

    def test_dataset_must_be_validated(self):
        p = self.pinned()
        self.c.execute("BEGIN IMMEDIATE")
        cat.insert(self.c, "risk_dataset", dict(dataset_id="D-draft", release_id="R0",
                   component_id=p["owners"]["exposure"][0], risk_model_id="lq-risk-v1", window_lo=cat.WIN[0],
                   window_hi=cat.WIN[1], compiler_version="t", created_by="AUTHOR", created_at="2026-11-07T00:00:00Z"))
        self.c.execute("COMMIT")
        g = {"domain": [[0, 0, 20], [40, 40, 120]], "nodes": 1, "edges": 0}
        with self.assertRaises(sqlite3.IntegrityError):
            io.store_graph(self.c, {**p, "dataset_id": "D-draft"}, g, TASK_WIN, payload_hash="0" * 64)

    # --- route_graph_cache ----------------------------------------------
    def test_cache_parent_rules_and_append_only(self):
        p = self.pinned()
        g = {"domain": [[0, 0, 20], [40, 40, 120]], "nodes": 1, "edges": 0}
        gid = io.store_graph(self.c, p, g, TASK_WIN, payload_hash="a" * 64)
        with self.assertRaises(sqlite3.IntegrityError):  # carried must keep the parent's payload
            io.store_graph(self.c, p, g, TASK_WIN, origin="carried", parent=gid, payload_hash="b" * 64)
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE route_graph_cache SET edge_count=5 WHERE graph_id=?", (gid,))
        bad = self.query_row(query_id="q-cache", access_path="graph_cache", graph_id=gid,
                             window_hi="2026-11-05T08:20:00Z")
        self.assertRejected("query_run", bad, "graph must match")

    # --- access paths -----------------------------------------------------
    def test_four_access_paths_agree_and_trace(self):
        c = self.c
        c.execute("BEGIN")
        doc = io.export_json(c, "R0", io.pin(c, "R0", self.tasks[0]["window"]))
        c.execute("COMMIT")
        cache = {}
        for t in self.tasks:
            res = {ap: io.plan_route(c, "R0", t["window"], t["start"], t["goal"], ap, cache=cache, json_doc=doc)
                   for ap in io.ACCESS_PATHS}
            first = res["sql_rtree"][0]
            for ap, (r, *_rest) in res.items():
                self.assertTrue(io.same_result(first, r), ap)
            hit = io.plan_route(c, "R0", t["window"], t["start"], t["goal"], "graph_cache", cache=cache)
            self.assertNotIn("build_ms", hit[3])
            self.assertTrue(io.same_result(first, hit[0]))
            r, p, zr, _, _ = res["sql_rtree"]
            qid = io.record_query(c, p, "DISPATCH", t["window"], t["start"], t["goal"], r, "sql_rtree", zr)
            if r["status"] == "feasible":
                self.assertEqual({x["segment_no"] for x in io.trace(c, qid)}, set(range(1, len(r["path"]))))


class CacheAcrossReleasesTest(unittest.TestCase):
    def test_carry_and_patch_equal_full_rebuild(self):
        tmp = tempfile.mkdtemp(prefix="zc-inval-test-")
        try:
            pl, boxes, _ = city.payload("M", seed=21, extra_air=[inv.OLD])
            c = city.database(str(Path(tmp) / "i.db"), pl)
            tasks = city.tasks(6, boxes, seed=22, region=inv.REGION, day=10, hours=(6, 18))
            cache = {}
            for t in tasks:
                io.plan_route(c, "R0", t["window"], t["start"], t["goal"], "graph_cache", cache=cache)
            pl1 = inv.add_restriction(pl, inv.NEW_ROWS)
            city.next_release(c, pl1, "R1", "R0")
            r1 = inv.transition(c, cache, tasks, "R0", "R1")
            city.next_release(c, inv.revoke(pl1, "NF-OLD"), "R2", "R1")
            r2 = inv.transition(c, cache, tasks, "R1", "R2")
            for r in (r1, r2):
                self.assertEqual(r["targeted_vs_full_mismatches"], 0)
                self.assertEqual(r["historical_cache_hits_prev"], len(tasks))
            self.assertEqual(r1["changed_restrictions"], ["NF-NEW"])
            self.assertEqual(r2["changed_restrictions"], ["NF-OLD"])
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            # a scene component change affects every graph: all rebuilt, still equal to full rebuild
            pl3 = inv.copy.deepcopy(inv.revoke(pl1, "NF-OLD"))
            b = pl3["scene"]["building"][0]
            b["top_z"] += 5.0
            b["height_m"] = b["top_z"] - b["base_z"]
            city.next_release(c, pl3, "R3", "R2")
            r3 = inv.transition(c, cache, tasks, "R2", "R3")
            self.assertEqual((r3["carried"], r3["patched"], r3["rebuilt"]), (0, 0, len(tasks)))
            self.assertEqual(r3["targeted_vs_full_mismatches"], 0)
            c.close()
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
