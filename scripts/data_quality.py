"""Data-quality checks that stop a bad publish.

Three serious errors were found by accident in November 2026: 290 US stocks without prices,
dividends compounded on scaled UK closes, and share counts filed in the wrong units (Edison
International worth $24,000 trillion). None of them would have been missed by a check of the data
as a whole, so this runs every night (prices) and every month (the history panel). Problems are
printed as warnings; serious ones make the step fail, which stops the publish and opens an issue.

    python scripts/data_quality.py prices [--universe universe] [--prices data/prices]
    python scripts/data_quality.py panel  [--panel site/data/panel.json] [--report reports/data_quality.md]

Panel checks:
  coverage     share of index members with a return each month (last 24 months)
  benchmark    each index against a market-value-weighted copy built from its own members: a
               copy should track it closely, so a large gap means missing stocks, wrong
               dividends or wrong market values
  market value month-to-month changes not explained by the price (a whole power of ten = units)
  returns      monthly returns above +200% or below -90%
  yields       free-cash-flow yields above 100% or dividend yields above 30%
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import statistics
import sys

INDEXES = {"US": ("sp500", "S&P 500"), "LSE": ("ftse100", "FTSE 100")}


class Report:
    def __init__(self):
        self.lines: list[str] = []
        self.fails: list[str] = []
        self.warns: list[str] = []

    def ok(self, msg):
        self.lines.append(f"- OK: {msg}")

    def warn(self, msg):
        self.warns.append(msg)
        self.lines.append(f"- Warning: {msg}")
        print(f"::warning::{msg}")

    def fail(self, msg):
        self.fails.append(msg)
        self.lines.append(f"- **Failed**: {msg}")
        print(f"::error::{msg}")


# ---------------------------------------------------------------- prices (nightly)

def check_prices(universe: str, prices: str, rep: Report) -> None:
    rows = [r for f in sorted(glob.glob(os.path.join(universe, "*.csv"))) for r in csv.DictReader(open(f, newline=""))]
    last: dict[str, str] = {}
    for r in rows:
        p = os.path.join(prices, (r.get("provider_ticker") or "") + ".csv")
        if not os.path.exists(p):
            continue
        with open(p, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - 200))
            tail = fh.read().decode("utf-8", "ignore").strip().splitlines()
        if tail and tail[-1][:4].isdigit():
            last[r["ticker"] + ":" + r.get("market", "")] = tail[-1][:10]
    small = {"S&P 400", "S&P 600", "FTSE SmallCap"}
    # mid and small caps (new in November 2026) are reported but can't stop the publish
    smid = [r for r in rows if r.get("index") in small]
    if smid:
        have = sum(1 for r in smid if r["ticker"] + ":" + r.get("market", "") in last)
        (rep.warn if have < 0.9 * len(smid) else rep.ok)(f"mid and small caps: {have} of {len(smid)} have a price file")
    rows = [r for r in rows if r.get("index") not in small]
    for mkt in ("US", "UK"):
        uni = [r for r in rows if (r.get("market") or "US") == mkt]
        have = [k for k in last if k.endswith(":" + mkt)]
        share = len(have) / max(1, len(uni))
        msg = f"{mkt} prices: {len(have)} of {len(uni)} stocks have a price file ({share:.0%})"
        (rep.fail if share < 0.90 else rep.warn if share < 0.97 else rep.ok)(msg)
        if not have:
            continue
        newest = max(last[k] for k in have)
        cut = (dt.date.fromisoformat(newest) - dt.timedelta(days=6)).isoformat()
        stale = sorted(k.split(":")[0] for k in have if last[k] < cut)
        frac = len(stale) / len(have)
        msg = f"{mkt} prices: {len(stale)} stocks have no price in the 6 days to {newest}" + (f" ({', '.join(stale[:12])})" if stale else "")
        (rep.fail if frac > 0.25 else rep.warn if frac > 0.03 else rep.ok)(msg)
    for b in ("bench-sp500", "bench-ftse100"):
        p = os.path.join(prices, b + ".csv")
        if not os.path.exists(p):
            rep.fail(f"benchmark {b} has no price file")


# ---------------------------------------------------------------- panel (monthly)

def _val(P, key, m, i):
    row = P["fields"].get(key, [])
    if m >= len(row) or row[m] is None:
        return None
    v = row[m][i]
    return None if v is None else v / (P.get("scale", {}).get(key) or 1)


def benchmark_gap(P, ex: str, last: int = 0):
    """Monthly differences between a market-value-weighted copy of the index's members and the
    index itself, for months where members with a market value make up most of the index.
    Second share classes of one company (same market value) are counted once."""
    bkey, iname = INDEXES[ex]
    M, out = P["months"], []
    for m in range(max(0, len(M) - 1 - last) if last else 0, len(M) - 1):
        b = P["bench"][bkey][m]
        if b is None:
            continue
        seen: dict[str, float] = {}
        s, w, n, members = 0.0, 0.0, 0, 0
        for i in range(len(P["ids"])):
            if P["ex"][i] != ex or P["idx"][i] != iname:
                continue
            f = P["fwd"][m][i]
            if f is None:
                continue
            members += 1
            c = _val(P, "mcapBn", m, i)
            if not c or c <= 0:
                continue
            # a second share class carries the whole company's value (GOOG and GOOGL, FOX and FOXA)
            tk = P["ids"][i].split("-", 1)[-1]
            if any((tk.startswith(o) or o.startswith(tk)) and abs(c / v - 1) < 0.02 for o, v in seen.items()):
                continue
            seen[tk] = c
            s, w, n = s + c * f, w + c, n + 1
        if members and n >= 0.8 * members:
            out.append((M[m], (s / w - b) / 1e4))
    return out


def check_panel(P: dict, rep: Report) -> None:
    M, ids, ex = P["months"], P["ids"], P["ex"]
    n = len(ids)
    mem = P["fields"].get("mem")
    # coverage
    for mk in ("US", "LSE"):
        worst = (1.0, "")
        for m in range(max(0, len(M) - 25), len(M) - 1):
            members = [i for i in range(n) if ex[i] == mk and (mem is None or (mem[m] and mem[m][i]))]
            if not members:
                continue
            share = sum(P["fwd"][m][i] is not None for i in members) / len(members)
            worst = min(worst, (share, M[m]))
        msg = f"{mk}: at least {worst[0]:.0%} of members have a return in every one of the last 24 months" + (f" (lowest {worst[1]})" if worst[1] else "")
        (rep.fail if worst[0] < 0.90 else rep.warn if worst[0] < 0.97 else rep.ok)(msg)
    # benchmark against its own members
    for mk in ("US", "LSE"):
        g = benchmark_gap(P, mk)
        if len(g) < 12:
            rep.warn(f"{mk}: too few months with market values to check the benchmark ({len(g)})")
            continue
        x = [d for _, d in g]
        mean, te = statistics.mean(x) * 12, statistics.stdev(x) * math.sqrt(12)
        worst = max(g, key=lambda t: abs(t[1]))
        msg = (f"{mk}: market-value-weighted members vs {INDEXES[mk][1]} since {g[0][0]}: {mean:+.1%} a year, "
               f"tracking error {te:.1%} (largest month {worst[0]}: {worst[1]:+.1%})")
        (rep.fail if te > 0.06 or abs(mean) > 0.04 else rep.warn if te > 0.03 or abs(mean) > 0.02 else rep.ok)(msg)
    # market value moves not explained by the price
    units, jumps = [], []
    for i in range(n):
        for m in range(len(M) - 1):
            a, b, f = _val(P, "mcapBn", m, i), _val(P, "mcapBn", m + 1, i), P["fwd"][m][i]
            if not a or not b or a <= 0 or b <= 0 or f is None or f <= -1e4:
                continue
            r = math.log10(b / a) - math.log10(1 + f / 1e4)
            if abs(r) >= 1.8:
                units.append(f"{ids[i]} {M[m + 1]} x{10 ** r:.3g}")
            elif abs(r) >= math.log10(1.6):
                jumps.append(f"{ids[i]} {M[m + 1]}")
    if units:
        rep.fail(f"market values that jump by a power of ten without the price ({len(units)}): " + ", ".join(units[:12]))
    else:
        rep.ok("no market value jumps by a power of ten")
    if jumps:
        rep.lines.append(f"- Note: {len(jumps)} market-value changes of 60% or more beyond the price, usually mergers or share issues: " + ", ".join(jumps[:20]))
    # returns
    odd = [f"{ids[i]} {M[m]} {P['fwd'][m][i] / 100:+.0f}%" for m in range(len(M)) for i in range(n)
           if P["fwd"][m][i] is not None and (P["fwd"][m][i] > 20000 or P["fwd"][m][i] < -9000)]
    obs = sum(1 for m in range(len(M)) for i in range(n) if P["fwd"][m][i] is not None)
    if odd:
        (rep.fail if len(odd) > 0.001 * obs else rep.warn)(f"monthly returns above +200% or below -90% ({len(odd)} of {obs}): " + ", ".join(odd[:10]))
    else:
        rep.ok(f"no monthly return above +200% or below -90% ({obs} stock-months)")
    # yields
    bad = []
    for key, lim in (("fcfY", 1.0), ("divY", 0.3)):
        for m in range(len(M)):
            for i in range(n):
                v = _val(P, key, m, i)
                if v is not None and abs(v) > lim:
                    bad.append(f"{ids[i]} {M[m]} {key} {v:.0%}")
    if bad:
        stocks = sorted({b.split()[0] for b in bad})
        (rep.fail if len(stocks) > 10 else rep.warn)(f"implausible yields for {len(stocks)} stocks ({len(bad)} stock-months): " + ", ".join(bad[:10]))
    else:
        rep.ok("no free-cash-flow yield above 100% or dividend yield above 30%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prices", "panel"])
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--prices", default="data/prices")
    ap.add_argument("--panel", default="site/data/panel.json")
    ap.add_argument("--report", default="")
    ap.add_argument("--warn-only", action="store_true", help="report but never fail")
    a = ap.parse_args()
    rep = Report()
    if a.mode == "prices":
        check_prices(a.universe, a.prices, rep)
    else:
        P = json.load(open(a.panel))
        check_panel(P, rep)
    head = f"# Data quality ({a.mode}), {dt.date.today().isoformat()}\n\n"
    text = head + "\n".join(rep.lines) + "\n"
    if a.report:
        os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
        open(a.report, "w").write(text)
    print(text)
    print(f"::notice::Data quality ({a.mode}): {len(rep.fails)} failed, {len(rep.warns)} warnings")
    return 1 if rep.fails and not a.warn_only else 0


if __name__ == "__main__":
    sys.exit(main())
