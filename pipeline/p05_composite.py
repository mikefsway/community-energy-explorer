"""Stage 5: merge everything, compute need x readiness, emit web artefacts.

Need      = deprivation (IMD 2025 rank, inverted percentile: high = more deprived)
Readiness = 0.75 * pct-rank of community infrastructure per 1k residents
            (registered charities + community venues in the LSOA)
          + 0.25 * pct-rank of the LAD's community energy orgs per 100k residents
cmp (1-9) = bivariate class: (readiness tercile - 1) * 3 + need tercile

Outputs: web/data/lad.geojson, web/data/lsoa/<LAD>.json, web/data/meta.json
"""
import datetime as dt
import json
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from common import PROCESSED, WEB_DATA, write_json


def load_pc_tree():
    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["lat", "long", "lsoa"], dtype={"lsoa": str})
    pc = pc.dropna()
    tree = cKDTree(np.c_[pc["lat"].astype(float), pc["long"].astype(float)])
    return tree, pc["lsoa"].to_numpy()


def assign_lsoa(df, tree, lsoas):
    """Fill missing df.lsoa using nearest postcode (approx; fine at neighbourhood scale)."""
    missing = df["lsoa"].isna() | (df["lsoa"] == "")
    if missing.any():
        pts = df.loc[missing, ["lat", "lon"]].astype(float).to_numpy()
        d, idx = tree.query(pts, workers=-1)
        df.loc[missing, "lsoa"] = lsoas[idx]
        far = (d > 0.02).sum()  # ~2km in degrees, rough
        if far:
            print(f"  note: {far} points >~2km from nearest postcode")
    return df


def pctrank(s):
    return s.rank(pct=True, na_option="keep")


def tercile(p):
    return np.where(p > 2 / 3, 3, np.where(p > 1 / 3, 2, 1))


def quintile_rank(s, invert=False):
    """1..5 from pct-rank; invert=True puts highest values in bucket 1."""
    p = pctrank(s)
    if invert:
        p = 1 - p
    return np.clip(np.ceil(p * 5), 1, 5).astype("Int64")


