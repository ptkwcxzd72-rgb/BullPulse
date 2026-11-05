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

function excess(a, b) {
  const d = a.map((x, k) => x == null || b[k] == null ? null : x - b[k]).filter(x => x != null);
  if (d.length < 6) return null;
  const mean = d.reduce((s, x) => s + x, 0) / d.length, sd = Math.sqrt(d.reduce((s, x) => s + (x - mean) ** 2, 0) / (d.length - 1));
  return { perYear: r4(mean * 12), t: sd > 0 ? Math.round(mean / (sd / Math.sqrt(d.length)) * 100) / 100 : null, beat: r4(d.filter(x => x > 0).length / d.length) };
}
const slim = st => st && { cagr: r4(st.cagr), vol: r4(st.vol), maxDD: r4(st.maxDD), sharpe: st.sharpe == null ? null : Math.round(st.sharpe * 100) / 100, worstYear: r4(st.worstYear), months: st.months };

// backtest one set of generator settings; shared with the page's tests through module.exports
function backtest(P, FX, opt, lastDate) {
  const r0 = E.run(P, FX, G.strategy(opt), { lastDate });
  const f = Math.max(0, r0.held.findIndex(h => h > 0)), c = a => a.slice(f);
  const inv = c(r0.invested), rets = c(r0.rets), dates = c(r0.dates);
  const uk = E.benchRets(c(r0.bench.ftse100), inv), us = E.benchRets(c(r0.bench.sp500), inv);
  const ix = uk.map((x, k) => opt.market === "LSE" ? x : opt.market === "US" ? us[k] : (x == null || us[k] == null ? null : (x + us[k]) / 2));
  const cut = Math.max(0, rets.length - HIDDEN);
  const res = {
    all: slim(E.stats(rets, dates)), index: slim(E.stats(ix, dates)),
    dev: slim(E.stats(rets.slice(0, cut), dates.slice(0, cut))), indexDev: slim(E.stats(ix.slice(0, cut), dates.slice(0, cut))),
    hidden: slim(E.stats(rets.slice(cut), dates.slice(cut))), indexHidden: slim(E.stats(ix.slice(cut), dates.slice(cut))),
    excess: excess(rets, ix), range: E.bootstrap(rets, 1000, 11), turnoverYr: r4(r0.turnoverYr), hiddenFrom: dates[cut] || null,
    dates, rets: rets.map(r4), indexRets: ix.map(r4),
  };
  const a = res.all, i = res.index, d = res.dev, di = res.indexDev, h = res.hidden, hi = res.indexHidden;
  const beatDev = d && di && d.cagr > di.cagr, beatHid = h && hi && h.cagr > hi.cagr;
  const calmer = a && i && a.maxDD > i.maxDD + 0.02 && a.vol < i.vol;
  res.verdict = beatDev && beatHid ? "beat" : beatDev || beatHid ? "mixed" : "lagged";
  res.calmer = !!calmer;
  res.summary = res.verdict === "beat" ? `Beat an index fund both before and during the last two years (${pct(a.cagr)} a year against ${pct(i.cagr)}), though not by enough to rule out luck${res.excess && res.excess.t >= 2 ? " — in fact by enough to be fairly sure" : ""}.`
    : res.verdict === "mixed" ? `Beat an index fund in ${beatDev ? "the earlier years but not the last two" : "the last two years but not the earlier ones"}; over the whole period ${pct(a.cagr)} a year against ${pct(i.cagr)}.`
    : `Has not beaten an index fund: ${pct(a.cagr)} a year against ${pct(i.cagr)}${calmer ? ", though with smaller falls" : ""}. An index fund would have done better.`;
  return res;
}
const pct = v => v == null ? "–" : (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(1) + "%";

// tonight's portfolio for a set of settings, with reasons and warnings
function live(P, D, opt, extra) {
  const S0 = E.snapshotPanel(D), V0 = E.makeView(S0), H = E.makeView(P);
  const by = Object.fromEntries(D.stocks.map(s => [s.id, s]));
  const names = Object.fromEntries(D.stocks.map(s => [s.id, s.name]));
  const res = G.choose(V0, 0, opt, { hist: H, hm: P.months.length, names, extra });
  const pick = p => { const s = by[S0.ids[p.i]]; return { id: s.id, name: s.name, t: s.t, ex: s.ex, sector: s.sector, ccy: s.ccy, price: s.price, w: r4(p.w), score: s.score, prob6: s.prob6 ?? null,
    divY: r4(s.div ? s.div.yld : s.divY), vol1y: r4(s.vol1y), ret1y: r4(s.ret1y), reasons: G.why(s, opt.aim), flags: MC.flags(s) }; };
  return { picks: res.picks.map(pick), left: res.left.map(l => ({ id: S0.ids[l.i], name: names[S0.ids[l.i]], reason: l.reason })), eligible: res.eligible };
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
      const q = backtest(P, FX, opt, D.asof), y = backtest(P, FX, Object.assign({}, opt, { reb: "Y" }), D.asof);
      out.aims[id].markets[mk] = { quarterly: q, yearly: Object.assign({}, y, { dates: undefined, rets: undefined, indexRets: undefined }), live: live(P, D, opt, extra) };
    }
  }
  fs.writeFileSync(path.join(SITE, "generator.json"), JSON.stringify(out));
  console.log("::notice::Generator: " + Object.entries(out.aims).map(([k, a]) => `${k} ${a.markets.ALL.quarterly.verdict}`).join(", "));
}

if (require.main === module) main();
module.exports = { backtest, live };
