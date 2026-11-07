"""Checks that the v2 unified schema loads and enforces its documented rules.

Run from the repository root:
    python3 -B -m unittest discover -s docs/v2/schema -v
"""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures as fx  # noqa: E402

ENTITIES = {
    "release", "release_layer", "source", "coverage_tile", "feature", "building",
    "terrain_surface", "terrain_post", "airspace_restriction", "airspace_event",
    "exposure_zone", "risk_model", "actor", "access_policy", "lineage_edge", "audit_event",
    "layer_component", "release_component", "component_source", "current_release",
    "publish_request", "failed_attempt", "outbox",
    "risk_model_control", "risk_dataset", "risk_input_period", "derived_risk", "quality_check",
    "governance_request", "governance_approval",
    "query_run", "route_result", "route_segment_source", "route_graph_cache",
}
WIN = ("2026-11-05T08:05:00Z", "2026-11-05T08:15:00Z")
CORRIDOR = {"x0": 100.0, "x1": 300.0, "y0": 100.0, "y1": 140.0, "z0": 40.0, "z1": 90.0}


def published_release(conn, release_id="rel-1", rid0=1):
    fx.create_release(conn, release_id)
    fx.add_layers(conn, release_id)
    fx.add_building(conn, rid0, release_id, "B-001", (0, 0, 50, 50), 0.0, 60.0)
    fx.add_airspace(conn, rid0 + 1, release_id, "NF-001", (150, 90, 200, 150),
                    ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"))
    fx.add_exposure(conn, rid0 + 2, release_id, "GZ-001", (0, 0, 600, 600), 0.5, 0.4)
    fx.publish(conn, release_id)


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.conn = fx.connect()
        fx.base(self.conn)

    def tearDown(self):
        self.conn.close()

    def assertAborts(self, sql, params=(), message=None):
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(sql, params)
        if message:
            self.assertIn(message, str(ctx.exception))

    # --- structure -------------------------------------------------------
    def test_all_dictionary_entities_exist(self):
        names = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'rtree_%'")}
        self.assertEqual(names, ENTITIES)

    def test_valid_fixture_passes_foreign_key_check(self):
        published_release(self.conn)
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_tile_and_terrain_ids_repeat_across_releases(self):
        for rel in ("rel-1", "rel-2"):
            fx.create_release(self.conn, rel)
            self.conn.execute(
                "INSERT INTO coverage_tile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel, "scene", "T-00-00", 0, 0, fx.box_wkt(0, 0, 100, 100), 1, "assumed",
                 "SRC-SYN", "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", fx.sha(rel)))
            self.conn.execute(
                "INSERT INTO terrain_surface (release_id, terrain_id, surface_type, bounds_wkt,"
                " post_spacing_m, vertical_datum, flat, min_z, max_z, source_id, quality,"
                " valid_lo, valid_hi, checksum) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel, "TER-001", "grid", fx.box_wkt(0, 0, 600, 600), 20.0, "local-z0", 1, 0, 0,
                 "SRC-SYN", "assumed", "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z",
                 fx.sha(rel + "t")))
        self.assertEqual(self.conn.execute("SELECT count(*) FROM coverage_tile").fetchone()[0], 2)

    # --- constraints -----------------------------------------------------
    def test_foreign_key_rejects_unknown_source(self):
        fx.create_release(self.conn, "rel-1")
        with self.assertRaises(sqlite3.IntegrityError):
            fx.add_feature(self.conn, 1, "rel-1", "B-001", "building", source_id="SRC-NONE")

    def test_check_constraints_reject_inconsistent_values(self):
        fx.create_release(self.conn, "rel-1")
        fx.add_feature(self.conn, 1, "rel-1", "B-001", "building")
        self.assertAborts(
            "INSERT INTO building (rid, footprint_wkt, solid_wkt, bbox_min_x, bbox_min_y,"
            " bbox_max_x, bbox_max_y, base_z, top_z, height_m, footprint_source, height_source,"
            " height_method, is_landmark) VALUES (1,'p','s',0,0,1,1,0,60,59,'SRC-SYN','SRC-SYN',"
            "'assumed',0)", message="CHECK")
        with self.assertRaises(sqlite3.IntegrityError):
            fx.add_exposure(self.conn, 2, "rel-1", "GZ-001", (0, 0, 10, 10), 0.5, 0.4, q=0.3)
        with self.assertRaises(sqlite3.IntegrityError):
            fx.add_airspace(self.conn, 3, "rel-1", "HL-001", (0, 0, 10, 10),
                            ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"),
                            kind="height_limit", ceiling_m=None)
        with self.assertRaises(sqlite3.IntegrityError):
            fx.add_airspace(self.conn, 4, "rel-1", "NF-002", (0, 0, 10, 10),
                            ("2026-11-05T09:00:00Z", "2026-11-05T08:00:00Z"))
        self.assertAborts(
            "UPDATE release SET content_hash = 'XYZ' WHERE release_id = 'rel-1'", message="CHECK")

    def test_feature_layer_must_match_subtype(self):
        fx.create_release(self.conn, "rel-1")
        self.assertAborts(
            "INSERT INTO feature (rid, release_id, feature_id, layer, feature_type, source_id,"
            " quality, valid_lo, valid_hi, recorded_at, sensitivity, geom_kind) VALUES"
            " (1,'rel-1','B-1','airspace','building','SRC-SYN','assumed','2026-01-01T00:00:00Z',"
            "'2027-01-01T00:00:00Z','2026-11-01T00:00:00Z','internal','polyhedral')",
            message="CHECK")

    def test_subtype_row_must_match_feature_type(self):
        fx.create_release(self.conn, "rel-1")
        fx.add_feature(self.conn, 1, "rel-1", "NF-001", "airspace")
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.conn.execute(
                "INSERT INTO building (rid, footprint_wkt, solid_wkt, bbox_min_x, bbox_min_y,"
                " bbox_max_x, bbox_max_y, base_z, top_z, height_m, footprint_source,"
                " height_source, height_method, is_landmark) VALUES (1,'p','s',0,0,1,1,0,10,10,"
                "'SRC-SYN','SRC-SYN','assumed',0)")
        self.assertIn("feature_type must be building", str(ctx.exception))

    # --- release lifecycle ----------------------------------------------
    def test_publish_requires_all_five_layers(self):
        fx.create_release(self.conn, "rel-1")
        self.conn.execute(
            "DELETE FROM release_layer WHERE release_id = 'rel-1'")
        fx.add_layers(self.conn, "rel-1")
        self.conn.execute("DELETE FROM release_layer WHERE layer = 'sources'")
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            fx.publish(self.conn, "rel-1")
        self.assertIn("five layers", str(ctx.exception))

    def test_illegal_status_transition_rejected(self):
        published_release(self.conn)
        self.conn.execute("UPDATE release SET status = 'superseded' WHERE release_id = 'rel-1'")
        self.assertAborts("UPDATE release SET status = 'published' WHERE release_id = 'rel-1'",
                          message="illegal status transition")
        self.assertAborts("UPDATE release SET status = 'draft', published_at = NULL"
                          " WHERE release_id = 'rel-1'")

    def test_published_content_is_immutable(self):
        published_release(self.conn)
        self.assertAborts("UPDATE building SET top_z = 99, height_m = 99 WHERE rid = 1",
                          message="immutable")
        self.assertAborts("UPDATE airspace_restriction SET state = 'revoked',"
                          " revoked_at = '2026-11-05T08:30:00Z' WHERE rid = 2",
                          message="immutable")
        self.assertAborts("DELETE FROM feature WHERE rid = 3", message="immutable")
        self.assertAborts("UPDATE release SET manifest = '{}' WHERE release_id = 'rel-1'",
                          message="immutable")
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            fx.add_building(self.conn, 9, "rel-1", "B-009", (0, 0, 5, 5), 0.0, 5.0)
        self.assertIn("not draft", str(ctx.exception))

    def test_audit_and_events_are_append_only(self):
        published_release(self.conn)
        self.conn.execute(
            "INSERT INTO audit_event (event_id, at, actor_id, action, object_kind, object_id,"
            " release_id, result) VALUES ('AU-1','2026-11-05T08:00:00Z','A-ADMIN','query',"
            "'route','R-1','rel-1','success')")
        self.assertAborts("UPDATE audit_event SET result = 'denied'", message="append-only")
        self.assertAborts("DELETE FROM audit_event", message="append-only")

        def event(eid, ts, prev=None):
            self.conn.execute(
                "INSERT INTO airspace_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (eid, "rel-1", "NF-001", "publish", ts, ts, "A-ADMIN", "SRC-SYN",
                 fx.sha(eid), "synthetic", prev))

        event("EV-2", "2026-11-05T08:00:00Z")
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            event("EV-1", "2026-11-05T07:00:00Z", "EV-2")
        self.assertIn("monotonic", str(ctx.exception))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO airspace_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("EV-X", "rel-1", "NF-404", "publish", "2026-11-05T09:00:00Z",
                 "2026-11-05T09:00:00Z", "A-ADMIN", "SRC-SYN", fx.sha("x"), "r", None))

    # --- indexes and operation A ----------------------------------------
    def test_rtree_rows_are_maintained_by_triggers(self):
        published_release(self.conn)
        for table, rtree in (("building", "rtree_building"),
                             ("airspace_restriction", "rtree_airspace"),
                             ("exposure_zone", "rtree_exposure")):
            base = self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            idx = self.conn.execute(f"SELECT count(*) FROM {rtree}").fetchone()[0]
            self.assertEqual(base, idx, table)

    def test_operation_a_returns_only_active_overlapping_restrictions(self):
        fx.create_release(self.conn, "rel-1")
        fx.add_layers(self.conn, "rel-1")
        box = (150, 90, 200, 150)
        rows = [
            ("NF-HIT", box, ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"), {}),
            ("NF-ENDS-AT-START", box, ("2026-11-05T07:00:00Z", "2026-11-05T08:05:00Z"), {}),
            ("NF-STARTS-AT-END", box, ("2026-11-05T08:15:00Z", "2026-11-05T09:00:00Z"), {}),
            ("NF-REVOKED", box, ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"),
             {"state": "revoked"}),
            ("NF-ELSEWHERE", (900, 900, 950, 950),
             ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"), {}),
            ("HL-BELOW", box, ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"),
             {"kind": "height_limit", "ceiling_m": 120.0}),
            ("HL-ABOVE", box, ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"),
             {"kind": "height_limit", "ceiling_m": 60.0}),
            ("NF-HIGH", box, ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"),
             {"floor_z": 100.0}),
        ]
        for i, (rid_name, b, eff, extra) in enumerate(rows, start=1):
            fx.add_airspace(self.conn, i, "rel-1", rid_name, b, eff, **extra)
        fx.publish(self.conn, "rel-1")
        fx.create_release(self.conn, "rel-0")
        fx.add_airspace(self.conn, 50, "rel-0", "NF-HIT", box,
                        ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"))

        params = dict(CORRIDOR, release_id="rel-1", win_lo=WIN[0], win_hi=WIN[1])
        hits = [r[0] for r in self.conn.execute(fx.op_a_sql(), params)]
        # half-open windows: ending at window start or starting at window end do not overlap;
        # a height limit at 60 m forbids the 40–90 m corridor, one at 120 m does not.
        self.assertEqual(hits, ["HL-ABOVE", "NF-HIT"])

        plan = " ".join(r[3] for r in self.conn.execute("EXPLAIN QUERY PLAN " + fx.op_a_sql(), params))
        # the 4D R*Tree drives the query with range constraints, not a per-row rowid lookup
        self.assertRegex(plan, r"^SCAN r VIRTUAL TABLE INDEX 2:[A-Z]")
        self.assertIn("SEARCH ar USING INTEGER PRIMARY KEY", plan)


if __name__ == "__main__":
    unittest.main()
