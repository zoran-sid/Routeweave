"""SkyRoute YHT: synthetic 3D scene, geometry predicates and version binding.

Standard library only. Coordinates are local east/north/up metres on a common
z=0 reference plane, following docs/scenario-contract.md. The sample terrain is
flat so that ZC's current flat-terrain planner can consume an export; the data
model still carries a terrain grid and its provenance.

All geometry is synthetic. Building footprints are local JSON rings (not RFC
7946 GeoJSON: RFC 7946 positions are WGS-84 longitude/latitude, so a local
metric ring must not be labelled GeoJSON).
"""
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from math import dist, isfinite, sqrt

SCHEMA = "yht-scene-0.1"
BOUNDS = ((0.0, 0.0, 0.0), (600.0, 600.0, 160.0))
SCENE_ID = "yht-synthetic-district-v1"
VALID = ("2026-11-05T08:00:00Z", "2026-11-05T09:00:00Z")
VERSION_KEYS = ("scene", "terrain", "airspace", "exposure", "sources")
EPS = 1e-9


def rect(x0, y0, x1, y1):
    """Closed counter-clockwise rectangle ring."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _b(fid, name, x0, y0, x1, y1, height, height_source="SRC-HEIGHT",
       quality="derived", base_z=0.0, footprint=None):
    return {
        "id": fid,
        "kind": "building",
        "name": name,
        "footprint": footprint if footprint is not None else rect(x0, y0, x1, y1),
        "base_z": base_z,
        "top_z": base_z + height,
        "height_m": height,
        "footprint_source": "SRC-FOOTPRINT",
        "height_source": height_source,
        "quality": quality,
        "valid": list(VALID),
    }


def _g(fid, name, x0, y0, x1, y1, exposure_class, q, exposure_e, consequence_c):
    return {
        "id": fid,
        "kind": "ground_zone",
        "name": name,
        "polygon": rect(x0, y0, x1, y1),
        "exposure_class": exposure_class,
        "q": q,
        "exposure_e": exposure_e,
        "consequence_c": consequence_c,
        "source_id": "SRC-EXPOSURE",
        "quality": "derived",
        "valid": list(VALID),
    }


def _a(fid, name, footprint, kind, z0, z1, valid=None, ceiling_m=None,
       state="published"):
    return {
        "id": fid,
        "kind": kind,
        "name": name,
        "footprint": footprint,
        "floor_z": z0,
        "ceiling_z": z1,
        "ceiling_m": ceiling_m,
        "valid": list(valid or VALID),
        "state": state,
        "authority": "mock-airspace-office",
        "source_id": "SRC-AIRSPACE",
        "quality": "assumed",
    }


def sources():
    return [
        {
            "id": "SRC-FOOTPRINT",
            "name": "合成建筑轮廓（OSM 结构类比）",
            "kind": "vector",
            "license": "CC0-1.0 (synthetic)",
            "acquired_at": "2026-11-01T00:00:00Z",
            "valid": list(VALID),
            "accuracy_xy_m": 2.0,
            "accuracy_z_m": None,
            "method": "hand-authored blocks and street grid",
        },
        {
            "id": "SRC-HEIGHT",
            "name": "合成激光雷达建筑高度",
            "kind": "lidar-derived",
            "license": "CC0-1.0 (synthetic)",
            "acquired_at": "2026-11-01T00:00:00Z",
            "valid": list(VALID),
            "accuracy_xy_m": 1.0,
            "accuracy_z_m": 1.5,
            "method": "roof DSM minus flat reference plane",
        },
        {
            "id": "SRC-TERRAIN",
            "name": "合成地形格网",
            "kind": "grid-dem",
            "license": "CC0-1.0 (synthetic)",
            "acquired_at": "2026-11-01T00:00:00Z",
            "valid": list(VALID),
            "accuracy_xy_m": 10.0,
            "accuracy_z_m": 0.3,
            "method": "flat reference variant for ZC integration",
        },
        {
            "id": "SRC-EXPOSURE",
            "name": "合成地面暴露代理",
            "kind": "polygon-derived",
            "license": "CC0-1.0 (synthetic)",
            "acquired_at": "2026-11-01T00:00:00Z",
            "valid": list(VALID),
            "accuracy_xy_m": 100.0,
            "accuracy_z_m": None,
            "method": "land-use class assigned q; not a population count",
        },
        {
            "id": "SRC-AIRSPACE",
            "name": "模拟空域参考与临时限制",
            "kind": "vector",
            "license": "CC0-1.0 (synthetic)",
            "acquired_at": "2026-11-01T00:00:00Z",
            "valid": list(VALID),
            "accuracy_xy_m": 5.0,
            "accuracy_z_m": 2.0,
            "method": "ZQO-owned reference fixtures, not published NOTAMs",
        },
    ]


def buildings():
    l_shape = [[330, 330], [410, 330], [410, 360], [360, 360],
               [360, 410], [330, 410], [330, 330]]
    return [
        _b("B-001", "云塔一号", 30, 30, 90, 90, 120, quality="observed"),
        _b("B-002", "云塔二号", 30, 110, 80, 140, 80, quality="observed"),
        _b("B-003", "商务中庭", 100, 30, 140, 80, 45),
        _b("B-004", "商务西座", 100, 100, 140, 140, 35),
        _b("B-005", "街角低层", 10, 180, 60, 230, 18, quality="observed"),
        _b("B-006", "社区中心", 80, 180, 140, 230, 30),
        _b("B-007", "滨河酒店", 180, 20, 240, 70, 60, quality="observed"),
        _b("B-008", "商业综合体", 180, 90, 260, 140, 25),
        _b("B-009", "办公楼九号", 180, 180, 230, 240, 55),
        _b("B-010", "住宅十号", 250, 20, 290, 70, 40),
        _b("B-011", "住宅十一号", 250, 90, 290, 140, 40),
        _b("B-012", "实验小学", 340, 30, 420, 90, 15, quality="observed"),
        _b("B-013", "市立医院", 340, 110, 420, 160, 70, quality="observed"),
        _b("B-014", "东塔十四", 500, 30, 560, 90, 100),
        _b("B-015", "东塔十五", 500, 110, 560, 150, 75),
        _b("B-016", "东侧低层", 480, 180, 540, 240, 22),
        _b("B-017", "东侧中座", 480, 260, 540, 320, 48),
        _b("B-018", "政务中心", 480, 480, 560, 560, 45, quality="observed"),
        _b("B-019", "综合交通站", 40, 480, 120, 540, 20, quality="observed"),
        _b("B-020", "南区中座", 150, 480, 200, 540, 50),
        _b("B-021", "南区住宅甲", 340, 470, 400, 530, 35),
        _b("B-022", "南区住宅乙", 340, 545, 400, 590, 35),
        _b("B-023", "创意园区 L 座", 330, 330, 410, 410, 26,
           base_z=0.0, footprint=l_shape),
        _b("B-024", "东南中座", 480, 340, 540, 400, 60),
        _b("B-025", "公园服务楼", 180, 340, 240, 400, 16,
           height_source="SRC-HEIGHT", quality="assumed"),
    ]


def ground_zones():
    return [
        _g("G-001", "商业步行区", 0, 0, 300, 300, "commercial", 0.78, 0.975, 0.8),
        _g("G-002", "东侧住宅区", 300, 0, 600, 300, "residential", 0.45, 0.75, 0.6),
        _g("G-003", "滨水公园", 0, 300, 300, 450, "park", 0.06, 0.3, 0.2),
        _g("G-004", "公共服务区", 300, 300, 600, 450, "civic", 0.55, 0.6875, 0.8),
        _g("G-005", "综合交通枢纽", 0, 450, 300, 600, "transit", 0.82, 0.9111111111111111, 0.9),
        _g("G-006", "政务与办公区", 300, 450, 600, 600, "government", 0.32, 0.4, 0.8),
    ]


def airspace():
    return [
        _a("NF-001", "政务中心临时禁飞区", rect(470, 470, 570, 570),
           "no_fly", 0, 120),
        _a("NF-002", "城市活动临时禁飞区", rect(130, 130, 170, 170),
           "no_fly", 0, 120,
           valid=("2026-11-05T07:00:00Z", "2026-11-05T11:00:00Z")),
        _a("HL-001", "医院进近限高", rect(330, 100, 430, 170),
           "height_limit", 0, 160, ceiling_m=60),
    ]


def terrain():
    """31 x 31 posts at 20 m spacing, flat reference variant."""
    posts = []
    for i in range(31):
        for j in range(31):
            posts.append({"x": i * 20.0, "y": j * 20.0, "z": 0.0})
    return {
        "kind": "grid-dem",
        "spacing_m": 20.0,
        "origin": [0.0, 0.0],
        "size": [31, 31],
        "z": 0.0,
        "flat": True,
        "posts": posts,
        "source_id": "SRC-TERRAIN",
        "valid": list(VALID),
    }


def coverage():
    return [
        {
            "id": f"T-{i:02d}-{j:02d}",
            "min": [i * 100.0, j * 100.0],
            "max": [i * 100.0 + 100.0, j * 100.0 + 100.0],
            "complete": True,
            "source_id": "SRC-FOOTPRINT",
        }
        for i, j in product(range(6), range(6))
    ]


def scene():
    """Unsealed scene: versions and manifest are added by seal()."""
    return {
        "schema": SCHEMA,
        "scene_id": SCENE_ID,
        "crs": "starter-v0-local-m",
        "bounds": [[v for v in BOUNDS[0]], [v for v in BOUNDS[1]]],
        "valid": list(VALID),
        "buildings": buildings(),
        "terrain": terrain(),
        "ground_zones": ground_zones(),
        "airspace": airspace(),
        "sources": sources(),
        "coverage": coverage(),
        "quality": {"missing_height_ids": [], "coverage_complete": True},
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()[:12]


def layer_payload(s, key):
    if key == "scene":
        return {k: s[k] for k in
                ("schema", "scene_id", "crs", "bounds", "valid", "buildings",
                 "coverage")}
    if key == "terrain":
        return s["terrain"]
    if key == "airspace":
        return s["airspace"]
    if key == "exposure":
        return s["ground_zones"]
    if key == "sources":
        return s["sources"]
    raise KeyError(key)


def versions(s):
    return {k: "mock-yht-" + k + "-" + digest(layer_payload(s, k))
            for k in VERSION_KEYS}


def seal(s):
    s = deepcopy(s)
    s["versions"] = versions(s)
    s["manifest"] = {
        "schema": SCHEMA,
        "scene_id": s["scene_id"],
        "created_at": "2026-11-05T08:00:00Z",
        "content_hash": digest({k: s["versions"][k] for k in VERSION_KEYS}),
        "counts": {
            "buildings": len(s["buildings"]),
            "terrain_posts": len(s["terrain"]["posts"]),
            "ground_zones": len(s["ground_zones"]),
            "airspace": len(s["airspace"]),
            "coverage_tiles": len(s["coverage"]),
        },
        "owner": "YHT",
    }
    return s


def verify_release(s):
    """Return a list of integrity problems; empty means the snapshot is usable."""
    problems = []
    expected = versions(s)
    stored = s.get("versions", {})
    for key in VERSION_KEYS:
        if stored.get(key) != expected[key]:
            problems.append("version_mismatch:" + key)
    manifest = s.get("manifest") or {}
    content = digest({k: expected[k] for k in VERSION_KEYS})
    if manifest.get("content_hash") != content:
        problems.append("manifest_content_hash_mismatch")
    return problems


def bbox(points_2d, z0, z1):
    xs = [p[0] for p in points_2d]
    ys = [p[1] for p in points_2d]
    return ((min(xs), min(ys), z0), (max(xs), max(ys), z1))


def building_bbox(b):
    lo, hi = bbox(b["footprint"], b["base_z"], b["top_z"])
    return [list(lo), list(hi)]


def airspace_bbox(a):
    lo, hi = bbox(a["footprint"], a["floor_z"], a["ceiling_z"])
    return [list(lo), list(hi)]


def ring_area(poly):
    total = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def point_in_ring(p, poly):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if point_on_segment(p, (x1, y1), (x2, y2)):
            return True
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if xin > x:
                inside = not inside
    return inside


def point_on_segment(p, a, b):
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > 1e-7:
        return False
    dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])
    if dot < -EPS:
        return False
    sq = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
    return dot <= sq + EPS


def ring_is_closed(poly):
    return len(poly) >= 4 and poly[0] == poly[-1]


def segments_intersect_2d(p1, p2, q1, q2):
    """Closed 2D segment intersection, including collinear overlap."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    def on(a, b, p):
        return (min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS
                and min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS)

    o1, o2 = orient(p1, p2, q1), orient(p1, p2, q2)
    o3, o4 = orient(q1, q2, p1), orient(q1, q2, p2)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and on(p1, p2, q1):
        return True
    if o2 == 0 and on(p1, p2, q2):
        return True
    if o3 == 0 and on(q1, q2, p1):
        return True
    if o4 == 0 and on(q1, q2, p2):
        return True
    return False


