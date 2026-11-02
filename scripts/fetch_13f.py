"""Quarterly US holdings of well-known investors, from their SEC Form 13F filings.

Managers of more than $100m in US-listed shares must file Form 13F within 45 days of each quarter
end, listing their long positions. This keeps every 13F filed since 2015 by the investors below,
one JSON file each (data/history/13f/<slug>.json), and maps each holding's CUSIP to a ticker
(OpenFIGI's free mapping API, cached in data/history/cusip_map.json; issuer-name matching against
the universe when that fails).

Only new filings are downloaded, so a run after the first takes seconds. 13F shows long US
positions only: no short positions, bonds, cash or non-US shares, and it is up to 45 days old.

    python scripts/fetch_13f.py [--since 2015-01-01]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

OUT = "data/history/13f"
MAP = "data/history/cusip_map.json"

# slug, manager, firm as filed, SEC CIK, a line about the investor
INVESTORS = [
    ("buffett", "Warren Buffett", "Berkshire Hathaway", 1067983, "Long-term value investing in large, durable businesses."),
    ("ackman", "Bill Ackman", "Pershing Square Capital Management", 1336528, "A handful of large, simple, high-quality companies, sometimes as an activist."),
    ("terry-smith", "Terry Smith", "Fundsmith", 1569205, "Buy good companies, don't overpay, do nothing. US holdings of the UK fund manager."),
    ("nick-train", "Nick Train", "Lindsell Train", 1484150, "Very long holding periods in a few quality brands. US holdings of the UK fund manager."),
    ("klarman", "Seth Klarman", "Baupost Group", 1061768, "Deep value with a margin of safety."),
    ("akre", "Chuck Akre", "Akre Capital Management", 1112520, "Compounders: good businesses, good managers, good reinvestment."),
    ("tepper", "David Tepper", "Appaloosa", 1656456, "Opportunistic, often buying what others are selling."),
    ("druckenmiller", "Stanley Druckenmiller", "Duquesne Family Office", 1536411, "Macro-driven, concentrated bets that change quickly."),
    ("li-lu", "Li Lu", "Himalaya Capital Management", 1709323, "Very concentrated long-term value investing."),
    ("hohn", "Chris Hohn", "TCI Fund Management", 1647251, "A few dominant, high-margin businesses held for years. UK-based."),
    ("russo", "Tom Russo", "Gardner Russo & Quinn", 860643, "Global consumer brands with the capacity to reinvest."),
    ("kantesaria", "Dev Kantesaria", "Valley Forge Capital Management", 1697868, "A very small number of toll-road-like businesses."),
    ("dorsey", "Pat Dorsey", "Dorsey Asset Management", 1671657, "Companies with durable competitive advantages (economic moats)."),
    ("gayner", "Thomas Gayner", "Markel Group", 1096343, "Profitable businesses with good management at fair prices, held for decades."),
    ("burry", "Michael Burry", "Scion Asset Management", 1649339, "Contrarian and concentrated; changes positions often."),
]

ERRORS: list[str] = []


def ua() -> str:
    return f"BullPulse research {os.environ.get('SEC_CONTACT_EMAIL', '').strip()}"


def get(url: str, data: bytes | None = None, headers: dict | None = None, tries: int = 4):
    for i in range(tries):
        try:
            h = {"User-Agent": ua(), "Accept-Encoding": "identity"}
            h.update(headers or {})
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1) ** 2)
        except Exception:
            time.sleep(3 * (i + 1))
    ERRORS.append(url)
    return None


def filings(cik: int, since: str) -> list[dict]:
    """13F-HR filings (and amendments) since a date, oldest first."""
    raw = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not raw:
        return []
    d = json.loads(raw)
    tables = [d.get("filings", {}).get("recent", {})]
    for f in d.get("filings", {}).get("files", []):   # older filings live in extra pages
        if f.get("filingTo", "9999") >= since:
            x = get("https://data.sec.gov/submissions/" + f["name"])
            if x:
                tables.append(json.loads(x))
            time.sleep(0.2)
    out = []
    for t in tables:
        for k, form in enumerate(t.get("form", [])):
            if form in ("13F-HR", "13F-HR/A") and t["filingDate"][k] >= since:
                out.append({"acc": t["accessionNumber"][k], "form": form, "filed": t["filingDate"][k], "period": t.get("reportDate", [""] * (k + 1))[k]})
    return sorted(out, key=lambda f: (f["filed"], f["acc"]))


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def info_table(cik: int, acc: str) -> tuple[list[dict], str] | None:
    """The holdings in one filing: (rows, amendment type)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    idx = get(base + "index.json")
    if not idx:
        return None
    items = [i["name"] for i in json.loads(idx).get("directory", {}).get("item", [])]
    xmls = [n for n in items if n.lower().endswith(".xml")]
    amend = ""
    primary = next((n for n in xmls if "primary" in n.lower()), None)
    if primary:
        p = get(base + primary)
        if p:
            m = re.search(rb"<amendmentType>\s*([A-Z ]+)\s*<", p)
            amend = m.group(1).decode().strip() if m else ""
    table = next((n for n in xmls if n != primary and ("info" in n.lower() or "table" in n.lower())), None) or next((n for n in xmls if n != primary), None)
    if not table:
        return None
    raw = get(base + table)
    if not raw:
        return None
    return parse_table(raw), amend


