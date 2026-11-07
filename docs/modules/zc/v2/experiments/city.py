"""Synthetic city for ZC v2 experiments, published through the real ZQO/LQ services.

Area 3 km x 3 km; N buildings; 100 airspace restrictions in November 2026;
a 10 x 10 exposure partition (300 m cells) with three hard-threshold hot cells.
All values are synthetic.
"""
import random
import sqlite3

import planner_io as io

cat = io.cat
import fixtures as fx  # noqa: E402  (on sys.path via catalog)
import governance as gov  # noqa: E402  LQ governance service

AREA = 3000.0
STEP = io.CONFIG["step_m"]
FLIGHT_Z = 100.0


def payload(n_buildings, seed=7, restrictions=100, extra_air=()):
    rng = random.Random(seed)
    c = fx.connect()
    c.row_factory = sqlite3.Row
    fx.base(c)
    fx.create_release(c, "seed")
    rid = 1
    boxes = []
    for i in range(n_buildings):
        w, d = rng.uniform(10, 30), rng.uniform(10, 30)
        x, y = rng.uniform(0, AREA - w), rng.uniform(0, AREA - d)
        top = rng.uniform(20, 100) if rng.random() < 0.9 else rng.uniform(100, 200)
        fx.add_building(c, rid, "seed", f"B-{i:05d}", (round(x, 2), round(y, 2), round(x + w, 2), round(y + d, 2)),
                        0.0, round(top, 2))
        boxes.append((x, y, x + w, y + d, top))
        rid += 1
    for i in range(restrictions):
        w, d = rng.uniform(40, 150), rng.uniform(40, 150)
        x, y = rng.uniform(0, AREA - w), rng.uniform(0, AREA - d)
        lo = 26265600 + rng.uniform(0, 29 * 86400)
        hi = lo + rng.uniform(3600, 6 * 3600)
        if rng.random() < 0.7:
            kind, ceiling = "no_fly", (None if rng.random() < 0.5 else round(rng.uniform(80, 150), 1))
        else:
            kind, ceiling = "height_limit", round(rng.uniform(60, 100), 1)
        fx.add_airspace(c, rid, "seed", f"NF-{i:03d}", (round(x, 2), round(y, 2), round(x + w, 2), round(y + d, 2)),
                        (fx.at(int(lo)), fx.at(int(hi))), kind=kind, ceiling_m=ceiling)
        rid += 1
    for spec in extra_air:
        fx.add_airspace(c, rid, "seed", spec["id"], spec["box"], spec["effective"], kind=spec.get("kind", "no_fly"),
                        ceiling_m=spec.get("ceiling_m"))
        rid += 1
    hot = {(2, 7), (6, 3), (8, 8)}
    for i in range(10):
        for j in range(10):
            e, cc = (1.0, 0.95) if (i, j) in hot else (round(rng.uniform(0.1, 0.9), 2), round(rng.uniform(0.1, 0.9), 2))
            fx.add_exposure(c, rid, "seed", f"G-{i}-{j}", (i * 300.0, j * 300.0, i * 300.0 + 300, j * 300.0 + 300), e, cc)
            rid += 1
    cat.insert(c, "terrain_surface", dict(release_id="seed", terrain_id="TER-1", surface_type="grid",
               bounds_wkt=fx.box_wkt(0, 0, AREA, AREA), post_spacing_m=300.0, vertical_datum="local-z0", flat=1,
               min_z=0.0, max_z=0.0, source_id="SRC-SYN", quality="assumed", valid_lo=cat.WIN[0],
               valid_hi=cat.WIN[1], checksum=cat.digest("flat")))
    for ix in range(11):
        for iy in range(11):
            cat.insert(c, "terrain_post", dict(release_id="seed", terrain_id="TER-1", ix=ix, iy=iy, x=ix * 300.0,
                       y=iy * 300.0, z=0.0, quality="assumed", source_id="SRC-SYN"))
    for layer in cat.LAYERS[:-1]:
        cat.insert(c, "coverage_tile", dict(release_id="seed", layer=layer, tile_id="T-0", tile_x=0, tile_y=0,
                   bounds_wkt=fx.box_wkt(0, 0, AREA, AREA), complete=1, quality="assumed", source_id="SRC-SYN",
                   valid_lo=cat.WIN[0], valid_hi=cat.WIN[1], checksum=cat.digest(layer)))
    out = {layer: cat.read_layer(c, "seed", layer) for layer in cat.LAYERS if layer != "sources"}
    out["sources"] = {"source": cat.rows(c, "SELECT * FROM source")}
    c.close()
    return out, boxes


def database(path, pl, release_id="R0"):
    """Create a WAL database, seed LQ actors, publish R0 and compile its validated risk dataset."""
    cat.initialize(path)
    c = cat.connect(path)
    gov.seed(c)
    cat.publish(c, pl, request_id="req-" + release_id, release_id=release_id, expected=None,
                provenance=cat.provenance())
    gov.compile_dataset(c, release_id, "D-" + release_id)
    return c


def next_release(c, pl, release_id, expected):
    cat.publish(c, pl, request_id="req-" + release_id, release_id=release_id, expected=expected,
                provenance=cat.provenance())
    gov.compile_dataset(c, release_id, "D-" + release_id)


def free(boxes, p, pad=4.0):
    x, y, z = p
    return not any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad and z <= top + pad
                   for x0, y0, x1, y1, top in boxes)


def tasks(n, boxes, seed=11, region=(200.0, 2800.0), day=None, hours=(0, 24)):
    """Random grid-aligned start/goal 160-260 m apart at the flight level, endpoints outside buildings."""
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        sx = round(rng.uniform(*region) / STEP) * STEP
        sy = round(rng.uniform(*region) / STEP) * STEP
        dx, dy = rng.choice([-1, 1]) * STEP * rng.randint(6, 12), rng.choice([-1, 1]) * STEP * rng.randint(2, 7)
        start, goal = (sx, sy, FLIGHT_Z), (sx + dx, sy + dy, FLIGHT_Z)
        if not (free(boxes, start) and free(boxes, goal)):
            continue
        d = day if day is not None else rng.randint(1, 29)
        minute = rng.randint(hours[0] * 60, hours[1] * 60 - 11)
        lo = f"2026-11-{d:02d}T{minute // 60:02d}:{minute % 60:02d}:00Z"
        hi_min = minute + 10
        hi = f"2026-11-{d:02d}T{hi_min // 60:02d}:{hi_min % 60:02d}:00Z"
        out.append({"start": start, "goal": goal, "window": (lo, hi)})
    return out
