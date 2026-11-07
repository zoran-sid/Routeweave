"""ZC v2: the planning service as a database client.

The v1 planner (docs/modules/zc/prototype/planner.py) is used unchanged. This module
decides how the planner gets its input from the unified schema:

  json_snapshot  read a whole-release JSON export, parse, filter in Python
  sql_full       read every object of the pinned release with SQL, filter in Python
  sql_rtree      let the R*Tree indexes return only objects near the search domain
  graph_cache    reuse a materialised graph of allowed edges keyed by release/domain/window/config

Every path pins one logical release inside a read transaction, resolves the physical
owner of each layer through release_component (ZQO component sharing), and requires a
validated LQ risk dataset whose window contains the task window.
"""
import hashlib
import json
import sqlite3
import sys
import time
import uuid
from heapq import heappop, heappush
from math import dist, inf
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
for sub in ("docs/modules/zqo/v2/experiments", "docs/modules/lq/v2/experiments", "docs/modules/zc/prototype"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

import catalog as cat  # noqa: E402  ZQO publication service
import planner as v1  # noqa: E402  ZC v1 planner, unchanged

T_OFFSET = 1767225600  # schema R*Tree time origin: 2026-01-01T00:00:00Z
CONFIG = {"step_m": 20, "buffer_m": 2, "speed_mps": 10, "lambda_risk": 1.0, "length_scale_m": 100}
RISK_MODEL = {"hard_threshold": 0.9, "footprint_m": 5, "aggregation": "edge_max_times_length"}
ACCESS_PATHS = ("json_snapshot", "sql_full", "sql_rtree", "graph_cache")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


CONFIG_HASH = digest({"config": CONFIG, "risk_model": RISK_MODEL})


def epoch(ts):
    from datetime import datetime, timezone
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() - T_OFFSET


# --------------------------------------------------------------------------- pinning
def pin(c, release_id, window):
    """Resolve layer owners, freshness and the risk dataset. Caller holds a read transaction."""
    rel = c.execute("SELECT * FROM release WHERE release_id=? AND status<>'draft'", (release_id,)).fetchone()
    if rel is None:
        raise LookupError("unknown published release: " + release_id)
    if not (rel["valid_lo"] <= window[0] < window[1] <= rel["valid_hi"]):
        raise ValueError("task window outside release validity")
    owners = {r["layer"]: (r["component_id"], r["owner_release_id"]) for r in c.execute(
        "SELECT rc.layer, rc.component_id, lc.owner_release_id FROM release_component rc "
        "JOIN layer_component lc USING(component_id) WHERE rc.release_id=?", (release_id,))}
    if len(owners) != 5:
        raise ValueError("unmapped release")
    dataset = c.execute(
        "SELECT dataset_id FROM risk_dataset WHERE release_id=? AND component_id=? AND state='validated' "
        "AND window_lo<=? AND ?<=window_hi ORDER BY dataset_id LIMIT 1",
        (release_id, owners["exposure"][0], window[0], window[1])).fetchone()
    if dataset is None:
        raise LookupError("no validated risk dataset covers the task window")
    head = c.execute("SELECT release_id FROM current_release WHERE scene_id=?", (rel["scene_id"],)).fetchone()
    return {"release_id": release_id, "owners": owners, "dataset_id": dataset[0],
            "freshness": "current" if head and head[0] == release_id else "historical",
            "valid": [rel["valid_lo"], rel["valid_hi"]],
            "versions": {"scene": owners["scene"][0], "airspace": owners["airspace"][0],
                         "risk_data": dataset[0], "risk_model": "lq-risk-v1",
                         "planner_config": CONFIG_HASH[:16]}}


# --------------------------------------------------------------------------- domain
def domain_for(start, goal, margin=40.0, z=(20.0, 120.0)):
    step = CONFIG["step_m"]
    lo = [((min(a, b) - margin) // step) * step for a, b in zip(start[:2], goal[:2])]
    hi = [-((-(max(a, b) + margin)) // step) * step for a, b in zip(start[:2], goal[:2])]
    return [[lo[0], lo[1], z[0]], [hi[0], hi[1], z[1]]]


def _expanded(domain, pad):
    return {"x0": domain[0][0] - pad, "x1": domain[1][0] + pad, "y0": domain[0][1] - pad,
            "y1": domain[1][1] + pad, "z0": domain[0][2] - pad, "z1": domain[1][2] + pad}


def relevant(obj, domain):
    """Conservative relevance: can this object change any edge inside the domain?"""
    pad = CONFIG["buffer_m"] if obj["kind"] != "zone" else RISK_MODEL["footprint_m"]
    e = _expanded(domain, pad)
    (x0, y0, z0), (x1, y1, z1) = obj["box"]
    if x1 < e["x0"] or x0 > e["x1"] or y1 < e["y0"] or y0 > e["y1"]:
        return False
    if obj["kind"] in ("building", "no_fly"):
        return not (z1 < e["z0"] or z0 > e["z1"])
    if obj["kind"] == "height_limit":
        return obj["ceiling_m"] < e["z1"]
    return True


# --------------------------------------------------------------------------- SQL access
_BUILDINGS = ("SELECT f.feature_id, b.bbox_min_x, b.bbox_min_y, b.base_z, b.bbox_max_x, b.bbox_max_y, b.top_z "
              "FROM {src} WHERE {where} f.release_id=:owner")
_AIR = ("SELECT f.feature_id, ar.kind, ar.bbox_min_x, ar.bbox_min_y, ar.floor_z, ar.bbox_max_x, ar.bbox_max_y, "
        "ar.forbid_hi_z, ar.ceiling_m, ar.effective_lo, ar.effective_hi, ar.state "
        "FROM {src} WHERE {where} f.release_id=:owner AND ar.state IN ('published','active')")
_ZONES = ("SELECT f.feature_id, e.rid, e.bbox_min_x, e.bbox_min_y, e.floor_z, e.bbox_max_x, e.bbox_max_y, e.top_z, "
          "dr.q_max FROM {src} LEFT JOIN derived_risk dr ON dr.dataset_id=:dataset AND dr.zone_rid=e.rid "
          "WHERE {where} f.release_id=:owner")

SQL = {
    "sql_full": {
        "building": _BUILDINGS.format(src="feature f JOIN building b ON b.rid=f.rid", where=""),
        "airspace": _AIR.format(src="feature f JOIN airspace_restriction ar ON ar.rid=f.rid", where=""),
        "zone": _ZONES.format(src="feature f JOIN exposure_zone e ON e.rid=f.rid", where=""),
    },
    "sql_rtree": {
        "building": _BUILDINGS.format(
            src="rtree_building r CROSS JOIN building b ON b.rid=r.rid CROSS JOIN feature f ON f.rid=b.rid",
            where="r.max_x>=:x0 AND r.min_x<=:x1 AND r.max_y>=:y0 AND r.min_y<=:y1 "
                  "AND r.max_z>=:z0 AND r.min_z<=:z1 AND"),
        "airspace": _AIR.format(
            src="rtree_airspace r CROSS JOIN airspace_restriction ar ON ar.rid=r.rid "
                "CROSS JOIN feature f ON f.rid=ar.rid",
            where="r.max_x>=:x0 AND r.min_x<=:x1 AND r.max_y>=:y0 AND r.min_y<=:y1 "
                  "AND r.max_z>=:z0 AND r.min_z<=:z1 AND r.max_t>=:t0 AND r.min_t<=:t1 AND"),
        "zone": _ZONES.format(
            src="rtree_exposure r CROSS JOIN exposure_zone e ON e.rid=r.rid CROSS JOIN feature f ON f.rid=e.rid",
            where="r.max_x>=:x0 AND r.min_x<=:x1 AND r.max_y>=:y0 AND r.min_y<=:y1 AND"),
    },
}


def fetch_sql(c, p, domain, window, mode):
    """Return raw rows for one access path. Parameters cover buffer/footprint padding."""
    b, z = _expanded(domain, CONFIG["buffer_m"]), _expanded(domain, RISK_MODEL["footprint_m"])
    t = {"t0": epoch(window[0]), "t1": epoch(window[1])}
    q = SQL[mode]
    return {
        "building": c.execute(q["building"], {**b, "owner": p["owners"]["scene"][1]}).fetchall(),
        "airspace": c.execute(q["airspace"], {**b, **t, "owner": p["owners"]["airspace"][1]}).fetchall(),
        "zone": c.execute(q["zone"], {**z, "owner": p["owners"]["exposure"][1],
                                      "dataset": p["dataset_id"]}).fetchall(),
    }


def objects_from_rows(raw):
    objs = [{"kind": "building", "id": r[0], "box": [[r[1], r[2], r[3]], [r[4], r[5], r[6]]]}
            for r in raw["building"]]
    for r in raw["airspace"]:
        objs.append({"kind": r[1], "id": r[0], "box": [[r[2], r[3], r[4]], [r[5], r[6], r[7]]],
                     "ceiling_m": r[8], "valid": [r[9], r[10]], "state": "published"})
    for r in raw["zone"]:
        objs.append({"kind": "zone", "id": r[0], "rid": r[1],
                     "box": [[r[2], r[3], r[4]], [r[5], r[6], r[7]]], "q": r[8]})
    return objs


# --------------------------------------------------------------------------- JSON export (v1 style)
def export_json(c, release_id, p):
    """Whole-release export: ZQO snapshot plus the validated risk values, as one JSON document."""
    snap = cat.snapshot(c, release_id)
    risk = {r[0]: r[1] for r in c.execute(
        "SELECT f.feature_id, dr.q_max FROM derived_risk dr JOIN feature f ON f.rid=dr.zone_rid "
        "WHERE dr.dataset_id=?", (p["dataset_id"],))}
    rids = {r[0]: r[1] for r in c.execute(
        "SELECT feature_id, rid FROM feature WHERE release_id=? AND layer='exposure'", (p["owners"]["exposure"][1],))}
    return json.dumps({"release_id": release_id, "layers": snap["layers"], "risk": risk, "zone_rid": rids,
                       "mappings": snap["mappings"]}, separators=(",", ":")).encode()


def objects_from_json(doc):
    layers = doc["layers"]
    objs = [{"kind": "building", "id": b["feature_id"],
             "box": [[b["bbox_min_x"], b["bbox_min_y"], b["base_z"]], [b["bbox_max_x"], b["bbox_max_y"], b["top_z"]]]}
            for b in layers["scene"]["building"]]
    for a in layers["airspace"]["airspace_restriction"]:
        if a["state"] not in ("published", "active"):
            continue
        top = 1.0e6 if a["kind"] == "height_limit" else (a["ceiling_m"] if a["ceiling_m"] is not None else 1.0e6)
        objs.append({"kind": a["kind"], "id": a["feature_id"],
                     "box": [[a["bbox_min_x"], a["bbox_min_y"], a["floor_z"]], [a["bbox_max_x"], a["bbox_max_y"], top]],
                     "ceiling_m": a["ceiling_m"], "valid": [a["effective_lo"], a["effective_hi"]], "state": "published"})
    for e in layers["exposure"]["exposure_zone"]:
        objs.append({"kind": "zone", "id": e["feature_id"], "rid": doc["zone_rid"][e["feature_id"]],
                     "box": [[e["bbox_min_x"], e["bbox_min_y"], e["floor_z"]], [e["bbox_max_x"], e["bbox_max_y"], e["top_z"]]],
                     "q": doc["risk"].get(e["feature_id"])})
    return objs


def time_relevant(obj, window):
    return obj["kind"] not in ("no_fly", "height_limit") or (obj["valid"][0] <= window[1] and window[0] <= obj["valid"][1])


# --------------------------------------------------------------------------- planner input
def planner_input(p, objs, domain, window, start, goal, query_id="q"):
    """Build the v1 planner snapshot and query. Objects are filtered and sorted deterministically."""
    keep = sorted((o for o in objs if relevant(o, domain) and time_relevant(o, window)),
                  key=lambda o: (o["kind"], o["id"]))
    meta = {"complete": True, "valid": p["valid"], "source": "unified-schema"}
    s = {
        "scene": {"crs": "starter-v0-local-m", "terrain_z": 0, "bounds": domain,
                  "obstacles": [{"id": o["id"], "box": o["box"]} for o in keep if o["kind"] == "building"],
                  **meta, "version": p["versions"]["scene"]},
        "airspace": {"restrictions": [
            {"id": o["id"], "box": o["box"], "kind": o["kind"], "state": o["state"], "valid": o["valid"],
             "ceiling_m": o["ceiling_m"] if o["ceiling_m"] is not None else inf}
            for o in keep if o["kind"] in ("no_fly", "height_limit")], **meta, "version": p["versions"]["airspace"]},
        "risk_data": {"background_q": 0.0, "zones": [{"id": o["id"], "box": o["box"], "q": o["q"]}
                                                    for o in keep if o["kind"] == "zone"],
                      **meta, "version": p["versions"]["risk_data"]},
        "risk_model": {**RISK_MODEL, "source": "lq-risk-v1", "version": p["versions"]["risk_model"]},
        "planner_config": {**CONFIG, "version": p["versions"]["planner_config"]},
        "versions": p["versions"],
    }
    q = {"id": query_id, "start": list(start), "goal": list(goal), "planned_at": window[0],
         "departure": window[0], "window": list(window), "versions": p["versions"]}
    zone_rid = {o["id"]: o["rid"] for o in keep if o["kind"] == "zone"}
    return s, q, zone_rid


def input_digest(s):
    return digest({k: s[k] for k in ("scene", "airspace", "risk_data")})


# --------------------------------------------------------------------------- explicit derived graph
def grid_nodes(domain):
    step = CONFIG["step_m"]
    (x0, y0, z0), (x1, y1, z1) = domain
    xs = [x0 + i * step for i in range(int(round((x1 - x0) / step)) + 1)]
    ys = [y0 + i * step for i in range(int(round((y1 - y0) / step)) + 1)]
    zs = [z0 + i * step for i in range(int(round((z1 - z0) / step)) + 1)]
    return [(x, y, z) for x in xs for y in ys for z in zs]


def _edge_entry(s, q, a, b):
    e = v1.edge_info(s, q, a, b)
    if e["state"] == "allowed":
        return (e["cost"], e["length_m"], e["time_s"], e["risk_proxy"], e["q_max"], tuple(e["sources"][1:]))
    return None if e["state"] == "forbidden" else "unknown"


PATCH_LIMIT = 0.5  # patch only if at most this share of nodes is touched; otherwise rebuild


def build_graph(s, q, region=None, base=None):
    """Materialise allowed edges in v1 neighbour order.

    With region (list of boxes) and base (graph of the previous release on the same domain,
    window and config), recompute only node states and edges whose box touches a region box;
    keep every other edge from base. If more than PATCH_LIMIT of the nodes are touched,
    rebuild instead (result['mode'] says which).
    """
    domain = s["scene"]["bounds"]
    step = CONFIG["step_m"]
    nodes = grid_nodes(domain)
    inside = set(nodes)

    def hits(lo, hi):
        for (rx0, ry0, rz0), (rx1, ry1, rz1) in region:
            if not (hi[0] < rx0 or lo[0] > rx1 or hi[1] < ry0 or lo[1] > ry1 or hi[2] < rz0 or lo[2] > rz1):
                return True
        return False

    if region is not None:
        # any edge leaving n lies inside the cube n +/- step, so this selects a superset of touched nodes
        touched = {n for n in nodes if hits([v - step for v in n], [v + step for v in n])}
        if len(touched) > PATCH_LIMIT * len(nodes):
            region, base = None, None
    mode = "built" if region is None else "patched"
    adj = {} if base is None else dict(base["adj"])
    point = {} if base is None else dict(base["point"])
    pair_cache = {}
    for n in (nodes if region is None else [n for n in nodes if n in touched]):
        if region is None or hits(n, n):
            point[n] = _edge_entry(s, q, n, n)
        prior = {} if base is None else dict(base["adj"].get(n, []))
        out = []
        for off in v1.OFFSETS:
            m = tuple(v + step * d for v, d in zip(n, off))
            if m not in inside:
                continue
            if region is not None and not hits([min(a, b) for a, b in zip(n, m)], [max(a, b) for a, b in zip(n, m)]):
                if m in prior:
                    out.append((m, prior[m]))
                continue
            key = (n, m) if n <= m else (m, n)
            if key not in pair_cache:
                pair_cache[key] = _edge_entry(s, q, n, m)
            entry = pair_cache[key]
            if entry is not None:
                out.append((m, entry))
        adj[n] = out
    return {"domain": domain, "adj": adj, "point": point, "nodes": len(nodes),
            "edges": sum(len(v) for v in adj.values()), "mode": mode,
            "recomputed_nodes": len(nodes) if region is None else len(touched)}


def graph_digest(g):
    return digest({"domain": g["domain"],
                   "adj": sorted([list(n), [[list(m), e if e == "unknown" else [round(x, 12) for x in e[:5]] + [list(e[5])]]
                                            for m, e in v]] for n, v in g["adj"].items()),
                   "point": sorted([list(n), e if e in (None, "unknown") else [round(x, 12) for x in e[:5]]]
                                   for n, e in g["point"].items())})


def search_graph(g, q, algorithm="astar"):
    """Same search as v1.plan, reading edges from the materialised graph."""
    start, goal = tuple(q["start"]), tuple(q["goal"])
    scale = CONFIG["length_scale_m"]
    for label, p in (("start", start), ("goal", goal)):
        e = g["point"].get(p)
        if e is None:
            return {"status": "infeasible", "reason": label + ":forbidden", "expanded": 0}
        if e == "unknown":
            return {"status": "unknown", "reason": label + ":unknown", "expanded": 0}

    def h(p):
        return dist(p, goal) / scale if algorithm == "astar" else 0

    frontier, best, parent = [(h(start), 0.0, start)], {start: 0.0}, {}
    expanded, saw_unknown = 0, False
    while frontier:
        _, cost, cur = heappop(frontier)
        if cost != best[cur]:
            continue
        expanded += 1
        if cur == goal:
            path = [cur]
            while cur != start:
                cur = parent[cur]
                path.append(cur)
            path.reverse()
            segs = [next(e for m, e in g["adj"][a] if m == b) for a, b in zip(path, path[1:])]
            duration = sum(s[2] for s in segs)
            from planner import instant
            if duration >= (instant(q["window"][1]) - instant(q["departure"])).total_seconds():
                return {"status": "unknown", "reason": "selected_route_exceeds_window", "expanded": expanded}
            return {"status": "feasible", "reason": "optimal_on_known_allowed_grid", "path": [list(p) for p in path],
                    "cost": sum(s[0] for s in segs), "length_m": sum(s[1] for s in segs), "time_s": duration,
                    "risk_proxy": sum(s[3] for s in segs), "segment_sources": [list(s[5]) for s in segs],
                    "expanded": expanded}
        for m, e in g["adj"].get(cur, []):
            if e == "unknown":
                saw_unknown = True
                continue
            cand = cost + e[0]
            if cand < best.get(m, inf):
                best[m], parent[m] = cand, cur
                heappush(frontier, (cand + h(m), cand, m))
    return {"status": "unknown" if saw_unknown else "infeasible",
            "reason": "unknown_edges_prevent_proof" if saw_unknown else "no_path_in_declared_grid",
            "expanded": expanded}


def lazy_plan(s, q, algorithm="astar"):
    """v1 planner, unchanged: edges are checked while searching."""
    r = v1.plan(s, q, algorithm)
    out = {"status": r["status"], "reason": r["reason"], "expanded": r["expanded"], "edge_checks": r["edge_checks"]}
    if r["status"] == "feasible":
        out.update(path=[list(p) for p in r["path"]], cost=r["metrics"]["cost"], length_m=r["metrics"]["length_m"],
                   time_s=r["metrics"]["time_s"], risk_proxy=r["metrics"]["risk_proxy"],
                   segment_sources=[[z for z in seg["sources"] if z != "background"] for seg in r["segments"]])
    return out


def same_result(a, b, tol=1e-9):
    if a["status"] != b["status"]:
        return False
    if a["status"] != "feasible":
        return True
    return abs(a["cost"] - b["cost"]) <= tol and a["path"] == b["path"]


# --------------------------------------------------------------------------- recording (ZC tables)
def store_graph(c, p, g, window, origin="built", parent=None, build_ms=0.0, payload_hash=None):
    gid = "g-" + uuid.uuid4().hex[:16]
    (x0, y0, z0), (x1, y1, z1) = g["domain"]
    cat.insert(c, "route_graph_cache", dict(
        graph_id=gid, release_id=p["release_id"], dataset_id=p["dataset_id"],
        min_x=x0, min_y=y0, min_z=z0, max_x=x1, max_y=y1, max_z=z1,
        window_lo=window[0], window_hi=window[1], config_hash=CONFIG_HASH,
        payload_hash=payload_hash or graph_digest(g), node_count=g["nodes"], edge_count=g["edges"],
        origin=origin, parent_graph_id=parent, created_at=cat.now(), build_ms=build_ms))
    return gid


def record_query(c, p, actor, window, start, goal, result, access_path, zone_rid, graph_id=None,
                 algorithm="astar"):
    """Write query_run, route_result and route_segment_source in one transaction."""
    qid = "q-" + uuid.uuid4().hex[:16]
    own = not c.in_transaction
    if own:
        c.execute("BEGIN IMMEDIATE")
    try:
        cat.insert(c, "query_run", dict(
            query_id=qid, release_id=p["release_id"], actor_id=actor, requested_at=cat.now(),
            window_lo=window[0], window_hi=window[1],
            start_x=start[0], start_y=start[1], start_z=start[2], goal_x=goal[0], goal_y=goal[1], goal_z=goal[2],
            planner_config=json.dumps({"config": CONFIG, "risk_model": RISK_MODEL}, sort_keys=True),
            config_hash=CONFIG_HASH, algorithm=algorithm, access_path=access_path,
            status=result["status"], reason=result["reason"], freshness=p["freshness"], graph_id=graph_id))
        if result["status"] == "feasible":
            cat.insert(c, "route_result", dict(
                query_id=qid, length_m=result["length_m"], time_s=result["time_s"],
                risk_proxy=result["risk_proxy"], cost=result["cost"], waypoints=json.dumps(result["path"])))
            for n, zones in enumerate(result["segment_sources"], start=1):
                for z in sorted(set(zones)):
                    cat.insert(c, "route_segment_source", dict(
                        query_id=qid, segment_no=n, component_id=p["owners"]["exposure"][0],
                        zone_rid=zone_rid[z], dataset_id=p["dataset_id"]))
        if own:
            c.execute("COMMIT")
    except Exception:
        if own and c.in_transaction:
            c.execute("ROLLBACK")
        raise
    return qid


def trace(c, query_id):
    return cat.rows(c, (ROOT / "docs/v2/schema/op_c.sql").read_text(encoding="utf-8"), {"query_id": query_id})


class Timer:
    def __init__(self):
        self.t = {}

    def __call__(self, name):
        timer = self

        class _T:
            def __enter__(self):
                self.s = time.perf_counter_ns()

            def __exit__(self, *a):
                timer.t[name] = timer.t.get(name, 0.0) + (time.perf_counter_ns() - self.s) / 1e6
        return _T()


def plan_route(c, release_id, window, start, goal, access_path, cache=None, json_doc=None):
    """One end-to-end Q1 through a chosen access path. Returns (result, pin, zone_rid, timings, graph_id)."""
    tm = Timer()
    graph_id = None
    c.execute("BEGIN")
    try:
        with tm("pin_ms"):
            p = pin(c, release_id, window)
        domain = domain_for(start, goal)
        if access_path == "graph_cache":
            key = (release_id, tuple(map(tuple, domain)), tuple(window), CONFIG_HASH)
            with tm("cache_lookup_ms"):
                row = c.execute(
                    "SELECT graph_id, payload_hash FROM route_graph_cache WHERE release_id=? AND min_x=? AND min_y=? "
                    "AND min_z=? AND max_x=? AND max_y=? AND max_z=? AND window_lo=? AND window_hi=? AND config_hash=?",
                    (release_id, *domain[0], *domain[1], window[0], window[1], CONFIG_HASH)).fetchone()
                g = cache.get(row[1]) if row else None
        if access_path == "json_snapshot":
            with tm("load_ms"):
                objs = objects_from_json(json.loads(json_doc))
        elif access_path in ("sql_full", "sql_rtree") or (access_path == "graph_cache" and g is None):
            with tm("db_ms"):
                raw = fetch_sql(c, p, domain, window, "sql_full" if access_path == "sql_full" else "sql_rtree")
            with tm("load_ms"):
                objs = objects_from_rows(raw)
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    if access_path == "graph_cache" and g is not None:
        s, q = None, {"start": list(start), "goal": list(goal), "window": list(window), "departure": window[0]}
        zone_rid = cache[row[1] + ":zones"]
        graph_id = row[0]
    else:
        with tm("load_ms"):
            s, q, zone_rid = planner_input(p, objs, domain, window, start, goal)
    if access_path == "graph_cache":
        if g is None:
            with tm("build_ms"):
                g = build_graph(s, q)
            ph = graph_digest(g)
            cache[ph], cache[ph + ":zones"] = g, zone_rid
            graph_id = store_graph(c, p, g, window, build_ms=tm.t["build_ms"], payload_hash=ph)
        with tm("search_ms"):
            result = search_graph(g, q)
    else:
        with tm("search_ms"):
            result = lazy_plan(s, q)
    return result, p, zone_rid, tm.t, graph_id
