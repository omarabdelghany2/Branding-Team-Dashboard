/* 51Talk ME Brand Weekly Monitoring Dashboard — MVP app logic.
   No build step. Loads JSON from /data, renders the brief's 3 sections + 5-part report.
   Serve locally:  python3 -m http.server 8000  →  http://localhost:8000  */

const DATA = "data";
const state = {
  config: null, manifest: null, latest: null, history: [], market: "ALL",
  tracker: null, website: null, appHistory: null,  // top-level data (not per-week)
  trackerMetric: "followers",                       // Section B chart toggle
};

async function fetchJSON(path) {
  const res = await fetch(`${path}?_=${Date.now()}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

// Non-critical top-level files (tracker / website / app-store history): a miss must
// NOT blank the whole board, so these resolve to null instead of throwing.
async function fetchJSONSafe(path) {
  try { return await fetchJSON(path); }
  catch (e) { console.warn(`optional data missing: ${path}`, e.message); return null; }
}

async function loadSnapshot(dateDir) {
  const base = `${DATA}/snapshots/${dateDir}`;
  const [meta, report, brand, social, reviews] = await Promise.all([
    fetchJSON(`${base}/meta.json`),
    fetchJSON(`${base}/report.json`),
    fetchJSON(`${base}/brand-voice.json`),
    fetchJSON(`${base}/social.json`),
    fetchJSON(`${base}/reviews.json`),
  ]);
  return { meta, report, brand, social, reviews };
}

async function boot() {
  try {
    state.config = await fetchJSON(`${DATA}/config.json`);
    state.manifest = await fetchJSON(`${DATA}/manifest.json`);
    const snaps = state.manifest.snapshots || [];
    if (!snaps.length) throw new Error("no snapshots in manifest");
    const recent = snaps.slice(-4);
    state.history = await Promise.all(recent.map((s) => loadSnapshot(s.date)));
    state.latest = state.history[state.history.length - 1];
    [state.tracker, state.website, state.appHistory] = await Promise.all([
      fetchJSONSafe(`${DATA}/social-tracker.json`),
      fetchJSONSafe(`${DATA}/website-traffic.json`),
      fetchJSONSafe(`${DATA}/appstore-history.json`),
    ]);
    renderAll();
  } catch (err) {
    console.error(err);
    document.getElementById("load-error").classList.remove("hidden");
  }
}

/* ---------- helpers ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const gapBadge = (txt = "待确认 / TBC") => `<span class="tag tag-gap">${esc(txt)}</span>`;
const fmtRating = (v) => (v == null ? "—" : Number(v).toFixed(2));
const fmtNum = (v) => (v == null || v === "" ? "—" : (isNaN(Number(v)) ? esc(v) : Number(v).toLocaleString()));
const emptyNote = (txt) => `<p class="empty-note">${esc(txt)}</p>`;

function statusTag(status) {
  if (!status) return "";
  const s = status.toLowerCase();
  if (s.includes("confirm") || s.includes("block") || s.includes("pending") || s.includes("draft"))
    return gapBadge(status);
  if (s.includes("ok") || s.includes("confirmed")) return `<span class="tag tag-ok">${esc(status)}</span>`;
  return `<span class="tag tag-note">${esc(status)}</span>`;
}

function deltaCell(cur, prev) {
  if (cur == null || prev == null) return `<td class="num">—</td>`;
  const d = cur - prev;
  if (d === 0) return `<td class="num delta-flat">±0</td>`;
  const cls = d > 0 ? "delta-up" : "delta-down";
  const arrow = d > 0 ? "▲" : "▼";
  return `<td class="num ${cls}">${arrow} ${Math.abs(d).toLocaleString()}</td>`;
}

// Signed net-growth cell (e.g. follower net Δ). Uses explicit value when given, else end-start.
function signedCell(value, cur, prev) {
  let d = value;
  if (d == null && cur != null && prev != null) d = cur - prev;
  if (d == null) return `<td class="num">—</td>`;
  d = Number(d);
  if (d === 0) return `<td class="num delta-flat">±0</td>`;
  const cls = d > 0 ? "delta-up" : "delta-down";
  return `<td class="num ${cls}">${d > 0 ? "+" : "−"}${Math.abs(d).toLocaleString()}</td>`;
}

// Dependency-free inline sparkline from an array of numbers (or {value}) — for 4-week trend.
function sparkline(series, w = 84, h = 22) {
  const vals = (series || []).map((p) => (typeof p === "number" ? p : Number(p.value))).filter((n) => !Number.isNaN(n));
  if (vals.length < 2) return `<span class="empty-note">—</span>`;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const step = w / (vals.length - 1);
  const pts = vals.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - ((v - min) / span) * (h - 4)).toFixed(1)}`).join(" ");
  const last = vals[vals.length - 1], first = vals[0];
  const stroke = last >= first ? "var(--ok)" : "var(--bad)";
  const cx = (w).toFixed(1), cy = (h - 2 - ((last - min) / span) * (h - 4)).toFixed(1);
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w + 4} ${h}" class="spark">
    <polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linejoin="round"/>
    <circle cx="${cx}" cy="${cy}" r="2" fill="${stroke}"/></svg>`;
}

/* ---------- charts (dependency-free SVG, Google-Trends style) ---------- */
// Distinct, CVD-aware line colours. Order matters: 51Talk-brand orange first so
// our own line reads as "us" against competitors.
const CHART_COLORS = ["#c2410c", "#1d5fa8", "#0ca30c", "#a21caf", "#b45309", "#0e7490", "#be123c"];
const channelColor = (name, i) => CHART_COLORS[i % CHART_COLORS.length];

// Compact big numbers (view counts run to tens of millions): 79850531 → "79.9M".
function fmtCompact(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return esc(v);
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return n.toLocaleString();
}

// Attainment bar for a "vs target" %. pct is a RATIO (0.85 = 85%). Capped visual at
// 100% but the label shows the true value (125% still reads "125%").
function pctBar(pct) {
  if (pct == null || pct === "") return `<span class="empty-note">—</span>`;
  const r = Number(pct);
  if (Number.isNaN(r)) return esc(pct);
  const shown = Math.round(r * 100);
  const w = Math.max(0, Math.min(100, shown));
  const cls = shown >= 100 ? "pb-ok" : shown >= 60 ? "pb-warn" : "pb-low";
  return `<span class="pbar" title="${shown}% of target"><span class="pbar-fill ${cls}" style="width:${w}%"></span></span><span class="pbar-num">${shown}%</span>`;
}

// Multi-line chart. series = [{label, points:[{label,value}]}] — every series must
// share the same ordered x labels (months / weeks). Renders a legend + gridded SVG
// with one polyline per series, native <title> tooltips on end points.
function lineChart(series, opts = {}) {
  const { width = 640, height = 210, valueFmt = fmtCompact, baseline0 = true, unit = "" } = opts;
  const clean = (series || []).filter((s) => (s.points || []).some((p) => p.value != null));
  if (!clean.length) return `<p class="empty-note">Not enough data to chart yet.</p>`;
  const xLabels = clean[0].points.map((p) => p.label);
  const n = xLabels.length;
  const vals = clean.flatMap((s) => s.points.map((p) => p.value).filter((v) => v != null));
  const rawMax = Math.max(...vals), rawMin = Math.min(...vals);
  const max = rawMax === rawMin ? rawMax + 1 : rawMax;
  const min = baseline0 ? Math.min(0, rawMin) : rawMin;
  const PAD = { l: 46, r: 14, t: 12, b: 26 };
  const plotW = width - PAD.l - PAD.r, plotH = height - PAD.t - PAD.b;
  const X = (i) => PAD.l + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const Y = (v) => PAD.t + plotH - ((v - min) / ((max - min) || 1)) * plotH;

  const ticks = 4;
  let grid = "";
  for (let t = 0; t <= ticks; t++) {
    const v = min + ((max - min) * t) / ticks;
    const y = Y(v).toFixed(1);
    grid += `<line x1="${PAD.l}" y1="${y}" x2="${width - PAD.r}" y2="${y}" class="grid-line"/>`;
    grid += `<text x="${PAD.l - 6}" y="${y}" class="axis-label" text-anchor="end" dominant-baseline="middle">${valueFmt(Math.round(v))}</text>`;
  }
  // x labels — thin out if crowded
  const every = n > 8 ? Math.ceil(n / 8) : 1;
  let xlab = "";
  xLabels.forEach((lb, i) => {
    if (i % every !== 0 && i !== n - 1) return;
    xlab += `<text x="${X(i).toFixed(1)}" y="${height - 8}" class="axis-label" text-anchor="middle">${esc(lb)}</text>`;
  });

  let paths = "";
  clean.forEach((s, si) => {
    const color = s.color || channelColor(s.label, si);
    const pts = s.points.map((p, i) => (p.value == null ? null : `${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`)).filter(Boolean).join(" ");
    paths += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    s.points.forEach((p, i) => {
      if (p.value == null) return;
      paths += `<circle cx="${X(i).toFixed(1)}" cy="${Y(p.value).toFixed(1)}" r="2.6" fill="${color}"><title>${esc(s.label)} · ${esc(p.label)}: ${valueFmt(p.value)}${esc(unit)}</title></circle>`;
    });
  });

  const legend = clean.map((s, si) => {
    const color = s.color || channelColor(s.label, si);
    const last = [...s.points].reverse().find((p) => p.value != null);
    return `<span class="lg-item"><span class="lg-swatch" style="background:${color}"></span>${esc(s.label)}${last ? ` <b>${valueFmt(last.value)}${esc(unit)}</b>` : ""}</span>`;
  }).join("");

  return `<div class="chart">
    <div class="chart-legend">${legend}</div>
    <svg viewBox="0 0 ${width} ${height}" class="linechart" role="img" preserveAspectRatio="xMidYMid meet">
      ${grid}${xlab}${paths}
    </svg></div>`;
}

function table(headers, rows, blockedMsg) {
  const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>`;
  const body = rows && rows.length
    ? rows.map((r) => `<tr>${r.join("")}</tr>`).join("")
    : `<tr class="blocked-row"><td colspan="${headers.length}">${esc(blockedMsg || "No data this week.")}</td></tr>`;
  return `<div class="table-wrap"><table>${thead}<tbody>${body}</tbody></table></div>`;
}

