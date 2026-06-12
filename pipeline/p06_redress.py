"""Stage 6: Energy Redress Scheme funded projects.

The Energy Industry Voluntary Redress Scheme (Ofgem, administered by Energy Saving
Trust) lists all funded projects in a Drupal view at /funded-projects (phase, round,
charity + website, country/region, grant award, project name, description). The
view's default pager drifts between requests — rows repeat and others are missed,
and some published project nodes never surface at all — so a plain page crawl is
lossy. Instead we enumerate the view's `field_charity_target_id` exposed filter
(one term per grantee, ~300) and crawl each charity's own small, stable subset;
the union is every funded project. Phase 1 rounds also appear as static tables on
/projects with town-level locations, used to refine those points.

Geocoding, in order of preference:
  1. Phase-1 town location -> postcodes.io /places (England gazetteer) -> loc="area"
  2. project text (title/grantee/description) naming exactly one English local
     authority -> that LAD's centroid -> loc="area". Names in the title or grantee
     name are trusted even when ambiguous ("Reading"); in free-text description,
     LAD names that are also common words are ignored.
  3. grantee name matched against the Charity Commission extract or FCA Mutuals
     Register -> registered-office postcode -> loc="office"
Projects located in Scotland/Wales/NI are excluded; England-region or UK-wide
projects keep their best available point.

Output: web/data/redress.geojson, data/processed/redress_projects.csv (cache)
"""
import io
import json
import re
import time
import zipfile
from html import unescape

import numpy as np
import pandas as pd
import requests

from common import PROCESSED, RAW, UA, WEB_DATA, download, write_json

LIST_URL = "https://energyredress.org.uk/funded-projects"
TABLES_URL = "https://energyredress.org.uk/projects"

NATIONS = {"Scotland", "Wales", "Northern Ireland"}
STOP_SUFFIX = re.compile(
    r"\b(limited|ltd|cic|cio|community benefit society|society|co-?operative|coop|"
    r"charity|trust|the)\b\.?", re.I)
