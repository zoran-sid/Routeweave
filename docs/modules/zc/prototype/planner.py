"""SkyRoute ZC: finite 3D grid search over a pinned synthetic snapshot.

Only Python's standard library is required. See ../design.md for model semantics.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from heapq import heappop, heappush
from itertools import product
from math import dist, inf, isfinite
from time import perf_counter

VERSION_KEYS = ("scene", "airspace", "risk_data", "risk_model", "planner_config")
OFFSETS = tuple(p for p in product((-1, 0, 1), repeat=3) if p != (0, 0, 0))


def instant(value):
    if not isinstance(value, str):
        raise ValueError("invalid_time_value")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timezone_required")
    return t.astimezone(timezone.utc)


def overlap(a, b):
    """Half-open temporal intervals."""
    return instant(a[0]) < instant(b[1]) and instant(b[0]) < instant(a[1])


def clip_segment(a, b, box, margin=0):
    """Closed segment / closed AABB slab clipping, including interior/tangency.

    Per-axis expansion is a conservative L-infinity safety envelope.
    Returns the intersecting parameter interval on [0, 1], or None.
    """
    low, high = 0.0, 1.0
    for i in range(3):
        lo, hi = box[0][i] - margin, box[1][i] + margin
        delta = b[i] - a[i]
        if delta == 0:
            if not lo <= a[i] <= hi:
                return None
        else:
            t1, t2 = (lo - a[i]) / delta, (hi - a[i]) / delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low > high:
                return None
    return low, high


def valid_box(box):
    return (len(box) == 2 and all(len(p) == 3 for p in box)
            and all(isfinite(v) for p in box for v in p)
            and all(a <= b for a, b in zip(*box)))


def preflight(s, q):
    """Fail closed for absent, malformed, stale or version-mixed inputs."""
    try:
        for key in VERSION_KEYS:
            if not s["versions"][key] or s[key]["version"] != s["versions"][key]:
                return "version_mismatch:" + key
        if q["versions"] != s["versions"]:
            return "query_snapshot_mismatch"
        start, end = map(instant, q["window"])
        if not instant(q["planned_at"]) <= instant(q["departure"]) == start < end:
            return "invalid_query_time"
        for key in ("scene", "airspace", "risk_data"):
            data = s[key]
            if not data["complete"]:
                return "incomplete:" + key
            if not instant(data["valid"][0]) <= start < end <= instant(data["valid"][1]):
                return "stale_or_uncovered:" + key
        scene, cfg, risk, model = (s[k] for k in
                                  ("scene", "planner_config", "risk_data", "risk_model"))
        if scene["crs"] != "starter-v0-local-m" or scene["terrain_z"] != 0:
            return "unsupported_spatial_reference_or_terrain"
        nums = [cfg[k] for k in ("step_m", "buffer_m", "speed_mps", "lambda_risk", "length_scale_m")]
        if not all(isfinite(v) for v in nums) or min(nums) < 0 or any(
                cfg[k] <= 0 for k in ("step_m", "speed_mps", "length_scale_m")):
            return "invalid_config"
        if not valid_box(scene["bounds"]) or any(not valid_box(b["box"]) for b in scene["obstacles"]):
            return "invalid_geometry"
        if scene["bounds"][0][2] <= cfg["buffer_m"]:
            return "terrain_clearance"
        if not all(isfinite(v) for v in (model["hard_threshold"], model["footprint_m"], risk["background_q"])):
            return "invalid_risk"
        if not (0 <= risk["background_q"] <= 1 and 0 < model["hard_threshold"] <= 1 and model["footprint_m"] >= 0):
            return "invalid_risk"
        if model["aggregation"] != "edge_max_times_length":
            return "unsupported_risk_aggregation"
        for z in risk["zones"]:
            if not valid_box(z["box"]) or (z["q"] is not None and
                    (not isfinite(z["q"]) or not 0 <= z["q"] <= 1)):
                return "invalid_risk_zone"
        for r in s["airspace"]["restrictions"]:
            if (not valid_box(r["box"]) or r["kind"] not in ("no_fly", "height_limit")
                    or r["state"] not in ("published", "revoked")
                    or instant(r["valid"][0]) >= instant(r["valid"][1])):
                return "invalid_airspace"
            if r["kind"] == "height_limit" and not isfinite(r["ceiling_m"]):
                return "invalid_ceiling"
        for p in (q["start"], q["goal"]):
            if len(p) != 3 or not all(isfinite(v) for v in p):
                return "invalid_endpoint"
            if not all(lo <= v <= hi for lo, v, hi in zip(scene["bounds"][0], p, scene["bounds"][1])):
                return "endpoint_outside_search_domain"
            if any(abs((v - lo) / cfg["step_m"] - round((v - lo) / cfg["step_m"])) > 1e-8
                   for v, lo in zip(p, scene["bounds"][0])):
                return "endpoint_off_grid"
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return "missing_or_malformed_input"
    return None


def edge_info(s, q, a, b):
    """Q2-style segment assessment; call only after preflight."""
    cfg, model = s["planner_config"], s["risk_model"]
    if any(not all(lo <= v <= hi for lo, v, hi in zip(s["scene"]["bounds"][0], p, s["scene"]["bounds"][1]))
           for p in (a, b)):
        return {"state": "forbidden", "reason": "domain"}
    for obs in s["scene"]["obstacles"]:
        if clip_segment(a, b, obs["box"], cfg["buffer_m"]) is not None:
            return {"state": "forbidden", "reason": "obstacle:" + obs["id"]}
    for r in s["airspace"]["restrictions"]:
        if r["state"] != "published" or not overlap(r["valid"], q["window"]):
            continue
        if r["kind"] == "no_fly":
            hit = clip_segment(a, b, r["box"], cfg["buffer_m"]) is not None
        else:
            # A height cap applies to its horizontal area at all altitudes.
            box = [[r["box"][0][0], r["box"][0][1], -inf],
                   [r["box"][1][0], r["box"][1][1], inf]]
            interval = clip_segment(a, b, box, cfg["buffer_m"])
            hit = interval is not None and max(a[2] + t * (b[2] - a[2]) for t in interval) + cfg["buffer_m"] > r["ceiling_m"]
        if hit:
            return {"state": "forbidden", "reason": "airspace:" + r["id"]}
    value, sources, unknown = s["risk_data"]["background_q"], ["background"], False
    for zone in s["risk_data"]["zones"]:
        # Ground footprint is independent of flight altitude in this mock model.
        box = [[zone["box"][0][0], zone["box"][0][1], -inf],
               [zone["box"][1][0], zone["box"][1][1], inf]]
        if clip_segment(a, b, box, model["footprint_m"]) is not None:
            sources.append(zone["id"])
            if zone["q"] is None:
                unknown = True
            else:
                value = max(value, zone["q"])
    if value >= model["hard_threshold"]:
        return {"state": "forbidden", "reason": "risk_threshold", "sources": sources}
    if unknown:
        return {"state": "unknown", "reason": "unknown_risk", "sources": sources}
    length = dist(a, b)
    risk = length / cfg["length_scale_m"] * value
    return {"state": "allowed", "reason": "checked", "length_m": length,
            "time_s": length / cfg["speed_mps"], "risk_proxy": risk,
            "q_max": value, "sources": sources,
            "cost": length / cfg["length_scale_m"] + cfg["lambda_risk"] * risk}


def assess_segment(snapshot, query, a, b):
    """Auditable segment helper, not a complete region-query service."""
    s, q = deepcopy(snapshot), deepcopy(query)
    error = preflight(s, q)
    if not error:
        valid_points = all(
            isinstance(p, (list, tuple)) and len(p) == 3
            and all(type(v) in (int, float) and isfinite(v) for v in p)
            for p in (a, b)
        )
        if not valid_points:
            error = "invalid_segment_endpoint"
        elif any(not all(lo <= v <= hi for lo, v, hi in
                         zip(s['scene']['bounds'][0], p, s['scene']['bounds'][1]))
                 for p in (a, b)):
            error = "segment_outside_search_domain"
    result = {"state": "unknown", "reason": error} if error else edge_info(s, q, a, b)
    return {**result, "versions": s.get("versions", {}), "window": q.get("window")}


def plan(snapshot, query, algorithm="astar", max_expansions=None):
    if algorithm not in ("astar", "dijkstra"):
        raise ValueError("algorithm must be astar or dijkstra")
    began = perf_counter()
    s, q = deepcopy(snapshot), deepcopy(query)
    expanded = checked = 0

    def result(state, reason, path=None, segments=None):
        path, segments = path or [], segments or []
        length = sum(e["length_m"] for e in segments)
        duration = sum(e["time_s"] for e in segments)
        return {"query_id": q.get("id"), "status": state, "reason": reason,
                "algorithm": algorithm, "versions": s.get("versions", {}),
                "planned_at": q.get("planned_at"), "departure": q.get("departure"),
                "window": q.get("window"), "time_policy": "whole_window_conservative",
                "search_scope": "finite_26_neighbor_grid", "path": path,
                "segments": [{"from": a, "to": b, **e} for a, b, e in zip(path, path[1:], segments)],
                "metrics": {"length_m": length, "time_s": duration,
                            "risk_proxy": sum(e["risk_proxy"] for e in segments),
                            "cost": sum(e["cost"] for e in segments)} if state == "feasible" else None,
                "arrival": (instant(q["departure"]) + timedelta(seconds=duration)).isoformat() if state == "feasible" else None,
                "expanded": expanded, "edge_checks": checked,
                "elapsed_ms": (perf_counter() - began) * 1000}

    error = preflight(s, q)
    if error:
        return result("unknown", error)
    start, goal = tuple(q["start"]), tuple(q["goal"])
    cfg = s["planner_config"]
    for label, p in (("start", start), ("goal", goal)):
        e = edge_info(s, q, p, p)
        if e["state"] != "allowed":
            return result("unknown" if e["state"] == "unknown" else "infeasible", label + ":" + e["reason"])

    def heuristic(p):
        return dist(p, goal) / cfg["length_scale_m"] if algorithm == "astar" else 0

    frontier, best, parent = [(heuristic(start), 0.0, start)], {start: 0.0}, {}
    saw_unknown = False
    while frontier:
        _, cost, current = heappop(frontier)
        if cost != best[current]:
            continue
        if max_expansions is not None and expanded >= max_expansions:
            return result("unknown", "search_budget_exhausted")
        expanded += 1
        if current == goal:
            path = [current]
            while current != start:
                current = parent[current]
                path.append(current)
            path.reverse()
            segments = [edge_info(s, q, a, b) for a, b in zip(path, path[1:])]
            # A single cost label does not solve a resource-constrained deadline problem.
            if sum(e["time_s"] for e in segments) >= (instant(q["window"][1]) - instant(q["departure"])).total_seconds():
                return result("unknown", "selected_route_exceeds_window")
            return result("feasible", "optimal_on_known_allowed_grid", path, segments)
        for offset in OFFSETS:
            nxt = tuple(v + cfg["step_m"] * d for v, d in zip(current, offset))
            if not all(lo <= v <= hi for lo, v, hi in zip(s["scene"]["bounds"][0], nxt, s["scene"]["bounds"][1])):
                continue
            checked += 1
            e = edge_info(s, q, current, nxt)
            if e["state"] == "unknown":
                saw_unknown = True
            if e["state"] != "allowed":
                continue
            candidate = cost + e["cost"]
            if candidate < best.get(nxt, inf):
                best[nxt], parent[nxt] = candidate, current
                heappush(frontier, (candidate + heuristic(nxt), candidate, nxt))
    return result("unknown" if saw_unknown else "infeasible",
                  "unknown_edges_prevent_proof" if saw_unknown else "no_path_in_declared_grid")
