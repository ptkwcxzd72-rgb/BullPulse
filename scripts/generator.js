// BullPulse portfolio generator: nightly checks and ready-made portfolios for site/generator.html.
//
// For each aim (growth, income, steadier, balanced) in each market, the generator's own stock
// picker runs at every month-end since December 2017 inside the Strategy Lab engine, with dealing
// costs, stamp duty and currency, trading only on the scheduled date. The result is compared with an
// index fund over the whole period, before the last two years and during them, and each aim gets a
// plain verdict. Tonight's default portfolio for each aim is also picked, so the page opens at once.
//
//   node scripts/generator.js        writes site/data/generator.json
"use strict";
const fs = require("fs");
const path = require("path");
const E = require("../site/lab-engine.js");
const G = require("../site/generator-core.js");
const MC = require("../site/models-core.js");

const SITE = "site/data";
const HIDDEN = 24;
const r4 = x => x == null || !isFinite(x) ? null : Math.round(x * 1e4) / 1e4;
const read = f => { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch (e) { return null; } };

const slim = st => st && { cagr: r4(st.cagr), vol: r4(st.vol), maxDD: r4(st.maxDD), sharpe: st.sharpe == null ? null : Math.round(st.sharpe * 100) / 100, worstYear: r4(st.worstYear), months: st.months };
function excess(a, b) {
  const d = a.map((x, k) => x == null || b[k] == null ? null : x - b[k]).filter(x => x != null);
  if (d.length < 6) return null;
  const mean = d.reduce((s, x) => s + x, 0) / d.length, sd = Math.sqrt(d.reduce((s, x) => s + (x - mean) ** 2, 0) / (d.length - 1));
  return { perYear: r4(mean * 12), t: sd > 0 ? Math.round(mean / (sd / Math.sqrt(d.length)) * 100) / 100 : null, beat: r4(d.filter(x => x > 0).length / d.length), te: r4(sd * Math.sqrt(12)) };
}
// backtest one set of settings (the shared code in generator-core.js), rounded for the file
function backtest(P, FX, opt, lastDate, series) {
  const b = G.backtest(E, P, FX, opt, lastDate, HIDDEN);
  const out = { verdict: b.verdict, summary: b.summary, calmer: b.calmer, hiddenFrom: b.hiddenFrom, range: b.range, turnoverYr: r4(b.turnoverYr), worstVsIndex: r4(b.worstVsIndex), excess: excess(b.rets, b.indexRets) };
  for (const k of ["all", "index", "stocks", "dev", "indexDev", "hidden", "indexHidden"]) out[k] = slim(b[k]);
  if (series !== false) Object.assign(out, { dates: b.dates, rets: b.rets.map(r4), indexRets: b.indexRets.map(r4) });
  else out.from = b.dates[0];
  return out;
}

// tonight's portfolio for a set of settings, with reasons, warnings and the risk report
const live = (P, D, opt, extra, FX) => G.livePortfolio(E, P, D, opt, extra, FX, MC.flags);

