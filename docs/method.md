# Method: the need × readiness view

The composite view crosses two percentile scores, computed at LSOA level (and again,
separately, at LAD level for the national view):

**Need** — how much a place stands to gain from community energy:
`need = 1 − IMD2025 rank / 33,755` (higher = more deprived).

**Readiness** — proxies for the civic capacity to organise and deliver:
`readiness = 0.75 × pct_rank(community infrastructure per 1,000 residents)
           + 0.25 × pct_rank(LAD community energy orgs per 100k residents)`

where *community infrastructure* = registered charities (Charity Commission, by contact
postcode) + community venues (OSM community centres, village halls, social centres) in
the LSOA, and the LAD org rate spreads the influence of existing community energy
organisations over their wider area (orgs are too sparse to score single LSOAs, and
they typically operate beyond one neighbourhood).

Both axes are cut into terciles and combined into a 9-class bivariate map:

| | need low | need mid | need high |
|---|---|---|---|
| **readiness high** | dark teal | | **deep plum — fertile + high impact** |
| **readiness mid** | | | |
| **readiness low** | pale grey | | **dark red — high need, thin fabric** |

Interpretation for "where on the journey":
- **Deep plum** (high need, strong fabric): best near-term prospects for community
  energy that reaches deprived places — capacity exists, benefit is large.
- **Dark red** (high need, thin fabric): community energy unlikely to emerge organically;
  needs capacity-building first, not just project funding.
- **Dark teal** (low need, strong fabric): where the sector already thrives (affluent,
  organised places) — useful as the comparison/diffusion frontier.
- Overlay the **grid headroom** layer to judge feasibility: a plum area near green
  substations is the strongest candidate of all.

## Known limitations
- Charity contact postcodes cluster in town centres and at professional addresses;
  density is a noisy proxy for civic capacity.
- OSM completeness varies regionally.
- Registered office location ≠ where an organisation operates.
- Grid headroom currently covers NPg and SSEN SEPD areas only (see data-sources.md);
  values are indicative snapshots, not connection offers.
- Weights (0.75/0.25) are judgement calls; the pipeline makes them easy to change in
  `p05_composite.py`.
- The Energy Redress and energy knowledge-base layers are visual overlays only — they
  do not feed the readiness score. Redress projects are placed at the local authority
  named in the project text where possible, else the grantee's registered office;
  projects with no recognised place and no register match are still dropped, so
  absence of a point is weak evidence of absence of activity.

## Data explorer (LAD-level)

`p08_explore.py` rolls every dataset up to the **local authority district** (296 in
England) and writes `web/data/explore.json`, which the `explore.html` page reasons over.
All headline axes are percentile ranks across those authorities:

- **need_p** — population-weighted IMD 2025 score (higher = more deprived).
- **ready_p** — *enabling conditions*, excluding existing community energy so the
  comparison stays meaningful: civic fabric per resident (50%), proximity to the nearest
  energy knowledge base (25%), and green grid headroom where the DNO publishes it (25%;
  a neutral 0.5 elsewhere).
- **presence_p** — community-energy organisations + project sites per 100k people.
  Because 87 authorities have none at all, this one is ranked as the share of
  authorities *strictly below* (not the tie-averaged percentile), so "none" scores
  exactly 0 rather than ~0.15 and the opportunity score isn't suppressed for the
  very places the latent lens is meant to surface.

Derived from these:

- **opportunity** = `ready_p − presence_p` — high = good conditions, little community
  energy yet (the easiest places to grow).
- **struggle** = `need_p × (1 − ready_p)` — high = deprived *and* thin on enabling
  conditions (the hardest ground).
- **typology** — median split of readiness × presence into *thriving* / *latent* (easy
  win) / *pioneering* / *cold*.

Installed capacity is parsed from the CEE-map `kind` field (e.g. `Solar · 24 kW`). Not
every scheme records a size and the extract is 2024 vintage, so capacity totals are a
floor, not a census. Like the map, organisation and redress locations are the named
local authority, a stated project town, or a registered office, and may differ from
where work actually happens.
