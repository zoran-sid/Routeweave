"""Q1 data-access experiment: fixed A*, same tasks, four ways to feed the planner.

For each city size and task, measure separately:
  pin      read transaction, layer owners, freshness, validated risk dataset
  io       JSON path only: read the whole-release export file
  db       SQL path: rows returned by the database
  load     parse/convert rows or JSON into planner objects and filter to the search domain
  search   v1 A* with edge checks during search (paths json_snapshot, sql_full, sql_rtree)
  build    graph_cache miss: materialise every allowed edge of the domain
  gsearch  A* (and Dijkstra) over the materialised graph; on a cache hit this is the whole cost

Correctness: the three non-cached paths must give the planner byte-identical input
(input_digest), and the lazy v1 A*, graph A* and graph Dijkstra must agree.

python3 -B docs/modules/zc/v2/experiments/access_paths.py
python3 -B docs/modules/zc/v2/experiments/access_paths.py --quick --output /tmp/zc-access.json
"""
import argparse
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


def ms(ns):
    return ns / 1e6


def timed(fn, repeats):
    samples, out = [], None
    for _ in range(repeats):
        t = time.perf_counter_ns()
        out = fn()
        samples.append(ms(time.perf_counter_ns() - t))
    return statistics.median(samples), out


def run_scale(n, queries, repeats, seed, tmp):
    path = Path(tmp) / f"city-{n}.db"
    t0 = time.perf_counter()
    pl, boxes = city.payload(n, seed=seed)
    c = city.database(str(path), pl)
    setup_s = time.perf_counter() - t0
    ts = city.tasks(queries, boxes, seed=seed + 1)

    c.execute("BEGIN")
    p0 = io.pin(c, "R0", ts[0]["window"])
    t = time.perf_counter_ns()
    doc = io.export_json(c, "R0", p0)
    export_ms = ms(time.perf_counter_ns() - t)
    c.execute("COMMIT")
    jpath = Path(tmp) / f"R0-{n}.json"
    jpath.write_bytes(doc)

    rows, checks = [], {"input_mismatch": 0, "lazy_vs_graph_mismatch": 0, "dijkstra_cost_mismatch": 0,
                        "trace_segments_missing": 0}
    for k, task in enumerate(ts):
        win, start, goal = task["window"], task["start"], task["goal"]
        domain = io.domain_for(start, goal)
        rec = {"task": k, "window": list(win), "start": list(start), "goal": list(goal), "domain": domain}

        def pinned(fn):
            c.execute("BEGIN")
            try:
                p = io.pin(c, "R0", win)
                return p, fn(p)
            finally:
                c.execute("COMMIT")

        stage, inputs = {}, {}
        # JSON whole-release export
        stage["json_snapshot"] = {}
        stage["json_snapshot"]["io_ms"], raw = timed(lambda: jpath.read_bytes(), repeats)
        stage["json_snapshot"]["pin_ms"], p = timed(lambda: pinned(lambda p: None)[0], repeats)
        stage["json_snapshot"]["load_ms"], built = timed(
            lambda: io.planner_input(p, io.objects_from_json(json.loads(raw)), domain, win, start, goal), repeats)
        inputs["json_snapshot"] = built
        # SQL full read and R*Tree prefilter
        for mode in ("sql_full", "sql_rtree"):
            stage[mode] = {}
            stage[mode]["pin_ms"], p = timed(lambda: pinned(lambda p: None)[0], repeats)
            stage[mode]["db_ms"], raw_rows = timed(lambda: pinned(lambda p: io.fetch_sql(c, p, domain, win, mode))[1],
                                                   repeats)
            stage[mode]["db_ms"] -= stage[mode]["pin_ms"]
            stage[mode]["load_ms"], built = timed(
                lambda: io.planner_input(p, io.objects_from_rows(raw_rows), domain, win, start, goal), repeats)
            stage[mode]["rows_returned"] = sum(len(v) for v in raw_rows.values())
            inputs[mode] = built
        digests = {m: io.input_digest(inputs[m][0]) for m in inputs}
        if len(set(digests.values())) != 1:
            checks["input_mismatch"] += 1
        s, q, zone_rid = inputs["sql_rtree"]
        rec["objects_in_domain"] = {"buildings": len(s["scene"]["obstacles"]),
                                    "restrictions": len(s["airspace"]["restrictions"]),
                                    "zones": len(s["risk_data"]["zones"])}
        # one lazy v1 search serves all three non-cached paths (identical input)
        t = time.perf_counter_ns()
        lazy = io.lazy_plan(s, q)
        search_ms = ms(time.perf_counter_ns() - t)
        # materialised graph
        t = time.perf_counter_ns()
        g = io.build_graph(s, q)
        build_ms = ms(time.perf_counter_ns() - t)
        gs_ms, gres = timed(lambda: io.search_graph(g, q, "astar"), repeats)
        gd_ms, dres = timed(lambda: io.search_graph(g, q, "dijkstra"), repeats)
        if not io.same_result(lazy, gres):
            checks["lazy_vs_graph_mismatch"] += 1
        if gres["status"] != dres["status"] or (gres["status"] == "feasible" and abs(gres["cost"] - dres["cost"]) > 1e-9):
            checks["dijkstra_cost_mismatch"] += 1
        # record through the ZC tables and trace with operation C
        p = pinned(lambda p: None)[0]
        qid = io.record_query(c, p, "DISPATCH", win, start, goal, lazy, "sql_rtree", zone_rid)
        if lazy["status"] == "feasible":
            traced = {r["segment_no"] for r in io.trace(c, qid)}
            if traced != set(range(1, len(lazy["path"]))):
                checks["trace_segments_missing"] += 1
        rec.update(stages=stage, input_digest=digests["sql_rtree"], status=lazy["status"],
                   cost=lazy.get("cost"), expanded_astar=lazy["expanded"], edge_checks_lazy=lazy["edge_checks"],
                   search_ms=search_ms, graph={"nodes": g["nodes"], "edges": g["edges"], "build_ms": build_ms,
                                               "astar_ms": gs_ms, "dijkstra_ms": gd_ms,
                                               "expanded_astar": gres["expanded"],
                                               "expanded_dijkstra": dres["expanded"]})
        rows.append(rec)

    # unfiltered v1 input equals filtered input in results (relevance filter is safe)
    filter_check = None
    if n <= 500:
        mism = 0
        for task in ts[:4]:
            c.execute("BEGIN")
            p = io.pin(c, "R0", task["window"])
            objs = io.objects_from_rows(io.fetch_sql(c, p, io.domain_for(task["start"], task["goal"]),
                                                     task["window"], "sql_full"))
            c.execute("COMMIT")
            dom = io.domain_for(task["start"], task["goal"])
            s_f, q_f, _ = io.planner_input(p, objs, dom, task["window"], task["start"], task["goal"])
            s_all = json.loads(json.dumps(s_f))
            s_all["scene"]["obstacles"] = [{"id": o["id"], "box": o["box"]} for o in objs if o["kind"] == "building"]
            s_all["airspace"]["restrictions"] = [
                {"id": o["id"], "box": o["box"], "kind": o["kind"], "state": o["state"], "valid": o["valid"],
                 "ceiling_m": o["ceiling_m"] if o["ceiling_m"] is not None else float("inf")}
                for o in objs if o["kind"] in ("no_fly", "height_limit")]
            s_all["risk_data"]["zones"] = [{"id": o["id"], "box": o["box"], "q": o["q"]} for o in objs if o["kind"] == "zone"]
            if not io.same_result(io.lazy_plan(s_f, q_f), io.lazy_plan(s_all, q_f)):
                mism += 1
        filter_check = {"tasks": 4, "unfiltered_vs_filtered_mismatch": mism}

    # cache hit through the full service path
    cache, hit = {}, []
    for task in ts:
        io.plan_route(c, "R0", task["window"], task["start"], task["goal"], "graph_cache", cache=cache)
        r, _, _, tm, gid = io.plan_route(c, "R0", task["window"], task["start"], task["goal"], "graph_cache", cache=cache)
        hit.append(sum(tm.values()))
    c.close()
    db_bytes = path.stat().st_size + (Path(str(path) + "-wal").stat().st_size if Path(str(path) + "-wal").exists() else 0)
    return {"n_buildings": n, "queries": queries, "setup_seconds": round(setup_s, 2), "db_bytes": db_bytes,
            "json_export_bytes": len(doc), "json_export_ms": export_ms, "checks": checks,
            "filter_equivalence": filter_check, "cache_hit_total_ms": hit, "tasks": rows}


