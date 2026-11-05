"""Storage adapters: SQLite 2D/3D R*Tree indexes and an in-memory 3D grid.

Both adapters only produce candidates. Exact geometry is always re-checked by
query.py, mirroring the "index is a filter, not the answer" rule. This makes the
three variants comparable on identical semantics and makes R*Tree float
rounding harmless for overlap queries (bounds are rounded outward).
"""
import json
import os
import sqlite3

from query import query_corridor, query_segment
from yht_model import airspace_bbox, building_bbox

SCHEMA_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source (
    source_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
    license TEXT, acquired_at TEXT, valid_from TEXT, valid_to TEXT,
    accuracy_xy_m REAL, accuracy_z_m REAL, method TEXT
);
CREATE TABLE coverage (
    tile_id TEXT PRIMARY KEY, minx REAL, miny REAL, maxx REAL, maxy REAL,
    complete INTEGER NOT NULL, source_id TEXT
);
CREATE TABLE feature (
    rid INTEGER PRIMARY KEY, feature_id TEXT NOT NULL UNIQUE, layer TEXT NOT NULL,
    name TEXT, source_id TEXT, quality TEXT, valid_from TEXT, valid_to TEXT
);
CREATE TABLE building (
    rid INTEGER PRIMARY KEY REFERENCES feature(rid),
    footprint TEXT NOT NULL, base_z REAL NOT NULL, top_z REAL,
    height_m REAL, height_source TEXT
);
CREATE TABLE ground (
    rid INTEGER PRIMARY KEY REFERENCES feature(rid),
    polygon TEXT NOT NULL, exposure_class TEXT, exposure_e REAL,
    consequence_c REAL, q REAL
);
CREATE TABLE airspace (
    rid INTEGER PRIMARY KEY REFERENCES feature(rid),
    footprint TEXT NOT NULL, floor_z REAL NOT NULL, ceiling_z REAL NOT NULL,
    ceiling_m REAL, kind TEXT NOT NULL, state TEXT, authority TEXT
);
CREATE TABLE release (
    version TEXT PRIMARY KEY, created_at TEXT, manifest TEXT
);
CREATE VIRTUAL TABLE rtree_building USING rtree(
    rid, minx, maxx, miny, maxy, minz, maxz
);
CREATE VIRTUAL TABLE rtree_building_2d USING rtree(
    rid, minx, maxx, miny, maxy
);
CREATE VIRTUAL TABLE rtree_ground USING rtree(
    rid, minx, maxx, miny, maxy
);
CREATE VIRTUAL TABLE rtree_airspace USING rtree(
    rid, minx, maxx, miny, maxy, minz, maxz
);
CREATE INDEX feature_layer ON feature(layer);
"""


def _bbox_of_ring(poly, z0, z1):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), z0, max(xs), max(ys), z1)


class SQLiteStore:
    def __init__(self, scene, path=":memory:", fast=True):
        self.scene = scene
        self.path = path
        self.fast = fast
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def build(self):
        c = self.conn
        c.execute("PRAGMA foreign_keys=ON")
        if self.fast:
            c.execute("PRAGMA synchronous=OFF")
            c.execute("PRAGMA temp_store=MEMORY")
        c.executescript(SCHEMA_SQL)
        s = self.scene
        meta = {
            "schema": s["schema"], "scene_id": s["scene_id"], "crs": s["crs"],
            "bounds": json.dumps(s["bounds"]), "valid": json.dumps(s["valid"]),
            "versions": json.dumps(s["versions"]),
            "manifest": json.dumps(s["manifest"]),
        }
        c.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", meta.items())
        for src in s["sources"]:
            c.execute(
                "INSERT INTO source(source_id,name,kind,license,acquired_at,"
                "valid_from,valid_to,accuracy_xy_m,accuracy_z_m,method) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (src["id"], src["name"], src["kind"], src["license"],
                 src["acquired_at"], src["valid"][0], src["valid"][1],
                 src["accuracy_xy_m"], src["accuracy_z_m"], src["method"]))
        for tile in s["coverage"]:
            c.execute(
                "INSERT INTO coverage(tile_id,minx,miny,maxx,maxy,complete,"
                "source_id) VALUES(?,?,?,?,?,?,?)",
                (tile["id"], tile["min"][0], tile["min"][1], tile["max"][0],
                 tile["max"][1], int(tile["complete"]), tile["source_id"]))
        rid = 0
        for bld in s["buildings"]:
            rid += 1
            c.execute(
                "INSERT INTO feature(rid,feature_id,layer,name,source_id,quality,"
                "valid_from,valid_to) VALUES(?,?,?,?,?,?,?,?)",
                (rid, bld["id"], "building", bld["name"],
                 bld["footprint_source"], bld.get("quality"), bld["valid"][0],
                 bld["valid"][1]))
            c.execute(
                "INSERT INTO building(rid,footprint,base_z,top_z,height_m,"
                "height_source) VALUES(?,?,?,?,?,?)",
                (rid, json.dumps(bld["footprint"]), bld["base_z"], bld["top_z"],
                 bld["height_m"], bld["height_source"]))
            x0, y0, z0, x1, y1, z1 = _bbox_of_ring(
                bld["footprint"], bld["base_z"], bld["top_z"])
            c.execute("INSERT INTO rtree_building VALUES(?,?,?,?,?,?,?)",
                      (rid, x0, x1, y0, y1, z0, z1))
            c.execute("INSERT INTO rtree_building_2d VALUES(?,?,?,?,?)",
                      (rid, x0, x1, y0, y1))
        for zone in s["ground_zones"]:
            rid += 1
            pts = zone["polygon"]
            c.execute(
                "INSERT INTO feature(rid,feature_id,layer,name,source_id,quality,"
                "valid_from,valid_to) VALUES(?,?,?,?,?,?,?,?)",
                (rid, zone["id"], "ground_zone", zone["name"],
                 zone["source_id"], zone.get("quality"), zone["valid"][0],
                 zone["valid"][1]))
            c.execute(
                "INSERT INTO ground(rid,polygon,exposure_class,exposure_e,"
                "consequence_c,q) VALUES(?,?,?,?,?,?)",
                (rid, json.dumps(pts), zone["exposure_class"],
                 zone.get("exposure_e"), zone.get("consequence_c"),
                 zone.get("q")))
            x0 = min(p[0] for p in pts)
            x1 = max(p[0] for p in pts)
            y0 = min(p[1] for p in pts)
            y1 = max(p[1] for p in pts)
            c.execute("INSERT INTO rtree_ground VALUES(?,?,?,?,?)",
                      (rid, x0, x1, y0, y1))
        for vol in s["airspace"]:
            rid += 1
            pts = vol["footprint"]
            c.execute(
                "INSERT INTO feature(rid,feature_id,layer,name,source_id,quality,"
                "valid_from,valid_to) VALUES(?,?,?,?,?,?,?,?)",
                (rid, vol["id"], "airspace", vol["name"], vol["source_id"],
                 vol.get("quality"), vol["valid"][0], vol["valid"][1]))
            c.execute(
                "INSERT INTO airspace(rid,footprint,floor_z,ceiling_z,ceiling_m,"
                "kind,state,authority) VALUES(?,?,?,?,?,?,?,?)",
                (rid, json.dumps(pts), vol["floor_z"], vol["ceiling_z"],
                 vol.get("ceiling_m"), vol["kind"], vol["state"],
                 vol["authority"]))
            x0, y0, z0, x1, y1, z1 = _bbox_of_ring(
                pts, vol["floor_z"], vol["ceiling_z"])
            c.execute("INSERT INTO rtree_airspace VALUES(?,?,?,?,?,?,?)",
                      (rid, x0, x1, y0, y1, z0, z1))
        c.execute(
            "INSERT INTO release(version,created_at,manifest) VALUES(?,?,?)",
            (s["versions"]["scene"], s["manifest"]["created_at"],
             json.dumps(s["manifest"], sort_keys=True)))
        c.commit()
        return self.stats()

    def stats(self):
        rows = {
            "buildings": self.conn.execute(
                "SELECT COUNT(*) FROM building").fetchone()[0],
            "ground_zones": self.conn.execute(
                "SELECT COUNT(*) FROM ground").fetchone()[0],
            "airspace": self.conn.execute(
                "SELECT COUNT(*) FROM airspace").fetchone()[0],
            "coverage_tiles": self.conn.execute(
                "SELECT COUNT(*) FROM coverage").fetchone()[0],
        }
        pages = self.conn.execute("PRAGMA page_count").fetchone()[0]
        size = self.conn.execute("PRAGMA page_size").fetchone()[0]
        rows["size_bytes"] = pages * size
        return rows

    def _building_rows(self, sql, params):
        return [self._to_building(row) for row in
                self.conn.execute(sql, params)]

    @staticmethod
    def _to_building(row):
        return {
            "id": row["feature_id"], "kind": "building", "name": row["name"],
            "footprint": json.loads(row["footprint"]),
            "base_z": row["base_z"], "top_z": row["top_z"],
            "height_m": row["height_m"],
            "footprint_source": row["source_id"],
            "height_source": row["height_source"],
            "quality": row["quality"],
            "valid": [row["valid_from"], row["valid_to"]],
        }

    def candidates_3d(self, lo, hi):
        sql = (
            "SELECT f.feature_id,f.name,f.source_id,f.quality,f.valid_from,"
            "f.valid_to,b.footprint,b.base_z,b.top_z,b.height_m,b.height_source "
            "FROM rtree_building r JOIN building b ON b.rid=r.rid "
            "JOIN feature f ON f.rid=r.rid "
            "WHERE r.maxx>=? AND r.minx<=? AND r.maxy>=? AND r.miny<=? "
            "AND r.maxz>=? AND r.minz<=?")
        return self._building_rows(
            sql, (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))

    def candidates_2d_z(self, lo, hi):
        sql = (
            "SELECT f.feature_id,f.name,f.source_id,f.quality,f.valid_from,"
            "f.valid_to,b.footprint,b.base_z,b.top_z,b.height_m,b.height_source "
            "FROM rtree_building_2d r JOIN building b ON b.rid=r.rid "
            "JOIN feature f ON f.rid=r.rid "
            "WHERE r.maxx>=? AND r.minx<=? AND r.maxy>=? AND r.miny<=? "
            "AND b.top_z>=? AND b.base_z<=?")
        return self._building_rows(
            sql, (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))

    def query_plan(self, mode="3d"):
        if mode == "3d":
            sql = ("SELECT f.feature_id FROM rtree_building r JOIN building b "
                   "ON b.rid=r.rid JOIN feature f ON f.rid=r.rid "
                   "WHERE r.maxx>=0 AND r.minx<=600 AND r.maxy>=0 "
                   "AND r.miny<=600 AND r.maxz>=0 AND r.minz<=160")
        else:
            sql = ("SELECT f.feature_id FROM rtree_building_2d r JOIN building b "
                   "ON b.rid=r.rid JOIN feature f ON f.rid=r.rid "
                   "WHERE r.maxx>=0 AND r.minx<=600 AND r.maxy>=0 "
                   "AND r.miny<=600 AND b.top_z>=0 AND b.base_z<=160")
        return [tuple(row) for row in
                self.conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall()]

    def segment_query(self, a, b, window, versions, mode="3d", verify=True):
        lo = [min(a[i], b[i]) for i in range(3)]
        hi = [max(a[i], b[i]) for i in range(3)]
        candidates = (self.candidates_3d(lo, hi) if mode == "3d"
                      else self.candidates_2d_z(lo, hi))
        return query_segment(self.scene, a, b, window, versions,
                             building_candidates=candidates, verify=verify)

    def corridor_query(self, a, b, radius, window, versions, mode="3d",
                       verify=True):
        lo = [min(a[i], b[i]) - radius for i in range(3)]
        hi = [max(a[i], b[i]) + radius for i in range(3)]
        candidates = (self.candidates_3d(lo, hi) if mode == "3d"
                      else self.candidates_2d_z(lo, hi))
        return query_corridor(self.scene, a, b, radius, window, versions,
                              building_candidates=candidates, verify=verify)

    def close(self):
        self.conn.close()


class GridIndex:
    """In-memory uniform grid over building AABBs (3D cells)."""

    def __init__(self, scene, cell=(40.0, 40.0, 40.0)):
        self.scene = scene
        self.cell = cell
        self.cells = {}
        for bld in scene["buildings"]:
            lo, hi = building_bbox(bld)
            for key in self._keys(lo, hi):
                self.cells.setdefault(key, []).append(bld)

    def _keys(self, lo, hi):
        (x0, y0, z0), (x1, y1, z1) = lo, hi
        cx, cy, cz = self.cell
        for ix in range(int(x0 // cx), int(x1 // cx) + 1):
            for iy in range(int(y0 // cy), int(y1 // cy) + 1):
                for iz in range(int(z0 // cz), int(z1 // cz) + 1):
                    yield (ix, iy, iz)

    def candidates(self, lo, hi):
        seen = {}
        for key in self._keys(lo, hi):
            for bld in self.cells.get(key, ()):
                seen[bld["id"]] = bld
        return list(seen.values())

    def segment_query(self, a, b, window, versions, verify=True):
        lo = [min(a[i], b[i]) for i in range(3)]
        hi = [max(a[i], b[i]) for i in range(3)]
        return query_segment(self.scene, a, b, window, versions,
                             building_candidates=self.candidates(lo, hi),
                             verify=verify)

    def corridor_query(self, a, b, radius, window, versions, verify=True):
        lo = [min(a[i], b[i]) - radius for i in range(3)]
        hi = [max(a[i], b[i]) + radius for i in range(3)]
        return query_corridor(self.scene, a, b, radius, window, versions,
                              building_candidates=self.candidates(lo, hi),
                              verify=verify)


def bbox_for_airspace(vol):
    lo, hi = airspace_bbox(vol)
    return lo, hi
