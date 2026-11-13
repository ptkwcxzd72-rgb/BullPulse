"""S&P 400 and 600 membership intervals from the funds' quarterly holdings
(data/history/fund_holdings, scripts/fund_holdings.py), in the format of
universe/history/sp500_membership.csv: ticker, start_date, end_date (empty = still a member).

A company counts from the first quarter-end at which the fund held it to the first quarter-end at
which it no longer did, so a change is dated up to three months late (between filings). Before
the first filing on record the start is that filing's date. Holdings the fund kept for a few days
after a company left (rare at quarter-ends) would count it a quarter too long.

    python scripts/build_membership.py [--figi]
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re

SRC = "data/history/fund_holdings"
OUT = {"ijh": "universe/history/sp400_membership.csv", "ijr": "universe/history/sp600_membership.csv"}


TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


def norm(t: str) -> str:
    """A listed share's ticker, or '' for placeholders (rights, delisted lines such as 2200963D)."""
    t = t.strip().upper().replace("/", ".").replace(" ", ".")
    return t if TICKER.match(t) else ""


NAME_JUNK = re.compile(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|PLC|HOLDINGS?|HLDGS?|GROUP|THE|NEW|CLASS [A-Z]|CL [A-Z]|COM|LLC|LP|NV|SA|NVS)\b\.?")


def simple(name: str) -> str:
    """A company name reduced for matching: 'Healthcare Services Group, Inc.' = 'HEALTHCARE SERVICES GROUP INC'."""
    n = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return re.sub(r"\s+", " ", NAME_JUNK.sub(" ", n)).strip()


def name_tickers(files: list[str], cmap: dict[str, str]) -> dict[str, str]:
    """Simplified name -> ticker from the filings that identify the holding (the older schedules
    give names only), then from tickers found by scripts/departed.py (data/history/departed.json)."""
    m: dict[str, str] = {}
    for f in files:
        for r in csv.DictReader(open(f, newline="")):
            t = norm(r.get("ticker", "")) or cmap.get((r.get("cusip") or "")[:9], "")
            if t:
                m.setdefault(simple(r["name"]), t)
    p = "data/history/departed.json"
    if os.path.exists(p):
        try:
            for k, t in json.load(open(p)).get("ids", {}).items():
                if k.startswith("name:") and norm(t):
                    m.setdefault(k[5:], norm(t))
        except Exception:
            pass
    return m


def ticker_of(r: dict, cmap: dict[str, str], nmap: dict[str, str]) -> str:
    return norm(r.get("ticker", "")) or cmap.get((r.get("cusip") or "")[:9], "") or nmap.get(simple(r.get("name", "")), "")


def cusip_tickers(files: list[str]) -> dict[str, str]:
    """CUSIP -> ticker from the filings that give both (later N-PORTs do; earlier ones often
    don't), then from the 13F CUSIP map (data/history/cusip_map.json)."""
    m: dict[str, str] = {}
    p = "data/history/cusip_map.json"
    if os.path.exists(p):
        try:
            for c, v in json.load(open(p)).items():
                t = norm((v or {}).get("ticker", "") if isinstance(v, dict) else str(v or ""))
                if t:
                    m[c[:9]] = t
        except Exception:
            pass
    for f in files:
        for r in csv.DictReader(open(f, newline="")):
            t = norm(r.get("ticker", ""))
            if t and r.get("cusip"):
                m[r["cusip"][:9]] = t   # the filings themselves win
    return m


def intervals(snaps: list[tuple[str, set[str]]]) -> list[tuple[str, str, str]]:
    """[(ticker, start, end)] from dated sets of tickers, in date order."""
    out, open_ = [], {}
    for k, (d, ts) in enumerate(snaps):
        for t in ts:
            open_.setdefault(t, d)
        for t in list(open_):
            if t not in ts:
                out.append((t, open_.pop(t), d))
    out += [(t, s, "") for t, s in open_.items()]
    return sorted(out)


def figi_unmapped() -> None:
    """Look up the CUSIPs no filing gives a ticker for (mostly companies that have since left or
    been taken over) with OpenFIGI, through the 13F job's cached helper."""
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import fetch_13f as F
    files = sorted(glob.glob(os.path.join(SRC, "*", "*.csv")))
    cmap = cusip_tickers(files)
    todo = sorted({r["cusip"][:9] for f in files for r in csv.DictReader(open(f, newline=""))
                   if r.get("cusip") and not norm(r.get("ticker", "")) and r["cusip"][:9] not in cmap})
    cache = json.load(open(F.MAP)) if os.path.exists(F.MAP) else {}
    before = sum(1 for c in todo if cache.get(c))
    F.figi(todo, cache)
    json.dump(cache, open(F.MAP, "w"), separators=(",", ":"), sort_keys=True)
    print(f"::notice::OpenFIGI: {sum(1 for c in todo if cache.get(c) not in (None, '', '?')) - before} of {len(todo)} unmapped CUSIPs now have a ticker")


def main() -> None:
    import sys
    if "--figi" in sys.argv:
        figi_unmapped()
    for fund, path in OUT.items():
        files = sorted(glob.glob(os.path.join(SRC, fund, "*.csv")))
        cmap = cusip_tickers(files)
        nmap = name_tickers(files, cmap)
        snaps, unmapped = [], 0
        for f in files:
            ts = set()
            for r in csv.DictReader(open(f, newline="")):
                t = ticker_of(r, cmap, nmap)
                if t:
                    ts.add(t)
                elif float(r.get("pct") or 0) > 0.01:
                    unmapped += 1
            if len(ts) > 100:
                snaps.append((os.path.basename(f)[:10], ts))
        if not snaps:
            continue
        rows = intervals(snaps)
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "start_date", "end_date"])
            w.writerows(rows)
        print(f"::notice::{path}: {len(rows)} spans from {len(snaps)} quarter-ends ({snaps[0][0]} to {snaps[-1][0]}), "
              f"{sum(1 for r in rows if r[2])} departures; {unmapped} holdings without a ticker")


if __name__ == "__main__":
    main()
