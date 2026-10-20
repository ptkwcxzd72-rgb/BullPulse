"""Insider dealings for US companies from SEC Form 4 filings.

Directors and officers must report trades in their own company's shares on Form 4 within two
business days. Purchases in the open market (transaction code P) are the informative ones:
insiders sell for many reasons (tax, diversification, planned 10b5-1 sales) but usually buy for
one. Several different insiders buying within a few months ("cluster buying") is the pattern
BullPulse flags.

Each night: one request per company for its filing index (data.sec.gov/submissions), then one
request per Form 4 not seen before (cached in data/insiders/cache.json, so only new filings are
downloaded). Needs SEC_CONTACT_EMAIL like the fundamentals step.

    python scripts/fetch_insiders.py [--universe universe] [--prices data/prices] [--days 120]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from fetch_fundamentals import contact, user_agent

OUT = "data/insiders.json"
CACHE = "data/insiders/cache.json"
ERRORS: list[str] = []


def fetch(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip"})
    last = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return gzip.decompress(data) if r.headers.get("Content-Encoding") == "gzip" else data
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 404:
                break
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            last = type(e).__name__
            time.sleep(3 * (attempt + 1))
    ERRORS.append(f"{url.rsplit('/', 1)[-1]}: {last}")
    return None


def _t(el, path: str) -> str:
    x = el.find(path)
    return (x.text or "").strip() if x is not None and x.text else ""


def parse_form4(xml: bytes, issuer_cik: str) -> list[dict]:
    """Open-market purchases (P) and sales (S) of common stock in one Form 4."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    if _t(root, "issuer/issuerCik").lstrip("0") != issuer_cik.lstrip("0"):
        return []   # the company itself reporting a stake in another company
    owners = root.findall("reportingOwner")
    names, roles = [], []
    for o in owners:
        names.append(_t(o, "reportingOwnerId/rptOwnerName").title())
        rel = o.find("reportingOwnerRelationship")
        if rel is None:
            continue
        flag = lambda k: _t(rel, k) in ("1", "true")
        title = _t(rel, "officerTitle")
        roles.append(title if flag("isOfficer") and title else "Director" if flag("isDirector") else
                     "Officer" if flag("isOfficer") else "10% owner" if flag("isTenPercentOwner") else "Other")
    out = []
    for tx in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _t(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        try:
            sh = float(_t(tx, "transactionAmounts/transactionShares/value") or 0)
            px = float(_t(tx, "transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        if sh <= 0:
            continue
        out.append({"d": _t(tx, "transactionDate/value")[:10], "code": code, "who": "; ".join(names)[:80],
                    "role": (roles[0] if roles else "")[:60], "sh": round(sh), "px": round(px, 4), "val": round(sh * px)})
    return out


def summarise(txs: list[dict], today: dt.date, window: int = 90) -> dict:
    since = (today - dt.timedelta(days=window)).isoformat()
    recent = [t for t in txs if t["d"] >= since]
    buys = [t for t in recent if t["code"] == "P"]
    sells = [t for t in recent if t["code"] == "S"]
    return {
        "buyers": len({t["who"] for t in buys}), "buyVal": sum(t["val"] for t in buys),
        "sellers": len({t["who"] for t in sells}), "sellVal": sum(t["val"] for t in sells),
        "cluster": len({t["who"] for t in buys}) >= 2,
        "recent": sorted(txs, key=lambda t: t["d"], reverse=True)[:12],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--prices", default="data/prices", help="only stocks with a price file ('' for all)")
    ap.add_argument("--days", type=int, default=120, help="look-back for Form 4 filings")
    ap.add_argument("--pause", type=float, default=0.12)
    ap.add_argument("--budget-min", type=float, default=12, help="stop reading new filings after this many minutes")
    args = ap.parse_args()
    t0 = time.time()
    if not contact():
        print("::warning::Insider data skipped: SEC_CONTACT_EMAIL is not set.")
        return
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    today = dt.date.today()
    since = (today - dt.timedelta(days=args.days)).isoformat()
    stocks = []
    for f in sorted(glob.glob(os.path.join(args.universe, "*.csv"))):
        for r in csv.DictReader(open(f, newline="")):
            if r.get("market") == "UK" or not r.get("cik"):
                continue
            if args.prices and not os.path.exists(os.path.join(args.prices, (r.get("provider_ticker") or "") + ".csv")):
                continue
            stocks.append(r)
    out, new = {}, 0
    for r in stocks:
        cik = r["cik"].lstrip("0")
        raw = fetch(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        time.sleep(args.pause)
        if not raw:
            continue
        rec = json.loads(raw).get("filings", {}).get("recent", {})
        txs = []
        for form, acc, filed, doc in zip(rec.get("form", []), rec.get("accessionNumber", []), rec.get("filingDate", []), rec.get("primaryDocument", [])):
            if form != "4" or filed < since:
                continue
            if acc not in cache and time.time() - t0 > args.budget_min * 60:
                continue   # out of time: picked up on the next run (the cache keeps what was read)
            if acc not in cache:
                xml = fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc.rsplit('/', 1)[-1]}")
                time.sleep(args.pause)
                if xml is None:
                    continue
                cache[acc] = {"f": filed, "tx": parse_form4(xml, cik)}
                new += 1
            txs += cache[acc]["tx"]
        out["US-" + r["ticker"].replace(".", "")] = summarise(txs, today)
    # forget filings that have dropped out of the window
    cache = {k: v for k, v in cache.items() if v["f"] >= since}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    json.dump({"generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "window_days": 90, "stocks": out},
              open(OUT, "w"), separators=(",", ":"))
    clusters = sorted(k for k, v in out.items() if v["cluster"])
    print(f"::notice::Insiders: {len(out)} companies checked, {new} new Form 4 filings read; cluster buying at {len(clusters)}: {', '.join(clusters[:15])}")
    for e in ERRORS[:5]:
        print(f"::warning::SEC request failed: {e}")


if __name__ == "__main__":
    main()
