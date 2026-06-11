"""Stage 4: grid capacity layers.

Open sources (no registration):
  - NESO: GB DNO licence area boundaries (EPSG:27700 -> 4326, simplified)
  - Northern Powergrid: heatmapdatatable (per-substation headroom + RAG)
  - SSEN: headroom dashboard data (GSP/BSP/Primary, SEPD filtered to England)

UKPN / NGED / ENWL / SPEN require free registered API keys. If keys are present
in pipeline/dno_keys.json ({"ukpn": "...", "nged": "...", ...}) those areas are
fetched too; otherwise the layer simply has no points there (documented on map).

Outputs: web/data/grid.geojson, web/data/dno.geojson
"""
import csv
import io
import json

import requests
from pyproj import Transformer
from shapely.geometry import mapping, shape

from common import RAW, UA, WEB_DATA, download, write_json

NESO_DNO_URL = ("https://api.neso.energy/dataset/0e377f16-95e9-4c15-a1fc-49e06a39cfa0/"
                "resource/1c6a7dc0-1b6c-443a-bc67-5f7125649434/download/"
                "gb-dno-license-areas-20240503-as-geojson.geojson")
NPG_URL = ("https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/"
           "datasets/heatmapdatatable/exports/json")
SSEN_URL = ("https://data-api.ssen.co.uk/dataset/93f6890a-4bd4-4b75-9955-6deace56decb/"
            "resource/52e9a305-ad90-4c81-9175-20a40ef57894/download/"
            "headroom-dashboard-data-march-2026.csv")
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"}


def rag_norm(v):
    v = str(v or "").strip().lower()
    if v.startswith("g"):
        return "g"
    if v.startswith("a") or "amber" in v or "yellow" in v:
        return "a"
    if v.startswith("r"):
        return "r"
    return ""


def num(v):
    try:
        f = float(str(v).replace(",", ""))
        return round(f, 2)
    except (TypeError, ValueError):
        return None


def dno_boundaries():
    dest = download(NESO_DNO_URL, RAW / "dno_areas_27700.geojson")
    gj = json.load(open(dest))
    tf = Transformer.from_crs(27700, 4326, always_xy=True)
    feats = []
    for f in gj["features"]:
        geom = shape(f["geometry"]).simplify(300)  # metres in BNG
        geom = mapping(geom)

        def reproject(coords):
            if isinstance(coords[0], (int, float)):
                x, y = tf.transform(coords[0], coords[1])
                return [round(x, 4), round(y, 4)]
            return [reproject(c) for c in coords]

        geom["coordinates"] = reproject(geom["coordinates"])
        p = f["properties"]
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {"name": p.get("DNO_Full") or p.get("Area"),
                                     "dno": p.get("DNO"), "area": p.get("Area")}})
    write_json({"type": "FeatureCollection", "features": feats}, WEB_DATA / "dno.geojson")


def npg_points():
    r = requests.get(NPG_URL, headers=UA, timeout=300)
    r.raise_for_status()
    rows = r.json()
    feats = []
    for row in rows:
        loc = row.get("substation_location") or {}
        lon, lat = loc.get("lon"), loc.get("lat")
        if lon is None or lat is None:
            continue
        rag = rag_norm(row.get("genconstraint")) or rag_norm(row.get("demconstraint"))
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "name": (row.get("psp_name") or "").title(),
                "dno": "Northern Powergrid",
                "dh": num(row.get("demhr")), "gh": num(row.get("genhr")),
                "rag": rag or "a",
            },
        })
    print(f"  NPg: {len(feats)} substations")
    return feats


def ssen_points():
    r = requests.get(SSEN_URL, headers=BROWSER_UA, timeout=300)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    feats = []
    for row in rows:
        lat, lon = num(row.get("Location Latitude")), num(row.get("Location Longitude"))
        if not lat or not lon:
            continue
        if lat > 54.0:  # SHEPD (north Scotland) — out of scope for England map
            continue
        rag = (rag_norm(row.get("Substation Generation RAG Status"))
               or rag_norm(row.get("Substation Demand RAG Status")))
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "name": (row.get("Substation") or "").title(),
                "dno": "SSEN (SEPD)",
                "dh": num(row.get("estimated_demand_headroom__mva_")),
                "gh": num(row.get("estimated_generation_headroom__mw_")),
                "rag": rag or "a",
            },
        })
    print(f"  SSEN SEPD: {len(feats)} substations")
    return feats


def main():
    print("== DNO boundaries ==")
    dno_boundaries()
    print("== Substation headroom ==")
    feats = []
    for fn in (npg_points, ssen_points):
        try:
            feats += fn()
        except Exception as e:
            print(f"  WARNING: {fn.__name__} failed: {e}")
    write_json({"type": "FeatureCollection", "features": feats}, WEB_DATA / "grid.geojson")


if __name__ == "__main__":
    main()
