"""Point-in-time fundamentals for the validation backtest.

For each US company it downloads SEC company facts once and rebuilds the figures BullPulse uses
(sec_financials.financials and fetch_fundamentals.analyse) as they stood after every filing,
using only facts filed on or before that date. The backtest then takes, at each month-end, the
latest version filed by then, so it never sees numbers before they were published.

Share counts and per-share figures are as reported at the time. Prices in data/prices are
split-adjusted to today, so each row also carries `split`: the product of all later stock
splits, detected from jumps in the reported share count, to put the two on the same basis.

    python scripts/fundamentals_history.py [--universe universe] [--prices data/prices]
Writes data/fundamentals_pit.jsonl (not committed; rebuilt by the monthly validation run).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import time

from fetch_fundamentals import ERRORS, REVENUE as REV2, EPS as EPS2, analyse, contact, get
import sec_financials as SF

OUT = "data/fundamentals_pit.jsonl"
KEEP = set(SF.REVENUE + SF.NET_INCOME + SF.OP_INCOME + SF.EPS + SF.OCF + SF.CAPEX + SF.INTEREST + SF.DIV_PAID + SF.DPS +
           SF.EQUITY + SF.CASH + SF.ASSETS_CUR + SF.LIAB_CUR + SF.DEBT_LT + SF.DEBT_ST + SF.SHARES + SF.SBC + REV2 + EPS2)
SPLITS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 1.5, 0.5, 1 / 3, 0.25, 0.2, 0.1]


def trim(facts: dict) -> dict:
    g = {k: v for k, v in facts.get("facts", {}).get("us-gaap", {}).items() if k in KEEP}
    dei = {k: v for k, v in facts.get("facts", {}).get("dei", {}).items() if k == "EntityCommonStockSharesOutstanding"}
    return {"facts": {"us-gaap": g, "dei": dei}}


def upto(facts: dict, date: str) -> dict:
    """Only the facts filed on or before date."""
    out = {}
    for tax, concepts in facts["facts"].items():
        out[tax] = {}
        for c, body in concepts.items():
            units = {u: [r for r in rows if r.get("filed", "") <= date] for u, rows in body.get("units", {}).items()}
            units = {u: rows for u, rows in units.items() if rows}
            if units:
                out[tax][c] = {"units": units}
    return {"facts": out}


def split_ratio(a: float, b: float) -> float:
    """Share count went from a to b: the split ratio if it looks like a split, else 1."""
    if not a or not b:
        return 1.0
    r = b / a
    for s in SPLITS:
        if abs(r / s - 1) < 0.08 and (r > 1.4 or r < 0.7):
            return s
    return 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--prices", default="data/prices")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if not contact():
        print("::warning::Point-in-time fundamentals skipped: SEC_CONTACT_EMAIL is not set.")
        return
    stocks = []
    for f in sorted(glob.glob(os.path.join(args.universe, "*.csv"))):
        for r in csv.DictReader(open(f, newline="")):
            if r.get("market") != "UK" and r.get("cik") and os.path.exists(os.path.join(args.prices, (r.get("provider_ticker") or "") + ".csv")):
                stocks.append(r)
    if args.limit:
        stocks = stocks[: args.limit]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n_rows = 0
    with open(OUT, "w") as out:
        for i, s in enumerate(stocks):
            raw = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(s['cik']):010d}.json")
            time.sleep(0.2)
            if not raw:
                continue
            facts = trim(raw)
            dates = sorted({r.get("filed", "") for body in facts["facts"]["us-gaap"].values()
                            for rows in body.get("units", {}).values() for r in rows if r.get("filed")})
            rows = []
            for d in dates:
                sub = upto(facts, d)
                fin = SF.financials(sub)
                if not fin.get("shares"):
                    continue
                g = analyse(sub) or {}
                rows.append({"id": "US-" + s["ticker"].replace(".", ""), "date": d, "fin": fin,
                             **{k: g[k] for k in ("rev_growth", "rev_accel", "eps_growth") if k in g}})
            # later splits: multiply today's-basis factors from the newest row backwards
            factor = 1.0
            for k in range(len(rows) - 1, -1, -1):
                rows[k]["split"] = factor
                if k > 0:
                    factor *= split_ratio(rows[k - 1]["fin"]["shares"], rows[k]["fin"]["shares"])
            for r in rows:
                out.write(json.dumps(r, separators=(",", ":")) + "\n")
            n_rows += len(rows)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(stocks)}", flush=True)
    print(f"::notice::Point-in-time fundamentals: {n_rows} filing snapshots for {len(stocks)} companies")
    for e in ERRORS[:5]:
        print(f"::warning::SEC request failed: {e}")


if __name__ == "__main__":
    main()
