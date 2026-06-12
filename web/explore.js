/* Community Energy Explorer — data explorer (explore.html).
 * Consumes web/data/explore.json (one record per English local authority).
 * Four lenses: ranked table, opportunity typology, mismatch finder, redress vs need.
 * Deep links: ?lad=<code> opens the authority drawer; #<lens> selects a lens.
 */
"use strict";

const fmt = n => n == null || Number.isNaN(n) ? "–" : Math.round(n).toLocaleString("en-GB");
const pct = p => p == null ? "–" : Math.round(p * 100) + "";
const ord = p => { // percentile 0..1 → "67th"
  if (p == null) return "–";
  const n = Math.round(p * 100), v = n % 100;
  return n + (["th", "st", "nd", "rd"][(v - 20) % 10] || ["th", "st", "nd", "rd"][v] || "th");
};
const gbp = n => !n ? "£0" : n >= 1e6 ? "£" + (n / 1e6).toFixed(1) + "m" : "£" + Math.round(n / 1e3) + "k";
const kw = n => !n ? "–" : n >= 1000 ? (n / 1000).toFixed(1) + " MW" : Math.round(n) + " kW";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const median = a => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

const TYP = {
  thriving:   { label: "Thriving",  blurb: "good conditions, lots of community energy", order: 1 },
  latent:     { label: "Latent",    blurb: "good conditions, little community energy yet — easy wins", order: 2 },
  pioneering: { label: "Pioneering", blurb: "community energy despite thin conditions", order: 3 },
  cold:       { label: "Cold",      blurb: "thin conditions and little community energy", order: 4 },
};
const IMD_Q = ["#cb4b3a", "#e0855a", "#f0bd87", "#cdd9c4", "#9fb59a"]; // q1 most deprived → q5

let DATA = null, LADS = [], MED = {}, RANKS = {};
let sortKey = "name", sortDir = 1, lens = "table";

init();

async function init() {
  const r = await fetch("data/explore.json");
  DATA = await r.json();
  LADS = DATA.lads;
  MED = { ready: median(LADS.map(d => d.ready_p)), pres: median(LADS.map(d => d.presence_p)) };
  // dense ranks (1 = best) for opportunity and struggle, for "#n of 296" context
  RANKS = {
    opportunity: rankOf(LADS, d => -d.opportunity),
    struggle: rankOf(LADS, d => -d.struggle),
  };
  renderStrip();
  renderFindings();
  document.querySelectorAll(".lens-tab").forEach(b =>
    b.addEventListener("click", () => switchLens(b.dataset.lens, true)));
  document.getElementById("method-btn").onclick = () =>
    document.getElementById("method-modal").classList.remove("hidden");
  document.getElementById("method-close").onclick = () =>
    document.getElementById("method-modal").classList.add("hidden");
  document.getElementById("method-modal").onclick = e => {
    if (e.target.id === "method-modal") e.target.classList.add("hidden"); };
  document.getElementById("drawer-close").onclick = closeDrawer;
  document.getElementById("drawer-scrim").onclick = closeDrawer;

  const wanted = location.hash.replace("#", "");
  switchLens(TYP_LENSES.includes(wanted) ? wanted : "table");
  const lad = new URLSearchParams(location.search).get("lad");
  if (lad) openDrawer(lad);
}

const TYP_LENSES = ["table", "typology", "mismatch", "redress"];

function rankOf(arr, key) {
  const sorted = [...arr].sort((a, b) => key(a) - key(b));
  const m = {};
  sorted.forEach((d, i) => m[d.code] = i + 1);
  return m;
}

function pearson(x, y) {
  const n = x.length, mx = x.reduce((a, b) => a + b, 0) / n, my = y.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { const dx = x[i] - mx, dy = y[i] - my; sxy += dx * dy; sx += dx * dx; sy += dy * dy; }
  return sx && sy ? sxy / Math.sqrt(sx * sy) : 0;
}

