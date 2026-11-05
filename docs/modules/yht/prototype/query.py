"""YHT query services: Q1 corridor clearance and Q2 segment/area status.

The functions accept an optional candidate list so a storage backend can supply
index-filtered buildings. Semantics are identical across backends; only the
candidate set changes. Unfiltered calls are the brute-force baseline.
"""
from datetime import datetime, timezone
from math import isfinite

from yht_model import (
    coverage_for_bbox, segment_above_ceiling, segment_box_distance,
    segment_hits_building, segment_hits_volume, segment_polygon_distance_2d,
    segment_polygon_intervals, verify_release, VERSION_KEYS,
)

EPS = 1e-9


def parse_instant(text):
    if not isinstance(text, str):
        raise ValueError("time must be an ISO 8601 string")
    value = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("time must carry a timezone: " + text)
    return parsed


def window_of(window):
    if not isinstance(window, dict) or "start" not in window or "end" not in window:
        raise ValueError("window must be {start, end}")
    start, end = parse_instant(window["start"]), parse_instant(window["end"])
    if start.astimezone(timezone.utc) >= end.astimezone(timezone.utc):
        raise ValueError("window start must be before end")
    return (_utc(window["start"]), _utc(window["end"]))


def _utc(text):
    parsed = parse_instant(text).astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_window(window):
    start, end = window_of(window)
    return {"start": start, "end": end}


def overlaps(valid, window):
    return valid[0] < window["end"] and valid[1] > window["start"]


def in_bounds(s, p):
    lo, hi = s["bounds"]
    return (all(isfinite(v) for v in p)
            and all(lo[i] - 1e-9 <= p[i] <= hi[i] + 1e-9 for i in range(3)))


def preflight(s, window, a, b, versions, verify=True):
    reasons = []
    if not isinstance(versions, dict) or any(k not in versions for k in VERSION_KEYS):
        reasons.append("versions_missing")
    else:
        for key in VERSION_KEYS:
            if versions[key] != s["versions"][key]:
                reasons.append("version_mismatch:" + key)
    if verify:
        for problem in verify_release(s):
            if problem not in reasons:
                reasons.append(problem)
    try:
        window_of(window)
    except ValueError as exc:
        reasons.append("bad_window:" + str(exc))
        return {"ok": False, "reasons": reasons, "coverage": []}
    if not (s["valid"][0] <= window["start"] and s["valid"][1] >= window["end"]):
        reasons.append("dataset_does_not_cover_window")
    if not in_bounds(s, a) or not in_bounds(s, b):
        reasons.append("endpoint_outside_scene")
    lo = [min(a[i], b[i]) for i in range(3)]
    hi = [max(a[i], b[i]) for i in range(3)]
    tiles = coverage_for_bbox(s, lo, hi)
    if not tiles:
        reasons.append("no_coverage_tiles")
    if any(not t["complete"] for t in tiles):
        reasons.append("incomplete_coverage")
    return {"ok": not reasons, "reasons": reasons,
            "coverage": [t["id"] for t in tiles]}


def _active(feature, window):
    return feature.get("state", "published") == "published" and overlaps(
        feature["valid"], window)


def _building_hit_unknown(b):
    return b.get("top_z") is None or b.get("height_m") is None


def query_segment(s, a, b, window, versions, building_candidates=None,
                  verify=True):
    """Q2: status of one 3D segment over a half-open time window."""
    try:
        window = canonical_window(window)
    except ValueError:
        pass
    pf = preflight(s, window, a, b, versions, verify=verify)
    buildings = building_candidates if building_candidates is not None else s["buildings"]
    result = {
        "service": "Q2",
        "window": dict(window),
        "segment": {"a": list(a), "b": list(b)},
        "status": "unknown",
        "reasons": list(pf["reasons"]),
        "buildings": [],
        "airspace": [],
        "ground": [],
        "versions": dict(s["versions"]),
        "coverage": pf["coverage"],
        "candidates": len(buildings),
        "checked": 0,
    }
    blocked = []
    unknown = list(pf["reasons"])
    if pf["ok"]:
        for bld in buildings:
            if not overlaps(bld["valid"], window):
                continue
            result["checked"] += 1
            if not segment_hits_building(a, b, bld):
                continue
            if _building_hit_unknown(bld):
                unknown.append("unknown_height:" + bld["id"])
                result["buildings"].append({
                    "id": bld["id"], "name": bld["name"], "effect": "unknown",
                    "height_m": None, "top_z": None,
                    "height_source": bld.get("height_source"),
                })
                continue
            blocked.append("building:" + bld["id"])
            result["buildings"].append({
                "id": bld["id"], "name": bld["name"], "effect": "blocked",
                "height_m": bld["height_m"], "top_z": bld["top_z"],
                "base_z": bld["base_z"], "height_source": bld.get("height_source"),
            })
        for vol in s["airspace"]:
            if not _active(vol, window):
                continue
            if vol["kind"] == "no_fly" and segment_hits_volume(a, b, vol):
                blocked.append("airspace:" + vol["id"])
                result["airspace"].append({
                    "id": vol["id"], "name": vol["name"], "kind": vol["kind"],
                    "effect": "blocked", "valid": vol["valid"],
                    "source_id": vol["source_id"],
                })
            elif vol["kind"] == "height_limit":
                if vol.get("ceiling_m") is None:
                    unknown.append("unknown_ceiling:" + vol["id"])
                    result["airspace"].append({
                        "id": vol["id"], "name": vol["name"],
                        "kind": vol["kind"], "effect": "unknown",
                        "valid": vol["valid"], "source_id": vol["source_id"],
                    })
                elif segment_above_ceiling(a, b, vol):
                    blocked.append("ceiling:" + vol["id"])
                    result["airspace"].append({
                        "id": vol["id"], "name": vol["name"],
                        "kind": vol["kind"], "effect": "blocked",
                        "ceiling_m": vol["ceiling_m"], "valid": vol["valid"],
                        "source_id": vol["source_id"],
                    })
        for zone in s["ground_zones"]:
            if not overlaps(zone["valid"], window):
                continue
            if not segment_polygon_intervals(a, b, zone["polygon"]):
                continue
            result["ground"].append({
                "id": zone["id"], "name": zone["name"],
                "exposure_class": zone["exposure_class"],
                "q": zone.get("q"), "source_id": zone["source_id"],
            })
            if zone.get("q") is None:
                unknown.append("unknown_exposure:" + zone["id"])
    result["blocked_by"] = blocked
    if blocked:
        result["status"] = "forbidden"
    elif unknown:
        result["status"] = "unknown"
    else:
        result["status"] = "allowed"
    result["reasons"] = sorted(set(unknown))
    return result


