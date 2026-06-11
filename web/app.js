/* Community Energy Explorer — static MapLibre app.
 * Data contract (web/data/):
 *   meta.json          {generated, counts:{orgs,infra,grid}}
 *   lad.geojson        England LADs: code,name,imd_s,imd_q(1-5),inf_q(1-5),cmp(1-9),orgs,inf,pop,pct12
 *   lsoa/<LAD>.json    LSOA FeatureCollections: c,n,d(1-10),r,s,iq(1-5),org,inf,cmp(1-9),pop
 *   orgs.geojson       points: name,src,kind,pc,lad,url (src=cee-map → project site)
 *   redress.geojson    points: name,n,total,projects,url,loc(area|office)
 *   knowledge.geojson  points: name,kind,n,active | name,kind,url,note (anchors)
 *   infra.geojson      points: name,kind
 *   grid.geojson       points: name,dno,dh,gh,rag(r|a|g)
 *   dno.geojson        polygons: name
 */
"use strict";

const DATA = "data/";
const LSOA_ZOOM = 8.6;           // load + show LSOA detail from here

const IMD_COLORS = ["#6a0220","#8c1127","#ab2330","#c44743","#d96f57",
                    "#e89670","#f2bb91","#f8d8b8","#fbeada","#fdf6ec"]; // decile 1..10
const INFRA_COLORS = ["#e6eee9","#b8d8d2","#7fbcb4","#449a96","#16707c"]; // quintile 1..5
const BIVAR = ["#e8e8e8","#e4acac","#c85a5a",   // ready-low  : need low→high
               "#b0d5df","#ad9ea5","#985356",   // ready-mid
               "#64acbe","#627f8c","#574249"];  // ready-high
const RAG = { g: "#2e9e5b", a: "#e8a013", r: "#cb4b3a" };

const METRICS = {
  imd: {
    note: "English Indices of Deprivation 2025. Darker = more deprived (decile 1 = most deprived tenth of neighbourhoods).",
    legend: rampLegend(IMD_COLORS.slice().reverse(), "least deprived", "most deprived"),
    lsoaColor: stepExpr(["get", "d"], IMD_COLORS, [2,3,4,5,6,7,8,9,10]),
    ladColor: stepExpr(["get", "imd_q"], ["#ab2330","#d96f57","#f2bb91","#fbeada","#fdf6ec"], [2,3,4,5]),
  },
  infra: {
    note: "Community fabric: registered charities and community venues per resident. Darker = denser civic infrastructure.",
    legend: rampLegend(INFRA_COLORS, "thin", "dense"),
    lsoaColor: stepExpr(["get", "iq"], INFRA_COLORS, [2,3,4,5]),
    ladColor: stepExpr(["get", "inf_q"], INFRA_COLORS, [2,3,4,5]),
  },
  comp: {
    note: "Need (deprivation) crossed with readiness (community fabric + existing organisations). Deep plum = high need and strong fabric — fertile ground where it matters most.",
    legend: bivarLegend(),
    lsoaColor: stepExpr(["get", "cmp"], BIVAR, [2,3,4,5,6,7,8,9]),
    ladColor: stepExpr(["get", "cmp"], BIVAR, [2,3,4,5,6,7,8,9]),
  },
};

function stepExpr(input, colors, stops) {
  const e = ["step", input, colors[0]];
  stops.forEach((s, i) => e.push(s, colors[i + 1]));
  return e;
}
function rampLegend(colors, lo, hi) {
  return `<div class="legend-ramp">${colors.map(c => `<div class="cell" style="background:${c}"></div>`).join("")}</div>
          <div class="legend-labels"><span>${lo}</span><span>${hi}</span></div>`;
}
function bivarLegend() {
  // grid rows top→bottom = ready high→low, cols left→right = need low→high
  const order = [6,7,8, 3,4,5, 0,1,2];
  return `<div class="legend-bivar">
    <div class="bivar-grid">${order.map(i => `<div class="cell" style="background:${BIVAR[i]}"></div>`).join("")}</div>
    <div class="bivar-axis">→ need (deprivation)<br>↑ readiness (fabric + orgs)</div></div>`;
}

