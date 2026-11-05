"""Data-quality rules and fault injection for the YHT scene release.

Quality is checked before a release is published. A warning is allowed in a
release but must be visible to consumers; an error blocks publication. Missing
height is a warning only when it is explicitly marked quality="unknown", and the
query service then returns unknown instead of treating the feature as absent.
"""
from copy import deepcopy
from math import isfinite

from yht_model import (
    BOUNDS, VERSION_KEYS, point_in_ring, ring_area, ring_is_closed,
    ring_is_simple, scene, seal, verify_release,
)


def _issue(rule, severity, feature, message):
    return {"rule": rule, "severity": severity, "feature": feature,
            "message": message}


def _inside_bounds(x, y, z=None):
    lo, hi = BOUNDS
    ok = lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]
    if z is not None:
        ok = ok and lo[2] <= z <= hi[2]
    return ok


def check_scene(s):
    errors, warnings = [], []

    def err(rule, feature, message):
        errors.append(_issue(rule, "error", feature, message))

    def warn(rule, feature, message):
        warnings.append(_issue(rule, "warning", feature, message))

    if s.get("schema") != "yht-scene-0.1":
        err("STR-001", "scene", "unexpected schema")
    if s.get("crs") != "starter-v0-local-m":
        err("STR-001", "scene", "unexpected crs")
    try:
        lo, hi = s["bounds"]
        if not (all(isfinite(v) for v in lo + hi) and
                all(lo[i] < hi[i] for i in range(3)) and lo[2] >= 0):
            err("STR-002", "scene", "bounds must be finite and increasing")
    except Exception:
        err("STR-002", "scene", "bounds missing or malformed")

    ids = [f["id"] for layer in ("buildings", "ground_zones", "airspace")
           for f in s[layer]]
    if len(ids) != len(set(ids)):
        err("STR-003", "scene", "duplicate feature ids")

    source_ids = {src["id"] for src in s["sources"]}
    for key in VERSION_KEYS:
        if key not in s.get("versions", {}):
            err("VER-001", "scene", "missing layer version: " + key)
    for problem in verify_release(s):
        err("VER-001", "scene", problem)

    for bld in s["buildings"]:
        fid = bld["id"]
        ring = bld["footprint"]
        if not ring_is_closed(ring) or len(ring) < 4:
            err("GEO-001", fid, "footprint ring not closed")
            continue
        if not ring_is_simple(ring):
            err("GEO-002", fid, "footprint ring self-intersects")
        if abs(ring_area(ring)) <= 1e-6:
            err("GEO-003", fid, "footprint has zero area")
        for x, y in ring:
            if not _inside_bounds(x, y):
                err("GEO-004", fid, "footprint outside scene bounds")
                break
        top = bld.get("top_z")
        if top is None or bld.get("height_m") is None:
            if bld.get("quality") != "unknown":
                err("ATTR-002", fid, "missing height is not marked unknown")
            else:
                warn("ATTR-002", fid, "height unknown; dependent queries must fail closed")
        else:
            if not isfinite(top) or not isfinite(bld["height_m"]):
                err("GEO-005", fid, "height is not finite")
            elif top <= bld["base_z"]:
                err("GEO-005", fid, "top_z must exceed base_z")
            elif abs((top - bld["base_z"]) - bld["height_m"]) > 1e-6:
                err("GEO-005", fid, "height_m inconsistent with top_z")
            if bld.get("quality") not in ("observed", "derived", "assumed"):
                err("ATTR-002", fid, "unexpected height quality flag")
        for key in ("footprint_source", "height_source"):
            if bld.get(key) not in source_ids:
                err("ATTR-001", fid, "unknown source: " + str(bld.get(key)))
        if not (bld["valid"][0] < bld["valid"][1]):
            err("TIME-001", fid, "invalid validity window")
        elif not (s["valid"][0] <= bld["valid"][0] and bld["valid"][1] <= s["valid"][1]):
            err("TIME-001", fid, "feature validity outside scene validity")

    for zone in s["ground_zones"]:
        fid = zone["id"]
        ring = zone["polygon"]
        if not ring_is_closed(ring) or not ring_is_simple(ring):
            err("GEO-002", fid, "exposure polygon invalid")
        if abs(ring_area(ring)) <= 1e-6:
            err("GEO-003", fid, "exposure polygon has zero area")
        if zone.get("source_id") not in source_ids:
            err("ATTR-001", fid, "unknown source")
        q = zone.get("q")
        e = zone.get("exposure_e")
        c = zone.get("consequence_c")
        if q is not None and not (0.0 <= q <= 1.0):
            err("ATTR-003", fid, "q outside [0,1]")
        if q is None:
            warn("ATTR-003", fid, "exposure q missing; queries must return unknown")
        else:
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and isfinite(v) and 0.0 <= v <= 1.0 for v in (e, c)):
                err("ATTR-003", fid, "exposure E/C missing or outside [0,1]")
            elif abs(e * c - q) > 1e-9:
                err("ATTR-003", fid, "q does not equal E*C")
        if not zone.get("exposure_class"):
            err("ATTR-003", fid, "missing exposure class")

    for vol in s["airspace"]:
        fid = vol["id"]
        ring = vol["footprint"]
        if not ring_is_closed(ring) or not ring_is_simple(ring):
            err("GEO-002", fid, "airspace footprint invalid")
        for x, y in ring:
            if not _inside_bounds(x, y):
                err("GEO-004", fid, "airspace outside scene bounds")
                break
        if vol.get("kind") not in ("no_fly", "height_limit"):
            err("AIR-001", fid, "unexpected airspace kind")
        if vol.get("state") not in ("published", "revoked", "expired"):
            err("AIR-001", fid, "unexpected airspace state")
        if not (vol["floor_z"] < vol["ceiling_z"]):
            err("AIR-001", fid, "floor_z must be below ceiling_z")
        if vol.get("source_id") not in source_ids:
            err("ATTR-001", fid, "unknown source")
        if vol.get("kind") == "height_limit":
            ceiling = vol.get("ceiling_m")
            if ceiling is None:
                err("AIR-001", fid, "height limit without ceiling_m")
            elif not (vol["floor_z"] <= ceiling <= vol["ceiling_z"]):
                err("AIR-001", fid, "ceiling_m outside volume")
        if vol.get("kind") == "no_fly" and vol.get("ceiling_m") is not None:
            err("AIR-001", fid, "no_fly must not carry ceiling_m")
        if not (vol["valid"][0] < vol["valid"][1]):
            err("TIME-001", fid, "invalid validity window")

    # Exposure partitions: sample interior cell centres, exactly one zone each.
    step = 20
    gaps = overlaps = 0
    for i in range(30):
        for j in range(30):
            p = [i * step + step / 2 + 2, j * step + step / 2 + 2]
            hits = sum(1 for z in s["ground_zones"]
                       if point_in_ring(p, z["polygon"]))
            if hits == 0:
                gaps += 1
            elif hits > 1:
                overlaps += 1
    if gaps or overlaps:
        err("RISK-001", "exposure", f"coverage gaps={gaps} overlaps={overlaps}")

    # Coverage tiles: area tiling and completeness flag.
    tile_area = sum((t["max"][0] - t["min"][0]) * (t["max"][1] - t["min"][1])
                    for t in s["coverage"])
    scene_area = (BOUNDS[1][0] - BOUNDS[0][0]) * (BOUNDS[1][1] - BOUNDS[0][1])
    if abs(tile_area - scene_area) > 1e-6:
        err("COV-001", "coverage", "coverage tiles do not cover the scene")
    if any(not t["complete"] for t in s["coverage"]):
        warn("COV-001", "coverage", "incomplete tile: queries over it return unknown")

    for src in s["sources"]:
        for key in ("license", "method", "acquired_at", "valid"):
            if not src.get(key):
                err("META-001", src["id"], "missing " + key)
        for key in ("accuracy_xy_m", "accuracy_z_m"):
            value = src.get(key)
            if value is not None and not (isfinite(value) and value >= 0):
                err("META-001", src["id"], "bad " + key)
        if not (src["valid"][0] < src["valid"][1]):
            err("TIME-001", src["id"], "invalid source validity")

    manifest = s.get("manifest") or {}
    expected_counts = {
        "buildings": len(s["buildings"]),
        "terrain_posts": len(s["terrain"]["posts"]),
        "ground_zones": len(s["ground_zones"]),
        "airspace": len(s["airspace"]),
        "coverage_tiles": len(s["coverage"]),
    }
    if manifest.get("counts") != expected_counts:
        err("META-002", "manifest", "manifest counts do not match payload")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "features": len(ids),
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }


