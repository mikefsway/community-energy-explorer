/* Community Energy Explorer — insights report (insights.html).
 * Consumes web/data/explore.json (per-LAD) and web/data/insights.json
 * (LSOA-decile distribution of community-energy points, from p09).
 * The prose in insights.html is fixed; every number and chart on the page is
 * recomputed here so the report stays consistent with the data as it refreshes.
 */
"use strict";

const fmt = n => n == null || Number.isNaN(n) ? "–" : Math.round(n).toLocaleString("en-GB");
const pc0 = x => Math.round(x * 100) + "%";
const gbp2 = n => "£" + n.toFixed(2);
const gbp = n => !n ? "£0" : n >= 1e6 ? "£" + (n / 1e6).toFixed(1) + "m" : "£" + Math.round(n / 1e3) + "k";
const mw = kw => (kw / 1000).toFixed(1) + " MW";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rfmt = r => (r < 0 ? "−" : "") + Math.abs(r).toFixed(2);
const sum = a => a.reduce((x, y) => x + y, 0);
const median = a => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

function pearson(x, y) {
  const n = x.length, mx = sum(x) / n, my = sum(y) / n;
  let sxy = 0, sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { const dx = x[i] - mx, dy = y[i] - my; sxy += dx * dy; sx += dx * dx; sy += dy * dy; }
  return sx && sy ? sxy / Math.sqrt(sx * sy) : 0;
}
/* residuals of y after a least-squares fit on x — for the partial correlation */
function resid(y, x) {
  const n = x.length, mx = sum(x) / n, my = sum(y) / n;
  let sxy = 0, sxx = 0;
  for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; }
  const b = sxx ? sxy / sxx : 0;
  return y.map((v, i) => v - (my + b * (x[i] - mx)));
}

const Q_COL = ["#cb4b3a", "#e0855a", "#f0bd87", "#cdd9c4", "#9fb59a"]; // quintile 1 most deprived → 5
const TYP_COL = { thriving: "#2e7d5b", latent: "#b87400", pioneering: "#16808c", cold: "#8a8474" };
const Q_LAB = ["Q1 most deprived", "Q2", "Q3", "Q4", "Q5 least deprived"];

init();

async function init() {
  const [ex, ins] = await Promise.all([
    fetch("data/explore.json").then(r => r.json()),
    fetch("data/insights.json").then(r => r.json()),
  ]);
  const L = ex.lads;
  const S = computeStats(L, ins);
  document.querySelectorAll("[data-n]").forEach(el => {
    if (S[el.dataset.n] != null) el.textContent = S[el.dataset.n];
  });
  const dateEl = document.getElementById("report-date");
  if (dateEl && ex.generated) dateEl.textContent = "Data generated " + ex.generated + ".";

  figDeciles(ins);
  figQuintiles(L);
  figTypology(L);
  figCapTop(L);
  figRedress(L);
  renderLists(L, S);
}

function quintiles(L) {
  const q = [1, 2, 3, 4, 5].map(i => L.filter(d => d.imd_q === i));
  return q.map(g => ({
    lads: g,
    pop: sum(g.map(d => d.pop)),
    ce: sum(g.map(d => d.ce_total)),
    cap: sum(g.map(d => d.cap_kw)),
    redress: sum(g.map(d => d.redress_total)),
    noCe: g.filter(d => d.ce_total === 0).length / g.length,
  }));
}

