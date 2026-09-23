/* 51Talk ME Brand Weekly Monitoring Dashboard — MVP app logic.
   No build step. Loads JSON from /data, renders the brief's 3 sections + 5-part report.
   Serve locally:  python3 -m http.server 8000  →  http://localhost:8000  */

const DATA = "data";
const state = { config: null, manifest: null, latest: null, history: [], market: "ALL" };

async function fetchJSON(path) {
  const res = await fetch(`${path}?_=${Date.now()}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
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
    btn.addEventListener("click", () => { state.market = btn.dataset.code; renderMarketFilter(); renderSectionA(); renderSectionB(); renderSectionC(); })
  );
}

function renderConclusions() {
  const items = state.latest.report.conclusions || [];
  $("conclusions-list").innerHTML = items.length
    ? items.map((c) => `<li>${esc(c.text)}</li>`).join("")
    : emptyNote("No conclusions authored yet.");
}

function renderSectionA() {
  const b = state.latest.brand;

  // Google Trends
  const gt = (b.googleTrends.entries || []).filter((e) => marketOK(e.market));
  $("trends-wrap").outerHTML = `<div id="trends-wrap">${
    gt.length
      ? table(
          ["Market", "Keyword", "This wk", "Prev", "WoW", "4-wk trend", "YoY", "Peak", "Source"],
          gt.map((e) => [
            `<td>${esc(e.market)}</td>`, `<td>${esc(e.keyword ?? b.googleTrends.keyword)}</td>`,
            `<td class="num">${esc(e.current)}</td>`, `<td class="num">${esc(e.prevWeek)}</td>`,
            deltaCell(e.current, e.prevWeek), `<td>${sparkline(e.series)}</td>`,
            `<td class="num">${esc(e.yoy ?? "—")}</td>`,
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

  // Competitor comparison was removed from the board 2026-09-23 — it never carried data
  // (blocked on Patrick's competitor list). The blocker is still tracked in ⑤ Open
  // Confirmations, so nothing is lost; only the permanently-empty table is gone.
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

function renderSectionB() {
  renderSocialLegend();
  const accounts = (state.latest.social.accounts || []).filter((a) => marketOK(a.country));
  const known = (state.config.socialAccounts.accounts || []).length;

  // KPIs
  const withData = accounts.filter((a) => a.endFollowers != null);
  const totalFollowers = withData.reduce((s, a) => s + Number(a.endFollowers), 0);
  const anyGrowth = accounts.some((a) => a.netFollowerGrowth != null);
  const totalGrowth = accounts.reduce((s, a) => s + (Number(a.netFollowerGrowth) || 0), 0);
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

  const fol = (a) => a.followers ?? a.endFollowers;
  const gro = (a) => a.followerGrowth ?? a.netFollowerGrowth;
  const views = (a) => a.views ?? a.avgVideoViews;
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
