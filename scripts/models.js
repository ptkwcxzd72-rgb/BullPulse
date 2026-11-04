// BullPulse model portfolios: nightly analysis for site/models.html.
//
// For every strategy in site/models-core.js, in three markets (UK and US, UK only, US only) and
// two rebalancing speeds (monthly, yearly), this runs the Strategy Lab engine over ten years of
// month-end data using only what was known at each date, with dealing costs, stamp duty and
// currency. It reports the whole period, the years before the last two and the last two years
// separately, a range of outcomes, the market's worst falls, and how each strategy did in past
// months that looked like today (trend, volatility, breadth and dispersion of returns).
//
// It then picks tonight's portfolio for each strategy with the same code, and once a month stores
// that month's portfolios (data/history/models/YYYY-MM.json) so a forward record builds up that
// is never edited.
//
//   node scripts/models.js
// Writes site/data/models.json.
"use strict";
const fs = require("fs");
const path = require("path");
const E = require("../site/lab-engine.js");
const M = require("../site/models-core.js");

const SITE = "site/data";
const HIST = "data/history/models";
const HIDDEN = 24;           // months reported separately at the end of each backtest
const K = 24;                // similar past months to compare with today
const r4 = x => x == null || !isFinite(x) ? null : Math.round(x * 1e4) / 1e4;
const read = (f, d) => { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { return d; } };

function csvSeries(file) {
  try {
    const rows = fs.readFileSync(file, "utf8").trim().split("\n").slice(1).map(l => l.split(","));
    return rows.map(r => [r[0].slice(0, 10), +r[4]]).filter(r => r[1] > 0);
  } catch (e) { return []; }
}
const priceOn = (ser, day) => { let k = -1; for (let i = 0; i < ser.length && ser[i][0] <= day; i++) k = i; return k < 0 ? null : ser[k][1]; };

// index returns that match each market: FTSE 100, S&P 500, or half of each
function indexRets(r, mk) {
  const uk = E.benchRets(r.bench.ftse100, r.invested), us = E.benchRets(r.bench.sp500, r.invested);
  return uk.map((x, k) => mk === "LSE" ? x : mk === "US" ? us[k] : (x == null || us[k] == null ? null : (x + us[k]) / 2));
}
const indexName = mk => mk === "LSE" ? "FTSE 100" : mk === "US" ? "S&P 500" : "half FTSE 100, half S&P 500";

function excessStats(a, b) {
  const d = a.map((x, k) => x == null || b[k] == null ? null : x - b[k]).filter(x => x != null);
  if (d.length < 6) return null;
  const mean = d.reduce((s, x) => s + x, 0) / d.length;
  const sd = Math.sqrt(d.reduce((s, x) => s + (x - mean) ** 2, 0) / (d.length - 1));
  return { months: d.length, mean: r4(mean), perYear: r4(mean * 12), t: sd > 0 ? Math.round(mean / (sd / Math.sqrt(d.length)) * 100) / 100 : null, beat: r4(d.filter(x => x > 0).length / d.length) };
}
function slim(st) {
  if (!st) return null;
  return { months: st.months, total: r4(st.total), cagr: r4(st.cagr), vol: r4(st.vol), sharpe: st.sharpe == null ? null : Math.round(st.sharpe * 100) / 100,
    maxDD: r4(st.maxDD), longestUnderwater: st.longestUnderwater, worstYear: r4(st.worstYear), bestYear: r4(st.bestYear),
    years: Object.fromEntries(Object.entries(st.years || {}).map(([y, v]) => [y, r4(v - 1)])) };
}