def query_corridor(s, a, b, radius, window, versions, building_candidates=None,
                   verify=True):
    """Q1: clearance of a straight 3D corridor with horizontal/vertical radius.

    A height cap applies to the horizontal area at any altitude; the check
    compares the highest centerline point plus the vertical radius against the
    cap, matching ZC's ``buffer_m`` semantics.
    """
    if not (isfinite(radius) and radius >= 0):
        raise ValueError("radius must be finite and non-negative")
    try:
        window = canonical_window(window)
    except ValueError:
        pass
    pf = preflight(s, window, a, b, versions, verify=verify)
    buildings = building_candidates if building_candidates is not None else s["buildings"]
    result = {
        "service": "Q1",
        "window": dict(window),
        "segment": {"a": list(a), "b": list(b)},
        "radius_m": radius,
        "status": "unknown",
        "reasons": list(pf["reasons"]),
        "nearby": [],
        "airspace": [],
        "ground": [],
        "versions": dict(s["versions"]),
        "coverage": pf["coverage"],
        "candidates": len(buildings),
        "checked": 0,
    }
    blocked = []
    unknown = list(pf["reasons"])
    zlo = min(a[2], b[2])
    zhi = max(a[2], b[2])
    if pf["ok"]:
        for bld in buildings:
            if not overlaps(bld["valid"], window):
                continue
            result["checked"] += 1
            box = [[min(p[0] for p in bld["footprint"]),
                    min(p[1] for p in bld["footprint"]), bld["base_z"]],
                   [max(p[0] for p in bld["footprint"]),
                    max(p[1] for p in bld["footprint"]),
                    bld["top_z"] if bld["top_z"] is not None else 1e9]]
            d = segment_box_distance(a, b, box)
            if d > radius + 1e-9:
                continue
            if _building_hit_unknown(bld):
                unknown.append("unknown_height:" + bld["id"])
                result["nearby"].append({
                    "id": bld["id"], "name": bld["name"], "effect": "unknown",
                    "distance_m": round(d, 3),
                })
            else:
                blocked.append("building:" + bld["id"])
                result["nearby"].append({
                    "id": bld["id"], "name": bld["name"], "effect": "blocked",
                    "distance_m": round(d, 3), "height_m": bld["height_m"],
                })
        for vol in s["airspace"]:
            if not _active(vol, window):
                continue
            d2 = segment_polygon_distance_2d(a, b, vol["footprint"])
            if d2 > radius + 1e-9:
                continue
            if vol["kind"] == "no_fly":
                # The volume is three-dimensional, so the corridor must also
                # overlap its vertical range.
                vertical_gap = max(vol["floor_z"] - zhi,
                                   zlo - vol["ceiling_z"], 0.0)
                if vertical_gap > radius + 1e-9:
                    continue
            effect = "clearance_hit"
            close = False
            if vol["kind"] == "no_fly":
                close = True
            elif vol["kind"] == "height_limit":
                if vol.get("ceiling_m") is None:
                    unknown.append("unknown_ceiling:" + vol["id"])
                    effect = "unknown"
                elif zhi + radius > vol["ceiling_m"] + EPS:
                    # Match ZC: the height cap is checked against the highest
                    # point plus the full safety envelope; equality is clear.
                    close = True
            if close:
                blocked.append("airspace:" + vol["id"])
                effect = "blocked"
            result["airspace"].append({
                "id": vol["id"], "name": vol["name"], "kind": vol["kind"],
                "effect": effect, "horizontal_distance_m": round(d2, 3),
                "source_id": vol["source_id"],
            })
        for zone in s["ground_zones"]:
            if not overlaps(zone["valid"], window):
                continue
            if not segment_polygon_intervals(a, b, zone["polygon"]):
                continue
            result["ground"].append({
                "id": zone["id"], "name": zone["name"],
                "exposure_class": zone["exposure_class"],
                "q": zone.get("q"), "source_id": zone["source_id"],
            })
            if zone.get("q") is None:
                unknown.append("unknown_exposure:" + zone["id"])
    result["blocked_by"] = blocked
    if blocked:
        result["status"] = "blocked"
    elif unknown:
        result["status"] = "unknown"
    else:
        result["status"] = "clear"
    result["reasons"] = sorted(set(unknown))
    return result