function marketOK(code) {
  return state.market === "ALL" || state.market === code;
}

/* ---------- renderers ---------- */
function renderAll() {
  renderHeader();
  renderMarketFilter();
  renderConclusions();
  renderSectionA();
  renderSectionB();
  renderSectionC();
  renderSectionD();
  renderExplanation();
  renderRisks();
  renderQuality();
  renderConfirmations();
}

function renderHeader() {
  const c = state.config, m = state.latest.meta;
  $("dash-title").textContent = "Brand Weekly Monitoring Dashboard";
  $("week-label").textContent = m.weekLabel + (m.isBaseline ? " · baseline" : "");
  $("week-period").textContent = `${m.collectionPeriod.start} → ${m.collectionPeriod.end} · captured ${m.captureDate}`;
  $("footer-owner").textContent = c.meta.owner;
  $("footer-meta").textContent = `${c.meta.title} · ${c.meta.version} · ${c.meta.cadence}`;
}

function renderMarketFilter() {
  const wrap = $("market-filter");
  const btns = [{ code: "ALL", name: "All markets" }, ...state.config.markets];
  wrap.innerHTML = btns
    .map((b) => `<button data-code="${b.code}" class="${b.code === state.market ? "active" : ""}">${esc(b.code === "ALL" ? "All" : b.code)}</button>`)
    .join("");
  wrap.querySelectorAll("button").forEach((btn) =>
    btn.addEventListener("click", () => { state.market = btn.dataset.code; renderMarketFilter(); renderSectionA(); renderSectionB(); renderSectionC(); renderSectionD(); })
  );
}

