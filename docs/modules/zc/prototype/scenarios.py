"""Deterministic, explicitly synthetic fixtures and version bindings."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path


def bind(s, q):
    # Content-derived mock versions prevent edits from silently retaining an ID.
    for key in ("scene", "airspace", "risk_data", "risk_model", "planner_config"):
        payload = {k: v for k, v in s[key].items() if k != "version"}
        digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
        s[key]["version"] = "mock-zc-" + key + "-" + digest
    s["versions"] = {k: s[k]["version"] for k in
                     ("scene", "airspace", "risk_data", "risk_model", "planner_config")}
    q["versions"] = dict(s["versions"])
    return s, q


def fixture():
    data = json.loads((Path(__file__).with_name("scenario.json")).read_text())
    return deepcopy(data["snapshot"]), deepcopy(data["query"])


def restriction(kind="no_fly", box=None, start="2026-11-04T00:00:00Z", end="2026-11-04T00:10:00Z"):
    return {"id": "NF-1", "kind": kind, "box": box or [[45, 0, 0], [55, 100, 100]],
            "valid": [start, end], "state": "published", "source": "synthetic-zc-v1", "ceiling_m": 30}


def cases():
    out = []
    for name in ("open", "building", "risk_0", "risk_2", "risk_8", "risk_hard", "no_fly", "expired", "ceiling", "missing", "mixed", "unknown_wall"):
        s, q = fixture()
        q["id"] = "zc-" + name
        if name == "open":
            s["scene"]["obstacles"] = []
            s["risk_data"]["zones"] = []
        if name == "building":
            s["risk_data"]["zones"] = []
        if name.startswith("risk_") and name != "risk_hard":
            s["planner_config"]["lambda_risk"] = float(name.split("_")[1])
        if name == "risk_hard":
            s["risk_data"]["zones"][0]["q"] = .95
        if name in ("no_fly", "expired", "ceiling"):
            r = restriction()
            if name == "expired":
                r["valid"] = ["2026-11-03T23:50:00Z", "2026-11-04T00:00:00Z"]
            if name == "ceiling":
                r = restriction("height_limit", [[0, 0, 0], [100, 100, 100]])
            s["airspace"]["restrictions"] = [r]
        if name == "missing":
            s["risk_data"]["complete"] = False
        if name == "unknown_wall":
            s["risk_data"]["zones"] = [{"id": "unknown-strip", "box": [[45, 0, 0], [55, 100, 100]], "q": None}]
        bind(s, q)
        if name == "mixed":
            s["airspace"]["version"] = "mock-wrong-airspace"
        out.append((name, s, q))
    return out
