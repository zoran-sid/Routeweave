"""Operation A access-path experiment on the v2 unified schema.

Question: for "restrictions active in a task window inside a 3D corridor, bound to
one release", which access path should the database use, and how does the answer
change with the number of restrictions per release (N) and the number of releases
kept in the same table (K, full-copy history)?

All variants run the same exact predicate on base-table columns over identical
data; only the access path differs. Results must be identical across variants.

Run from the repository root:
    python3 -B docs/modules/yht/v2/experiments/op_a_index_comparison.py
    python3 -B docs/modules/yht/v2/experiments/op_a_index_comparison.py --quick --output /tmp/op_a.json
"""
import argparse
import csv
import hashlib
import json
import math
import platform
import random
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCHEMA_DIR = ROOT / "docs" / "v2" / "schema"
sys.path.insert(0, str(SCHEMA_DIR))

import fixtures as fx  # noqa: E402

AREA = 3000.0                 # m, square synthetic area
T0 = 26265600                 # 2026-11-01T00:00:00Z in seconds after 2026-01-01
SPAN = 30 * 86400             # restrictions start within 30 days
WINDOW = 600                  # 10-minute task window
CORRIDOR_LEN = 400.0
CORRIDOR_BUF = 20.0
Z_BAND = (40.0, 120.0)

EXACT = """
  AND f.release_id = :release_id
  AND ar.state IN ('published', 'active')
  AND ar.effective_lo < :win_hi AND ar.effective_hi > :win_lo
  AND ar.bbox_max_x >= :x0 AND ar.bbox_min_x <= :x1
  AND ar.bbox_max_y >= :y0 AND ar.bbox_min_y <= :y1
  AND ar.forbid_hi_z >= :z0 AND ar.forbid_lo_z <= :z1
ORDER BY f.feature_id"""

XYZ = """r.max_x >= :x0 AND r.min_x <= :x1
  AND r.max_y >= :y0 AND r.min_y <= :y1
  AND r.max_z >= :z0 AND r.min_z <= :z1"""
T = """AND r.max_t >= unixepoch(:win_lo) - 1767225600
  AND r.min_t <= unixepoch(:win_hi) - 1767225600"""

VARIANTS = {
    "V0_full_scan": (
        "全表扫描（基线）",
        "SELECT f.feature_id FROM airspace_restriction AS ar NOT INDEXED"
        " CROSS JOIN feature AS f ON f.rid = ar.rid WHERE 1 = 1" + EXACT,
        "SELECT count(*) FROM airspace_restriction",
    ),
    "V1_release_btree": (
        "发布 B-tree 驱动（feature(release_id, layer, feature_type)）",
        "SELECT f.feature_id FROM feature AS f INDEXED BY feature_release_type"
        " CROSS JOIN airspace_restriction AS ar ON ar.rid = f.rid"
        " WHERE f.layer = 'airspace' AND f.feature_type = 'airspace'" + EXACT,
        "SELECT count(*) FROM feature WHERE release_id = :release_id"
        " AND layer = 'airspace' AND feature_type = 'airspace'",
    ),
    "V2_time_btree": (
        "时间 B-tree 驱动（airspace_restriction(effective_lo)）",
        "SELECT f.feature_id FROM airspace_restriction AS ar INDEXED BY exp_ar_effective_lo"
        " CROSS JOIN feature AS f ON f.rid = ar.rid WHERE 1 = 1" + EXACT,
        "SELECT count(*) FROM airspace_restriction WHERE effective_lo < :win_hi",
    ),
    "V3_rtree_3d": (
        "三维 R*Tree 驱动（x, y, z）",
        "SELECT f.feature_id FROM exp_rtree_3d AS r"
        " CROSS JOIN airspace_restriction AS ar ON ar.rid = r.rid"
        " CROSS JOIN feature AS f ON f.rid = ar.rid WHERE " + XYZ + EXACT,
        "SELECT count(*) FROM exp_rtree_3d AS r WHERE " + XYZ,
    ),
    "V4_rtree_4d": (
        "时空四维 R*Tree 驱动（x, y, z, t），即 op_a.sql",
        None,   # filled from op_a.sql
        "SELECT count(*) FROM rtree_airspace AS r WHERE " + XYZ + "\n  " + T,
    ),
    "V5_planner_default": (
        "规划器自选（op_a.sql 去掉 CROSS JOIN，不固定连接顺序）",
        None,   # filled from op_a.sql
        None,
    ),
}


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_restrictions(n, rng):
    rows = []
    for i in range(n):
        w, h = rng.uniform(20, 200), rng.uniform(20, 200)
        x0, y0 = rng.uniform(0, AREA - w), rng.uniform(0, AREA - h)
        lo = T0 + rng.uniform(0, SPAN)
        dur = math.exp(rng.uniform(math.log(900), math.log(43200)))
        if rng.random() < 0.7:
            kind, floor_z = "no_fly", 0.0
            ceiling = None if rng.random() < 0.5 else rng.uniform(60, 150)
        else:
            kind, floor_z, ceiling = "height_limit", 0.0, rng.uniform(60, 150)
        state = "revoked" if rng.random() < 0.05 else "published"
        rows.append((f"NF-{i:06d}", kind, (x0, y0, x0 + w, y0 + h), floor_z, ceiling,
                     fx.at(int(lo)), fx.at(int(lo + dur)), state))
    return rows