function computeStats(L, ins) {
  const S = {};
  const nOrgs = sum(ins.orgs), nSites = sum(ins.sites);
  const share = (counts, from, to) => sum(counts.slice(from - 1, to)) /
    (counts === ins.pop_share ? 1 : sum(counts));
  S.orgBotFifth = pc0(share(ins.orgs, 1, 2));
  S.popBotFifth = pc0(sum(ins.pop_share.slice(0, 2)));
  S.orgMid = pc0(share(ins.orgs, 4, 8));
  S.popMid = pc0(sum(ins.pop_share.slice(3, 8)));
  S.siteBotFifth = pc0(share(ins.sites, 1, 2));

  S.nLads = S.nLads2 = L.length;
  const Q = quintiles(L);
  S.q1per100k = (Q[0].ce / Q[0].pop * 1e5).toFixed(1);
  S.q5per100k = (Q[4].ce / Q[4].pop * 1e5).toFixed(1);
  S.q1none = pc0(Q[0].noCe);
  S.q5none = pc0(Q[4].noCe);
  const noCe = L.filter(d => d.ce_total === 0);
  S.popNoCe = (sum(noCe.map(d => d.pop)) / 1e6).toFixed(1);
  S.popNoCePct = pc0(sum(noCe.map(d => d.pop)) / sum(L.map(d => d.pop)));

  const need = L.map(d => d.need_p), pres = L.map(d => d.presence_p), ready = L.map(d => d.ready_p);
  S.rNeedPres = rfmt(pearson(need, pres));
  S.rNeedReady = rfmt(pearson(need, ready));
  S.rPartial = rfmt(pearson(resid(pres, ready), resid(need, ready)));
  S.rKnow = rfmt(pearson(L.map(d => d.know_km), pres));

  const typShare = (q, t) => Q[q].lads.filter(d => d.typology === t).length / Q[q].lads.length;
  S.q5cold = pc0(typShare(4, "cold"));
  S.q1pio = pc0(typShare(0, "pioneering"));
  S.q5pio = pc0(typShare(4, "pioneering"));

  const capTotal = sum(L.map(d => d.cap_kw));
  const capsDesc = L.map(d => d.cap_kw).sort((a, b) => b - a);
  S.capTotal = mw(capTotal);
  S.capTop10 = pc0(sum(capsDesc.slice(0, 10)) / capTotal);
  S.capZeroLads = L.filter(d => d.cap_kw === 0).length;
  S.capQ1Share = pc0(Q[0].cap / capTotal);
  const latMed = median(L.map(d => d.lat));
  S.capSouth = pc0(sum(L.filter(d => d.lat < latMed).map(d => d.cap_kw)) / capTotal);

  S.redressQ12 = gbp2((Q[0].redress + Q[1].redress) / (Q[0].pop + Q[1].pop));
  S.redressQ45 = gbp2((Q[3].redress + Q[4].redress) / (Q[3].pop + Q[4].pop));

  const HI = 2 / 3;
  S._pioneers = L.filter(d => d.need_p >= HI && d.ce_total > 0)
    .sort((a, b) => b.ce_per_100k - a.ce_per_100k).slice(0, 10);
  S._footholds = L.filter(d => d.need_p >= HI && d.redress_grantees > 0 && d.ce_orgs === 0)
    .sort((a, b) => b.redress_total - a.redress_total);
  S.nFootholds = S._footholds.length;
  S._priority = L.filter(d => d.need_p >= 0.6 && d.ready_p >= 0.5 && d.presence_p <= 0.35)
    .sort((a, b) => b.need_p - a.need_p);
  // tiers 1 and 3 must stay disjoint: "ready ground" can't also be "nothing to build from"
  const tier1 = new Set(S._priority.map(d => d.code));
  S._overlooked = L.filter(d => d.need_p >= HI && d.ce_total === 0 && d.redress_total === 0
      && !tier1.has(d.code))
    .sort((a, b) => b.need_p - a.need_p);
  S.nOverlooked = S._overlooked.length;
  S.popOverlooked = (sum(S._overlooked.map(d => d.pop)) / 1e6).toFixed(1);
  return S;
}

/* ---------------- tiny svg helpers ---------------- */
const svgOpen = (w, h) => `<svg viewBox="0 0 ${w} ${h}" class="chart" role="img">`;
const txt = (x, y, s, cls, anchor) =>
  `<text x="${x}" y="${y}" class="${cls}" ${anchor ? `text-anchor="${anchor}"` : ""}>${esc(s)}</text>`;