function renderConclusions() {
  const items = state.latest.report.conclusions || [];
  $("conclusions-list").innerHTML = items.length
    ? items.map((c) => `<li>${esc(c.text)}</li>`).join("")
    : emptyNote("No conclusions authored yet.");
}

const MONTHS_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (ym) => { const m = Number(String(ym).split("-")[1]); return MONTHS_ABBR[m - 1] || ym; };
const monthNum = (m) => MONTHS_ABBR[(Number(m) - 1) % 12] || m;
const dateLabel = (d) => { const p = String(d).split("-"); return `${MONTHS_ABBR[Number(p[1]) - 1] || p[1]} ${Number(p[2])}`; };

function renderSectionA() {
  const b = state.latest.brand;

  // 6-month multi-brand comparison chart (manager: "plot different brands on one
  // chart like Google Trends"). One chart PER MARKET — Trends normalises WITHIN a
  // market, so keywords are comparable only inside the same market, never across.
  const gt = (b.googleTrends.entries || []).filter((e) => marketOK(e.market));
  const marketsInView = [...new Set(gt.map((e) => e.market))];
  const chartsHtml = marketsInView.map((mk) => {
    const series = gt.filter((e) => e.market === mk).map((e) => {
      const pts = (e.seriesMonthly && e.seriesMonthly.length)
        ? e.seriesMonthly.map((p) => ({ label: monthLabel(p.month), value: p.value }))
        : (e.series6m || e.series || []).map((p) => ({ label: (p.date || "").slice(5), value: p.value }));
      return { label: e.keyword, points: pts };
    }).filter((s) => s.points.length);
    if (!series.length) return "";
    return `<div class="chart-block"><div class="chart-title">${esc(mk)}
      <span class="tag tag-note">6-mo · relative 0–100</span></div>
      ${lineChart(series, { valueFmt: (v) => Math.round(v), baseline0: true, height: 190 })}</div>`;
  }).join("");
  $("trends-chart-wrap").outerHTML = `<div id="trends-chart-wrap">${
    chartsHtml || `<p class="empty-note">${
      (b.googleTrends.entries || []).length
        ? "No 6-month series stored yet — re-run scripts/fetch_google_trends.py (it now saves series6m + seriesMonthly)."
        : "Run scripts/fetch_google_trends.py after keywords are confirmed."}</p>`
  }<p class="chart-note">Every keyword/brand on one chart, Google-Trends style. <strong>Competitor lines drop in here once Patrick confirms the competitor list.</strong> Index is RELATIVE (0–100), comparable only within a market and not across snapshots.</p></div>`;

  // Google Trends detail table
  $("trends-wrap").outerHTML = `<div id="trends-wrap">${
    gt.length
      ? table(
          ["Market", "Keyword", "This wk", "Prev", "WoW", "4-wk trend", "6-mo peak", "Source"],
          gt.map((e) => [
            `<td>${esc(e.market)}</td>`, `<td>${esc(e.keyword ?? b.googleTrends.keyword)}</td>`,
            `<td class="num">${esc(e.current)}</td>`, `<td class="num">${esc(e.prevWeek)}</td>`,
            deltaCell(e.current, e.prevWeek), `<td>${sparkline(e.series)}</td>`,
            `<td>${esc(e.peakDate ?? "—")}</td>`, `<td>${esc(b.googleTrends.source)}</td>`,
          ])
        )
      : `<div class="table-wrap"><table><tbody><tr class="blocked-row"><td>${gapBadge("Run scripts/fetch_google_trends.py after keywords are confirmed")}</td></tr></tbody></table></div>`
  }</div>`;

  // App Store
  const as = (b.appStore.entries || []).filter((e) => marketOK(e.market));
  $("appstore-wrap").outerHTML = `<div id="appstore-wrap">${
    as.length
      ? table(
          ["Market", "App", "Rating", "#Ratings", "ΔRating", "Rank", "Version", "Ver. date"],
          as.map((e) => [
            `<td>${esc(e.market)}</td>`, `<td>${esc(e.app || "—")}</td>`,
            `<td class="num">${fmtRating(e.rating)}</td>`, `<td class="num">${esc(e.ratingCount)}</td>`,
            deltaCell(e.rating, e.prevRating),
            `<td class="num">${e.rank == null ? gapBadge("no rank") : esc(e.rank)}</td>`,
            `<td>${esc(e.version)}</td>`, `<td>${esc(e.versionDate)}</td>`,
          ])
        )
      : `<div class="table-wrap"><table><tbody><tr class="blocked-row"><td>${gapBadge("Confirm iOS appId, then run scripts/fetch_appstore.py")}</td></tr></tbody></table></div>`
  }</div>`;

  // App Store 12-month rolling rating trend (manager: "a trend view, not just the
  // current value"). Fills forward from our captures; full backfill needs a paid ASO tool.
  renderAppStoreTrend();

  // Competitor comparison was removed from the board 2026-09-23 — it never carried data
  // (blocked on Patrick's competitor list). The blocker is still tracked in ⑤ Open
  // Confirmations, so nothing is lost; only the permanently-empty table is gone.
}