def build_db(n, k, rng):
    conn = fx.connect()
    fx.base(conn)
    restrictions = make_restrictions(n, rng)
    rid = 0
    for r in range(k):
        rel = f"rel-{r:03d}"
        fx.create_release(conn, rel)
        feats, airs = [], []
        for fid, kind, (x0, y0, x1, y1), floor_z, ceiling, lo, hi, state in restrictions:
            rid += 1
            feats.append((rid, rel, fid, "airspace", "airspace", "SRC-SYN", "assumed",
                          "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z",
                          "2026-11-01T00:00:00Z", "restricted", "polyhedral"))
            airs.append((rid, fid, kind, fx.box_wkt(x0, y0, x1, y1), x0, y0, x1, y1, floor_z,
                         ceiling, lo, hi, state, "synthetic", "SRC-SYN", "2026-11-01T00:00:00Z",
                         "2026-11-01T00:10:00Z" if state == "revoked" else None,
                         "assumed", "restricted"))
        conn.executemany(
            "INSERT INTO feature (rid, release_id, feature_id, layer, feature_type, source_id,"
            " quality, valid_lo, valid_hi, recorded_at, sensitivity, geom_kind)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", feats)
        conn.executemany(
            "INSERT INTO airspace_restriction (rid, restriction_id, kind, volume_wkt,"
            " bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y, floor_z, ceiling_m,"
            " effective_lo, effective_hi, state, authority, source_id, published_at,"
            " revoked_at, quality, sensitivity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            airs)
        fx.add_layers(conn, rel)
        fx.publish(conn, rel)
    # comparison-only structures (not part of the chosen schema)
    conn.execute("CREATE INDEX exp_ar_effective_lo ON airspace_restriction(effective_lo)")
    conn.execute("CREATE VIRTUAL TABLE exp_rtree_3d USING rtree(rid, min_x, max_x, min_y, max_y,"
                 " min_z, max_z)")
    conn.execute("INSERT INTO exp_rtree_3d SELECT rid, min_x, max_x, min_y, max_y, min_z, max_z"
                 " FROM rtree_airspace")
    conn.execute("ANALYZE")
    conn.commit()
    return conn, f"rel-{k - 1:03d}"


def make_queries(q, rng, release_id):
    out = []
    for _ in range(q):
        sx, sy = rng.uniform(200, AREA - 200), rng.uniform(200, AREA - 200)
        a = rng.uniform(0, 2 * math.pi)
        ex, ey = sx + CORRIDOR_LEN * math.cos(a), sy + CORRIDOR_LEN * math.sin(a)
        ws = int(T0 + rng.uniform(0, SPAN - WINDOW))
        out.append({
            "release_id": release_id,
            "win_lo": fx.at(ws), "win_hi": fx.at(ws + WINDOW),
            "x0": min(sx, ex) - CORRIDOR_BUF, "x1": max(sx, ex) + CORRIDOR_BUF,
            "y0": min(sy, ey) - CORRIDOR_BUF, "y1": max(sy, ey) + CORRIDOR_BUF,
            "z0": Z_BAND[0], "z1": Z_BAND[1],
        })
    return out


def plan_of(conn, sql, params):
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]