def norm_name(name):
    s = STOP_SUFFIX.sub(" ", str(name).lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def strip_tags(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def scrape_listing():
    """Scrape the funded-projects view per grantee (charity) term.

    The view's default pager drifts between page requests, so rows repeat, others
    are missed, and some published nodes never appear under any phase filter.
    The exposed `field_charity_target_id` filter lists every grantee as its own
    term; each charity's filtered subset is one or two stable pages, and their
    union is the complete project list. The term label is the canonical charity
    name (cleaner than the per-row link text), carried through as ``org``.
    """
    r0 = requests.get(LIST_URL, headers=UA, timeout=60)
    r0.raise_for_status()
    charities = {m.group(1): strip_tags(m.group(2)) for m in re.finditer(
        r'name="field_charity_target_id\[(\d+)\]"[^>]*>\s*<label[^>]*>(.*?)</label>',
        r0.text, re.S)}
    print(f"  grantee filter terms: {len(charities)}")
    rows = []
    for tid, cname in charities.items():
        page = 0
        while page < 10:
            r = requests.get(LIST_URL, headers=UA, timeout=60, params={
                f"field_charity_target_id[{tid}]": tid, "page": page})
            r.raise_for_status()
            chunks = r.text.split('<div class="views-row">')[1:]
            if not chunks:
                break
            rows.extend(parse_row(c, cname) for c in chunks)
            page += 1
            time.sleep(0.1)
    rows = [r for r in rows if r]
    print(f"  listing: {len(rows)} rows across {len(charities)} grantee subsets")
    return rows


def parse_row(c, cname):
    url_m = re.search(r'field--name-field-charity-link[^>]*>\s*<a href="([^"]*)"', c, re.S)
    url = url_m.group(1) if url_m else ""
    phase_m = re.search(r'field--name-field-phase.*?cshs-term-group__title[^>]*>(.*?)</div>', c, re.S)
    round_m = re.search(r'field--name-field-round[^>]*>(.*?)</div>', c, re.S)
    grant_m = re.search(r'field--name-field-grant-value.*?field__item[^>]*>(.*?)</div>', c, re.S)
    title_m = re.search(r'field--name-node-title.*?field__item[^>]*>(.*?)</div>', c, re.S)
    body_m = re.search(r'field--name-body.*?field__item[^>]*>(.*?)(?:</div>\s*){2}', c, re.S)
    loc_terms = [strip_tags(t) for t in re.findall(
        r'cshs-term-group__(?:title|term)[^>]*>(.*?)</(?:div|li)>',
        field_block(c, "field-location"), re.S)]
    amt = None
    if grant_m:
        digits = re.sub(r"[^\d]", "", grant_m.group(1).split(".")[0])
        amt = int(digits) if digits else None
    body = strip_tags(body_m.group(1)) if body_m else ""
    return {
        "org": cname, "url": url,
        "phase": strip_tags(phase_m.group(1)) if phase_m else "",
        "round": strip_tags(round_m.group(1)) if round_m else "",
        "loc_terms": " > ".join(t for t in loc_terms if t),
        "amount": amt,
        "project": strip_tags(title_m.group(1)) if title_m else "",
        "body": body, "desc": body[:220],
    }


def field_block(row_html, fname):
    """HTML of one field block: from its opening div to the next field--name-."""
    i = row_html.find(f'field--name-{fname}')
    if i < 0:
        return ""
    j = row_html.find('field--name-field-grant', i + 10)
    return row_html[i:j if j > 0 else i + 4000]


def static_table_rows():
    """Rows from the static /projects accordion tables (mostly Phase 1, with towns)."""
    dest = download(TABLES_URL, RAW / "redress.html")
    html = open(dest, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", html, re.S):
        title = strip_tags(m.group(1))
        pm = re.search(r"Phase\s*(\d+),\s*Round\s*(\d+)", title, re.I)
        if not pm:
            continue
        phase, rnd = f"Phase {pm.group(1)}", f"Round {pm.group(2)}"
        for tbl in re.findall(r"<table.*?</table>", m.group(2), re.S):
            trs = re.findall(r"<tr.*?</tr>", tbl, re.S)
            if not trs:
                continue
            header = [strip_tags(c).lower() for c in re.findall(r"<td.*?</td>", trs[0], re.S)]
            def col(*terms):
                return next((i for i, h in enumerate(header)
                             if any(t in h for t in terms)), None)
            c_org, c_loc, c_amt, c_prj = (col("charity", "organisation"),
                                          col("location"), col("grant"), col("project"))
            if c_org is None:
                continue
            for tr in trs[1:]:
                cells = [strip_tags(c) for c in re.findall(r"<td.*?</td>", tr, re.S)]
                if len(cells) <= c_org or not cells[c_org]:
                    continue
                amt = None
                if c_amt is not None and c_amt < len(cells):
                    digits = re.sub(r"[^\d]", "", cells[c_amt].split(".")[0])
                    amt = int(digits) if digits else None
                out.append({
                    "org": cells[c_org], "url": "", "phase": phase, "round": rnd,
                    "town": cells[c_loc] if c_loc is not None and c_loc < len(cells) else "",
                    "loc_terms": "", "amount": amt,
                    "project": cells[c_prj] if c_prj is not None and c_prj < len(cells) else "",
                    "desc": "",
                })
    print(f"  static tables: {len(out)} rows with town locations")
    return out


def register_lookup():
    """norm name -> (lat, lon) from Charity Commission + FCA registers (England)."""
    pc = pd.read_csv(PROCESSED / "postcode_lookup.csv",
                     usecols=["pcds", "lat", "long"], dtype=str)
    pc["key"] = pc["pcds"].str.replace(" ", "", regex=False).str.upper()
    pc = pc.drop_duplicates("key").set_index("key")

    out = {}
    with zipfile.ZipFile(RAW / "cc_charity.zip") as z:
        with z.open(z.namelist()[0]) as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), sep="\t",
                             dtype=str, quoting=3, on_bad_lines="skip",
                             usecols=["charity_name", "linked_charity_number",
                                      "charity_registration_status",
                                      "charity_contact_postcode"])
    df = df[(df["linked_charity_number"].astype(float) == 0)
            & df["charity_registration_status"].str.strip().eq("Registered")]
    df["key"] = (df["charity_contact_postcode"].fillna("")
                 .str.upper().str.replace(" ", "", regex=False))
    df = df.join(pc, on="key").dropna(subset=["lat"])
    for _, r in df.iterrows():
        out.setdefault(norm_name(r["charity_name"]),
                       (float(r["lat"]), float(r["long"])))
    print(f"  register lookup: {len(out)} charity names", end="")

    pc_re = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
    fca = pd.read_csv(RAW / "fca_societies.csv", encoding="cp1252", dtype=str)
    fca.columns = [c.strip() for c in fca.columns]
    n_fca = 0
    for _, r in fca.iterrows():
        m = pc_re.search(str(r.get("Society Address") or ""))
        if not m:
            continue
        key = m.group(1).replace(" ", "").upper()
        if key in pc.index:
            nm = norm_name(r["Society Name"])
            if nm not in out:
                out[nm] = (float(pc.loc[key, "lat"]), float(pc.loc[key, "long"]))
                n_fca += 1
    print(f" + {n_fca} FCA societies")
    return out


def place_geocode(location, cache):
    """Town-level geocode via postcodes.io places (England only)."""
    q = location.split(",")[0].split("&")[0].strip()
    if len(q) < 3:
        return None
    if q in cache:
        return cache[q]
    hit = None
    try:
        r = requests.get("https://api.postcodes.io/places",
                         params={"q": q, "limit": 5}, headers=UA, timeout=30)
        if r.ok:
            for res in (r.json().get("result") or []):
                if res.get("country") == "England":
                    hit = (res["latitude"], res["longitude"])
                    break
    except requests.RequestException:
        pass
    cache[q] = hit
    time.sleep(0.12)
    return hit


# LAD names that are also common English words / personal names: trusted when they
# appear in a project title or grantee name, ignored in free-text descriptions.
AMBIG = {"Reading", "Hart", "Brent", "Bury", "Rother", "Arun", "Adur", "Eden",
         "Craven", "Maldon", "Wyre", "Swale", "Rugby", "Dover", "Halton", "Boston",
         "Pendle", "Lewes", "Three Rivers", "Mole Valley", "Charnwood", "Selby"}


def lad_centroid(geom):
    """Mean of all coordinates in a (multi)polygon: (lat, lon)."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)

    walk(geom["coordinates"])
    return float(np.mean(ys)), float(np.mean(xs))


def load_lad_resolver():
    """Return resolve(row) -> (lat, lon) | None, placing a project at the centroid
    of the one English LAD its text names, or None when zero/ambiguous/many."""
    feats = json.load(open(WEB_DATA / "lad.geojson"))["features"]
    pts = {f["properties"]["name"]: lad_centroid(f["geometry"]) for f in feats}
    pats = [(re.compile(r"\b" + re.escape(n) + r"\b"), n) for n in pts]

    def named(text):
        return {n for pat, n in pats if pat.search(text)}

    def resolve(row):
        title = named(f"{row['project']} {row['org']}")
        if len(title) == 1:
            return pts[next(iter(title))]
        body = {n for n in named(row.get("body", "")) if n not in AMBIG}
        if len(body) == 1:
            return pts[next(iter(body))]
        if title:                                  # title lists several; body picks one
            both = title & named(row.get("body", ""))
            if len(both) == 1:
                return pts[next(iter(both))]
        return None

    print(f"  LAD resolver: {len(pts)} English authorities")
    return resolve


def main():
    cache_path = PROCESSED / "redress_projects.csv"
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        print(f"  using cached geocodes: {cache_path.name} ({len(df)} rows)")
    else:
        rows = scrape_listing()
        static = static_table_rows()
        # dedupe the view (pagination drift repeats rows)
        seen, deduped = set(), []
        for r in rows:
            key = (norm_name(r["org"]), r["round"], r["amount"], r["project"].lower())
            if key not in seen:
                seen.add(key)
                deduped.append(dict(r, town=""))
        # enrich with static towns; append static rows missing from the view
        view_keys = {(norm_name(r["org"]), r["amount"]) for r in deduped}
        towns = {(norm_name(r["org"]), r["amount"]): r["town"] for r in static}
        for r in deduped:
            r["town"] = towns.get((norm_name(r["org"]), r["amount"]), "")
        extra = [r for r in static
                 if (norm_name(r["org"]), r["amount"]) not in view_keys]
        merged = deduped + extra
        print(f"  view {len(deduped)} (deduped from {len(rows)}) + {len(extra)} "
              f"static-only = {len(merged)}")

        registers = register_lookup()
        resolve_lad = load_lad_resolver()
        pcache, out = {}, []
        skipped = {"non_england": 0, "no_geocode": 0}
        for r in merged:
            if any(n in r["loc_terms"] for n in NATIONS):
                skipped["non_england"] += 1
                continue
            pt, loc = None, ""
            if r["town"]:                                  # Phase-1 town (most specific)
                pt, loc = place_geocode(r["town"], pcache), "area"
            if not pt and (pt := resolve_lad(r)):          # one LAD named in the text
                loc = "area"
            if not pt:                                     # grantee registered office
                pt, loc = registers.get(norm_name(r["org"])), "office"
            if not pt:
                skipped["no_geocode"] += 1
                continue
            out.append({**{k: v for k, v in r.items()
                           if k not in ("loc_terms", "town", "body")},
                        "region": r["loc_terms"],
                        "lat": round(pt[0], 5), "lon": round(pt[1], 5), "loc": loc})
        print(f"  geocoded {len(out)} | by source: "
              f"{pd.Series([o['loc'] for o in out]).value_counts().to_dict()} | "
              f"skipped: {skipped}")
        df = pd.DataFrame(out)
        df.to_csv(cache_path, index=False)

    # aggregate: one feature per organisation per point
    feats = []
    for (org, lat, lon), grp in df.groupby(["org", "lat", "lon"]):
        projects = [p for p in grp["project"].fillna("").tolist() if p]
        total = int(grp["amount"].fillna(0).sum())
        url = next((u for u in grp["url"].fillna("").tolist() if u), "")
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {k: v for k, v in {
                "name": org,
                "n": len(grp),
                "total": total or None,
                "projects": " · ".join(projects[:3]) + (" …" if len(projects) > 3 else ""),
                "url": url,
                "loc": grp["loc"].iloc[0],
            }.items() if v},
        })
    write_json({"type": "FeatureCollection", "features": feats},
               WEB_DATA / "redress.geojson")
    print(f"  redress.geojson: {len(feats)} grantee points")


if __name__ == "__main__":
    main()