function renderStrip() {
  const n = DATA.national;
  const cells = [
    [n.lads, "local authorities"],
    [n.ce_orgs + " + " + n.ce_sites, "orgs + project sites"],
    [n.cap_mw + " MW", "known installed capacity"],
    [n.lads_no_ce, "authorities with none"],
    [gbp(n.redress_total), "Energy Redress funding"],
  ];
  document.getElementById("stat-strip").innerHTML = cells.map(([v, k]) =>
    `<div class="stat"><div class="stat-v">${typeof v === "number" ? fmt(v) : v}</div>
     <div class="stat-k">${k}</div></div>`).join("");
}

/* Headline findings, computed from the data so they stay honest when it updates. */
function renderFindings() {
  const need = LADS.map(d => d.need_p);
  const rPres = pearson(need, LADS.map(d => d.presence_p));
  const rReady = pearson(need, LADS.map(d => d.ready_p));
  const rRedress = pearson(need, LADS.map(d => Math.log10(d.redress_total / Math.max(d.pop, 1) + 1)));
  const caps = LADS.map(d => d.cap_kw).sort((a, b) => b - a);
  const capShare = Math.round(caps.slice(0, 10).reduce((a, b) => a + b, 0) /
                              Math.max(caps.reduce((a, b) => a + b, 0), 1) * 100);
  const nLatent = LADS.filter(d => d.typology === "latent").length;
  const tilt = r => Math.abs(r) < 0.1 ? "barely tracks" : r > 0 ? "tilts towards" : "tilts away from";
  const items = [
    `<strong>Known capacity is concentrated:</strong> the top 10 authorities hold
     <strong>${capShare}%</strong> of all recorded community-energy capacity.`,
    `<strong>Community energy ${tilt(rPres)} deprivation</strong>
     (r&nbsp;=&nbsp;${rPres.toFixed(2)}) — and the enabling conditions are skewed further still
     (readiness vs need r&nbsp;=&nbsp;${rReady.toFixed(2)}).`,
    `<strong>Redress funding ${tilt(rRedress)} deprivation</strong>
     (£/person vs need, r&nbsp;=&nbsp;${rRedress.toFixed(2)}) — the
     <a href="#redress" data-lens-link="redress">redress lens</a> shows who still gets neither.`,
    `<strong>${nLatent} authorities look ready but near-empty</strong> — the
     <a href="#typology" data-lens-link="typology">latent quadrant</a>, where the sector could
     most easily grow next.`,
  ];
  const el = document.getElementById("findings");
  if (!el) return;
  el.innerHTML = `<h2 class="findings-h">What the data says</h2>
    <ul class="findings-list">${items.map(i => `<li>${i}</li>`).join("")}</ul>`;
  el.querySelectorAll("[data-lens-link]").forEach(a => a.onclick = e => {
    e.preventDefault(); switchLens(a.dataset.lensLink, true);
    document.getElementById("lens-tabs").scrollIntoView({ behavior: "smooth" });
  });
}

function switchLens(l, pushHash) {
  lens = l;
  if (pushHash) history.replaceState(null, "", location.pathname + location.search + "#" + l);
  document.querySelectorAll(".lens-tab").forEach(b => b.classList.toggle("active", b.dataset.lens === l));
  ({ table: renderTable, typology: renderTypology, mismatch: renderMismatch, redress: renderRedress }[l])();
}

/* ---------------- Lens 1: ranked table ---------------- */
const COLS = [
  { k: "name", label: "Local authority", align: "left" },
  { k: "pop", label: "Pop", fmt: fmt },
  { k: "need_p", label: "Need", title: "Deprivation percentile (0–100, higher = more deprived)", fmt: v => pct(v), bar: "need" },
  { k: "ready_p", label: "Ready", title: "Enabling-conditions percentile (civic fabric, knowledge nearby, grid headroom)", fmt: v => pct(v), bar: "ready" },
  { k: "presence_p", label: "Presence", title: "Community energy on the ground, percentile (0 = none at all)", fmt: v => pct(v), bar: "pres" },
  { k: "opportunity", label: "Opp", title: "Readiness − presence: high = ready but little here yet", fmt: v => signed(v), diverge: true },
  { k: "ce_orgs", label: "Orgs", fmt: v => v || "0" },
  { k: "ce_sites", label: "Sites", fmt: v => v || "0" },
  { k: "cap_kw", label: "Capacity", fmt: kw },
  { k: "redress_total", label: "Redress", fmt: gbp },
  { k: "typology", label: "Type", fmt: v => `<span class="badge ${v}">${TYP[v].label}</span>` },
];
const signed = v => (v > 0 ? "+" : "") + (+v).toFixed(2);
const KW_STOPS = [0, 50, 100, 250, 500, 1000, 5000];
const tstate = { q: "", typ: "all", minkw: 0, quick: "all" };

