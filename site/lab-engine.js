// BullPulse Strategy Lab: the backtest engine. Pure functions over the month-end history panel
// (data/panel.json), so the same code runs in the browser and in tests (node).
//
// A strategy picks stocks at each month-end using only what was known then, weights them, trades
// with costs, optional capital-gains tax and currency conversion, and holds them for a month.
(function (root) {
  "use strict";

  // Screen fields stored as fractions in the panel but entered as percentages in rules
  const PCT = new Set(["ret1y", "mom", "d200", "hi52", "vol1y", "revGrowth", "epsGrowth", "divY", "fcfY", "roe", "de", "fairVs", "implied", "rev1m"]);
  const ALIAS = { insb: "insB" };

  function makeView(P) {
    const nM = P.months.length, n = P.ids.length;
    const idx = new Map(P.ids.map((id, i) => [id, i]));
    const val = (k, m, i) => {
      k = ALIAS[k] || k;
      const r = P.fields[k] && P.fields[k][m];
      const x = r ? r[i] : null;
      return x == null ? null : x / ((P.scale && P.scale[k]) || 1);
    };
    const fwd = (m, i) => (P.fwd[m] && P.fwd[m][i] != null ? P.fwd[m][i] / 1e4 : null);
    const member = (m, i) => !P.fields.mem || P.fields.mem[m][i] == null || P.fields.mem[m][i] > 0;
    const trust = i => !!(P.trust && P.trust[i]);
    return { P, nM, n, idx, val, fwd, member, trust };
  }

  // dollars per pound on or before a date
  function fxAt(FX, date) {
    if (!FX || !FX.length) return null;
    let lo = 0, hi = FX.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (FX[m][0] <= date) { k = m; lo = m + 1; } else hi = m - 1; }
    return k < 0 ? FX[0][1] : FX[k][1];
  }

  // value of the rule's field for stock i at month m, in the units people type (percent fields x100)
  function ruleValue(V, f, m, i) {
    let v = V.val(f, m, i);
    if (v == null) return null;
    return PCT.has(f) ? v * 100 : v;
  }
  function passes(V, rules, m, i) {
    for (const [f, op, a, b] of rules || []) {
      const v = ruleValue(V, f, m, i);
      if (v == null) return false;
      if (op === ">=" && a !== "" && a != null && v < +a) return false;
      if (op === "<=" && a !== "" && a != null && v > +a) return false;
      if (op === "between" && ((a !== "" && a != null && v < +a) || (b !== "" && b != null && v > +b))) return false;
    }
    return true;
  }
  // ranking blend: trend, momentum, growth, fundamentals (of 30 -> 0..100), value (cheapness percentile)
  function blend(V, w, m, i) {
    const c = { T: V.val("T", m, i), M: V.val("M", m, i), G: V.val("G", m, i), F: V.val("FP", m, i) == null ? null : V.val("FP", m, i) / 30 * 100, V: V.val("Vp", m, i) };
    let s = 0, d = 0;
    for (const k in c) if ((w[k] || 0) > 0 && c[k] != null) { s += w[k] * c[k]; d += w[k]; }
    return d ? s / d : (V.val("score", m, i) ?? 0);
  }

  // stocks and target weights at month-end m (sum <= 1; the rest is cash)
  function targets(V, S, m, held) {
    // a strategy can bring its own stock-picker (the portfolio generator does): Map(i -> weight)
    if (typeof S.select === "function") return S.select(V, m, held);
    let ids = [];
    const src = S.source || {};
    if (src.type === "list") {
      for (const id of src.ids || []) {
        const i = V.idx.get(id);
        if (i != null && V.val("T", m, i) != null) ids.push(i);
      }
    } else {
      const mk = src.market || "ALL";
      for (let i = 0; i < V.n; i++) {
        if (mk !== "ALL" && V.P.ex[i] !== mk) continue;
        if (src.idx && V.P.idx && V.P.idx[i] !== src.idx) continue;
        if (src.sector && V.P.sector[i] !== src.sector) continue;
        if (src.noTrusts && V.trust(i)) continue;
        if (!V.member(m, i) || V.val("T", m, i) == null) continue;
        if (!passes(V, src.rules, m, i)) continue;
        ids.push(i);
      }
      const w = src.w || { T: 50, M: 50 };
      const sc = new Map(ids.map(i => [i, blend(V, w, m, i)]));
      ids.sort((a, b) => sc.get(b) - sc.get(a));
      if (src.top > 0) {
        // a buffer cuts needless trading: a stock already held stays while it ranks within `keep`
        if (src.keep > src.top && held && held.size) {
          const stay = ids.slice(0, src.keep).filter(i => held.has(i)).slice(0, src.top);
          const fill = ids.filter(i => !stay.includes(i)).slice(0, src.top - stay.length);
          ids = stay.concat(fill);
        } else ids = ids.slice(0, src.top);
      }
    }
    // exit rule: no stock below its 200-day average
    let cashShare = 0;
    if (S.exit200) {
      const kept = ids.filter(i => { const d = V.val("d200", m, i); return d == null || d >= 0; });
      if (S.exitTo === "cash" && ids.length) cashShare = (ids.length - kept.length) / ids.length;
      ids = kept;
    }
    if (!ids.length) return new Map();
    // weights
    let raw;
    if (S.weighting === "score") raw = ids.map(i => Math.max(1, V.val("score", m, i) ?? 50));
    else if (S.weighting === "invvol") raw = ids.map(i => 1 / Math.max(0.08, V.val("vol1y", m, i) ?? 0.3));
    else if (S.weighting === "custom" && src.type === "list") raw = ids.map(i => Math.max(0, +((src.w || {})[V.P.ids[i]] ?? 0)));
    else raw = ids.map(() => 1);
    let tot = raw.reduce((a, b) => a + b, 0);
    if (!(tot > 0)) { raw = ids.map(() => 1); tot = ids.length; }
    let w = raw.map(x => x / tot);
    // cap any single holding, spreading the excess over the rest
    const cap = S.cap > 0 ? S.cap / 100 : 1;
    if (cap < 1 && cap * ids.length >= 1) {
      for (let it = 0; it < 20; it++) {
        let excess = 0, free = 0;
        w = w.map(x => { if (x > cap) { excess += x - cap; return cap; } free += x < cap ? x : 0; return x; });
        if (excess < 1e-9) break;
        w = w.map(x => (x < cap && free > 0 ? x + excess * x / free : x));
      }
    }
    const scale = 1 - cashShare;
    return new Map(ids.map((i, k) => [i, w[k] * scale]));
  }

  function isRebalance(S, m, m0, date) {
    if (m === m0) return true;
    const mo = +date.slice(5, 7);
    switch (S.rebalance) {
      case "M": return true;
      case "Q": return mo % 3 === 0;
      case "Y": return mo === 12;
      case "never": return false;
      default: return false; // "drift": decided by drift
    }
  }

  // UK tax on a general account, by tax year (the year starting 6 April; 2024 = 2024/25).
  // Capital gains: annual exempt amount and the rate on shares by band (basic, higher; additional
  // rate taxpayers pay the higher rate). 2010/11 uses the rates from 23 June 2010 for the whole
  // year; 2024/25 changes on 30 October 2024 and is applied by the date of each sale.
  const CGT_ALLOW = { 2008: 9600, 2009: 10100, 2010: 10100, 2011: 10600, 2012: 10600, 2013: 10900, 2014: 11000, 2015: 11100,
    2016: 11100, 2017: 11300, 2018: 11700, 2019: 12000, 2020: 12300, 2021: 12300, 2022: 12300, 2023: 6000, 2024: 3000 };
  function cgtRate(date, band) {
    const hi = band !== "basic";
    if (date < "2010-06-23") return 0.18;
    if (date < "2016-04-06") return hi ? 0.28 : 0.18;
    if (date < "2024-10-30") return hi ? 0.20 : 0.10;
    return hi ? 0.24 : 0.18;
  }
  // Dividends: allowance and rates on the cash dividend. Before April 2016 the tax credit left
  // basic-rate taxpayers nothing to pay and higher and additional rates 25% and 30.56% (36.11%
  // in 2010/11 to 2012/13, when the additional rate was 50%) of the cash dividend.
  const DIV_ALLOW = { 2016: 5000, 2017: 5000, 2018: 2000, 2019: 2000, 2020: 2000, 2021: 2000, 2022: 2000, 2023: 1000, 2024: 500 };
  function divRate(y, band) {
    const k = band === "basic" ? 0 : band === "additional" ? 2 : 1;
    if (y < 2016) return [0, 0.25, y >= 2010 && y <= 2012 ? 0.3611 : y >= 2013 ? 0.3056 : 0.25][k];
    if (y < 2022) return [0.075, 0.325, 0.381][k];
    if (y < 2026) return [0.0875, 0.3375, 0.3935][k];
    return [0.1075, 0.3575, 0.3935][k];
  }
  const taxYear = d => { const y = +d.slice(0, 4); return d.slice(5, 10) < "04-06" ? y - 1 : y; };
  const fromTable = (t, y) => { const ks = Object.keys(t).map(Number).sort((a, b) => a - b); let v = t[ks[0]]; for (const k of ks) if (k <= y) v = t[k]; return v; };
  // US dividends paid to a UK investor lose 15% at source (the treaty rate, with a W-8BEN form), in
  // an ISA or SIPP as well; on a general account it counts against the UK tax on them.
  const US_WHT = 0.15;

  // Run a strategy. Returns month-end values, time-weighted monthly returns, the benchmarks run
  // with the same money in, and a record of trades, costs and tax.
  function run(P, FX, S, opt) {
    const V = makeView(P);
    opt = opt || {};
    const months = P.months;
    let m0 = 0;
    if (S.from) while (m0 < V.nM - 1 && months[m0].slice(0, 7) < S.from) m0++;
    const ccy = S.ccy || "GBP";
    const lastDate = opt.lastDate || months[V.nM - 1];
    const dateAt = m => (m < V.nM ? months[m] : lastDate);
    const fx = m => fxAt(FX, dateAt(m));
    // currency factor for holding stock i (or an index on exchange ex) from month m to m+1
    const conv = (ex, m) => {
      if (ccy === "local") return 1;
      const a = fx(m), b = fx(m + 1);
      if (!a || !b) return 1;
      if (ccy === "GBP" && ex === "US") return a / b;
      if (ccy === "USD" && ex === "LSE") return b / a;
      return 1;
    };
    const toBase = (gbp, m) => (ccy === "USD" ? gbp * (fx(m) || 1.3) : gbp); // pound amounts (allowances) in the base currency
    const c = Object.assign({ commission: 0.1, spread: 0.1, stamp: true, fxFee: 0.5 }, S.costs || {});
    const pos = new Map(); // i -> { v: value, b: cost basis }
    let cash = 0, invested = 0, costs = 0, tax = 0, gains = 0, turnover = 0, missing = 0;
    // tax state: gains weighted by the rate at the date of sale, losses carried forward, the tax
    // year's dividends (and US tax already withheld), and how many holding-months had a known yield
    const band = S.taxBand || "higher";
    let gainsRated = 0, lossCarry = 0, divs = 0, divUS = 0, wht = 0, whtYear = 0, taxCGT = 0, taxDiv = 0, divKnown = 0, divAll = 0;
    const realise = (g, date) => { gains += g; gainsRated += g * cgtRate(date, band); };
    const out = { dates: [], values: [], invested: [], rets: [], cash: [], held: [], trades: 0, months: [] };
    let prevSet = null, prevAfter = 0;
    const benches = { ftse100: { v: 0 }, sp500: { v: 0 }, avg: { v: 0 } };
    const bOut = { ftse100: [], sp500: [], avg: [] };
    const benchRet = (k, m) => (P.bench && P.bench[k] && P.bench[k][m] != null ? P.bench[k][m] / 1e4 : null);
    const mk = (S.source && S.source.market) || "ALL";
    const avgRet = m => {
      let s = 0, n = 0;
      for (let i = 0; i < V.n; i++) {
        if ((mk !== "ALL" && P.ex[i] !== mk) || !V.member(m, i)) continue;
        const r = V.fwd(m, i);
        if (r == null || Math.abs(r) > 2) continue;
        s += (1 + r) * conv(P.ex[i], m) - 1;
        n++;
      }
      return n ? s / n : 0;
    };
    const tradeCost = (i, amount, buy) => {
      let x = Math.abs(amount) * (c.commission + c.spread) / 100;
      if (buy && c.stamp && P.ex[i] === "LSE") x += amount * 0.005;
      if ((ccy === "GBP" && P.ex[i] === "US") || (ccy === "USD" && P.ex[i] === "LSE")) x += Math.abs(amount) * c.fxFee / 100;
      return x;
    };
    for (let m = m0; m < V.nM; m++) {
      const date = dateAt(m);
      // money in
      const add = m === m0 ? (+S.start || 0) : (+S.monthly || 0);
      cash += add; invested += add;
      for (const k in benches) benches[k].v += add;
      const T = targets(V, S, m, pos);
      const total = cash + [...pos.values()].reduce((a, p) => a + p.v, 0);
      let reb = isRebalance(S, m, m0, date);
      const setNow = [...T.keys()].sort().join(",");
      // between scheduled rebalances a rule strategy still swaps names that leave the list for
      // names that join it, without resetting everything else
      // (S.swaps === false: trade only on scheduled rebalances, as a slow model portfolio would)
      const swap = !reb && S.swaps !== false && S.source && S.source.type !== "list" && prevSet !== null && setNow !== prevSet;
      if (!reb && S.rebalance === "drift" && total > 0) {
        for (const [i, w] of T) if (Math.abs((pos.get(i)?.v || 0) / total - w) > (S.drift || 5) / 100) reb = true;
        for (const i of pos.keys()) if (!T.has(i)) reb = true;
      }
      if (S.rebalance === "never" && m !== m0) {
        // buy-and-hold: new money goes to the original targets in proportion; nothing is sold
        reb = false;
      }
      let spent = 0;
      if (reb && total > 0) {
        const want = new Map([...T].map(([i, w]) => [i, w * total]));
        for (const [i, p] of pos) if (!want.has(i)) want.set(i, 0);
        for (const [i, target] of want) {
          const p = pos.get(i) || { v: 0, b: 0 };
          const d = target - p.v;
          if (Math.abs(d) < total * 1e-6) continue;
          const cst = tradeCost(i, d, d > 0);
          spent += cst; turnover += Math.abs(d); out.trades++;
          if (d < 0) { const f = -d / p.v; realise(f * (p.v - p.b), date); p.b *= 1 - f; } else p.b += d;
          p.v = target;
          if (p.v <= 1e-9) pos.delete(i); else pos.set(i, p);
        }
        cash = total - [...pos.values()].reduce((a, p) => a + p.v, 0);
        // pay the costs out of the holdings pro rata (cash first)
        let left = spent;
        const fromCash = Math.min(Math.max(cash, 0), left); cash -= fromCash; left -= fromCash;
        if (left > 0) { const hv = [...pos.values()].reduce((a, p) => a + p.v, 0); for (const p of pos.values()) p.v -= left * p.v / hv; }
      } else if (swap) {
        for (const [i, p] of [...pos]) {
          if (T.has(i)) continue;
          const cst = tradeCost(i, -p.v, false);
          realise(p.v - p.b, date); cash += p.v - cst; spent += cst; turnover += p.v; out.trades++;
          pos.delete(i);
        }
        const fresh = [...T].filter(([i]) => !pos.has(i));
        const fw = fresh.reduce((a, [, w]) => a + w, 0);
        if (fw > 0 && cash > 0) {
          const budget = cash;
          for (const [i, w] of fresh) {
            const amt = budget * w / fw;
            const cst = tradeCost(i, amt, true);
            pos.set(i, { v: amt - cst, b: amt });
            spent += cst; turnover += amt; out.trades++;
          }
          cash -= budget;
        }
      } else if (cash > 0 && T.size) {
        // invest new money in line with the targets, without selling anything
        const tw = [...T.values()].reduce((a, b) => a + b, 0);
        const budget = cash * tw;
        for (const [i, w] of T) {
          const amt = budget * w / tw;
          const cst = tradeCost(i, amt, true);
          const p = pos.get(i) || { v: 0, b: 0 };
          p.v += amt - cst; p.b += amt; pos.set(i, p);
          spent += cst; turnover += amt; out.trades++;
        }
        cash -= budget;
      }
      costs += spent;
      prevSet = setNow;
      // tax at the end of each UK tax year (March): capital gains above the allowance (after any
      // losses brought forward), and dividends above the dividend allowance
      if (S.account === "gia" && date.slice(5, 7) === "03") {
        const y = taxYear(date);
        let due = 0;
        if (gains < 0) lossCarry -= gains;
        else {
          const over = Math.max(0, gains - toBase(fromTable(CGT_ALLOW, y), m)), use = Math.min(lossCarry, over);
          lossCarry -= use;
          const cg = gains > 0 ? (over - use) * (gainsRated / gains) : 0;
          taxCGT += cg; due += cg;
        }
        const allow = y >= 2016 ? toBase(fromTable(DIV_ALLOW, y), m) : 0, rate = divRate(y, band);
        const taxable = Math.max(0, divs - allow);
        // the UK tax on the US part, less what was withheld (never below nothing)
        const onUS = taxable * (divs > 0 ? divUS / divs : 0) * rate;
        const dt = Math.max(0, taxable * rate - Math.min(onUS, whtYear));
        taxDiv += dt; due += dt;
        if (due > 0) {
          tax += due;
          const hv = [...pos.values()].reduce((a, p) => a + p.v, 0) + cash;
          const k = Math.max(0, 1 - due / Math.max(hv, 1e-9));
          for (const p of pos.values()) p.v *= k;
          cash *= k;
        }
        gains = 0; gainsRated = 0; divs = 0; divUS = 0; whtYear = 0;
      }
      out.held.push(pos.size);
      // this month's dividends (prices include them, reinvested): a twelfth of the yield, from the
      // company's figures, else the median of its market that month; US tax withheld at source
      if (pos.size && (S.account === "gia" || P.ex.some(e => e === "US"))) {
        const med = {};
        for (const ex of ["US", "LSE"]) {
          const ys = [];
          for (let i = 0; i < V.n; i++) if (P.ex[i] === ex && V.member(m, i)) { const v = V.val("divY", m, i); if (v != null && v >= 0 && v < 0.3) ys.push(v); }
          ys.sort((a, b) => a - b);
          med[ex] = ys.length >= 20 ? ys[ys.length >> 1] : null;
        }
        for (const [i, p] of pos) {
          let y = V.val("divY", m, i);
          divAll++;
          if (y != null && y >= 0 && y < 0.3) divKnown++;
          else y = med[P.ex[i]];
          if (y == null) continue;
          const d = p.v * y / 12;
          if (P.ex[i] === "US") { const w = d * US_WHT; p.v -= w; wht += w; whtYear += w; divUS += d; }
          divs += d;
        }
      }
      // a month passes (the last row runs only to the latest close)
      for (const [i, p] of pos) {
        const r = V.fwd(m, i);
        if (r == null) { missing++; continue; } // no price that month: held at its value
        p.v *= (1 + r) * conv(P.ex[i], m);
      }
      const after = cash + [...pos.values()].reduce((a, p) => a + p.v, 0);
      // time-weighted: against last month's value plus the money added, so costs and tax count
      out.rets.push(prevAfter + add > 0 ? after / (prevAfter + add) - 1 : 0);
      prevAfter = after;
      out.dates.push(m + 1 < V.nM ? months[m + 1] : lastDate);
      out.months.push(months[m]);
      out.values.push(after);
      out.invested.push(invested);
      out.cash.push(cash);
      // benchmarks with the same money in
      for (const k of ["ftse100", "sp500"]) {
        const r = benchRet(k, m);
        if (r != null) benches[k].v *= (1 + r) * conv(k === "ftse100" ? "LSE" : "US", m);
        bOut[k].push(r == null ? null : benches[k].v);
      }
      benches.avg.v *= 1 + avgRet(m);
      bOut.avg.push(benches.avg.v);
    }
    out.bench = bOut;
    out.costs = costs; out.tax = tax; out.missing = missing;
    out.taxCGT = taxCGT; out.taxDiv = taxDiv; out.wht = wht; out.lossCarry = lossCarry;
    out.divCover = divAll ? divKnown / divAll : null; // share of holding-months with the company's own yield
    const avgVal = out.values.reduce((a, b) => a + b, 0) / Math.max(1, out.values.length);
    out.turnoverYr = out.values.length ? turnover / avgVal / (out.values.length / 12) : 0;
    out.final = out.values[out.values.length - 1] || 0;
    out.ccy = ccy;
    return out;
  }

  // time-weighted monthly returns of a value path that receives the same money each month
  function benchRets(values, invested) {
    const r = [];
    let prev = 0;
    for (let k = 0; k < values.length; k++) {
      const add = invested[k] - (k ? invested[k - 1] : 0);
      if (values[k] == null) { r.push(null); continue; }
      const base = prev + add;
      r.push(base > 0 ? values[k] / base - 1 : null);
      prev = values[k];
    }
    return r;
  }

  function stats(rets, dates) {
    const r = rets.filter(x => x != null);
    if (r.length < 3) return null;
    const n = r.length, yrs = n / 12;
    let g = 1, peak = 1, peakAt = 0, dd = 0, longest = 0;
    r.forEach((x, k) => {
      g *= 1 + x;
      if (g >= peak) { longest = Math.max(longest, k + 1 - peakAt - 1); peak = g; peakAt = k + 1; }
      dd = Math.min(dd, g / peak - 1);
    });
    longest = Math.max(longest, n - peakAt); // still below the last high
    const cagr = Math.pow(g, 1 / yrs) - 1;
    const mean = r.reduce((a, b) => a + b, 0) / n;
    const sd = Math.sqrt(r.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1));
    const down = Math.sqrt(r.reduce((a, b) => a + Math.min(0, b) ** 2, 0) / n);
    const years = {};
    if (dates) rets.forEach((x, k) => { if (x == null) return; const y = dates[k].slice(0, 4); years[y] = (years[y] ?? 1) * (1 + x); });
    const yv = Object.values(years).map(v => v - 1);
    const roll = [];
    for (let k = 36; k <= r.length; k++) { let p = 1; for (let j = k - 36; j < k; j++) p *= 1 + r[j]; roll.push(Math.pow(p, 1 / 3) - 1); }
    return {
      months: n, total: g - 1, cagr, vol: sd * Math.sqrt(12),
      sharpe: sd > 0 ? (mean * 12) / (sd * Math.sqrt(12)) : null,
      sortino: down > 0 ? (mean * 12) / (down * Math.sqrt(12)) : null,
      maxDD: dd, longestUnderwater: longest,
      positive: r.filter(x => x > 0).length / n,
      bestYear: yv.length ? Math.max(...yv) : null, worstYear: yv.length ? Math.min(...yv) : null, years,
      roll3min: roll.length ? Math.min(...roll) : null, roll3max: roll.length ? Math.max(...roll) : null,
    };
  }

  // a range of outcomes: resample whole 12-month blocks of the strategy's own history
  function bootstrap(rets, sims, seed) {
    const r = rets.filter(x => x != null);
    if (r.length < 24) return null;
    let s = seed || 12345;
    const rnd = () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648);
    const n = r.length, block = 12, out = [];
    let loss5 = 0;
    for (let k = 0; k < (sims || 1000); k++) {
      let g = 1, j = 0, g5 = null;
      while (j < n) {
        const st = Math.floor(rnd() * (n - block + 1));
        for (let b = 0; b < block && j < n; b++, j++) { g *= 1 + r[st + b]; if (j === 59) g5 = g; }
      }
      out.push(Math.pow(g, 12 / n) - 1);
      if (g5 != null && g5 < 1) loss5++;
    }
    out.sort((a, b) => a - b);
    const q = p => out[Math.min(out.length - 1, Math.floor(p * out.length))];
    return { p5: q(0.05), p25: q(0.25), p50: q(0.5), p75: q(0.75), p95: q(0.95), lossAfter5: n >= 60 ? loss5 / out.length : null };
  }

  // History for measures the month-end panel doesn't store, rebuilt from its own monthly total
  // returns using only what was known at each date: 12-month return, momentum (12 months leaving
  // out the last), volatility (12 months) and price against its 10-month average (the usual
  // monthly stand-in for the 200-day average). Fields the panel already has are left alone.
  function augment(P) {
    if (!P || !P.fwd || P._augmented) return P;
    const nM = P.months.length, n = P.ids.length;
    const want = ["ret1y", "mom", "vol1y", "d200"].filter(k => !(P.fields && P.fields[k]));
    if (!want.length) { P._augmented = true; return P; }
    const F = {}; want.forEach(k => F[k] = Array.from({ length: nM }, () => new Array(n).fill(null)));
    for (let i = 0; i < n; i++) {
      const px = [1], r = [];
      for (let m = 0; m < nM; m++) {
        const x = P.fwd[m] && P.fwd[m][i] != null ? P.fwd[m][i] / 1e4 : null;
        r.push(x);
        px.push(x == null || px[m] == null ? null : px[m] * (1 + x));
      }
      for (let m = 12; m < nM; m++) {
        const p0 = px[m - 12], p1 = px[m - 1], p = px[m];
        if (F.ret1y && p != null && p0) F.ret1y[m][i] = p / p0 - 1;
        if (F.mom && p1 != null && p0) F.mom[m][i] = p1 / p0 - 1;
        if (F.vol1y) {
          const w = r.slice(m - 12, m);
          if (w.every(v => v != null)) { const mu = w.reduce((a, b) => a + b, 0) / 12; F.vol1y[m][i] = Math.sqrt(w.reduce((a, b) => a + (b - mu) ** 2, 0) / 11 * 12); }
        }
        if (F.d200 && p != null) {
          const w = px.slice(m - 9, m + 1);
          if (w.every(v => v != null)) F.d200[m][i] = p / (w.reduce((a, b) => a + b, 0) / 10) - 1;
        }
      }
    }
    P.fields = Object.assign({}, P.fields, F);
    P.scale = Object.assign({}, P.scale); want.forEach(k => P.scale[k] = 1);
    P._augmented = true;
    return P;
  }

  // Tonight's figures as a one-month panel, so live portfolios are picked by the same code as the
  // backtests (targets(makeView(snapshotPanel(D)), S, 0, held)).
  function snapshotPanel(D) {
    const st = D.stocks, ids = st.map(s => s.id);
    const f = fn => [st.map(fn)];
    const cheap = {};
    for (const ex of ["LSE", "US"]) {
      const xs = st.filter(s => s.ex === ex && s.fairVs != null).map(s => s.fairVs).sort((a, b) => b - a);
      st.filter(s => s.ex === ex && s.fairVs != null).forEach(s => { cheap[s.id] = xs.length > 1 ? xs.indexOf(s.fairVs) / (xs.length - 1) * 100 : 50; });
    }
    return {
      months: [D.asof], ids, ex: st.map(s => s.ex === "LSE" ? "LSE" : "US"), sector: st.map(s => s.sector), idx: st.map(s => s.idx || ""), trust: st.map(s => s.trust ? 1 : 0), scale: {},
      fields: {
        score: f(s => (s.T + s.M) / 2), T: f(s => s.T), M: f(s => s.M), G: f(s => s.G ?? null), FP: f(s => s.FP ?? null), Vp: f(s => cheap[s.id] ?? null),
        d200: f(s => s.sma200 ? s.price / s.sma200 - 1 : null), ret1y: f(s => s.ret1y), mom: f(s => s.mom), hi52: f(s => s.hi52 ? s.price / s.hi52 - 1 : null),
        vol1y: f(s => s.vol1y), rsi: f(s => s.rsi), revGrowth: f(s => s.revGrowth ?? null), epsGrowth: f(s => s.epsGrowth ?? null), pe: f(s => s.pe ?? null),
        divY: f(s => s.div ? s.div.yld : s.divY ?? null), fcfY: f(s => s.fcfY ?? null), roe: f(s => s.roe ?? null), de: f(s => s.de ?? null), fairVs: f(s => s.fairVs ?? null),
        mcapBn: f(s => s.mcapBn ?? null), insB: f(s => s.ex === "US" ? (s.ins ? s.ins.buyers : 0) : null), sue: f(s => s.sue ?? null), rev1m: f(() => null),
      },
      fwd: [st.map(() => null)], bench: {},
    };
  }

  // a stable key for a strategy (for the hidden final period and version counting)
  function key(S) {
    const c = JSON.parse(JSON.stringify(S));
    delete c.name; delete c.start; delete c.monthly; delete c.ccy;
    return JSON.stringify(c);
  }

  // Factor check: regress a portfolio's monthly returns above the risk-free rate on the Fama-French
  // factors (F: one set from factors.json; months YYYY-MM). rets[k] is the return over the month
  // ending dates[k]; usd(k) converts it to dollars, the factors' currency (identity if already).
  // model "ff3": market, size, value; "ff5m": the five factors and momentum (Carhart). Returns
  // alpha a year with its Newey-West t (3 lags) and 95% interval, the loadings, R-squared and
  // months used; null with fewer than 36 matched months.
  const FACTOR_NAMES = { mkt: "Market", smb: "Size (small minus big)", hml: "Value (high minus low book-to-market)", rmw: "Profitability (robust minus weak)", cma: "Investment (conservative minus aggressive)", mom: "Momentum" };
  function factorRegression(rets, dates, F, model, usd) {
    if (!F || !F.months) return null;
    const keys = model === "ff3" ? ["mkt", "smb", "hml"] : ["mkt", "smb", "hml", "rmw", "cma", "mom"];
    const at = new Map(F.months.map((m, k) => [m, k]));
    const X = [], y = [], used = [];
    rets.forEach((r, k) => {
      const d = dates[k]; if (r == null || !d) return;
      const j = at.get(d.slice(0, 7)); if (j == null) return;
      // a return dated in the middle of a month is the partial last month: left out
      if (k === rets.length - 1 && +d.slice(8, 10) < 25) return;
      const ru = usd ? usd(k, r) : r;
      if (ru == null || !isFinite(ru)) return;
      X.push([1, ...keys.map(f => F[f][j])]); y.push(ru - F.rf[j]); used.push(d.slice(0, 7));
    });
    const n = y.length, p = keys.length + 1;
    if (n < 36) return null;
    // OLS by the normal equations
    const XtX = Array.from({ length: p }, () => new Array(p).fill(0)), Xty = new Array(p).fill(0);
    for (let k = 0; k < n; k++) for (let a = 0; a < p; a++) { Xty[a] += X[k][a] * y[k]; for (let b = 0; b < p; b++) XtX[a][b] += X[k][a] * X[k][b]; }
    const inv = invert(XtX); if (!inv) return null;
    const beta = inv.map(row => row.reduce((s, v, b) => s + v * Xty[b], 0));
    const e = y.map((v, k) => v - X[k].reduce((s, x, a) => s + x * beta[a], 0));
    const ym = y.reduce((a, b) => a + b, 0) / n, sst = y.reduce((a, v) => a + (v - ym) ** 2, 0), sse = e.reduce((a, v) => a + v * v, 0);
    // Newey-West covariance of the coefficients, 3 lags
    const L = 3, S = Array.from({ length: p }, () => new Array(p).fill(0));
    for (let lag = 0; lag <= L; lag++) {
      const w = lag === 0 ? 1 : 1 - lag / (L + 1);
      for (let k = lag; k < n; k++) for (let a = 0; a < p; a++) for (let b = 0; b < p; b++) {
        const v = w * e[k] * e[k - lag] * X[k][a] * X[k - lag][b];
        S[a][b] += v; if (lag > 0) S[b][a] += v;
      }
    }
    const mul = (A, B) => A.map(r => B[0].map((_, j) => r.reduce((s, v, k) => s + v * B[k][j], 0)));
    const V = mul(mul(inv, S), inv).map(r => r.map(v => v * n / (n - p)));
    const se = V.map((r, a) => Math.sqrt(Math.max(0, r[a])));
    return {
      model, months: n, from: used[0], to: used[n - 1],
      alpha: beta[0] * 12, alphaT: se[0] > 0 ? beta[0] / se[0] : null, alphaLo: (beta[0] - 1.96 * se[0]) * 12, alphaHi: (beta[0] + 1.96 * se[0]) * 12,
      loadings: keys.map((f, a) => ({ key: f, name: FACTOR_NAMES[f], beta: beta[a + 1], t: se[a + 1] > 0 ? beta[a + 1] / se[a + 1] : null })),
      r2: sst > 0 ? 1 - sse / sst : null,
    };
  }
  function invert(A) {
    const n = A.length, M = A.map((r, i) => [...r, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
    for (let c = 0; c < n; c++) {
      let piv = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
      if (Math.abs(M[piv][c]) < 1e-14) return null;
      [M[c], M[piv]] = [M[piv], M[c]];
      const d = M[c][c]; for (let j = 0; j < 2 * n; j++) M[c][j] /= d;
      for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c]; if (f) for (let j = 0; j < 2 * n; j++) M[r][j] -= f * M[c][j]; }
    }
    return M.map(r => r.slice(n));
  }

  const api = { run, stats, bootstrap, targets, makeView, benchRets, key, fxAt, PCT, augment, snapshotPanel, factorRegression };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.LabEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