function renderAppStoreTrend() {
  const wrap = $("appstore-trend-wrap");
  if (!wrap) return;
  const hist = state.appHistory;
  const series = ((hist && hist.series) || []).filter((s) => marketOK(s.market));
  if (!series.length) {
    wrap.innerHTML = `<p class="empty-note">${hist
      ? "No rating history for this market yet."
      : "Run scripts/fetch_appstore_history.py to build the rating trend."}</p>`;
    return;
  }
  const meta = hist.meta || {};
  const marketsHere = [...new Set(series.map((s) => s.market))];
  const blocks = marketsHere.map((mk) => {
    const lines = series.filter((s) => s.market === mk).map((s) => ({
      label: s.app,
      points: (s.points || []).map((p) => ({ label: dateLabel(p.date), value: p.rating })),
    }));
    const pts = Math.max(...lines.map((l) => l.points.length));
    return `<div class="chart-block"><div class="chart-title">${esc(mk)}
        <span class="tag tag-note">iOS rating · ${pts} pt(s)</span></div>
      ${lineChart(lines, { valueFmt: (v) => Number(v).toFixed(2), baseline0: false, unit: "★", height: 180 })}</div>`;
  }).join("");
  wrap.innerHTML = `${blocks}<p class="chart-note">
    Rolling ${esc(meta.window || "12-month")} view; fills forward from our first capture (W35).
    ${meta.backfillBlocked ? `<span class="tag tag-gap">full 12-mo backfill needs a paid ASO tool</span> <span class="chart-note-owner">owner: ${esc(meta.backfillOwner || "Patrick / Omar")}</span>` : ""}</p>`;
}

function renderSocialLegend() {
  const sa = state.config.socialAccounts;
  const mc = sa.metricCapability || {};
  const metrics = Object.entries(mc).filter(([k]) => k !== "note");
  const chip = (label, access, source) =>
    `<span class="cap ${access === "auto" ? "cap-auto" : "cap-creds"}">${esc(label)}
      <em>${access === "auto" ? "AUTO" : "NEEDS CREDS"}</em>
      <small>${esc(source)}</small></span>`;
  const metricChips = metrics.map(([k, v]) => chip(k, v.access, v.source)).join("");

  const plat = sa.platformCapability || {};
  const platRows = Object.entries(plat).map(([p, v]) => {
    const badge = v.publicScrape
      ? `<span class="tag tag-ok">public scrape ✓</span>`
      : `<span class="tag tag-cred">NEEDS CREDENTIALS</span>`;
    return `<div class="plat-row"><strong>${esc(p)}</strong> ${badge}<span>${esc(v.note)}</span></div>`;
  }).join("");

  $("social-legend").innerHTML = `
    <div class="cap-block">
      <div class="cap-title">What auto-fills vs what needs credentials</div>
      <div class="cap-metrics">${metricChips}</div>
      <div class="cap-plats">${platRows}</div>
    </div>`;
}

// Two field families coexist in social.json: the original endFollowers /
// netFollowerGrowth / avgVideoViews, and the Phase-2 followers / followerGrowth /
// views that import_social_csv.py writes. Read BOTH through these accessors —
// the KPI row previously used endFollowers alone and silently dropped every
// CSV-imported account from the headline total.
const fol = (a) => a.followers ?? a.endFollowers;
const gro = (a) => a.followerGrowth ?? a.netFollowerGrowth;
const views = (a) => a.views ?? a.avgVideoViews;

/* ---------- Section B · Monthly Target Tracker (team's own numbers) ---------- */
const CH_KEYS = ["tiktok", "instagram", "snapchat", "x", "youtube"];
const CH_LABELS = { tiktok: "TikTok", instagram: "Instagram", snapchat: "Snapchat", x: "X", youtube: "YouTube" };
const TRACKER_METRICS = [
  { key: "followers", label: "Followers Increasing", kind: "channel", fmt: fmtNum, hasTarget: true },
  { key: "leads", label: "Leads", kind: "channel", fmt: fmtNum, hasTarget: true },
  { key: "views", label: "Total Views", kind: "channel", fmt: fmtCompact, hasTarget: false },
  { key: "avgTikTokView", label: "Ave. TikTok View", kind: "scalar", fmt: fmtNum, hasTarget: true },
];

// The tracker is per-market; only KSA is populated. KWT/UAE are empty templates
// (no market-specific accounts exist), so ALL / KSA both resolve to KSA.
function activeTrackerMarket() {
  return (state.market === "KWT" || state.market === "UAE") ? state.market : "KSA";
}

