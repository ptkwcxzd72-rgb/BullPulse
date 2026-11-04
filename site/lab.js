// BullPulse Strategy Lab: the page (builder, results, comparison, forward tracking).
// The backtest itself is in lab-engine.js.
(() => {
"use strict";
const E = window.LabEngine;
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const store = { get(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
const enc = o => btoa(unescape(encodeURIComponent(JSON.stringify(o)))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const dec = t => { try { return JSON.parse(decodeURIComponent(escape(atob(t.replace(/-/g, "+").replace(/_/g, "/"))))); } catch (e) { return null; } };
const pc = (v, d = 1) => v == null || !isFinite(v) ? "–" : Math.abs(v) < 0.5 * Math.pow(10, -d - 2) ? (0).toFixed(d) + "%" : (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(d) + "%";
const pl = (v, d = 1) => v == null || !isFinite(v) ? "–" : (v * 100).toFixed(d) + "%";
const cls = v => v > 0 ? "pos" : v < 0 ? "neg" : "flat";
const MKT = { LSE: "UK", US: "US" };
const HOLD = 24; // hidden final months

const RFIELDS = [["score", "Score (trend and momentum, 0–100)"], ["T", "Trend percentile"], ["M", "Momentum percentile"], ["G", "Growth percentile"],
  ["FP", "Fundamental checks passed (of 30)"], ["Vp", "Cheapness against fair value (percentile)"], ["d200", "Price vs 200-day average, %"], ["ret1y", "1-year return, %"],
  ["mom", "12-month momentum, %"], ["hi52", "Price vs 52-week high, %"], ["vol1y", "Volatility, %"], ["rsi", "RSI (14 days)"], ["revGrowth", "Revenue growth, %"],
  ["epsGrowth", "Earnings growth, %"], ["pe", "P/E ratio"], ["divY", "Dividend yield, %"], ["fcfY", "Free-cash-flow yield, %"], ["roe", "Return on equity, %"],
  ["de", "Debt to equity, %"], ["fairVs", "Price vs fair value, %"], ["mcapBn", "Market cap, $bn"], ["insB", "Insiders buying, 90 days (US)"],
  ["sue", "Earnings surprise (US)"], ["rev1m", "Last month's return, %"]];
const PRESETS = {
  "Momentum leaders": { rules: [["M", ">=", 70], ["d200", ">=", 0]], w: { T: 40, M: 60, G: 0, F: 0, V: 0 }, top: 20, keep: 40 },
  "Quality at a fair price": { rules: [["FP", ">=", 18], ["roe", ">=", 12], ["fairVs", "<=", 10]], w: { T: 20, M: 0, G: 0, F: 50, V: 30 }, top: 20, keep: 30 },
  "Dividend income": { rules: [["divY", ">=", 3], ["de", "<=", 150]], w: { T: 30, M: 0, G: 0, F: 50, V: 20 }, top: 25, keep: 40 },
  "Growth at a sensible price": { rules: [["revGrowth", ">=", 10], ["fairVs", "<=", 20]], w: { T: 20, M: 0, G: 40, F: 0, V: 40 }, top: 20, keep: 30 },
  "Insider buying (US)": { rules: [["insB", ">=", 2]], w: { T: 30, M: 0, G: 0, F: 40, V: 30 }, top: 20, keep: 30, market: "US" },
  "Strong earnings surprise (US)": { rules: [["sue", ">=", 2]], w: { T: 50, M: 50, G: 0, F: 0, V: 0 }, top: 20, keep: 30, market: "US" },
};
const COLORS = ["var(--accent)", "var(--fm)", "var(--amber)", "var(--blue)"];

let P, FX, D, BY = {}, MONTHLY = null, BENCH = null;
let UI = store.get("bp-lab", null) || {
  mode: "list", ids: [], cw: {}, rule: { market: "ALL", idx: "", sector: "", noTrusts: true, rules: [["score", ">=", 60]], w: { T: 50, M: 50, G: 0, F: 0, V: 0 }, top: 20, keep: 40 },
  weighting: "equal", cap: 20, rebalance: "Q", drift: 5, exit200: false, exitTo: "spread", start: 10000, monthly: 0, ccy: "GBP", from: "", account: "isa",
  costs: { commission: 0.1, spread: 0.1, fxFee: 0.5, stamp: true }, name: "",
};
const seen = new Set(); // strategy versions run this visit

function strategy(u = UI) {
  const src = u.mode === "list" ? { type: "list", ids: u.ids.slice(), w: Object.assign({}, u.cw) }
    : { type: "rule", market: u.rule.market, idx: u.rule.idx, sector: u.rule.sector, noTrusts: u.rule.noTrusts, rules: u.rule.rules.map(r => r.slice()), w: Object.assign({}, u.rule.w), top: +u.rule.top || 20, keep: +u.rule.keep || 0 };
  return { name: u.name || "", source: src, weighting: u.weighting, cap: +u.cap || 0, rebalance: u.rebalance, drift: +u.drift || 5, exit200: !!u.exit200, exitTo: u.exitTo, ...(u.swaps === false ? { swaps: false } : {}),
    start: +u.start || 0, monthly: +u.monthly || 0, ccy: u.ccy, from: u.from, account: u.account, costs: Object.assign({}, u.costs) };
}
function fromStrategy(S) {
  const u = JSON.parse(JSON.stringify(UI));
  const s = S.source || {};
  if (s.type === "list") { u.mode = "list"; u.ids = s.ids || []; u.cw = s.w || {}; }
  else { u.mode = "rule"; Object.assign(u.rule, { market: s.market || "ALL", idx: s.idx || "", sector: s.sector || "", noTrusts: s.noTrusts !== false, rules: s.rules || [], w: s.w || { T: 50, M: 50 }, top: s.top || 20, keep: s.keep || 0 }); }
  for (const k of ["weighting", "cap", "rebalance", "drift", "exit200", "exitTo", "start", "monthly", "ccy", "from", "account", "name", "swaps"]) if (S[k] !== undefined) u[k] = S[k];
  if (S.swaps === undefined) delete u.swaps;
  if (S.costs) u.costs = Object.assign({}, u.costs, S.costs);
  return u;
}

// ---------- builder ----------
function drawBuilder() {
  document.querySelectorAll("[data-src]").forEach(b => b.setAttribute("aria-pressed", b.dataset.src === UI.mode));
  $("src-list").hidden = UI.mode !== "list"; $("src-rule").hidden = UI.mode !== "rule";
  $("srcn").textContent = UI.mode === "list" ? `${UI.ids.length} stock${UI.ids.length === 1 ? "" : "s"}` : `top ${UI.rule.top}`;
  const custom = UI.weighting === "custom";
  $("lst").innerHTML = UI.ids.map(id => { const s = BY[id]; return s ? `<div class="li"><span><b>${esc(s.name)}</b><small>${MKT[s.ex]} ${esc(s.t)}, ${esc(s.sector)}</small></span>${custom ? `<input type="number" min="0" step="1" data-cw="${id}" value="${UI.cw[id] ?? ""}" aria-label="Weight for ${esc(s.name)}, percent">` : "<span></span>"}<button class="x" data-rm="${id}" aria-label="Remove ${esc(s.name)}">×</button></div>` : ""; }).join("") || `<p class="note">No stocks yet. Add some above, or import them.</p>`;
  $("lst").querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { UI.ids = UI.ids.filter(x => x !== b.dataset.rm); changed(true); });
  $("lst").querySelectorAll("[data-cw]").forEach(i => i.oninput = () => { UI.cw[i.dataset.cw] = +i.value || 0; changed(); });
  $("hindsight").hidden = UI.mode !== "list" || UI.ids.length === 0;
  const R = UI.rule;
  $("r-mkt").value = R.market; $("r-idx").value = R.idx; $("r-sec").value = R.sector; $("r-notr").checked = R.noTrusts;
  $("rules").innerHTML = R.rules.map((r, k) => `<div class="rule"><select data-rf="${k}" aria-label="Measure">${RFIELDS.map(([f, l]) => `<option value="${f}" ${f === r[0] ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
    <select data-ro="${k}" aria-label="Condition"><option value=">=" ${r[1] === ">=" ? "selected" : ""}>at least</option><option value="<=" ${r[1] === "<=" ? "selected" : ""}>at most</option></select>
    <input type="number" step="any" data-rv="${k}" value="${r[2] ?? ""}" aria-label="Value"><button class="x" data-rx="${k}" aria-label="Remove condition">×</button></div>`).join("") || `<p class="note">No conditions: every stock in the market can be picked.</p>`;
  $("rules").querySelectorAll("[data-rf]").forEach(s => s.onchange = () => { R.rules[+s.dataset.rf][0] = s.value; changed(); });
  $("rules").querySelectorAll("[data-ro]").forEach(s => s.onchange = () => { R.rules[+s.dataset.ro][1] = s.value; changed(); });
  $("rules").querySelectorAll("[data-rv]").forEach(s => s.oninput = () => { R.rules[+s.dataset.rv][2] = s.value === "" ? "" : +s.value; changed(); });
  $("rules").querySelectorAll("[data-rx]").forEach(b => b.onclick = () => { R.rules.splice(+b.dataset.rx, 1); changed(true); });
  for (const k of ["T", "M", "G", "F", "V"]) $("w-" + k).value = R.w[k] ?? 0;
  $("r-top").value = R.top; $("r-keep").value = R.keep;
  document.querySelectorAll("#wm button").forEach(b => { b.setAttribute("aria-pressed", b.dataset.w === UI.weighting); b.disabled = b.dataset.w === "custom" && UI.mode !== "list"; });
  $("cap").value = UI.cap; $("reb").value = UI.rebalance; $("drift").value = UI.drift;
  $("driftl").hidden = $("driftd").hidden = UI.rebalance !== "drift";
  $("swaps").checked = UI.swaps === false; $("swapl").hidden = UI.mode === "list";
  $("ex200").checked = UI.exit200; $("exto").hidden = !UI.exit200; $("exw").value = UI.exitTo;
  $("amt").value = UI.start; $("mon").value = UI.monthly; $("ccy").value = UI.ccy; $("from").value = UI.from; $("acct").value = UI.account;
  $("c-com").value = UI.costs.commission; $("c-spr").value = UI.costs.spread; $("c-fx").value = UI.costs.fxFee; $("c-stamp").checked = UI.costs.stamp;
  $("name").value = UI.name || "";
}
let timer = 0;
function changed(redraw) {
  store.set("bp-lab", UI);
  if (redraw) drawBuilder();
  clearTimeout(timer); timer = setTimeout(update, 200);
}
function bindBuilder() {
  document.querySelectorAll("[data-src]").forEach(b => b.onclick = () => { UI.mode = b.dataset.src; if (UI.mode !== "list" && UI.weighting === "custom") UI.weighting = "equal"; changed(true); });
  const add = () => {
    const v = $("add").value.trim().toLowerCase(); if (!v) return;
    const s = D.stocks.find(s => `${s.name} (${s.t})`.toLowerCase() === v) || D.stocks.find(s => s.t.toLowerCase() === v) || D.stocks.find(s => s.name.toLowerCase().includes(v));
    if (!s) { $("msg").textContent = `No company matching "${$("add").value}".`; return; }
    if (!UI.ids.includes(s.id)) UI.ids.push(s.id);
    $("add").value = ""; changed(true);
  };
  $("addb").onclick = add; $("add").onkeydown = e => { if (e.key === "Enter") add(); };
  $("r-mkt").onchange = e => { UI.rule.market = e.target.value; changed(); };
  $("r-idx").onchange = e => { UI.rule.idx = e.target.value; changed(); };
  $("r-sec").onchange = e => { UI.rule.sector = e.target.value; changed(); };
  $("r-notr").onchange = e => { UI.rule.noTrusts = e.target.checked; changed(); };
  $("addrule").onclick = () => { UI.rule.rules.push(["d200", ">=", 0]); changed(true); };
  $("preset").innerHTML = `<option value="">Start from a preset…</option>` + Object.keys(PRESETS).map(k => `<option>${esc(k)}</option>`).join("");
  $("preset").onchange = e => { const p = PRESETS[e.target.value]; if (!p) return; Object.assign(UI.rule, JSON.parse(JSON.stringify({ rules: p.rules, w: p.w, top: p.top, keep: p.keep })), p.market ? { market: p.market } : {}); UI.name = e.target.value; e.target.value = ""; changed(true); };
  for (const k of ["T", "M", "G", "F", "V"]) $("w-" + k).oninput = e => { UI.rule.w[k] = +e.target.value || 0; changed(); };
  $("r-top").oninput = e => { UI.rule.top = Math.max(1, +e.target.value || 20); changed(); };
  $("r-keep").oninput = e => { UI.rule.keep = Math.max(0, +e.target.value || 0); changed(); };
  document.querySelectorAll("#wm button").forEach(b => b.onclick = () => { UI.weighting = b.dataset.w; changed(true); });
  $("cap").oninput = e => { UI.cap = +e.target.value || 100; changed(); };
  $("reb").onchange = e => { UI.rebalance = e.target.value; changed(true); };
  $("drift").oninput = e => { UI.drift = +e.target.value || 5; changed(); };
  $("ex200").onchange = e => { UI.exit200 = e.target.checked; changed(true); };
  $("swaps").onchange = e => { if (e.target.checked) UI.swaps = false; else delete UI.swaps; changed(true); };
  $("exw").onchange = e => { UI.exitTo = e.target.value; changed(); };
  $("amt").oninput = e => { UI.start = +e.target.value || 0; changed(); };
  $("mon").oninput = e => { UI.monthly = +e.target.value || 0; changed(); };
  $("ccy").onchange = e => { UI.ccy = e.target.value; changed(); };
  $("from").onchange = e => { UI.from = e.target.value; changed(); };
  $("acct").onchange = e => { UI.account = e.target.value; changed(); };
  $("c-com").oninput = e => { UI.costs.commission = +e.target.value || 0; changed(); };
  $("c-spr").oninput = e => { UI.costs.spread = +e.target.value || 0; changed(); };
  $("c-fx").oninput = e => { UI.costs.fxFee = +e.target.value || 0; changed(); };
  $("c-stamp").onchange = e => { UI.costs.stamp = e.target.checked; changed(); };
  $("name").oninput = e => { UI.name = e.target.value; store.set("bp-lab", UI); };
  // imports
  $("imp-model").onclick = () => {
    const m = store.get("bp-portfolio", null);
    if (!m || !(m.h || []).length) { $("msg").textContent = "Your model portfolio is empty. Build one on the Portfolio page first."; return; }
    UI.mode = "list"; UI.ids = m.h.filter(id => BY[id]); UI.cw = m.mw || {}; UI.weighting = m.m === "custom" ? "custom" : m.m === "score" ? "score" : m.m === "risk" ? "invvol" : "equal";
    $("msg").textContent = `Imported ${UI.ids.length} stocks from your model portfolio.`; changed(true);
  };
  $("imp-hold").onclick = () => {
    const h = store.get("bp-holdings", null);
    const lots = (h && h.lots || []).filter(l => BY[l.id]);
    if (!lots.length) { $("msg").textContent = "You have no holdings saved. Add them on the Portfolio page under My holdings."; return; }
    const usd = 1 / ((D.fx && D.fx.USD) || 0.75), val = {};
    lots.forEach(l => { const s = BY[l.id]; val[l.id] = (val[l.id] || 0) + l.sh * (s.ccy === "GBX" ? s.price / 100 : s.price / usd); });
    const tot = Object.values(val).reduce((a, b) => a + b, 0);
    UI.mode = "list"; UI.ids = Object.keys(val); UI.cw = Object.fromEntries(Object.entries(val).map(([k, v]) => [k, Math.round(v / tot * 1000) / 10])); UI.weighting = "custom";
    $("msg").textContent = `Imported ${UI.ids.length} holdings at today's weights.`; changed(true);
  };
  $("imp-screen").onclick = () => {
    const sc = store.get("bp-screen", null);
    if (!sc || !sc.rules) { $("msg").textContent = "No screen saved yet. Build one under Build your own in the screener."; return; }
    const known = new Set(RFIELDS.map(r => r[0]).concat(["insb", "FA0", "FA1", "FA2", "FA3", "FA4", "epsGrowth", "implied"]));
    const skipped = sc.rules.filter(r => !known.has(r[0]));
    UI.mode = "rule"; UI.rule.rules = sc.rules.filter(r => known.has(r[0])).map(r => [r[0] === "insb" ? "insB" : r[0], r[1], r[2], r[3]]);
    UI.rule.w = { T: sc.w.T || 0, M: sc.w.M || 0, G: sc.w.G || 0, F: sc.w.F || 0, V: sc.w.V || 0 };
    $("msg").textContent = "Imported your screener screen." + (skipped.length ? ` Left out (no history to test): ${skipped.map(r => r[0]).join(", ")}.` : "") + (sc.w.S ? " News sentiment has no history, so its weight is dropped." : "");
    changed(true);
  };
  $("imp-inv").onclick = () => { location.href = "investors.html"; };
  $("share").onclick = async () => {
    const url = location.origin + location.pathname + "#s=" + enc(strategy());
    try { await navigator.clipboard.writeText(url); $("msg").textContent = "Link copied. Anyone opening it sees this strategy."; } catch (e) { $("msg").innerHTML = `Copy this link: <input class="inp" readonly value="${esc(url)}" onclick="this.select()" style="width:100%">`; }
  };
  document.querySelectorAll("[data-slot]").forEach(b => b.onclick = () => {
    const slots = store.get("bp-lab-slots", [null, null, null]);
    const S = strategy(); S.name = UI.name || `Strategy ${"ABC"[+b.dataset.slot]}`;
    slots[+b.dataset.slot] = S; store.set("bp-lab-slots", slots);
    $("msg").textContent = `Saved as ${"ABC"[+b.dataset.slot]}.`; update();
  });
  $("track").onclick = startTracking;
}

// ---------- results ----------
let LAST = null;
function update() {
  const S = strategy();
  if (S.source.type === "list" && !S.source.ids.length) { $("res").innerHTML = `<div class="card emptyp"><h2 style="margin:0 0 6px;color:var(--ink);font:650 20px var(--f-display)">Add some stocks, or follow a rule</h2><p style="margin:0">Pick companies on the left, import your model portfolio or holdings, or switch to "Follow a rule" to let the strategy choose stocks each month.</p></div>`; drawCompare(null); return; }
  const r = E.run(P, FX, S, { lastDate: D.asof });
  const key = E.key(S);
  seen.add(key);
  const tried = store.get("bp-lab-tried", []);
  if (!tried.includes(key)) { tried.push(key); store.set("bp-lab-tried", tried.slice(-500)); }
  const revealed = store.get("bp-lab-revealed", []).includes(key);
  const N = r.rets.length;
  const cut = N >= 60 ? N - HOLD : N;
  const vis = revealed ? N : cut;
  LAST = { S, r, key, cut, vis, revealed };
  render();
}
function windowStats(r, upto) {
  const dates = r.dates.slice(0, upto), inv = r.invested.slice(0, upto);
  const st = E.stats(r.rets.slice(0, upto), dates);
  const b = {};
  for (const k of ["ftse100", "sp500", "avg"]) b[k] = E.stats(E.benchRets(r.bench[k].slice(0, upto), inv), dates);
  return { st, b, dates };
}
function chart(lines, dates, holdFrom) {
  const W = 820, H = 260, padL = 44, padB = 22;
  const all = lines.flatMap(l => l.g).filter(v => v > 0);
  if (!all.length) return "";
  const lo = Math.min(...all), hi = Math.max(...all), L = Math.log;
  const X = k => padL + k / (dates.length) * (W - padL - 50), Y = v => H - padB - (L(v) - L(lo)) / ((L(hi) - L(lo)) || 1) * (H - padB - 12);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Growth of 100, log scale">`;
  // gridlines at round levels
  const steps = [50, 75, 100, 150, 200, 300, 400, 600, 800, 1000, 1500, 2000];
  steps.filter(v => v >= lo * 0.98 && v <= hi * 1.02).forEach(v => { s += `<line x1="${padL}" x2="${W - 50}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${padL - 6}" y="${Y(v) + 4}" font-size="11" text-anchor="end" fill="var(--muted)">${v}</text>`; });
  if (holdFrom != null) s += `<rect x="${X(holdFrom)}" y="6" width="${W - 50 - X(holdFrom)}" height="${H - padB - 6}" fill="color-mix(in srgb,var(--amber) 10%,transparent)"/><text x="${X(holdFrom) + 6}" y="18" font-size="11" fill="var(--warn)">hidden period</text>`;
  const years = [...new Set(dates.map(d => d.slice(0, 4)))];
  years.forEach(y => { const k = dates.findIndex(d => d.slice(0, 4) === y); if (k > 0) s += `<text x="${X(k)}" y="${H - 4}" font-size="11" fill="var(--muted)" text-anchor="middle">${y}</text>`; });
  lines.forEach(l => {
    const d = l.g.map((v, k) => v > 0 ? (k ? "L" : "M") + X(k).toFixed(1) + " " + Y(v).toFixed(1) : "").join("");
    s += `<path d="${d.replace(/^L/, "M")}" fill="none" stroke="${l.c}" stroke-width="${l.w || 1.6}" ${l.dash ? 'stroke-dasharray="5 4"' : ""} vector-effect="non-scaling-stroke"/>`;
    const last = l.g[l.g.length - 1];
    if (last > 0) s += `<text x="${W - 46}" y="${Y(last) + 4}" font-size="11.5" fill="${l.c}" font-weight="600">${Math.round(last)}</text>`;
  });
  return s + "</svg>";
}
const growth = rets => { let g = 100; return [100, ...rets.map(x => (g *= 1 + (x ?? 0)))]; };
function money(v, ccy) { const c = ccy === "USD" ? "$" : "£"; return (v < 0 ? "−" : "") + c + Math.round(Math.abs(v)).toLocaleString("en-GB"); }

function render() {
  const { S, r, cut, vis, revealed } = LAST;
  const W = windowStats(r, vis), st = W.st, b = W.b;
  if (!st) { $("res").innerHTML = `<div class="card emptyp">Not enough history for this strategy. Try an earlier start or more stocks.</div>`; return; }
  const fin = r.values[vis - 1], inv = r.invested[vis - 1];
  const idxName = (S.source.market || "ALL") === "LSE" ? "ftse100" : "sp500";
  const lines = [{ g: growth(r.rets.slice(0, vis)), c: COLORS[0], w: 2.4 }, { g: growth(E.benchRets(r.bench.sp500.slice(0, vis), r.invested.slice(0, vis))), c: "var(--us)", dash: true },
    { g: growth(E.benchRets(r.bench.ftse100.slice(0, vis), r.invested.slice(0, vis))), c: "var(--uk)", dash: true }, { g: growth(E.benchRets(r.bench.avg.slice(0, vis), r.invested.slice(0, vis))), c: "var(--fm)", w: 1.2 }];
  const dates = [r.months[0], ...r.dates.slice(0, vis)];
  const boot = E.bootstrap(r.rets.slice(0, vis), 1000);
  // earlier and later halves against the average stock
  const half = Math.floor(vis / 2), ann = a => { const x = a.filter(v => v != null); return x.length ? Math.pow(x.reduce((g, v) => g * (1 + v), 1), 12 / x.length) - 1 : null; };
  const avgR = E.benchRets(r.bench.avg.slice(0, vis), r.invested.slice(0, vis));
  const halves = [[0, half], [half, vis]].map(([a, z]) => ({ from: r.months[a].slice(0, 7), to: r.dates[z - 1].slice(0, 7), s: ann(r.rets.slice(a, z)), a: ann(avgR.slice(a, z)) }));
  const both = halves.every(h => h.s - h.a > 0.005);
  // current holdings (latest month-end)
  const V = E.makeView(P), T = E.targets(V, S, P.months.length - 1, new Map());
  const holds = [...T].sort((a, b2) => b2[1] - a[1]);
  const row = (label, f, fmt) => `<tr><td>${label}</td><td><b>${fmt(f(st))}</b></td><td>${fmt(b.sp500 && f(b.sp500))}</td><td>${fmt(b.ftse100 && f(b.ftse100))}</td><td>${fmt(b.avg && f(b.avg))}</td></tr>`;
  const ccy = S.ccy;
  const triedN = store.get("bp-lab-tried", []).length;
  const ban = r.rets.length >= 60 ? (revealed
    ? `<div class="banner ok"><span><b>Final ${HOLD} months revealed for this version.</b> Changing the strategy now makes a new version, judged on the earlier years until you reveal again.</span></div>`
    : `<div class="banner"><span><b>The last ${HOLD} months are hidden</b> so you can't tune the strategy to them. When you're happy with it, reveal them once to see how it does on months it wasn't shaped by. Versions tried: ${seen.size} this visit, ${triedN} in all.</span><button class="bbtn dark" id="reveal">Reveal the hidden period</button></div>`) : "";
  $("res").innerHTML = `${ban}
    <div class="stats">
      <div><span class="sub">${money(inv, ccy)} paid in became</span><span class="v">${money(fin, ccy)}</span><span class="s">${r.dates[vis - 1] ? "by " + new Date(r.dates[vis - 1] + "T12:00:00Z").toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }) : ""}</span></div>
      <div><span class="sub">Return a year</span><span class="v ${cls(st.cagr)}">${pc(st.cagr)}</span><span class="s">S&amp;P 500 ${pc(b.sp500 && b.sp500.cagr)}, FTSE 100 ${pc(b.ftse100 && b.ftse100.cagr)}</span></div>
      <div><span class="sub">Worst fall from a high</span><span class="v neg">${pc(st.maxDD)}</span><span class="s">longest below a high: ${st.longestUnderwater} months</span></div>
      <div><span class="sub">Costs${S.account === "gia" ? " and tax" : ""}</span><span class="v">${money(r.costs + r.tax, ccy)}</span><span class="s">traded ${(r.turnoverYr * 100).toFixed(0)}% of the portfolio a year</span></div>
    </div>
    <div class="card cc"><h3>Growth of 100 <span class="sub">${r.months[0].slice(0, 7)} to ${(r.dates[vis - 1] || "").slice(0, 7)}, log scale, after costs${S.account === "gia" ? " and tax" : ""}</span></h3>
      ${chart(lines, dates, revealed && r.rets.length >= 60 ? cut + 1 : null)}
      <div class="leg"><span><i style="background:${COLORS[0]}"></i>${esc(S.name || "This strategy")}</span><span><i style="background:var(--us)"></i>S&amp;P 500 fund</span><span><i style="background:var(--uk)"></i>FTSE 100 fund</span><span><i style="background:var(--fm)"></i>Average stock${S.source.market && S.source.market !== "ALL" ? " in the market" : ""}</span><span>All in ${ccy === "USD" ? "dollars" : "pounds"}, dividends reinvested</span></div>
    </div>
    <div class="card cc"><h3>Compared with the alternatives</h3>
      <div class="tw"><table class="tt"><thead><tr><th></th><th>Strategy</th><th>S&amp;P 500</th><th>FTSE 100</th><th>Average stock</th></tr></thead><tbody>
      ${row("Return a year", s => s.cagr, pc)}${row("Yearly swing (volatility)", s => s.vol, pl)}${row("Return per unit of risk (Sharpe, before cash)", s => s.sharpe, v => v == null ? "–" : v.toFixed(2))}
      ${row("Same, counting only falls (Sortino)", s => s.sortino, v => v == null ? "–" : v.toFixed(2))}${row("Worst fall from a high", s => s.maxDD, pc)}
      ${row("Best year", s => s.bestYear, pc)}${row("Worst year", s => s.worstYear, pc)}${row("Months up", s => s.positive, v => v == null ? "–" : Math.round(v * 100) + "%")}
      ${row("Worst 3 years, a year", s => s.roll3min, pc)}${row("Best 3 years, a year", s => s.roll3max, pc)}
      </tbody></table></div>
      <p class="note">Index funds and the average stock get the same money on the same dates, without dealing costs. Sharpe and Sortino here use returns before any cash rate.</p>
    </div>
    ${boot ? `<div class="card cc"><h3>The range of outcomes <span class="sub">1,000 reshuffles of the strategy's own years</span></h3>
      ${rangeBar(boot)}
      <p class="note">History happened only one way. Reshuffling 12-month blocks of this strategy's returns gives a sense of what else was likely: half the time between ${pc(boot.p25)} and ${pc(boot.p75)} a year, and nine times in ten between ${pc(boot.p5)} and ${pc(boot.p95)}.${boot.lossAfter5 != null ? ` The chance of having lost money after five years: ${Math.round(boot.lossAfter5 * 100)}%.` : ""}</p></div>` : ""}
    <div class="card cc"><h3>Does it hold up in both halves?</h3>
      <div class="tw"><table class="tt"><thead><tr><th></th><th>Strategy, a year</th><th>Average stock, a year</th><th>Difference</th></tr></thead><tbody>
      ${halves.map((h, k) => `<tr><td>${k ? "Later" : "Earlier"} half, ${h.from} to ${h.to}</td><td>${pc(h.s)}</td><td>${pc(h.a)}</td><td class="${cls(h.s - h.a)}"><b>${pc(h.s - h.a)}</b></td></tr>`).join("")}
      </tbody></table></div>
      <p class="note">${both ? "It beat the average stock in both halves, a good sign, though not proof." : "It didn't beat the average stock in both halves. A result that depends on one period is often luck, or rules fitted to the past."}</p>
    </div>
    <div class="card cc"><h3>Year by year</h3><div class="years">${Object.entries(st.years).map(([y, g]) => `<span><b>${y}</b> <span class="${cls(g - 1)}">${pc(g - 1)}</span></span>`).join("")}</div></div>
    <div class="card cc"><h3>What it would hold now <span class="sub">${holds.length} stock${holds.length === 1 ? "" : "s"}, at the latest month-end</span></h3>
      ${holds.length ? `<div class="tw"><table class="tt"><thead><tr><th>Company</th><th>Weight</th><th>Score today</th></tr></thead><tbody>${holds.map(([i, w]) => { const s = BY[P.ids[i]]; return `<tr><td>${s ? `<a href="app.html#${s.id}">${esc(s.name)}</a> <span class="sub">${MKT[s.ex]} ${esc(s.t)}</span>` : esc(P.ids[i])}</td><td>${pl(w)}</td><td>${s ? s.score : "–"}</td></tr>`; }).join("")}</tbody></table></div>` : `<p class="note">Nothing passes the rules at the latest month-end.</p>`}
      ${r.missing ? `<p class="note">${r.missing} stock-months had no price and were held at their last value.</p>` : ""}
    </div>
    <div class="card cc" id="compare"></div>`;
  if ($("reveal")) $("reveal").onclick = () => { const v = store.get("bp-lab-revealed", []); v.push(LAST.key); store.set("bp-lab-revealed", v.slice(-300)); update(); };
  drawCompare(LAST);
}
function rangeBar(b) {
  const lo = Math.min(-0.1, b.p5) - 0.02, hi = Math.max(0.2, b.p95) + 0.02, X = v => ((v - lo) / (hi - lo) * 100).toFixed(1) + "%";
  return `<div class="range" aria-hidden="true"><span class="ax"></span><span class="w" style="left:${X(b.p5)};width:calc(${X(b.p95)} - ${X(b.p5)})"></span><span class="b" style="left:${X(b.p25)};width:calc(${X(b.p75)} - ${X(b.p25)})"></span><span class="m" style="left:${X(b.p50)}"></span>${lo < 0 ? `<span class="z" style="left:${X(0)}"></span>` : ""}</div>
    <div class="rlab"><span>${pc(lo, 0)} a year</span><span>middle: ${pc(b.p50)}</span><span>${pc(hi, 0)}</span></div>`;
}
function drawCompare(cur) {
  const box = $("compare"); if (!box) return;
  const slots = store.get("bp-lab-slots", [null, null, null]);
  const items = [];
  if (cur) items.push({ name: cur.S.name || "This strategy", S: cur.S, color: COLORS[0] });
  slots.forEach((S, k) => { if (S) items.push({ name: `${"ABC"[k]}: ${S.name || "Strategy " + "ABC"[k]}`, S, color: COLORS[k + 1], slot: k }); });
  if (items.length < 2) { box.innerHTML = `<h3>Compare strategies</h3><p class="note">Save up to three strategies as A, B and C (on the left) to compare them here, measured over the same years.</p>`; return; }
  const runs = items.map(it => ({ it, r: E.run(P, FX, Object.assign({}, it.S, { from: cur ? cur.S.from : it.S.from, start: 10000, monthly: 0 }), { lastDate: D.asof }) }));
  const n = Math.min(...runs.map(x => x.r.rets.length)), upto = n >= 60 && !(cur && cur.revealed) ? n - HOLD : n;
  const lines = runs.map(x => ({ g: growth(x.r.rets.slice(0, upto)), c: x.it.color, w: 2 }));
  const dates = [runs[0].r.months[0], ...runs[0].r.dates.slice(0, upto)];
  const sts = runs.map(x => E.stats(x.r.rets.slice(0, upto), x.r.dates.slice(0, upto)));
  box.innerHTML = `<h3>Compare strategies <span class="sub">same start, £10,000 each, up to the hidden period</span></h3>
    <div class="slots">${items.map(it => `<span class="slot"><i style="background:${it.color}"></i>${esc(it.name)}${it.slot != null ? ` <button class="x" data-load="${it.slot}" title="Load into the builder" aria-label="Load">↺</button><button class="x" data-del="${it.slot}" aria-label="Remove">×</button>` : ""}</span>`).join("")}</div>
    ${chart(lines, dates, null)}
    <div class="tw"><table class="tt"><thead><tr><th></th>${items.map(it => `<th style="color:${it.color}">${esc(it.name)}</th>`).join("")}</tr></thead><tbody>
    ${[["Return a year", s => pc(s.cagr)], ["Volatility", s => pl(s.vol)], ["Sharpe", s => s.sharpe == null ? "–" : s.sharpe.toFixed(2)], ["Worst fall", s => pc(s.maxDD)], ["Worst 3 years, a year", s => pc(s.roll3min)]].map(([l, f]) => `<tr><td>${l}</td>${sts.map(s => `<td>${s ? f(s) : "–"}</td>`).join("")}</tr>`).join("")}
    <tr><td>Costs</td>${runs.map(x => `<td>${money(x.r.costs, x.r.ccy)}</td>`).join("")}</tr>
    </tbody></table></div>`;
  box.querySelectorAll("[data-load]").forEach(b => b.onclick = () => { UI = fromStrategy(slots[+b.dataset.load]); changed(true); });
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { slots[+b.dataset.del] = null; store.set("bp-lab-slots", slots); drawCompare(LAST); });
}

// ---------- forward tracking ----------
// tonight's values for each stock, in the panel's units, so the same rules pick today's stocks
function snapshotPanel() { return E.snapshotPanel(D); }
function startTracking() {
  const S = strategy();
  if (S.source.type === "list" && !S.source.ids.length) { $("msg").textContent = "Add some stocks first."; return; }
  const P1 = snapshotPanel();
  const T = E.targets(E.makeView(P1), S, 0, new Map());
  if (!T.size) { $("msg").textContent = "Nothing passes the rules today, so there's nothing to track yet."; return; }
  const picks = [...T].map(([i, w]) => [P1.ids[i], Math.round(w * 10000) / 10000, BY[P1.ids[i]].price]);
  const rec = { id: Math.random().toString(36).slice(2, 10), name: UI.name || "Untitled strategy", S, start: D.asof, picks, created: new Date().toISOString().slice(0, 10) };
  const list = store.get("bp-lab-tracked", []); list.unshift(rec); store.set("bp-lab-tracked", list.slice(0, 20));
  $("msg").textContent = `Tracking "${rec.name}" from the close on ${D.asof}. It's saved in this browser; copy its link to keep it elsewhere.`;
  drawTracked();
  $("tracked").scrollIntoView({ behavior: "smooth", block: "start" });
}
async function loadTrackingData() {
  if (!MONTHLY) { try { MONTHLY = await (await fetch("data/monthly.json", { cache: "no-cache" })).json(); } catch (e) { MONTHLY = { months: [], ids: [], px: [] }; } }
  if (!BENCH) { try { BENCH = await (await fetch("data/bench.json", { cache: "no-cache" })).json(); } catch (e) { BENCH = {}; } }
}
// value of a tracked strategy: the start picks to the first month-end, then month by month using
// month-end closes, rebalancing on the strategy's schedule (rules re-applied to each month-end in the
// history panel once it is published). Costs on trades; no tax; no money added.
function trackValue(rec) {
  const M = MONTHLY, k0 = M.months.indexOf(rec.start.slice(0, 7));
  const col = new Map(M.ids.map((id, i) => [id, i]));
  const px = (id, k) => { const i = col.get(id); return i == null ? null : M.px[i][k]; };
  if (k0 < 0) return null;
  const S = rec.S, c = Object.assign({ commission: 0.1, spread: 0.1, fxFee: 0.5, stamp: true }, S.costs || {});
  const ccy = S.ccy || "GBP";
  const fxAt = d => E.fxAt(FX, d);
  let hold = new Map(rec.picks.map(([id, w]) => [id, w]));
  const p0 = new Map(rec.picks.map(([id, , p]) => [id, p]));
  const seg0 = rec.seg0 || {};
  let value = 1, dates = [rec.start], vals = [1];
  const last = M.months.length - 1;
  const monthEnd = k => k === last ? M.asof : M.months[k] + "-28";
  const fxf = (id, a, b) => { const ex = id.startsWith("LSE-") ? "LSE" : "US"; const x = fxAt(a), y = fxAt(b); if (!x || !y) return 1; if (ccy === "GBP" && ex === "US") return x / y; if (ccy === "USD" && ex === "LSE") return y / x; return 1; };
  // first segment: start to the end of the start month (or to now)
  let total = 0, newVals = new Map();
  for (const [id, w] of hold) {
    let ratio;
    if (seg0[id] != null && k0 < last) ratio = seg0[id];
    else { const p = px(id, k0), a = p0.get(id); ratio = p && a ? p / a : 1; if (k0 < last && p && a) seg0[id] = ratio; }
    const v = w * ratio * fxf(id, rec.start, monthEnd(k0));
    newVals.set(id, v); total += v;
  }
  if (k0 < last && !rec.seg0) { rec.seg0 = seg0; const list = store.get("bp-lab-tracked", []); const r = list.find(x => x.id === rec.id); if (r) { r.seg0 = seg0; store.set("bp-lab-tracked", list); } }
  value = total; dates.push(monthEnd(k0)); vals.push(value);
  let cur = newVals;
  for (let k = k0 + 1; k <= last; k++) {
    // decide at the month-end k-1
    const mo = +M.months[k - 1].slice(5, 7);
    const sched = S.rebalance === "M" || (S.rebalance === "Q" && mo % 3 === 0) || (S.rebalance === "Y" && mo === 12);
    let target = null;
    if (S.source.type !== "list") {
      const m = P.months.findIndex(d => d.slice(0, 7) === M.months[k - 1]);
      if (m >= 0) { const T = E.targets(E.makeView(P), S, m, new Map([...cur.keys()].map(id => [P.ids.indexOf(id), 1]))); target = new Map([...T].map(([i, w]) => [P.ids[i], w])); }
    } else if (sched) target = new Map(rec.picks.map(([id, w]) => [id, w]));
    if (target && (sched || [...target.keys()].sort().join() !== [...cur.keys()].sort().join())) {
      let tv = [...cur.values()].reduce((a, b) => a + b, 0), cost = 0;
      const ids = new Set([...cur.keys(), ...target.keys()]);
      for (const id of ids) {
        const d = (target.get(id) || 0) * tv - (cur.get(id) || 0);
        cost += Math.abs(d) * (c.commission + c.spread) / 100 + (d > 0 && c.stamp && id.startsWith("LSE-") ? d * 0.005 : 0) + (((ccy === "GBP") !== id.startsWith("LSE-")) ? Math.abs(d) * c.fxFee / 100 : 0);
      }
      tv -= cost;
      const tw = [...target.values()].reduce((a, b) => a + b, 0) || 1;
      cur = new Map([...target].map(([id, w]) => [id, tv * w / tw]));
    }
    let tot = 0; const nx = new Map();
    for (const [id, v] of cur) { const a = px(id, k - 1), b = px(id, k); const nv = a && b ? v * b / a * fxf(id, monthEnd(k - 1), monthEnd(k)) : v; nx.set(id, nv); tot += nv; }
    cur = nx; value = tot; dates.push(monthEnd(k)); vals.push(value);
  }
  // benchmarks from the start date
  const lvl = (k, d) => { const b = BENCH[k]; if (!b) return null; const a = (b.daily || []).filter(x => x[0] <= d).pop() || (b.monthly || []).filter(x => x[0] <= d).pop(); return a ? a[1] : null; };
  const benchRet = (k, ex) => { const a = lvl(k, rec.start), z = lvl(k, M.asof); if (!a || !z) return null; let r = z / a; const x = fxAt(rec.start), y = fxAt(M.asof); if (x && y) { if (ccy === "GBP" && ex === "US") r *= x / y; if (ccy === "USD" && ex === "LSE") r *= y / x; } return r - 1; };
  return { ret: value - 1, dates, vals, holdings: cur, sp: benchRet("sp500", "US"), ftse: benchRet("ftse100", "LSE") };
}
async function drawTracked() {
  const list = store.get("bp-lab-tracked", []);
  const box = $("tracked");
  if (!list.length) { box.hidden = true; return; }
  await loadTrackingData();
  box.hidden = false;
  box.innerHTML = `<h3>Tracked from today <span class="sub">real prices since you started tracking; nothing here can be fitted to the past</span></h3>
    ${list.map(rec => { const t = trackValue(rec); return `<div class="tr"><span><b>${esc(rec.name)}</b><div class="sub">since ${new Date(rec.start + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}, ${rec.picks.length} stock${rec.picks.length === 1 ? "" : "s"} at the start</div></span>
      <span style="text-align:right">${t ? `<b class="${cls(t.ret)}">${pc(t.ret)}</b><div class="sub">S&amp;P 500 ${pc(t.sp)}, FTSE 100 ${pc(t.ftse)}</div>` : `<span class="sub">starts with tonight's prices</span>`}</span>
      <span class="actions"><button class="bbtn ghost" data-tl="${rec.id}">Load</button><button class="bbtn ghost" data-tc="${rec.id}">Copy link</button><button class="x" data-td="${rec.id}" aria-label="Stop tracking">×</button></span></div>`; }).join("")}
    <p class="note">Tracking keeps the stocks picked on the start date, rebalances on the strategy's schedule using month-end prices (rules are re-applied once each month-end joins the history), and charges dealing costs. No money is added and no tax is taken.</p>`;
  box.querySelectorAll("[data-tl]").forEach(b => b.onclick = () => { const r = list.find(x => x.id === b.dataset.tl); UI = fromStrategy(r.S); UI.name = r.name; changed(true); window.scrollTo({ top: 0, behavior: "smooth" }); });
  box.querySelectorAll("[data-td]").forEach(b => b.onclick = () => { store.set("bp-lab-tracked", list.filter(x => x.id !== b.dataset.td)); drawTracked(); });
  box.querySelectorAll("[data-tc]").forEach(b => b.onclick = async () => { const r = list.find(x => x.id === b.dataset.tc); const url = location.origin + location.pathname + "#t=" + enc(r); try { await navigator.clipboard.writeText(url); b.textContent = "Copied"; } catch (e) { $("msg").innerHTML = `Copy this link: <input class="inp" readonly value="${esc(url)}" onclick="this.select()" style="width:100%">`; } });
}

// ---------- start ----------
(async () => {
  const get = u => fetch(u, { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error(u); return r.json(); });
  try {
    [P, D] = await Promise.all([get("data/panel.json"), get("data/snapshot.json")]);
    E.augment(P);   // 12-month return, momentum, volatility and trend history from the panel's returns
    FX = (await get("data/fx_history.json").catch(() => ({ usdPerGbp: [] }))).usdPerGbp;
  } catch (e) { $("res").innerHTML = `<div class="card emptyp">The history file couldn't be loaded. Check your connection and refresh the page.</div>`; return; }
  D.stocks.forEach(s => BY[s.id] = s);
  $("stocklist").innerHTML = D.stocks.map(s => `<option value="${esc(s.name)} (${esc(s.t)})">`).join("");
  $("r-sec").innerHTML = `<option value="">Any</option>` + [...new Set(D.stocks.map(s => s.sector))].sort().map(s => `<option>${esc(s)}</option>`).join("");
  const years = [...new Set(P.months.map(m => m.slice(0, 4)))];
  $("from").innerHTML = `<option value="">The start (${P.months[0].slice(0, 7)})</option>` + years.slice(1, -2).map(y => `<option value="${y}-01">January ${y}</option>`).join("");
  // links: a shared strategy (#s=), a tracked strategy (#t=), or an investor's portfolio (#inv=)
  const h = location.hash;
  if (h.startsWith("#s=")) { const S = dec(h.slice(3)); if (S) UI = fromStrategy(S); }
  if (h.startsWith("#t=")) {
    const rec = dec(h.slice(3));
    if (rec && rec.S && rec.picks) {
      UI = fromStrategy(rec.S); UI.name = rec.name;
      const list = store.get("bp-lab-tracked", []);
      if (!list.some(x => x.id === rec.id)) { list.unshift(rec); store.set("bp-lab-tracked", list.slice(0, 20)); $("msg").textContent = `Added "${rec.name}" to your tracked strategies.`; }
    }
  }
  if (h.startsWith("#inv=")) {
    try {
      const slug = decodeURIComponent(h.slice(5)), inv = await get(`data/investors/${slug}.json`);
      const w = {}; (inv.holdings || []).filter(x => x.id && BY[x.id]).forEach(x => { w[x.id] = Math.round(x.w * 1000) / 10; });
      UI.mode = "list"; UI.ids = Object.keys(w); UI.cw = w; UI.weighting = "custom"; UI.name = `${inv.name}'s latest filing`;
      $("msg").textContent = `Loaded ${UI.ids.length} holdings from ${inv.name}'s latest filing (${inv.covered != null ? Math.round(inv.covered * 100) + "% of its US portfolio has prices here" : ""}). This tests today's portfolio on the past, which flatters it; the investor's page shows the honest record of following each filing as it was published.`;
    } catch (e) { $("msg").textContent = "That investor's portfolio couldn't be loaded."; }
  }
  if (h) try { history.replaceState(null, "", location.pathname); } catch (e) {}
  drawBuilder(); bindBuilder(); update(); drawTracked();
})();
})();