function renderTable() {
  document.getElementById("lens-panel").innerHTML = `
    <p class="lens-intro">Every authority and metric — click a column to sort, a row for detail.
    Need, Ready and Presence are <strong>percentiles (0–100)</strong> across the ${LADS.length}
    authorities; Presence 0 means no community energy at all.</p>
    <div class="controls">
      <input id="t-search" class="ctrl-input" type="text" placeholder="Search authority…" value="${esc(tstate.q)}">
      <select id="t-typ" class="ctrl-input">
        <option value="all">All types</option>
        ${Object.entries(TYP).map(([k, v]) => `<option value="${k}" ${tstate.typ === k ? "selected" : ""}>${v.label}</option>`).join("")}
      </select>
      <select id="t-quick" class="ctrl-input">
        <option value="all">All authorities</option>
        <option value="none" ${tstate.quick === "none" ? "selected" : ""}>No community energy</option>
        <option value="redress_no_ce" ${tstate.quick === "redress_no_ce" ? "selected" : ""}>Redress but no community energy</option>
        <option value="high_need" ${tstate.quick === "high_need" ? "selected" : ""}>Most deprived third</option>
      </select>
      <span class="ctrl-chips" id="t-kw-chips" title="Show only authorities with at least one project of this size">
        <span class="chips-label">Biggest project ≥</span>
        ${KW_STOPS.map(v => `<button class="chip ${tstate.minkw === v ? "on" : ""}" data-kw="${v}">${v ? kw(v) : "any"}</button>`).join("")}
      </span>
      <span class="ctrl-spacer"></span>
      <span id="t-count" class="ctrl-count"></span>
      <button id="t-csv" class="link-btn">Download CSV</button>
    </div>
    <div class="table-scroll"><table class="data-table"><thead><tr>
      ${COLS.map(c => `<th data-k="${c.k}" ${c.title ? `title="${esc(c.title)}"` : ""}
        class="${c.align === "left" ? "tl" : ""} ${c.k === sortKey ? "sorted " + (sortDir > 0 ? "asc" : "desc") : ""}">${c.label}</th>`).join("")}
    </tr></thead><tbody id="t-body"></tbody></table></div>`;

  document.getElementById("t-search").oninput = e => { tstate.q = e.target.value; fillTable(); };
  document.getElementById("t-typ").onchange = e => { tstate.typ = e.target.value; fillTable(); };
  document.getElementById("t-quick").onchange = e => { tstate.quick = e.target.value; fillTable(); };
  document.querySelectorAll("#t-kw-chips .chip").forEach(ch => ch.onclick = () => {
    tstate.minkw = +ch.dataset.kw;
    document.querySelectorAll("#t-kw-chips .chip").forEach(c =>
      c.classList.toggle("on", +c.dataset.kw === tstate.minkw));
    fillTable();
  });
  document.querySelectorAll(".data-table th").forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = k === "name" ? 1 : -1; }
    renderTable();
  });
  document.getElementById("t-csv").onclick = downloadCsv;
  fillTable();
}

function filteredRows() {
  const q = tstate.q.trim().toLowerCase();
  return LADS.filter(d => {
    if (q && !d.name.toLowerCase().includes(q)) return false;
    if (tstate.typ !== "all" && d.typology !== tstate.typ) return false;
    if (tstate.minkw && d.biggest_kw < tstate.minkw) return false;
    if (tstate.quick === "none" && d.ce_total > 0) return false;
    if (tstate.quick === "redress_no_ce" && !(d.redress_grantees > 0 && d.ce_total === 0)) return false;
    if (tstate.quick === "high_need" && d.need_p < 2 / 3) return false;
    return true;
  });
}

