"""Hong Kong (Kowloon) open-data payloads for the v2 experiments.

Builds the same layer payload the experiments used to generate synthetically, from the snapshot written by
fetch.py. Coordinates stay in HK1980 Grid (EPSG:2326, metres); heights are metres above Principal Datum (mPD).

Real inputs: building footprints and heights (Lands Department), 2021 census population by Large Subunit Group,
school and hospital locations, and gazetted drone restricted flying zones (Civil Aviation Department).
Derived: terrain posts from building base heights; exposure E from census density; zone boxes for restricted
flying zones from the facility footprints. Assumed: the risk model parameters (C, threshold) and every scenario
restriction used to exercise publication and update experiments (``scenario_restrictions``).
"""
import gzip
import json
import math
import random
import sqlite3
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "docs/v2/schema"))
import fixtures as fx  # noqa: E402

MANIFEST = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
CENTRE = tuple(MANIFEST["centre"])
AREAS = {k: tuple(v) for k, v in MANIFEST["areas"].items()}
ACQUIRED = MANIFEST["retrieved_at"]
STUDY = ("2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z")
FLIGHT_Z = 100.0                       # mPD; task endpoints are placed at this level
UNKNOWN_TOP = 400.0                    # mPD; structures without a height block every altitude
RFZ_BUFFER = 20.0                      # m around facility footprints (official boundary: CAD Drone Map)
SCHOOL_HALF, HOSPITAL_HALF = 30.0, 50.0
C_RESIDENTIAL, C_SENSITIVE = 0.5, 0.95  # LQ demo consequence parameters (assumed, not calibrated)
LICENCE = "DATA.GOV.HK terms: free use with source identified and attribution to the HKSAR Government and provider"

SOURCES = {
    "SRC-HK-BLDG": ("Lands Department Building (CSDI)", "gis", "Lands Department, HKSAR Government", "monthly", "public"),
    "SRC-HK-CENSUS": ("2021 Population Census by Large Subunit Group", "census", "Census and Statistics Department", "static", "public"),
    "SRC-HK-SCHOOL": ("School Location and Information", "gis", "Education Bureau", "monthly", "public"),
    "SRC-HK-HOSP": ("Hospital Authority hospitals and institutions", "gis", "Hospital Authority", "monthly", "public"),
    "SRC-HK-RFZ": ("Restricted flying zones, G.N. 8002 (Cap. 448G)", "authority_feed", "Civil Aviation Department", "event", "public"),
    "SRC-HK-DERIVED": ("SkyRoute derivations from the HK snapshot", "derived", "SkyRoute (course project)", "static", "internal"),
    "SRC-SCENARIO": ("Scenario temporary restrictions (not real notices)", "synthetic", "SkyRoute (course project)", "event", "internal"),
}


def load(name):
    return json.loads(gzip.decompress((HERE / "snapshot" / f"{name}.json.gz").read_bytes()))


def ring_bbox(rings):
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def signed_area(ring):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def polygon_wkt(rings):
    """Esri rings (outer clockwise, holes counter-clockwise) -> POLYGON or MULTIPOLYGON WKT."""
    def text(r):
        return "(" + ",".join(f"{x:.2f} {y:.2f}" for x, y in r) + ")"
    outers = [[r] for r in rings if signed_area(r) <= 0] or [[rings[0]]]
    for h in (r for r in rings if signed_area(r) > 0 and len(outers) and r is not outers[0][0]):
        x, y = h[0]
        home = next((o for o in outers if ring_bbox([o[0]])[0] <= x <= ring_bbox([o[0]])[2]
                     and ring_bbox([o[0]])[1] <= y <= ring_bbox([o[0]])[3]), outers[0])
        home.append(h)
    if len(outers) == 1:
        return "POLYGON(" + ",".join(text(r) for r in outers[0]) + ")"
    return "MULTIPOLYGON(" + ",".join("(" + ",".join(text(r) for r in o) + ")" for o in outers) + ")"