function renderTracker() {
  const wrap = $("tracker-wrap");
  if (!wrap) return;
  const t = state.tracker;
  if (!t) { wrap.innerHTML = emptyNote("Run scripts/fetch_dingtalk_tracker.py to load the team tracker."); return; }
  const src = t.meta || {};
  const srcLink = src.sourceUrl ? `<a href="${esc(src.sourceUrl)}" target="_blank">${esc(src.source)}</a>` : esc(src.source);
  const srcLine = `<div class="src-line">Source: ${srcLink} · captured ${esc(src.capturedAt || "—")} · <span class="tag tag-ok mini">their numbers</span></div>`;

  const mkCode = activeTrackerMarket();
  const mk = (t.markets || {})[mkCode];
  if (!mk || !mk.hasData) {
    wrap.innerHTML = `<div class="blocker-lite">
      <strong>${esc(mkCode)}: no market-specific social data yet.</strong>
      The tracker has a ${esc(mkCode)} tab but it is an empty template — all owned accounts are KSA-branded / regional, so ${esc(mkCode)} carries no separate numbers.
      ${mkCode !== "KSA" ? ` Switch to <strong>KSA</strong> or <strong>All</strong> to see the populated tracker.` : ""}
      ${srcLine}</div>`;
    return;
  }

  const metric = TRACKER_METRICS.find((m) => m.key === state.trackerMetric) || TRACKER_METRICS[0];
  const months12 = mk.months || [];
  const dataMonths = months12.slice(0, mk.monthsWithData || months12.length);

  // ---- KPI row (year-to-date vs annual target) ----
  const y = mk.yearly || {};
  const kpi = (label, val, sub) => `<div class="kpi"><div class="k-label">${label}</div>
    <div class="k-value">${val}</div><div class="k-sub">${sub}</div></div>`;
  const yFol = y.followers || {}, yLead = y.leads || {}, yView = y.views || {};
  const last = dataMonths[dataMonths.length - 1];
  const lastFolPct = last && last.followers ? last.followers.pct : null;
  const kpis = `<div class="kpi-row">
    ${kpi("Followers gained · YTD", fmtNum(yFol.total),
        `${pctBar(yFol.total != null && yFol.target ? yFol.total / yFol.target : null)} of ${fmtNum(yFol.target)} target`)}
    ${kpi("Leads · YTD", fmtNum(yLead.total),
        `${pctBar(yLead.total != null && yLead.target ? yLead.total / yLead.target : null)} of ${fmtNum(yLead.target)} target`)}
    ${kpi("Total views · YTD", fmtCompact(yView.total), `across ${CH_KEYS.length} channels`)}
    ${kpi(`Latest month (M${last ? last.month : "—"})`, last ? pctBar(lastFolPct) : "—", "followers vs target")}
  </div>`;

  // ---- metric toggle ----
  const toggle = `<div class="seg">${TRACKER_METRICS.map((m) =>
    `<button data-metric="${m.key}" class="${m.key === metric.key ? "active" : ""}">${esc(m.label)}</button>`).join("")}</div>`;

  // ---- chart (per-channel lines over months, or single line for the scalar) ----
  let chart;
  if (metric.kind === "channel") {
    const series = CH_KEYS.map((ch, i) => ({
      label: CH_LABELS[ch],
      points: dataMonths.map((m) => ({ label: "M" + m.month, value: m[metric.key] ? m[metric.key][ch] : null })),
    })).filter((s) => s.points.some((p) => p.value != null));
    chart = lineChart(series, { valueFmt: metric.fmt, baseline0: true, unit: "" });
  } else {
    const series = [{
      label: "Ave. TikTok view", color: CHART_COLORS[0],
      points: dataMonths.map((m) => ({ label: "M" + m.month, value: m.avgTikTokView ? m.avgTikTokView.value : null })),
    }];
    chart = lineChart(series, { valueFmt: metric.fmt, baseline0: true, unit: "" });
  }

  // ---- monthly table (matches the team sheet layout) ----
  const tbl = metric.kind === "channel"
    ? trackerChannelTable(months12, mk.yearly, metric)
    : trackerScalarTable(months12, mk.yearly);

  wrap.innerHTML = `
    <div class="tracker-head">
      <span class="tracker-market">${esc(mkCode)} · 2026</span>
      ${srcLine}
    </div>
    ${kpis}
    <div class="tracker-controls">${toggle}
      <span class="chart-title">${esc(metric.label)} — monthly${metric.hasTarget ? " vs target" : ""}</span></div>
    ${chart}
    ${tbl}`;

  wrap.querySelectorAll(".seg button").forEach((btn) =>
    btn.addEventListener("click", () => { state.trackerMetric = btn.dataset.metric; renderTracker(); }));
}

function trackerChannelTable(months12, yearly, metric) {
  const heads = ["Month", ...CH_KEYS.map((c) => CH_LABELS[c]), "Total",
    ...(metric.hasTarget ? ["Target", "Attain."] : [])];
  const rowFor = (rec, label, isYear) => {
    const blk = rec[metric.key] || {};
    const cells = [
      `<td class="${isYear ? "yr-cell" : ""}">${esc(label)}</td>`,
      ...CH_KEYS.map((c) => `<td class="num">${blk[c] == null ? "<span class='dash'>—</span>" : metric.fmt(blk[c])}</td>`),
      `<td class="num total-cell">${blk.total == null ? "—" : metric.fmt(blk.total)}</td>`,
    ];
    if (metric.hasTarget) {
      cells.push(`<td class="num">${fmtNum(blk.target)}</td>`);
      cells.push(`<td class="num pbar-cell">${pctBar(blk.pct)}</td>`);
    }
    return cells;
  };
  const rows = months12.map((m) => rowFor(m, "M" + m.month, false));
  if (yearly) rows.push(rowFor(yearly, "Yearly", true));
  return table(heads, rows);
}

function trackerScalarTable(months12, yearly) {
  const heads = ["Month", "Ave. TikTok View", "Target", "Attain."];
  const rowFor = (rec, label, isYear) => {
    const a = rec.avgTikTokView || {};
    return [
      `<td class="${isYear ? "yr-cell" : ""}">${esc(label)}</td>`,
      `<td class="num total-cell">${a.value == null ? "<span class='dash'>—</span>" : fmtNum(a.value)}</td>`,
      `<td class="num">${fmtNum(a.target)}</td>`,
      `<td class="num pbar-cell">${pctBar(a.pct)}</td>`,
    ];
  };
  const rows = months12.map((m) => rowFor(m, "M" + m.month, false));
  if (yearly) rows.push(rowFor(yearly, "Yearly", true));
  return table(heads, rows);
}