def ring_is_simple(poly):
    if not ring_is_closed(poly) or len(poly) < 4:
        return False
    edges = list(zip(poly, poly[1:]))
    n = len(edges)
    for i in range(n):
        a, b = edges[i]
        if dist(a, b) <= EPS:
            return False
        for j in range(i + 1, n):
            c, d = edges[j]
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if segments_intersect_2d(a, b, c, d):
                return False
    return True


def segment_param_2d(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy) and abs(dx) > EPS:
        return (p[0] - a[0]) / dx
    if abs(dy) > EPS:
        return (p[1] - a[1]) / dy
    return 0.0


def segment_polygon_intervals(a, b, poly):
    """Parameter intervals on a->b whose midpoint lies on/inside the ring."""
    ts = {0.0, 1.0}
    for c, d in zip(poly, poly[1:]):
        # Solve a + t(b-a) = c + u(d-c) for t, u.
        rx, ry = b[0] - a[0], b[1] - a[1]
        sx, sy = d[0] - c[0], d[1] - c[1]
        den = rx * sy - ry * sx
        if abs(den) > 1e-12:
            qx, qy = c[0] - a[0], c[1] - a[1]
            t = (qx * sy - qy * sx) / den
            u = (qx * ry - qy * rx) / den
            if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
                ts.add(min(1.0, max(0.0, t)))
        elif segments_intersect_2d(a, b, c, d):
            for p in (c, d):
                ts.add(min(1.0, max(0.0, segment_param_2d(a, b, p))))
            if point_in_ring((a[0], a[1]), poly):
                ts.add(0.0)
            if point_in_ring((b[0], b[1]), poly):
                ts.add(1.0)
    ordered = sorted(ts)
    out = []
    for t0, t1 in zip(ordered, ordered[1:]):
        if t1 - t0 <= 1e-12:
            continue
        mid = ((a[0] + b[0]) / 2 + (t0 + t1) / 2 * (b[0] - a[0]),
               (a[1] + b[1]) / 2 + (t0 + t1) / 2 * (b[1] - a[1]))
        if point_in_ring(mid, poly):
            out.append((t0, t1))
    if not out and point_in_ring(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), poly):
        out.append((0.0, 1.0))
    return out


