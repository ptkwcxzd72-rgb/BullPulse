// node tests/js/models_test.js -- model portfolios: trading only on schedule, shared rules, reasons
const assert = require("assert");
const L = require("../../site/lab-engine.js");
const MC = require("../../site/models-core.js");

// 2 stocks whose ranks swap every month: with monthly swaps the strategy trades every month;
// with swaps off and a quarterly schedule it trades only at quarter-ends.
const months = ["2020-01-31", "2020-02-28", "2020-03-31", "2020-04-30", "2020-05-29", "2020-06-30", "2020-07-31"];
const P = {
  months, ids: ["US-A", "US-B"], ex: ["US", "US"], sector: ["X", "X"], idx: ["S&P 500", "S&P 500"], trust: [0, 0], scale: { T: 1 },
  fields: { T: months.map((_, k) => k % 2 ? [10, 90] : [90, 10]) },
  fwd: months.map(() => [0, 0]), bench: { sp500: months.map(() => 0), ftse100: months.map(() => 0) },
};
const S = extra => Object.assign({ start: 1000, monthly: 0, ccy: "local", costs: { commission: 0, spread: 0, stamp: false, fxFee: 0 }, rebalance: "Q", weighting: "equal",
  source: { type: "rule", market: "ALL", rules: [], top: 1, keep: 1, w: { T: 1 } } }, extra);
const swapping = L.run(P, [], S({}));
const scheduled = L.run(P, [], S({ swaps: false }));
assert(swapping.trades > scheduled.trades, "trading only on schedule trades less");
assert(scheduled.trades <= 2 * 3, "scheduled: only the first month and quarter-ends");

// the shared strategy definitions: same trading rules for all, keep = twice the size
for (const def of MC.STRATEGIES) {
  const s = MC.strategy(def, "US", "Y");
  assert.strictEqual(s.swaps, false, def.id + " trades only on schedule");
  assert.strictEqual(s.source.keep, def.top * 2, def.id + " keeps holdings within twice its size");
  assert.strictEqual(s.source.market, "US");
  assert.strictEqual(s.rebalance, "Y");
}

// reasons and context read naturally
const st = { M: 95, T: 88, mom: 0.5, above200: true, fairVs: -0.3, FP: 20, roe: 0.25, revGrowth: 0.2, score: 80, rank: 3, tone30: -0.4, newsN30: 5, nextRes: "2026-11-23" };
const rs = MC.reasons(st, MC.STRATEGIES.find(s => s.id === "value"));
assert(rs.some(r => r.includes("30% below our estimate of fair value")), "value reason: " + rs.join(" | "));
assert(!rs.some(r => r.includes("+30%")), "no stray plus sign");
const fl = MC.flags(st);
assert(fl.some(f => f.kind === "neg" && f.text.startsWith("Negative news")), "negative news flagged");
assert(fl.some(f => f.text === "Results due 23 Nov 2026."), "results date written out");

// market conditions use only returns before each date
const M = require("../../scripts/models.js");
const n = 30, ids = Array.from({ length: 60 }, (_, i) => "US-" + i);
const Q = { months: Array.from({ length: n }, (_, k) => new Date(Date.UTC(2020, k + 1, 0)).toISOString().slice(0, 10)), ids, ex: ids.map(() => "US"),
  fwd: Array.from({ length: n }, (_, k) => ids.map(() => (k < 15 ? 100 : -100))), bench: { sp500: Array(n).fill(100), ftse100: Array(n).fill(100) }, fields: {} };
const reg = M.regimes(Q, "2022-07-31");
const at15 = reg.find(x => x.m === 15), at28 = reg.find(x => x.m === 28);
assert(at15.breadth === 1 && at28.breadth === 0, "breadth reflects the past six months only");
assert(Math.abs(at15.trend - (Math.pow(1.01, 12) - 1)) < 1e-9, "trend is the past 12 months of the index");
console.log("model portfolios: all tests passed");
