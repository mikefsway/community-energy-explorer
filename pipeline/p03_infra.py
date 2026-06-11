"""Stage 3: community infrastructure.

  A. Charity Commission bulk extract -> registered charities per LSOA (via postcode),
     plus energy-named community charities appended to the orgs layer.
  B. OpenStreetMap Overpass -> community venues (community centres, village halls,
     social centres) as a point layer.

Outputs: data/processed/charity_lsoa_counts.csv, data/processed/infra_points.csv,
         web/data/infra.geojson, data/processed/cc_energy_orgs.csv
"""
import io
import json
import re
import zipfile

import pandas as pd
import requests

from common import PROCESSED, RAW, UA, WEB_DATA, download, write_json

CC_URL = "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.charity.zip"
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_Q = """
[out:json][timeout:900];
area["ISO3166-2"="GB-ENG"][admin_level=4]->.eng;
nwr["amenity"~"^(community_centre|village_hall|social_centre)$"](area.eng);
out center tags;
"""

ENERGY_NAME = re.compile(r"\benergy\b", re.I)
ENERGY_QUAL = re.compile(r"\b(communit|renewab|solar|hydro|wind|low.?carbon|sustainab)", re.I)


def charities():
    dest = download(CC_URL, RAW / "cc_charity.zip")
    with zipfile.ZipFile(dest) as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), sep="\t",
                             dtype=str, quoting=3, on_bad_lines="skip")
    print(f"  charity extract: {len(df)} rows, cols: {list(df.columns)[:8]}...")
    main = df[(df["linked_charity_number"].astype(float) == 0)
              & df["charity_registration_status"].str.strip().eq("Registered")].copy()
    main["pc"] = (main["charity_contact_postcode"].fillna("")
                  .str.upper().str.replace(" ", "", regex=False))
    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["pcds", "lsoa", "lat", "long"], dtype=str)
    pc["key"] = pc["pcds"].str.replace(" ", "", regex=False).str.upper()
    pc = pc.drop_duplicates("key").set_index("key")
    main = main.join(pc, on="pc")
    located = main.dropna(subset=["lsoa"])
    print(f"  charities: {len(main)} registered, {len(located)} located in England")

    located["lsoa"].value_counts().rename("charities").rename_axis("lsoa") \
        .to_csv(PROCESSED / "charity_lsoa_counts.csv")

    en = located[located["charity_name"].str.contains(ENERGY_NAME, na=False)
                 & located["charity_name"].str.contains(ENERGY_QUAL, na=False)]
    en[["charity_name", "pc", "lsoa", "lat", "long"]].to_csv(
        PROCESSED / "cc_energy_orgs.csv", index=False)
    print(f"  energy-named community charities: {len(en)}")


def osm_venues():
    cache = RAW / "osm_venues.json"
    if cache.exists():
        data = json.load(open(cache))
    else:
        print("  querying Overpass (England community venues)...")
        r = requests.post(OVERPASS, data={"data": OVERPASS_Q}, headers=UA, timeout=1200)
        r.raise_for_status()
        data = r.json()
        json.dump(data, open(cache, "w"))
    feats, rows = [], []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None:
            continue
        kind = tags.get("amenity", "")
        if tags.get("community_centre") == "village_hall":
            kind = "village_hall"
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {"name": tags.get("name", ""), "kind": kind},
        })
        rows.append({"lat": lat, "lon": lon, "lsoa": ""})
    print(f"  OSM venues: {len(feats)}")
    write_json({"type": "FeatureCollection", "features": feats}, WEB_DATA / "infra.geojson")
    pd.DataFrame(rows).to_csv(PROCESSED / "infra_points.csv", index=False)


if __name__ == "__main__":
    print("== Charity Commission ==")
    charities()
    print("== OSM community venues ==")
    osm_venues()