function renderSectionB() {
  renderTracker();
  renderSocialLegend();
  const accounts = (state.latest.social.accounts || []).filter((a) => marketOK(a.country));
  const known = (state.config.socialAccounts.accounts || []).length;

  // KPIs
  const withData = accounts.filter((a) => fol(a) != null);
  const totalFollowers = withData.reduce((s, a) => s + Number(fol(a)), 0);
  const anyGrowth = accounts.some((a) => gro(a) != null);
  const totalGrowth = accounts.reduce((s, a) => s + (Number(gro(a)) || 0), 0);
  const pending = (accounts.length || known) - withData.length;
  $("social-kpis").innerHTML = `
    <div class="kpi"><div class="k-label">Public followers tracked</div>
      <div class="k-value">${withData.length ? totalFollowers.toLocaleString() : "—"}</div>
      <div class="k-sub">${withData.length} of ${accounts.length || known} accounts have public data</div></div>
    <div class="kpi"><div class="k-label">Net follower growth (core KPI)</div>
      <div class="k-value">${anyGrowth ? (totalGrowth >= 0 ? "+" : "") + totalGrowth.toLocaleString() : "—"}</div>
      <div class="k-sub">${anyGrowth ? "week-over-week" : "baseline — WoW starts next week"}</div></div>
    <div class="kpi"><div class="k-label">Pending platform access</div>
      <div class="k-value">${pending}</div>
      <div class="k-sub">${gapBadge("need API key / backend / export")}</div></div>`;

  const srcTag = (a) => a.source ? `<span class="tag tag-note mini">${esc((a.source + "").split(" ")[0])}</span>`
    : (fol(a) != null ? `<span class="tag tag-ok mini">public</span>` : gapBadge("pending"));
  $("social-wrap").outerHTML = `<div id="social-wrap">${
    accounts.length
      ? table(
          ["Platform", "Account", "Followers", "Growth", "Posts", "Views", "Likes", "Comments",
           `Shares <span class="tag tag-cred mini">creds</span>`,
           `Impr. <span class="tag tag-cred mini">creds</span>`,
           `Reach <span class="tag tag-cred mini">creds</span>`,
           `Eng% <span class="tag tag-cred mini">creds</span>`, "Src"],
          accounts.map((a) => [
            `<td>${esc(a.platform)}</td>`,
            `<td>${a.accountUrl ? `<a href="${esc(a.accountUrl)}" target="_blank">${esc(a.accountName)}</a>` : esc(a.accountName)}</td>`,
            `<td class="num">${fmtNum(fol(a))}</td>`, signedCell(gro(a), fol(a), null),
            `<td class="num">${fmtNum(a.posts)}</td>`, `<td class="num">${fmtNum(views(a))}</td>`,
            `<td class="num">${fmtNum(a.likes)}</td>`, `<td class="num">${fmtNum(a.comments)}</td>`,
            `<td class="num">${fmtNum(a.shares)}</td>`, `<td class="num">${fmtNum(a.impressions)}</td>`,
            `<td class="num">${fmtNum(a.reach)}</td>`, `<td class="num">${fmtNum(a.engagementRate)}</td>`,
            `<td>${srcTag(a)}</td>`,
          ])
        )
      : `<div class="table-wrap"><table><tbody><tr class="blocked-row"><td>${regionalNote(known)}</td></tr></tbody></table></div>`
  }</div>`;

  renderMonthly();
}

// Section B has no Kuwait/UAE rows because no Kuwait/UAE accounts EXIST — verified
// 2026-09-23. That is a structural fact, not a collection gap, and an empty table
// implies the wrong one. Sections A and C do carry per-market data.
function regionalNote(known) {
  if (state.market === "ALL")
    return `${gapBadge(known + " accounts identified")} — weekly metrics pending platform access.`;
  return `${gapBadge("No " + esc(state.market) + "-specific accounts exist")}
    All ${known} accounts are <strong>regional</strong> (KSA-branded, serving KSA · KWT · UAE) — verified
    2026-09-23 against the live platforms. Their followers are <em>not</em> attributable to a single
    market, so they are shown only under <strong>All</strong>.
    Sections A and C <em>do</em> have ${esc(state.market)} data.`;
}

// Monthly (≈ last 4 weeks) rollup per platform.
// Two kinds of metric, handled differently on purpose (brief §5 — never let one
// metric stand in for another, never sum across incompatible scopes):
//   STOCK (followers): aggregate PER ACCOUNT first — earliest and latest value in
//     the window — then sum the accounts. Summing raw rows across snapshots would
//     count the same account once per week; taking "the last row seen" reported a
//     platform by whichever account happened to come last (TikTok showed 1,795
//     instead of 227,795).
//   FLOW (posts, likes, comments, shares, impressions, reach, engagement): genuine
//     per-period counts, so these do sum across the window.
// `views` is deliberately EXCLUDED from summing: for YouTube it holds a median of
// recent video views, an average — adding four weeks of averages is meaningless.
// The latest week's value is shown instead, labelled as a median.
const FLOW_METRICS = ["posts", "likes", "comments", "shares", "impressions", "reach", "engagement"];