function fillTable() {
  const rows = filteredRows().sort((a, b) => {
    if (sortKey === "typology") return sortDir * (TYP[a.typology].order - TYP[b.typology].order);
    const x = a[sortKey], y = b[sortKey];
    if (typeof x === "string") return sortDir * x.localeCompare(y);
    return sortDir * ((x ?? 0) - (y ?? 0));
  });
  document.getElementById("t-count").textContent = `${rows.length} of ${LADS.length}`;
  document.getElementById("t-body").innerHTML = rows.map(d => `<tr data-code="${d.code}">
    ${COLS.map(c => {
      const v = d[c.k];
      const disp = c.fmt ? c.fmt(v) : v;
      if (c.bar) return `<td class="num"><span class="minibar"><i style="width:${pct(v)}%"></i></span>${disp}</td>`;
      if (c.diverge) return `<td class="num ${v > 0.15 ? "pos" : v < -0.15 ? "neg" : ""}">${disp}</td>`;
      return `<td class="${c.align === "left" ? "tl" : "num"}">${disp}</td>`;
    }).join("")}
  </tr>`).join("");
  document.querySelectorAll("#t-body tr").forEach(tr =>
    tr.onclick = () => openDrawer(tr.dataset.code));
}

function downloadCsv() {
  const keys = ["code", "name", "pop", "need_p", "ready_p", "presence_p", "ce_orgs", "ce_sites",
    "cap_kw", "cap_sites", "biggest_kw", "redress_grantees", "redress_total", "know_km", "know_name",
    "grid_green", "opportunity", "struggle", "typology"];
  const rows = filteredRows();
  const csv = [keys.join(",")].concat(rows.map(d =>
    keys.map(k => { const v = d[k]; return typeof v === "string" && v.includes(",") ? `"${v}"` : v; }).join(","))).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = "community-energy-by-authority.csv";
  a.click();
}

