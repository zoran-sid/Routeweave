"""Derived-graph cache across releases: full rebuild vs change-driven carry/patch.

Release-keyed caches never become wrong for their own release (releases are immutable);
the question is what a NEW release can reuse. Two real publications through
catalog.publish change the airspace layer only:

  R0 -> R1  publish a new no-fly volume over part of the task area
  R1 -> R2  revoke an existing no-fly volume

Full strategy: rebuild every cached graph for the new release.
Targeted strategy: read changed restrictions from airspace_event (written by ZQO's
publish transaction) and changed risk values by diffing the two LQ datasets; graphs
whose domain x window does not meet any change are carried (new cache row, no compute);
the rest are patched by recomputing only edges whose box touches a change.
Every targeted graph must have the same digest as its full rebuild.

python3 -B docs/modules/zc/v2/experiments/invalidation.py
"""
import argparse
import copy
import hashlib
import json
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planner_io as io  # noqa: E402
import city  # noqa: E402

cat = io.cat
BUF = io.CONFIG["buffer_m"]
FOOT = io.RISK_MODEL["footprint_m"]
OLD = {"id": "NF-OLD", "box": (1000.0, 1000.0, 1250.0, 1250.0),
       "effective": ("2026-11-10T06:00:00Z", "2026-11-10T18:00:00Z")}
NEW_ROWS = {"id": "NF-NEW", "box": (1400.0, 1500.0, 1800.0, 1800.0),
            "effective": ("2026-11-10T08:00:00Z", "2026-11-10T14:00:00Z")}


def ms_since(t):
    return (time.perf_counter_ns() - t) / 1e6


def add_restriction(pl, spec):
    """Copy an existing no-fly row as a template and insert a new restriction into the payload."""
    out = copy.deepcopy(pl)
    air = out["airspace"]
    f = copy.deepcopy(next(r for r in air["feature"]))
    a = copy.deepcopy(next(r for r in air["airspace_restriction"] if r["kind"] == "no_fly"))
    x0, y0, x1, y1 = spec["box"]
    f["feature_id"] = a["feature_id"] = a["restriction_id"] = spec["id"]
    a.update(kind="no_fly", ceiling_m=None, floor_z=0.0, bbox_min_x=x0, bbox_min_y=y0, bbox_max_x=x1, bbox_max_y=y1,
             volume_wkt=f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))",
             effective_lo=spec["effective"][0], effective_hi=spec["effective"][1], state="published", revoked_at=None)
    air["feature"].append(f)
    air["airspace_restriction"].append(a)
    return out


def revoke(pl, rid, at="2026-11-09T00:00:00Z"):
    out = copy.deepcopy(pl)
    row = next(r for r in out["airspace"]["airspace_restriction"] if r["restriction_id"] == rid)
    row["state"], row["revoked_at"] = "revoked", at
    return out


def change_boxes(c, prev, nxt):
    """Change feed: restrictions with an airspace_event in the new release, plus risk values that differ."""
    owners = {}
    for rel in (prev, nxt):
        owners[rel] = {r[0]: (r[1], r[2]) for r in c.execute(
            "SELECT rc.layer, rc.component_id, lc.owner_release_id FROM release_component rc "
            "JOIN layer_component lc USING(component_id) WHERE rc.release_id=?", (rel,))}
    if owners[prev]["scene"][0] != owners[nxt]["scene"][0] or owners[prev]["terrain"][0] != owners[nxt]["terrain"][0]:
        return None  # scene/terrain changed: every graph is affected (not exercised here)
    changed = [r[0] for r in c.execute("SELECT restriction_id FROM airspace_event WHERE release_id=?", (nxt,))]
    boxes = []
    for rel in (prev, nxt):
        owner = owners[rel]["airspace"][1]
        for rid in changed:
            r = c.execute(
                "SELECT ar.kind, ar.bbox_min_x, ar.bbox_min_y, ar.bbox_max_x, ar.bbox_max_y, ar.forbid_lo_z, "
                "ar.forbid_hi_z, ar.effective_lo, ar.effective_hi FROM airspace_restriction ar JOIN feature f "
                "USING(rid) WHERE f.release_id=? AND f.feature_id=?", (owner, rid)).fetchone()
            if r is None:
                continue
            kind, x0, y0, x1, y1, zlo, zhi, lo, hi = r
            boxes.append({"why": f"airspace:{rid}@{rel}",
                          "box": [[x0 - BUF, y0 - BUF, zlo - BUF], [x1 + BUF, y1 + BUF, zhi + BUF]],
                          "time": [lo, hi]})
    d_prev = c.execute("SELECT dataset_id FROM risk_dataset WHERE release_id=? AND state='validated'", (prev,)).fetchone()[0]
    d_next = c.execute("SELECT dataset_id FROM risk_dataset WHERE release_id=? AND state='validated'", (nxt,)).fetchone()[0]
    for r in c.execute(
            "SELECT e.bbox_min_x, e.bbox_min_y, e.bbox_max_x, e.bbox_max_y FROM derived_risk a "
            "LEFT JOIN derived_risk b ON b.dataset_id=? AND b.zone_rid=a.zone_rid "
            "JOIN exposure_zone e ON e.rid=a.zone_rid WHERE a.dataset_id=? AND (b.q_max IS NULL OR b.q_max<>a.q_max)",
            (d_next, d_prev)):
        boxes.append({"why": "risk", "box": [[r[0] - FOOT, r[1] - FOOT, -1e9], [r[2] + FOOT, r[3] + FOOT, 1e9]],
                      "time": None})
    if owners[prev]["exposure"][0] != owners[nxt]["exposure"][0]:
        return None
    return {"changed_restrictions": changed, "boxes": boxes}