function renderMonthly() {
  const wrap = $("social-monthly");
  if (!wrap) return;
  const snaps = state.history || [];
  const byPlat = {};

  snaps.forEach((s) => (s.social.accounts || []).forEach((a) => {
    if (!marketOK(a.country)) return;
    const p = a.platform || "?";
    const b = (byPlat[p] = byPlat[p] || { flows: {}, accounts: {}, latestViews: null, any: false });

    FLOW_METRICS.forEach((m) => {
      if (a[m] != null) { b.flows[m] = (b.flows[m] || 0) + Number(a[m]); b.any = true; }
    });

    const key = a.accountUrl || a.accountName || "?";
    const f = a.followers ?? a.endFollowers;
    if (f != null) {
      const acc = (b.accounts[key] = b.accounts[key] || { first: null, last: null, seen: 0 });
      if (acc.first == null) acc.first = Number(f);
      acc.last = Number(f);
      acc.seen += 1;
      b.any = true;
    }
    const v = a.views ?? a.avgVideoViews;
    if (v != null) { b.latestViews = Number(v); b.any = true; }  // snapshots are oldest→newest
  }));

  const sumAccounts = (b, field) => {
    const vals = Object.values(b.accounts).map((x) => x[field]).filter((n) => n != null);
    return vals.length ? vals.reduce((s, n) => s + n, 0) : null;
  };
  // Window growth only counts accounts measured in at least TWO snapshots. An account
  // seen once has first === last, which would otherwise render a confident "±0" when
  // the truth is "no baseline yet" — exactly the fabricated-zero the brief forbids.
  const windowGrowth = (b) => {
    const deltas = Object.values(b.accounts)
      .filter((x) => x.seen > 1 && x.first != null && x.last != null)
      .map((x) => x.last - x.first);
    return deltas.length ? deltas.reduce((s, n) => s + n, 0) : null;
  };

  const plats = Object.entries(byPlat).filter(([, b]) => b.any);
  const win = snaps.length;
  wrap.innerHTML = `<h3 class="sub">Monthly rollup <span class="tag tag-note">≈ last ${win} week(s)</span>
      <span class="tag tag-note">followers summed per account · flows summed per period</span></h3>` + (
    plats.length
      ? table(["Platform", "Accounts", "Followers (latest)", "Growth (window)", "Posts",
               `Views <span class="tag tag-note mini">median, latest wk</span>`, "Impr.", "Engagement"],
          plats.map(([p, b]) => {
            const last = sumAccounts(b, "last");
            const n = Object.keys(b.accounts).length;
            return [
              `<td>${esc(p)}</td>`, `<td class="num">${n || "—"}</td>`,
              `<td class="num">${fmtNum(last)}</td>`,
              signedCell(windowGrowth(b), null, null),
              `<td class="num">${fmtNum(b.flows.posts ?? null)}</td>`,
              `<td class="num">${fmtNum(b.latestViews)}</td>`,
              `<td class="num">${fmtNum(b.flows.impressions ?? null)}</td>`,
              `<td class="num">${fmtNum(b.flows.engagement ?? null)}</td>`,
            ];
          }))
      : `<div class="table-wrap"><table><tbody><tr class="blocked-row"><td>${
          state.market === "ALL"
            ? "Monthly totals accumulate as weekly data comes in."
            : `No ${esc(state.market)}-specific accounts exist — the regional accounts roll up under <strong>All</strong>.`
        }</td></tr></tbody></table></div>`
  );
}
function ttAvgLabel(list) {
  if (!list.length) return "—";
  const avg = Math.round(list.reduce((s, a) => s + Number(a.avgVideoViews), 0) / list.length);
  return avg.toLocaleString();
}

function renderSectionC() {
  const r = state.latest.reviews;

  const ratings = (r.storeRatings.entries || []).filter((e) => marketOK(e.market));
  $("ratings-wrap").outerHTML = `<div id="ratings-wrap">${
    ratings.length
      ? table(
          ["Market", "App", "Store", "Rating", "#Ratings", "ΔRating", "1–2★ share"],
          ratings.map((e) => [
            `<td>${esc(e.market)}</td>`, `<td>${esc(e.app || "—")}</td>`, `<td>${esc(e.store)}</td>`,
            `<td class="num">${fmtRating(e.rating)}</td>`,
            `<td class="num">${esc(e.ratingCount)}${e.ratingCountNote ? ' <span class="tag tag-note mini">global</span>' : ""}</td>`,
            deltaCell(e.rating, e.prevRating),
            `<td class="num">${e.oneTwoStarShare == null ? gapBadge("n/a") : esc(e.oneTwoStarShare)}</td>`,
          ])
        )
      : `<div class="table-wrap"><table><tbody><tr class="blocked-row"><td>${gapBadge("Confirm app IDs, then run scripts/fetch_appstore.py (ratings + reviews)")}</td></tr></tbody></table></div>`
  }</div>`;

  // Review Themes removed from the board 2026-09-23 — never populated (theme tagging is
  // manual and has not been run). Representative reviews below carry the sentiment signal.

  const revs = r.representativeReviews.entries || [];
  $("reviews-wrap").innerHTML = revs.length
    ? revs.map((v) => `<div class="review-card"><div class="q">“${esc(v.quote)}”</div>
        <div class="meta"><span>${esc(v.market)} · ${esc(v.store)}${v.app ? " · " + esc(v.app) : ""}</span>
        ${v.language ? `<span>${esc(v.language)}</span>` : ""}
        <span>${esc(v.date)}</span><span class="tag ${sentimentClass(v.sentiment)}">${esc(v.sentiment)}</span>
        <span>evidence: ${esc(v.evidenceStrength ?? "—")}</span>
        ${v.link ? `<a href="${esc(v.link)}" target="_blank">source</a>` : ""}</div></div>`).join("")
    : emptyNote("3–5 representative reviews will appear here once collection runs. Never escalate a single review into an overall conclusion.");
}
function sentimentClass(s = "") {
  s = s.toLowerCase();
  if (s.includes("neg")) return "tag-bad";
  if (s.includes("pos")) return "tag-ok";
  return "tag-note";
}

/* ---------- Section D · Website Traffic ---------- */
const WEB_COLS = [
  { key: "sessions", label: "Sessions" }, { key: "users", label: "Users" },
  { key: "newUsers", label: "New users" }, { key: "pageviews", label: "Pageviews" },
  { key: "avgEngagementTimeSec", label: "Avg engage (s)" }, { key: "bounceRate", label: "Bounce %" },
  { key: "conversions", label: "Conversions" },
];

