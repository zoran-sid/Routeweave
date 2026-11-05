"""Export YHT exposure polygons as LQ profiles and run LQ's adapter.

YHT owns geometry and provenance; LQ owns E, C and the whole-window maximum.
The adapter keeps the mapping explicit: a zone's q must equal E*C, and the
profile period is exactly the YHT release validity. The output is a check, not
a claim that the synthetic numbers are real risk probabilities.
"""
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LQ = REPO / "docs" / "modules" / "lq" / "prototype"
sys.path.insert(0, str(LQ))

import export_zc  # noqa: E402
import yht_model  # noqa: E402


def _unit_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and 0.0 <= value <= 1.0)


def profiles_from_scene(s, z_top=120.0):
    export_zc.require_exportable(s)
    profiles = []
    for zone in s["ground_zones"]:
        e, c, q = zone.get("exposure_e"), zone.get("consequence_c"), zone.get("q")
        if not (_unit_number(e) and _unit_number(c) and _unit_number(q)):
            raise ValueError("unknown_or_invalid_exposure:" + zone.get("id", "?"))
        if abs(q - e * c) > 1e-9:
            raise ValueError("inconsistent_exposure:" + zone.get("id", "?"))
        xs = [p[0] for p in zone["polygon"]]
        ys = [p[1] for p in zone["polygon"]]
        profiles.append({
            "id": zone["id"],
            "box": [[min(xs), min(ys), 0.0], [max(xs), max(ys), z_top]],
            "source": zone["source_id"],
            "periods": [{
                "valid": list(s["valid"]),
                "E": e,
                "C": c,
            }],
        })
    return profiles


def write_export(output, repo_root=REPO):
    s = yht_model.seal(yht_model.scene())
    window = {"start": "2026-11-05T08:05:00Z", "end": "2026-11-05T08:15:00Z"}
    search_bounds = [[0.0, 0.0, 10.0], [450.0, 450.0, 120.0]]
    start, goal = [20.0, 20.0, 70.0], [420.0, 420.0, 70.0]

    snapshot, query = export_zc.export_snapshot(
        s, window, search_bounds, start, goal, query_id="yht-lq-1")
    profiles = profiles_from_scene(s)
    from risk import compile_profiles  # LQ module, imported after sys.path setup
    from planner import preflight, plan, assess_segment

    report = {"profiles": len(profiles), "adapter": "LQ compile_profiles"}
    try:
        bound, q = compile_profiles(snapshot, query, profiles)
        report["lq_versions"] = dict(bound["versions"])
        report["preflight"] = preflight(bound, q)
        report["plan"] = plan(bound, q, "astar")
        report["q2_assess"] = assess_segment(bound, q, start, goal)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
        report["error"] = "lq_invalid_input:" + str(exc)

    payload = {
        "schema": "yht-lq-export-0.1",
        "window": window,
        "search_bounds": search_bounds,
        "query": query,
        "source_release": {"versions": dict(s["versions"]),
                           "manifest": deepcopy(s["manifest"])},
        "profiles": profiles,
        "report": report,
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                       sort_keys=True) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    payload = write_export(HERE.parent / "results" / "lq-export.json")
    print(json.dumps({
        "profiles": payload["report"].get("profiles", 0),
        "preflight": payload["report"].get("preflight"),
        "status": payload["report"].get("plan", {}).get("status"),
        "distance_m": payload["report"].get("plan", {}).get("metrics", {}).get("distance_m"),
        "risk_proxy": payload["report"].get("plan", {}).get("metrics", {}).get("risk_proxy"),
    }, ensure_ascii=False))