/* ---------------- Lens 2: opportunity typology ---------------- */
function renderTypology() {
  const W = 760, H = 560, PAD = 54;
  const sx = v => PAD + v * (W - 2 * PAD);
  const sy = v => H - PAD - v * (H - 2 * PAD);
  const counts = {};
  LADS.forEach(d => counts[d.typology] = (counts[d.typology] || 0) + 1);
  const quads = [
    { t: "thriving", at: [0.80, 0.93] },    // high ready, high presence — top-right
    { t: "latent", at: [0.80, 0.07] },      // high ready, low presence  — bottom-right
    { t: "pioneering", at: [0.16, 0.93] },  // low ready, high presence  — top-left
    { t: "cold", at: [0.16, 0.07] },        // low ready, low presence   — bottom-left
  ];
  const dots = LADS.map(d => `<circle cx="${sx(d.ready_p).toFixed(1)}" cy="${sy(d.presence_p).toFixed(1)}"
     r="${(2.5 + Math.sqrt(d.pop) / 90).toFixed(1)}" fill="${IMD_Q[d.imd_q - 1]}" fill-opacity="0.82"
     stroke="#20251f" stroke-width="0.4" data-code="${d.code}" class="dot"><title>${esc(d.name)} — ready ${pct(d.ready_p)}, presence ${pct(d.presence_p)}</title></circle>`).join("");
  const qbg = `
    <rect x="${sx(MED.ready)}" y="${PAD}" width="${W - PAD - sx(MED.ready)}" height="${sy(MED.pres) - PAD}" class="q q-thriving"/>
    <rect x="${PAD}" y="${PAD}" width="${sx(MED.ready) - PAD}" height="${sy(MED.pres) - PAD}" class="q q-pioneering"/>
    <rect x="${sx(MED.ready)}" y="${sy(MED.pres)}" width="${W - PAD - sx(MED.ready)}" height="${H - PAD - sy(MED.pres)}" class="q q-latent"/>
    <rect x="${PAD}" y="${sy(MED.pres)}" width="${sx(MED.ready) - PAD}" height="${H - PAD - sy(MED.pres)}" class="q q-cold"/>`;
  const qlabels = quads.map(q => `<text x="${sx(q.at[0])}" y="${sy(q.at[1])}" class="qlab badge-${q.t}" text-anchor="middle">${TYP[q.t].label.toUpperCase()} · ${counts[q.t] || 0}</text>`).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(v => `
    <text x="${sx(v)}" y="${H - PAD + 16}" text-anchor="middle" class="tick">${v * 100}</text>
    <text x="${PAD - 8}" y="${sy(v) + 3}" text-anchor="end" class="tick">${v * 100}</text>`).join("");

  document.getElementById("lens-panel").innerHTML = `
    <p class="lens-intro">Each authority placed by <strong>readiness</strong> (enabling conditions, →)
    against <strong>community-energy presence</strong> (↑), both percentiles. Dot colour is deprivation
    (red = most deprived), size is population. The bottom-right
    <span class="badge latent">Latent</span> quadrant — ready but empty — is where the sector could
    most easily grow. Click any dot or name.</p>
    <div class="typo-wrap">
      <svg viewBox="0 0 ${W} ${H}" class="scatter" id="scatter">
        ${qbg}
        <line x1="${sx(MED.ready)}" y1="${PAD}" x2="${sx(MED.ready)}" y2="${H - PAD}" class="med"/>
        <line x1="${PAD}" y1="${sy(MED.pres)}" x2="${W - PAD}" y2="${sy(MED.pres)}" class="med"/>
        ${qlabels}
        ${ticks}
        ${dots}
        <text x="${W / 2}" y="${H - 8}" text-anchor="middle" class="axlab">Readiness — enabling conditions →</text>
        <text x="14" y="${H / 2}" text-anchor="middle" class="axlab" transform="rotate(-90 14 ${H / 2})">Community-energy presence →</text>
      </svg>
      <div class="typo-side" id="typo-lists"></div>
    </div>`;

  const lists = [
    ["latent", "Easy wins — ready, but little here yet", d => d.typology === "latent", (a, b) => b.opportunity - a.opportunity,
      d => "ready " + ord(d.ready_p) + " · " + (d.ce_total ? d.ce_total + " CE" : "none")],
    ["cold", "Hardest ground — deprived & thin", d => d.typology === "cold", (a, b) => b.struggle - a.struggle,
      d => "need " + ord(d.need_p) + " pctile"],
  ];
  document.getElementById("typo-lists").innerHTML = lists.map(([t, title, f, s, note]) => {
    const items = LADS.filter(f).sort(s).slice(0, 8);
    return `<div class="typo-list"><h3><span class="badge ${t}">${TYP[t].label}</span> ${title}</h3>
      <ol>${items.map(d => `<li data-code="${d.code}"><span>${esc(d.name)}</span>
        <em>${note(d)}</em></li>`).join("")}</ol></div>`;
  }).join("");

  document.querySelectorAll("#scatter .dot").forEach(c => c.onclick = () => openDrawer(c.dataset.code));
  document.querySelectorAll("#typo-lists li").forEach(li => li.onclick = () => openDrawer(li.dataset.code));
}

/* ---------------- Lens 3: mismatch finder ---------------- */
function renderMismatch() {
  const lo = 1 / 3, hi = 2 / 3;
  const cards = [
    {
      title: "Civic fabric without the energy",
      sub: "Top-fifth community fabric, but little community energy — organising capacity waiting to be tapped.",
      f: d => d.inf_q >= 4 && d.presence_p < lo,
      s: (a, b) => b.infra_per_1k - a.infra_per_1k,
      note: d => `${d.infra_per_1k.toFixed(1)} venues+charities / 1k`,
    },
    {
      title: "Knowledge on the doorstep",
      sub: "An energy knowledge base within 10 km, yet no community-energy organisation — a link not being made.",
      f: d => d.know_km <= 10 && d.ce_orgs === 0,
      s: (a, b) => a.know_km - b.know_km,
      note: d => `${d.know_km} km to ${esc(shortName(d.know_name))}`,
    },
    {
      title: "Grid headroom going spare",
      sub: "Green substations with capacity to connect, but thin community energy (Northern Powergrid & SSEN areas only).",
      f: d => d.grid_green >= 1 && d.presence_p < lo,
      s: (a, b) => b.grid_green - a.grid_green,
      note: d => `${d.grid_green} green substation${d.grid_green > 1 ? "s" : ""}`,
    },
    {
      title: "Deprived and overlooked",
      sub: "Most-deprived third with no community energy and no Energy Redress funding — neither grown nor reached.",
      f: d => d.need_p >= hi && d.ce_total === 0 && d.redress_grantees === 0,
      s: (a, b) => b.need_p - a.need_p,
      note: d => `need ${ord(d.need_p)} pctile`,
    },
  ];
  document.getElementById("lens-panel").innerHTML = `
    <p class="lens-intro">Places where one ingredient is present but another is missing — the gaps
    where a small intervention could unlock a lot. Counts are over all ${LADS.length} authorities.</p>
    <div class="mismatch-grid">${cards.map(c => {
      const items = LADS.filter(c.f).sort(c.s);
      return `<div class="mm-card"><div class="mm-head"><h3>${c.title}</h3>
        <span class="mm-count">${items.length}</span></div>
        <p class="mm-sub">${c.sub}</p>
        <ol>${items.slice(0, 10).map(d => `<li data-code="${d.code}"><span>${esc(d.name)}</span>
          <em>${c.note(d)}</em></li>`).join("") || "<li class='mm-empty'>None</li>"}</ol>
        ${items.length > 10 ? `<div class="mm-more">+${items.length - 10} more</div>` : ""}</div>`;
    }).join("")}</div>`;
  document.querySelectorAll(".mm-card li[data-code]").forEach(li => li.onclick = () => openDrawer(li.dataset.code));
}

