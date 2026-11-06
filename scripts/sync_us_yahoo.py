"""US end-of-day prices from Yahoo Finance for the S&P 500 stocks that Tiingo's free tier can't cover.

Tiingo's free tier allows 500 unique symbols a month and about 50 requests an hour, so
scripts/sync_prices.sh syncs only the first MAX_TICKERS US stocks (210 by default, in universe
order). Without this script the rest of the index (Microsoft, Nvidia, Meta, JPMorgan and most
companies after "F") had no prices and were left out of the screener and every backtest.

This fills them from Yahoo's public chart endpoint, as sync_uk_prices.py does for London: ten years
of daily bars, adjusted for splits and dividends (total return, like Tiingo's adjusted prices),
written to data/prices/<provider_ticker>.csv in the same format. Missing files come first, then the
oldest, within a time budget.

  python scripts/sync_us_yahoo.py [--budget-min 25]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from sync_uk_prices import CHART, add_dividends, dividends_missing, get_json, looks_sane, parse_chart, parse_dividends, write_bars  # noqa: E402


def tiingo_tickers(pattern: str = "universe/*.csv") -> set[str]:
    """The provider tickers scripts/sync_prices.sh downloads from Tiingo (same order and cap)."""
    if os.environ.get("TIINGO_TIER", "free") == "power":
        cap = int(os.environ.get("MAX_TICKERS", "10000"))
    else:
        cap = int(os.environ.get("MAX_TICKERS", "210"))
    out = []
    for f in sorted(glob.glob(pattern)):
        for r in csv.DictReader(open(f, newline="")):
            t = (r.get("provider_ticker") or "").strip()
            if t and r.get("market") != "UK":
                out.append(t)
    return set(out[:cap])


def ny_unfinished_day(now: dt.datetime | None = None) -> str:
    """Today's date while New York is trading or its close is settling (before 16:30 New York
    time), else ''. A bar for an unfinished day is a price, not a close."""
    try:
        from zoneinfo import ZoneInfo
        now = now or dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = now or (dt.datetime.utcnow() - dt.timedelta(hours=5))
    return now.date().isoformat() if (now.hour, now.minute) < (16, 30) else ""


def yahoo_symbol(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def todo(rows: list[dict], out_dir: str, skip: set[str]) -> list[dict]:
    """Stocks to fetch: missing files first, then the least recently written."""
    need = [r for r in rows if r["provider_ticker"] and r["provider_ticker"] not in skip]
    def age(r):
        p = os.path.join(out_dir, r["provider_ticker"] + ".csv")
        return (1, os.path.getmtime(p)) if os.path.exists(p) else (0, 0.0)
    return sorted(need, key=age)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe/us.csv")
    ap.add_argument("--out", default="data/prices")
    ap.add_argument("--pause", type=float, default=0.8)
    ap.add_argument("--budget-min", type=float, default=25)
    ap.add_argument("--all", action="store_true", help="also re-fetch the Tiingo stocks from Yahoo")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = [r for r in csv.DictReader(open(args.universe, newline="")) if r.get("market", "US") != "UK"]
    skip = set() if args.all else tiingo_tickers()
    queue = todo(rows, args.out, skip)
    stop = time.time() + args.budget_min * 60
    ok, kept, failed = 0, [], []
    for r in queue:
        if time.time() > stop:
            break
        path = os.path.join(args.out, r["provider_ticker"] + ".csv")
        d = get_json(CHART.format(sym=yahoo_symbol(r["ticker"]), rng="10y"))
        missing = dividends_missing(d)
        ccy, bars = parse_chart(d, scale_override=1.0, raw=missing)
        if bars and ccy and ccy != "USD":
            bars = []
        today = ny_unfinished_day()
        bars = [b for b in bars if b[0] != today]
        if bars and missing:
            bars = add_dividends(bars, parse_dividends(d, 1.0))
        why = "no data" if not bars else looks_sane(bars, path)
        if why:
            (kept if os.path.exists(path) else failed).append(f"{r['ticker']} ({why})")
        else:
            write_bars(path, bars)
            ok += 1
        time.sleep(args.pause)
    have = sum(os.path.exists(os.path.join(args.out, r["provider_ticker"] + ".csv")) for r in rows)
    print(f"::notice::US prices from Yahoo: {ok} updated of {len(queue)} not covered by Tiingo; {have} of {len(rows)} US stocks now have prices")
    for k in kept[:10]:
        print(f"::warning::Kept previous prices for {k}")
    if failed:
        print("::warning::No US prices for: " + ", ".join(failed[:30]))


if __name__ == "__main__":
    main()
