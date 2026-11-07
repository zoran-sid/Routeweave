"""SQLite backup, fault injection, and restore verification on real Hong Kong data.

Two releases of Kowloon area S (docs/v2/data/hk): every building, terrain post, census/school/hospital exposure
zone of the Mong Kok core, plus one scenario no-fly restriction per release placed over a real street.

Run from the repository root:
    python -X utf8 -B docs/modules/lj/v2/experiments/recovery.py \
        --output docs/modules/lj/v2/experiments/results/recovery.json
"""
import argparse
import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCHEMA = ROOT / "docs" / "v2" / "schema"
import sys

sys.path.insert(0, str(SCHEMA))
import fixtures as fx  # noqa: E402

sys.path.insert(0, str(ROOT / "docs" / "v2" / "data" / "hk"))
import hk  # noqa: E402

SCENARIO = [{"id": "NF-001", "box": (835380.0, 819980.0, 835460.0, 820060.0),
             "effective": ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z")},
            {"id": "NF-002", "box": (835460.0, 820060.0, 835540.0, 820140.0),
             "effective": ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z")}]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def make_database(path):
    conn = fx.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    fx.base(conn)
    hk.add_sources(conn)
    fx.create_release(conn, "R0")
    fx.add_layers(conn, "R0")
    _, stats, rid = hk.build(conn, "S", "R0", extra_air=SCENARIO[:1])
    fx.publish(conn, "R0", "2026-11-05T00:05:00Z")
    fx.create_release(conn, "R1", base_release_id="R0")
    fx.add_layers(conn, "R1")
    hk.build(conn, "S", "R1", extra_air=SCENARIO, first_rid=rid)
    fx.publish(conn, "R1", "2026-11-05T00:10:00Z")
    conn.execute("CREATE TEMP TABLE _stats(v TEXT)")
    conn.execute("INSERT INTO _stats VALUES (?)", (json.dumps(stats),))
    conn.commit()
    return conn


def historical_query(conn, release_id):
    rows = conn.execute(
        "SELECT f.feature_id, a.restriction_id, a.kind, a.effective_lo, "
        "a.effective_hi, a.state FROM feature f JOIN airspace_restriction a "
        "USING (rid) WHERE f.release_id=? AND a.effective_lo < ? "
        "AND a.effective_hi > ? ORDER BY a.restriction_id",
        (release_id, "2026-11-05T08:30:00Z", "2026-11-05T08:00:00Z"),
    ).fetchall()
    return [dict(zip(("feature_id", "restriction_id", "kind", "effective_lo",
                      "effective_hi", "state"), row)) for row in rows]


def checks(conn):
    return {
        "integrity_check": conn.execute("PRAGMA integrity_check").fetchone()[0],
        "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
    }


def chain_check(conn):
    rows = conn.execute(
        "SELECT child.release_id, child.base_release_id, child.content_hash, "
        "parent.content_hash FROM release child JOIN release parent "
        "ON parent.release_id=child.base_release_id WHERE child.release_id='R1'"
    ).fetchall()
    return bool(rows) and rows[0][1] == "R0" and len(rows[0][2]) == 64 and len(rows[0][3]) == 64


def backup(source_path, target_path):
    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(target_path))
    started = time.perf_counter_ns()
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    return (time.perf_counter_ns() - started) / 1e6


def verify_restore(path, expected_rows, expected_digest):
    conn = sqlite3.connect(str(path))
    try:
        result = {
            **checks(conn),
            "release_chain": chain_check(conn),
            "history_rows_equal": historical_query(conn, "R0") == expected_rows,
            "history_digest_equal": digest(historical_query(conn, "R0")) == expected_digest,
        }
    finally:
        conn.close()
    result["passed"] = (
        result["integrity_check"] == "ok"
        and result["foreign_key_violations"] == 0
        and result["release_chain"]
        and result["history_rows_equal"]
        and result["history_digest_equal"]
    )
    return result


def verify_truncation(path):
    corrupted = path.with_name("corrupted.db")
    data = path.read_bytes()
    corrupted.write_bytes(data[: max(512, len(data) // 2)])
    result = {"detected": False, "error": None}
    try:
        conn = sqlite3.connect(str(corrupted))
        try:
            result["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
            result["detected"] = result["integrity_check"] != "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        result["detected"] = True
        result["error"] = str(exc)
    finally:
        corrupted.unlink(missing_ok=True)
    result["passed"] = result["detected"]
    return result


def run():
    with tempfile.TemporaryDirectory(prefix="lj-recovery-") as tmp:
        root = Path(tmp)
        source_path = root / "source.db"
        backup_path = root / "backup.db"
        conn = make_database(source_path)
        expected = historical_query(conn, "R0")
        expected_hash = digest(expected)
        source_checks = checks(conn)
        data_stats = json.loads(conn.execute("SELECT v FROM _stats").fetchone()[0])
        conn.close()
        backup_ms = backup(source_path, backup_path)
        restore = verify_restore(backup_path, expected, expected_hash)
        truncation = verify_truncation(backup_path)
        return {
            "synthetic": False,
            "data": "Hong Kong open data, Kowloon area S (docs/v2/data/hk/manifest.json); NF-001/NF-002 are scenario rows",
            "data_stats": data_stats,
            "operation": "SQLite Connection.backup",
            "source_checks": source_checks,
            "historical_query": {
                "release_id": "R0",
                "rows": expected,
                "digest": expected_hash,
            },
            "backup": {"elapsed_ms": round(backup_ms, 3), "restore": restore},
            "fault_injection": {"truncated_backup": truncation},
            "passed": restore["passed"] and truncation["passed"],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = run()
    tracked = [
        Path(__file__),
        SCHEMA / "schema.sql",
        SCHEMA / "fixtures.py",
    ]
    evidence["environment"] = {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in tracked
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "backup_ms": evidence["backup"]["elapsed_ms"]}))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