def parse_table(raw: bytes) -> list[dict]:
    """Rows of a 13F information table (XML); options are left out."""
    rows = []
    for el in ET.fromstring(raw).iter():
        if strip_ns(el.tag) != "infoTable":
            continue
        v = {strip_ns(c.tag): (c.text or "").strip() for c in el.iter()}
        if v.get("putCall"):
            continue   # options, not shares
        try:
            rows.append({"cusip": v.get("cusip", "").upper(), "name": v.get("nameOfIssuer", ""), "class": v.get("titleOfClass", ""),
                         "value": float(v.get("value") or 0), "shares": float(v.get("sshPrnamt") or 0), "type": v.get("sshPrnamtType", "")})
        except ValueError:
            continue
    return rows


def aggregate(rows: list[dict], filed: str) -> list[dict]:
    """One line per security; values in dollars (before 2023 filings reported thousands)."""
    mult = 1000 if filed < "2023-01-03" else 1
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r["cusip"], {"cusip": r["cusip"], "name": r["name"], "class": r["class"], "value": 0.0, "shares": 0.0})
        a["value"] += r["value"] * mult
        a["shares"] += r["shares"] if r["type"] in ("SH", "") else 0
    return sorted(agg.values(), key=lambda a: -a["value"])


def figi(cusips: list[str], cache: dict) -> None:
    """Fill cache[cusip] = ticker via OpenFIGI (free, no key: 25 requests a minute, 10 ids each)."""
    todo = [c for c in cusips if c and c not in cache]
    for k in range(0, len(todo), 10):
        batch = todo[k:k + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch]).encode()
        raw = get("https://api.openfigi.com/v3/mapping", data=body, headers={"Content-Type": "application/json"}, tries=2)
        if raw is None:
            break
        try:
            res = json.loads(raw)
        except ValueError:
            break
        for c, r in zip(batch, res):
            data = r.get("data") or []
            eq = [x for x in data if x.get("marketSector") == "Equity"] or data
            cache[c] = (eq[0].get("ticker") or "") if eq else ""
        time.sleep(2.6)


NORM = re.compile(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|PLC|HLDGS?|HOLDINGS?|GROUP|CL [A-Z]|NEW|DEL|THE|COM|SHS|ORD|NV|SA|AG|LP|LLC)\b\.?")


def norm(name: str) -> str:
    n = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    return re.sub(r"\s+", " ", NORM.sub(" ", n)).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2015-01-01")
    ap.add_argument("--only", default="", help="comma-separated slugs (testing)")
    args = ap.parse_args()
    if not os.environ.get("SEC_CONTACT_EMAIL"):
        print("::warning::13F filings skipped: SEC_CONTACT_EMAIL is not set.")
        return 0
    os.makedirs(OUT, exist_ok=True)
    cache = json.load(open(MAP)) if os.path.exists(MAP) else {}
    # issuer names in the universe, for when OpenFIGI has no answer
    names = {}
    for f in glob.glob("universe/us*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            names[norm(r["name"])] = r["ticker"]
    new_total = 0
    for slug, manager, firm, cik, about in INVESTORS:
        if args.only and slug not in args.only.split(","):
            continue
        path = os.path.join(OUT, slug + ".json")
        doc = json.load(open(path)) if os.path.exists(path) else {"slug": slug, "manager": manager, "firm": firm, "cik": cik, "filings": []}
        doc.update({"manager": manager, "firm": firm, "cik": cik, "about": about})
        have = {f["acc"] for f in doc["filings"]}
        for f in filings(cik, args.since):
            if f["acc"] in have:
                continue
            got = info_table(cik, f["acc"])
            time.sleep(0.3)
            if not got:
                continue
            rows, amend = got
            if f["form"] == "13F-HR/A" and amend != "RESTATEMENT":
                continue   # "new holdings" amendments add a few lines; restatements replace the filing
            f["holdings"] = aggregate(rows, f["filed"])
            f["amendment"] = amend
            doc["filings"] = [x for x in doc["filings"] if not (f["form"] == "13F-HR/A" and x["period"] == f["period"])]
            doc["filings"].append(f)
            new_total += 1
        doc["filings"].sort(key=lambda x: (x["period"], x["filed"]))
        # one filing per quarter: the latest (a restatement replaces the original)
        byq = {}
        for x in doc["filings"]:
            byq[x["period"]] = x
        doc["filings"] = [byq[k] for k in sorted(byq)]
        cus = sorted({h["cusip"] for x in doc["filings"] for h in x.get("holdings", [])})
        figi(cus, cache)
        for x in doc["filings"]:
            for h in x.get("holdings", []):
                t = cache.get(h["cusip"]) or names.get(norm(h["name"]), "")
                h["ticker"] = t.replace("/", ".")
        json.dump(doc, open(path, "w"), separators=(",", ":"))
        print(f"  {slug}: {len(doc['filings'])} quarters", flush=True)
    json.dump(cache, open(MAP, "w"), separators=(",", ":"), sort_keys=True)
    print(f"::notice::13F: {new_total} new filings")
    for e in ERRORS[:5]:
        print(f"::warning::Request failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
