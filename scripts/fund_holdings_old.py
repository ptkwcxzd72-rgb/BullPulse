"""The S&P 400 and 600 funds' holdings before N-PORT (2009 to mid-2019), from their N-Q quarterly
schedules and N-CSR / N-CSRS shareholder reports: HTML schedules of investments listing each
holding's name, shares and value (no tickers or CUSIPs). Written like scripts/fund_holdings.py,
to data/history/fund_holdings/<fund>/<period>.csv, with names to be matched to tickers later.

    python scripts/fund_holdings_old.py --probe     # print the structure of a few filings
    python scripts/fund_holdings_old.py [--max 20]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fund_holdings as H  # noqa: E402

FORMS = ["N-Q", "N-CSR", "N-CSRS"]
SINCE = "2009-01-01"


def text_of(doc: str) -> str:
    doc = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?i)</(td|th)>", " | ", doc)
    doc = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", doc)
    doc = re.sub(r"<[^>]+>", " ", doc)
    doc = html.unescape(doc).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", doc))


def documents(cik: str, adsh: str) -> list[tuple[str, int]]:
    idx = H.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/index.json")
    items = json.loads(idx or b"{}").get("directory", {}).get("item", [])
    return [(i["name"], int(i.get("size") or 0)) for i in items if i["name"].lower().endswith((".htm", ".html", ".txt"))]


def probe() -> None:
    sid = H.series_ids(["IJH"])
    for form in FORMS:
        fs = [f for f in H.filings(sid["IJH"], form) if f["date"] >= SINCE]
        print(f"== {form}: {len(fs)} filings since {SINCE}: {[f['date'] for f in fs][:40]}")
        for f in fs[:1] + fs[len(fs) // 2: len(fs) // 2 + 1]:
            docs = documents(f["cik"], f["adsh"])
            print(f"  {f['date']} {f['adsh']} docs: {sorted(docs, key=lambda d: -d[1])[:6]}")
            big = max(docs, key=lambda d: d[1])[0] if docs else ""
            raw = H.get(f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{f['adsh'].replace('-', '')}/{big}")
            t = text_of((raw or b"").decode("utf-8", "ignore"))
            for m in list(re.finditer(r"(?i)s&p mid-?cap|mid-cap etf|midcap 400", t))[:3]:
                print("  ---", m.start(), repr(t[m.start(): m.start() + 900]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    if not H.contact():
        print("::warning::SEC_CONTACT_EMAIL is not set.")
        return 0
    if a.probe:
        probe()
    return 0


if __name__ == "__main__":
    sys.exit(main())