const shortName = s => String(s || "").replace(/^(University of |The )/, "").slice(0, 26);

/* ---------------- Lens 4: redress vs need ---------------- */
function renderRedress() {
  const withpc = LADS.map(d => ({ ...d, rpc: d.redress_total / Math.max(d.pop, 1) }));
  const r = pearson(withpc.map(d => d.need_p), withpc.map(d => Math.log10(d.rpc + 1)));
  const verdict = r >= 0.3 ? "the money does broadly follow need"
    : r >= 0.1 ? "the money leans towards need, but only weakly"
    : r >= -0.1 ? "the money barely tracks need at all"
    : "the money tilts away from need";
  const W = 760, H = 460, PAD = 56;
  const maxrpc = Math.max(...withpc.map(d => d.rpc));
  const sx = v => PAD + v * (W - 2 * PAD);
  const sy = v => H - PAD - (Math.log10(v + 1) / Math.log10(maxrpc + 1)) * (H - 2 * PAD);
  const dots = withpc.map(d => `<circle cx="${sx(d.need_p).toFixed(1)}" cy="${sy(d.rpc).toFixed(1)}"
     r="${d.ce_total === 0 ? 4 : 3}" fill="${d.ce_total === 0 ? "#cb4b3a" : "#2e7d5b"}"
     fill-opacity="0.75" stroke="#20251f" stroke-width="0.4" data-code="${d.code}" class="dot">
     <title>${esc(d.name)} — ${gbp(d.redress_total)} (${d.rpc >= 0.005 ? "£" + d.rpc.toFixed(2) : "£0"}/person)</title></circle>`).join("");

  const gap = withpc.filter(d => d.need_p >= 2 / 3 && d.redress_total === 0 && d.ce_total === 0)
    .sort((a, b) => b.need_p - a.need_p).slice(0, 10);
  const vacuum = withpc.filter(d => d.redress_grantees > 0 && d.ce_orgs === 0)
    .sort((a, b) => b.redress_total - a.redress_total).slice(0, 10);
  const top = [...withpc].sort((a, b) => b.redress_total - a.redress_total).slice(0, 10);

  document.getElementById("lens-panel").innerHTML = `
    <p class="lens-intro">Energy Redress funds energy-hardship projects — a marker of <em>recognised</em>
    need being acted on. Plotting it against deprivation shows how well the money tracks need, and where
    deprived places get <strong>neither</strong> redress nor community energy.
    <span class="rstat">Redress £/person vs deprivation: <strong>r = ${r.toFixed(2)}</strong> — ${verdict}.</span></p>
    <div class="typo-wrap">
      <svg viewBox="0 0 ${W} ${H}" class="scatter" id="rscatter">
        ${dots}
        <text x="${W / 2}" y="${H - 14}" text-anchor="middle" class="axlab">Deprivation (need) →</text>
        <text x="16" y="${H / 2}" text-anchor="middle" class="axlab" transform="rotate(-90 16 ${H / 2})">Redress £ per person (log) →</text>
        <text x="${sx(0.02)}" y="${PAD - 12}" class="axlab small">● red = no community energy locally</text>
      </svg>
      <div class="typo-side">
        ${listBlock("Deprived, but neither redress nor community energy", gap, d => "need " + ord(d.need_p))}
        ${listBlock("Redress filling a vacuum (funded, but no local org)", vacuum, d => gbp(d.redress_total))}
        ${listBlock("Most redress funding", top, d => gbp(d.redress_total))}
      </div>
    </div>`;
  document.querySelectorAll("#rscatter .dot").forEach(c => c.onclick = () => openDrawer(c.dataset.code));
  document.querySelectorAll(".typo-side li[data-code]").forEach(li => li.onclick = () => openDrawer(li.dataset.code));
}