def intersects(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def polygon_area(rings):
    """Esri convention: outer rings clockwise (negative), holes counter-clockwise (positive)."""
    return abs(sum(signed_area(r) for r in rings))


_CACHE = {}


def snapshot():
    if not _CACHE:
        _CACHE.update({k: load(k) for k in ("buildings", "census_lsg", "schools", "hospitals", "rfz")})
        dens = [z["pop"] / polygon_area(z["rings"]) for z in _CACHE["census_lsg"] if z["pop"] and z["rings"]]
        _CACHE["density_ref"] = statistics.quantiles(dens, n=20)[18]   # 95th percentile, persons per m2 (L extent)
    return _CACHE


def add_sources(c):
    """Register the snapshot sources. owner_org is the custodian inside SkyRoute (org code SYN, the organisation of
    the seeded actors), which holds the licensed copy; the government provider is recorded in name and notes."""
    for sid, (name, stype, owner, freq, sens) in SOURCES.items():
        c.execute("INSERT INTO source (source_id, name, source_type, owner_org, license, acquisition_method, acquired_at,"
                  " update_frequency, sensitivity, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (sid, name, stype, "SYN", LICENCE if stype != "synthetic" else "scenario (not a real notice)",
                   "fetch.py snapshot" if stype not in ("derived", "synthetic") else "hk.py", ACQUIRED, freq, sens,
                   f"provider: {owner}; see docs/v2/data/hk/README.md"))


def feature(c, rid, release_id, fid, ftype, source, quality, name=None, attrs=None, valid=STUDY):
    layer = {"building": "scene", "airspace": "airspace", "exposure": "exposure"}[ftype]
    c.execute("INSERT INTO feature (rid, release_id, feature_id, layer, feature_type, name, source_id, quality, valid_lo,"
              " valid_hi, recorded_at, sensitivity, attrs, geom_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (rid, release_id, fid, layer, ftype, name, source, quality, valid[0], valid[1], ACQUIRED,
               "internal" if ftype == "building" else "restricted", json.dumps(attrs) if attrs else None,
               "polygon" if ftype == "exposure" else "polyhedral"))


def add_airspace(c, rid, release_id, rid_text, box, effective, kind="no_fly", ceiling=None, source="SRC-SCENARIO",
                 authority="scenario", quality="assumed", name=None, attrs=None, state="published"):
    feature(c, rid, release_id, rid_text, "airspace", source, quality, name, attrs)
    x0, y0, x1, y1 = box
    c.execute("INSERT INTO airspace_restriction (rid, restriction_id, kind, volume_wkt, bbox_min_x, bbox_min_y, bbox_max_x,"
              " bbox_max_y, floor_z, ceiling_m, effective_lo, effective_hi, state, authority, source_id, published_at,"
              " revoked_at, quality, sensitivity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (rid, rid_text, kind, fx.box_wkt(*box), x0, y0, x1, y1, 0.0, ceiling, effective[0], effective[1], state,
               authority, source, "2026-11-01T00:00:00Z", "2026-11-01T00:10:00Z" if state == "revoked" else None,
               quality, "restricted"))


def ground_posts(blds, box, spacing):
    """Terrain posts from building base heights (median within 80 m, else nearest); quality 'derived'."""
    pts = [((b0 + b2) / 2, (b1 + b3) / 2, b["base"]) for b, (b0, b1, b2, b3) in blds if b["base"] is not None]
    nx = int(round((box[2] - box[0]) / spacing)) + 1
    ny = int(round((box[3] - box[1]) / spacing)) + 1
    posts = []
    for ix in range(nx):
        for iy in range(ny):
            x, y = box[0] + ix * spacing, box[1] + iy * spacing
            near = [z for px, py, z in pts if (px - x) ** 2 + (py - y) ** 2 <= 80.0 ** 2]
            z = statistics.median(near) if near else min(pts, key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)[2]
            posts.append((ix, iy, x, y, round(z, 2)))
    return posts