const fmt = n => n == null ? "–" : n.toLocaleString("en-GB");

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      base: {
        type: "raster",
        tiles: ["https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png"],
        tileSize: 256,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
      },
      labels: {
        type: "raster",
        tiles: ["https://a.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}@2x.png"],
        tileSize: 256,
      },
    },
    layers: [{ id: "base", type: "raster", source: "base" }],
  },
  center: [-1.7, 52.6],
  zoom: 6,
  minZoom: 5,
  maxZoom: 15,
  attributionControl: { compact: true },
  preserveDrawingBuffer: true,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

const state = { metric: "imd", loadedLads: new Set(), lsoaFeatures: [], selected: null };

map.on("load", init);

async function init() {
  // ---- choropleth sources/layers ----
  const lad = await fetchJson(DATA + "lad.geojson");
  map.addSource("lad", { type: "geojson", data: lad || empty(), promoteId: "code" });
  map.addSource("lsoa", { type: "geojson", data: empty(), promoteId: "c" });

  map.addLayer({
    id: "lad-fill", type: "fill", source: "lad", maxzoom: LSOA_ZOOM,
    paint: { "fill-color": METRICS.imd.ladColor, "fill-opacity": 0.78 },
  });
  map.addLayer({
    id: "lsoa-fill", type: "fill", source: "lsoa", minzoom: LSOA_ZOOM,
    paint: {
      "fill-color": METRICS.imd.lsoaColor,
      "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.95, 0.72],
    },
  });
  map.addLayer({
    id: "lsoa-line", type: "line", source: "lsoa", minzoom: LSOA_ZOOM,
    paint: { "line-color": "#ffffff", "line-width": 0.4, "line-opacity": 0.5 },
  });
  map.addLayer({
    id: "lad-line", type: "line", source: "lad",
    paint: { "line-color": "#8a8474", "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.3, 10, 1.2] },
  });
  map.addLayer({
    id: "select-line", type: "line", source: "lsoa", minzoom: LSOA_ZOOM,
    paint: {
      "line-color": "#20251f",
      "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2, 0],
    },
  });

  // ---- overlay sources/layers (each optional) ----
  await addOptionalLayer("dno", "dno.geojson", src => {
    map.addLayer({
      id: "dno-line", type: "line", source: src,
      layout: { visibility: "none" },
      paint: { "line-color": "#5a6052", "line-width": 1.6, "line-dasharray": [3, 2] },
    });
  });

  await addOptionalLayer("grid", "grid.geojson", src => {
    map.addLayer({
      id: "grid-pts", type: "circle", source: src,
      layout: { visibility: "none" },
      paint: {
        "circle-color": ["match", ["get", "rag"], "g", RAG.g, "a", RAG.a, "r", RAG.r, "#999"],
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 1.6, 9, 4, 13, 9],
        "circle-opacity": 0.85,
        "circle-stroke-color": "#fffdf8",
        "circle-stroke-width": 0.6,
      },
    });
  }, "count-grid");

  await addOptionalLayer("infra", "infra.geojson", src => {
    map.addLayer({
      id: "infra-pts", type: "circle", source: src,
      layout: { visibility: "none" },
      paint: {
        "circle-color": "#16808c",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 1.2, 10, 3.2, 14, 6],
        "circle-opacity": 0.75,
        "circle-stroke-color": "#fffdf8",
        "circle-stroke-width": 0.5,
      },
    });
  }, "count-infra");

  await addOptionalLayer("redress", "redress.geojson", src => {
    map.addLayer({
      id: "redress-pts", type: "circle", source: src,
      layout: { visibility: "none" },
      paint: {
        "circle-color": "#7d4fb3",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.8, 10, 6],
        "circle-stroke-color": "#fffdf8",
        "circle-stroke-width": 0.9,
        "circle-opacity": 0.9,
      },
    });
  }, "count-redress");

  await addOptionalLayer("knowledge", "knowledge.geojson", src => {
    map.addLayer({
      id: "knowledge-pts", type: "circle", source: src,
      layout: { visibility: "none" },
      paint: {
        "circle-color": ["match", ["get", "kind"],
          "university", "#2d5fa6", "industry", "#5e83b8", "#15355f"],
        "circle-radius": ["interpolate", ["linear"], ["zoom"],
          5, ["+", 2.5, ["*", 0.35, ["sqrt", ["min", ["coalesce", ["get", "n"], 9], 330]]]],
          10, ["+", 5, ["*", 0.55, ["sqrt", ["min", ["coalesce", ["get", "n"], 9], 330]]]]],
        "circle-stroke-color": "#fffdf8",
        "circle-stroke-width": 0.9,
        "circle-opacity": 0.85,
      },
    });
  }, "count-knowledge");

  const isProj = ["==", ["get", "src"], "cee-map"];
  const orgsData = await addOptionalLayer("orgs", "orgs.geojson", src => {
    map.addLayer({
      id: "proj-pts", type: "circle", source: src, filter: isProj,
      paint: {
        "circle-color": "#2e7d5b",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.4, 10, 5.5],
        "circle-stroke-color": "#fffdf8",
        "circle-stroke-width": 0.8,
        "circle-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "orgs-glow", type: "circle", source: src, filter: ["!", isProj],
      paint: {
        "circle-color": "#e8a013",
        "circle-opacity": 0.25,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 6, 10, 13],
      },
    });
    map.addLayer({
      id: "orgs-pts", type: "circle", source: src, filter: ["!", isProj],
      paint: {
        "circle-color": "#e8a013",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 3, 10, 6.5],
        "circle-stroke-color": "#20251f",
        "circle-stroke-width": 1.1,
      },
    });
  }, "count-orgs");
  if (orgsData) {
    const nProj = orgsData.features.filter(f => f.properties.src === "cee-map").length;
    document.getElementById("count-orgs").textContent = fmt(orgsData.features.length - nProj);
    document.getElementById("count-proj").textContent = fmt(nProj);
  }

  // raster labels above everything polygonal
  map.addLayer({ id: "labels", type: "raster", source: "labels", paint: { "raster-opacity": 0.9 } });

  wireInteractions();
  wireUi();
  refreshLsoaViewport();
  map.on("moveend", refreshLsoaViewport);
  updateZoomHint();
  map.on("zoom", updateZoomHint);
}