def summarize(scale):
    t = scale["tasks"]
    med = lambda xs: round(statistics.median(xs), 3)  # noqa: E731
    out = {}
    for mode in ("json_snapshot", "sql_full", "sql_rtree"):
        st = [r["stages"][mode] for r in t]
        data = med([s.get("io_ms", 0) + s["pin_ms"] + s.get("db_ms", 0) + s["load_ms"] for s in st])
        out[mode] = {"data_ms": data, "io_ms": med([s.get("io_ms", 0) for s in st]),
                     "db_ms": med([s.get("db_ms", 0) for s in st]), "load_ms": med([s["load_ms"] for s in st]),
                     "search_ms": med([r["search_ms"] for r in t]),
                     "total_ms": med([s.get("io_ms", 0) + s["pin_ms"] + s.get("db_ms", 0) + s["load_ms"] + r["search_ms"]
                                      for s, r in zip(st, t)])}
        if mode != "json_snapshot":
            out[mode]["rows_returned"] = med([s["rows_returned"] for s in st])
    out["graph_cache"] = {"miss_build_ms": med([r["graph"]["build_ms"] for r in t]),
                          "astar_on_graph_ms": med([r["graph"]["astar_ms"] for r in t]),
                          "dijkstra_on_graph_ms": med([r["graph"]["dijkstra_ms"] for r in t]),
                          "hit_total_ms": med(scale["cache_hit_total_ms"]),
                          "nodes": med([r["graph"]["nodes"] for r in t]), "edges": med([r["graph"]["edges"] for r in t])}
    out["search"] = {"expanded_astar": med([r["expanded_astar"] for r in t]),
                     "expanded_dijkstra": med([r["graph"]["expanded_dijkstra"] for r in t]),
                     "edge_checks_lazy": med([r["edge_checks_lazy"] for r in t]),
                     "objects_in_domain": med([sum(r["objects_in_domain"].values()) for r in t]),
                     "statuses": {s: sum(1 for r in t if r["status"] == s) for s in ("feasible", "infeasible", "unknown")}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--output", default=str(HERE / "results" / "access_paths.json"))
    ap.add_argument("--seed", type=int, default=20261107)
    args = ap.parse_args()
    sizes = (200, 1000) if args.quick else (200, 2400, 10000)
    queries, repeats = (4, 2) if args.quick else (12, 3)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    scales = []
    with tempfile.TemporaryDirectory(prefix="zc-access-") as tmp:
        for n in sizes:
            t = time.perf_counter()
            s = run_scale(n, queries, repeats, args.seed, tmp)
            s["summary"] = summarize(s)
            scales.append(s)
            print(f"N={n} done in {time.perf_counter() - t:.1f}s checks={s['checks']}", file=sys.stderr)
    files = [HERE / f for f in ("access_paths.py", "planner_io.py", "city.py")] + [
        io.ROOT / "docs/v2/schema/schema.sql", io.ROOT / "docs/v2/schema/op_c.sql",
        io.ROOT / "docs/modules/zc/prototype/planner.py", io.ROOT / "docs/modules/zqo/v2/experiments/catalog.py",
        io.ROOT / "docs/modules/lq/v2/experiments/governance.py"]
    out = {
        "experiment": "zc_v2_access_paths", "started_at": started, "synthetic": True,
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                        "platform": platform.platform(), "machine": platform.machine(),
                        "database": "file SQLite in WAL mode, published through catalog.publish",
                        "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=io.ROOT, text=True,
                                                   capture_output=True).stdout.strip()},
        "parameters": {"seed": args.seed, "queries_per_scale": queries, "repeats": repeats,
                       "planner_config": io.CONFIG, "risk_model": io.RISK_MODEL,
                       "domain": "task bbox + 40 m, z 20-120 m, 20 m grid", "area_m": city.AREA,
                       "restrictions": 100, "exposure_zones": 100, "task_window_min": 10},
        "source_sha256": {str(f.relative_to(io.ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        "scales": scales,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    for s in scales:
        print(json.dumps({"n": s["n_buildings"], **s["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