def main():
    imd = pd.read_csv(PROCESSED / "imd.csv", dtype={"lsoa": str, "lad": str})
    tree, pc_lsoas = load_pc_tree()

    counts = {}
    for name, fname in [("org", "org_points.csv"), ("venue", "infra_points.csv")]:
        path = PROCESSED / fname
        if path.exists():
            df = pd.read_csv(path, dtype={"lsoa": str})
            df["lsoa"] = df.get("lsoa", "").fillna("") if "lsoa" in df else ""
            df = assign_lsoa(df, tree, pc_lsoas)
            counts[name] = df["lsoa"].value_counts()
            print(f"  {name}: {len(df)} points")
        else:
            counts[name] = pd.Series(dtype=int)
            print(f"  WARNING: {fname} missing, {name} counts = 0")

    ch_path = PROCESSED / "charity_lsoa_counts.csv"
    if ch_path.exists():
        ch = pd.read_csv(ch_path, dtype={"lsoa": str}).set_index("lsoa")["charities"]
    else:
        ch = pd.Series(dtype=int)
        print("  WARNING: charity_lsoa_counts.csv missing")

    df = imd.set_index("lsoa")
    df["org"] = counts["org"].reindex(df.index).fillna(0).astype(int)
    df["inf"] = counts["venue"].reindex(df.index).fillna(0).astype(int)
    df["char"] = ch.reindex(df.index).fillna(0).astype(int)

    # --- indicators ---
    df["infra_per_1k"] = (df["char"] + df["inf"]) / df["pop"].clip(lower=1) * 1000
    df["iq"] = quintile_rank(df["infra_per_1k"])

    lad_g = df.groupby("lad")
    lad_orgs = lad_g["org"].sum()
    lad_pop = lad_g["pop"].sum()
    lad_org_rate = (lad_orgs / lad_pop * 100_000)
    org_rate_pct = pctrank(lad_org_rate)

    need_p = 1 - (df["imd_rank"] / df["imd_rank"].max())
    ready_p = 0.75 * pctrank(df["infra_per_1k"]) + 0.25 * df["lad"].map(org_rate_pct)
    df["cmp"] = ((tercile(ready_p) - 1) * 3 + tercile(need_p)).astype(int)

    # --- LSOA chunks per LAD ---
    lsoa_props = df.to_dict("index")
    chunks = defaultdict(list)
    n_geo = 0
    with open(PROCESSED / "lsoa_geo.jsonl") as f:
        for line in f:
            feat = json.loads(line)
            code = feat["properties"]["LSOA21CD"]
            p = lsoa_props.get(code)
            if not p:
                continue
            feat["properties"] = {
                "c": code,
                "n": p["lsoa_name"],
                "ladn": p["lad_name"],
                "d": int(p["imd_decile"]),
                "r": int(p["imd_rank"]),
                "pop": int(p["pop"]),
                "iq": int(p["iq"]),
                "org": int(p["org"]),
                "inf": int(p["inf"]) + int(p["char"]),
                "cmp": int(p["cmp"]),
            }
            chunks[p["lad"]].append(feat)
            n_geo += 1
    (WEB_DATA / "lsoa").mkdir(exist_ok=True)
    for lad, feats in chunks.items():
        with open(WEB_DATA / "lsoa" / f"{lad}.json", "w") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f,
                      separators=(",", ":"))
    print(f"  wrote {len(chunks)} LSOA chunk files ({n_geo} features)")

    # --- LAD aggregates ---
    agg = pd.DataFrame({
        "pop": lad_pop,
        "imd_s": (df["imd_score"] * df["pop"]).groupby(df["lad"]).sum() / lad_pop,
        "pct12": lad_g.apply(lambda g: (g["imd_decile"] <= 2).mean(), include_groups=False),
        "orgs": lad_orgs,
        "inf": lad_g["inf"].sum() + lad_g["char"].sum(),
        "infra_per_1k": (lad_g["inf"].sum() + lad_g["char"].sum()) / lad_pop * 1000,
        "name": lad_g["lad_name"].first(),
    })
    agg["imd_q"] = quintile_rank(agg["imd_s"], invert=True)  # 1 = most deprived
    lad_need_p = pctrank(agg["imd_s"])
    lad_ready_p = 0.75 * pctrank(agg["infra_per_1k"]) + 0.25 * org_rate_pct
    agg["cmp"] = ((tercile(lad_ready_p) - 1) * 3 + tercile(lad_need_p)).astype(int)
    agg["inf_q"] = quintile_rank(agg["infra_per_1k"])

    lad_geo = json.load(open(PROCESSED / "lad_geo.json"))
    out_feats = []
    for feat in lad_geo["features"]:
        code = feat["properties"]["LAD24CD"]
        if code not in agg.index:
            continue
        a = agg.loc[code]
        feat["properties"] = {
            "code": code, "name": a["name"],
            "pop": int(a["pop"]), "imd_s": round(float(a["imd_s"]), 2),
            "imd_q": int(a["imd_q"]), "inf_q": int(a["inf_q"]),
            "pct12": round(float(a["pct12"]), 3),
            "orgs": int(a["orgs"]), "inf": int(a["inf"]),
            "cmp": int(a["cmp"]),
        }
        out_feats.append(feat)
    write_json({"type": "FeatureCollection", "features": out_feats},
               WEB_DATA / "lad.geojson")

    write_json({
        "generated": dt.date.today().isoformat(),
        "lsoa": n_geo, "lad": len(out_feats),
        "orgs": int(counts["org"].sum()), "venues": int(counts["venue"].sum()),
        "charities": int(df["char"].sum()),
    }, WEB_DATA / "meta.json", compact=False)


if __name__ == "__main__":
    main()
