"""Stage 8: per-LAD analytics table for the data explorer.

Joins every dataset to the Local Authority District (LAD) level and derives the
indices the explorer reasons over:

  need_p      deprivation percentile (high = more deprived)           [from IMD]
  ready_p     enabling-conditions percentile, EXCLUDING existing CE:
              civic fabric (0.5) + knowledge-base proximity (0.25)
              + grid headroom (0.25)
  presence_p  existing community-energy percentile (orgs+sites/100k)

From these the explorer builds the four lenses (ranked table, opportunity
typology, mismatch finder, redress lens). We emit the raw counts plus the three
percentile indices and let the web app compute thresholds/flags on the fly.

Runs after p05 (needs lad.geojson), p06 (redress) and p07 (knowledge).
Output: web/data/explore.json
"""
import datetime as dt
import json
import re

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from common import PROCESSED, WEB_DATA, write_json

KW_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*kW", re.I)


def pctrank(s):
    return pd.Series(s).rank(pct=True)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def centroid(geom):
    """Rough representative point: mean of all coordinates in the polygon(s)."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return float(np.mean(xs)), float(np.mean(ys))


def load_resolver():
    """Return (resolve_coords, lsoa2lad): map any point to a LAD24 code."""
    imd = pd.read_csv(PROCESSED / "imd.csv", dtype={"lsoa": str, "lad": str})
    lsoa2lad = dict(zip(imd["lsoa"], imd["lad"]))

    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["lat", "long", "lsoa"], dtype={"lsoa": str}).dropna()
    tree = cKDTree(np.c_[pc["lat"].astype(float), pc["long"].astype(float)])
    pc_lsoa = pc["lsoa"].to_numpy()

    def resolve_coords(lon, lat):
        _, idx = tree.query([lat, lon])
        return lsoa2lad.get(pc_lsoa[idx])

    return resolve_coords, lsoa2lad


def load_geojson(name):
    with open(WEB_DATA / name) as f:
        return json.load(f)["features"]


def main():
    resolve, lsoa2lad = load_resolver()

    # --- base: per-LAD frame from lad.geojson (single source of truth) ---
    lad_feats = load_geojson("lad.geojson")
    rows, centroids = {}, {}
    for f in lad_feats:
        p = f["properties"]
        lon, lat = centroid(f["geometry"])
        centroids[p["code"]] = (lat, lon)
        rows[p["code"]] = {
            "code": p["code"], "name": p["name"], "lat": round(lat, 4), "lon": round(lon, 4),
            "pop": p["pop"], "imd_s": p["imd_s"], "imd_q": p["imd_q"],
            "inf": p["inf"], "inf_q": p["inf_q"],
            "infra_per_1k": round(p["inf"] / max(p["pop"], 1) * 1000, 2),
            "ce_orgs": 0, "ce_sites": 0, "ce_total": 0,
            "cap_kw": 0.0, "cap_sites": 0, "biggest_kw": 0.0,
            "redress_grantees": 0, "redress_projects": 0, "redress_total": 0,
            "know_count": 0, "grid_subs": 0, "grid_green": 0, "grid_headroom": 0.0,
        }
    df = pd.DataFrame(rows).T

    def lad_of(feat):
        g = feat.get("geometry")
        if not g:
            return None
        lon, lat = g["coordinates"][:2]
        return resolve(lon, lat)

    # --- community energy: orgs vs project sites, installed capacity ---
    for f in load_geojson("orgs.geojson"):
        p = f["properties"]
        lad = lsoa2lad.get(p.get("lsoa")) or lad_of(f)
        if lad not in rows:
            continue
        rows[lad]["ce_total"] += 1
        if p.get("src") == "cee-map":
            rows[lad]["ce_sites"] += 1
            m = KW_RE.search(p.get("kind", ""))
            if m:
                kw = float(m.group(1).replace(",", ""))
                rows[lad]["cap_kw"] += kw
                rows[lad]["cap_sites"] += 1
                rows[lad]["biggest_kw"] = max(rows[lad]["biggest_kw"], kw)
        else:
            rows[lad]["ce_orgs"] += 1

    # --- redress grantees ---
    for f in load_geojson("redress.geojson"):
        lad = lad_of(f)
        if lad not in rows:
            continue
        p = f["properties"]
        rows[lad]["redress_grantees"] += 1
        rows[lad]["redress_projects"] += int(p.get("n", 0))
        rows[lad]["redress_total"] += int(p.get("total", 0))

    # --- knowledge bases: count within LAD ---
    know_pts, know_names = [], []
    for f in load_geojson("knowledge.geojson"):
        lon, lat = f["geometry"]["coordinates"][:2]
        know_pts.append((lat, lon))
        know_names.append(f["properties"].get("name", ""))
        lad = lad_of(f)
        if lad in rows:
            rows[lad]["know_count"] += 1
    know_pts = np.array(know_pts)

    # --- grid headroom (partial national coverage) ---
    for f in load_geojson("grid.geojson"):
        lad = lad_of(f)
        if lad not in rows:
            continue
        p = f["properties"]
        rows[lad]["grid_subs"] += 1
        rows[lad]["grid_headroom"] += float(p.get("gh", 0) or 0)
        if p.get("rag") == "g":
            rows[lad]["grid_green"] += 1

    df = pd.DataFrame(rows).T
    for c in ["pop", "ce_total", "ce_orgs", "ce_sites", "cap_sites", "redress_grantees",
              "redress_projects", "redress_total", "know_count", "grid_subs", "grid_green",
              "inf", "imd_q", "inf_q"]:
        df[c] = df[c].astype(int)
    for c in ["cap_kw", "biggest_kw", "grid_headroom", "imd_s", "infra_per_1k"]:
        df[c] = df[c].astype(float)

    # --- nearest knowledge base from LAD centroid (km) ---
    know_km, know_name = [], []
    for code in df["code"]:
        lat, lon = centroids[code]
        d = haversine_km(lat, lon, know_pts[:, 0], know_pts[:, 1])
        i = int(d.argmin())
        know_km.append(round(float(d[i]), 1))
        know_name.append(know_names[i])
    df["know_km"] = know_km
    df["know_name"] = know_name

    # --- derived percentile indices ---
    df["ce_per_100k"] = (df["ce_total"] / df["pop"].clip(lower=1) * 1e5).round(2)
    df["cap_per_1k"] = (df["cap_kw"] / df["pop"].clip(lower=1) * 1000).round(2)

    df["need_p"] = pctrank(df["imd_s"]).round(3)
    # presence has a large tie mass at zero (LADs with no CE at all); average-rank
    # percentiles would put them all at ~0.15. Use share-strictly-below so "none"
    # reads as exactly 0 and the opportunity score isn't suppressed for them.
    df["presence_p"] = ((df["ce_per_100k"].rank(method="min") - 1)
                        / (len(df) - 1)).round(3)

    # enabling conditions (independent of existing CE so opportunity is meaningful)
    infra_p = pctrank(df["infra_per_1k"])
    know_p = pctrank(-df["know_km"])                  # closer = readier
    grid_cov = df["grid_subs"] > 0
    grid_p = pd.Series(0.5, index=df.index)           # neutral where no DNO data
    if grid_cov.any():
        grid_p.loc[grid_cov] = pctrank(df.loc[grid_cov, "grid_green"])
    df["ready_p"] = (0.5 * infra_p + 0.25 * know_p + 0.25 * grid_p).round(3)
    df["grid_cov"] = grid_cov.astype(int)

    # headline lens scores
    df["opportunity"] = (df["ready_p"] - df["presence_p"]).round(3)   # high = easy win
    df["struggle"] = (df["need_p"] * (1 - df["ready_p"])).round(3)    # high = hard ground

    # opportunity typology (median split of readiness x presence)
    rmed, pmed = df["ready_p"].median(), df["presence_p"].median()
    def typ(r):
        hi_r, hi_p = r["ready_p"] >= rmed, r["presence_p"] >= pmed
        if hi_r and hi_p:
            return "thriving"
        if hi_r and not hi_p:
            return "latent"
        if not hi_r and hi_p:
            return "pioneering"
        return "cold"
    df["typology"] = df.apply(typ, axis=1)

    df = df.sort_values("name").reset_index(drop=True)

    national = {
        "lads": int(len(df)),
        "ce_total": int(df["ce_total"].sum()),
        "ce_orgs": int(df["ce_orgs"].sum()),
        "ce_sites": int(df["ce_sites"].sum()),
        "cap_mw": round(float(df["cap_kw"].sum()) / 1000, 1),
        "lads_no_ce": int((df["ce_total"] == 0).sum()),
        "redress_total": int(df["redress_total"].sum()),
        "grid_lads": int(grid_cov.sum()),
    }

    fields = {
        "need_p": "Deprivation percentile (IMD 2025, higher = more deprived)",
        "ready_p": "Enabling-conditions percentile: civic fabric 50%, knowledge proximity 25%, grid headroom 25% (excludes existing community energy)",
        "presence_p": "Existing community-energy percentile (orgs + project sites per 100k people; share of LADs strictly below, so no-CE LADs = 0)",
        "know_name": "Name of the nearest energy knowledge base (from LAD centroid)",
        "opportunity": "ready_p − presence_p: high = good conditions but little community energy yet (easy wins)",
        "struggle": "need_p × (1 − ready_p): high = deprived AND thin enabling conditions (hardest ground)",
        "typology": "thriving / latent (easy win) / pioneering / cold, from median split of readiness × presence",
        "cap_kw": "Installed capacity (kW) summed over CEE-map project sites — partial: 2024 vintage, not all schemes carry a size",
    }

    write_json({
        "generated": dt.date.today().isoformat(),
        "national": national,
        "fields": fields,
        "lads": df.to_dict("records"),
    }, WEB_DATA / "explore.json", compact=False)

    print(f"  {len(df)} LADs · {national['ce_total']} CE entries · "
          f"{national['cap_mw']} MW known · {national['lads_no_ce']} LADs with no CE")


if __name__ == "__main__":
    main()