def affecting(meta, change):
    dom = [[meta["min_x"], meta["min_y"], meta["min_z"]], [meta["max_x"], meta["max_y"], meta["max_z"]]]
    if change is None:  # scene/terrain/exposure component changed: the whole domain is affected
        return [[[v - 1.0 for v in dom[0]], [v + 1.0 for v in dom[1]]]]
    out = []
    for b in change["boxes"]:
        (x0, y0, z0), (x1, y1, z1) = b["box"]
        if x1 < dom[0][0] or x0 > dom[1][0] or y1 < dom[0][1] or y0 > dom[1][1] or z1 < dom[0][2] or z0 > dom[1][2]:
            continue
        if b["time"] and not (b["time"][0] <= meta["window_hi"] and meta["window_lo"] <= b["time"][1]):
            continue
        out.append(b["box"])
    return out


def inputs_for(c, release, meta, task):
    win = (meta["window_lo"], meta["window_hi"])
    c.execute("BEGIN")
    try:
        p = io.pin(c, release, win)
        dom = [[meta["min_x"], meta["min_y"], meta["min_z"]], [meta["max_x"], meta["max_y"], meta["max_z"]]]
        objs = io.objects_from_rows(io.fetch_sql(c, p, dom, win, "sql_rtree"))
    finally:
        c.execute("COMMIT")
    s, q, zr = io.planner_input(p, objs, dom, win, task["start"], task["goal"])
    return p, s, q, zr


