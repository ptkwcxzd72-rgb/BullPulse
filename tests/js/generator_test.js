// node tests/js/generator_test.js -- portfolio generator: limits, filters, exclusions, near-duplicates, whole shares
const assert = require("assert");
const E = require("../../site/lab-engine.js");
const G = require("../../site/generator-core.js");

// A synthetic panel of 40 stocks in 4 sectors over 30 months, generated deterministically.
const NM = 30, N = 40;
let seed = 7;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const months = Array.from({ length: NM }, (_, k) => new Date(Date.UTC(2020, k + 1, 0)).toISOString().slice(0, 10));
const ids = Array.from({ length: N }, (_, i) => (i < 20 ? "LSE-" : "US-") + "S" + i);
const sector = ids.map((_, i) => ["Energy", "Technology", "Utilities", "Financials"][i % 4]);
const ex = ids.map(id => id.startsWith("LSE") ? "LSE" : "US");
const field = f => months.map(() => ids.map((_, i) => f(i)));
// stocks 0 and 4 (both Energy) move in perfect step; everything else is independent noise
const base = months.map(() => (rnd() - 0.5) * 0.2);
const fwd = months.map((_, k) => ids.map((_, i) => Math.round(((i === 0 || i === 4) ? base[k] : (rnd() - 0.5) * 0.2) * 1e4)));
const P = {
  months, ids, ex, sector, idx: ex.map(e => e === "LSE" ? "FTSE 100" : "S&P 500"), trust: ids.map((_, i) => i === 39 ? 1 : 0), scale: {},
  fields: {
    T: field(i => 100 - i), M: field(i => (i * 37) % 100), G: field(i => (i * 53) % 100), FP: field(i => 10 + (i % 20)),
    Vp: field(i => (i * 11) % 100), divY: field(i => i % 5 === 0 ? 0.2 : (i % 8) * 0.01), vol1y: field(i => 0.1 + (i % 10) * 0.04), d200: field(i => i % 3 ? 0.05 : -0.05),
  },
  fwd, bench: { sp500: months.map(() => 0.01), ftse100: months.map(() => 0.01) },
};
const V = E.makeView(P), M = NM - 1;
const names = Object.fromEntries(ids.map(id => [id, "Company " + id]));
const pick = opt => G.choose(V, M, Object.assign({}, G.DEFAULTS, opt), { names });
const sum = a => a.reduce((s, x) => s + x, 0);

// 1. size, weights, per-stock and per-sector limits
for (const aim of Object.keys(G.AIMS)) for (const [n, cap, sc] of [[12, 10, 30], [8, 15, 25], [20, 5, 40]]) {
  const r = pick({ aim, n, cap, sectorCap: sc, maxCorr: 1 });
  const W = sum(r.picks.map(p => p.w));
  assert(r.picks.length <= n, `${aim}: at most ${n} stocks`);
  assert(W <= 1 + 1e-9, `${aim}: weights add to at most 100%`);
  if (r.picks.length * cap / 100 >= 1) assert(r.picks.every(p => p.w <= cap / 100 + 1e-9), `${aim}: no stock above ${cap}%`);
  const bySec = {};
  r.picks.forEach(p => bySec[sector[p.i]] = (bySec[sector[p.i]] || 0) + p.w);
  assert(Object.values(bySec).every(v => v <= sc / 100 + 1e-9), `${aim}: no sector above ${sc}% (${JSON.stringify(bySec)})`);
  assert(Object.values(r.picks.reduce((a, p) => (a[sector[p.i]] = (a[sector[p.i]] || 0) + 1, a), {})).every(c => c <= Math.floor(n * sc / 100)), `${aim}: sector count limit`);
  assert(r.picks.every(p => !P.trust[p.i]), `${aim}: investment trusts left out unless asked`);
}

// 2. the same settings give the same portfolio
assert.deepStrictEqual(pick({ aim: "balanced" }), pick({ aim: "balanced" }), "deterministic");

// 3. exclusions are respected
{
  const r = pick({ aim: "balanced", avoidSectors: ["Energy"], avoidIds: ["US-S21", "LSE-S1"], market: "ALL", maxCorr: 1 });
  assert(r.picks.every(p => sector[p.i] !== "Energy"), "avoided sector");
  assert(r.picks.every(p => !["US-S21", "LSE-S1"].includes(ids[p.i])), "avoided stocks");
  assert(pick({ market: "US" }).picks.every(p => ex[p.i] === "US"), "US only");
  assert(pick({ market: "LSE" }).picks.every(p => ex[p.i] === "LSE"), "UK only");
}

// 4. aims' filters: income needs a 2.5-12% yield and 12+ checks; growth needs a share above its long-term average
{
  const inc = pick({ aim: "income", maxCorr: 1 });
  assert(inc.picks.length > 0, "income finds stocks");
  inc.picks.forEach(p => { const y = V.val("divY", M, p.i); assert(y >= 0.025 && y <= 0.12 && V.val("FP", M, p.i) >= 12, "income filter " + ids[p.i]); });
  pick({ aim: "growth" }).picks.forEach(p => assert(V.val("d200", M, p.i) >= 0, "growth filter " + ids[p.i]));
}