/* Fig 1 — points per decile relative to population share */
function figDeciles(ins) {
  const W = 760, H = 300, PAD = { l: 44, r: 12, t: 26, b: 42 };
  const orgT = sum(ins.orgs), siteT = sum(ins.sites);
  const ratio = (c, i, t) => (c / t) / ins.pop_share[i];
  const series = [
    { name: "Organisations (offices)", col: "#b87400", v: ins.orgs.map((c, i) => ratio(c, i, orgT)) },
    { name: "Project sites", col: "#2e7d5b", v: ins.sites.map((c, i) => ratio(c, i, siteT)) },
  ];
  const ymax = Math.max(1.25, ...series.flatMap(s => s.v)) * 1.08;
  const iw = (W - PAD.l - PAD.r) / 10, bw = iw * 0.34;
  const sy = v => PAD.t + (1 - v / ymax) * (H - PAD.t - PAD.b);
  let g = "";
  series.forEach((s, si) => s.v.forEach((v, i) => {
    const x = PAD.l + i * iw + iw * 0.14 + si * bw;
    g += `<rect x="${x.toFixed(1)}" y="${sy(v).toFixed(1)}" width="${bw.toFixed(1)}"
          height="${(sy(0) - sy(v)).toFixed(1)}" fill="${s.col}" fill-opacity="0.88">
          <title>Decile ${i + 1} — ${s.name}: ${v.toFixed(2)}× population share</title></rect>`;
  }));
  for (let i = 0; i < 10; i++)
    g += txt(PAD.l + i * iw + iw / 2, H - PAD.b + 16, i + 1, "tick", "middle");
  [0, 0.5, 1, 1.5].filter(v => v < ymax).forEach(v => {
    g += `<line x1="${PAD.l}" x2="${W - PAD.r}" y1="${sy(v)}" y2="${sy(v)}" class="${v === 1 ? "parity" : "grid"}"/>`
      + txt(PAD.l - 7, sy(v) + 3, v.toFixed(1), "tick", "end");
  });
  g += txt(W - PAD.r, sy(1) - 5, "population share", "parity-lab", "end");
  g += txt(PAD.l, H - PAD.b + 32, "← most deprived tenth of neighbourhoods", "axlab small");
  g += txt(W - PAD.r, H - PAD.b + 32, "least deprived →", "axlab small", "end");
  g += series.map((s, i) =>
    `<rect x="${PAD.l + i * 190}" y="6" width="11" height="11" fill="${s.col}"/>` +
    txt(PAD.l + i * 190 + 16, 16, s.name, "leg")).join("");
  document.getElementById("fig-deciles").innerHTML = svgOpen(W, H) + g + "</svg>";
}

/* shared simple bar chart over the five quintiles */
function quintBars(values, fmtV, ymaxPad = 1.15) {
  const W = 370, H = 240, PAD = { l: 14, r: 14, t: 26, b: 40 };
  const ymax = Math.max(...values) * ymaxPad;
  const iw = (W - PAD.l - PAD.r) / 5, bw = iw * 0.64;
  const sy = v => PAD.t + (1 - v / ymax) * (H - PAD.t - PAD.b);
  let g = "";
  values.forEach((v, i) => {
    const x = PAD.l + i * iw + (iw - bw) / 2;
    g += `<rect x="${x.toFixed(1)}" y="${sy(v).toFixed(1)}" width="${bw.toFixed(1)}"
          height="${(sy(0) - sy(v)).toFixed(1)}" fill="${Q_COL[i]}" stroke="#20251f" stroke-width="0.4"/>`
      + txt(x + bw / 2, sy(v) - 6, fmtV(v), "val", "middle")
      + txt(x + bw / 2, H - PAD.b + 16, "Q" + (i + 1), "tick", "middle");
  });
  g += txt(PAD.l, H - PAD.b + 32, "← most deprived", "axlab small");
  g += txt(W - PAD.r, H - PAD.b + 32, "least →", "axlab small", "end");
  return svgOpen(W, H) + g + "</svg>";
}

function figQuintiles(L) {
  const Q = quintiles(L);
  document.getElementById("fig-quintiles").innerHTML =
    `<div class="fig-cell"><h4>Community energy per 100k people</h4>
       ${quintBars(Q.map(q => q.ce / q.pop * 1e5), v => v.toFixed(1))}</div>
     <div class="fig-cell"><h4>Share of authorities with none</h4>
       ${quintBars(Q.map(q => q.noCe), v => Math.round(v * 100) + "%")}</div>`;
}

function figTypology(L) {
  const W = 760, ROW = 34, PAD = { l: 130, r: 12, t: 30, b: 8 };
  const H = PAD.t + 5 * ROW + PAD.b;
  const order = ["thriving", "latent", "pioneering", "cold"];
  const Q = quintiles(L);
  let g = "";
  Q.forEach((q, i) => {
    const y = PAD.t + i * ROW;
    let x = PAD.l;
    g += txt(PAD.l - 8, y + ROW * 0.55, Q_LAB[i], "tick", "end");
    order.forEach(t => {
      const f = q.lads.filter(d => d.typology === t).length / q.lads.length;
      const w = f * (W - PAD.l - PAD.r);
      g += `<rect x="${x.toFixed(1)}" y="${y}" width="${w.toFixed(1)}" height="${ROW - 8}"
            fill="${TYP_COL[t]}" fill-opacity="0.9"><title>${Q_LAB[i]} — ${t}: ${Math.round(f * 100)}%</title></rect>`;
      if (f >= 0.09) g += txt(x + w / 2, y + ROW * 0.55, Math.round(f * 100) + "%", "stack-lab", "middle");
      x += w;
    });
  });
  let lx = PAD.l;
  order.forEach(t => {
    g += `<rect x="${lx}" y="8" width="11" height="11" fill="${TYP_COL[t]}"/>`
      + txt(lx + 16, 18, t, "leg");
    lx += 24 + t.length * 7 + 28;
  });
  document.getElementById("fig-typology").innerHTML = svgOpen(W, H) + g + "</svg>";
}

