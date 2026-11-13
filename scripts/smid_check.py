"""Index check for the mid and small caps: can the S&P 400 and 600 be rebuilt from their members?

Each month from the first fund filing on record, a copy of each index holds the members of that
date (universe/history/sp400_membership.csv, sp600) weighted by market value, with our daily
prices (data/prices, and data/prices_departed for companies that have left), and is compared with
the iShares fund that tracks the index (IJH, IJR; total return from Yahoo). Weights come from the
fund's own holdings at the last quarter-end, grown by each stock's return since, so they follow
the index's float-adjusted weights. A copy that tracks its fund closely means the members and
prices are complete enough for backtests; coverage says what share of the index's value we have
prices for.

    python scripts/smid_check.py [--report reports/smid_check.md]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import glob
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))
import build_membership as BM  # noqa: E402

FUNDS = {"S&P 400": ("ijh", "IJH", "universe/history/sp400_membership.csv"),
         "S&P 600": ("ijr", "IJR", "universe/history/sp600_membership.csv")}


def load_closes(path: str) -> tuple[list[str], list[float]]:
    d, c = [], []
    if os.path.exists(path):
        for r in csv.DictReader(open(path, newline="")):
            try:
                v = float(r["Close"])
            except (KeyError, TypeError, ValueError):
                continue
            if v > 0:
                d.append(r["Date"][:10])
                c.append(v)
    return d, c


def spliced(live_path: str, archive_path: str) -> tuple[list[str], list[float]]:
    """Live closes with the 2008-2017 archive in front, scaled to the live basis by the median
    ratio over the days both have (as internal/core.Splice does)."""
    d, c = load_closes(live_path)
    ad, ac = load_closes(archive_path)
    if not ad:
        return d, c
    if not d:
        return ad, ac
    live = dict(zip(d, c))
    ratios = sorted(live[x] / y for x, y in zip(ad, ac) if x in live)
    if not ratios:
        return d, c
    k = ratios[len(ratios) // 2]
    head = [(x, y * k) for x, y in zip(ad, ac) if x < d[0]]
    return [x for x, _ in head] + d, [y for _, y in head] + c


def on(series, day: str, slack: int = 6):
    """The close on or before day, if within `slack` days."""
    d, c = series
    k = bisect.bisect_right(d, day) - 1
    if k < 0 or (dt.date.fromisoformat(day) - dt.date.fromisoformat(d[k])).days > slack:
        return None
    return c[k]


def month_ends(first: str, last: str) -> list[str]:
    out, y, m = [], int(first[:4]), int(first[5:7])
    while True:
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        e = (nxt - dt.timedelta(days=1)).isoformat()
        if e > last:
            return out
        out.append(e)
        y, m = nxt.year, nxt.month


def fund_series(sym: str):
    """Total-return daily closes of a fund from Yahoo (adjusted for its distributions)."""
    import departed as D
    res = D.yahoo(sym)
    if not res:
        return [], []
    bars = res[0]
    return [b[0] for b in bars], [b[4] for b in bars]


def check(index: str, prices_for, fund=None, since: str = "", until: str = "9999") -> dict | None:
    code, sym, mpath = FUNDS[index]
    spans = [r for r in csv.DictReader(open(mpath, newline=""))] if os.path.exists(mpath) else []
    files = sorted(glob.glob(os.path.join(BM.SRC, code, "*.csv")))
    if not spans or not files:
        return None
    cmap = BM.cusip_tickers(files)
    nmap = BM.name_tickers(files, cmap)
    hold = {}   # quarter-end -> ticker -> value in dollars
    for f in files:
        q = os.path.basename(f)[:10]
        hold[q] = {}
        for r in csv.DictReader(open(f, newline="")):
            t = BM.ticker_of(r, cmap, nmap)
            try:
                v = float(r["value_usd"])
            except (TypeError, ValueError):
                continue
            if t and v > 0:
                hold[q][t] = hold[q].get(t, 0) + v
    qs = sorted(hold)
    fund = fund if fund is not None else fund_series(sym)
    if not fund[0]:
        return None
    ends = month_ends(qs[0], fund[0][-1])
    rows = []
    for a, b in zip(ends, ends[1:]):
        if not since <= a < until:
            continue
        q = qs[bisect.bisect_right(qs, a) - 1]
        mem = [s["ticker"] for s in spans if s["start_date"] <= a and (not s["end_date"] or a < s["end_date"])]
        tot = cov = s = w = 0.0
        for t in mem:
            v0 = hold[q].get(t)
            if not v0:
                continue
            ser = prices_for(t)
            pq, pa, pb = (on(ser, q), on(ser, a), on(ser, b)) if ser else (None, None, None)
            if pq and pa:
                v0 = v0 * pa / pq      # grown to this month-end
            tot += v0
            if pa and pb:
                cov += v0
                s += v0 * (pb / pa - 1)
                w += v0
        fa, fb = on(fund, a), on(fund, b)
        if w > 0 and fa and fb:
            rows.append((b, s / w, fb / fa - 1, cov / tot if tot else 0))
    if len(rows) < 12:
        return None
    diff = [x[1] - x[2] for x in rows]
    worst = max(rows, key=lambda x: abs(x[1] - x[2]))
    return {"index": index, "fund": sym, "from": rows[0][0], "to": rows[-1][0], "months": len(rows),
            "gap": statistics.mean(diff) * 12, "te": statistics.stdev(diff) * math.sqrt(12),
            "coverage_min": min(x[3] for x in rows), "coverage_mean": statistics.mean(x[3] for x in rows),
            "worst": (worst[0], worst[1] - worst[2])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    paths = {}
    for f in glob.glob("universe/*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            if r.get("market") != "UK" and r.get("provider_ticker"):
                paths[BM.norm(r["ticker"])] = os.path.join("data/prices", r["provider_ticker"] + ".csv")
    cache = {}

    def prices_for(t: str):
        if t not in cache:
            p = paths.get(t) or os.path.join("data/prices_departed", t.lower().replace(".", "-") + ".csv")
            arch = os.path.join("data/prices_archive", os.path.basename(p))
            cache[t] = spliced(p, arch) if os.path.exists(p) else None
        return cache[t]

    lines = [f"# Mid and small-cap index check, {dt.date.today().isoformat()}", "",
             "A market-value-weighted copy of each index, built from its members of each month and our prices, against the "
             "iShares fund that tracks it. Coverage is the share of the index's value with prices.", ""]
    fund_cache = {}
    for index, (since, until, label) in [(i, p) for i in FUNDS for p in (("", "2019-09-30", "before N-PORT"), ("2019-09-30", "9999", "N-PORT"))]:
        if index not in fund_cache:
            fund_cache[index] = fund_series(FUNDS[index][1])
        r = check(index, prices_for, fund=fund_cache[index], since=since, until=until)
        if not r:
            lines.append(f"- {index} ({label}): not enough data yet")
            continue
        lines.append(f"- {index} ({label}) against {r['fund']}, {r['from'][:7]} to {r['to'][:7]} ({r['months']} months): "
                     f"{r['gap']:+.1%} a year, tracking error {r['te']:.1%}; coverage {r['coverage_mean']:.0%} on average, "
                     f"lowest {r['coverage_min']:.0%}; largest month {r['worst'][0][:7]} {r['worst'][1]:+.1%}")
        print(f"::notice::{lines[-1][2:]}")
    lines += ["", "Rule (fixed before the result): mid and small caps join the Lab and generator backtests when, for both "
              "indexes, average coverage is at least 95%, the gap is within 2% a year and tracking error below 3%."]
    text = "\n".join(lines) + "\n"
    if a.report:
        os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
        open(a.report, "w").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
