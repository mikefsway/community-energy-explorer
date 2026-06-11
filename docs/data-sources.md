# Data sources

All sources are open data, fetched directly by the pipeline. Verified June 2026.

## Deprivation
- **English Indices of Deprivation 2025** (MHCLG, published 30 Oct 2025, corrected Nov 2025).
  File 7 — all ranks, scores, deciles, population denominators. LSOA 2021 geography,
  33,755 English LSOAs. Licence: OGL v3.
  https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025

## Geography
- **LSOA (Dec 2021) boundaries EW BGC V5** — ONS Open Geography Portal, generalised 20m,
  fetched via FeatureServer in WGS84. Licence: OGL v3.
- **LAD (May 2024) boundaries UK BUC** — ONS Open Geography Portal. Matches the LAD 2024
  codes embedded in IoD2025 File 7.
- **ONS Postcode Directory (Nov 2025)** — postcode → LSOA21 + coordinates.
  Contains OS, ONS and Royal Mail data © Crown copyright.

## Community energy organisations
- **FCA Mutuals Public Register bulk CSV** (refreshed daily, cp1252 encoding) — registered
  societies filtered to `Reporting Classification = "Energy and environment"` plus
  energy-term name matches; registered office postcodes geocoded via ONSPD.
  https://mutuals.fca.org.uk (Download the Register)
- **Community Energy England member directory** — single server-rendered page with
  lat/lng per member card. ~330 members. https://communityenergyengland.org/our-members/
- **CEE national map bulk extract** — community-maintained CSV scrape of the CEE Google
  My Maps (1,323 project sites with technology + installed kW; 2024 vintage).
  https://github.com/sim11833/Community-Energy-Projects-in-UK
- **Charity Commission register** — energy-named community charities (supplementary).

Caveats: registered office ≠ project location; CICs and companies limited by guarantee
appear only via CEE/charity sources; the project-site extract is ~2 years stale.

## Community infrastructure
- **Charity Commission register of charities bulk extract** — registered main charities
  per LSOA via contact postcode. Licence: OGL.
  https://register-of-charities.charitycommission.gov.uk/register/full-register-download
- **OpenStreetMap** (Overpass API) — `amenity=community_centre|village_hall|social_centre`
  across England. Licence: ODbL. © OpenStreetMap contributors.

## Grid capacity
- **NESO GB DNO licence areas** (GeoJSON, EPSG:27700 → reprojected). OGL.
- **Northern Powergrid `heatmapdatatable`** — 670 grid/primary substations: firm capacity,
  demand/generation headroom (MVA), RAG constraint status. Open, no key.
- **SSEN headroom dashboard data (March 2026)** — ~1,000 GSP/BSP/primary substations,
  estimated demand/generation headroom + RAG; SEPD (southern England) rows used.
  Open, no key (requires a browser User-Agent header).
- **UKPN / NGED / ENWL / SP Energy Networks** — equivalent datasets exist on their open
  data portals but rows are gated behind free registration + API key. Add keys to
  `pipeline/dno_keys.json` (not committed) and extend `p04_grid.py` to fetch:
  - UKPN: `grid-and-primary-sites`, `dfes-network-headroom-report`
    (ukpowernetworks.opendatasoft.com)
  - NGED: `nged-network-capacity`, `network-opportunity-map-headroom`
    (connecteddata.nationalgrid.co.uk)
  - ENWL: `ndp-pry-bsp-headroom` (electricitynorthwest.opendatasoft.com)
  - SPEN: `spm-nshr-data-workbook` + `ndp-spm-primary-group-polygons`
    (spenergynetworks.opendatasoft.com)
- **National Embedded Capacity Register** (combined, hosted on NPg portal,
  `ecr_manual_combine_test`, 20k records) — available for a future "what's already
  connected/queued" layer.

Grid coverage on the map is therefore currently: Northern Powergrid (north-east England,
Yorkshire) and SSEN SEPD (central southern England). Other regions show DNO boundaries
with a pointer to the operator's own capacity map.
