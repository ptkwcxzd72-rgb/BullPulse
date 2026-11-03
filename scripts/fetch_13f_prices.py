"""Prices for investors' holdings that are not in the S&P 500 price set, for their copy records.

The screener prices S&P 500 shares only, so many of the investors' holdings (smaller US companies,
foreign companies' US listings) had no price and were left out of the copy record. This fetches
them from Yahoo Finance's public chart endpoint (no key; the same source as the UK prices).

Only what the copy record needs is kept, per ticker: the close on each day a follower would have
bought or sold it (the first trading day after each filing) and at each month end while it was
held, as total-return prices (dividends included). Stored one ticker per line in
data/history/13f_prices.jsonl, so daily updates change only a few lines.

Tickers are checked before use, because an old ticker can later belong to another company: for
each filing, the price the investor reported (value / shares) must match Yahoo's close at the
quarter end, allowing for later stock splits. Only filings that pass are used ("ok").

    python scripts/fetch_13f_prices.py [--budget 25]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import glob
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from sync_uk_prices import add_dividends, dividends_missing, get_json  # noqa: E402

SRC = "data/history/13f"
OUT = "data/history/13f_prices.jsonl"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit&includeAdjustedClose=true"
MIN_W = 0.002          # holdings that never reached 0.2% of a portfolio barely move a copy record
REFRESH_W = 0.005      # holdings at 0.5% or more of a latest filing are refreshed every run
SPLITS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100]
FACTORS = sorted({1.0} | {float(a) for a in SPLITS} | {float(a * b) for a in SPLITS for b in SPLITS if a * b <= 2000})


def yahoo(t: str) -> str:
    return t.replace(".", "-").replace("/", "-")


def entry_day(cal: list[str], day: str) -> str | None:
    """First trading day after a date (the day a follower could act on a filing)."""
    k = bisect.bisect_right(cal, day)
    return cal[k] if k < len(cal) else None


def month_ends(a: str, b: str) -> list[str]:
    out, y, m = [], int(a[:4]), int(a[5:7])
    while True:
        nm = dt.date(y + (m == 12), m % 12 + 1, 1)
        me = (nm - dt.timedelta(days=1)).isoformat()
        if me > b:
            return out
        if me >= a:
            out.append(me)
        y, m = nm.year, nm.month


def needs(docs: list[dict], cal: list[str], skip: set[str]) -> dict[str, dict]:
    """For each ticker to price: the days needed, the quarter ends to check, the filed prices,
    its largest weight in any filing and its weight in the latest filings."""
    today = cal[-1]
    out: dict[str, dict] = {}
    for doc in docs:
        fs = [f for f in doc.get("filings", []) if f.get("holdings")]
        for k, f in enumerate(fs):
            tot = sum(h["value"] for h in f["holdings"]) or 1
            start = entry_day(cal, f["filed"])
            end = entry_day(cal, fs[k + 1]["filed"]) if k + 1 < len(fs) else today
            for h in f["holdings"]:
                t = (h.get("ticker") or "").upper()
                if not t or t in skip:
                    continue
                n = out.setdefault(t, {"days": set(), "checks": {}, "maxw": 0.0, "latestw": 0.0})
                w = h["value"] / tot
                n["maxw"] = max(n["maxw"], w)
                if k == len(fs) - 1:
                    n["latestw"] = max(n["latestw"], w)
                if h.get("shares") and h["value"] > 0:
                    n["checks"][f["period"]] = h["value"] / h["shares"]
                if start and end and start < end:
                    n["days"].update([start, end, *month_ends(start, end)])
    return {t: n for t, n in out.items() if n["maxw"] >= MIN_W}


def chart(sym: str, p1: str, p2: str) -> dict | None:
    ts = lambda d: int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp())
    return get_json(URL.format(sym=sym, p1=ts(p1), p2=ts(p2) + 86400 * 2), tries=3)


def parse(d: dict) -> tuple[list[str], list[float], list[float]]:
    """(days, total-return closes, split-adjusted closes) from a chart response."""
    res = (d or {}).get("chart", {}).get("result") or []
    if not res:
        return [], [], []
    r = res[0]
    if r.get("meta", {}).get("currency") not in (None, "USD"):
        return [], [], []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    close = q.get("close") or []
    adj = ((r.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or close
    days, tr, cl = [], [], []
    for i, t in enumerate(r.get("timestamp") or []):
        c = close[i] if i < len(close) else None
        a = adj[i] if i < len(adj) else None
        if not c or c <= 0:
            continue
        day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        if days and day <= days[-1]:
            continue
        days.append(day); cl.append(c); tr.append(a or c)
    if dividends_missing(d):             # adjusted closes without the dividends: add them back
        divs = []
        for e in ((r.get("events") or {}).get("dividends") or {}).values():
            if e.get("amount"):
                divs.append([dt.datetime.fromtimestamp(e["date"], dt.timezone.utc).date().isoformat(), e["amount"]])
        bars = add_dividends([[dd, c, c, c, c, 0] for dd, c in zip(days, cl)], sorted(divs))
        tr = [b[4] for b in bars]
    return days, tr, cl


def on_or_before(days: list[str], vals: list[float], day: str):
    k = bisect.bisect_right(days, day) - 1
    return (days[k], vals[k]) if k >= 0 else (None, None)


def verified(checks: dict[str, float], days: list[str], cl: list[float]) -> list[str]:
    """Quarter ends where the filed price matches Yahoo's close (allowing for later splits)."""
    ok = []
    for period, filed in checks.items():
        d0, c = on_or_before(days, cl, period)
        if not c or not d0 or (dt.date.fromisoformat(period) - dt.date.fromisoformat(d0)).days > 7:
            continue
        r = filed / c
        if any(abs(math.log(r / f)) < 0.12 for f in FACTORS) or any(abs(math.log(r * f)) < 0.12 for f in FACTORS if f > 1):
            ok.append(period)
    return sorted(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=25, help="minutes")
    ap.add_argument("--prices", default="data/prices")
    args = ap.parse_args()
    T0 = time.time()
    docs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(SRC, "*.json")))]
    bp = os.path.join(args.prices, "bench-sp500.csv")
    if not docs or not os.path.exists(bp):
        print("::warning::13F prices skipped: no filings or no S&P 500 calendar yet")
        return 0
    cal = [r["Date"][:10] for r in csv.DictReader(open(bp, newline=""))]
    skip = set()
    for f in glob.glob("universe/us*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            if os.path.exists(os.path.join(args.prices, (r.get("provider_ticker") or "") + ".csv")):
                skip.add(r["ticker"].upper())
    want = needs(docs, cal, skip)
    have: dict[str, dict] = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            if line.strip():
                x = json.loads(line)
                have[x["t"]] = x
    today = cal[-1]
    # order: never fetched (largest first), then this run's refreshes, then the oldest fetched
    new = sorted((t for t in want if t not in have), key=lambda t: -want[t]["maxw"])
    refresh = sorted((t for t in want if t in have and want[t]["latestw"] >= REFRESH_W), key=lambda t: -want[t]["latestw"])
    stale = sorted((t for t in want if t in have and t not in refresh and have[t].get("asof", "") < today), key=lambda t: have[t].get("asof", ""))
    done = got = 0
    for t in new + refresh + stale:
        if time.time() - T0 > args.budget * 60:
            break
        n = want[t]
        if not n["days"]:
            continue
        lo = min(min(n["days"]), min(n["checks"], default=today))
        d = chart(yahoo(t), (dt.date.fromisoformat(lo) - dt.timedelta(days=10)).isoformat(), today)
        done += 1
        time.sleep(0.25)
        days, tr, cl = parse(d)
        if not days:
            have.setdefault(t, {"t": t, "d": [], "p": [], "ok": [], "missing": True})["asof"] = today
            continue
        keep = sorted(n["days"])
        pts = {}
        for day in keep:
            d0, p = on_or_before(days, tr, day)
            if p and (dt.date.fromisoformat(day) - dt.date.fromisoformat(d0)).days <= 7:
                pts[d0] = round(p, 4)
        have[t] = {"t": t, "d": sorted(pts), "p": [pts[k] for k in sorted(pts)], "ok": verified(n["checks"], days, cl), "asof": today}
        got += 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        for t in sorted(have):
            if t in want:
                f.write(json.dumps(have[t], separators=(",", ":")) + "\n")
    priced = sum(1 for t in want if t in have and have[t].get("p"))
    left = len([t for t in want if t not in have])
    print(f"::notice::13F prices: {got} fetched this run ({done} requests); {priced} of {len(want)} holdings priced; {left} still to fetch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
