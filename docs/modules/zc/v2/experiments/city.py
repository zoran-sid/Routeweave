"""Kowloon city for ZC v2 experiments, from Hong Kong open data, published through the real ZQO/LQ services.

Nested areas around Mong Kok MTR station (docs/v2/data/hk): S 250 m, M 1.1 km, L 3.3 km squares with about
200 / 2,400 / 10,000 real buildings. Buildings, census exposure, schools, hospitals and gazetted restricted
flying zones are real; terrain is derived from building base heights; the 100 temporary restrictions per release
are scenario rows placed on real building locations (see hk.scenario_restrictions). Coordinates: HK1980 Grid.
"""
import sys

import planner_io as io

cat = io.cat
sys.path.insert(0, str(io.ROOT / "docs/v2/data/hk"))
import hk  # noqa: E402
import governance as gov  # noqa: E402  LQ governance service

AREAS = hk.AREAS
STEP = io.CONFIG["step_m"]
FLIGHT_Z = hk.FLIGHT_Z


def payload(area, seed=7, restrictions=100, extra_air=()):
    """Real layers of area S/M/L plus `restrictions` scenario rows; returns (payload, building boxes, stats)."""
    return hk.payload(cat, area, restrictions=restrictions, seed=seed, extra_air=extra_air)


def database(path, pl, release_id="R0"):
    """Create a WAL database, seed LQ actors and the HK sources, publish R0 and compile its validated risk dataset."""
    cat.initialize(path)
    c = cat.connect(path)
    gov.seed(c)
    with c:
        hk.add_sources(c)
    cat.publish(c, pl, request_id="req-" + release_id, release_id=release_id, expected=None,
                provenance=hk.provenance(cat))
    gov.compile_dataset(c, release_id, "D-" + release_id)
    return c


def next_release(c, pl, release_id, expected):
    cat.publish(c, pl, request_id="req-" + release_id, release_id=release_id, expected=expected,
                provenance=hk.provenance(cat))
    gov.compile_dataset(c, release_id, "D-" + release_id)


def free(boxes, p, pad=4.0):
    return hk.free(boxes, p, pad)


def tasks(n, boxes, seed=11, region=None, day=None, hours=(0, 24)):
    """Grid-aligned start/goal 80-160 m apart at FLIGHT_Z (mPD) inside region (default: area S)."""
    return hk.tasks(n, boxes, seed=seed, region=region, step=STEP, day=day, hours=hours)
