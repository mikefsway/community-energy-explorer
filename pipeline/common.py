"""Shared helpers for the data pipeline."""
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
WEB_DATA = ROOT / "web" / "data"

for d in (RAW, PROCESSED, WEB_DATA):
    d.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "community-energy-explorer/0.1 (research; github.com/mikefsway/community-energy-explorer)"}


def download(url: str, dest: Path, force: bool = False, **kwargs) -> Path:
    """Download url to dest unless it already exists. Streams large files."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  cached: {dest.name}")
        return dest
    print(f"  downloading {url}")
    with requests.get(url, headers=UA, stream=True, timeout=600, **kwargs) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    print(f"  saved {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
    return dest


def get_json(url: str, retries: int = 3, **kwargs):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=120, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def write_json(obj, dest: Path, compact: bool = True):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        if compact:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        else:
            json.dump(obj, f, indent=1, ensure_ascii=False)
    print(f"  wrote {dest.relative_to(ROOT)} ({dest.stat().st_size/1e6:.2f} MB)")


def round_coords(geom, ndigits=5):
    """Round coordinates in a GeoJSON geometry in place (~1m precision at 5dp)."""
    def rnd(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], ndigits), round(coords[1], ndigits)]
        return [rnd(c) for c in coords]
    geom["coordinates"] = rnd(geom["coordinates"])
    return geom


def postcode_lookup_bulk(postcodes: list[str], sleep: float = 0.15) -> dict:
    """Bulk-resolve postcodes via postcodes.io. Returns {postcode: result|None}.

    result includes longitude, latitude, codes.lsoa (LSOA21), codes.admin_district (LAD).
    """
    out = {}
    cleaned = [p.strip().upper() for p in postcodes if p and p.strip()]
    cleaned = list(dict.fromkeys(cleaned))
    for i in range(0, len(cleaned), 100):
        batch = cleaned[i : i + 100]
        r = requests.post(
            "https://api.postcodes.io/postcodes",
            json={"postcodes": batch},
            headers=UA,
            timeout=60,
        )
        r.raise_for_status()
        for item in r.json()["result"]:
            out[item["query"].upper()] = item["result"]
        if i // 100 % 10 == 0:
            print(f"  geocoded {min(i+100, len(cleaned))}/{len(cleaned)} postcodes")
        time.sleep(sleep)
    return out
