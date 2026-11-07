"""ZC leg 4, step 1: independent review of LQ's governance leg.

Each probe states what LQ claims, runs the claim against the real schema/service,
and records expected vs actual. Failures are findings for LQ, not fixes by ZC.

python3 -B docs/modules/zc/v2/experiments/review_lq.py --output /tmp/zc-lq-review.json
"""
import argparse
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planner_io as io  # noqa: E402
import governance as gov  # noqa: E402

cat = io.cat


def probe(results, name, claim, fn, expect):
    try:
        actual = fn()
        outcome = "accepted"
    except (sqlite3.DatabaseError, PermissionError, ValueError) as e:
        actual, outcome = str(e), "rejected"
    results.append({"probe": name, "claim": claim, "expected": expect, "actual": outcome, "detail": actual,
                    "pass": outcome == expect})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(HERE / "results" / "lq-review.json"))
    args = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix="zc-lq-review-") as tmp:
        path = str(Path(tmp) / "lq.db")
        cat.initialize(path)
        c = cat.connect(path)
        gov.seed(c)
        pl = cat.fixture()
        gov.request_release(c, pl, "R0", None, "AUTHOR", "req-R0")
        gov.approve(c, "req-R0", "REVIEWER")
        gov.publish_approved(c, pl, "R0", None, "req-R0", "REVIEWER")
        gov.compile_dataset(c, "R0", "D0")

        # LQ-V2-01: model identity is immutable once approved/referenced.
        probe(results, "model_formula_update", "LQ-V2-01: approved/referenced risk_model cannot change in place",
              lambda: c.execute("UPDATE risk_model SET params='{\"hard_q\":0.5}' WHERE risk_model_id='lq-risk-v1'"),
              "rejected")
        probe(results, "model_delete", "LQ-V2-01: referenced risk_model cannot be deleted",
              lambda: c.execute("DELETE FROM risk_model WHERE risk_model_id='lq-risk-v1'"), "rejected")
        probe(results, "sealed_derived_update", "validated derived_risk is append-only",
              lambda: c.execute("UPDATE derived_risk SET q_max=0 WHERE dataset_id='D0'"), "rejected")
        probe(results, "sealed_dataset_reopen", "validated risk_dataset cannot return to draft",
              lambda: c.execute("UPDATE risk_dataset SET state='draft' WHERE dataset_id='D0'"), "rejected")
        probe(results, "self_approval", "author cannot approve own request",
              lambda: (gov.request_release(c, cat.changed(pl), "R1", "R0", "AUTHOR", "req-self"),
                       gov.approve(c, "req-self", "AUTHOR")), "rejected")
        probe(results, "gap_seal", "a dataset with a temporal gap cannot be sealed",
              lambda: (gov.compile_dataset(c, "R0", "GAP", {"G-0": [{"valid": [cat.WIN[0], "2026-06-01T00:00:00Z"],
                                                                    "E": .5, "C": .4}]}, seal=False),
                       c.execute("UPDATE risk_dataset SET state='validated' WHERE dataset_id='GAP'")), "rejected")

        # Restricted reads: fixed endpoint vs. the reader connection's authorizer on its own.
        probe(results, "endpoint_raw_table", "fixed endpoint denies raw exposure_zone",
              lambda: gov.read_audited(path, "DISPATCH", "SELECT * FROM exposure_zone"), "rejected")
        probe(results, "endpoint_helper_view", "fixed endpoint denies the internal resolved_feature view",
              lambda: gov.read_audited(path, "DISPATCH", "SELECT * FROM resolved_feature"), "rejected")
        probe(results, "authorizer_raw_table", "reader() authorizer alone denies raw exposure_zone",
              lambda: gov.reader(path, "DISPATCH").execute("SELECT * FROM exposure_zone").fetchall(), "rejected")

        def helper_view_via_authorizer():
            r = gov.reader(path, "DISPATCH")
            rows = r.execute("SELECT feature_id, layer, sensitivity FROM resolved_feature "
                             "WHERE sensitivity='restricted'").fetchall()
            r.close()
            return {"rows": len(rows), "layers": sorted({x[1] for x in rows})}
        probe(results, "authorizer_helper_view",
              "reader() authorizer alone confines a dispatcher to the two restricted views", helper_view_via_authorizer,
              "rejected")
        detail_rows = len(gov.read_audited(path, "DISPATCH", "SELECT * FROM v_exposure_detail"))
        results.append({"probe": "dispatcher_detail_rows", "claim": "dispatcher sees no exposure detail",
                        "expected": 0, "actual": detail_rows, "pass": detail_rows == 0})

        # Operation C window contract: LQ's TEMP fixture SQL vs. a real 10-minute task window.
        task = ("2026-11-05T08:05:00Z", "2026-11-05T08:15:00Z")
        c.execute("BEGIN")
        p = io.pin(c, "R0", task)
        c.execute("COMMIT")
        zones = cat.rows(c, "SELECT f.rid, f.feature_id FROM feature f WHERE f.release_id=? AND f.layer='exposure' "
                            "ORDER BY f.feature_id", (p["owners"]["exposure"][1],))
        result = {"status": "feasible", "reason": "fixture", "length_m": 20.0, "time_s": 2.0, "risk_proxy": 0.04,
                  "cost": 0.24, "path": [[0, 0, 100], [20, 0, 100], [40, 0, 100]],
                  "segment_sources": [[zones[0]["feature_id"]], [zones[0]["feature_id"]]]}
        qid = io.record_query(c, p, "DISPATCH", task, (0, 0, 100), (40, 0, 100), result, "sql_rtree",
                              {z["feature_id"]: z["rid"] for z in zones})
        zc_rows = io.trace(c, qid)
        lq_sql = (io.ROOT / "docs/modules/lq/v2/experiments/op_c.sql").read_text()
        lq_rows = cat.rows(c, lq_sql, {"query_id": qid})
        results.append({"probe": "op_c_task_window", "claim": "LQ op_c.sql traces a route planned for a task window",
                        "expected": len(zc_rows), "actual": len(lq_rows), "pass": len(lq_rows) == len(zc_rows),
                        "detail": {"task_window": task, "dataset_window": list(cat.WIN),
                                   "zc_op_c_rows": len(zc_rows), "lq_op_c_rows": len(lq_rows),
                                   "cause": "LQ requires q.window == dataset window; tasks are sub-windows"}})
        integrity = {"check": c.execute("PRAGMA integrity_check").fetchone()[0],
                     "foreign_key_violations": len(c.execute("PRAGMA foreign_key_check").fetchall())}
        c.close()
    out = {"review": "ZC leg 4 review of LQ leg 3", "synthetic": True,
           "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                           "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=io.ROOT, text=True,
                                                      capture_output=True).stdout.strip()},
           "probes": results, "passed": sum(r["pass"] for r in results), "total": len(results),
           "integrity": integrity}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in results:
        print(("PASS " if r["pass"] else "FAIL ") + r["probe"] + ": expected " + str(r["expected"]) +
              ", actual " + str(r["actual"]))


if __name__ == "__main__":
    main()