def percentile(values, p):
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def run_config(n, k, q, repeats, seed):
    rng = random.Random(seed + n * 31 + k)
    t_build = time.perf_counter()
    conn, target = build_db(n, k, rng)
    build_s = time.perf_counter() - t_build
    queries = make_queries(q, rng, target)
    op_a = fx.op_a_sql()
    sqls = {v: spec[1] for v, spec in VARIANTS.items()}
    sqls["V4_rtree_4d"] = op_a
    sqls["V5_planner_default"] = op_a.replace("CROSS JOIN", "JOIN")

    def ids(sql, p):
        return [row[0] for row in conn.execute(sql, p)]

    reference = [ids(sqls["V0_full_scan"], p) for p in queries]
    mismatches = {}
    for v, sql in sqls.items():
        got = [ids(sql, p) for p in queries]
        mismatches[v] = sum(1 for a, b in zip(reference, got) if a != b)

    rows = []
    for v, (label, _, count_sql) in VARIANTS.items():
        sql = sqls[v]
        per_query = []
        for p in queries:
            samples = []
            for _ in range(repeats):
                t = time.perf_counter_ns()
                conn.execute(sql, p).fetchall()
                samples.append(time.perf_counter_ns() - t)
            per_query.append(statistics.median(samples) / 1000.0)
        cands = ([conn.execute(count_sql, p).fetchone()[0] for p in queries]
                 if count_sql else None)
        rows.append({
            "n_per_release": n, "releases": k, "total_rows": n * k, "variant": v,
            "label": label,
            "median_us": round(statistics.median(per_query), 2),
            "p95_us": round(percentile(per_query, 95), 2),
            "mean_driving_rows": round(statistics.mean(cands), 1) if cands else None,
            "mean_hits": round(statistics.mean(len(r) for r in reference), 2),
            "mismatched_queries": mismatches[v],
            "plan": plan_of(conn, sql, queries[0]),
        })
    conn.close()
    return {"n_per_release": n, "releases": k, "build_seconds": round(build_s, 2)}, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small grid for a smoke run")
    ap.add_argument("--output", default=str(HERE / "results" / "op_a_index_comparison.json"))
    ap.add_argument("--seed", type=int, default=20261106)
    args = ap.parse_args()

    grid_n = (100, 1000) if args.quick else (100, 1000, 10000)
    grid_k = (1, 5) if args.quick else (1, 20)
    q, repeats = (20, 3) if args.quick else (100, 5)

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    builds, results = [], []
    for k in grid_k:
        for n in grid_n:
            b, rows = run_config(n, k, q, repeats, args.seed)
            builds.append(b)
            results.extend(rows)
            print(f"N={n:>6} K={k:>3} built in {b['build_seconds']}s", file=sys.stderr)

    out = {
        "experiment": "op_a_index_comparison",
        "question": "access path for restrictions active in a task window inside a 3D corridor",
        "started_at": started,
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "database": "in-memory SQLite, ANALYZE after load",
        },
        "parameters": {
            "seed": args.seed, "queries_per_config": q, "repeats_per_query": repeats,
            "area_m": AREA, "start_span_days": SPAN // 86400, "window_s": WINDOW,
            "corridor": {"length_m": CORRIDOR_LEN, "buffer_m": CORRIDOR_BUF, "z_band_m": Z_BAND},
            "history_model": "each release is a full copy of the same restriction set",
            "restriction_mix": "70% no_fly (half open-topped), 30% height_limit, 5% revoked",
        },
        "source_sha256": {
            "script": sha_file(__file__),
            "schema.sql": sha_file(SCHEMA_DIR / "schema.sql"),
            "op_a.sql": sha_file(SCHEMA_DIR / "op_a.sql"),
            "fixtures.py": sha_file(SCHEMA_DIR / "fixtures.py"),
        },
        "builds": builds,
        "results": results,
        "synthetic": True,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = Path(args.output).with_suffix(".csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["n_per_release", "releases", "variant", "median_us", "p95_us",
                    "mean_driving_rows", "mean_hits", "mismatched_queries"])
        for r in results:
            w.writerow([r["n_per_release"], r["releases"], r["variant"], r["median_us"],
                        r["p95_us"], r["mean_driving_rows"], r["mean_hits"],
                        r["mismatched_queries"]])
    print(f"wrote {args.output} and {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
