"""Stage 2: community energy organisations.

Sources:
  A. FCA Mutuals Register bulk CSV (daily refresh, cp1252) — registered societies,
     filtered to energy via Reporting Classification + name terms. Postcode -> coords.
  B. Community Energy England member directory (server-rendered, lat/lng on cards).
  C. CEE national map bulk extract (GitHub scrape, 2024) — project-level points.

Output: web/data/orgs.geojson + data/processed/org_lsoa_counts.csv
"""
import csv
import io
import json
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from common import PROCESSED, RAW, UA, WEB_DATA, download, write_json

FCA_URL = "https://fcastoragemprprod.blob.core.windows.net/societylist/SocietyList.csv"
CEE_URL = "https://communityenergyengland.org/our-members/"
CEEMAP_URL = "https://raw.githubusercontent.com/sim11833/Community-Energy-Projects-in-UK/main/community_energy_projects_uk.csv"

PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
NAME_TERMS = re.compile(r"\b(energy|solar|hydro|wind|power|renewabl)", re.I)
STOP_SUFFIX = re.compile(
    r"\b(limited|ltd|cic|cio|community benefit society|society|co-?operative|coop)\b\.?", re.I)


def norm_name(name):
    s = STOP_SUFFIX.sub(" ", str(name).lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_postcodes():
    df = pd.read_csv(PROCESSED / "postcode_lookup.csv", dtype=str)
    df["key"] = df["pcds"].str.replace(" ", "").str.upper()
    df = df.drop_duplicates("key").set_index("key")
    return df


def fca_orgs(pclookup):
    dest = download(FCA_URL, RAW / "fca_societies.csv", force=True)
    df = pd.read_csv(dest, encoding="cp1252", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    is_energy = (df["Reporting Classification"].str.strip().eq("Energy and environment")
                 | df["Society Name"].str.contains(NAME_TERMS, na=False))
    live = df["Society Status"].str.strip().eq("Registered")
    sel = df[is_energy & live].copy()
    print(f"  FCA: {len(sel)} live energy/environment societies (of {len(df)})")
    out = []
    for _, r in sel.iterrows():
        addr = str(r.get("Society Address") or "")
        m = PC_RE.search(addr)
        if not m:
            continue
        key = m.group(1).replace(" ", "").upper()
        hit = pclookup.loc[key] if key in pclookup.index else None
        if hit is None:  # not an England postcode
            continue
        out.append({
            "name": r["Society Name"].strip(),
            "norm": norm_name(r["Society Name"]),
            "src": "fca",
            "kind": (r.get("Registered As") or "").strip(),
            "pc": m.group(1).upper(),
            "lsoa": hit["lsoa"],
            "lat": float(hit["lat"]), "lon": float(hit["long"]),
            "url": "",
            "reg": (r.get("Full Registation Number") or "").strip(),
        })
    print(f"  FCA: {len(out)} geocoded to England")
    return out


def cee_orgs():
    r = requests.get(CEE_URL, headers=UA, timeout=120)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for card in soup.select("article.organisation-card"):
        title = card.select_one(".organisation-card__title")
        if not title:
            continue
        lat, lng = card.get("data-lat"), card.get("data-lng")
        techs = sorted({s.get_text(strip=True) for s in
                        card.select('[data-filter="technology"]')} - {""})
        link = card.select_one("a.organisation-card__permalink")
        region = card.select_one(".organisation-card__region")
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        out.append({
            "name": title.get_text(strip=True),
            "norm": norm_name(title.get_text(strip=True)),
            "src": "cee",
            "kind": ", ".join(t.replace("-", " ") for t in techs) or "member",
            "pc": "",
            "lsoa": "",
            "lat": lat, "lon": lng,
            "url": link["href"] if link else "",
            "region": region.get_text(strip=True).replace("Region:", "").strip() if region else "",
        })
    print(f"  CEE: {len(out)} members with coordinates")
    return out


def ceemap_projects():
    dest = download(CEEMAP_URL, RAW / "cee_map_projects.csv")
    out = []
    with open(dest, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                lat, lon = float(r["Lat"]), float(r["Lon"])
            except (TypeError, ValueError, KeyError):
                continue
            name = (r.get("Project Name") or "").strip()
            if not name:
                continue
            kw = r.get("Installed Capacity (kW)") or ""
            out.append({
                "name": name,
                "norm": norm_name(re.sub(r"\[.*?\]", "", name)),
                "src": "cee-map",
                "kind": ((r.get("Energy") or "").strip()
                         + (f" · {kw} kW" if kw.strip() else "")).strip(" ·"),
                "pc": "", "lsoa": "",
                "lat": lat, "lon": lon, "url": "",
            })
    print(f"  CEE map extract: {len(out)} projects")
    return out


def cc_orgs():
    """Energy-named community charities (produced by stage 3, if it has run)."""
    path = PROCESSED / "cc_energy_orgs.csv"
    if not path.exists():
        print("  Charity Commission: cc_energy_orgs.csv not present yet (run stage 3)")
        return []
    df = pd.read_csv(path, dtype=str)
    out = []
    for _, r in df.iterrows():
        try:
            lat, lon = float(r["lat"]), float(r["long"])
        except (TypeError, ValueError):
            continue
        out.append({
            "name": str(r["charity_name"]).strip().title(),
            "norm": norm_name(r["charity_name"]),
            "src": "charity",
            "kind": "registered charity",
            "pc": str(r.get("pc") or ""),
            "lsoa": str(r.get("lsoa") or ""),
            "lat": lat, "lon": lon, "url": "",
        })
    print(f"  Charity Commission: {len(out)} energy charities")
    return out


def in_england_bbox(o):
    return 49.8 <= o["lat"] <= 55.9 and -6.5 <= o["lon"] <= 2.0


def main():
    pclookup = load_postcodes()
    fca = fca_orgs(pclookup)
    cee = cee_orgs()
    proj = ceemap_projects()
    cc = cc_orgs()

    # merge: CEE member entries enrich/absorb FCA rows with same normalised name
    by_norm = {}
    for o in fca:
        by_norm[o["norm"]] = o
    for o in cc:
        by_norm.setdefault(o["norm"], o)
    for o in cee:
        if o["norm"] in by_norm:
            base = by_norm[o["norm"]]
            base["src"] = "fca+cee"
            base["url"] = o["url"]
            if o["kind"] != "member":
                base["kind"] = o["kind"]
        else:
            by_norm[o["norm"]] = o
    orgs = [o for o in by_norm.values() if in_england_bbox(o)]
    # projects kept separate (site-level), but drop exact name dupes of orgs
    projects = [p for p in proj if p["norm"] not in by_norm and in_england_bbox(p)]
    print(f"  merged: {len(orgs)} orgs + {len(projects)} project sites")

    feats = []
    for o in orgs + projects:
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(o["lon"], 5), round(o["lat"], 5)]},
            "properties": {k: v for k, v in {
                "name": o["name"], "src": o["src"], "kind": o.get("kind", ""),
                "pc": o.get("pc", ""), "url": o.get("url", ""),
                "lsoa": o.get("lsoa", ""),
            }.items() if v},
        })
    write_json({"type": "FeatureCollection", "features": feats},
               WEB_DATA / "orgs.geojson")

    # per-LSOA org counts (orgs with a known LSOA via postcode; others assigned in stage 5)
    rows = [{"lsoa": o["lsoa"], "lat": o["lat"], "lon": o["lon"]} for o in orgs + projects]
    pd.DataFrame(rows).to_csv(PROCESSED / "org_points.csv", index=False)
    print(f"  org_points.csv: {len(rows)} rows")


if __name__ == "__main__":
    main()