function figCapTop(L) {
  const top = [...L].sort((a, b) => b.cap_kw - a.cap_kw).slice(0, 10);
  const W = 760, ROW = 28, PAD = { l: 200, r: 70, t: 8, b: 8 };
  const H = PAD.t + top.length * ROW + PAD.b;
  const max = top[0].cap_kw;
  let g = "";
  top.forEach((d, i) => {
    const y = PAD.t + i * ROW;
    const w = d.cap_kw / max * (W - PAD.l - PAD.r);
    g += txt(PAD.l - 8, y + ROW * 0.62, d.name, "tick", "end")
      + `<rect x="${PAD.l}" y="${y + 4}" width="${w.toFixed(1)}" height="${ROW - 11}"
         fill="${Q_COL[d.imd_q - 1]}" stroke="#20251f" stroke-width="0.4" class="rowlink"
         data-code="${d.code}"><title>${esc(d.name)} — ${mw(d.cap_kw)}, deprivation quintile ${d.imd_q}</title></rect>`
      + txt(PAD.l + w + 6, y + ROW * 0.62, mw(d.cap_kw), "val");
  });
  const el = document.getElementById("fig-captop");
  el.innerHTML = svgOpen(W, H) + g + "</svg>";
  el.querySelectorAll(".rowlink").forEach(r =>
    r.addEventListener("click", () => location.href = "explore.html?lad=" + r.dataset.code));
}

function figRedress(L) {
  const Q = quintiles(L);
  document.getElementById("fig-redress").innerHTML =
    quintBars(Q.map(q => q.redress / q.pop), v => gbp2(v));
}

/* ---------------- lists ---------------- */
const li = d => `<li><a href="explore.html?lad=${d.code}"><span>${esc(d.name)}</span>
  <em>${d._note}</em></a></li>`;

function card(title, count, sub, items) {
  return `<div class="mm-card"><div class="mm-head"><h3>${title}</h3>
    <span class="mm-count">${count}</span></div>
    <p class="mm-sub">${sub}</p>
    <ol>${items.map(li).join("") || "<li class='mm-empty'>None</li>"}</ol></div>`;
}

function renderLists(L, S) {
  const ordp = p => Math.round(p * 100) + "th";
  document.getElementById("list-pioneers").innerHTML = card(
    "Most deprived third, strongest presence per head", S._pioneers.length,
    "Sorted by organisations + sites per 100,000 people. Click through for each authority's full record.",
    S._pioneers.map(d => ({ ...d, _note: d.ce_per_100k.toFixed(1) + " per 100k · " + (d.cap_kw ? mw(d.cap_kw) : "no recorded capacity") })));

  document.getElementById("list-footholds").innerHTML = card(
    "Redress-funded, deprived, no community-energy organisation", S.nFootholds,
    "Most deprived third, at least one Energy Redress grantee, no organisation of their own. Sorted by funding.",
    S._footholds.slice(0, 10).map(d => ({ ...d, _note: gbp(d.redress_total) + " redress · need " + ordp(d.need_p) + " pctile" })));

  document.getElementById("lists-start").innerHTML =
    card("Tier 1 — best first bets", S._priority.length,
      "Deprived, with above-median enabling conditions, but little or no community energy. Ready ground.",
      S._priority.map(d => ({ ...d, _note: "need " + ordp(d.need_p) + " · ready " + ordp(d.ready_p) }))) +
    card("Tier 2 — through the footholds", S.nFootholds,
      "Deprived, no organisation, but a Redress-funded delivery body already working there to build from. Full list in section 5.",
      S._footholds.slice(0, 7).map(d => ({ ...d, _note: gbp(d.redress_total) + " redress" }))) +
    card("Tier 3 — the hardest ground", S.nOverlooked,
      "Most deprived third with no community energy and no Redress funding either — nothing yet to build from.",
      S._overlooked.map(d => ({ ...d, _note: "need " + ordp(d.need_p) + " pctile" })));
}
