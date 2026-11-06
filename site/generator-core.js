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
  const DEFAULTS = { aim: "balanced", market: "ALL", n: 30, cap: 10, sectorCap: 30, reb: "Y", core: 50, amount: 10000, avoidSectors: [], avoidIds: [], avoidOwned: false,
    weighting: "aim", maxCorr: 0.85, trusts: false, build: "" };

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
  function trailing(H, hm, i, len) {
    if (!H || i == null) return null;
    const r = [];
    for (let k = hm - (len || 24); k < hm; k++) { const x = k >= 0 ? H.fwd(k, i) : null; if (x == null || Math.abs(x) > 2) return null; r.push(x); }
    return r;
  }
  function corr(a, b) {
    if (!a || !b) return 0;
    const n = a.length, ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n;
    let c = 0, va = 0, vb = 0;
    for (let k = 0; k < n; k++) { c += (a[k] - ma) * (b[k] - mb); va += (a[k] - ma) ** 2; vb += (b[k] - mb) ** 2; }
    return va > 0 && vb > 0 ? c / Math.sqrt(va * vb) : 0;
  }

  // Covariance of monthly returns, shrunk halfway towards a constant-correlation matrix (Ledoit and
  // Wolf's target): with 36 months for 20+ stocks the raw matrix is too noisy to optimise on. Stocks
  // without a full history get the average correlation and their one-year volatility.
  function covariance(R, vol1y) {
    const n = R.length, T = 36;
    const sd = new Array(n), mu = new Array(n);
    R.forEach((r, a) => {
      if (r) { mu[a] = r.reduce((s, x) => s + x, 0) / r.length; sd[a] = Math.sqrt(r.reduce((s, x) => s + (x - mu[a]) ** 2, 0) / (r.length - 1)); }
      if (!r || !(sd[a] > 0)) sd[a] = Math.max(0.02, (vol1y[a] ?? 0.3) / Math.sqrt(12));
    });
    const rho = [], cs = [];
    for (let a = 0; a < n; a++) { rho.push(new Array(n).fill(0)); rho[a][a] = 1; }
    for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) if (R[a] && R[b]) {
      let c = 0; for (let k = 0; k < T && k < R[a].length; k++) c += (R[a][k] - mu[a]) * (R[b][k] - mu[b]);
      const x = c / (R[a].length - 1) / (sd[a] * sd[b]);
      rho[a][b] = rho[b][a] = x; cs.push(x);
    } else rho[a][b] = rho[b][a] = null;
    const avg = cs.length ? cs.reduce((s, x) => s + x, 0) / cs.length : 0.3;
    const C = [];
    for (let a = 0; a < n; a++) { C.push([]); for (let b = 0; b < n; b++) { const r = a === b ? 1 : rho[a][b] == null ? avg : 0.5 * rho[a][b] + 0.5 * avg; C[a].push(r * sd[a] * sd[b]); } }
    return C;
  }
  const mv = (C, w) => C.map(row => row.reduce((s, x, b) => s + x * w[b], 0));
  // equal risk contribution: each holding adds the same amount of risk to the whole
  function riskParity(C) {
    const n = C.length;
    let w = C.map((r, a) => 1 / Math.sqrt(r[a]));
    let t = w.reduce((s, x) => s + x, 0); w = w.map(x => x / t);
    for (let it = 0; it < 200; it++) {
      const m = mv(C, w);
      w = w.map((x, a) => Math.sqrt(x / Math.max(1e-12, m[a])));   // scales each weight by 1/sqrt(its risk contribution)
      t = w.reduce((s, x) => s + x, 0); w = w.map(x => x / t);
    }
    return w;
  }
  // lowest-risk mix, long only, at most `cap` in any stock (projected gradient)
  function minVariance(C, cap) {
    const n = C.length;
    let w = new Array(n).fill(1 / n);
    const proj = v => {   // onto { sum 1, 0 <= w <= cap } by bisection on a shift
      let lo = -1, hi = 1;
      for (let k = 0; k < 60; k++) { const s = (lo + hi) / 2, t = v.reduce((a, x) => a + Math.min(cap, Math.max(0, x - s)), 0); if (t > 1) lo = s; else hi = s; }
      return v.map(x => Math.min(cap, Math.max(0, x - (lo + hi) / 2)));
    };
    const step = 1 / Math.max(...C.map((r, a) => r[a])) / n;
    for (let it = 0; it < 400; it++) { const g = mv(C, w); w = proj(w.map((x, a) => x - step * g[a])); }
    return w;
  }

  // the index-fund core: `core` percent in an index fund (rebalanced each month, 0.1% a year in
  // charges), the rest in the chosen stocks. ix: the index's monthly returns.
  const FUND_FEE = 0.001;
  function blend(rets, ix, core) {
    const c = Math.max(0, Math.min(100, core || 0)) / 100;
    return rets.map((x, k) => x == null && ix[k] == null ? null : c * ((ix[k] ?? 0) - FUND_FEE / 12) + (1 - c) * (x ?? 0));
  }
  // the index fund(s) the core goes into, by market
  const FUNDS = { LSE: [["FTSE 100 index fund", 1]], US: [["S&P 500 index fund", 1]], ALL: [["FTSE 100 index fund", 0.5], ["S&P 500 index fund", 0.5]] };

  // how well a signal has ranked next month's returns: the monthly rank correlation between the
  // signal and the following month's return (information coefficient) over a market's stocks
  function signalRecord(V, key, market, from, to, minN) {
    const rk = a => { const o = a.map((x, k) => [x, k]).sort((p, q) => p[0] - q[0]); const r = new Array(a.length); o.forEach(([, k], j) => r[k] = j); return r; };
    const ics = [];
    for (let m = from; m < to; m++) {
      const xs = [], ys = [];
      for (let i = 0; i < V.n; i++) {
        if (V.P.ex[i] !== market || !V.member(m, i)) continue;
        const x = rawSignal(V, key, m, i), y = V.fwd(m, i);
        if (x != null && y != null && isNum(x)) { xs.push(x); ys.push(y); }
      }
      if (xs.length >= (minN || 30)) ics.push(corr(rk(xs), rk(ys)));
    }
    if (ics.length < 12) return null;
    const mean = ics.reduce((s, x) => s + x, 0) / ics.length, sd = Math.sqrt(ics.reduce((s, x) => s + (x - mean) ** 2, 0) / (ics.length - 1));
    return { ic: mean, t: sd > 1e-12 ? mean / sd * Math.sqrt(ics.length) : (mean > 0 ? 99 : mean < 0 ? -99 : 0), hit: ics.filter(x => x > 0).length / ics.length, months: ics.length };
  }

  // Backtest a set of settings with the Strategy Lab engine E: the stocks alone, the index, and the
  // mix with the index-fund core, over the whole period, before the last `hidden` months and during
  // them. Shared by the nightly script and the page, so both report the same numbers.
  function backtest(E, P, FX, opt, lastDate, hidden) {
    const o = Object.assign({}, DEFAULTS, opt || {}), H = hidden || 24;
    const r0 = E.run(P, FX, strategy(o), { lastDate });
    const f = Math.max(0, r0.held.findIndex(h => h > 0)), c = a => a.slice(f);
    const inv = c(r0.invested), stock = c(r0.rets), dates = c(r0.dates);
    const uk = E.benchRets(c(r0.bench.ftse100), inv), us = E.benchRets(c(r0.bench.sp500), inv);
    const ix = uk.map((x, k) => o.market === "LSE" ? x : o.market === "US" ? us[k] : (x == null || us[k] == null ? null : (x + us[k]) / 2));
    const rets = blend(stock, ix, o.core);
    const cut = Math.max(0, rets.length - H);
    const st = (a, d) => { const x = a.length ? E.stats(a, d) : null; return x && { cagr: x.cagr, vol: x.vol, maxDD: x.maxDD, sharpe: x.sharpe, worstYear: x.worstYear, months: x.months }; };
    const res = {
      all: st(rets, dates), index: st(ix, dates), stocks: st(stock, dates),
      dev: st(rets.slice(0, cut), dates.slice(0, cut)), indexDev: st(ix.slice(0, cut), dates.slice(0, cut)),
      hidden: st(rets.slice(cut), dates.slice(cut)), indexHidden: st(ix.slice(cut), dates.slice(cut)),
      range: E.bootstrap(rets, 1000, 11), turnoverYr: r0.turnoverYr * (1 - (o.core || 0) / 100), hiddenFrom: dates[cut] || null,
      dates, rets, indexRets: ix,
    };
    // the worst calendar year against the index
    const yrs = {};
    dates.forEach((d, k) => { const y = d.slice(0, 4); yrs[y] = yrs[y] || [1, 1]; yrs[y][0] *= 1 + (rets[k] || 0); yrs[y][1] *= 1 + (ix[k] || 0); });
    res.worstVsIndex = Math.min(...Object.values(yrs).map(([a, b]) => a - b));
    const a = res.all, i = res.index, d = res.dev, di = res.indexDev, h = res.hidden, hi = res.indexHidden;
    const beatDev = d && di && d.cagr > di.cagr, beatHid = h && hi && h.cagr > hi.cagr;
    res.verdict = beatDev && beatHid ? "beat" : beatDev || beatHid ? "mixed" : "lagged";
    res.calmer = !!(a && i && a.maxDD > i.maxDD + 0.02);
    const pc = v => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(1) + "%";
    res.summary = res.verdict === "beat" ? `Beat an index fund both before and during the last two years (${pc(a.cagr)} a year against ${pc(i.cagr)}), though not by enough to rule out luck.`
      : res.verdict === "mixed" ? `Beat an index fund in ${beatDev ? "the earlier years but not the last two" : "the last two years but not the earlier ones"}; over the whole period ${pc(a.cagr)} a year against ${pc(i.cagr)}.`
      : `Has not beaten an index fund: ${pc(a.cagr)} a year against ${pc(i.cagr)}${res.calmer ? ", though with smaller falls" : ""}.`;
    return res;
  }

  // is an index (monthly returns x1e4, return of month k in slot k) below its n-month average at month hm?
  function belowAverage(b, hm, n) {
    if (!b || hm < n) return false;
    let lvl = 1; const L = [];
    for (let k = 0; k < hm; k++) { lvl *= 1 + (b[k] == null ? 0 : b[k] / 1e4); L.push(lvl); }
    const avg = L.slice(-n).reduce((s, x) => s + x, 0) / n;
    return L[L.length - 1] < avg;
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
    // ranks across the whole market, or within each sector (sector-neutral: a stock is compared with
    // its own industry, so cheap banks don't crowd out everything else; small sectors use the market)
    let R = ranks(V, m, ids, keys);
    if (o.rankMode === "sector") {
      const bySec = {};
      ids.forEach(i => (bySec[P.sector[i] || "Other"] = bySec[P.sector[i] || "Other"] || []).push(i));
      for (const g of Object.values(bySec)) if (g.length >= 8) {
        const Rs = ranks(V, m, g, keys);
        for (const k of keys) for (const i of g) { if (Rs[k].has(i)) R[k].set(i, Rs[k].get(i)); else R[k].delete(i); }
      }
    }
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
    // index-aware construction: hold the largest eligible companies (as an index fund would) and
    // tilt their weights towards the aim's score, so the active bets are the score's, not an
    // accidental bet on smaller companies
    const capOf = i => { const c = V.val("mcapBn", m, i); return c > 0 ? c : null; };
    if (o.build === "index") order = order.slice().sort((a, b) => (capOf(b) ?? -1) - (capOf(a) ?? -1) || score.get(b) - score.get(a));
    // stocks already held stay while they rank within twice the size
    const held = ctx.held || new Set();
    if (held.size) {
      const top = new Set(order.slice(0, Math.round(o.n * (o.keep || 2))));
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
    const ivol = p => 1 / Math.max(0.08, V.val("vol1y", m, p.i) ?? 0.3);
    const caps = picks.map(p => V.val("mcapBn", m, p.i)).filter(x => x > 0).sort((a, b) => a - b), medCap = caps.length ? caps[caps.length >> 1] : 1;
    const capw = p => Math.sqrt(Math.max(0.1, V.val("mcapBn", m, p.i) || medCap)) * (0.5 + p.score);
    let raw = picks.map(p => mode === "invvol" ? ivol(p) : mode === "score" ? 0.5 + p.score : mode === "capscore" ? capw(p) : 1);
    if (o.build === "index" && picks.length) {
      const byS = picks.map((p, k) => [p.score, k]).sort((a, b) => a[0] - b[0]), pct = new Array(picks.length);
      byS.forEach(([, k], j) => pct[k] = picks.length > 1 ? j / (picks.length - 1) : 0.5);
      const tilt = o.tilt ?? 0.5;
      raw = picks.map((p, k) => (capOf(p.i) ?? medCap) * Math.max(0, 1 + tilt * (2 * pct[k] - 1)));
    }
    let tot = raw.reduce((a, b) => a + b, 0) || 1;
    let w = raw.map(x => x / tot);
    if ((mode === "erc" || mode === "minvar") && picks.length > 1) {
      const C = covariance(picks.map(p => trailing(H, hm, hidx(p.i), 36)), picks.map(p => V.val("vol1y", m, p.i)));
      w = mode === "erc" ? riskParity(C) : minVariance(C, Math.max(o.cap / 100, 1.5 / picks.length));
    }
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
    // market trend filter: when the index is below its 10-month average, hold half in cash
    let trendDown = false;
    if (o.trend) {
      const hp = (ctx.hist || V).P, bk = o.market === "LSE" ? ["ftse100"] : o.market === "US" ? ["sp500"] : ["ftse100", "sp500"];
      trendDown = bk.reduce((n, k) => n + (belowAverage(hp.bench && hp.bench[k], hm, 10) ? 1 : 0), 0) * 2 > bk.length;
      if (trendDown) w = w.map(x => x * 0.5);
    }
    return { trendDown, picks: picks.map((p, k) => ({ i: p.i, w: w[k], score: p.score })), left: left.slice(0, 12), eligible: ids.length, aim: o.aim };
  }

  // Risk report for a portfolio, as a portfolio manager would check it before committing money.
  // picks: [{ i, w }] (weights of the money in stocks); V, m: the view and month the picks come from;
  // H, hm: a view with return history and the month to look back from; hidx: V index -> H index;
  // conv(ex, k): currency multiplier for a stock on exchange ex in history month k (1 for local);
  // ix(k): the index's return in history month k (in the same currency). Uses the last 36 months.
  function riskReport(V, m, picks, H, hm, hidx, conv, ix) {
    const P = V.P, T = Math.min(36, hm), n = picks.length;
    if (!n || T < 24) return null;
    const W = picks.reduce((a, p) => a + p.w, 0) || 1, w = picks.map(p => p.w / W);
    const R = picks.map(p => { const r = trailing(H, hm, hidx(p.i), T); return r && r.map((x, j) => (1 + x) * conv(P.ex[p.i], hm - T + j) - 1); });
    const C = covariance(R, picks.map(p => V.val("vol1y", m, p.i)));
    const Cw = mv(C, w), varP = w.reduce((a, x, k) => a + x * Cw[k], 0), volP = Math.sqrt(Math.max(varP, 0) * 12);
    const contrib = w.map((x, k) => x * Cw[k] / (varP || 1));     // shares of the portfolio's variance, sum 1
    // the portfolio's own monthly history with today's weights (stocks without a full history are
    // left out and the rest scaled up), against the index
    const ok = R.map(r => !!r), wk = w.map((x, k) => ok[k] ? x : 0), sw = wk.reduce((a, b) => a + b, 0) || 1;
    const port = [], idx = [];
    for (let j = 0; j < T; j++) {
      const b = ix(hm - T + j);
      if (b == null) continue;
      port.push(R.reduce((a, r, k) => a + (r ? wk[k] / sw * r[j] : 0), 0)); idx.push(b);
    }
    let beta = null, te = null, corrIx = null, idxVol = null;
    if (port.length >= 24) {
      const mp = port.reduce((a, b) => a + b, 0) / port.length, mi = idx.reduce((a, b) => a + b, 0) / idx.length;
      let cv = 0, vi = 0, vp = 0;
      for (let j = 0; j < port.length; j++) { cv += (port[j] - mp) * (idx[j] - mi); vi += (idx[j] - mi) ** 2; vp += (port[j] - mp) ** 2; }
      beta = cv / vi; corrIx = cv / Math.sqrt(vi * vp); idxVol = Math.sqrt(vi / (idx.length - 1) * 12);
      const d = port.map((x, j) => x - idx[j]), md = d.reduce((a, b) => a + b, 0) / d.length;
      te = Math.sqrt(d.reduce((a, x) => a + (x - md) ** 2, 0) / (d.length - 1) * 12);
    }
    // risk by sector, and the holdings that add most risk compared with their share of the money
    const bySector = {};
    picks.forEach((p, k) => { const sc = P.sector[p.i] || "Other"; bySector[sc] = bySector[sc] || { money: 0, risk: 0 }; bySector[sc].money += w[k]; bySector[sc].risk += contrib[k]; });
    // exposures: the portfolio's weighted percentile on each signal among the market's stocks
    const exposures = {};
    const mk = {}; picks.forEach(p => mk[P.ex[p.i]] = 1);
    const pool = []; for (let i = 0; i < V.n; i++) if (mk[P.ex[i]] && V.member(m, i) && !V.trust(i)) pool.push(i);
    const Rk = ranks(V, m, pool, Object.keys(SIGNALS));
    for (const k of Object.keys(SIGNALS)) {
      let a = 0, b = 0;
      picks.forEach((p, j) => { if (Rk[k].has(p.i)) { a += w[j] * Rk[k].get(p.i); b += w[j]; } });
      exposures[k] = b > 0.5 ? a / b : null;
    }
    // active share against a market-value-weighted version of the same market(s)
    let active = null;
    const capOf = i => { const c = V.val("mcapBn", m, i); return c > 0 ? c : null; };
    const withCap = pool.filter(i => capOf(i) != null);
    if (withCap.length > pool.length * 0.8) {
      const exs = Object.keys(mk), bw = new Map();
      for (const e of exs) { const g = withCap.filter(i => P.ex[i] === e), t = g.reduce((a, i) => a + capOf(i), 0); g.forEach(i => bw.set(i, capOf(i) / t / exs.length)); }
      const pw = new Map(picks.map((p, k) => [p.i, w[k]]));
      let d = 0; for (const i of new Set([...bw.keys(), ...pw.keys()])) d += Math.abs((pw.get(i) || 0) - (bw.get(i) || 0));
      active = d / 2;
    }
    return { vol: volP, idxVol, beta, te, corr: corrIx, months: port.length,
      contrib: picks.map((p, k) => ({ i: p.i, w: w[k], risk: contrib[k] })),
      bySector, exposures, activeShare: active, diversified: 1 / contrib.reduce((a, x) => a + x * x, 0) };
  }

  // currency and index helpers for riskReport, from a history view H and dollars-per-pound FX
  // ([[date, rate]]): returns in pounds, the index for the market (half each for UK and US)
  function riskContext(H, FX, market) {
    const months = H.P.months, fx = k => { if (!FX || !FX.length || k < 0 || k >= months.length) return null; let lo = 0, hi = FX.length - 1, j = -1; const d = months[k]; while (lo <= hi) { const x = (lo + hi) >> 1; if (FX[x][0] <= d) { j = x; lo = x + 1; } else hi = x - 1; } return j < 0 ? FX[0][1] : FX[j][1]; };
    const conv = (ex, k) => { if (ex !== "US") return 1; const a = fx(k), b = fx(k + 1) ?? fx(k); return a && b ? a / b : 1; };
    const b = (key, k) => { const r = H.P.bench && H.P.bench[key] && H.P.bench[key][k]; return r == null ? null : r / 1e4; };
    const ix = k => {
      const uk = b("ftse100", k), us = b("sp500", k), usg = us == null ? null : (1 + us) * conv("US", k) - 1;
      return market === "LSE" ? uk : market === "US" ? usg : uk == null || usg == null ? null : (uk + usg) / 2;
    };
    return { conv, ix };
  }

  // Tonight's portfolio for a set of settings, with reasons, warnings and the risk report. E: the
  // Lab engine; P: the history panel; D: tonight's snapshot; extra: id -> { prob6, tone30 };
  // flags(s): warnings for a snapshot stock (models-core.js). Shared by the nightly script and the page.
  function livePortfolio(E, P, D, opt, extra, FX, flags) {
    const o = Object.assign({}, DEFAULTS, opt || {});
    const S0 = E.snapshotPanel(D), V0 = E.makeView(S0), H = E.makeView(P), hm = P.months.length;
    const by = Object.fromEntries(D.stocks.map(s => [s.id, s]));
    const names = Object.fromEntries(D.stocks.map(s => [s.id, s.name]));
    const res = choose(V0, 0, o, { hist: H, hm, names, extra });
    const r4 = x => x == null || !isFinite(x) ? null : Math.round(x * 1e4) / 1e4;
    const pick = p => { const s = by[S0.ids[p.i]]; return { id: s.id, name: s.name, t: s.t, ex: s.ex, sector: s.sector, ccy: s.ccy, price: s.price, w: r4(p.w), score: s.score, prob6: s.prob6 ?? null,
      mcapBn: s.mcapBn ?? null, divY: r4(s.div ? s.div.yld : s.divY), vol1y: r4(s.vol1y), ret1y: r4(s.ret1y), reasons: why(s, o.aim), flags: flags ? flags(s) : [] }; };
    const ctx = riskContext(H, FX, o.market);
    const rr = riskReport(V0, 0, res.picks, H, hm, i => H.idx.get(S0.ids[i]), ctx.conv, ctx.ix);
    const risk = rr && { vol: r4(rr.vol), idxVol: r4(rr.idxVol), beta: rr.beta == null ? null : Math.round(rr.beta * 100) / 100, te: r4(rr.te), corr: r4(rr.corr), months: rr.months,
      activeShare: r4(rr.activeShare), diversified: Math.round(rr.diversified * 10) / 10,
      contrib: Object.fromEntries(rr.contrib.map(c => [S0.ids[c.i], r4(c.risk)])),
      bySector: Object.fromEntries(Object.entries(rr.bySector).map(([k, v]) => [k, { money: r4(v.money), risk: r4(v.risk) }])),
      exposures: Object.fromEntries(Object.entries(rr.exposures).map(([k, v]) => [k, r4(v)])) };
    return { picks: res.picks.map(pick), left: res.left.map(l => ({ id: S0.ids[l.i], name: names[S0.ids[l.i]], reason: l.reason })), eligible: res.eligible, trendDown: res.trendDown, risk };
  }

  // A random portfolio of the same size from the same eligible stocks, drawn afresh at each
  // rebalance (seeded): the null hypothesis that the ranking adds nothing. Comparing the real picks
  // with many of these shows whether the selection itself has skill, apart from the market.
  function randomStrategy(opt, seed) {
    const o = Object.assign({}, DEFAULTS, opt || {});
    let s = (seed >>> 0) % 2147483646 + 1;
    const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    return Object.assign(strategy(o), {
      select(V, m) {
        const res = choose(V, m, Object.assign({}, o, { n: 100000, sectorCap: 100, cap: 100, maxCorr: 1, weighting: "equal", build: "" }), {});
        const ids = res.picks.map(p => p.i);
        for (let j = ids.length - 1; j > 0; j--) { const k = Math.floor(rnd() * (j + 1)); [ids[j], ids[k]] = [ids[k], ids[j]]; }
        const pick = ids.slice(0, o.n);
        return new Map(pick.map(i => [i, 1 / pick.length]));
      },
    });
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

  const api = { AIMS, SIGNALS, DEFAULTS, FUNDS, riskReport, riskContext, livePortfolio, randomStrategy, blend, signalRecord, backtest, choose, strategy, shares, why, corr, company, covariance, riskParity, minVariance };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.GeneratorCore = api;
})(typeof window !== "undefined" ? window : globalThis);
