"""Reproduce YHT results: quality, queries, storage/index benchmark, ZC export.

Run from the repository root:
    python3 docs/modules/yht/prototype/evaluate.py
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import sys
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import export_zc  # noqa: E402
import export_lq  # noqa: E402
import quality  # noqa: E402
import yht_model as model  # noqa: E402
from cache import QueryCache, query_key  # noqa: E402
from query import query_corridor, query_segment  # noqa: E402
from store import GridIndex, SQLiteStore  # noqa: E402

RESULTS = HERE.parent / "results"
REPO = HERE.parents[3]
WINDOW = {"start": "2026-11-05T08:05:00Z", "end": "2026-11-05T08:15:00Z"}
SCALES = (200, 800, 2400)
SEED = 20261105


def _filler_pool():
    """Deterministic 6-8 m blocks on a 10 m inset lattice, no named overlaps."""
    named = model.buildings()
    occupied = []
    for bld in named:
        xs = [p[0] for p in bld["footprint"]]
        ys = [p[1] for p in bld["footprint"]]
        occupied.append((min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3))
    rng = random.Random(SEED)
    pool = []
    for gx in range(75):
        for gy in range(75):
            x0, y0 = gx * 8 + 1, gy * 8 + 1
            if any(x0 < ox1 and x0 + 6 > ox0 and y0 < oy1 and y0 + 6 > oy0
                   for ox0, oy0, ox1, oy1 in occupied):
                continue
            side = rng.choice((5.0, 6.0))
            height = round(rng.uniform(6.0, 45.0), 1)
            pool.append({
                "id": "F-%04d-%04d" % (gx, gy),
                "kind": "building",
                "name": "合成体块 %02d-%02d" % (gx, gy),
                "footprint": model.rect(x0, y0, x0 + side, y0 + side),
                "base_z": 0.0,
                "top_z": height,
                "height_m": height,
                "footprint_source": "SRC-FOOTPRINT",
                "height_source": "SRC-HEIGHT",
                "quality": "derived",
                "valid": list(model.VALID),
            })
    return pool


FILLERS = _filler_pool()


def make_scene(n):
    s = deepcopy(model.scene())
    s["buildings"] = s["buildings"] + deepcopy(FILLERS[:max(0, n - len(s["buildings"]))])
    if len(s["buildings"]) != n:
        raise RuntimeError("cannot reach scale %d with %d fillers" % (n, len(FILLERS)))
    return model.seal(s)


def make_queries():
    rng = random.Random(SEED + 1)
    corridors, segments = [], []
    for _ in range(120):
        a = [rng.uniform(20, 560), rng.uniform(20, 560), rng.uniform(25, 130)]
        length = rng.uniform(70, 260)
        angle = rng.uniform(0, 6.283185307179586)
        b = [min(580, max(20, a[0] + length * __import__("math").cos(angle))),
             min(580, max(20, a[1] + length * __import__("math").sin(angle))),
             min(140, max(20, a[2] + rng.uniform(-30, 30)))]
        corridors.append((a, b, 15.0))
    for _ in range(80):
        a = [rng.uniform(20, 560), rng.uniform(20, 560), rng.uniform(20, 120)]
        length = rng.uniform(50, 220)
        angle = rng.uniform(0, 6.283185307179586)
        b = [min(580, max(20, a[0] + length * __import__("math").cos(angle))),
             min(580, max(20, a[1] + length * __import__("math").sin(angle))),
             min(140, max(15, a[2] + rng.uniform(-20, 20)))]
        segments.append((a, b))
    return corridors, segments


CORRIDORS, SEGMENTS = make_queries()


def _signature(kind, result):
    if kind == "q1":
        return (result["status"],
                tuple(sorted((n["id"], n["effect"]) for n in result["nearby"])),
                tuple(sorted(a["id"] for a in result["airspace"]
                             if a["effect"] == "blocked")))
    return (result["status"],
            tuple(sorted(result["blocked_by"])),
            tuple(sorted(b["id"] for b in result["buildings"])))


def _summ(values):
    values = sorted(values)
    n = len(values)
    return {
        "median_us": round(statistics.median(values) * 1e6, 3),
        "p95_us": round(values[max(0, int(round(0.95 * (n - 1))))] * 1e6, 3),
        "mean_us": round(sum(values) / n * 1e6, 3),
    }


def _time_calls(fn, items, repeats=5):
    samples = []
    last = None
    fn(items[0])  # warm-up outside the measured window
    for _ in range(repeats):
        for item in items:
            began = perf_counter()
            last = fn(item)
            samples.append(perf_counter() - began)
    return samples, last


def _run_method(name, scene, queries, factory):
    if name == "bruteforce":
        q1 = lambda item: query_corridor(  # noqa: E731
            scene, item[0], item[1], item[2], WINDOW, scene["versions"],
            building_candidates=scene["buildings"], verify=False)
        q2 = lambda item: query_segment(  # noqa: E731
            scene, item[0], item[1], WINDOW, scene["versions"],
            building_candidates=scene["buildings"], verify=False)
        build_s = 0.0
        storage = None
    else:
        began = perf_counter()
        storage = factory(scene)
        build_s = perf_counter() - began
        q1 = lambda item: storage.corridor_query(  # noqa: E731
            item[0], item[1], item[2], WINDOW, scene["versions"], verify=False)
        q2 = lambda item: storage.segment_query(  # noqa: E731
            item[0], item[1], WINDOW, scene["versions"], verify=False)
    s1, last1 = _time_calls(q1, queries[0])
    s2, last2 = _time_calls(q2, queries[1])
    avg_candidates = sum(r["candidates"] for r in
                         [q1(i) for i in queries[0]] +
                         [q2(i) for i in queries[1]]) / (len(queries[0]) + len(queries[1]))
    out = {
        "method": name,
        "build_s": round(build_s, 4),
        "q1": _summ(s1),
        "q2": _summ(s2),
        "avg_candidates": round(avg_candidates, 1),
        "candidate_ratio": round(avg_candidates / len(scene["buildings"]), 4),
        "signatures": [_signature("q1", q1(i)) for i in queries[0]] +
                      [_signature("q2", q2(i)) for i in queries[1]],
    }
    if storage is not None and hasattr(storage, "stats"):
        out["storage"] = storage.stats()
        storage.close()
    return out


def benchmark():
    data = []
    for n in SCALES:
        s = make_scene(n)
        release_problems = model.verify_release(s)
        if release_problems:
            raise RuntimeError("release invalid at scale %d: %s" %
                               (n, release_problems))
        base_report = quality.check_scene(s)
        if not base_report["ok"]:
            raise RuntimeError("quality failed at scale %d: %s" %
                               (n, base_report["errors"][:2]))
        methods = {}
        for name, factory in (
            ("bruteforce", None),
            ("sqlite_2d_z", lambda sc: _sqlite(sc, "2d")),
            ("sqlite_3d", lambda sc: _sqlite(sc, "3d")),
            ("grid_3d", lambda sc: GridIndex(sc)),
        ):
            methods[name] = _run_method(name, s, (CORRIDORS, SEGMENTS), factory)
        ref = methods["bruteforce"]["signatures"]
        mismatches = {m: sum(1 for a, b in zip(ref, r["signatures"]) if a != b)
                      for m, r in methods.items() if m != "bruteforce"}
        if any(mismatches.values()):
            raise RuntimeError("index/bruteforce mismatch at %d: %s" % (n, mismatches))
        for m in methods:
            del methods[m]["signatures"]
        data.append({
            "buildings": n,
            "scene": model.scene_stats(s),
            "release_bytes": len(json.dumps(s, ensure_ascii=False).encode("utf-8")),
            "quality": base_report["counts"],
            "methods": methods,
            "signature_mismatches": mismatches,
        })
        print("scale %d: %s" % (n, {
            m: (v["q2"]["median_us"], v["avg_candidates"]) for m, v in methods.items()}))

        if n == SCALES[-1]:
            path = RESULTS / "sample.sqlite"
            store = SQLiteStore(s, str(path), fast=True)
            store.build()
            size = path.stat().st_size
            store.close()
            data[-1]["sqlite_file_bytes"] = size
            path.unlink()
    return data


def _sqlite(scene, mode):
    store = SQLiteStore(scene, ":memory:", fast=True)
    store.build()
    store.mode = mode
    if mode == "2d":
        store.corridor_query_orig = store.corridor_query
        store.segment_query_orig = store.segment_query
        store.corridor_query = lambda a, b, r, w, v, **kw: store.corridor_query_orig(
            a, b, r, w, v, "2d", **kw)
        store.segment_query = lambda a, b, w, v, **kw: store.segment_query_orig(
            a, b, w, v, "2d", **kw)
    return store


def examples():
    s = model.seal(model.scene())
    out = {
        "window": WINDOW,
        "versions": s["versions"],
        "q2_building": query_segment(
            s, [240, 40, 20], [300, 40, 20], WINDOW, s["versions"]),
        "q2_no_fly": query_segment(
            s, [140, 150, 80], [160, 150, 80], WINDOW, s["versions"]),
        "q2_ceiling": query_segment(
            s, [325, 105, 65], [335, 105, 65], WINDOW, s["versions"]),
        "q2_allowed": query_segment(
            s, [20, 300, 80], [120, 300, 80], WINDOW, s["versions"]),
        "q2_version_mismatch": query_segment(
            s, [280, 120, 70], [370, 120, 70], WINDOW,
            dict(s["versions"], scene="mock-yht-scene-deadbeef")),
        "q1_clear": query_corridor(
            s, [20, 20, 140], [240, 220, 140], 15.0, WINDOW, s["versions"]),
        "q1_blocked": query_corridor(
            s, [20, 20, 80], [240, 220, 80], 20.0, WINDOW, s["versions"]),
        "quality": quality.check_scene(s)["counts"],
        "quality_faults": quality.run_fault_injection(),
        "mutation_queries": quality.query_after_mutation(),
    }
    return out


def update_example():
    s = model.seal(model.scene())
    before = query_segment(s, [50, 240, 60], [50, 300, 60], WINDOW, s["versions"])
    nxt = deepcopy(s)
    nxt["airspace"].append({
        "id": "NF-003", "kind": "no_fly", "name": "临时活动禁飞",
        "footprint": model.rect(40, 250, 80, 290),
        "floor_z": 0.0, "ceiling_z": 120.0, "ceiling_m": None,
        "valid": ["2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z"],
        "state": "published", "authority": "mock-airspace-office",
        "source_id": "SRC-AIRSPACE", "quality": "assumed",
    })
    nxt = model.seal(nxt)
    stale = query_segment(nxt, [50, 240, 60], [50, 300, 60], WINDOW, s["versions"])
    after = query_segment(nxt, [50, 240, 60], [50, 300, 60], WINDOW, nxt["versions"])
    return {
        "before": {"status": before["status"], "versions": before["versions"]},
        "after": {"status": after["status"], "blocked_by": after["blocked_by"],
                  "versions": after["versions"]},
        "old_versions_against_new_release": {
            "status": stale["status"], "reasons": stale["reasons"]},
        "changed_versions": {
            k: [s["versions"][k], nxt["versions"][k]]
            for k in model.VERSION_KEYS if s["versions"][k] != nxt["versions"][k]},
    }


def zc_export():
    s = model.seal(model.scene())
    payload = export_zc.write_export(
        s, WINDOW, ((0, 0, 10), (450, 450, 120)), (20, 20, 70),
        (420, 420, 70), RESULTS / "zc-export.json", repo_root=str(REPO))
    plan = payload["zc_report"]["plan"]
    return {
        "preflight": payload["zc_report"]["preflight"],
        "plan_status": plan["status"] if plan else None,
        "reason": plan["reason"] if plan else None,
        "metrics": plan["metrics"] if plan else None,
        "expanded": plan["expanded"] if plan else None,
        "edge_checks": plan["edge_checks"] if plan else None,
        "elapsed_ms": plan["elapsed_ms"] if plan else None,
        "q2_assess": payload["zc_report"].get("q2_assess"),
        "obstacles": len(payload["snapshot"]["scene"]["obstacles"]),
        "restrictions": [r["id"] for r in payload["snapshot"]["airspace"]["restrictions"]],
        "risk_zones": len(payload["snapshot"]["risk_data"]["zones"]),
        "versions": payload["snapshot"]["versions"],
    }


def lq_export():
    payload = export_lq.write_export(RESULTS / "lq-export.json")
    report = payload["report"]
    plan = report.get("plan")
    return {
        "profiles": report.get("profiles"),
        "preflight": report.get("preflight"),
        "plan_status": plan["status"] if plan else None,
        "reason": plan["reason"] if plan else None,
        "metrics": plan["metrics"] if plan else None,
        "expanded": plan["expanded"] if plan else None,
        "edge_checks": plan["edge_checks"] if plan else None,
        "elapsed_ms": plan["elapsed_ms"] if plan else None,
        "q2_assess": report.get("q2_assess"),
        "error": report.get("error"),
        "versions": report.get("lq_versions"),
    }


def cache_benchmark():
    """Cold miss vs hit latency for the local version-keyed cache."""
    s = model.seal(model.scene())
    store = SQLiteStore(s)
    store.build()

    items = []
    for a, b, radius in CORRIDORS[:10]:
        items.append(("q1", a, b, radius))
    for a, b in SEGMENTS[:10]:
        items.append(("q2", a, b, None))

    def run(cache, item):
        kind, a, b, radius = item
        if kind == "q1":
            payload = {"a": a, "b": b, "radius": radius, "window": WINDOW}
            compute = lambda: store.corridor_query(  # noqa: E731
                a, b, radius, WINDOW, s["versions"])
        else:
            payload = {"a": a, "b": b, "window": WINDOW}
            compute = lambda: store.segment_query(  # noqa: E731
                a, b, WINDOW, s["versions"])
        return cache.get_or_compute(query_key(kind, payload), s["versions"], compute)

    cold_cache = QueryCache(capacity=128)
    cold = []
    for item in items:
        began = perf_counter()
        run(cold_cache, item)
        cold.append(perf_counter() - began)

    warm_cache = QueryCache(capacity=128)
    for item in items:
        run(warm_cache, item)
    warm_cache.reset_stats()
    warm = []
    for _ in range(3):
        for item in items:
            began = perf_counter()
            run(warm_cache, item)
            warm.append(perf_counter() - began)

    s2 = deepcopy(s)
    s2["buildings"][0]["height_m"] = 121.0
    s2["buildings"][0]["top_z"] = 121.0
    s2 = model.seal(s2)
    last_key = query_key("q2", {"a": items[-1][1], "b": items[-1][2],
                                "window": WINDOW})
    warm_cache.get_or_compute(last_key, s2["versions"],
                              lambda: {"status": "unknown", "reason": "new_release"})

    store.close()
    stats = warm_cache.stats()
    return {
        "queries": len(items),
        "cold_median_us": round(statistics.median(cold) * 1e6, 3),
        "warm_median_us": round(statistics.median(warm) * 1e6, 3),
        "speedup": round(statistics.median(cold) / statistics.median(warm), 2),
        "hit_rate": round(stats["hit_rate"], 4),
        "warm_hits": stats["hits"],
        "warm_misses": stats["misses"],
        "entries": stats["entries"],
        "invalidations": stats["invalidations"],
        "note": "single-process in-memory cache; hit includes deep copy; not a "
                "distributed cache or a production QPS measurement",
    }


def write_csv(data, path):
    lines = ["scale,method,q1_median_us,q1_p95_us,q2_median_us,q2_p95_us,"
             "avg_candidates,candidate_ratio,build_s"]
    for row in data:
        for method in ("bruteforce", "sqlite_2d_z", "sqlite_3d", "grid_3d"):
            m = row["methods"][method]
            lines.append(",".join(str(x) for x in (
                row["buildings"], method, m["q1"]["median_us"],
                m["q1"]["p95_us"], m["q2"]["median_us"], m["q2"]["p95_us"],
                m["avg_candidates"], m["candidate_ratio"], m["build_s"])))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    began = datetime.now(timezone.utc).isoformat()
    data = benchmark()
    write_csv(data, RESULTS / "summary.csv")
    meta = {
        "generated_at": began,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "processes": 1,
        },
        "scales": list(SCALES),
        "queries": {"corridor": len(CORRIDORS), "segment": len(SEGMENTS),
                    "radius_m": 15.0, "repeats": 5},
        "window": WINDOW,
        "methods": ["bruteforce", "sqlite_2d_z", "sqlite_3d", "grid_3d"],
        "note": "in-process wall clock; release integrity is verified once per "
                "scene load and query timing excludes re-hashing; includes Python "
                "geometry re-check; not a DB server benchmark",
    }
    (RESULTS / "benchmark.json").write_text(json.dumps(
        {"meta": meta, "results": data}, ensure_ascii=False, indent=2,
        sort_keys=True), encoding="utf-8")
    base = model.seal(model.scene())
    (RESULTS / "scene.json").write_text(json.dumps(
        base, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (RESULTS / "scene-stats.json").write_text(json.dumps(
        {"stats": model.scene_stats(base),
         "release_bytes": len(json.dumps(base, ensure_ascii=False).encode("utf-8")),
         "layer_versions": base["versions"],
         "manifest": base["manifest"]},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "quality.json").write_text(json.dumps(
        {"baseline": quality.check_scene(base),
         "faults": quality.run_fault_injection(),
         "mutation_queries": quality.query_after_mutation()},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "cache.json").write_text(json.dumps(
        cache_benchmark(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (RESULTS / "query-examples.json").write_text(json.dumps(
        examples(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "update-example.json").write_text(json.dumps(
        update_example(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    (RESULTS / "zc-export-summary.json").write_text(json.dumps(
        zc_export(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    (RESULTS / "lq-export-summary.json").write_text(json.dumps(
        lq_export(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    print("wrote", RESULTS)


if __name__ == "__main__":
    main()