function empty() { return { type: "FeatureCollection", features: [] }; }

async function fetchJson(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

async function addOptionalLayer(name, file, addFn, countElId) {
  const data = await fetchJson(DATA + file);
  const toggle = document.getElementById("tgl-" + name);
  if (!data || !data.features || !data.features.length) {
    if (toggle) { toggle.disabled = true; toggle.closest(".layer-toggle").style.opacity = 0.4; }
    return;
  }
  map.addSource(name, { type: "geojson", data });
  addFn(name);
  if (countElId) document.getElementById(countElId).textContent = fmt(data.features.length);
  return data;
}

/* ---- on-demand LSOA loading ---- */
async function refreshLsoaViewport() {
  if (map.getZoom() < LSOA_ZOOM - 0.4) return;
  const lads = map.queryRenderedFeatures({ layers: ["lad-fill", "lad-line"] })
    .map(f => f.properties.code)
    .filter(c => c && !state.loadedLads.has(c));
  const unique = [...new Set(lads)];
  if (!unique.length) return;
  unique.forEach(c => state.loadedLads.add(c));
  const chunks = await Promise.all(unique.map(c => fetchJson(`${DATA}lsoa/${c}.json`)));
  let added = false;
  chunks.forEach((fc, i) => {
    if (fc && fc.features) { state.lsoaFeatures.push(...fc.features); added = true; }
    else state.loadedLads.delete(unique[i]);
  });
  if (added) map.getSource("lsoa").setData({ type: "FeatureCollection", features: state.lsoaFeatures });
}

function updateZoomHint() {
  document.getElementById("zoom-hint").classList.toggle("show",
    map.getZoom() >= 6.8 && map.getZoom() < LSOA_ZOOM);
}

/* ---- interactions ---- */
function wireInteractions() {
  for (const layer of ["lad-fill", "lsoa-fill"]) {
    map.on("mousemove", layer, () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", layer, () => map.getCanvas().style.cursor = "");
  }
  map.on("click", "lsoa-fill", e => { selectLsoa(e.features[0]); });
  map.on("click", "lad-fill", e => { showLadDetail(e.features[0].properties); });

  const popup = (e, html) => new maplibregl.Popup({ closeButton: false })
    .setLngLat(e.lngLat).setHTML(html).addTo(map);

  const orgPopup = e => {
    const p = e.features[0].properties;
    const srcLabel = { "cee-map": "project site", fca: "FCA register", cee: "CEE member",
                       "fca+cee": "FCA + CEE", charity: "charity" }[p.src] || p.src;
    popup(e, `<h4>${esc(p.name)}</h4>
      ${(p.kind ? `<span class="tag">${esc(p.kind)}</span>` : "")}
      <span class="tag">${esc(srcLabel || "")}</span>
      <p>${p.pc ? esc(p.pc) + " · " : ""}${esc(p.lad || "")}</p>
      ${p.url ? `<p><a href="${esc(p.url)}" target="_blank" rel="noopener">website</a></p>` : ""}`);
    e.preventDefault();
  };
  map.on("click", "orgs-pts", orgPopup);
  map.on("click", "proj-pts", orgPopup);

  map.on("click", "redress-pts", e => {
    const p = e.features[0].properties;
    popup(e, `<h4>${esc(p.name)}</h4>
      <span class="tag">Energy Redress grantee</span>
      <span class="tag">${p.loc === "area" ? "project area" : "registered office"}</span>
      <p>${p.n || 1} funded project${p.n > 1 ? "s" : ""}${p.total ? " · £" + fmt(+p.total) : ""}</p>
      ${p.projects ? `<p>${esc(p.projects)}</p>` : ""}
      ${p.url ? `<p><a href="${esc(p.url)}" target="_blank" rel="noopener">website</a></p>` : ""}`);
    e.preventDefault();
  });

  map.on("click", "knowledge-pts", e => {
    const p = e.features[0].properties;
    const kindLabel = { university: "University energy research", industry: "Industry energy R&D",
                        dno: "Network operator HQ", system: "System operator",
                        research: "Research centre", agency: "Regulator",
                        intermediary: "Sector intermediary", supplier: "Supplier HQ" }[p.kind] || p.kind;
    popup(e, `<h4>${esc(p.name)}</h4>
      <span class="tag">${esc(kindLabel)}</span>
      ${p.n ? `<p>${fmt(+p.n)} UKRI energy research projects · ${fmt(+p.active || 0)} active</p>` : ""}
      ${p.note ? `<p>${esc(p.note)}</p>` : ""}
      ${p.url ? `<p><a href="${esc(p.url)}" target="_blank" rel="noopener">website</a></p>` : ""}`);
    e.preventDefault();
  });
  map.on("click", "infra-pts", e => {
    const p = e.features[0].properties;
    popup(e, `<h4>${esc(p.name || "Community venue")}</h4><span class="tag">${esc((p.kind || "").replace(/_/g, " "))}</span>`);
    e.preventDefault();
  });
  map.on("click", "grid-pts", e => {
    const p = e.features[0].properties;
    const rag = { g: "headroom available", a: "limited headroom", r: "constrained" }[p.rag] || "";
    popup(e, `<h4>${esc(p.name)}</h4><span class="tag">${esc(p.dno)}</span><span class="tag">${rag}</span>
      <p>Demand headroom: <strong>${p.dh != null ? (+p.dh).toFixed(1) + " MVA" : "n/a"}</strong><br>
      Generation headroom: <strong>${p.gh != null ? (+p.gh).toFixed(1) + " MVA" : "n/a"}</strong></p>`);
    e.preventDefault();
  });
}

function selectLsoa(f) {
  if (state.selected) map.setFeatureState({ source: "lsoa", id: state.selected }, { selected: false });
  state.selected = f.id ?? f.properties.c;
  map.setFeatureState({ source: "lsoa", id: state.selected }, { selected: true });
  showLsoaDetail(f.properties);
}

function decilePips(d) {
  return `<div class="decile-pips">${Array.from({ length: 10 }, (_, i) =>
    `<span style="${i < 11 - d ? `background:${IMD_COLORS[Math.max(0, d - 1)]}` : ""}"></span>`).join("")}</div>`;
}

function showLsoaDetail(p) {
  const cmpLabel = ["low need · thin fabric","mid need · thin fabric","high need · thin fabric",
                    "low need · mid fabric","mid need · mid fabric","high need · mid fabric",
                    "low need · strong fabric","mid need · strong fabric","high need · strong fabric"][p.cmp - 1] || "–";
  document.getElementById("detail").innerHTML = `<div class="detail-card">
    <h3>${esc(p.n || p.c)}</h3>
    <div class="sub">Neighbourhood (LSOA) · ${esc(p.ladn || "")}</div>
    <div class="stat-row"><span class="k">IMD decile (1 = most deprived)</span><span class="v">${p.d ?? "–"}</span></div>
    ${p.d ? decilePips(p.d) : ""}
    <div class="stat-row"><span class="k">IMD rank of 33,755</span><span class="v">${fmt(p.r)}</span></div>
    <div class="stat-row"><span class="k">Population</span><span class="v">${fmt(p.pop)}</span></div>
    <div class="stat-row"><span class="k">Energy orgs registered here</span><span class="v">${p.org || 0}</span></div>
    <div class="stat-row"><span class="k">Community venues</span><span class="v">${p.inf || 0}</span></div>
    <div class="stat-row"><span class="k">Need × readiness</span><span class="v">${cmpLabel}</span></div>
  </div>`;
}

function showLadDetail(p) {
  document.getElementById("detail").innerHTML = `<div class="detail-card">
    <h3>${esc(p.name)}</h3>
    <div class="sub">Local authority</div>
    <div class="stat-row"><span class="k">Population</span><span class="v">${fmt(p.pop)}</span></div>
    <div class="stat-row"><span class="k">Avg IMD score (pop-weighted)</span><span class="v">${p.imd_s != null ? (+p.imd_s).toFixed(1) : "–"}</span></div>
    <div class="stat-row"><span class="k">Share of LSOAs in most deprived 20%</span><span class="v">${p.pct12 != null ? Math.round(p.pct12 * 100) + "%" : "–"}</span></div>
    <div class="stat-row"><span class="k">Community energy organisations</span><span class="v">${p.orgs || 0}</span></div>
    <div class="stat-row"><span class="k">Community venues</span><span class="v">${fmt(p.inf)}</span></div>
    <div class="stat-row"><span class="k">Zoom in</span><span class="v">neighbourhood detail</span></div>
  </div>`;
}

/* ---- UI ---- */
function wireUi() {
  document.querySelectorAll(".metric-tab").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".metric-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      setMetric(btn.dataset.metric);
    });
  });
  setMetric("imd");

  const toggles = { orgs: ["orgs-pts", "orgs-glow"], proj: ["proj-pts"],
                    redress: ["redress-pts"], knowledge: ["knowledge-pts"],
                    infra: ["infra-pts"], grid: ["grid-pts"], dno: ["dno-line"] };
  for (const [name, layers] of Object.entries(toggles)) {
    const el = document.getElementById("tgl-" + name);
    el.addEventListener("change", () => {
      layers.forEach(l => map.getLayer(l) &&
        map.setLayoutProperty(l, "visibility", el.checked ? "visible" : "none"));
    });
  }

  document.getElementById("about-btn").addEventListener("click", () =>
    document.getElementById("about-modal").classList.remove("hidden"));
  document.getElementById("about-close").addEventListener("click", () =>
    document.getElementById("about-modal").classList.add("hidden"));
  document.getElementById("about-modal").addEventListener("click", e => {
    if (e.target.id === "about-modal") e.target.classList.add("hidden");
  });

  wireSearch();
}

