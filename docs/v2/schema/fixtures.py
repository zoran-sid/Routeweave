"""Helpers that load the v2 unified schema and insert valid synthetic rows.

Used by test_schema.py and by member experiments. All data is synthetic.
Times are UTC strings in the fixed format YYYY-MM-DDTHH:MM:SSZ.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.sql"
OP_A_PATH = HERE / "op_a.sql"
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
LAYERS = ("scene", "terrain", "airspace", "exposure", "sources")


def sha(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def at(seconds_from_epoch):
    """ISO time for a number of seconds after 2026-01-01T00:00:00Z."""
    return iso(EPOCH + timedelta(seconds=seconds_from_epoch))


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def op_a_sql():
    return OP_A_PATH.read_text(encoding="utf-8")


def add_actor(conn, actor_id="A-ADMIN", role="airspace_admin"):
    conn.execute(
        "INSERT INTO actor VALUES (?,?,?,?,?)",
        (actor_id, role, "SYN", 1, "2026-11-01T00:00:00Z"),
    )


def add_source(conn, source_id="SRC-SYN", source_type="synthetic"):
    conn.execute(
        "INSERT INTO source (source_id, name, source_type, owner_org, license,"
        " acquisition_method, acquired_at, update_frequency, sensitivity)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (source_id, "synthetic", source_type, "SYN", "CC0-1.0 (synthetic)",
         "generated", "2026-11-01T00:00:00Z", "event", "internal"),
    )


def add_risk_model(conn, risk_model_id="lq-risk-v1", actor_id="A-ADMIN", source_id="SRC-SYN"):
    conn.execute(
        "INSERT INTO risk_model (risk_model_id, model_version, name, formula, params,"
        " valid_lo, valid_hi, source_id, status, approved_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (risk_model_id, "1.0.0", "synthetic exposure proxy", "q = E * C",
         json.dumps({"hard_q": 0.9}), "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z",
         source_id, "approved", actor_id),
    )


def create_release(conn, release_id, base_release_id=None, actor_id="A-ADMIN"):
    conn.execute(
        "INSERT INTO release (release_id, scene_id, schema_version, baseline, status,"
        " base_release_id, valid_lo, valid_hi, created_at, actor_id, content_hash, manifest)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (release_id, "syn-district", "v2-schema-0.1", "starter-v0", "draft",
         base_release_id, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z",
         "2026-11-01T00:00:00Z", actor_id, sha(release_id), json.dumps({"release": release_id})),
    )


def add_layers(conn, release_id, complete=True):
    for layer in LAYERS:
        conn.execute(
            "INSERT INTO release_layer VALUES (?,?,?,?,?,?,?)",
            (release_id, layer, f"{layer}-{release_id}", sha(release_id + layer), 0,
             "2026-11-01T00:00:00Z", 1 if complete else 0),
        )


def publish(conn, release_id, published_at="2026-11-01T00:05:00Z"):
    conn.execute(
        "UPDATE release SET status = 'published', published_at = ? WHERE release_id = ?",
        (published_at, release_id),
    )


def add_feature(conn, rid, release_id, feature_id, feature_type, source_id="SRC-SYN"):
    layer = {"building": "scene", "airspace": "airspace", "exposure": "exposure"}[feature_type]
    geom_kind = "polygon" if feature_type == "exposure" else "polyhedral"
    conn.execute(
        "INSERT INTO feature (rid, release_id, feature_id, layer, feature_type, source_id,"
        " quality, valid_lo, valid_hi, recorded_at, sensitivity, geom_kind)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, release_id, feature_id, layer, feature_type, source_id, "assumed",
         "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "2026-11-01T00:00:00Z",
         "restricted" if feature_type != "building" else "internal", geom_kind),
    )


def box_wkt(x0, y0, x1, y1):
    return f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"


def add_building(conn, rid, release_id, feature_id, box, base_z, top_z, source_id="SRC-SYN"):
    add_feature(conn, rid, release_id, feature_id, "building", source_id)
    x0, y0, x1, y1 = box
    conn.execute(
        "INSERT INTO building (rid, footprint_wkt, solid_wkt, bbox_min_x, bbox_min_y,"
        " bbox_max_x, bbox_max_y, base_z, top_z, height_m, footprint_source, height_source,"
        " height_method, is_landmark) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, box_wkt(*box), f"EXTRUDE({box_wkt(*box)},{base_z},{top_z})", x0, y0, x1, y1,
         base_z, top_z, top_z - base_z, source_id, source_id, "assumed", 0),
    )


def add_airspace(conn, rid, release_id, restriction_id, box, effective, kind="no_fly",
                 floor_z=0.0, ceiling_m=None, state="published", source_id="SRC-SYN"):
    add_feature(conn, rid, release_id, restriction_id, "airspace", source_id)
    x0, y0, x1, y1 = box
    lo, hi = effective
    conn.execute(
        "INSERT INTO airspace_restriction (rid, restriction_id, kind, volume_wkt, bbox_min_x,"
        " bbox_min_y, bbox_max_x, bbox_max_y, floor_z, ceiling_m, effective_lo, effective_hi,"
        " state, authority, source_id, published_at, revoked_at, quality, sensitivity)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, restriction_id, kind, box_wkt(*box), x0, y0, x1, y1, floor_z, ceiling_m, lo, hi,
         state, "synthetic", source_id, "2026-11-01T00:00:00Z",
         "2026-11-01T00:10:00Z" if state == "revoked" else None, "assumed", "restricted"),
    )


def add_exposure(conn, rid, release_id, zone_id, box, e, c, risk_model_id="lq-risk-v1",
                 source_id="SRC-SYN", q=None):
    add_feature(conn, rid, release_id, zone_id, "exposure", source_id)
    x0, y0, x1, y1 = box
    conn.execute(
        "INSERT INTO exposure_zone (rid, zone_id, class, footprint_wkt, bbox_min_x, bbox_min_y,"
        " bbox_max_x, bbox_max_y, floor_z, top_z, exposure_e, consequence_c, q, risk_model_id,"
        " source_id, quality, valid_lo, valid_hi, sensitivity)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, zone_id, "residential", box_wkt(*box), x0, y0, x1, y1, 0.0, 30.0, e, c,
         e * c if q is None else q, risk_model_id, source_id, "assumed",
         "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "restricted"),
    )


def base(conn):
    """Actor, source and approved risk model shared by most fixtures."""
    add_actor(conn)
    add_source(conn)
    add_risk_model(conn)