def transition(c, cache, tasks, prev, nxt):
    metas = cat.rows(c, "SELECT * FROM route_graph_cache WHERE release_id=? ORDER BY graph_id", (prev,))
    by_domain = {(m["min_x"], m["min_y"], m["window_lo"]): m for m in metas}
    task_of = {}
    for t in tasks:
        d = io.domain_for(t["start"], t["goal"])
        task_of[(d[0][0], d[0][1], t["window"][0])] = t

    # Full strategy: fetch, rebuild and hash every graph for the new release. Rows are not inserted
    # (one cache row per key); an insert costs about 0.1 ms and is left out of both strategies' compute.
    full, full_digest, t_full = {}, {}, time.perf_counter_ns()
    for m in metas:
        t = task_of[(m["min_x"], m["min_y"], m["window_lo"])]
        _, s, q, _ = inputs_for(c, nxt, m, t)
        full[m["graph_id"]] = io.build_graph(s, q)
        full_digest[m["graph_id"]] = io.graph_digest(full[m["graph_id"]])
    full_ms = ms_since(t_full)

    # Targeted strategy.
    t_tgt = time.perf_counter_ns()
    t = time.perf_counter_ns()
    change = change_boxes(c, prev, nxt)
    detect_ms = ms_since(t)
    per, mismatches, carried, patched, rebuilt = [], 0, 0, 0, 0
    for m in metas:
        task = task_of[(m["min_x"], m["min_y"], m["window_lo"])]
        boxes = affecting(m, change)
        t = time.perf_counter_ns()
        old = cache[m["payload_hash"]]
        if not boxes:
            p = io.pin(c, nxt, (m["window_lo"], m["window_hi"]))
            gid = io.store_graph(c, p, old, (m["window_lo"], m["window_hi"]), origin="carried",
                                 parent=m["graph_id"], payload_hash=m["payload_hash"])
            g, ph, kind = old, m["payload_hash"], "carried"
            carried += 1
        else:
            p, s, q, zr = inputs_for(c, nxt, m, task)
            g = io.build_graph(s, q, region=boxes, base=old)
            ph = io.graph_digest(g)
            cache[ph], cache[ph + ":zones"] = g, zr
            kind = g["mode"]  # 'patched', or 'built' when most of the domain is touched
            gid = io.store_graph(c, p, g, (m["window_lo"], m["window_hi"]), origin=kind,
                                 parent=m["graph_id"] if kind == "patched" else None, payload_hash=ph)
            patched += 1 if kind == "patched" else 0
            rebuilt += 1 if kind == "built" else 0
        elapsed = ms_since(t)
        ok = ph == full_digest[m["graph_id"]]
        mismatches += 0 if ok else 1
        q = {"start": list(task["start"]), "goal": list(task["goal"]), "window": [m["window_lo"], m["window_hi"]],
             "departure": m["window_lo"]}
        same_route = io.same_result(io.search_graph(g, q), io.search_graph(full[m["graph_id"]], q))
        mismatches += 0 if same_route else 1
        per.append({"parent": m["graph_id"], "graph_id": gid, "origin": kind, "touching_changes": len(boxes),
                    "recomputed_nodes": 0 if kind == "carried" else g["recomputed_nodes"], "nodes": g["nodes"],
                    "ms": elapsed, "digest_equal_full_rebuild": ok, "route_equal_full_rebuild": same_route,
                    "status_before": io.search_graph(old, q)["status"], "status_after": io.search_graph(g, q)["status"]})
    targeted_ms = ms_since(t_tgt)
    # Historical queries on the previous release keep hitting its own cache rows.
    hist_hits = 0
    for task in tasks:
        _, _, _, tm, gid = io.plan_route(c, prev, task["window"], task["start"], task["goal"], "graph_cache", cache=cache)
        hist_hits += 1 if "build_ms" not in tm else 0
    return {"from": prev, "to": nxt, "graphs": len(metas),
            "changed_restrictions": change["changed_restrictions"] if change else "component changed: all graphs",
            "change_boxes": len(change["boxes"]) if change else None, "carried": carried, "patched": patched, "rebuilt": rebuilt,
            "full_rebuild_ms": full_ms, "targeted_ms": targeted_ms, "detect_ms": detect_ms,
            "targeted_vs_full_mismatches": mismatches, "historical_cache_hits_prev": hist_hits,
            "routes_changed": sum(1 for r in per if r["status_before"] != r["status_after"]),
            "patched_median_ms": statistics.median([r["ms"] for r in per if r["origin"] == "patched"]) if patched else None,
            "rebuilt_median_ms": statistics.median([r["ms"] for r in per if r["origin"] == "built"]) if rebuilt else None,
            "carried_median_ms": statistics.median([r["ms"] for r in per if r["origin"] == "carried"]) if carried else None,
            "full_median_ms_per_graph": full_ms / len(metas), "per_graph": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(HERE / "results" / "invalidation.json"))
    ap.add_argument("--graphs", type=int, default=24)
    ap.add_argument("--buildings", type=int, default=2400)
    ap.add_argument("--seed", type=int, default=20261107)
    args = ap.parse_args()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with tempfile.TemporaryDirectory(prefix="zc-inval-") as tmp:
        pl0, boxes = city.payload(args.buildings, seed=args.seed, extra_air=[OLD])
        c = city.database(str(Path(tmp) / "inval.db"), pl0)
        tasks = city.tasks(args.graphs, boxes, seed=args.seed + 3, region=(900.0, 2100.0), day=10, hours=(6, 18))
        cache = {}
        for t in tasks:
            io.plan_route(c, "R0", t["window"], t["start"], t["goal"], "graph_cache", cache=cache)
        pl1 = add_restriction(pl0, NEW_ROWS)
        city.next_release(c, pl1, "R1", "R0")
        r1 = transition(c, cache, tasks, "R0", "R1")
        city.next_release(c, revoke(pl1, "NF-OLD"), "R2", "R1")
        r2 = transition(c, cache, tasks, "R1", "R2")
        components = cat.rows(c, "SELECT release_id, layer, component_id FROM release_component ORDER BY release_id, layer")
        integrity = {"check": c.execute("PRAGMA integrity_check").fetchone()[0],
                     "foreign_key_violations": len(c.execute("PRAGMA foreign_key_check").fetchall()),
                     "cache_rows_by_origin": {r[0]: r[1] for r in c.execute(
                         "SELECT origin, count(*) FROM route_graph_cache GROUP BY origin")}}
        c.close()
    files = [HERE / f for f in ("invalidation.py", "planner_io.py", "city.py")] + [io.ROOT / "docs/v2/schema/schema.sql"]
    out = {"experiment": "zc_v2_cache_invalidation", "started_at": started, "synthetic": True,
           "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                           "platform": platform.platform(),
                           "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=io.ROOT, text=True,
                                                      capture_output=True).stdout.strip()},
           "parameters": {"buildings": args.buildings, "graphs": args.graphs, "seed": args.seed,
                          "task_region_m": [900, 2100], "task_day": "2026-11-10 06:00-18:00 UTC",
                          "changes": {"R1": {"publish": NEW_ROWS}, "R2": {"revoke": OLD["id"]}},
                          "planner_config": io.CONFIG},
           "source_sha256": {str(f.relative_to(io.ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
           "component_mapping": components, "transitions": [r1, r2], "integrity": integrity}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    for r in (r1, r2):
        print(json.dumps({k: v for k, v in r.items() if k != "per_graph"}, ensure_ascii=False))
    print(json.dumps(integrity))


if __name__ == "__main__":
    main()
