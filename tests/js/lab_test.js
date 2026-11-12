// node tests/js/lab_test.js  -- checks the Strategy Lab engine on a tiny synthetic panel
const assert = require("assert");
const L = require("../../site/lab-engine.js");

// 3 stocks, 13 month-ends; A gains 10% a month, B loses 5%, C flat. 1 UK, 2 US.
const months = Array.from({ length: 13 }, (_, k) => `2020-${String(k % 12 + 1).padStart(2, "0")}-28`.replace(/^2020-(\d\d)/, (m, mo) => (k >= 12 ? "2021-" : "2020-") + mo));
const P = {
  months, ids: ["US-A", "US-B", "LSE-C"], ex: ["US", "US", "LSE"], sector: ["X", "X", "Y"], idx: ["S&P 500", "S&P 500", "FTSE 100"], trust: [0, 0, 0],
  scale: { T: 1, score: 1, d200: 1000, vol1y: 1000 },
  fields: {
    T: months.map(() => [90, 10, 50]), M: months.map(() => [90, 10, 50]), score: months.map(() => [90, 10, 50]),
    d200: months.map(() => [100, -100, 0]), vol1y: months.map(() => [200, 200, 200]),
  },
  fwd: months.map(() => [1000, -500, 0]),
  bench: { sp500: months.map(() => 100), ftse100: months.map(() => 0) },
};
const FX = [["2000-01-01", 1.25]];
const base = { start: 1000, monthly: 0, ccy: "local", costs: { commission: 0, spread: 0, stamp: false, fxFee: 0 }, rebalance: "M", weighting: "equal" };

// 1. hold only A, no costs: 13 months of +10%
let r = L.run(P, FX, Object.assign({}, base, { source: { type: "list", ids: ["US-A"] } }));
assert(Math.abs(r.final - 1000 * Math.pow(1.1, 13)) < 1e-6, "list of one stock compounds its returns");

// 2. rule: top 1 by score picks A
r = L.run(P, FX, Object.assign({}, base, { source: { type: "rule", market: "ALL", rules: [], top: 1, w: { T: 1 } } }));
assert(Math.abs(r.final - 1000 * Math.pow(1.1, 13)) < 1e-6, "rule picks the top stock");

// 3. exit below the 200-day average to cash: B is dropped, A and B equal -> half in A, half cash
r = L.run(P, FX, Object.assign({}, base, { source: { type: "list", ids: ["US-A", "US-B"] }, exit200: true, exitTo: "cash" }));
const s = L.stats(r.rets, r.dates);
assert(Math.abs(r.rets[0] - 0.05) < 1e-9, "exit to cash keeps half in cash");

// 4. costs: 1% each way on a monthly-rebalanced pair reduces the result
const withCost = L.run(P, FX, Object.assign({}, base, { source: { type: "list", ids: ["US-A", "US-B"] }, costs: { commission: 1, spread: 0, stamp: false, fxFee: 0 } }));
const noCost = L.run(P, FX, Object.assign({}, base, { source: { type: "list", ids: ["US-A", "US-B"] } }));
assert(withCost.final < noCost.final && withCost.costs > 0, "costs are charged");

// 5. currency: pound view of a US stock when the dollar is flat is unchanged
r = L.run(P, FX, Object.assign({}, base, { ccy: "GBP", source: { type: "list", ids: ["US-A"] } }));
assert(Math.abs(r.final - 1000 * Math.pow(1.1, 13)) < 1e-6, "flat exchange rate leaves returns unchanged");

// 6. monthly saving and the benchmark run with the same money
r = L.run(P, FX, Object.assign({}, base, { monthly: 100, source: { type: "list", ids: ["LSE-C"] } }));
assert(Math.abs(r.final - 2200) < 1e-6 && r.invested[r.invested.length - 1] === 2200, "flat stock keeps the money paid in");
const br = L.benchRets(r.bench.sp500, r.invested);
assert(br.every(x => Math.abs(x - 0.01) < 1e-9), "benchmark time-weighted returns ignore the money paid in");

// 7. stats and bootstrap
const st = L.stats(Array(36).fill(0.01), Array.from({ length: 36 }, (_, k) => `20${20 + Math.floor(k / 12)}-01-31`));
assert(Math.abs(st.cagr - (Math.pow(1.01, 12) - 1)) < 1e-9 && st.maxDD === 0, "stats");
const bs = L.bootstrap(Array(60).fill(0.01), 200);
assert(Math.abs(bs.p50 - (Math.pow(1.01, 12) - 1)) < 1e-9, "bootstrap of a constant return is that return");

// 8. capital gains tax in a general account: gains above the allowance taxed in March
// (2019/20: allowance £12,000, 20% for a higher-rate taxpayer; about £30,000 of gains by March)
r = L.run(P, FX, Object.assign({}, base, { start: 3000000, account: "gia", source: { type: "list", ids: ["US-A", "US-B"] } }));
assert(r.taxCGT > 0 && r.tax >= r.taxCGT, "tax charged on realised gains");
const small = L.run(P, FX, Object.assign({}, base, { start: 1000000, account: "gia", source: { type: "list", ids: ["US-A", "US-B"] } }));
assert(small.taxCGT === 0, "gains within that year's £12,000 allowance are not taxed");
const basic = L.run(P, FX, Object.assign({}, base, { start: 3000000, account: "gia", taxBand: "basic", source: { type: "list", ids: ["US-A", "US-B"] } }));
assert(basic.taxCGT > 0 && basic.taxCGT < r.taxCGT, "basic-rate taxpayers pay the lower rate");

// 9. dividends: US tax withheld at source even in an ISA; UK dividend tax only on a general account
const PD = Object.assign({}, P, { scale: Object.assign({}, P.scale, { divY: 1000 }), fields: Object.assign({}, P.fields, { divY: months.map(() => [40, 40, 40]) }), fwd: months.map(() => [0, 0, 0]) });
const isa = L.run(PD, FX, Object.assign({}, base, { start: 100000, account: "isa", source: { type: "list", ids: ["US-A"] } }));
assert(Math.abs(isa.wht - 100000 * 0.04 * 0.15) < 100 && isa.tax === 0, "15% of US dividends withheld in an ISA, no UK tax");
const ukIsa = L.run(PD, FX, Object.assign({}, base, { start: 100000, account: "isa", source: { type: "list", ids: ["LSE-C"] } }));
assert(ukIsa.wht === 0 && Math.abs(ukIsa.final - 100000) < 1e-6, "UK dividends untaxed in an ISA");
const gia = L.run(PD, FX, Object.assign({}, base, { start: 1000000, account: "gia", source: { type: "list", ids: ["LSE-C"] } }));
assert(gia.taxDiv > 0 && gia.taxCGT === 0, "UK dividend tax on a general account");
const giaUS = L.run(PD, FX, Object.assign({}, base, { start: 1000000, account: "gia", source: { type: "list", ids: ["US-A"] } }));
assert(giaUS.taxDiv < gia.taxDiv, "tax withheld in the US counts against UK dividend tax");
console.log("lab engine: all tests passed");