def segment_box_interval(a, b, box, margin=0.0):
    low, high = 0.0, 1.0
    for i in range(3):
        lo, hi = box[0][i] - margin, box[1][i] + margin
        delta = b[i] - a[i]
        if abs(delta) <= EPS:
            if not lo - EPS <= a[i] <= hi + EPS:
                return None
        else:
            t1, t2 = (lo - a[i]) / delta, (hi - a[i]) / delta
            low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low > high + EPS:
                return None
    return max(0.0, low), min(1.0, high)


def segment_hits_box(a, b, box):
    return segment_box_interval(a, b, box) is not None


def point_box_distance(p, box):
    total = 0.0
    for i in range(3):
        v = p[i]
        if v < box[0][i]:
            total += (box[0][i] - v) ** 2
        elif v > box[1][i]:
            total += (v - box[1][i]) ** 2
    return sqrt(total)


def segments_distance(p1, q1, p2, q2):
    """Closest distance between two 3D segments (Ericson's algorithm)."""
    d1 = [q1[i] - p1[i] for i in range(3)]
    d2 = [q2[i] - p2[i] for i in range(3)]
    r = [p1[i] - p2[i] for i in range(3)]
    a = sum(v * v for v in d1)
    e = sum(v * v for v in d2)
    f = sum(d2[i] * r[i] for i in range(3))
    if a <= EPS and e <= EPS:
        return sqrt(sum(v * v for v in r))
    if a <= EPS:
        s = 0.0
        t = min(1.0, max(0.0, f / e))
    else:
        c = sum(d1[i] * r[i] for i in range(3))
        if e <= EPS:
            t = 0.0
            s = min(1.0, max(0.0, -c / a))
        else:
            b = sum(d1[i] * d2[i] for i in range(3))
            den = a * e - b * b
            s = min(1.0, max(0.0, (b * f - c * e) / den)) if abs(den) > EPS else 0.0
            t = (b * s + f) / e
            if t < 0:
                t = 0.0
                s = min(1.0, max(0.0, -c / a))
            elif t > 1:
                t = 1.0
                s = min(1.0, max(0.0, (b - c) / a))
    closest1 = [p1[i] + s * d1[i] for i in range(3)]
    closest2 = [p2[i] + t * d2[i] for i in range(3)]
    return sqrt(sum((closest1[i] - closest2[i]) ** 2 for i in range(3)))