def _reseal(s, mutate):
    out = deepcopy(s)
    mutate(out)
    return seal(out)


FAULTS = {
    "duplicate_id": (
        "STR-003", lambda s: s["buildings"][1].update({"id": "B-001"})),
    "self_intersecting_footprint": (
        "GEO-002",
        lambda s: s["buildings"][2].update({
            "footprint": [[100, 30], [140, 80], [100, 80], [140, 30], [100, 30]]})),
    "unclosed_ring": (
        "GEO-001",
        lambda s: s["buildings"][3].update({"footprint": [[100, 100], [140, 100], [140, 140]]})),
    "top_below_base": (
        "GEO-005",
        lambda s: s["buildings"][4].update({"height_m": -1.0, "top_z": -1.0})),
    "missing_height": (
        "ATTR-002",
        lambda s: s["buildings"][5].update(
            {"height_m": None, "top_z": None, "quality": "unknown"})),
    "unknown_source": (
        "ATTR-001",
        lambda s: s["buildings"][6].update({"footprint_source": "SRC-NOPE"})),
    "bad_exposure_q": (
        "ATTR-003",
        lambda s: s["ground_zones"][0].update({"q": 1.4})),
    "incomplete_tile": (
        "COV-001",
        lambda s: s["coverage"][14].update({"complete": False})),
    "bad_airspace_kind": (
        "AIR-001",
        lambda s: s["airspace"][0].update({"kind": "temporary"})),
    "missing_ceiling": (
        "AIR-001",
        lambda s: s["airspace"][2].update({"ceiling_m": None})),
    "outside_bounds": (
        "GEO-004",
        lambda s: s["buildings"][7].update({
            "footprint": [[590, 90], [650, 90], [650, 140], [590, 140], [590, 90]]})),
    "stale_version": (
        "VER-001",
        lambda s: s["buildings"][0].update({"name": "changed without reseal"})),
}


