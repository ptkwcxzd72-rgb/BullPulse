"""Fama-French factor returns for the Strategy Lab's factor check (site/data/factors.json).

From Kenneth French's data library (free; cite Fama and French 2015 for the five factors and
Carhart 1997 for momentum): monthly US five factors and momentum, and the European ones for
portfolios of UK shares (French publishes no UK-only set; the Exeter UK factors stop in 2017).
All are in US dollars and per cent a month; they are stored as decimals.

    python scripts/fetch_factors.py [--out site/data/factors.json]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
SETS = {
    "us": ("F-F_Research_Data_5_Factors_2x3_CSV.zip", "F-F_Momentum_Factor_CSV.zip"),
    "europe": ("Europe_5_Factors_CSV.zip", "Europe_Mom_Factor_CSV.zip"),
}
UA = "Mozilla/5.0 (compatible; BullPulse research; +https://github.com/ptkwcxzd72-rgb/BullPulse)"


def monthly(text: str) -> dict[str, dict[str, float]]:
    """The monthly table of a French CSV: 'YYYY-MM' -> {column: decimal}. The file has a text
    preamble, then the monthly rows (YYYYMM), then annual rows (YYYY) after a blank line."""
    out: dict[str, dict[str, float]] = {}
    cols = None
    for row in csv.reader(io.StringIO(text)):
        cells = [c.strip() for c in row]
        if not cells or not any(cells):
            if out:
                break          # the annual table follows
            continue
        if cells[0] == "" and len(cells) > 1 and not cols:
            cols = cells[1:]
            continue
        if cols and len(cells[0]) == 6 and cells[0].isdigit():
            try:
                vals = [float(v) / 100 for v in cells[1:1 + len(cols)]]
            except ValueError:
                continue
            if any(v <= -0.99 for v in vals):   # -99.99: missing
                continue
            out[f"{cells[0][:4]}-{cells[0][4:]}"] = dict(zip(cols, vals))
        elif out:
            break
    return out


def fetch(name: str) -> str | None:
    try:
        req = urllib.request.Request(BASE + name, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        return z.read(z.namelist()[0]).decode("latin-1")
    except Exception as e:  # keep the previous file rather than fail the run
        print(f"::warning::Fama-French factors: {name} not downloaded ({e})")
        return None


def build(five: dict, mom: dict) -> dict:
    months = sorted(set(five) & set(mom))
    key = {"Mkt-RF": "mkt", "SMB": "smb", "HML": "hml", "RMW": "rmw", "CMA": "cma", "RF": "rf"}
    out = {"months": months}
    for src, k in key.items():
        out[k] = [round(five[m][src], 6) for m in months]
    mcol = next(iter(mom[months[0]])) if months else "Mom"
    out["mom"] = [round(mom[m][mcol], 6) for m in months]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data/factors.json")
    a = ap.parse_args()
    old = {}
    if os.path.exists(a.out):
        try:
            old = json.load(open(a.out))
        except Exception:
            old = {}
    res = {"source": "Kenneth R. French Data Library", "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
           "units": "decimal monthly returns in US dollars"}
    for k, (f5, fm) in SETS.items():
        t5, tm = fetch(f5), fetch(fm)
        if t5 and tm:
            res[k] = build(monthly(t5), monthly(tm))
        elif k in old:
            res[k] = old[k]
    if not any(k in res for k in SETS):
        print("::warning::Fama-French factors: nothing downloaded and no previous file")
        return 0
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(res, open(a.out, "w"), separators=(",", ":"))
    print("::notice::Fama-French factors: " + "; ".join(f"{k} {res[k]['months'][0]} to {res[k]['months'][-1]}" for k in SETS if k in res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