def scenario_restrictions(n, seed, box=None, month="2026-11", days=29, hours=(1, 6)):
    """n scenario temporary restrictions centred on real building centroids inside box (default: area L)."""
    rng = random.Random(seed)
    box = box or AREAS["L"]
    centres = [((b0 + b2) / 2, (b1 + b3) / 2) for b0, b1, b2, b3 in
               (ring_bbox(b["rings"]) for b in snapshot()["buildings"] if b["rings"])]
    centres = [p for p in centres if box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]]
    out = []
    for i in range(n):
        cx, cy = rng.choice(centres)
        w, d = rng.uniform(40, 150), rng.uniform(40, 150)
        lo = rng.uniform(0, days * 86400)
        hi = lo + rng.uniform(hours[0] * 3600, hours[1] * 3600)
        start = f"{month}-01T00:00:00Z"
        if rng.random() < 0.7:
            kind, ceiling = "no_fly", (None if rng.random() < 0.5 else round(rng.uniform(80, 150), 1))
        else:
            kind, ceiling = "height_limit", round(rng.uniform(60, 100), 1)
        out.append({"id": f"SC-{i:05d}", "box": (round(cx - w / 2, 2), round(cy - d / 2, 2), round(cx + w / 2, 2), round(cy + d / 2, 2)),
                    "effective": (_shift(start, lo), _shift(start, hi)), "kind": kind, "ceiling_m": ceiling})
    return out


