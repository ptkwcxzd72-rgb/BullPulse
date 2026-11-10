// Signal study: how well each signal has ranked later returns, measured the way a quant team would.
//
// For each month and market, the information coefficient (IC) is the rank correlation between a
// signal and the following h months' returns among index members (trusts left out). Both sides are
// neutralised: signal ranks are taken within sectors, and returns are measured against the average
// of the stock's sector and size group (thirds by market value), so a signal isn't credited for
// favouring banks or small companies. t-statistics use Newey-West standard errors with h-1 lags,
// since h-month windows overlap.
//
// Decision rule (fixed in November 2026, before the candidates' results were seen): a signal enters
// the alpha model if it has the expected sign with t >= 2 at its natural horizon over the whole
// period AND the same sign in both halves; signals without a long published record need t >= 3.
// Every candidate here has a published record, so the bar for them is t >= 2 with the sign stable.
//
//   node scripts/signal_study.js [site/data/panel.json] [--report reports/signal_study.md] [--json site/data/signal_study.json]
const fs = require("fs"), path = require("path");
const args = process.argv.slice(2);
const opt = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const panelPath = args.find((a, k) => !a.startsWith("--") && !(k > 0 && args[k - 1].startsWith("--"))) || "site/data/panel.json";
const P = JSON.parse(fs.readFileSync(panelPath));
const resPath = path.join(path.dirname(panelPath), "panel_research.json");
if (fs.existsSync(resPath)) {
  const R = JSON.parse(fs.readFileSync(resPath));
  if (R.months.length === P.months.length && R.ids.length === P.ids.length) {
    Object.assign(P.fields, R.fields); Object.assign(P.scale, R.scale);
  } else console.error("panel_research.json doesn't match panel.json; candidates skipped");
}
const M = P.months, N = P.ids.length;
const val = (k, m, i) => { const r = P.fields[k] && P.fields[k][m]; const v = r ? r[i] : null; return v == null ? null : v / (P.scale[k] || 1); };
const member = (m, i) => !P.fields.mem || val("mem", m, i) === 1;
const fwdH = (m, i, h) => { let g = 1; for (let k = m; k < m + h; k++) { if (k >= M.length) return null; const r = P.fwd[k][i]; if (r == null || Math.abs(r) > 20000) return null; g *= 1 + r / 1e4; } return g - 1; };

// signal: [label, expected sign, natural horizon in months, published record?]
const SIGNALS = {
  mom: ["Momentum (12-1 months)", 1, 12, true], mvol: ["Momentum per unit of risk", 1, 12, true],
  imom: ["Industry momentum", 1, 6, true], rev1m: ["Last month's return (reversal)", -1, 1, true],
  hi52: ["Nearness to 52-week high", 1, 6, true], T: ["Trend", 1, 3, false],
  vol1y: ["Volatility (low is good)", -1, 12, true],
  gp: ["Gross profit / assets", 1, 12, true], roe: ["Return on equity", 1, 12, true],
  accr: ["Accruals (low is good)", -1, 12, true], agr: ["Asset growth (low is good)", -1, 12, true],
  iss: ["Net share issuance (low is good)", -1, 12, true], fcfY: ["Free-cash-flow yield", 1, 12, true],
  divY: ["Dividend yield", 1, 12, true], pe: ["P/E (low is good)", -1, 12, true], Vp: ["Value vs fair-value estimate", 1, 12, false],
  sue: ["Earnings surprise", 1, 3, true], revGrowth: ["Revenue growth", 1, 12, false], G: ["Revenue growth rank", 1, 12, false],
  insB: ["Insider buying", 1, 6, true], FP: ["Fundamentals checks", 1, 12, false], de: ["Debt / equity (low is good)", -1, 12, false],
};

function ranks(a) {
  const o = a.map((x, k) => [x, k]).sort((p, q) => p[0] - q[0]), r = new Array(a.length);
  for (let s = 0; s < o.length;) { let e = s; while (e + 1 < o.length && o[e + 1][0] === o[s][0]) e++; for (let q = s; q <= e; q++) r[o[q][1]] = (s + e) / 2 / Math.max(1, a.length - 1); s = e + 1; }
  return r;
}
const corr = (a, b) => { const n = a.length, ma = a.reduce((s, x) => s + x, 0) / n, mb = b.reduce((s, x) => s + x, 0) / n; let c = 0, va = 0, vb = 0; for (let k = 0; k < n; k++) { c += (a[k] - ma) * (b[k] - mb); va += (a[k] - ma) ** 2; vb += (b[k] - mb) ** 2; } return va && vb ? c / Math.sqrt(va * vb) : 0; };
const demean = (vals, groups) => { const s = {}, c = {}; vals.forEach((v, k) => { s[groups[k]] = (s[groups[k]] || 0) + v; c[groups[k]] = (c[groups[k]] || 0) + 1; }); return vals.map((v, k) => v - s[groups[k]] / c[groups[k]]); };