def segment_box_distance(a, b, box):
    interval = segment_box_interval(a, b, box)
    if interval is not None:
        return 0.0
    best = min(point_box_distance(a, box), point_box_distance(b, box))
    lo, hi = box
    corners = [[lo[0] if i & 1 == 0 else hi[0],
                lo[1] if i & 2 == 0 else hi[1],
                lo[2] if i & 4 == 0 else hi[2]] for i in range(8)]
    for i in range(8):
        for j in range(i + 1, 8):
            if bin(i ^ j).count("1") != 1:
                continue
            best = min(best, segments_distance(a, b, corners[i], corners[j]))
    return best


def segment_polygon_distance_2d(a, b, poly):
    if segment_polygon_intervals(a, b, poly):
        return 0.0
    best = min(dist(a[:2], p) for p in poly)
    best = min(best, min(dist(b[:2], p) for p in poly))
    for c, d in zip(poly, poly[1:]):
        # 2D segment-to-segment distance via lifting to z=0.
        best = min(best, segments_distance(
            (a[0], a[1], 0.0), (b[0], b[1], 0.0),
            (c[0], c[1], 0.0), (d[0], d[1], 0.0)))
    return best


def z_at(a, b, t):
    return a[2] + t * (b[2] - a[2])


def segment_hits_building(a, b, building):
    intervals = segment_polygon_intervals(a, b, building["footprint"])
    if not intervals:
        return False
    if building.get("top_z") is None:
        return True
    base, top = building["base_z"], building["top_z"]
    for t0, t1 in intervals:
        zlo = min(z_at(a, b, t0), z_at(a, b, t1))
        zhi = max(z_at(a, b, t0), z_at(a, b, t1))
        if zhi >= base - EPS and zlo <= top + EPS:
            return True
    return False


