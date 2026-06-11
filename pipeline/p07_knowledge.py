"""Stage 7: energy knowledge bases.

Two parts:
  A. UKRI Gateway to Research — projects whose research topics match energy terms,
     aggregated by lead organisation (count + active count), geocoded via the
     organisation record's postcode. Academic orgs vs other lead orgs are
     distinguished by name. Only orgs with >= MIN_PROJECTS energy projects kept.
  B. pipeline/knowledge_anchors.csv — curated sector anchors (DNO HQs, system
     operator, regulator, catapults, intermediaries, major supplier HQs),
     geocoded via the England postcode lookup.

Output: web/data/knowledge.geojson, data/processed/gtr_energy_orgs.csv (cache)
"""
import csv
import re
import time

import pandas as pd
import requests

from common import PROCESSED, ROOT, UA, WEB_DATA, write_json

GTR = "https://gtr.ukri.org/gtr/api"
HDRS = {**UA, "Accept": "application/json"}
TOPICS = ["Energy", "Solar Technology", "Wind Power", "Bioenergy",
          "Fuel Cell", "Carbon Capture", "Hydrogen"]
# exact-topic whitelist: the q= search is full-text over topic names, so e.g.
# "Energy" also matches "Bioenergetics" (cell biology) — filter to real energy
# topics: anything starting "Energy" plus these technology topics
TOPIC_OK = {"Solar Technology", "Wind Power", "Bioenergy", "Fuel Cell Technologies",
            "Carbon Capture & Storage", "Sustainable Energy Networks",
            "Sustainable Energy Vectors"}
# org records that 404 (superseded ids) remapped to their canonical record
ORG_REMAP = {
    # UCL (old record; depts incl. Bartlett Sch of Env, Energy & Resources)
    "BFE41CB6-4B8A-4082-B96B-3DFEFE793924": "2E89A125-8219-459F-9EC4-A2BD9FC9B245",
    # University of Oxford (old record; depts incl. Materials, Engineering Science)
    "47649064-FCD1-4D7A-A5AA-31B69B9BDFFC": "54C97C7A-ADCC-4814-A44C-CEFDA954E0CC",
}
NAME_FIX = {
    "THE CHANCELLOR, MASTERS AND SCHOLARS OF THE UNIVERSITY OF OXFORD":
        "University of Oxford",
}
# org records whose GtR postcode is missing/"Unknown"
PC_FIX = {
    "University College London": "WC1E 6BT",
    "University of Oxford": "OX1 2JD",
}
MIN_PROJECTS = 3
ACADEMIC = re.compile(r"\buniversit|college|institute|laborator|school of\b", re.I)


def get_json(url, params=None, retries=4):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HDRS, timeout=120)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def gtr_energy_orgs():
    cache = PROCESSED / "gtr_energy_orgs.csv"
    if cache.exists():
        print(f"  using cached {cache.name}")
        return pd.read_csv(cache, dtype={"pc": str})

    import json
    scan_cache = PROCESSED / "gtr_projects_raw.json"
    if scan_cache.exists():
        projects = json.load(open(scan_cache))
        print(f"  using cached project scan: {len(projects)} projects")
    else:
        projects = {}  # id -> [status, lead_org_id, dept]
        for topic in TOPICS:
            page, pages = 1, 1
            while page <= pages:
                d = get_json(f"{GTR}/projects", {"q": topic, "f": "pro.rt",
                                                 "s": 100, "p": page})
                pages = d.get("totalPages", 1)
                for p in d.get("project") or []:
                    topics = [(t.get("text") or "") for t in
                              (p.get("researchTopics") or {}).get("researchTopic") or []]
                    if not any(t.startswith("Energy") or t in TOPIC_OK for t in topics):
                        continue
                    lead = next((l["href"].rsplit("/", 1)[1]
                                 for l in p.get("links", {}).get("link") or []
                                 if l.get("rel") == "LEAD_ORG"), None)
                    if lead and p["id"] not in projects:
                        projects[p["id"]] = [p.get("status") or "", lead,
                                             p.get("leadOrganisationDepartment") or ""]
                page += 1
                time.sleep(0.15)
            print(f"  GtR topic '{topic}': cumulative {len(projects)} projects")
        json.dump(projects, open(scan_cache, "w"))

    counts = {}
    for status, org, dept in projects.values():
        org = ORG_REMAP.get(org, org)
        c = counts.setdefault(org, {"n": 0, "active": 0, "depts": {}})
        c["n"] += 1
        c["active"] += status == "Active"
        if dept:
            c["depts"][dept] = c["depts"].get(dept, 0) + 1

    keep = {oid: c for oid, c in counts.items() if c["n"] >= MIN_PROJECTS}
    print(f"  {len(counts)} lead orgs, {len(keep)} with >= {MIN_PROJECTS} projects")

    rows = []
    for i, (oid, c) in enumerate(keep.items()):
        try:
            d = get_json(f"{GTR}/organisations/{oid}", retries=2)
        except requests.HTTPError as e:
            top = sorted(c["depts"].items(), key=lambda kv: -kv[1])[:3]
            print(f"  skipping org {oid}: {e.response.status_code} "
                  f"(n={c['n']}, depts={top}) — add to ORG_REMAP if identifiable")
            continue
        addr = (d.get("addresses") or {}).get("address") or []
        main = next((a for a in addr if a.get("type") == "MAIN_ADDRESS"), addr[0] if addr else {})
        name = d.get("name", "")
        name = NAME_FIX.get(name) or (
            re.sub(r"\b(Of|The|And|For)\b", lambda m: m.group(1).lower(), name.title())
            if name.isupper() else name)
        rows.append({"name": name, "pc": (main.get("postCode") or "").strip(),
                     "n": c["n"], "active": c["active"]})
        if (i + 1) % 50 == 0:
            print(f"  org details {i + 1}/{len(keep)}")
        time.sleep(0.12)
    df = pd.DataFrame(rows)
    df.to_csv(cache, index=False)
    return df


def main():
    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["pcds", "lat", "long"], dtype=str)
    pc["key"] = pc["pcds"].str.replace(" ", "", regex=False).str.upper()
    pc = pc.drop_duplicates("key").set_index("key")

    def locate(postcode):
        key = str(postcode or "").replace(" ", "").upper()
        if key in pc.index:
            return float(pc.loc[key, "lat"]), float(pc.loc[key, "long"])
        return None

    feats = []
    gtr = gtr_energy_orgs()
    n_eng = 0
    for _, r in gtr.iterrows():
        pt = locate(r["pc"]) or locate(PC_FIX.get(r["name"]))
        if not pt or not r["name"]:
            continue
        n_eng += 1
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(pt[1], 5), round(pt[0], 5)]},
            "properties": {
                "name": r["name"],
                "kind": "university" if ACADEMIC.search(r["name"]) else "industry",
                "n": int(r["n"]), "active": int(r["active"]),
            },
        })
    print(f"  GtR orgs located in England: {n_eng} of {len(gtr)}")

    with open(ROOT / "pipeline" / "knowledge_anchors.csv") as f:
        for r in csv.DictReader(f):
            pt = locate(r["pc"])
            if not pt:
                print(f"  WARNING: anchor postcode not found: {r['name']} {r['pc']}")
                continue
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(pt[1], 5), round(pt[0], 5)]},
                "properties": {"name": r["name"], "kind": r["kind"],
                               "url": r["url"], "note": r["note"]},
            })

    write_json({"type": "FeatureCollection", "features": feats},
               WEB_DATA / "knowledge.geojson")
    print(f"  knowledge.geojson: {len(feats)} points")


if __name__ == "__main__":
    main()