// monthly ICs for one signal, market and horizon: [{m, ic}]
function icSeries(key, ex, h, sign) {
  const out = [];
  for (let m = 0; m + h < M.length; m++) {
    const I = [];
    for (let i = 0; i < N; i++) if (P.ex[i] === ex && !P.trust[i] && member(m, i)) I.push(i);
    const xs = [], ys = [], sec = [], caps = [];
    for (const i of I) {
      const x = val(key, m, i), y = fwdH(m, i, h);
      if (x == null || y == null || !isFinite(x)) continue;
      xs.push(sign * x); ys.push(y); sec.push(P.sector[i]); caps.push(val("mcapBn", m, i));
    }
    if (xs.length < 40) continue;
    // size thirds, where market values cover most stocks
    let size = caps.map(() => "");
    const have = caps.filter(c => c > 0);
    if (have.length > 0.8 * caps.length) { const s = have.slice().sort((a, b) => a - b), t1 = s[Math.floor(s.length / 3)], t2 = s[Math.floor(2 * s.length / 3)]; size = caps.map(c => !(c > 0) ? "?" : c < t1 ? "S" : c < t2 ? "M" : "L"); }
    const xr = demean(ranks(xs), sec);
    const yr = demean(ys, sec.map((s, k) => s + "/" + size[k]));
    out.push({ m, ic: corr(xr, ranks(yr)) });
  }
  return out;
}
// mean and Newey-West t (h-1 lags, Bartlett weights)
function summarise(series, h) {
  const x = series.map(s => s.ic), n = x.length;
  if (n < 24) return null;
  const mu = x.reduce((a, b) => a + b, 0) / n, e = x.map(v => v - mu);
  let v = e.reduce((a, b) => a + b * b, 0) / n;
  for (let L = 1; L < h && L < n; L++) { let c = 0; for (let k = L; k < n; k++) c += e[k] * e[k - L]; v += 2 * (1 - L / h) * c / n; }
  return { ic: mu, t: mu / Math.sqrt(Math.max(v, 1e-12) / n), months: n, hit: x.filter(y => y > 0).length / n, from: M[series[0].m], to: M[series[n - 1].m] };
}

const rows = [];
for (const ex of ["US", "LSE"]) for (const [key, [label, sign, hNat, published]] of Object.entries(SIGNALS)) {
  if (!P.fields[key]) continue;
  const r = { market: ex, key, label, sign, horizon: hNat, published, by: {} };
  for (const h of [1, 3, 6, 12]) {
    const s = icSeries(key, ex, h, sign), all = summarise(s, h);
    if (!all) continue;
    const half = Math.floor(s.length / 2);
    r.by[h] = { ...all, first: summarise(s.slice(0, half), h), second: summarise(s.slice(half), h) };
  }
  const nat = r.by[hNat];
  if (nat) {
    const bar = published ? 2 : 3;
    r.passes = nat.t >= bar && nat.first && nat.second && nat.first.ic > 0 && nat.second.ic > 0;
    r.bar = bar;
  }
  rows.push(r);
}

const pct = x => (x * 100).toFixed(1);
let md = `# Signal study, ${new Date().toISOString().slice(0, 10)}\n\n` +
  `Information coefficient: the rank correlation between a signal (ranked within sectors) and the next h months' returns (against the stock's sector and size group), index members only, as a percentage. t uses Newey-West errors for overlapping windows. The decision horizon is in bold. A signal passes with the expected sign, t ≥ 2 (t ≥ 3 without a published record) and the same sign in both halves of the period.\n\n`;
for (const ex of ["US", "LSE"]) {
  md += `## ${ex === "US" ? "US (S&P 500)" : "UK (FTSE 350)"}\n\n| Signal | 1 month | 3 months | 6 months | 12 months | Halves (decision horizon) | Months | Passes |\n|---|---|---|---|---|---|---|---|\n`;
  for (const r of rows.filter(r => r.market === ex).sort((a, b) => ((b.by[b.horizon] || {}).t || -99) - ((a.by[a.horizon] || {}).t || -99))) {
    const cell = h => { const b = r.by[h]; if (!b) return "–"; const s = `${pct(b.ic)} (t ${b.t.toFixed(1)})`; return h === r.horizon ? `**${s}**` : s; };
    const nat = r.by[r.horizon];
    md += `| ${r.label} | ${[1, 3, 6, 12].map(cell).join(" | ")} | ${nat && nat.first && nat.second ? `${pct(nat.first.ic)} / ${pct(nat.second.ic)}` : "–"} | ${nat ? `${nat.months} (${nat.from.slice(0, 7)} to ${nat.to.slice(0, 7)})` : "–"} | ${r.passes ? "Yes" : "No"} |\n`;
  }
  md += "\n";
}
const tests = rows.reduce((a, r) => a + (r.by[r.horizon] ? 1 : 0), 0);
md += `${tests} signal-market tests at the decision horizon; at t ≥ 2, about ${(tests * 0.023).toFixed(1)} would pass by chance if no signal worked (one-sided), which is why both halves must agree.\n`;
const rep = opt("--report"), js = opt("--json");
if (rep) { fs.mkdirSync(path.dirname(rep), { recursive: true }); fs.writeFileSync(rep, md); }
if (js) fs.writeFileSync(js, JSON.stringify({ generated: new Date().toISOString(), rows }, null, 0));
console.log(md);