def segment_hits_volume(a, b, volume):
    intervals = segment_polygon_intervals(a, b, volume["footprint"])
    if not intervals:
        return False
    for t0, t1 in intervals:
        zlo = min(z_at(a, b, t0), z_at(a, b, t1))
        zhi = max(z_at(a, b, t0), z_at(a, b, t1))
        if zhi >= volume["floor_z"] - EPS and zlo <= volume["ceiling_z"] + EPS:
            return True
    return False


def segment_above_ceiling(a, b, volume):
    intervals = segment_polygon_intervals(a, b, volume["footprint"])
    if not intervals:
        return False
    ceiling = volume["ceiling_m"]
    return any(max(z_at(a, b, t0), z_at(a, b, t1)) > ceiling + EPS
               for t0, t1 in intervals)


def bbox_of_segment(a, b, margin=0.0):
    return ([min(a[i], b[i]) - margin for i in range(3)],
            [max(a[i], b[i]) + margin for i in range(3)])


def point_in_coverage(s, p, margin=0.0):
    for tile in s["coverage"]:
        if (tile["min"][0] - margin <= p[0] <= tile["max"][0] + margin
                and tile["min"][1] - margin <= p[1] <= tile["max"][1] + margin):
            return tile
    return None


def coverage_for_bbox(s, lo, hi):
    tiles = []
    for tile in s["coverage"]:
        if (tile["min"][0] <= hi[0] and tile["max"][0] >= lo[0]
                and tile["min"][1] <= hi[1] and tile["max"][1] >= lo[1]):
            tiles.append(tile)
    return tiles


def valid_at(feature, at):
    return feature["valid"][0] <= at < feature["valid"][1]


def scene_stats(s):
    area = sum(abs(ring_area(z["polygon"])) for z in s["ground_zones"])
    return {
        "scene_id": s["scene_id"],
        "bounds": s["bounds"],
        "buildings": len(s["buildings"]),
        "ground_zones": len(s["ground_zones"]),
        "airspace": len(s["airspace"]),
        "terrain_posts": len(s["terrain"]["posts"]),
        "coverage_tiles": len(s["coverage"]),
        "coverage_complete": all(t["complete"] for t in s["coverage"]),
        "building_footprint_m2": round(sum(
            abs(ring_area(b["footprint"])) for b in s["buildings"]), 1),
        "exposure_area_m2": round(area, 1),
        "max_building_top_m": max(b["top_z"] for b in s["buildings"]),
        "sources": len(s["sources"]),
        "versions": dict(s.get("versions", {})),
    }
