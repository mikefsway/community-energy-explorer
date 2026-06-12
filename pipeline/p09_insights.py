"""Stage 9: small-area numbers for the insights report (insights.html).

Everything LAD-level on that page is computed in the browser from explore.json.
The one thing that can't be is the LSOA-level question — "are community energy
organisations and project sites located in deprived neighbourhoods?" — which
needs the 33k-LSOA IMD table. This stage answers it once and emits the decile
distributions.

For each point in orgs.geojson we take its LSOA (postcode-derived where the
source had one, else the LSOA of the nearest postcode — same resolver idea as
p08) and tally counts by IMD decile, separately for organisations (registered
offices) and CEE-map project sites, alongside each decile's population share
as the baseline.

Runs after p02 (orgs.geojson). Output: web/data/insights.json
"""
import datetime as dt
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from common import PROCESSED, WEB_DATA, write_json


def main():
    imd = pd.read_csv(PROCESSED / "imd.csv", dtype={"lsoa": str})
    decile_of = dict(zip(imd["lsoa"], imd["imd_decile"]))
    pop_by_decile = imd.groupby("imd_decile")["pop"].sum()
    pop_share = (pop_by_decile / pop_by_decile.sum()).to_dict()

    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["lat", "long", "lsoa"], dtype={"lsoa": str}).dropna()
    tree = cKDTree(np.c_[pc["lat"].astype(float), pc["long"].astype(float)])
    pc_lsoa = pc["lsoa"].to_numpy()

    with open(WEB_DATA / "orgs.geojson") as f:
        feats = json.load(f)["features"]

    counts = {"orgs": {d: 0 for d in range(1, 11)},
              "sites": {d: 0 for d in range(1, 11)}}
    unresolved = 0
    for feat in feats:
        p = feat["properties"]
        lsoa = p.get("lsoa")
        if not lsoa:
            lon, lat = feat["geometry"]["coordinates"][:2]
            _, idx = tree.query([lat, lon])
            lsoa = pc_lsoa[idx]
        dec = decile_of.get(lsoa)
        if dec is None:
            unresolved += 1
            continue
        kind = "sites" if p.get("src") == "cee-map" else "orgs"
        counts[kind][int(dec)] += 1

    write_json({
        "generated": dt.date.today().isoformat(),
        "note": "IMD decile (1 = most deprived 10% of LSOAs) of each community-energy "
                "point's neighbourhood; pop_share is each decile's share of England's "
                "population, the baseline an even spread would match.",
        "deciles": list(range(1, 11)),
        "orgs": [counts["orgs"][d] for d in range(1, 11)],
        "sites": [counts["sites"][d] for d in range(1, 11)],
        "pop_share": [round(pop_share[d], 4) for d in range(1, 11)],
    }, WEB_DATA / "insights.json", compact=False)

    print(f"  {sum(counts['orgs'].values())} orgs + {sum(counts['sites'].values())} sites "
          f"placed in deciles · {unresolved} unresolved")


if __name__ == "__main__":
    main()
