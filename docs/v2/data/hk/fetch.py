"""Fetch a Kowloon snapshot of Hong Kong government open data for the v2 experiments.

    python3 docs/v2/data/hk/fetch.py            # writes docs/v2/data/hk/snapshot/*.json.gz and manifest.json

Sources (DATA.GOV.HK / CSDI terms: free use with attribution to the Government of the HKSAR and the
data provider; see README.md):
  - Lands Department, "Building" (CSDI landsd_rcd_1637211194312_35158): footprints, base/top height (mPD)
  - Census and Statistics Department, "2021 Population Census (Statistics and Boundaries of Large Subunit
    Groups)" (CSDI censtatd_rcd_1635933282224_58228): LSG boundaries and total population
  - Education Bureau, "School Location and Information" (all CSDI layers of the data.gov.hk package)
  - Hospital Authority, "List of Hospital Authority Hospitals/Institutions" (facility-hosp.json), converted to
    HK1980 Grid with the Geodetic Survey Section's official transformation service
  - Civil Aviation Department, restricted flying zones under the Small Unmanned Aircraft Order (Cap. 448G),
    G.N. 8002 (in force 19 December 2025): Kowloon facilities matched to Lands Department building footprints

Coordinates are HK1980 Grid (EPSG:2326), metres; heights are metres above Hong Kong Principal Datum (mPD).
"""
import gzip
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "snapshot"
CSDI = "https://portal.csdi.gov.hk/server/rest/services/common/{}/FeatureServer/0/query"
BUILDING = "landsd_rcd_1637211194312_35158"
CENSUS = "censtatd_rcd_1635933282224_58228"
SCHOOL_PACKAGE = "hk-edb-schinfo-school-location-and-information"
HOSPITALS = "https://www.ha.org.hk/opendata/facility-hosp.json"
GEODETIC = "https://www.geodetic.gov.hk/transform/v2/"
CENTRE = (835450.0, 820050.0)          # Mong Kok MTR station, Nathan Road (from Lands Department footprints)
# Nested squares (side, m) around CENTRE, sized to about 200 / 2,400 / 10,000 towers and podiums.
AREAS = {"S": 250.0, "M": 1100.0, "L": 3300.0}


def area_bbox(name):
    h = AREAS[name] / 2
    return (CENTRE[0] - h, CENTRE[1] - h, CENTRE[0] + h, CENTRE[1] + h)


# Kowloon restricted flying zones listed in G.N. 8002 (section 19(3), in force all day) -> name prefixes of
# buildings in the Lands Department layer. Zones without a matching footprint are recorded as unmatched.
RFZ = {
    "Mong Kok Police Station": ["MONG KOK POLICE STATION"],
    "Yau Ma Tei Police Station": ["YAU MA TEI POLICE STATION"],
    "Ex-Yau Ma Tei Police Station": ["FORMER YAU MA TEI POLICE STATION", "OLD YAU MA TEI POLICE STATION"],
    "Tsim Sha Tsui Police Station": ["TSIM SHA TSUI POLICE STATION"],
    "Kowloon West Regional Headquarters": ["KOWLOON WEST REGIONAL HEADQUARTERS", "KOWLOON WEST REGIONAL POLICE HEADQUARTERS"],
    "Sham Shui Po Police Station": ["SHAM SHUI PO POLICE STATION"],
    "Cheung Sha Wan Police Station": ["CHEUNG SHA WAN POLICE STATION"],
    "Kowloon City Police Station": ["KOWLOON CITY POLICE STATION"],
    "Kowloon City Headquarters and Hung Hom Divisional Police Station": ["KOWLOON CITY DISTRICT HEADQUARTERS AND HUNG HOM DIVISIONAL POLICE STATION"],
    "West Kowloon Law Courts Building": ["WEST KOWLOON LAW COURTS BUILDING"],
    "Kowloon City Law Courts Building": ["KOWLOON CITY LAW COURTS BUILDING"],
    "Gun Club Hill Barracks": ["GUN CLUB HILL BARRACKS"],
    "China Ferry Terminal Control Point": ["CHINA HONG KONG CITY", "CHINA FERRY TERMINAL"],
    "Express Rail Link West Kowloon Control Point": ["HONG KONG WEST KOWLOON STATION", "WEST KOWLOON STATION"],
    "Ocean Terminal": ["OCEAN TERMINAL"],
    "Traffic Kowloon West Operational Base": ["TRAFFIC KOWLOON WEST"],
    "Shek Kip Mei Operational Base": ["SHEK KIP MEI OPERATIONAL BASE"],
    "Ma Tau Kok Detention Centre": ["MA TAU KOK DETENTION CENTRE"],
}


def get(url, params=None, tries=4):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SkyRoute-course-project/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:  # noqa: BLE001  network retry
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def arcgis(dataset, bbox, fields, where="1=1", page=2000):
    """All features intersecting bbox, geometry in EPSG:2326, paged by OBJECTID."""
    out, offset = [], 0
    while True:
        params = {"where": where, "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
                  "inSR": 2326, "outSR": 2326, "spatialRel": "esriSpatialRelIntersects", "outFields": ",".join(fields),
                  "returnGeometry": "true", "geometryPrecision": 2, "orderByFields": "OBJECTID",
                  "resultOffset": offset, "resultRecordCount": page, "f": "json"}
        d = json.loads(get(CSDI.format(dataset), params))
        if "error" in d:
            raise RuntimeError(f"{dataset}: {d['error']}")
        feats = d.get("features", [])
        out.extend(feats)
        print(f"  {dataset}: {len(out)}", file=sys.stderr)
        if not d.get("exceededTransferLimit") and len(feats) < page:
            return out, CSDI.format(dataset), params
        offset += len(feats)


