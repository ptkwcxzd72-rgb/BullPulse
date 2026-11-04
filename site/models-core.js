// BullPulse model portfolios: the strategy definitions and the plain-English reasons for each pick.
// Shared by the nightly analysis (scripts/models.js, in node) and the page (models.html), so the
// portfolios people see are picked by exactly the rules that were backtested.
//
// The rules are fixed in advance from well-known ideas (momentum, quality, value, growth, low
// volatility); they are not fitted to BullPulse's own data. The last two years of every backtest
// are reported separately so anyone can see whether a strategy held up after the years it was
// judged on.
(function (root) {
  "use strict";

  const BASE = { weighting: "equal", cap: 10, exit200: false, exitTo: "spread", start: 10000, monthly: 0, ccy: "GBP", account: "isa",
    costs: { commission: 0.1, spread: 0.1, fxFee: 0.5, stamp: true } };

  // w: ranking blend of Trend, Momentum, Growth, Fundamentals and Value (cheapness) percentiles
  const STRATEGIES = [
    { id: "score", name: "BullPulse score leaders", short: "The highest BullPulse scores",
      idea: "Owns the stocks with the strongest combination of long-term trend and 12-month momentum, the two signals behind the BullPulse score.",
      why: "Shares that have risen steadily tend to keep rising for some months because investors react slowly to good news (the momentum effect, documented across markets and decades). Its weakness is sharp reversals when markets turn.",
      rules: [], w: { T: 50, M: 50 }, top: 20 },
    { id: "momentum", name: "Momentum leaders", short: "Strong 12-month winners still in an uptrend",
      idea: "Owns the strongest 12-month performers that are still above their long-term trend.",
      why: "A purer momentum strategy. Historically one of the most reliable return sources, but it can lose heavily when the market leadership changes quickly, as in 2009 and 2020.",
      rules: [["M", ">=", 70], ["T", ">=", 50]], w: { T: 40, M: 60 }, top: 20 },
    { id: "quality", name: "Quality with trend", short: "Financially strong companies in an uptrend",
      idea: "Owns companies that pass the most fundamental checks (profitability, debt, cash flow), preferring those whose shares are trending up.",
      why: "Profitable, conservatively financed companies have tended to do better than their risk suggests, and they usually fall less in bad markets. It can lag in sharp rallies led by weaker companies.",
      rules: [["FP", ">=", 18], ["T", ">=", 50]], w: { F: 60, T: 40 }, top: 20 },
    { id: "value", name: "Value with trend", short: "Cheap shares that have started to recover",
      idea: "Owns shares that look cheap against their estimated fair value, but only once their trend has turned up.",
      why: "Cheap shares have earned more over long periods, but they can stay cheap for years. Requiring an uptrend tries to avoid buying too early. Value has had long dry spells, such as most of the 2010s.",
      rules: [["Vp", ">=", 60], ["T", ">=", 50]], w: { V: 60, T: 40 }, top: 20 },
    { id: "growth", name: "Growth leaders", short: "Fast-growing revenue with the market's approval",
      idea: "Owns companies with the fastest revenue growth whose shares are also moving up.",
      why: "Companies that keep growing sales can compound for years; momentum confirms the market agrees. It is sensitive to interest rates and expensive valuations, as in 2022.",
      rules: [["G", ">=", 70], ["T", ">=", 40]], w: { G: 60, M: 40 }, top: 20 },
    { id: "steady", name: "Steady compounders", short: "Lower-volatility, financially sound companies",
      idea: "Owns financially sound companies whose shares have moved least over the past year, weighted towards the steadiest.",
      why: "Calmer shares have historically delivered returns close to the market's with smaller falls (the low-volatility effect). It tends to lag in strong bull markets.",
      rules: [["vol1y", "<=", 28], ["FP", ">=", 15]], w: { F: 50, T: 50 }, top: 20, weighting: "invvol" },
    { id: "allround", name: "All-rounder", short: "A balance of every signal",
      idea: "Ranks every stock on a blend of trend, momentum, growth, fundamentals and value, and owns the best all-round scores.",
      why: "Combining signals that work at different times smooths the ride: when momentum stumbles, value or quality often holds up. Expect fewer big wins and fewer big losses than any single idea.",
      rules: [], w: { T: 25, M: 25, G: 15, F: 20, V: 15 }, top: 25 },
  ];

  const MARKETS = { ALL: "UK and US", LSE: "UK only", US: "US only" };

  // The same trading rules for every strategy (not tuned strategy by strategy): trade only on the
  // scheduled date, and keep a holding while it still ranks within twice the portfolio's size, so
  // a stock isn't sold the moment it slips from 20th to 21st. Frequent trading was tested and its
  // costs outweighed the gains (see "How often to trade" on the page).
  function strategy(def, market, rebalance, extra) {
    return Object.assign({}, BASE, { weighting: def.weighting || BASE.weighting }, {
      name: def.name, rebalance: rebalance || "Q", drift: 5, from: "", swaps: false,
      source: { type: "rule", market: market || "ALL", idx: "", sector: "", noTrusts: true, rules: def.rules.map(r => r.slice()), w: Object.assign({}, def.w), top: def.top, keep: def.top * 2 },
    }, extra || {});
  }

  const pct = (v, d = 0) => v == null ? "" : (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(d) + "%";
  // why a stock is in the portfolio, from tonight's figures (s: a snapshot stock)
  function reasons(s, def) {
    const out = [];
    const w = def ? def.w : { T: 1, M: 1 };
    const top = v => Math.min(99, v);
    if ((w.M || 0) > 0 && s.M != null && s.M >= 70) out.push(`Strong momentum: ${pct(s.mom)} over the past year leaving out the last month, more than ${top(s.M)}% of its market.`);
    if ((w.T || 0) > 0 && s.T != null && s.T >= 60) out.push(`In an uptrend${s.above200 ? ", above its 200-day average" : ""}; a stronger trend than ${top(s.T)}% of its market.`);
    if ((w.G || 0) > 0 && s.revGrowth != null && s.revGrowth > 0.05) out.push(`Revenue growing ${pct(s.revGrowth)} a year.`);
    if ((w.F || 0) > 0 && s.FP != null && s.FP >= 15) out.push(`Passes ${s.FP} of 30 fundamental checks${s.roe != null ? `; return on equity ${pct(s.roe)}` : ""}.`);
    if ((w.V || 0) > 0 && s.fairVs != null && s.fairVs < 0) out.push(`Priced ${Math.round(-s.fairVs * 100)}% below our estimate of fair value.`);
    if (def && def.id === "steady" && s.vol1y != null) out.push(`Steadier than most: volatility ${pct(s.vol1y)} a year.`);
    if (!out.length && s.score != null) out.push(`BullPulse score ${s.score}, rank ${s.rank} in its market.`);
    return out;
  }
  const day = d => { try { return new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); } catch (e) { return d; } };
  // news and other context that isn't part of the (backtested) rules but a reader should see
  function flags(s) {
    const out = [];
    if (s.tone30 != null && s.newsN30 >= 3) {
      if (s.tone30 <= -0.25) out.push({ kind: "neg", text: `Negative news lately (tone ${s.tone30.toFixed(2)} over ${s.newsN30} stories in 30 days).` });
      else if (s.tone30 >= 0.25) out.push({ kind: "pos", text: `Positive news lately (tone +${s.tone30.toFixed(2)} over ${s.newsN30} stories in 30 days).` });
    }
    if (s.toneChg != null && s.toneChg <= -0.3) out.push({ kind: "neg", text: "News tone has turned down sharply." });
    if (s.nextRes) out.push({ kind: "info", text: `Results due ${day(s.nextRes)}.` });
    if (s.above200 === false) out.push({ kind: "neg", text: "Currently below its 200-day average." });
    return out;
  }

  const api = { STRATEGIES, MARKETS, BASE, strategy, reasons, flags };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.ModelsCore = api;
})(typeof window !== "undefined" ? window : globalThis);
