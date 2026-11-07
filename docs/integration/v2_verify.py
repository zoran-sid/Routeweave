"""v2 integration verification: rerun every member's tests, experiments and review scripts.

Outputs of experiments go to a temporary directory so delivered results are not overwritten.
The evidence file records each command, exit code, a log tail, environment and source digests.

python3 -B docs/integration/v2_verify.py --output docs/final/evidence/verification-v2.json
"""
import argparse
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def commands(tmp):
    py = [sys.executable, "-B"]
    out = lambda name: str(Path(tmp) / name)  # noqa: E731
    return [
        ("schema", "unified schema (all members' table groups)", py + ["-m", "unittest", "discover", "-s", "docs/v2/schema", "-v"], 0),
        ("zqo_v2_tests", "ZQO transactions", py + ["-m", "unittest", "discover", "-s", "docs/modules/zqo/v2/experiments", "-v"], 0),
        ("lq_v2_tests", "LQ governance", py + ["-m", "unittest", "discover", "-s", "docs/modules/lq/v2/experiments", "-v"], 0),
        ("zc_v2_tests", "ZC query tables and cache", py + ["-m", "unittest", "discover", "-s", "docs/modules/zc/v2/experiments", "-v"], 0),
        ("yht_op_a", "YHT operation A access paths (quick grid)", py + ["docs/modules/yht/v2/experiments/op_a_index_comparison.py", "--quick", "--output", out("op_a.json")], 0),
        ("zqo_run", "ZQO publish/rollback/storage (10 releases)", py + ["docs/modules/zqo/v2/experiments/run.py", "--counts", "10", "--output", out("zqo.json")], 0),
        ("lq_run", "LQ governance, operation C, invalidation", py + ["docs/modules/lq/v2/experiments/run.py", "--output", out("lq.json")], 0),
        ("zc_access", "ZC access paths (quick grid)", py + ["docs/modules/zc/v2/experiments/access_paths.py", "--quick", "--output", out("access.json")], 0),
        ("zc_invalidation", "ZC cache invalidation (6 graphs, Kowloon area M)", py + ["docs/modules/zc/v2/experiments/invalidation.py", "--graphs", "6", "--area", "M", "--output", out("inval.json")], 0),
        ("lj_recovery", "LJ backup, restore checks and truncation detection", py + ["docs/modules/lj/v2/experiments/recovery.py", "--output", out("recovery.json")], 0),
        ("zc_review_lq", "ZC probes of LQ (12/12 after LQ-V2-02 fix)", py + ["docs/modules/zc/v2/experiments/review_lq.py", "--output", out("review_lq.json")], 0),
        ("lq_review_zqo", "LQ probe of ZQO-V2-01 (fixed: both invalid inputs rejected)", py + ["docs/modules/lq/v2/experiments/review_zqo.py", "--output", out("review_zqo.json")], 0),
        *[(f"v1_{m}", f"v1 {m.upper()} module tests", py + ["-m", "unittest", "discover", "-s", f"docs/modules/{m}/prototype"], 0)
          for m in ("yht", "lq", "zc", "zqo", "lj")],
        ("v1_audit", "v1 issue audit", py + ["docs/integration/audit.py", "--output", out("audit.json")], 0),
        ("v1_five_module", "v1 five-module chain", py + ["docs/integration/five_module.py", "--output", out("five.json")], 0),
        ("v1_risk_review", "v1 risk review", py + ["docs/modules/lq/prototype/review_integration.py", "--output", out("risk.json")], 0),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    runs, started = [], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with tempfile.TemporaryDirectory(prefix="skyroute-v2-verify-") as tmp:
        for key, label, cmd, expected in commands(tmp):
            t = time.perf_counter()
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log = (p.stdout + p.stderr).strip()
            tests = re.findall(r"Ran (\d+) tests?", log)
            runs.append({"key": key, "label": label, "command": " ".join(["python3"] + cmd[1:]),
                         "exit_code": p.returncode, "expected_exit": expected, "pass": p.returncode == expected,
                         "tests_ran": int(tests[-1]) if tests else None, "seconds": round(time.perf_counter() - t, 2),
                         "log_tail": log.splitlines()[-6:]})
            print(("PASS " if p.returncode == expected else "FAIL ") + key, file=sys.stderr)
    sources = sorted(p for p in ROOT.glob("docs/**/*") if p.suffix in (".py", ".sql") and "__pycache__" not in p.parts)
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    out = {"verification": "SkyRoute v2 integration", "started_at": started,
           "git_head": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
           "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                           "platform": platform.platform()},
           "summary": {"commands": len(runs), "passed": sum(r["pass"] for r in runs),
                       "tests_ran": sum(r["tests_ran"] or 0 for r in runs)},
           "runs": runs,
           "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["summary"]), file=sys.stderr)
    sys.exit(0 if out["summary"]["passed"] == out["summary"]["commands"] else 1)


if __name__ == "__main__":
    main()