function listBlock(title, items, note) {
  return `<div class="typo-list"><h3>${title}</h3>
    <ol>${items.map(d => `<li data-code="${d.code}"><span>${esc(d.name)}</span><em>${note(d)}</em></li>`).join("")
      || "<li class='mm-empty'>None</li>"}</ol></div>`;
}

/* ---------------- detail drawer ---------------- */
function openDrawer(code) {
  const d = LADS.find(x => x.code === code);
  if (!d) return;
  const N = LADS.length;
  const row = (k, v) => `<div class="d-row"><span>${k}</span><strong>${v}</strong></div>`;
  const axis = (k, v) => `<div class="d-axis"><span>${k}</span><span class="minibar wide"><i style="width:${pct(v)}%"></i></span><b>${ord(v)}</b></div>`;
  document.getElementById("drawer-body").innerHTML = `
    <div class="d-kicker">Local authority · <span class="badge ${d.typology}">${TYP[d.typology].label}</span></div>
    <h2>${esc(d.name)}</h2>
    <p class="d-typblurb">${TYP[d.typology].blurb}</p>
    <div class="d-axes">
      ${axis("Need (deprivation)", d.need_p)}
      ${axis("Readiness (conditions)", d.ready_p)}
      ${axis("Community-energy presence", d.presence_p)}
    </div>
    <div class="d-scores">
      <div class="d-score"><span>Opportunity rank</span><b>#${RANKS.opportunity[d.code]}</b>
        <i>of ${N} — ready but unserved</i></div>
      <div class="d-score"><span>Struggle rank</span><b>#${RANKS.struggle[d.code]}</b>
        <i>of ${N} — deprived &amp; thin conditions</i></div>
    </div>
    <div class="d-grid">
      ${row("Population", fmt(d.pop))}
      ${row("IMD score", (+d.imd_s).toFixed(1) + " (q" + d.imd_q + ")")}
      ${row("Community energy orgs", d.ce_orgs)}
      ${row("Project sites", d.ce_sites)}
      ${row("Installed capacity", kw(d.cap_kw) + (d.cap_sites ? " · " + d.cap_sites + " sized" : ""))}
      ${row("Largest single site", kw(d.biggest_kw))}
      ${row("Civic fabric / 1k", d.infra_per_1k.toFixed(1))}
      ${row("Nearest knowledge base", esc(d.know_name || "") + " · " + d.know_km + " km")}
      ${row("Knowledge bases here", d.know_count)}
      ${row("Green substations", d.grid_cov ? d.grid_green + " of " + d.grid_subs : "no DNO data")}
      ${row("Energy Redress", d.redress_grantees ? d.redress_grantees + " grantee(s) · " + gbp(d.redress_total) : "none")}
      ${row("Redress projects", d.redress_projects || 0)}
    </div>
    <a class="d-maplink" href="index.html?lad=${d.code}&lat=${d.lat}&lon=${d.lon}&z=9.2">View on the map →</a>`;
  document.getElementById("drawer").classList.remove("hidden");
  document.getElementById("drawer-scrim").classList.remove("hidden");
  history.replaceState(null, "", "?lad=" + code + location.hash);
}
function closeDrawer() {
  document.getElementById("drawer").classList.add("hidden");
  document.getElementById("drawer-scrim").classList.add("hidden");
  history.replaceState(null, "", location.pathname + location.hash);
}