function renderSectionD() {
  const wrap = $("website-wrap");
  if (!wrap) return;
  const w = state.website;
  if (!w) { wrap.innerHTML = emptyNote("website-traffic.json not found — run scripts/fetch_website_traffic.py."); return; }
  const meta = w.meta || {};
  const months = w.months || [];

  // Live path — a source is connected and monthly rows exist.
  if (meta.status === "live" && months.length) {
    const totalSessions = months.reduce((s, m) => s + (Number(m.sessions) || 0), 0);
    const series = [{ label: "Sessions", color: CHART_COLORS[1],
      points: months.map((m) => ({ label: monthNum(m.month), value: m.sessions })) }];
    const heads = ["Month", ...WEB_COLS.map((c) => c.label)];
    const rows = months.map((m) => [
      `<td>M${esc(m.month)}</td>`, ...WEB_COLS.map((c) => `<td class="num">${fmtNum(m[c.key])}</td>`),
    ]);
    wrap.innerHTML = `<div class="src-line">Source: ${esc(meta.source || "CSV import")} · ${esc((w.sites || []).join(", ") || "site TBC")} · captured ${esc(meta.capturedAt || "—")}</div>
      <div class="kpi-row"><div class="kpi"><div class="k-label">Sessions · YTD</div>
        <div class="k-value">${fmtCompact(totalSessions)}</div><div class="k-sub">${months.length} month(s)</div></div></div>
      <div class="chart-title">Sessions — monthly</div>${lineChart(series, { valueFmt: fmtCompact })}
      ${table(heads, rows)}`;
    return;
  }

  // Blocked path — no analytics source yet. Surface exactly what's needed (manager:
  // "if you encounter any blockers, let me know immediately").
  const bl = meta.blocker || {};
  const qs = (bl.questionsForManager || []).map((q) => `<li>${esc(q)}</li>`).join("");
  wrap.innerHTML = `<div class="blocker">
    <div class="blocker-title"><span class="tag tag-gap">blocked · needs data source</span>
      Website traffic is ready to render — it just needs a source connected.</div>
    <div class="blocker-body">
      <p><strong>Blocker:</strong> ${esc(bl.issue || "No web-analytics access.")}</p>
      <p><strong>Needs:</strong> ${esc(bl.needs || "")}</p>
      <p><strong>Owner:</strong> ${esc(bl.owner || "Patrick / Omar")}</p>
      ${qs ? `<p><strong>To confirm with the manager:</strong></p><ul class="plain">${qs}</ul>` : ""}
      <p class="chart-note">${esc(bl.ready || "")}</p>
    </div></div>`;
}

function renderExplanation() {
  const ce = state.latest.report.changeExplanation || { verified: [], hypotheses: [] };
  $("verified-list").innerHTML = ce.verified?.length
    ? ce.verified.map((v) => `<li><strong>${esc(v.observation)}</strong> — ${esc(v.cause)}</li>`).join("")
    : emptyNote("None this week.");
  $("hypotheses-list").innerHTML = ce.hypotheses?.length
    ? ce.hypotheses.map((h) => `<li><strong>${esc(h.observation)}</strong> — ${esc(h.hypothesis)}</li>`).join("")
    : emptyNote("None this week.");
}

function renderRisks() {
  const risks = state.latest.report.risks || [];
  $("risks-wrap").outerHTML = `<div id="risks-wrap">${
    table(["Problem", "Impact", "Prob.", "Owner", "Next step", "Deadline"],
      risks.map((k) => [
        `<td>${esc(k.problem)}</td>`, `<td>${esc(k.impact)}</td>`,
        `<td>${esc(k.probability)}</td>`, `<td>${esc(k.owner)}</td>`,
        `<td>${esc(k.nextStep)}</td>`, `<td>${esc(k.deadline)}</td>`,
      ]), "No open risks this week.")
  }</div>`;
}

function renderQuality() {
  const dq = state.latest.meta.dataQuality || [];
  $("quality-wrap").outerHTML = `<div id="quality-wrap">${
    table(["Issue", "Impact", "Status", "Owner"],
      dq.map((q) => [
        `<td>${esc(q.issue)}</td>`, `<td>${esc(q.impact)}</td>`,
        `<td>${statusTag(q.status)}</td>`, `<td>${esc(q.owner)}</td>`,
      ]), "No data-quality issues logged.")
  }</div>`;
}

function renderConfirmations() {
  const c = state.config;
  const rows = [
    ["Competitor list + keywords", "Patrick", c.competitors.status],
    ["51Talk keyword set (EN/AR + products)", "Omar → Patrick", c.brand.keywords.status],
    ["Official social accounts (per market/platform)", "Fei / Omar", c.socialAccounts.status],
    ["iOS / Android app IDs", "Omar / Patrick", c.brand.apps.status],
    ["“Exposure” definition", "Patrick / Fei", c.definitions.exposure.status],
    ["TikTok avg-views method", "Patrick / Fei", c.definitions.tiktokAvgViews.status],
    ["App Store/Play collection method + latency + baseline", "Omar / Patrick", c.definitions.collection.appStore.method ? "set" : "pending-confirmation"],
    ["Dashboard home + Wed submission time", "Patrick", "pending-confirmation"],
  ];
  $("confirmations-wrap").outerHTML = `<div id="confirmations-wrap">${
    table(["Item (brief §7)", "Owner", "Status"],
      rows.map((r) => [`<td>${esc(r[0])}</td>`, `<td>${esc(r[1])}</td>`, `<td>${statusTag(r[2])}</td>`]))
  }</div>`;
}

document.addEventListener("DOMContentLoaded", boot);
