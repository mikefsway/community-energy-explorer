# Community Energy Explorer

Interactive map exploring where community energy organisations exist in England, how that
aligns with deprivation at small-area level, what wider "community infrastructure" exists
that could be leveraged, and where the electricity grid has capacity for new local energy
projects.

The aim: understand where places are on the journey to delivering community energy, and
where it would be most beneficial.

**Live map:** https://mikefsway.github.io/community-energy-explorer/
**Data explorer:** https://mikefsway.github.io/community-energy-explorer/explore.html

## Data explorer

Beyond the map, `explore.html` is a data-first view that scores every English local
authority on three axes — **need** (deprivation), **readiness** (civic fabric + nearby
energy knowledge + grid headroom, deliberately excluding existing community energy) and
**presence** (community energy already on the ground) — and answers four questions:

- **Ranked table** — every authority and metric, sortable/filterable, with an installed-size
  slider ("which places have community energy above X kW") and CSV export.
- **Opportunity map** — readiness × presence quadrants: *thriving*, *latent* (easy wins —
  ready but empty), *pioneering*, *cold*.
- **Mismatches** — civic fabric without the energy; a knowledge base on the doorstep but no
  organisation; grid headroom going spare; deprived-and-overlooked.
- **Redress & need** — does Energy Redress funding track deprivation, and where do deprived
  places get neither community energy nor redress.

See `docs/method.md` for how the three axes are built.

## Layers

| Layer | Source | Geography |
|---|---|---|
| Deprivation (IMD) | MHCLG English Indices of Deprivation | LSOA |
| Community energy organisations | Community Energy England directory, FCA Mutuals Register, Charity Commission | point (geocoded) |
| Community energy project sites | CEE national map extract (2024) | point |
| Energy Redress funded projects | Ofgem Energy Redress Scheme (Energy Saving Trust) | point (geocoded) |
| Energy knowledge bases | UKRI Gateway to Research + curated sector anchors (DNO HQs, NESO, Ofgem, catapults, intermediaries, supplier HQs) | point |
| Community infrastructure | Charity Commission register density, OSM community centres / village halls | LSOA / point |
| Grid capacity | DNO open data portals (primary substation headroom), DNO licence areas | point / polygon |
| Need vs readiness composite | derived | LSOA + LAD |

## Structure

- `pipeline/` — Python scripts that download raw data, process it, and emit static
  GeoJSON/JSON artefacts into `web/data/`
- `web/` — static MapLibre GL site (deployed to GitHub Pages)
- `docs/` — data source notes, licences, methodology

## Running the pipeline

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
.venv/bin/python pipeline/run_all.py        # stages: p01, p03, p02, p04, p05, p06, p07, p08
```

## Licences

All input data is open data; see `docs/data-sources.md` for per-source licences
(mostly OGL v3). Contains OS, ONS and Royal Mail data © Crown copyright.
