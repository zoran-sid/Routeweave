"""Export a YHT release window into ZC's starter-v0 snapshot.

The adapter is deliberately conservative: an L-shaped footprint becomes its
bounding box, all active restrictions inside the window are kept, and exposure
polygons become ZC risk boxes with the same q. It never invents a field that
ZC's preflight does not define. The ZC modules are imported only by
``bind_and_check`` so exporting does not depend on ZC being present.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

ZC_KEYS = ("scene", "airspace", "risk_data", "risk_model", "planner_config")


def _clip_box(box, lo, hi):
    low = [max(box[0][i], lo[i]) for i in range(3)]
    high = [min(box[1][i], hi[i]) for i in range(3)]
    if any(low[i] >= high[i] for i in range(3)):
        return None
    return [low, high]


def _polygon_box(poly, z0, z1):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return [[min(xs), min(ys), z0], [max(xs), max(ys), z1]]


def export_snapshot(s, window, search_bounds, start, goal, query_id="yht-zc-1"):
    """Build a ZC-shaped snapshot and query; versions are placeholders."""
    lo, hi = search_bounds
    obstacles = []
    for bld in s["buildings"]:
        box = _clip_box(
            [[min(p[0] for p in bld["footprint"]),
              min(p[1] for p in bld["footprint"]), bld["base_z"]],
             [max(p[0] for p in bld["footprint"]),
              max(p[1] for p in bld["footprint"]),
              bld["top_z"] if bld["top_z"] is not None else hi[2]]], lo, hi)
        if box:
            obstacles.append({"id": bld["id"], "box": box})
    restrictions = []
    for vol in s["airspace"]:
        if vol["state"] != "published":
            continue
        if not (vol["valid"][0] < window["end"] and vol["valid"][1] > window["start"]):
            continue
        box = _clip_box(_polygon_box(vol["footprint"], vol["floor_z"],
                                     vol["ceiling_z"]), lo, hi)
        if not box:
            continue
        item = {
            "id": vol["id"], "kind": vol["kind"], "box": box,
            "valid": list(vol["valid"]), "state": vol["state"],
            "source": "yht-" + vol["source_id"],
        }
        if vol["kind"] == "height_limit":
            item["ceiling_m"] = vol["ceiling_m"]
        restrictions.append(item)
    zones = []
    for zone in s["ground_zones"]:
        box = _clip_box(_polygon_box(zone["polygon"], 0.0, hi[2]), lo, hi)
        if box and zone.get("q") is not None:
            zones.append({"id": zone["id"], "box": box, "q": zone["q"]})
    snapshot = {
        "scene": {
            "crs": "starter-v0-local-m",
            "terrain_z": 0.0,
            "bounds": [list(lo), list(hi)],
            "obstacles": obstacles,
            "complete": True,
            "valid": list(s["valid"]),
            "source": "yht-synthetic-district-v1",
            "version": "pending",
        },
        "airspace": {
            "restrictions": restrictions,
            "complete": True,
            "valid": list(s["valid"]),
            "source": "yht-synthetic-district-v1",
            "version": "pending",
        },
        "risk_data": {
            "background_q": 0.02,
            "zones": zones,
            "complete": True,
            "valid": list(s["valid"]),
            "source": "yht-synthetic-exposure-v1",
            "version": "pending",
        },
        "risk_model": {
            "hard_threshold": 0.9,
            "footprint_m": 5.0,
            "aggregation": "edge_max_times_length",
            "version": "pending",
        },
        "planner_config": {
            "step_m": 20.0,
            "buffer_m": 5.0,
            "speed_mps": 10.0,
            "lambda_risk": 0.0,
            "length_scale_m": 100.0,
            "version": "pending",
        },
    }
    query = {
        "id": query_id,
        "start": list(start),
        "goal": list(goal),
        "planned_at": window["start"],
        "departure": window["start"],
        "window": [window["start"], window["end"]],
        "versions": {},
    }
    return snapshot, query


def _load_zc(repo_root):
    proto = Path(repo_root) / "docs" / "modules" / "zc" / "prototype"
    specs = {}
    for name in ("scenarios", "planner"):
        spec = importlib.util.spec_from_file_location(
            "yht_" + name, proto / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        specs[name] = module
    return specs["scenarios"], specs["planner"]


def bind_and_check(snapshot, query, repo_root="."):
    """Bind ZC versions, then run preflight and one baseline plan."""
    scenarios, planner = _load_zc(repo_root)
    s, q = scenarios.bind(deepcopy(snapshot), deepcopy(query))
    error = planner.preflight(s, q)
    report = {"preflight": error, "plan": None}
    if error is None:
        report["plan"] = planner.plan(s, q, "astar")
        a = q["start"]
        b = q["goal"]
        report["q2_assess"] = planner.assess_segment(s, q, a, b)
    return s, q, report


def write_export(s, window, search_bounds, start, goal, out_path, repo_root="."):
    snapshot, query = export_snapshot(s, window, search_bounds, start, goal)
    snapshot, query, report = bind_and_check(
        snapshot, query, repo_root=repo_root)
    payload = {
        "schema": "yht-zc-export-0.1",
        "source_release": s["versions"],
        "window": dict(window),
        "search_bounds": [list(search_bounds[0]), list(search_bounds[1])],
        "snapshot": snapshot,
        "query": query,
        "zc_report": report,
    }
    Path(out_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    return payload