def _shift(iso, seconds):
    from datetime import datetime, timedelta
    t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=int(seconds))
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def build(c, area, release_id="seed", restrictions=0, seed=7, extra_air=(), first_rid=1, terrain_spacing=None):
    """Insert the real layers of `area` (S/M/L) into a fixture database; returns (boxes, stats)."""
    snap = snapshot()
    box = AREAS[area]
    rid = first_rid
    blds = [(b, ring_bbox(b["rings"])) for b in snap["buildings"] if b["rings"]]
    blds = [(b, bb) for b, bb in blds if intersects(bb, box)]
    boxes, unknown = [], 0
    for b, (x0, y0, x1, y1) in blds:
        known = b["top"] is not None and b["base"] is not None and b["top"] > b["base"]
        base = b["base"] if b["base"] is not None else 0.0
        top = b["top"] if known else UNKNOWN_TOP
        unknown += not known
        feature(c, rid, release_id, b["id"], "building", "SRC-HK-BLDG", "observed" if known else "unknown", b["name"],
                {"type": b["type"], "storeys": b["storeys"]})
        wkt = polygon_wkt(b["rings"])
        c.execute("INSERT INTO building (rid, footprint_wkt, solid_wkt, bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y, base_z,"
                  " top_z, height_m, footprint_source, height_source, height_method, is_landmark) VALUES"
                  " (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (rid, wkt, f"EXTRUDE({wkt},{base},{top})", x0, y0, x1, y1, base, top, top - base, "SRC-HK-BLDG",
                   "SRC-HK-BLDG", "measured" if known else "unknown", 1 if known and top - base > 150 else 0))
        boxes.append((x0, y0, x1, y1, top))
        rid += 1
    # real restricted flying zones (gazetted names, footprint-derived boxes)
    by_id = {b["id"]: bb for b, bb in blds}
    rfz = []
    for k, z in enumerate(snap["rfz"]):
        bbs = [by_id[i] for i in z["building_ids"] if i in by_id]
        if not bbs:
            continue
        zb = (min(b[0] for b in bbs) - RFZ_BUFFER, min(b[1] for b in bbs) - RFZ_BUFFER,
              max(b[2] for b in bbs) + RFZ_BUFFER, max(b[3] for b in bbs) + RFZ_BUFFER)
        add_airspace(c, rid, release_id, f"RFZ-{k:02d}", tuple(round(v, 2) for v in zb),
                     STUDY, source="SRC-HK-RFZ", authority="CAD", quality="derived", name=z["zone"],
                     attrs={"notice": z["notice"], "geometry": "facility footprints + 20 m; official boundary on CAD Drone Map"})
        rfz.append(z["zone"])
        rid += 1
    for spec in scenario_restrictions(restrictions, seed, box) if restrictions else []:
        add_airspace(c, rid, release_id, spec["id"], spec["box"], spec["effective"], spec["kind"], spec["ceiling_m"])
        rid += 1
    for spec in extra_air:
        add_airspace(c, rid, release_id, spec["id"], spec["box"], spec["effective"], spec.get("kind", "no_fly"),
                     spec.get("ceiling_m"), name=spec.get("name"))
        rid += 1
    # exposure: census LSG (E from density, C residential) and sensitive sites (schools, hospitals)
    zones = 0
    for z in snap["census_lsg"]:
        if not z["rings"] or z["pop"] is None:
            continue
        zb = ring_bbox(z["rings"])
        if not intersects(zb, box):
            continue
        e = round(min(1.0, z["pop"] / polygon_area(z["rings"]) / snap["density_ref"]), 3)
        _exposure(c, rid, release_id, f"LSG-{z['id']}", "residential", polygon_wkt(z["rings"]), zb, e, C_RESIDENTIAL,
                  "SRC-HK-CENSUS", {"population_2021": z["pop"]})
        rid += 1
        zones += 1
    for kind, rows, half, src in (("school", snap["schools"], SCHOOL_HALF, "SRC-HK-SCHOOL"),
                                  ("hospital", snap["hospitals"], HOSPITAL_HALF, "SRC-HK-HOSP")):
        for i, s in enumerate(sorted(rows, key=lambda r: (r["name"], r["x"], r["y"]))):
            zb = (s["x"] - half, s["y"] - half, s["x"] + half, s["y"] + half)
            if not (box[0] <= s["x"] <= box[2] and box[1] <= s["y"] <= box[3]):
                continue
            _exposure(c, rid, release_id, f"{kind[:3].upper()}-{i:03d}", kind, fx.box_wkt(*zb), zb, 1.0, C_SENSITIVE, src,
                      {"name": s["name"]})
            rid += 1
            zones += 1
    # terrain from building base heights and coverage tiles
    spacing = terrain_spacing or (50.0 if box[2] - box[0] <= 500 else 100.0)
    posts = ground_posts(blds, box, spacing)
    zs = [p[4] for p in posts]
    c.execute("INSERT INTO terrain_surface (release_id, terrain_id, surface_type, bounds_wkt, post_spacing_m, vertical_datum,"
              " flat, min_z, max_z, source_id, quality, valid_lo, valid_hi, checksum) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (release_id, "TER-HK-" + area, "grid", fx.box_wkt(*box), spacing, "HKPD", 0, min(zs), max(zs),
               "SRC-HK-DERIVED", "derived", STUDY[0], STUDY[1], fx.sha(json.dumps(posts))))
    c.executemany("INSERT INTO terrain_post (release_id, terrain_id, ix, iy, x, y, z, quality, source_id) VALUES (?,?,?,?,?,?,?,?,?)",
                  [(release_id, "TER-HK-" + area, ix, iy, x, y, z, "derived", "SRC-HK-DERIVED") for ix, iy, x, y, z in posts])
    for layer, quality in (("scene", "observed"), ("terrain", "derived"), ("airspace", "derived"), ("exposure", "derived")):
        c.execute("INSERT INTO coverage_tile (release_id, layer, tile_id, tile_x, tile_y, bounds_wkt, complete, quality,"
                  " source_id, valid_lo, valid_hi, checksum) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (release_id, layer, "T-HK-" + area, 0, 0, fx.box_wkt(*box), 1, quality, "SRC-HK-DERIVED", STUDY[0],
                   STUDY[1], fx.sha(layer + area)))
    stats = {"area": area, "bbox": box, "buildings": len(blds), "unknown_height": unknown, "rfz_zones": rfz,
             "scenario_restrictions": restrictions + len(extra_air), "exposure_zones": zones, "terrain_posts": len(posts),
             "terrain_z": [min(zs), max(zs)], "density_ref_per_m2": snap["density_ref"]}
    return boxes, stats, rid


def _exposure(c, rid, release_id, zone_id, cls, wkt, zb, e, cc, source, attrs):
    feature(c, rid, release_id, zone_id, "exposure", source, "derived", attrs.get("name"), attrs)
    c.execute("INSERT INTO exposure_zone (rid, zone_id, class, footprint_wkt, bbox_min_x, bbox_min_y, bbox_max_x, bbox_max_y,"
              " floor_z, top_z, exposure_e, consequence_c, q, risk_model_id, source_id, quality, valid_lo, valid_hi,"
              " sensitivity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (rid, zone_id, cls, wkt, *zb, 0.0, 30.0, e, cc, round(e * cc, 6), "lq-risk-v1", source, "derived",
               STUDY[0], STUDY[1], "restricted"))