// 5. near-duplicates: stock 4 moves exactly with stock 0 (same sector), so they are never both picked
{
  const r = pick({ aim: "balanced", n: 40, sectorCap: 100, cap: 10 });
  const got = new Set(r.picks.map(p => p.i));
  assert(!(got.has(0) && got.has(4)), "twins not both picked");
  assert(r.left.some(l => /in step with/.test(l.reason)), "the left-out twin is explained");
  const off = pick({ aim: "balanced", n: 40, sectorCap: 100, cap: 10, maxCorr: 1 });
  assert(off.picks.some(p => p.i === 0) && off.picks.some(p => p.i === 4), "with the check off, both can be picked");
}

// 6. whole shares: money adds up, nothing goes over the amount
{
  const picks = [{ id: "a", ex: "LSE", ccy: "GBX", price: 250, w: 0.5 }, { id: "b", ex: "US", ccy: "USD", price: 180, w: 0.3 }, { id: "c", ex: "LSE", ccy: "GBP", price: 40, w: 0.2 }];
  const s = G.shares(picks, 10000, 1.3, null, 0.5);
  assert(s.rows.every(r => Number.isInteger(r.shares) && r.shares >= 0), "whole shares");
  assert(Math.abs(s.spent + s.fees + s.cash - 10000) < 1e-6, "spent + costs + cash = amount");
  assert(s.cash >= 0, "never spends more than the amount");
  s.rows.forEach(r => assert(r.cost + r.fee <= 10000 * 0.5 + 1e-6, "no holding above the stock limit"));
  { const big = G.shares([{ ex: "US", ccy: "USD", price: 300, w: 0.25 }, { ex: "US", ccy: "USD", price: 300, w: 0.25 }, { ex: "US", ccy: "USD", price: 300, w: 0.25 }, { ex: "US", ccy: "USD", price: 300, w: 0.25 }], 1000, 1.3);
    assert(big.cash < 240, "rounding leaves less than one share of cash where it can (" + big.cash.toFixed(0) + ")"); }
  { const pk = [0.25, 0.25, 0.25, 0.25].map((w, k) => ({ ex: "US", ccy: "USD", price: [300, 20, 25, 410][k], w }));
    const z = G.shares(pk, 2000, 1.3, null, 0.4);
    assert(z.cash >= 0 && z.cash < 300 / 1.3, "leftover placed in cheaper holdings (" + z.cash.toFixed(0) + ")");
    assert(z.rows.every(r => r.cost + r.fee <= 2000 * 0.4 + 1e-6), "no holding above the stock limit after placing leftovers"); }
  { const r = G.why({ divY: 0.05, vol1y: 0.2, FP: 20, T: 80, above200: true }, "income"); assert(/^Dividend yield 5.0%/.test(r[0]), "income reasons lead with the yield"); }
  assert.strictEqual(s.rows[0].pxGbp, 2.5, "pence converted to pounds");
  assert(Math.abs(s.rows[1].pxGbp - 180 / 1.3) < 1e-9, "dollars converted to pounds");
  // UK stamp duty and US currency fee
  assert(s.rows[0].fee / s.rows[0].cost > 0.0069 && s.rows[1].fee / s.rows[1].cost > 0.0069, "stamp duty and FX fee included");
}

// 7. the generator's rules run inside the Lab engine, trading only on schedule
{
  const st = G.strategy({ aim: "balanced", n: 10, reb: "Q", maxCorr: 1 });
  assert.strictEqual(st.swaps, false);
  const r = E.run(P, [], Object.assign(st, { ccy: "local", costs: { commission: 0, spread: 0, stamp: false, fxFee: 0 } }));
  assert(r.rets.length > 0 && r.rets.every(x => x == null || isFinite(x)), "engine runs the generator");
  assert(r.held.some(h => h > 0), "engine holds stocks");
}

// 8. the nightly file, when present, keeps its promises
const fs = require("fs");
if (fs.existsSync("site/data/generator.json")) {
  const X = JSON.parse(fs.readFileSync("site/data/generator.json", "utf8"));
  for (const [id, a] of Object.entries(X.aims)) for (const [mk, m] of Object.entries(a.markets)) {
    const p = m.live.picks;
    assert(p.length > 0 && p.length <= G.DEFAULTS.n, `${id}/${mk} size`);
    assert(sum(p.map(x => x.w)) <= 1.001, `${id}/${mk} weights`);
    if (mk !== "ALL") assert(p.every(x => (mk === "LSE") === (x.ex === "LSE")), `${id}/${mk} market`);
    assert(["beat", "mixed", "lagged"].includes(m.quarterly.verdict), `${id}/${mk} verdict`);
  }
  console.log("generator.json checked");
}
console.log("generator tests passed");