// The alternatives tested in the November 2026 review, rerun every night on current data so the
// page's evidence stays true: each on its own against the standard settings, stocks only (no index
// core), in every aim and market, before the last two years and during them. Plus the standard
// settings against random portfolios of the same size from the same stocks.
const REVIEW = [
  ["std", "The standard settings", {}],
  ["orig", "The original settings: 20 stocks, each quarter", { n: 20, reb: "Q" }],
  ["index", "Index-aware: the 50 largest eligible companies, tilted towards the score", { build: "index", n: 50 }],
  ["sector", "Rank within each sector (sector-neutral)", { rankMode: "sector", build: "" }],
  ["erc", "Equal risk from each stock (risk parity)", { weighting: "erc", build: "" }],
  ["opt", "Mean-variance: expected returns from the aim's past skill (Grinold), shrunk covariance", { weighting: "opt", build: "" }],
  ["trend", "Half in cash when the index is below its 10-month average", { trend: true }],
  ["n50", "50 stocks, chosen by score", { n: 50, build: "" }],
];
function irOf(r, ix) {
  const d = r.map((x, k) => x == null || ix[k] == null ? null : x - ix[k]).filter(x => x != null);
  if (d.length < 12) return null;
  const m = d.reduce((a, b) => a + b, 0) / d.length, sd = Math.sqrt(d.reduce((a, x) => a + (x - m) ** 2, 0) / (d.length - 1));
  return { ir: sd > 0 ? Math.round(m * 12 / (sd * Math.sqrt(12)) * 100) / 100 : null, te: r4(sd * Math.sqrt(12)) };
}
function review(P, FX, asof) {
  const cells = {}, sum = {};
  for (const [id] of REVIEW) sum[id] = { devEx: 0, hidEx: 0, devIR: 0, hidIR: 0, dd: 0, to: 0, n: 0, devWins: 0, hidWins: 0 };
  for (const aim of Object.keys(G.AIMS)) for (const mk of ["ALL", "LSE", "US"]) {
    const c = cells[aim + "/" + mk] = {};
    for (const [id, , v] of REVIEW) {
      const b = G.backtest(E, P, FX, Object.assign({}, G.DEFAULTS, { aim, market: mk, core: 0 }, v), asof, HIDDEN);
      const cut = Math.max(0, b.rets.length - HIDDEN);
      const dv = irOf(b.rets.slice(0, cut), b.indexRets.slice(0, cut)), hd = irOf(b.rets.slice(cut), b.indexRets.slice(cut));
      c[id] = { devEx: r4(b.dev.cagr - b.indexDev.cagr), hidEx: r4(b.hidden.cagr - b.indexHidden.cagr), devIR: dv && dv.ir, hidIR: hd && hd.ir, te: dv && dv.te, dd: r4(b.all.maxDD), ixDD: r4(b.index.maxDD), to: r4(b.turnoverYr) };
    }
    for (const [id] of REVIEW) {
      const x = c[id], S = sum[id];
      S.devEx += x.devEx; S.hidEx += x.hidEx; S.devIR += x.devIR || 0; S.hidIR += x.hidIR || 0; S.dd += x.dd; S.to += x.to; S.n++;
      if (id !== "std") { if ((x.devIR ?? -9) > (c.std.devIR ?? -9)) S.devWins++; if ((x.hidIR ?? -9) > (c.std.hidIR ?? -9)) S.hidWins++; }
    }
    // the standard settings against random portfolios of the same size from the same stocks
    const std = G.backtest(E, P, FX, Object.assign({}, G.DEFAULTS, { aim, market: mk, core: 0 }), asof, HIDDEN);
    const exOf = b => b.all.cagr - b.index.cagr, mine = exOf(std), rnd = [];
    for (let j = 0; j < 30; j++) {
      const o = Object.assign({}, G.DEFAULTS, { aim, market: mk, core: 0 });
      const r0 = E.run(P, FX, G.randomStrategy(o, 7919 * (j + 1)), { lastDate: asof });
      const f = Math.max(0, r0.held.findIndex(h => h > 0)), cs = a => a.slice(f);
      const inv = cs(r0.invested), rets = cs(r0.rets), dates = cs(r0.dates);
      const uk = cs(E.benchRets(r0.bench.ftse100, r0.invested)), us = cs(E.benchRets(r0.bench.sp500, r0.invested));
      const ix = uk.map((x, k) => mk === "LSE" ? x : mk === "US" ? us[k] : (x == null || us[k] == null ? null : (x + us[k]) / 2));
      rnd.push(E.stats(rets, dates).cagr - E.stats(ix, dates).cagr);
    }
    rnd.sort((a, b) => a - b);
    c.random = { beats: r4(rnd.filter(x => x < mine).length / rnd.length), median: r4(rnd[rnd.length >> 1]), p10: r4(rnd[Math.floor(rnd.length * 0.1)]), p90: r4(rnd[Math.floor(rnd.length * 0.9)]), mine: r4(mine), n: rnd.length };
  }
  const summary = Object.fromEntries(Object.entries(sum).map(([id, S]) => [id, { devEx: r4(S.devEx / S.n), hidEx: r4(S.hidEx / S.n), devIR: Math.round(S.devIR / S.n * 100) / 100, hidIR: Math.round(S.hidIR / S.n * 100) / 100, dd: r4(S.dd / S.n), to: r4(S.to / S.n), devWins: S.devWins, hidWins: S.hidWins, cells: S.n }]));
  return { variants: REVIEW.map(([id, label]) => ({ id, label })), cells, summary };
}

function main() {
  const P = read(path.join(SITE, "panel.json")), D = read(path.join(SITE, "snapshot.json"));
  if (!P || !D) { console.log("generator: panel or snapshot missing"); return; }
  E.augment(P);
  const FX = (read(path.join(SITE, "fx_history.json")) || {}).usdPerGbp || [];
  const extra = Object.fromEntries(D.stocks.map(s => [s.id, { prob6: s.prob6, tone30: s.tone30 }]));
  const out = { generated: new Date().toISOString().replace(/\.\d+Z$/, "Z"), asof: D.asof, panelTo: P.months[P.months.length - 1], hiddenMonths: HIDDEN,
    aims: {}, sectors: [...new Set(D.stocks.map(s => s.sector).filter(Boolean))].sort() };
  for (const [id, aim] of Object.entries(G.AIMS)) {
    out.aims[id] = { name: aim.name, short: aim.short, about: aim.about, recipe: aim.recipe, filters: aim.filters, weighting: aim.weighting, markets: {} };
    for (const mk of ["ALL", "LSE", "US"]) {
      const opt = Object.assign({}, G.DEFAULTS, { aim: id, market: mk });
      out.aims[id].markets[mk] = {
        evidence: backtest(P, FX, opt, D.asof),
        // the same stocks without the index core, and rebalanced each quarter, for comparison
        stocksOnly: backtest(P, FX, Object.assign({}, opt, { core: 0 }), D.asof, false),
        quarterly: backtest(P, FX, Object.assign({}, opt, { reb: "Q" }), D.asof, false),
        live: live(P, D, opt, extra, FX),
      };
    }
  }
  // how well each ingredient has predicted the next month's returns, in each market: the whole
  // history and the last two years
  const V = E.makeView(P), nM = P.months.length;
  out.signals = {};
  for (const mk of ["US", "LSE"]) {
    out.signals[mk] = {};
    for (const k of Object.keys(G.SIGNALS)) {
      const all = G.signalRecord(V, k, mk, 12, nM - 1), last = G.signalRecord(V, k, mk, Math.max(12, nM - 1 - HIDDEN), nM - 1);
      const rd = x => x && { ic: r4(x.ic), t: Math.round(x.t * 10) / 10, hit: r4(x.hit), months: x.months };
      out.signals[mk][k] = { all: rd(all), last: rd(last) };
    }
  }
  out.review = review(P, FX, D.asof);
  fs.writeFileSync(path.join(SITE, "generator.json"), JSON.stringify(out));
  console.log("::notice::Generator: " + Object.entries(out.aims).map(([k, a]) => `${k} ${a.markets.ALL.evidence.verdict}`).join(", "));
}

if (require.main === module) main();
module.exports = { backtest, live };