def payload(cat, area, restrictions=0, seed=7, extra_air=()):
    """Layer payload for catalog.publish (same shape as the synthetic generators) plus building boxes and stats."""
    c = fx.connect()
    c.row_factory = sqlite3.Row
    fx.base(c)
    add_sources(c)
    fx.create_release(c, "seed")
    boxes, stats, _ = build(c, area, "seed", restrictions, seed, extra_air)
    out = {layer: cat.read_layer(c, "seed", layer) for layer in cat.LAYERS if layer != "sources"}
    out["sources"] = {"source": cat.normalized(cat.rows(c, "SELECT * FROM source"))}
    c.close()
    return out, boxes, stats


def free(boxes, p, pad=4.0):
    x, y, z = p
    return not any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad and z <= top + pad
                   for x0, y0, x1, y1, top in boxes)


def tasks(n, boxes, seed=11, region=None, step=20.0, day=None, hours=(0, 24), span=(4, 8)):
    """Grid-aligned start/goal pairs at FLIGHT_Z inside region (default: area S), endpoints outside buildings."""
    rng = random.Random(seed)
    region = region or AREAS["S"]
    out, tries = [], 0
    while len(out) < n:
        tries += 1
        if tries > 100000:
            raise RuntimeError("could not place tasks")
        sx = round(rng.uniform(region[0], region[2]) / step) * step
        sy = round(rng.uniform(region[1], region[3]) / step) * step
        dx = rng.choice([-1, 1]) * step * rng.randint(*span)
        dy = rng.choice([-1, 1]) * step * rng.randint(1, span[0])
        gx, gy = sx + dx, sy + dy
        if not (region[0] <= gx <= region[2] and region[1] <= gy <= region[3]):
            continue
        start, goal = (sx, sy, FLIGHT_Z), (gx, gy, FLIGHT_Z)
        if not (free(boxes, start) and free(boxes, goal)):
            continue
        d = day if day is not None else rng.randint(1, 29)
        minute = rng.randint(hours[0] * 60, hours[1] * 60 - 11)
        lo = f"2026-11-{d:02d}T{minute // 60:02d}:{minute % 60:02d}:00Z"
        hi = f"2026-11-{d:02d}T{(minute + 10) // 60:02d}:{(minute + 10) % 60:02d}:00Z"
        out.append({"start": start, "goal": goal, "window": (lo, hi)})
    return out


def distance(a, b):
    return math.dist(a, b)


def provenance(cat, window=None):
    """Catalog provenance naming the snapshot behind each layer instead of the synthetic fixture."""
    p = cat.provenance(window) if window else cat.provenance()
    tag = ACQUIRED[:10]
    p["source_versions"] = {"scene": f"hk-landsd-building@{tag}", "terrain": f"hk-derived-from-base-height@{tag}",
                            "airspace": f"hk-cad-gn8002@{tag}+scenario", "exposure": f"hk-census2021-edb-ha@{tag}",
                            "sources": f"hk-snapshot@{tag}"}
    p["compiler_version"] = "hk-loader-1"
    return p


def building_centres(area):
    box = AREAS[area]
    out = []
    for b in snapshot()["buildings"]:
        if b["rings"]:
            x0, y0, x1, y1 = ring_bbox(b["rings"])
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                out.append((cx, cy))
    return out


def rfz_boxes(area):
    """[(zone name, box)] for gazetted restricted flying zones with footprints inside area."""
    box = AREAS[area]
    by_id = {b["id"]: ring_bbox(b["rings"]) for b in snapshot()["buildings"] if b["rings"]}
    out = []
    for z in snapshot()["rfz"]:
        bbs = [by_id[i] for i in z["building_ids"] if i in by_id and intersects(by_id[i], box)]
        if bbs:
            out.append((z["zone"], (min(b[0] for b in bbs) - RFZ_BUFFER, min(b[1] for b in bbs) - RFZ_BUFFER,
                                    max(b[2] for b in bbs) + RFZ_BUFFER, max(b[3] for b in bbs) + RFZ_BUFFER)))
    return out
