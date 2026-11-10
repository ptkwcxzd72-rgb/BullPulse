"""Older daily prices (2008 to early 2017) for the backtests, downloaded once per stock.

The live price files hold about ten years and are rewritten as dividends re-base total-return
prices, so they can't simply be made longer without the repository growing every night. This
writes a separate archive, data/prices_archive/<provider_ticker>.csv, in the same format, ending a
few months into the live files' range. internal/core.LoadLong joins it in front of the live
file, scaling it to the live basis over the days both cover, so later dividends don't matter.
Each file is written once; stocks that already have one are skipped, so after the first fill a
run costs nothing unless the universe changes.

Same sources and adjustments as the live files: Yahoo's chart endpoint, dividends added where
Yahoo left them out (sync_uk_prices.dividends_missing), London prices in pence with
pounds/pence steps undone. The benchmarks (SPY, ISF.L) are archived too.

    python scripts/archive_prices.py [--budget-min 25]
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
import sync_uk_prices as UK  # noqa: E402

OUT = "data/prices_archive"
START, END = "2008-01-01", "2017-04-30"
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}"
       "&interval=1d&events=div%2Csplit&includeAdjustedClose=true")


def epoch(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def symbol(r: dict) -> str:
    if r.get("market") == "UK":
        return UK.yahoo_symbol(r["ticker"])
    return r["ticker"].strip().upper().replace(".", "-")


def fetch(sym: str, uk: bool) -> list[list] | None:
    """Total-return daily bars for the archive window (UK in pence); [] if Yahoo has none, None
    if the request failed (tried again next run)."""
    d = UK.get_json(URL.format(sym=sym, p1=epoch(START), p2=epoch(END)))
    if d is None:
        return None
    missing = UK.dividends_missing(d)
    if uk:
        ccy, bars = UK.parse_chart(d, raw=missing)
        scale = {"GBp": 1.0, "GBX": 1.0, "GBP": 100.0}.get(ccy) or UK.FX.get(ccy, 0) * 100
        bars, _ = UK.fix_unit_steps(bars)
    else:
        ccy, bars = UK.parse_chart(d, scale_override=1.0, raw=missing)
        scale = 1.0
        if ccy and ccy != "USD":
            return []
    if bars and missing:
        bars = UK.add_dividends(bars, UK.parse_dividends(d, scale))
    return [b for b in bars if START <= b[0] <= END]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--budget-min", type=float, default=25)
    ap.add_argument("--pause", type=float, default=0.8)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = [r for f in sorted(glob.glob(os.path.join(args.universe, "*.csv"))) for r in csv.DictReader(open(f, newline=""))]
    jobs = [(r["provider_ticker"], symbol(r), r.get("market") == "UK") for r in rows if r.get("provider_ticker")]
    jobs += [(name, sym, sym.endswith(".L")) for name, sym in UK.BENCHMARKS.items()]
    todo = [j for j in jobs if not os.path.exists(os.path.join(args.out, j[0] + ".csv"))]
    UK.FX.update(UK.fx_rates())
    stop = time.time() + args.budget_min * 60
    done, short = 0, []
    for name, sym, uk in todo:
        if time.time() > stop:
            break
        bars = fetch(sym, uk)
        if bars is None:
            time.sleep(args.pause)
            continue
        # a stock listed after 2008 has a shorter archive; one listed after 2016 needs none
        if len(bars) >= 60:
            UK.write_bars(os.path.join(args.out, name + ".csv"), bars)
            done += 1
        else:
            short.append(sym)
            # remember that there is nothing to archive, so it isn't asked for again
            open(os.path.join(args.out, name + ".csv"), "w").write("Date,Open,High,Low,Close,Volume\n")
        time.sleep(args.pause)
    have = sum(1 for j in jobs if os.path.exists(os.path.join(args.out, j[0] + ".csv")))
    print(f"::notice::Price archive (2008 to 2017): {done} written this run; {have} of {len(jobs)} stocks done"
          + (f"; {len(todo) - done - len(short)} left for the next run" if have < len(jobs) else ""))
    if short:
        print(f"  no history before 2017 (listed later, or not on Yahoo under today's symbol): {', '.join(short[:40])}")


if __name__ == "__main__":
    main()
