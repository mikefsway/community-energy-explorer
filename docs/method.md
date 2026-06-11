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
  do not feed the readiness score. Redress geocoding drops grantees absent from the
  charity/FCA registers (~⅓ of England rows), so absence of a point is weak evidence
  of absence of activity.