def num(v):
    try:
        return None if v in (None, "", "-") else float(v)
    except (TypeError, ValueError):
        return None


def buildings(bbox):
    fields = ["OBJECTID", "BuildingCSUID", "BuildingBlockType", "Status", "BuildingNameEN", "BaseHeight", "TopHeight",
              "Storeys", "DateStamp"]
    feats, url, params = arcgis(BUILDING, bbox, fields, where="Status='Active'")
    rows = []
    for f in feats:
        a, g = f["attributes"], f.get("geometry") or {}
        rows.append({"id": a["BuildingCSUID"], "type": a["BuildingBlockType"], "name": a["BuildingNameEN"],
                     "base": num(a["BaseHeight"]), "top": num(a["TopHeight"]), "storeys": a["Storeys"],
                     "date": a["DateStamp"], "rings": g.get("rings", [])})
    return rows, url, params


def census(bbox):
    feats, url, params = arcgis(CENSUS, bbox, ["OBJECTID", "lsbg", "t_pop"])
    return [{"id": f["attributes"]["lsbg"], "pop": num(f["attributes"]["t_pop"]),
             "rings": (f.get("geometry") or {}).get("rings", [])} for f in feats], url, params


def schools(bbox):
    pkg = json.loads(get("https://data.gov.hk/en-data/api/3/action/package_show", {"id": SCHOOL_PACKAGE}))["result"]
    ids = sorted({urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query).get("datasetId", [None])[0]
                  for r in pkg["resources"]} - {None})
    rows, seen = [], set()
    for ds in ids:
        feats, _, _ = arcgis(ds, bbox, ["OBJECTID", "NameEN", "SchoolLevelEN", "Easting", "Northing"])
        for f in feats:
            a = f["attributes"]
            key = (a["NameEN"], a["Easting"], a["Northing"])
            if key in seen or a["Easting"] is None:
                continue
            seen.add(key)
            rows.append({"name": a["NameEN"], "level": a["SchoolLevelEN"], "x": a["Easting"], "y": a["Northing"], "dataset": ds})
    return rows, ids


def hospitals(bbox):
    rows = []
    for h in json.loads(get(HOSPITALS)):
        t = json.loads(get(GEODETIC, {"inSys": "wgsgeog", "outSys": "hkgrid", "lat": h["latitude"], "long": h["longitude"]}))
        x, y = t["hkE"], t["hkN"]
        if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
            rows.append({"name": h["institution_eng"], "ae": h["with_AE_service_eng"], "x": x, "y": y})
    return rows


def rfz(blds):
    named = [(b["name"].strip().upper(), b["id"]) for b in blds if b["name"]]
    zones = []
    for zone, prefixes in RFZ.items():
        hits = [(n, i) for n, i in named if any(n.startswith(p) for p in prefixes)]
        zones.append({"zone": zone, "notice": "G.N. 8002 (Cap. 448G s.19(3)), in force 2025-12-19",
                      "matched_names": sorted({n for n, _ in hits}), "building_ids": sorted({i for _, i in hits})})
    return zones


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    path = OUT / f"{name}.json.gz"
    path.write_bytes(gzip.compress(raw, mtime=0))
    return {"file": f"snapshot/{path.name}", "records": len(data), "sha256_json": hashlib.sha256(raw).hexdigest()}


def main():
    bbox = area_bbox("L")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("buildings", file=sys.stderr)
    blds, burl, bparams = buildings(bbox)
    print("census", file=sys.stderr)
    lsg, curl, cparams = census(bbox)
    print("schools", file=sys.stderr)
    sch, sch_ids = schools(bbox)
    print("hospitals", file=sys.stderr)
    hos = hospitals(bbox)
    zones = rfz(blds)
    manifest = {
        "retrieved_at": started, "crs": "EPSG:2326 (HK1980 Grid), metres", "vertical_datum": "Hong Kong Principal Datum (mPD)",
        "centre": CENTRE, "areas": {k: area_bbox(k) for k in AREAS}, "extent": bbox,
        "licence": "DATA.GOV.HK Terms and Conditions: free use with source identified and attribution to the Government "
                   "of the HKSAR and the providing organisation",
        "layers": {
            "buildings": {**write("buildings", blds), "provider": "Lands Department", "url": burl,
                          "query": {k: v for k, v in bparams.items() if k not in ("resultOffset",)}},
            "census_lsg": {**write("census_lsg", lsg), "provider": "Census and Statistics Department (2021 Population Census)",
                           "url": curl, "query": {k: v for k, v in cparams.items() if k not in ("resultOffset",)}},
            "schools": {**write("schools", sch), "provider": "Education Bureau", "csdi_datasets": sch_ids},
            "hospitals": {**write("hospitals", hos), "provider": "Hospital Authority", "url": HOSPITALS,
                          "transform": GEODETIC + " (wgsgeog -> hkgrid)"},
            "rfz": {**write("rfz", zones), "provider": "Civil Aviation Department (gazetted names); footprints from Lands Department",
                    "notice": "https://www.cad.gov.hk/documents/G.N.8002_E.pdf"},
        },
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v["records"] for k, v in manifest["layers"].items()}), file=sys.stderr)


if __name__ == "__main__":
    main()
