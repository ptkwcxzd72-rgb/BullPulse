"""Past members of the S&P MidCap 400 and SmallCap 600, from the holdings that index funds file
with the SEC, for backtests free of survivorship bias.

The iShares Core S&P Mid-Cap ETF (IJH) and Core S&P Small-Cap ETF (IJR) hold every member of
their index. Since late 2019 each files its full holdings every quarter on Form N-PORT (public
for the third month of each fiscal quarter), as structured XML. This finds those filings with
EDGAR's full-text search, reads each one, and keeps the common-stock holdings: name, CUSIP,
ISIN, ticker where given, shares and dollar value at the quarter-end, in
data/history/fund_holdings/<fund>/<report date>.csv. Each filing is read once.

The 2009-2019 holdings (Form N-Q, and N-CSR reports) are HTML tables and come next.

    python scripts/fund_holdings.py [--max 40]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OUT = "data/history/fund_holdings"
FUNDS = {
    # fund: (index, names the series has had)
    "ijh": ("S&P 400", ["iShares Core S&P Mid-Cap ETF", "iShares S&P MidCap 400 Index Fund", "iShares Core S&P Mid Cap ETF"]),
    "ijr": ("S&P 600", ["iShares Core S&P Small-Cap ETF", "iShares S&P SmallCap 600 Index Fund", "iShares Core S&P Small Cap ETF"]),
}
FTS = "https://efts.sec.gov/LATEST/search-index"


def contact() -> str:
    return os.environ.get("SEC_CONTACT_EMAIL", "").strip()


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": f"BullPulse research screener {contact()}", "Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
            time.sleep(0.15)
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def search(name: str, form: str = "NPORT-P") -> list[dict]:
    """Every filing of a form whose text contains the exact series name: [{adsh, cik, date}]."""
    out, start = [], 0
    while True:
        q = urllib.parse.urlencode({"q": f'"{name}"', "forms": form, "from": start})
        raw = get(f"{FTS}?{q}")
        if not raw:
            break
        d = json.loads(raw)
        hits = d.get("hits", {}).get("hits", [])
        for h in hits:
            s = h.get("_source", {})
            adsh = h.get("_id", "").split(":")[0]
            ciks = s.get("ciks") or []
            if adsh and ciks:
                out.append({"adsh": adsh, "cik": str(int(ciks[0])), "date": s.get("file_date", ""), "period": s.get("period_ending", "")})
        start += len(hits)
        if not hits or start >= d.get("hits", {}).get("total", {}).get("value", 0):
            break
    seen, uniq = set(), []
    for x in out:
        if x["adsh"] not in seen:
            seen.add(x["adsh"])
            uniq.append(x)
    return uniq


def strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def parse_nport(xml: bytes) -> tuple[str, str, list[dict]]:
    """(series name, report period date, common-stock holdings) from an N-PORT primary_doc.xml."""
    root = strip_ns(ET.fromstring(xml))
    gen = root.find(".//genInfo")
    series = (gen.findtext("seriesName") if gen is not None else "") or ""
    period = (gen.findtext("repPdDate") if gen is not None else "") or ""
    rows = []
    for inv in root.iter("invstOrSec"):
        cat = inv.findtext("assetCat") or ""
        if cat != "EC":       # equity, common
            continue
        ids = inv.find("identifiers")
        isin = ids.find("isin").get("value") if ids is not None and ids.find("isin") is not None else ""
        tick = ""
        if ids is not None:
            for o in ids.iter("other"):
                if (o.get("otherDesc") or "").lower().startswith("ticker"):
                    tick = o.get("value") or ""
            if ids.find("ticker") is not None:
                tick = ids.find("ticker").get("value") or tick
        rows.append({"name": inv.findtext("name") or "", "cusip": inv.findtext("cusip") or "", "isin": isin, "ticker": tick,
                     "shares": inv.findtext("balance") or "", "value_usd": inv.findtext("valUSD") or "",
                     "pct": inv.findtext("pctVal") or ""})
    return series.strip(), period.strip(), rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="filings to read this run")
    a = ap.parse_args()
    if not contact():
        print("::warning::Fund holdings skipped: SEC_CONTACT_EMAIL is not set.")
        return 0
    done_path = os.path.join(OUT, "read.json")
    os.makedirs(OUT, exist_ok=True)
    done = json.load(open(done_path)) if os.path.exists(done_path) else {}
    read = 0
    for fund, (index, names) in FUNDS.items():
        os.makedirs(os.path.join(OUT, fund), exist_ok=True)
        cands = {}
        for nm in names:
            for x in search(nm):
                cands[x["adsh"]] = x
        new = [x for x in sorted(cands.values(), key=lambda x: x["date"]) if x["adsh"] not in done]
        print(f"  {fund}: {len(cands)} N-PORT filings found, {len(new)} not read yet")
        for x in new:
            if read >= a.max:
                break
            xml = get(f"https://www.sec.gov/Archives/edgar/data/{x['cik']}/{x['adsh'].replace('-', '')}/primary_doc.xml")
            read += 1
            if not xml:
                continue
            try:
                series, period, rows = parse_nport(xml)
            except ET.ParseError:
                done[x["adsh"]] = "unreadable"
                continue
            if not any(series.lower() == n.lower() for n in names) or len(rows) < 100:
                done[x["adsh"]] = f"other series: {series}"[:80]
                continue
            path = os.path.join(OUT, fund, f"{period}.csv")
            with open(path, "w", newline="") as fh:
                w = csv.DictWriter(fh, ["name", "cusip", "isin", "ticker", "shares", "value_usd", "pct"])
                w.writeheader()
                w.writerows(rows)
            done[x["adsh"]] = f"{fund} {period} {len(rows)}"
            print(f"  {fund} {period}: {len(rows)} holdings ({index})")
    json.dump(done, open(done_path, "w"), indent=0, sort_keys=True)
    have = {f: len([p for p in os.listdir(os.path.join(OUT, f)) if p.endswith(".csv")]) for f in FUNDS}
    print(f"::notice::Fund holdings (N-PORT): {read} filings read this run; quarters on file: {have}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