function setMetric(m) {
  state.metric = m;
  const cfg = METRICS[m];
  document.getElementById("metric-note").textContent = cfg.note;
  document.getElementById("legend").innerHTML = cfg.legend;
  if (map.getLayer("lsoa-fill")) map.setPaintProperty("lsoa-fill", "fill-color", cfg.lsoaColor);
  if (map.getLayer("lad-fill")) map.setPaintProperty("lad-fill", "fill-color", cfg.ladColor);
}

function wireSearch() {
  const input = document.getElementById("search");
  const results = document.getElementById("search-results");
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { results.innerHTML = ""; return; }
    timer = setTimeout(() => doSearch(q), 350);
  });
  async function doSearch(q) {
    let hits = [];
    const pc = await fetchJson("https://api.postcodes.io/postcodes?q=" + encodeURIComponent(q) + "&limit=4");
    if (pc && pc.result) {
      hits = pc.result.filter(r => r.country === "England")
        .map(r => ({ label: `${r.postcode} · ${r.admin_district}`, lon: r.longitude, lat: r.latitude, z: 12 }));
    }
    if (!hits.length) {
      const nm = await fetchJson("https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=gb&limit=4&q=" + encodeURIComponent(q));
      if (nm) hits = nm.map(r => ({ label: r.display_name.split(",").slice(0, 2).join(","), lon: +r.lon, lat: +r.lat, z: 11 }));
    }
    results.innerHTML = hits.map((h, i) => `<div data-i="${i}">${esc(h.label)}</div>`).join("");
    results.querySelectorAll("div").forEach(el => el.addEventListener("click", () => {
      const h = hits[+el.dataset.i];
      map.flyTo({ center: [h.lon, h.lat], zoom: h.z });
      results.innerHTML = ""; input.value = h.label;
    }));
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
