"""Mid and small-cap universe files: universe/us400.csv (S&P MidCap 400) and universe/us600.csv
(S&P SmallCap 600), in the same columns as universe/us.csv.

Members, names and GICS sectors come from Wikipedia's constituent tables (kept current by its
editors; checked here against SEC records), and each company's SEC identifier (CIK) from the
SEC's own ticker file. A company the SEC file doesn't know is left out rather than guessed.
These stocks are scored nightly but kept out of the backtests until their membership history
is built (internal/core.SmallerIndexes).

    python scripts/build_smid_universe.py [--min 300]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

PAGES = {"S&P 400": ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "universe/us400.csv"),
         "S&P 600": ("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "universe/us600.csv")}
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SECTORS = {"Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials", "Health Care",
           "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities"}


def get(url: str, ua: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
        return gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b


class Tables(HTMLParser):
    """Every <table> as rows of cell texts."""
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.tables.append([])
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1
        elif self.depth == 1 and tag in ("td", "th") and self.cell is not None:
            self.row.append(re.sub(r"\s+", " ", html.unescape("".join(self.cell))).strip())
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def constituents(page: bytes) -> list[dict]:
    """(ticker, name, sector) from the first table with Symbol, Security and GICS Sector columns."""
    p = Tables()
    p.feed(page.decode("utf-8", "ignore"))
    for t in p.tables:
        if not t:
            continue
        head = [h.lower() for h in t[0]]
        try:
            ks = next(i for i, h in enumerate(head) if h in ("symbol", "ticker symbol", "ticker"))
            kn = next(i for i, h in enumerate(head) if h in ("security", "company"))
            kg = next(i for i, h in enumerate(head) if "gics sector" in h or h == "sector")
        except StopIteration:
            continue
        out = []
        for r in t[1:]:
            if len(r) > max(ks, kn, kg) and r[ks] and r[kg] in SECTORS:
                out.append({"ticker": r[ks].replace(" ", "").upper(), "name": re.sub(r"\[\w+\]$", "", r[kn]).strip(), "sector": r[kg]})
        if len(out) > 100:
            return out
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=300, help="refuse to write a list shorter than this")
    a = ap.parse_args()
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not contact:
        print("::warning::Mid and small-cap universe not rebuilt: SEC_CONTACT_EMAIL is not set.")
        return 0
    sec = json.loads(get(SEC_TICKERS, f"BullPulse research screener {contact}"))
    cik = {v["ticker"].upper().replace("-", "."): str(v["cik_str"]) for v in sec.values()}
    large = {r["ticker"] for r in csv.DictReader(open("universe/us.csv", newline=""))}
    seen = set(large)
    for index, (url, path) in PAGES.items():
        rows = constituents(get(url, "BullPulse universe builder (+https://github.com/ptkwcxzd72-rgb/BullPulse)"))
        out, missing = [], []
        for r in rows:
            t = r["ticker"].replace("-", ".")
            if t in seen:           # also in the S&P 500 list (an index move not yet reflected), or listed twice
                continue
            c = cik.get(t)
            if not c:
                missing.append(t)
                continue
            seen.add(t)
            out.append({"ticker": t, "name": r["name"], "sector": r["sector"], "market": "US", "cik": c,
                        "provider_ticker": t.lower().replace(".", "-"), "index": index})
        if len(out) < a.min:
            print(f"::warning::{index}: only {len(out)} members found; {path} left as it was")
            continue
        out.sort(key=lambda r: r["name"].lower())
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, ["ticker", "name", "sector", "market", "cik", "provider_ticker", "index"])
            w.writeheader()
            w.writerows(out)
        print(f"::notice::{index}: {len(out)} members written to {path}" + (f"; not in the SEC ticker file: {', '.join(missing[:15])}" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