// the market's character at each month-end, from returns before that date only
function regimes(P, nowDate) {
  const V = E.makeView(P), nM = P.months.length;
  const idx = m => { const a = P.bench.ftse100[m], b = P.bench.sp500[m]; return a == null || b == null ? null : (a + b) / 2 / 1e4; };
  const out = [];
  for (let m = 12; m <= nM; m++) {
    const past = []; for (let k = m - 12; k < m; k++) past.push(idx(k));
    if (past.some(x => x == null)) continue;
    const trend = past.reduce((g, x) => g * (1 + x), 1) - 1;
    const six = past.slice(6), mu = six.reduce((a, b) => a + b, 0) / 6;
    const vol = Math.sqrt(six.reduce((a, b) => a + (b - mu) ** 2, 0) / 5 * 12);
    let up = 0, n = 0; const r12 = [];
    for (let i = 0; i < V.n; i++) {
      let g6 = 1, g12 = 1, ok = true;
      for (let k = m - 12; k < m; k++) { const x = V.fwd(k, i); if (x == null || Math.abs(x) > 2) { ok = false; break; } g12 *= 1 + x; if (k >= m - 6) g6 *= 1 + x; }
      if (!ok) continue;
      n++; if (g6 > 1) up++; r12.push(g12 - 1);
    }
    if (n < 50) continue;
    const mr = r12.reduce((a, b) => a + b, 0) / r12.length;
    const disp = Math.sqrt(r12.reduce((a, b) => a + (b - mr) ** 2, 0) / (r12.length - 1));
    out.push({ m, date: m < nM ? P.months[m] : nowDate, trend, vol, breadth: up / n, disp });
  }
  return out;
}
const FEATS = [
  ["trend", "Market trend", "the past 12 months' index return", v => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}%`, ["falling", "flat to modest", "strong"]],
  ["vol", "Market volatility", "how much the index swung over the past 6 months, a year", v => `${(v * 100).toFixed(0)}%`, ["calm", "normal", "turbulent"]],
  ["breadth", "Breadth", "share of stocks up over the past 6 months", v => `${Math.round(v * 100)}%`, ["narrow", "mixed", "broad"]],
  ["disp", "Dispersion", "how far apart stocks' 12-month returns are", v => `${(v * 100).toFixed(0)}%`, ["stocks moving together", "normal", "stocks moving apart"]],
];

function main() {
  const P = E.augment(read(path.join(SITE, "panel.json")));
  const D = read(path.join(SITE, "snapshot.json"));
  if (!P || !D || !D.stocks) { console.log("models: panel or snapshot missing"); return; }
  const FX = (read(path.join(SITE, "fx_history.json"), { usdPerGbp: [] }).usdPerGbp) || [];
  const learning = read(path.join(SITE, "learning.json"), {});
  const live = read(path.join(SITE, "live.json"), {});
  const news = read(path.join(SITE, "news", "index.json"), null);
  const nM = P.months.length;
  const lastEnd = (() => { const d = new Date(P.months[nM - 1] + "T00:00:00Z"); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + 2); d.setUTCDate(0); return d.toISOString().slice(0, 10); })();

  // ---- backtests
  const runs = {};
  for (const def of M.STRATEGIES) {
    runs[def.id] = {};
    for (const mk of ["ALL", "LSE", "US"]) {
      runs[def.id][mk] = {};
      for (const reb of ["Q", "Y", "M"]) {
        // "M": monthly trading as the Lab does by default (swapping names every month), kept only
        // for the "How often to trade" comparison
        const S = reb === "M" ? M.strategy(def, mk, "M", { swaps: true, source: Object.assign(M.strategy(def, mk).source, { keep: def.top * 2 }) }) : M.strategy(def, mk, reb);
        const r0 = E.run(P, FX, S, { lastDate: lastEnd });
        // start the record when the strategy first owns shares (some measures, such as revenue
        // growth, only have history from a later date); the index is compared over the same months
        const first = Math.max(0, r0.held.findIndex(h => h > 0));
        const cutr = a => a.slice(first);
        const r = Object.assign({}, r0, { rets: cutr(r0.rets), dates: cutr(r0.dates), months: cutr(r0.months), held: cutr(r0.held), invested: cutr(r0.invested),
          bench: { ftse100: cutr(r0.bench.ftse100), sp500: cutr(r0.bench.sp500), avg: cutr(r0.bench.avg) } });
        const ix = indexRets(r, mk), avg = E.benchRets(r.bench.avg, r.invested);
        const n = r.rets.length, cut = Math.max(0, n - HIDDEN);
        runs[def.id][mk][reb] = { S, r, ix, avg, res: {
          index: indexName(mk),
          all: slim(E.stats(r.rets, r.dates)), indexAll: slim(E.stats(ix, r.dates)), avgAll: slim(E.stats(avg, r.dates)),
          dev: slim(E.stats(r.rets.slice(0, cut), r.dates.slice(0, cut))), indexDev: slim(E.stats(ix.slice(0, cut), r.dates.slice(0, cut))),
          hidden: slim(E.stats(r.rets.slice(cut), r.dates.slice(cut))), indexHidden: slim(E.stats(ix.slice(cut), r.dates.slice(cut))),
          excess: excessStats(r.rets, ix), excessHidden: excessStats(r.rets.slice(cut), ix.slice(cut)),
          range: E.bootstrap(r.rets, 1000, 7), turnoverYr: r4(r.turnoverYr), costs: Math.round(r.costs), trades: r.trades,
          hiddenFrom: r.dates[cut] || null, holdings: Math.round(r.held.reduce((a, b) => a + b, 0) / Math.max(1, r.held.length)),
          dates: r.dates, rets: r.rets.map(r4), indexRets: ix.map(r4),
        } };
      }
    }
  }

  // ---- the market's worst falls (half FTSE 100, half S&P 500) and each strategy in them
  const base = runs[M.STRATEGIES[0].id].ALL.Q;
  const ixAll = base.ix, dates = base.r.dates;
  const falls = [];
  const used = new Set();
  const cands = [];
  for (let k = 0; k + 3 <= ixAll.length; k++) { let g = 1; for (let j = k; j < k + 3; j++) g *= 1 + (ixAll[j] || 0); cands.push([g - 1, k]); }
  cands.sort((a, b) => a[0] - b[0]);
  for (const [g, k] of cands) {
    if (falls.length >= 4 || g > -0.04) break;
    if ([k, k + 1, k + 2].some(j => used.has(j))) continue;
    [k - 2, k - 1, k, k + 1, k + 2, k + 3, k + 4].forEach(j => used.add(j));
    falls.push({ from: dates[k], to: dates[k + 2], k, index: r4(g) });
  }
  falls.sort((a, b) => a.from.localeCompare(b.from));
  const stressOf = rets => falls.map(f => { let g = 1; for (let j = f.k; j < f.k + 3; j++) g *= 1 + (rets[j] || 0); return r4(g - 1); });

  // ---- today's market against the past, and each strategy in similar months
  const reg = regimes(P, lastEnd);
  const now = reg[reg.length - 1];
  const hist = reg.filter(x => x.m <= nM - 6);
  const z = {};
  for (const [f] of FEATS) { const xs = hist.map(x => x[f]); const mu = xs.reduce((a, b) => a + b, 0) / xs.length; const sd = Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / (xs.length - 1)) || 1; z[f] = v => (v - mu) / sd; }
  const dist = x => Math.sqrt(FEATS.reduce((s, [f]) => s + (z[f](x[f]) - z[f](now[f])) ** 2, 0));
  const similar = hist.filter(x => x.m < now.m - 6).sort((a, b) => dist(a) - dist(b)).slice(0, K).sort((a, b) => a.m - b.m);
  const market = FEATS.map(([f, label, about, fmt, words]) => {
    const xs = hist.map(x => x[f]).sort((a, b) => a - b);
    const pctile = xs.filter(v => v < now[f]).length / xs.length;
    return { key: f, label, about, value: r4(now[f]), text: fmt(now[f]), pct: Math.round(pctile * 100), word: pctile < 1 / 3 ? words[0] : pctile < 2 / 3 ? words[1] : words[2],
      series: reg.map(x => [x.date, r4(x[f])]) };
  });
  const six = (rets, ix, start) => { let a = 1, b = 1; for (let j = start; j < start + 6 && j < rets.length; j++) { a *= 1 + (rets[j] || 0); b *= 1 + (ix[j] || 0); } return a - b; };
  function fit(run) {
    const pos = new Map(run.r.months.map((d, k) => [d, k]));
    const all = [], sim = [];
    for (const x of hist) { const k = pos.get(x.date); if (k == null || k + 6 > run.r.rets.length) continue; const e = six(run.r.rets, run.ix, k); all.push(e); }
    for (const x of similar) { const k = pos.get(x.date); if (k == null || k + 6 > run.r.rets.length) continue; sim.push(six(run.r.rets, run.ix, k)); }
    if (sim.length < 8 || all.length < 24) return null;
    const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
    const ms = mean(sim), ma = mean(all), sd = Math.sqrt(all.reduce((s, x) => s + (x - ma) ** 2, 0) / (all.length - 1));
    // similar months overlap (6-month windows), so count them as roughly a third as many independent tries
    const t = sd > 0 ? (ms - ma) / (sd / Math.sqrt(Math.max(2, sim.length / 3))) : 0;
    return { n: sim.length, avg6: r4(ms), usual6: r4(ma), beat: r4(sim.filter(x => x > 0).length / sim.length), t: Math.round(t * 100) / 100,
      verdict: t >= 1 && ms > 0 ? "better" : t <= -1 ? "worse" : "unclear" };
  }

  // ---- tonight's portfolios, picked by the same code, with reasons and news
  const S0 = E.snapshotPanel(D), V0 = E.makeView(S0);
  const byId = Object.fromEntries(D.stocks.map(s => [s.id, s]));
  fs.mkdirSync(HIST, { recursive: true });
  const pubs = fs.readdirSync(HIST).filter(f => /^\d{4}-\d{2}\.json$/.test(f)).sort();
  const lastPub = pubs.length ? read(path.join(HIST, pubs[pubs.length - 1]), null) : null;
  const month = D.asof.slice(0, 7);
  const prevPub = lastPub && lastPub.month < month ? lastPub : (pubs.length > 1 ? read(path.join(HIST, pubs[pubs.length - 2]), null) : null);
  const strategies = [];
  const nowPicks = {};
  for (const def of M.STRATEGIES) {
    const entry = { id: def.id, name: def.name, short: def.short, idea: def.idea, why: def.why, rules: def.rules, w: def.w, top: def.top, keep: def.keep, weighting: def.weighting || "equal", markets: {} };
    for (const mk of ["ALL", "LSE", "US"]) {
      const prev = prevPub && prevPub.portfolios && prevPub.portfolios[def.id] && prevPub.portfolios[def.id][mk];
      const held = new Set((prev ? prev.ids : []).map(id => V0.idx.get(id)).filter(i => i != null));
      const S = M.strategy(def, mk, "Q");
      const tw = E.targets(V0, S, 0, held);
      const picks = [...tw.entries()].sort((a, b) => b[1] - a[1]).map(([i, w]) => {
        const s = byId[S0.ids[i]];
        return { id: s.id, name: s.name, t: s.t, ex: s.ex, sector: s.sector, w: r4(w), price: s.price, ccy: s.ccy, score: s.score, rank: s.rank, prob6: s.prob6 ?? null,
          ret1y: r4(s.ret1y), tone30: s.tone30 == null ? null : Math.round(s.tone30 * 100) / 100, newsN30: s.newsN30 || 0,
          status: prev ? (prev.ids.includes(s.id) ? "kept" : "new") : "", reasons: M.reasons(s, def), flags: M.flags(s) };
      });
      const ids = picks.map(p => p.id);
      const out = prev ? prev.ids.filter(id => !ids.includes(id)).map(id => ({ id, name: (byId[id] || {}).name || id, t: (byId[id] || {}).t || "", score: (byId[id] || {}).score ?? null })) : [];
      nowPicks[def.id] = nowPicks[def.id] || {};
      nowPicks[def.id][mk] = { ids, w: picks.map(p => p.w), px: picks.map(p => p.price), ex: picks.map(p => p.ex) };
      const rm = runs[def.id][mk];
      const sec = {};
      picks.forEach(p => sec[p.sector] = (sec[p.sector] || 0) + p.w);
      entry.markets[mk] = {
        quarterly: rm.Q.res, yearly: Object.assign({}, rm.Y.res, { dates: undefined, indexRets: undefined }),
        trading: ["M", "Q", "Y"].map(k => ({ every: { M: "Month", Q: "Quarter", Y: "Year" }[k], cagr: rm[k].res.all && rm[k].res.all.cagr, turnoverYr: rm[k].res.turnoverYr, costs: rm[k].res.costs })),
        fit: fit(rm.Q), stress: stressOf(rm.Q.r.rets), stressIndex: stressOf(rm.Q.ix),
        picks, out, sectors: Object.entries(sec).sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, r4(v)]),
        avgProb6: picks.length && picks.every(p => p.prob6 != null) ? r4(picks.reduce((s, p) => s + p.prob6 * p.w, 0) / picks.reduce((s, p) => s + p.w, 0)) : null,
        lab: S,
      };
    }
    strategies.push(entry);
  }

  // ---- picks for this month and this year: what most strategies agree on, with the strategies
  // that have the better record for that horizon counting more
  function consensus(reb) {
    const score = {}, who = {};
    for (const st of strategies) {
      const m = st.markets.ALL, res = reb === "Q" ? m.quarterly : m.yearly;
      const tval = res.excess && res.excess.t != null ? res.excess.t : 0;
      const weight = 1 + Math.max(0, Math.min(3, tval)) / 2 + (reb === "Q" && m.fit && m.fit.verdict === "better" ? 0.5 : 0) - (reb === "Q" && m.fit && m.fit.verdict === "worse" ? 0.5 : 0);
      for (const p of m.picks) { score[p.id] = (score[p.id] || 0) + weight; (who[p.id] = who[p.id] || []).push(st.id); }
    }
    return Object.keys(score).sort((a, b) => score[b] - score[a] || (byId[b].prob6 ?? 0) - (byId[a].prob6 ?? 0)).slice(0, 12).map(id => {
      const s = byId[id];
      return { id, name: s.name, t: s.t, ex: s.ex, sector: s.sector, price: s.price, ccy: s.ccy, score: s.score, prob6: s.prob6 ?? null, ret1y: r4(s.ret1y),
        tone30: s.tone30 == null ? null : Math.round(s.tone30 * 100) / 100, newsN30: s.newsN30 || 0,
        strategies: who[id], weight: Math.round(score[id] * 100) / 100, reasons: M.reasons(s, { w: { T: 1, M: 1, G: 1, F: 1, V: 1 } }).slice(0, 3), flags: M.flags(s) };
    });
  }
  const picks = { month: consensus("Q"), year: consensus("Y") };

  // ---- publish this month's portfolios once, and the record of every month so far
  const pubFile = path.join(HIST, month + ".json");
  if (!fs.existsSync(pubFile)) {
    const fxNow = D.fx && (D.fx.usdPerGbp || D.fx.GBPUSD || D.fx.usd) || null;
    fs.writeFileSync(pubFile, JSON.stringify({ month, asof: D.asof, usdPerGbp: fxNow, portfolios: nowPicks,
      picks: { month: picks.month.map(p => [p.id, p.price, p.ex]), year: picks.year.map(p => [p.id, p.price, p.ex]) } }) + "\n");
  }
  const sp = csvSeries("data/prices/bench-sp500.csv"), uk = csvSeries("data/prices/bench-ftse100.csv");
  const fxNow = E.fxAt(FX, D.asof) || null;
  function since(ids, w, px, ex, pub) {
    let v = 0, tot = 0;
    const fx0 = E.fxAt(FX, pub.asof) || pub.usdPerGbp, fx1 = fxNow || fx0;
    ids.forEach((id, k) => {
      const s = byId[id]; if (!s || !px[k]) return;
      const r = s.price / px[k] * (ex[k] === "US" && fx0 && fx1 ? fx0 / fx1 : 1);
      v += (w ? w[k] : 1) * r; tot += w ? w[k] : 1;
    });
    return tot ? r4(v / tot - 1) : null;
  }
  const idxSince = (mk, pub) => {
    const a = priceOn(uk, pub.asof), b = priceOn(uk, D.asof), c = priceOn(sp, pub.asof), d = priceOn(sp, D.asof);
    const fx0 = E.fxAt(FX, pub.asof), fx1 = fxNow;
    const ukr = a && b ? b / a - 1 : null, usr = c && d ? d / c * (fx0 && fx1 ? fx0 / fx1 : 1) - 1 : null;
    return r4(mk === "LSE" ? ukr : mk === "US" ? usr : ukr == null || usr == null ? null : (ukr + usr) / 2);
  };
  const record = [];
  for (const f of fs.readdirSync(HIST).filter(f => /^\d{4}-\d{2}\.json$/.test(f)).sort()) {
    const pub = read(path.join(HIST, f), null); if (!pub) continue;
    const row = { month: pub.month, asof: pub.asof, strategies: {}, index: idxSince("ALL", pub) };
    for (const [sid, mks] of Object.entries(pub.portfolios || {})) {
      const a = mks.ALL; if (!a) continue;
      row.strategies[sid] = since(a.ids, a.w, a.px, a.ex, pub);
    }
    if (pub.picks) row.picks = { month: since(pub.picks.month.map(x => x[0]), null, pub.picks.month.map(x => x[1]), pub.picks.month.map(x => x[2]), pub), year: since(pub.picks.year.map(x => x[0]), null, pub.picks.year.map(x => x[1]), pub.picks.year.map(x => x[2]), pub) };
    record.push(row);
  }

  const out = {
    generated: new Date().toISOString().replace(/\.\d+Z$/, "Z"), asof: D.asof, panelTo: P.months[nM - 1], from: P.months[0], hiddenMonths: HIDDEN,
    marketAsOf: now.date, market, similar: similar.map(x => x.date), falls: falls.map(f => ({ from: f.from, to: f.to, index: f.index })),
    news: news && news.days && news.days.length ? { date: news.days[0].date, n: news.days[0].n, pos: news.days[0].pos, neg: news.days[0].neg,
      avg: r4(news.days.slice(0, 15).reduce((s, d) => s + (d.pos - d.neg) / Math.max(1, d.n), 0) / Math.min(15, news.days.length)) } : null,
    model: { calibration: learning.calibration || null, championIC: learning.championIC || null, decision: learning.decision || "", horizonMonths: learning.horizonMonths || 6,
      evidenceMonths: learning.evidenceMonths || null, live: live && live.horizons ? live.horizons : null, liveSince: live && live.since || null },
    strategies, picks, record,
  };
  fs.writeFileSync(path.join(SITE, "models.json"), JSON.stringify(out));
  console.log(`::notice::Model portfolios: ${strategies.length} strategies; picks this month ${picks.month.length}; record ${record.length} month(s)`);
}

if (require.main === module) main();
module.exports = { regimes, excessStats, indexRets };
