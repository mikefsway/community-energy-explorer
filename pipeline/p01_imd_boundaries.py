"""Stage 1: IMD 2025, LSOA21/LAD24 boundaries, ONS postcode directory.

Outputs (data/processed/):
  imd.csv             trimmed IMD2025 per LSOA21
  lsoa_geo.jsonl      one GeoJSON feature per line (EPSG:4326, rounded), England only
  lad_geo.json        LAD24 FeatureCollection, England only
  postcode_lookup.csv pcds,lat,long,lsoa21,lad  (live + recently terminated England postcodes)
"""
import csv
import io
import json
import sys
import zipfile

import pandas as pd
import requests

from common import RAW, PROCESSED, UA, download, round_coords

IMD_URL = "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
LSOA_FS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0/query"
LAD_FS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/Local_Authority_Districts_May_2024_Boundaries_UK_BUC/FeatureServer/0/query"
ONSPD_URL = "https://www.arcgis.com/sharing/rest/content/items/3635ca7f69df4733af27caf86473ffa1/data"


def fetch_imd():
    dest = download(IMD_URL, RAW / "iod2025_file7.csv")
    df = pd.read_csv(dest)
    cols = {
        "LSOA code (2021)": "lsoa",
        "LSOA name (2021)": "lsoa_name",
        "Local Authority District code (2024)": "lad",
        "Local Authority District name (2024)": "lad_name",
        "Index of Multiple Deprivation (IMD) Score": "imd_score",
        "Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)": "imd_rank",
        "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": "imd_decile",
        "Income Score (rate)": "income_score",
        "Income Decile (where 1 is most deprived 10% of LSOAs)": "income_decile",
        "Employment Decile (where 1 is most deprived 10% of LSOAs)": "employment_decile",
        "Total population: mid 2022 (excluding prisoners)": "pop",
    }
    # column headers occasionally differ in small ways; match defensively
    resolved = {}
    for want, short in cols.items():
        match = [c for c in df.columns if c.strip().lower() == want.lower()]
        if not match:
            match = [c for c in df.columns if want.split("(")[0].strip().lower() in c.lower()]
        if match:
            resolved[match[0]] = short
        else:
            print(f"  WARNING: column not found: {want}")
    out = df[list(resolved)].rename(columns=resolved)
    out.to_csv(PROCESSED / "imd.csv", index=False)
    print(f"  imd.csv: {len(out)} LSOAs, {out['lad'].nunique()} LADs")
    return out


def fetch_featureserver(base_url, out_fields, code_field, england_prefixes, ndigits=5):
    feats, offset = [], 0
    while True:
        params = {
            "where": "1=1", "outFields": out_fields, "outSR": "4326",
            "f": "geojson", "resultOffset": offset, "resultRecordCount": 2000,
        }
        r = requests.get(base_url, params=params, headers=UA, timeout=300)
        r.raise_for_status()
        page = r.json()
        got = page.get("features", [])
        if not got:
            break
        for f in got:
            code = f["properties"].get(code_field, "")
            if any(code.startswith(p) for p in england_prefixes):
                round_coords(f["geometry"], ndigits)
                feats.append(f)
        offset += len(got)
        print(f"  fetched {offset} features...")
        if not page.get("properties", {}).get("exceededTransferLimit") and len(got) < 2000:
            break
    return feats


def fetch_lsoa_boundaries():
    dest = PROCESSED / "lsoa_geo.jsonl"
    if dest.exists() and dest.stat().st_size > 10_000_000:
        print(f"  cached: {dest.name}")
        return
    feats = fetch_featureserver(LSOA_FS, "LSOA21CD,LSOA21NM", "LSOA21CD", ("E01",))
    with open(dest, "w") as f:
        for feat in feats:
            f.write(json.dumps(feat, separators=(",", ":")) + "\n")
    print(f"  lsoa_geo.jsonl: {len(feats)} England LSOAs")


def fetch_lad_boundaries():
    dest = PROCESSED / "lad_geo.json"
    if dest.exists():
        print(f"  cached: {dest.name}")
        return
    feats = fetch_featureserver(
        LAD_FS, "LAD24CD,LAD24NM", "LAD24CD", ("E06", "E07", "E08", "E09"), ndigits=4
    )
    json.dump({"type": "FeatureCollection", "features": feats},
              open(dest, "w"), separators=(",", ":"))
    print(f"  lad_geo.json: {len(feats)} England LADs")


def fetch_onspd():
    dest_lookup = PROCESSED / "postcode_lookup.csv"
    if dest_lookup.exists():
        print(f"  cached: {dest_lookup.name}")
        return
    import re

    zpath = download(ONSPD_URL, RAW / "onspd.zip")
    with zipfile.ZipFile(zpath) as z:
        single = [n for n in z.namelist()
                  if re.search(r"Data/ONSPD.*\.csv$", n)]
        data_names = single or sorted(
            n for n in z.namelist() if re.search(r"Data/multi_csv/.*\.csv$", n))
        assert data_names, f"no data csvs in {z.namelist()[:20]}"
        # resolve columns by pattern (names carry vintage suffixes, e.g. ctry25cd)
        with z.open(data_names[0]) as f:
            header = io.TextIOWrapper(f, encoding="latin-1").readline().strip().split(",")
        def col(pattern):
            hits = [c for c in header if re.fullmatch(pattern, c)]
            assert hits, f"no column matching {pattern} in {header}"
            return hits[0]
        c_pcds, c_term = col("pcds"), col("doterm")
        c_lsoa, c_ctry = col(r"lsoa21cd?"), col(r"ctry\d*cd")
        c_lat, c_long = col("lat"), col("long")
        usecols = [c_pcds, c_term, c_lsoa, c_ctry, c_lat, c_long]
        chunks = []
        for name in data_names:
            with z.open(name) as f:
                for chunk in pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"),
                                         usecols=usecols, chunksize=500_000,
                                         dtype=str):
                    c = chunk[chunk[c_ctry] == "E92000001"]
                    chunks.append(c.drop(columns=[c_ctry]))
        print(f"  parsed {len(data_names)} csv file(s)")
    df = pd.concat(chunks, ignore_index=True)
    df = df.rename(columns={c_pcds: "pcds", c_term: "doterm",
                            c_lsoa: "lsoa", c_lat: "lat", c_long: "long"})
    df.to_csv(dest_lookup, index=False)
    print(f"  postcode_lookup.csv: {len(df)} England postcodes")


if __name__ == "__main__":
    print("== IMD 2025 ==")
    fetch_imd()
    print("== LSOA21 boundaries ==")
    fetch_lsoa_boundaries()
    print("== LAD24 boundaries ==")
    fetch_lad_boundaries()
    print("== ONS Postcode Directory ==")
    fetch_onspd()
    print("done")
    sys.exit(0)
