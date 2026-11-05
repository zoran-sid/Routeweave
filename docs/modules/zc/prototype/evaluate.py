"""Regenerate local evidence: python3 docs/modules/zc/prototype/evaluate.py."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

from planner import assess_segment, plan
from scenarios import bind, cases, fixture, restriction

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results"
REPEATS = 7


def main():
    OUT.mkdir(exist_ok=True)
    rows, examples = [], {}
    for name, s, q in cases():
        for algo in ("dijkstra", "astar"):
            plan(s, q, algo)  # One unmeasured warm-up; no shared search cache.
        samples = {a: [] for a in ("dijkstra", "astar")}
        for i in range(REPEATS):
            for algo in (("dijkstra", "astar") if i % 2 == 0 else ("astar", "dijkstra")):
                samples[algo].append(plan(s, q, algo))
        for algo, runs in samples.items():
            r = runs[-1]
            assert len({(x["status"], x["expanded"], json.dumps(x["metrics"], sort_keys=True)) for x in runs}) == 1
            ms = [x["elapsed_ms"] for x in runs]
            rows.append({"case": name, "algorithm": algo, "status": r["status"], "reason": r["reason"],
                         "expanded": r["expanded"], "edge_checks": r["edge_checks"],
                         "lambda_risk": s["planner_config"]["lambda_risk"],
                         "metrics": r["metrics"], "versions": r["versions"], "path": r["path"],
                         "elapsed_ms_samples": ms, "median_ms": statistics.median(ms),
                         "p95_ms": sorted(ms)[math.ceil(.95 * len(ms)) - 1]})
            if algo == "astar" and name in ("building", "risk_0", "risk_8", "no_fly", "missing"):
                examples[name] = {"snapshot": s, "query": q, "result": r}
        a, d = samples["astar"][-1], samples["dijkstra"][-1]
        assert a["status"] == d["status"]
        if a["status"] == "feasible":
            assert abs(a["metrics"]["cost"] - d["metrics"]["cost"]) < 1e-9
    s, q = fixture()
    before = plan(s, q)
    s["airspace"]["restrictions"] = [restriction(box=[[45, 35, 0], [55, 65, 100]])]
    bind(s, q)
    t = perf_counter()
    rechecked = [assess_segment(s, q, a, b) for a, b in zip(before["path"], before["path"][1:])]
    recheck_ms = (perf_counter() - t) * 1000
    after = plan(s, q)
    assert any(e["state"] == "forbidden" for e in rechecked) and after["status"] == "feasible"
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "prototype").glob("*")) if p.is_file()}
    report = {"executed_at_utc": datetime.now(timezone.utc).isoformat(), "fixture": "zc-synthetic-v1",
              "python": sys.version.split()[0], "os": platform.system(), "machine": platform.machine(),
              "grid_nodes_before_filtering": 847, "repeat_count": REPEATS, "source_sha256": hashes,
              "timing_scope": "deepcopy + validation + search + route recheck, in-memory only; no database/network",
              "rows": rows}
    (OUT / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "query-examples.json").write_text(json.dumps(examples, indent=2) + "\n")
    (OUT / "update-example.json").write_text(json.dumps({"new_snapshot": s, "new_query": q,
        "before": before, "recheck": rechecked, "recheck_ms": recheck_ms, "after": after}, indent=2) + "\n")
    fields = ["case", "algorithm", "status", "length_m", "time_s", "risk_proxy", "cost", "expanded", "edge_checks", "median_ms", "p95_ms"]
    with (OUT / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: (r.get(k, (r["metrics"] or {}).get(k))) for k in fields})
    print("case         algorithm  status      length_m  risk       expanded  median_ms")
    for r in rows:
        m = r["metrics"] or {"length_m": 0, "risk_proxy": 0}
        print(f'{r["case"]:12} {r["algorithm"]:10} {r["status"]:11} {m["length_m"]:8.3f} {m["risk_proxy"]:8.4f} {r["expanded"]:9} {r["median_ms"]:9.3f}')
    print("Updated route:", before["metrics"], "=>", after["metrics"])


if __name__ == "__main__":
    main()
