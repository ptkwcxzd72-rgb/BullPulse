// BullPulse portfolio generator: turns your preferences into a portfolio, using the signals the app
// computes every night. The same select() picks today's portfolio and runs inside the Strategy Lab
// engine at every past month-end, so any combination of settings can be backtested exactly as it
// would have been used.
//
// Only signals with history pick the stocks (trend, momentum, growth, fundamentals, value,
// dividend yield, volatility). News tone, investor ownership and the learning model's estimate have
// little or no history, so they only appear as warnings and break near-ties.
(function (root) {
  "use strict";

  // Each aim: hard filters (applied before ranking) and a recipe of ranked signals (percentiles
  // within the eligible stocks, 0..1). Fixed in advance from well-known ideas, not fitted.
  const AIMS = {
    growth: { name: "Growth", short: "Companies growing fast, with the market's approval",
      about: "Ranks on revenue growth and momentum, with some weight on trend and quality, and leaves out shares below their long-term average.",
      filters: [["d200", ">=", 0]], recipe: { growth: 0.4, momentum: 0.3, trend: 0.15, quality: 0.15 }, weighting: "equal" },
    income: { name: "Income", short: "Dividends from financially sound companies",
      about: "Requires a dividend yield of at least 2.5% and passing at least 12 of 30 fundamental checks, then ranks on yield, quality and trend, avoiding the very highest yields that often signal trouble.",
      filters: [["divY", ">=", 0.025], ["divY", "<=", 0.12], ["FP", ">=", 12]], recipe: { yield: 0.45, quality: 0.3, trend: 0.15, steady: 0.1 }, weighting: "equal" },
    steady: { name: "Steadier", short: "Calmer shares and sound finances",
      about: "Keeps to shares that moved less than the typical one over the past year, ranks on steadiness and quality, and puts more money in the steadiest.",
      filters: [["volRank", "<=", 0.5]], recipe: { steady: 0.45, quality: 0.35, trend: 0.2 }, weighting: "invvol" },
    balanced: { name: "Balanced", short: "A blend of every signal",
      about: "Ranks every stock on trend, momentum, growth, quality, value and steadiness together, so no single idea dominates.",
      filters: [], recipe: { trend: 0.2, momentum: 0.2, growth: 0.15, quality: 0.2, value: 0.15, steady: 0.1 }, weighting: "equal" },
  };
  const SIGNALS = {
    trend: "Trend", momentum: "Momentum", growth: "Revenue growth", quality: "Fundamentals", value: "Value", yield: "Dividend yield", steady: "Steadiness",
  };
  const DEFAULTS = { aim: "balanced", market: "ALL", n: 20, cap: 10, sectorCap: 30, reb: "Q", amount: 10000, avoidSectors: [], avoidIds: [], avoidOwned: false,
    weighting: "aim", maxCorr: 0.85, trusts: false };

  const isNum = x => typeof x === "number" && isFinite(x);
  function rawSignal(V, k, m, i) {
    switch (k) {
      case "trend": return V.val("T", m, i);
      case "momentum": return V.val("M", m, i);
      case "growth": return V.val("G", m, i);
      case "quality": return V.val("FP", m, i);
      case "value": return V.val("Vp", m, i);
      case "yield": return V.val("divY", m, i);
      case "steady": { const v = V.val("vol1y", m, i); return v == null ? null : -v; }
    }
    return null;
  }
  // percentile ranks (0..1) of each signal within the eligible stocks
  function ranks(V, m, ids, keys) {
    const out = {};
    for (const k of keys) {
      const xs = ids.map(i => [i, rawSignal(V, k, m, i)]).filter(x => isNum(x[1])).sort((a, b) => a[1] - b[1]);
      const r = new Map();
      xs.forEach(([i], j) => r.set(i, xs.length > 1 ? j / (xs.length - 1) : 0.5));
      out[k] = r;
    }
    return out;
  }
  // a company's name without share class, so two classes of one company aren't both picked
  const company = s => String(s || "").replace(/\s*\((?:class|series)\s+[a-z]\)|\s+class\s+[a-z]$/i, "").trim().toLowerCase();

  // trailing 24 monthly returns of stock i from a view with history, before month hm
  function trailing(H, hm, i) {
    if (!H || i == null) return null;
    const r = [];
    for (let k = hm - 24; k < hm; k++) { const x = k >= 0 ? H.fwd(k, i) : null; if (x == null || Math.abs(x) > 2) return null; r.push(x); }
    return r;
  }
  function corr(a, b) {
    if (!a || !b) return 0;
    const n = a.length, ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n;
    let c = 0, va = 0, vb = 0;
    for (let k = 0; k < n; k++) { c += (a[k] - ma) * (b[k] - mb); va += (a[k] - ma) ** 2; vb += (b[k] - mb) ** 2; }
    return va > 0 && vb > 0 ? c / Math.sqrt(va * vb) : 0;
  }

  // Choose the portfolio at month m of view V. opt: settings (see DEFAULTS); ctx: { hist: a view
  // with return history and hm, the month in it to look back from (defaults to V, m), names: id ->
  // name, extra: id -> { prob6, tone30 } used only to break near-ties, held: Set of indexes already
  // held (kept while they rank within twice the size) }. Returns { picks: [{ i, w, score, why }],
  // left: [{ i, reason }] }.
  function choose(V, m, opt, ctx) {
    const o = Object.assign({}, DEFAULTS, opt || {});
    ctx = ctx || {};
    const aim = AIMS[o.aim] || AIMS.balanced;
    const avoidS = new Set(o.avoidSectors || []), avoidI = new Set(o.avoidIds || []);
    const P = V.P;
    // eligible stocks
    let ids = [];
    for (let i = 0; i < V.n; i++) {
      if (o.market !== "ALL" && P.ex[i] !== o.market) continue;
      if (!o.trusts && V.trust(i)) continue;
      if (!V.member(m, i) || V.val("T", m, i) == null) continue;
      if (avoidS.has(P.sector[i]) || avoidI.has(P.ids[i])) continue;
      ids.push(i);
    }
    // volatility rank for the "steadier" filter (within the eligible stocks)
    const vr = ranks(V, m, ids, ["steady"]).steady;
    const passes = i => aim.filters.every(([f, op, a]) => {
      const v = f === "volRank" ? (vr.has(i) ? 1 - vr.get(i) : null) : V.val(f, m, i);
      if (v == null) return false;
      return op === ">=" ? v >= a : v <= a;
    });
    ids = ids.filter(passes);
    const keys = Object.keys(aim.recipe);
    const R = ranks(V, m, ids, keys);
    const score = new Map();
    for (const i of ids) {
      let s = 0, w = 0;
      for (const k of keys) if (R[k].has(i)) { s += aim.recipe[k] * R[k].get(i); w += aim.recipe[k]; }
      if (w >= 0.6) score.set(i, s / w);   // needs most of the recipe's signals
    }
    // near-ties (within 1 point on a 0..100 scale) broken by the untested signals, then by name
    const extra = ctx.extra || {};
    const tb = i => { const e = extra[P.ids[i]] || {}; return (e.prob6 ?? 0.5) + (e.tone30 ?? 0) * 0.05; };
    let order = [...score.keys()].sort((a, b) => {
      const d = score.get(b) - score.get(a);
      if (Math.abs(d) > 0.01) return d;
      const t = tb(b) - tb(a);
      return t || P.ids[a].localeCompare(P.ids[b]);
    });
    // stocks already held stay while they rank within twice the size
    const held = ctx.held || new Set();
    if (held.size) {
      const top = new Set(order.slice(0, o.n * 2));
      const stay = order.filter(i => held.has(i) && top.has(i));
      order = stay.concat(order.filter(i => !stay.includes(i)));
    }
    // pick greedily, keeping to the sector limit and avoiding near-duplicates
    const H = ctx.hist || V, hm = ctx.hist ? ctx.hm : m;
    const hidx = ctx.hist ? (i => H.idx.get(P.ids[i])) : (i => i);
    const maxPerSector = Math.max(1, Math.floor(o.n * o.sectorCap / 100 + 1e-9));
    const picks = [], left = [], perSector = {}, names = new Set(), rets = [];
    for (const i of order) {
      if (picks.length >= o.n) break;
      const sec = P.sector[i] || "Other";
      const nm = company(ctx.names ? ctx.names[P.ids[i]] : P.ids[i]);
      if (names.has(nm)) { left.push({ i, reason: "another share class of a company already chosen" }); continue; }
      if ((perSector[sec] || 0) >= maxPerSector) { left.push({ i, reason: `${sec} already at the ${o.sectorCap}% sector limit` }); continue; }
      const r = trailing(H, hm, hidx(i));
      let twin = null;
      // near-duplicates: very closely correlated over two years (a higher bar across sectors,
      // where a close match is more likely to be chance)
      if (r && o.maxCorr < 1) for (const p of picks) { const lim = (P.sector[p.i] || "Other") === sec ? o.maxCorr : Math.max(o.maxCorr, 0.92); if (corr(r, p.r) > lim) { twin = p; break; } }
      if (twin) { left.push({ i, reason: `moves almost in step with ${ctx.names ? ctx.names[P.ids[twin.i]] : P.ids[twin.i]}`, twin: twin.i }); continue; }
      picks.push({ i, r, score: score.get(i) });
      perSector[sec] = (perSector[sec] || 0) + 1;
      names.add(nm);
    }
    // weights
    const mode = o.weighting === "aim" ? aim.weighting : o.weighting;
    let raw = picks.map(p => mode === "invvol" ? 1 / Math.max(0.08, V.val("vol1y", m, p.i) ?? 0.3) : mode === "score" ? 0.5 + p.score : 1);
    let tot = raw.reduce((a, b) => a + b, 0) || 1;
    let w = raw.map(x => x / tot);
    // both limits together: trim anything over the per-stock or sector limit and pass the excess to
    // stocks with room under both, in proportion; whatever can't be placed stays as cash
    const cap = picks.length && o.cap / 100 * picks.length >= 1 ? o.cap / 100 : 1, scap = o.sectorCap / 100;
    const secOf = k => P.sector[picks[k].i] || "Other";
    for (let it = 0; it < 60; it++) {
      let excess = 0;
      w = w.map(x => { if (x > cap) { excess += x - cap; return cap; } return x; });
      const sw = {};
      w.forEach((x, k) => sw[secOf(k)] = (sw[secOf(k)] || 0) + x);
      for (const [s, v] of Object.entries(sw)) if (v > scap + 1e-12) {
        const f = scap / v;
        w = w.map((x, k) => { if (secOf(k) === s) { excess += x * (1 - f); return x * f; } return x; });
        sw[s] = scap;
      }
      if (excess < 1e-12) break;
      const room = w.map((x, k) => Math.max(0, Math.min(cap - x, scap - sw[secOf(k)])));
      const base = w.map((x, k) => room[k] > 1e-12 ? x : 0), bt = base.reduce((a, b) => a + b, 0);
      if (bt <= 0) break;   // nowhere to put it: hold cash rather than break a limit
      w = w.map((x, k) => x + excess * base[k] / bt);
    }
    return { picks: picks.map((p, k) => ({ i: p.i, w: w[k], score: p.score })), left: left.slice(0, 12), eligible: ids.length, aim: o.aim };
  }

  // the strategy object the Lab engine runs: its targets come from choose()
  function strategy(opt, extraS) {
    const o = Object.assign({}, DEFAULTS, opt || {});
    let held = new Set();
    return Object.assign({ name: (AIMS[o.aim] || AIMS.balanced).name + " portfolio", rebalance: o.reb, swaps: false, weighting: "equal", cap: o.cap,
      start: 10000, monthly: 0, ccy: "GBP", account: "isa", costs: { commission: 0.1, spread: 0.1, fxFee: 0.5, stamp: true }, from: "",
      source: { type: "rule", market: o.market, rules: [], top: o.n },
      select(V, m, heldNow) {
        const res = choose(V, m, o, { held: heldNow || held });
        return new Map(res.picks.map(p => [p.i, p.w]));
      } }, extraS || {});
  }

  // why a stock suits the aim, strongest ingredient first (s: a snapshot stock)
  function why(s, aimId) {
    const aim = AIMS[aimId] || AIMS.balanced, pc = v => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(0) + "%", top = v => Math.min(99, v);
    const y = s.div && s.div.yld != null ? s.div.yld : s.divY;
    const say = {
      yield: () => y != null && y > 0 ? `Dividend yield ${(y * 100).toFixed(1)}%.` : null,
      steady: () => s.vol1y != null ? `Steadier than most: its price swung about ${(s.vol1y * 100).toFixed(0)}% a year.` : null,
      growth: () => s.revGrowth != null && s.revGrowth > 0.03 ? `Revenue growing ${pc(s.revGrowth)} a year.` : null,
      momentum: () => s.M != null && s.M >= 60 ? `Strong momentum: ${pc(s.mom)} over the past year leaving out the last month, more than ${top(s.M)}% of its market.` : null,
      trend: () => s.T != null && s.T >= 60 ? `In an uptrend${s.above200 ? ", above its 200-day average" : ""}; a stronger trend than ${top(s.T)}% of its market.` : null,
      quality: () => s.FP != null && s.FP >= 15 ? `Passes ${s.FP} of 30 fundamental checks${s.roe != null ? `; return on equity ${pc(s.roe)}` : ""}.` : null,
      value: () => s.fairVs != null && s.fairVs < 0 ? `Priced ${Math.round(-s.fairVs * 100)}% below our estimate of fair value.` : null,
    };
    return Object.entries(aim.recipe).sort((a, b) => b[1] - a[1]).map(([k]) => say[k] && say[k]()).filter(Boolean).slice(0, 3);
  }

  // whole shares for an amount in pounds; prices in pence (GBX), pounds or dollars
  function shares(picks, amount, usdPerGbp, costs, maxW) {
    const c = Object.assign({ commission: 0.1, spread: 0.1, fxFee: 0.5, stamp: true }, costs || {});
    let spent = 0, fees = 0;
    const rows = picks.map(p => {
      const px = p.ccy === "GBX" ? p.price / 100 : p.ccy === "USD" ? p.price / usdPerGbp : p.price;
      const rate = (c.commission + c.spread) / 100 + (p.ex === "LSE" && c.stamp ? 0.005 : 0) + (p.ex !== "LSE" ? c.fxFee / 100 : 0);
      const budget = amount * p.w;
      const n = px > 0 ? Math.floor(budget / (px * (1 + rate))) : 0;
      const cost = n * px, fee = cost * rate;
      spent += cost; fees += fee;
      return Object.assign({}, p, { shares: n, cost, fee, pxGbp: px, rate, budget });
    });
    // rounding down leaves cash; buy one more share where it brings a holding nearest its target,
    // while the extra share costs no more than half a share over the target and the money lasts
    for (let it = 0; it < 500; it++) {
      const cash = amount - spent - fees;
      let best = null, gap = 0;
      for (const r of rows) {
        const one = r.pxGbp * (1 + r.rate);
        if (!(r.pxGbp > 0) || one > cash + 1e-9) continue;
        const after = (r.shares + 1) * one;
        if (after > r.budget + one / 2) continue;
        const g = r.budget - r.shares * one;
        if (g > gap) { gap = g; best = r; }
      }
      if (!best) break;
      best.shares++; best.cost += best.pxGbp; best.fee += best.pxGbp * best.rate; spent += best.pxGbp; fees += best.pxGbp * best.rate;
    }
    // expensive shares can still leave a lot unspent: place it in the holdings furthest below the
    // most allowed in one stock (maxW), so the money is invested without breaking that limit
    const lim = amount * (maxW || 1);
    for (let it = 0; it < 2000; it++) {
      const cash = amount - spent - fees;
      let best = null, room = 0;
      for (const r of rows) {
        const one = r.pxGbp * (1 + r.rate), now = r.cost + r.fee;
        if (!(r.pxGbp > 0) || one > cash + 1e-9 || now + one > lim + 1e-9) continue;
        const rel = (now + one) / Math.max(r.budget, 1e-9);
        if (best == null || rel < room) { room = rel; best = r; }
      }
      if (!best) break;
      best.shares++; best.cost += best.pxGbp; best.fee += best.pxGbp * best.rate; spent += best.pxGbp; fees += best.pxGbp * best.rate;
    }
    rows.forEach(r => { delete r.rate; delete r.budget; });
    return { rows, spent, fees, cash: amount - spent - fees };
  }

  const api = { AIMS, SIGNALS, DEFAULTS, choose, strategy, shares, why, corr, company };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.GeneratorCore = api;
})(typeof window !== "undefined" ? window : globalThis);