def run_fault_injection():
    base = seal(scene())
    results = []
    for name, (expected, mutate) in FAULTS.items():
        if name == "stale_version":
            faulty = deepcopy(base)
            mutate(faulty)
        else:
            faulty = _reseal(base, mutate)
        report = check_scene(faulty)
        rules = {e["rule"] for e in report["errors"]} | {
            w["rule"] for w in report["warnings"]}
        results.append({
            "case": name,
            "expected_rule": expected,
            "detected": expected in rules,
            "errors": report["counts"]["errors"],
            "warnings": report["counts"]["warnings"],
        })
    return results


def query_after_mutation():
    """Missing height and incomplete coverage must return unknown, not allowed."""
    from query import query_segment
    base = seal(scene())
    window = {"start": "2026-11-05T08:05:00Z", "end": "2026-11-05T08:15:00Z"}
    cases = {}
    faulty = _reseal(base, lambda s: s["buildings"][5].update(
        {"height_m": None, "top_z": None, "quality": "unknown"}))
    # B-006 occupies 80..140 x 180..230; use a segment that clearly crosses it.
    cases["missing_height"] = query_segment(
        faulty, [70, 200, 20], [150, 200, 20], window, faulty["versions"])
    faulty = _reseal(base, lambda s: s["coverage"][14].update(
        {"complete": False}))
    cases["incomplete_coverage"] = query_segment(
        faulty, [250, 250, 20], [290, 290, 20], window, faulty["versions"])
    return {k: {"status": v["status"], "reasons": v["reasons"]}
            for k, v in cases.items()}
